# Standard Order of Terms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the corpus ISO standard-order comparison — `@<`, `@>`, `@=<`, `@>=`, `compare/3`, `=..` — on an order that is ISO-correct, coherent with `'=='`, and sound for Clausal's own types.

**Architecture:** `_standard_order_key` in `clausal/logic/builtins/_helpers.py` already implements a total standard order and drives `sort/2`. Tasks 1-3 correct it; Tasks 4-5 expose it as quoted canonical predicates in `clausal/logic/builtins/iso_compare.py`; Task 6 proves the ISO identity across the whole surface and gates the corpus.

**Tech Stack:** Python 3, pytest, Scryer Prolog as the reference oracle.

**Spec:** `docs/superpowers/specs/2026-09-09-standard-order-of-terms-design.md`

## Global Constraints

- Python is `/workspace/clausal/venv/bin/python`, ALWAYS run with the repo root as cwd.
- Every standalone probe starts with `import sys, os; sys.path.insert(0, os.getcwd())` then `import clausal; assert os.getcwd() in clausal.__file__, clausal.__file__`. Without it you silently test the canonical install.
- Scryer: `/workspace/scryer-prolog/target/release/scryer-prolog`, goal on STDIN, NO `?- ` prefix.
- New predicates are reachable from `.clausal` ONLY as quoted canonical forms. NO infix surface is added. Bare infix `==` stays `nodes.ArithEq`; infix `is` stays unification; Python's `is`/`is not`/`in`/`not in` are untouched.
- Never edit a test to match the engine when it disagrees with Scryer. Pin the divergence with an `OPEN_iso_divergence` name and a docstring saying it documents rather than blesses.
- Every test written to catch a bug MUST be proven to FAIL before its fix, with the observed output recorded.
- Do NOT touch `clausal/logic/tabling.py` or `_tabling_core.c` (spec §8; the tabling half of A01-D001 is filed as `todo/a01-d001-tabling-half-2026-09-09.md`).
- Full-suite gate by failure-NAME set, ANSI-stripped with `sed -E 's/\x1b\[[0-9;]*m//g'`, both sets asserted NON-EMPTY before comparing.
- zsh: quote any `*.py` glob and any `====`.

---

### Task 1: Make `'=='` transitive

`'=='` is not an equivalence relation today, which makes the ISO identity in Task 6 impossible. Fix the comparison site only.

**Files:**
- Modify: `clausal/logic/builtins/iso_compare.py:211-225` (`_numeric_tag`)
- Test: `tests/iso/test_iso_compare_scryer.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_numeric_tag(x)` returns `type(x)` for `Decimal` and `Fraction` as it already does for `float`. Tasks 2 and 6 rely on every numeric type being its own kind.

- [ ] **Step 1: Write the failing test**

```python
def test_iso_identical_is_transitive_over_numeric_types():
    """`==` must be an equivalence relation: order-equality is transitive, so
    `compare(=, X, Y) <=> X == Y` (Task 6) is impossible without this."""
    from decimal import Decimal
    from fractions import Fraction
    values = [1, 1.0, True, Decimal(1), Fraction(1)]
    for a in values:
        for b in values:
            for c in values:
                if _iso_identical(a, b) and _iso_identical(b, c):
                    assert _iso_identical(a, c), (
                        f"{a!r} == {b!r} and {b!r} == {c!r} but {a!r} != {c!r}")
```

- [ ] **Step 2: Run it and record the failure**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso/test_iso_compare_scryer.py::test_iso_identical_is_transitive_over_numeric_types -q`
Expected: FAIL — `1.0 == Decimal('1') and Decimal('1') == 1 but 1.0 != 1`. Paste the exact assertion text into the commit message.

- [ ] **Step 3: Tag Decimal and Fraction**

```python
def _numeric_tag(x):
    """The numeric type tag of *x*, or None if *x* is not a tagged number.

    Every numeric type is its own kind, so `==` is an equivalence relation and
    `compare(=, X, Y) <=> X == Y` can hold (spec §4a). Returns a TYPE OBJECT —
    nothing is wrapped and no term representation changes.

    This is the COMPARISON site only. `tabling._normalize_for_key_py` and its C
    twin `do_normalize` keep the A01-D001 residual deliberately; see
    todo/a01-d001-tabling-half-2026-09-09.md.
    """
    if type(x) is int:
        return int
    if isinstance(x, (bool, float, complex, _Decimal, _Fraction)):
        return type(x)
    return None
```

Add `from decimal import Decimal as _Decimal` and `from fractions import Fraction as _Fraction` to the imports at the TOP of the module (the file already consolidated its imports there; do not add a third import block).

- [ ] **Step 4: Run the test and the whole iso suite**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso -q -p no:randomly`
Expected: the new test PASSES. The `_identity_table` rows for `Decimal(1)` vs `1` now expect `False` where they expected `True` — update that ONE row and say so in the commit; do not touch the representation-hole rows.

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/builtins/iso_compare.py tests/iso/test_iso_compare_scryer.py
git commit -m "fix(iso): '==' is an equivalence relation again"
```

---

### Task 2: Quantity into the number band, with the ISO tiebreak

**Files:**
- Modify: `clausal/logic/builtins/_helpers.py:719-720` (the number-band branch of `_standard_order_key`)
- Test: `tests/iso/test_standard_order.py` (create)

**Interfaces:**
- Consumes: Task 1's `_numeric_tag` contract (every numeric type its own kind).
- Produces: number-band keys of shape `(_ORD_NUM, dim_signature, magnitude, rank)`. Task 3 relies on the shape; Task 6 relies on rank distinctness matching `'=='`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from decimal import Decimal
from clausal.terms import Quantity
from clausal.logic.builtins._helpers import _standard_order_key as K

def _lt(a, b):
    return K(a) < K(b)

def test_iso_float_precedes_int_of_equal_value():
    assert _lt(1.0, 1)
    assert not _lt(1, 1.0)

def test_dimensionless_quantity_sorts_beside_its_plain_twin_not_equal_to_it():
    q = Quantity(5000, {})
    assert K(q) != K(5000)                      # '==' says they differ
    assert _lt(4999, q) and _lt(q, 5001)        # but it sorts among numbers

def test_quantity_is_in_the_number_band_not_the_opaque_band():
    assert K(Quantity(5, {"m": 1}))[0] == K(1)[0]

def test_quantities_group_by_dimension_then_value():
    kg2, m3, m5 = Quantity(2, {"kg": 1}), Quantity(3, {"m": 1}), Quantity(5, {"m": 1})
    assert _lt(kg2, m3) and _lt(m3, m5)

def test_cross_dimension_comparison_never_raises():
    assert _lt(Quantity(1, {"m": 1}), Quantity(1, {"s": 1})) in (True, False)
```

- [ ] **Step 2: Run and record the failures**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso/test_standard_order.py -q`
Expected: FAIL — float/int keys are equal, and `Quantity` keys in band 6.

- [ ] **Step 3: Implement**

Replace `_helpers.py:719-720` with:

```python
    if isinstance(term, Quantity):
        # An extension never interleaves between two ISO terms (spec §2), so
        # Quantity ranks after every ISO numeric type at equal value.
        return (_ORD_NUM, tuple(sorted(term.dims.items())), term.value,
                _NUMERIC_RANK_QUANTITY)
    if isinstance(term, (bool, int, float, _Fraction, _Decimal, _Real)):
        # ISO 7.2.1: at equal value a FLOAT precedes an INT. Ranks are
        # per-TYPE so two terms share a rank exactly when `_numeric_tag`
        # calls them the same kind — that is what makes
        # `compare(=, X, Y) <=> X == Y` hold by construction, not by luck.
        return (_ORD_NUM, (), term, _NUMERIC_RANK.get(type(term), 90))
```

and add above `_standard_order_key`:

```python
# float before int is ISO 7.2.1. The rest are Clausal extensions and follow,
# each its own kind, mirroring `iso_compare._numeric_tag`.
_NUMERIC_RANK = {float: 0, int: 1, bool: 2, _Decimal: 3, _Fraction: 4}
_NUMERIC_RANK_QUANTITY = 5
```

Import `Quantity` from `clausal.terms` at the top of `_helpers.py` if it is not already imported.

- [ ] **Step 4: Run the tests**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Verify the six ISO rules still hold**

```python
def test_the_six_iso_ordering_rules_are_unchanged():
    """Scryer-verified 2026-09-09; the number-band change must not move any
    ISO term relative to another ISO term (spec §2)."""
    from clausal.logic.variables import Var
    assert _lt(Var(), 1)                    # var before number
    assert _lt(1, ("a",))                   # number before atom
    assert _lt(("a",), ("f", 1))            # atom before compound
    assert _lt(("g", 1), ("f", 1, 2))       # arity before name
    assert _lt(("f", 1), ("f", 2))          # args left to right
    assert _lt([], ("a",))                  # [] is an atom
```

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/builtins/_helpers.py tests/iso/test_standard_order.py
git commit -m "fix(order): Quantity joins the number band; ISO float/int tiebreak"
```

---

### Task 3: Gate the `sort/2` fast path

**Files:**
- Modify: `clausal/logic/builtins/_helpers.py:812-822` (`_standard_order_sorted`)
- Test: `tests/iso/test_standard_order.py`

**Interfaces:**
- Consumes: Task 2's key shape.
- Produces: `_NATIVE_ORDER_SAFE`, a frozenset of exact types whose native `<` agrees with `_standard_order_key`.

- [ ] **Step 1: Write the failing test**

```python
from clausal.logic.builtins._helpers import _standard_order_sorted as S

def test_sort_is_not_input_order_dependent():
    """Measured before the fix: [1, 1.0] and [1.0, 1] sorted to themselves,
    so sort/2 had no stable opinion about equal-value int/float."""
    assert S([1, 1.0]) == S([1.0, 1])

def test_same_type_is_not_a_sufficient_guard_for_the_native_path():
    """All tuples, one type — but cells key ARITY-FIRST (ISO 7.2.1) while
    Python compares tuples elementwise."""
    assert S([("f", 1, 2), ("g", 1)]) == [("g", 1), ("f", 1, 2)]

def test_homogeneous_safe_types_still_take_the_native_path():
    assert S([3, 1, 2]) == [1, 2, 3]
    assert S(["b", "ab", "a"]) == ["a", "ab", "b"]
```

- [ ] **Step 2: Run and record the failures**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso/test_standard_order.py -q`
Expected: the first two FAIL.

- [ ] **Step 3: Implement**

```python
# Types whose native `<` is KNOWN to agree with `_standard_order_key`.
# Membership is a positive claim and needs a measurement; absence costs only
# speed. `tuple` is excluded because it is PROVEN wrong (cells key arity-first
# while Python compares elementwise); `list` because it is not proven right.
_NATIVE_ORDER_SAFE = frozenset({int, float, bool, str, bytes, _Decimal, _Fraction})


def _standard_order_sorted(items: list) -> list:
    """Sort *items* into the standard order of terms.

    `set(map(type, items))` is one C-level pass bounded by the number of
    DISTINCT types. `type()` rather than `isinstance()` is deliberate: exact
    identity keeps subclasses off the native path, which matters for `bool`
    (a subclass of `int`) and any future `Quantity` subclass.

    This replaces a `try/except TypeError` fallback that discovered
    incomparability by catching a failure — and so never fired for `Quantity`
    across dimensions, which returned nonsense instead of raising.
    """
    types = set(map(type, items))
    if len(types) == 1 and types.pop() in _NATIVE_ORDER_SAFE:
        return sorted(items)
    return sorted(items, key=_standard_order_key)
```

- [ ] **Step 4: Run the tests**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso tests/test_builtins_lists.py -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Measure the fast path's value**

```bash
/workspace/clausal/venv/bin/python -c "
import sys, os, timeit; sys.path.insert(0, os.getcwd())
import clausal; assert os.getcwd() in clausal.__file__, clausal.__file__
from clausal.logic.builtins._helpers import _standard_order_key as K
xs = list(range(20000, 0, -1))
print('native+scan', timeit.timeit(lambda: (set(map(type, xs)), sorted(xs)), number=20))
print('key path   ', timeit.timeit(lambda: sorted(xs, key=K), number=20))
"
```

Record both numbers in the commit message. If the scan costs more than the keys it saves, DELETE the fast path (`return sorted(items, key=_standard_order_key)` unconditionally) and say so — spec §5 leaves that call to the implementer, on evidence.

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/builtins/_helpers.py tests/iso/test_standard_order.py
git commit -m "fix(order): gate sort/2's native fast path by exact type"
```

---

### Task 4: The comparison predicates

**Files:**
- Modify: `clausal/logic/builtins/iso_compare.py` (append)
- Test: `tests/iso/test_standard_order_scryer.py` (create)

**Interfaces:**
- Consumes: `_standard_order_key` from Task 2.
- Produces: `'@<'/2`, `'@>'/2`, `'@=<'/2`, `'@>='/2`, `'compare'/3`. Task 6 calls `'compare'/3`.

- [ ] **Step 1: Write the failing oracle test**

```python
import pytest

ORDER_ROWS = [
    ("'@<'(1, a)", "yes"), ("'@<'(a, 1)", "no"),
    ("'@<'(f(1), f(2))", "yes"), ("'@<'(g(1), f(1,2))", "yes"),
    ("'@=<'(1, 1)", "yes"), ("'@>'(a, 1)", "yes"), ("'@>='(1, 1)", "yes"),
    ("'@<'(1.0, 1)", "yes"),
]

@pytest.mark.parametrize("goal,expected", ORDER_ROWS)
def test_order_operators_against_the_engine(goal, expected, run_clausal):
    assert _yesno(run_clausal, goal) == expected

@pytest.mark.parametrize("goal,expected", ORDER_ROWS)
def test_order_operators_against_scryer(goal, expected, scryer):
    assert scryer(f"({goal} -> write(yes) ; write(no)), nl, halt.") == expected

def test_no_two_order_operators_agree_on_every_row(run_clausal):
    """The predecessor branch shipped six comparison operators that were
    indistinguishable from one another for three review rounds."""
    ops = ["@<", "@>", "@=<", "@>="]
    pairs = [(1, 1), (1, 2), (2, 1)]
    sigs = {op: tuple(_yesno(run_clausal, f"'{op}'({a}, {b})") for a, b in pairs)
            for op in ops}
    assert len({*sigs.values()}) == len(ops), sigs
```

**Fixture signatures — do NOT guess these, they are not what they look like:**

```python
run_clausal(src: str, goal_head: tuple, nargs: int = 1) -> list[str]
    # src is a WHOLE .clausal module. `_hN` in it is substituted with a unique
    # module name. Returns one repr per solution, so a success is
    # [repr(("yes",))], not the string "yes".
scryer(goal: str, program: str = "") -> str
    # goal goes on STDIN with NO `?- ` prefix; returns the LAST stdout line.
```

Import the `_yesno` / `_yesno_src` helpers from `tests/iso/test_iso_compare_scryer.py` rather than rebuilding them — they already wrap `run_clausal` into the yes/no shape these rows use. Keep the engine test and the oracle test SEPARATE so a missing binary cannot retire engine coverage.

- [ ] **Step 2: Run and record the failures**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso/test_standard_order_scryer.py -q`
Expected: FAIL — `existence_error` for `@</2`.

- [ ] **Step 3: Implement**

```python
def _order_atom(a, b):
    """`<`, `=` or `>` as a bare str, for the atom cell the callers build."""
    ka = _standard_order_key(a)
    kb = _standard_order_key(b)
    if ka < kb:
        return "<"
    if kb < ka:
        return ">"
    return "="


def _register_order_cmp(name, accept):
    @_builtin(name, 2, fields=("a", "b"))
    def _cmp(a, b, trail, k):
        # `accept` is closed over, NOT a default argument: a default would
        # push (trail, k) past `_extract_fields_simple`'s params[:-2] and
        # register a /4 term class with two junk variables.
        if _order_atom(a, b) in accept:
            yield None
    return _cmp


_register_order_cmp("@<", ("<",))
_register_order_cmp("@>", (">",))
_register_order_cmp("@=<", ("<", "="))
_register_order_cmp("@>=", (">", "="))


@_builtin("compare", 3, fields=("order", "a", "b"))
def _iso_compare(order, a, b, trail, k):
    """ISO compare/3: unify Order with the atom `<`, `=` or `>`."""
    if _unify(order, (_order_atom(a, b),), trail):
        yield None
```

`_standard_order_key` is imported from `._helpers`; add it to the existing top-of-module import.

- [ ] **Step 4: Run the tests**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso -q -p no:randomly`
Expected: PASS.

- [ ] **Step 5: Prove the term classes are 2-arity**

```python
def test_order_predicates_register_two_arity_term_classes():
    from clausal.logic.builtins._registry import _BUILTIN_FIELDS
    for name in ("@<", "@>", "@=<", "@>=", "compare"):
        arity = 3 if name == "compare" else 2
        assert len(_BUILTIN_FIELDS[(name, arity)]) == arity, name
```

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/builtins/iso_compare.py tests/iso/test_standard_order_scryer.py
git commit -m "feat(iso): @<, @>, @=<, @>= and compare/3"
```

---

### Task 5: `'=..'` over the existing `univ/2`

**Files:**
- Modify: `clausal/logic/builtins/iso_compare.py` (append)
- Test: `tests/iso/test_standard_order_scryer.py`

**Interfaces:**
- Consumes: `_univ__2` from `clausal/logic/builtins/inspection.py:465`.
- Produces: `'=..'/2`.

- [ ] **Step 1: Write the failing test**

```python
UNIV_ROWS = [("'=..'(f(1,2), L), write(L)", "[f,1,2]"),
             ("'=..'(T, [f,1,2]), write(T)", "f(1,2)"),
             ("'=..'(a, L), write(L)", "[a]")]

@pytest.mark.parametrize("goal,expected", UNIV_ROWS)
def test_univ_against_the_engine(goal, expected, run_clausal):
    got = run_clausal(
        "-module(_hN, [p(X)])\n"
        f"p(X) <- ({goal})\n", ("p",))
    assert got == [repr(expected)]

@pytest.mark.parametrize("goal,expected", UNIV_ROWS)
def test_univ_against_scryer(goal, expected, scryer):
    assert scryer(f"{goal}, nl, halt.") == expected
```

- [ ] **Step 2: Run and record the failure**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso/test_standard_order_scryer.py -k univ -q`
Expected: FAIL — `existence_error` for `=../2`.

- [ ] **Step 3: Implement**

```python
@_builtin("=..", 2, fields=("term", "lst"))
def _iso_univ(term, lst, trail, k):
    """ISO `=..` (univ). The canonical spelling over the existing `univ/2`;
    no new logic, so the two spellings cannot drift apart."""
    yield from _univ__2(term, lst, trail, k)
```

Import `_univ__2` from `.inspection` at the top of the module.

- [ ] **Step 4: Run the tests**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso -q -p no:randomly`
Expected: PASS. If any row diverges from Scryer, PIN it as `OPEN_iso_divergence` rather than editing the expectation.

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/builtins/iso_compare.py tests/iso/test_standard_order_scryer.py
git commit -m "feat(iso): '=..' as the canonical spelling of univ/2"
```

---

### Task 6: The ISO identity, and the gates

**Files:**
- Test: `tests/iso/test_standard_order.py`
- Create: `implementation_plans/standard-order-corpus-gate-2026-09-09.md`

**Interfaces:**
- Consumes: Tasks 1-5.
- Produces: the identity property test and two gate reports.

- [ ] **Step 1: Write the identity property test**

```python
def test_compare_equals_iff_iso_identical():
    """ISO guarantees `compare(=, X, Y)` holds exactly when `X == Y`. This is
    the primary instrument for this branch: it is what makes the ordering and
    the identity one design rather than two that happen to agree today."""
    from decimal import Decimal
    from fractions import Fraction
    from clausal.terms import Quantity
    from clausal.logic.builtins.iso_compare import _iso_identical, _order_atom
    terms = [1, 1.0, True, Decimal(1), Fraction(1), Quantity(1, {}),
             Quantity(1, {"m": 1}), ("a",), ("b",), ("f", 1), ("f", 1, 2),
             ("g", 1), [], [1], [1, 2], "ab", b"ab", 2, 2.0]
    for a in terms:
        for b in terms:
            assert (_order_atom(a, b) == "=") == bool(_iso_identical(a, b)), (a, b)
```

- [ ] **Step 2: Run it**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/iso/test_standard_order.py::test_compare_equals_iff_iso_identical -q`
Expected: PASS. If it fails, the failing pair is a REAL incoherence — fix the ranking or the tag, never the test.

- [ ] **Step 3: Prove the property test discriminates**

Temporarily set `_NUMERIC_RANK = {}` in `_helpers.py`, re-run Step 2, and confirm it FAILS naming a specific pair. Then `git checkout -- clausal/logic/builtins/_helpers.py` and say you did. A property test that has only ever passed proves nothing.

- [ ] **Step 4: Full-suite gate**

```bash
/workspace/clausal/venv/bin/python -m pytest tests -q --continue-on-collection-errors -p no:randomly > /tmp/after.log 2>&1
sed -E 's/\x1b\[[0-9;]*m//g' /tmp/after.log | grep -E "^(FAILED|ERROR) " | sed -E 's/^(FAILED|ERROR) //; s/ - .*//' | sort -u > /tmp/after.txt
wc -l < /tmp/after.txt   # MUST be non-empty
```

Compare the NAME SET against the same extraction run on the branch point. `0 NEW` is the bar.

- [ ] **Step 5: Corpus gate**

Tasks 2 and 3 change `sort/2` output, so a corpus gate is REQUIRED before landing.

**The corpus is not in this repository** — `find /workspace/clausal -name '*.clausal' -path '*corpus*'` returns nothing, and the domain files live on the other side of the information barrier. This step therefore CANNOT be executed here, and must not be reported as done.

Instead: write `implementation_plans/standard-order-corpus-gate-2026-09-09.md` stating what needs measuring, and request the run from a lane that holds the corpus (iso-export-lane or corpus-lane). The request must name:

- the two commits to compare (branch point and this branch's tip);
- what to look for — any site whose `sort/2` or `msort/2` output changes, split into (a) equal-value int/float no longer collapsing, (b) `Decimal(1)` no longer collapsing with `1`, (c) anything else, which is a BUG not an intended change;
- that category (c) blocks landing outright, while (a) and (b) are the intended tiebreak and need a count, not a veto.

If the fallout in (a)/(b) is wide, backing out is a one-line revert of `_NUMERIC_RANK` — independent of Tasks 3-5. **Do not land on a green full-suite gate alone**: the suite does not contain the corpus, so it cannot see this class of change.

- [ ] **Step 6: Commit**

```bash
git add tests/iso/test_standard_order.py implementation_plans/standard-order-corpus-gate-2026-09-09.md
git commit -m "test(iso): compare(=, X, Y) holds exactly when X == Y"
```
