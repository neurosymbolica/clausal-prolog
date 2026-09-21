# Quantity Transfer Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a `Quantity` a marshal-clean functor-first transfer form, both directions, plus the explicit relation `quantity_number/2`, without changing what a same-interpreter seam does.

**Architecture:** Two transfer tables (`TO_TRANSFER` / `FROM_TRANSFER`) and two entry points (`to_transfer` / `from_transfer`) are added BESIDE the seam registry in `clausal/logic/python_terms.py`; they consult the transfer tables first and fall through to the seam converters, so a `Decimal` or a date inside a quantity reuses its existing entry. `Quantity` and `Fraction` register ONLY in the transfer tables. `quantity_number/2` is a units predicate in `clausal/modules/units.py` beside `make_quantity/3`. The seam functions `to_term` / `from_term` and the seam tables are not edited, and two tests pin that.

**Tech Stack:** Python 3.13, pytest, the engine's `_UnitsPredicate` + `_simple_to_trampoline` predicate pattern, `marshal` as the transfer oracle.

**Spec:** `docs/superpowers/specs/2026-09-16-quantity-transfer-form-design.md` (commit `8e26fdc9`), which builds on `docs/superpowers/specs/2026-09-14-retire-predicatemeta-section4-answer.md` §§2–5.

## Global Constraints

- Work happens in the worktree `/workspace/clausal-bug-fix/.claude/worktrees/iso-l3` on branch `feat/iso-l3-lowering-2026-09-14`. Run every command from that directory. Check `git branch --show-current` before every commit (a peer can check a branch out under you).
- Stage explicit paths only. Never `git add -A`, never bare `git stash` (shared clone).
- Python is `/workspace/clausal/venv/bin/python`, run FROM the worktree (cwd wins for `import clausal`). Every probe prints `clausal.__file__` and you check it starts with the worktree path.
- Tests are named as sentences, `test_<what_the_test_pins>`, matching the existing files.
- Do NOT edit `to_term`, `from_term`, `TO_TERM`, `FROM_TERM`, `register`, or `clausal/modules/py/datetime.py`. The spec's whole mechanism is that the seam stays untouched, and the harness lane's date migration measures against those.
- Do NOT edit `clausal/terms.py` structurally. If any line is inserted above `term_str`, `tests/test_funnel_lint.py` trips on its line-range allowlist; the plan inserts nothing there.
- Encoding, verbatim from the spec (the plan's tests assert exactly these):

      a dimension          ('metre', 1)
      dimensions, N >= 1   ('dimensions', ('metre', 1), ('second', -2))   sorted by atom on emit
      dimensionless        ('dimensionless',)
      a unit               ('unit', Ratio, Dims)                         always unit/2
      a quantity           ('quantity', Magnitude, Unit)                 always quantity/2
      a rational           ('rdiv', N, D)   D > 1, lowest terms, sign on N
      EMIT ratio is ALWAYS 1.  READ multiplies the ratio through, exactly.

- Commit trailer on every commit:

      Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
      Claude-Session: https://claude.ai/code/session_01G3Bi6ruQWgu7WHKrYWPTT9

- No mention of the exporter repo's name or its files in any commit, test, or docstring (information barrier).

---

## File map

| file | responsibility |
|---|---|
| `clausal/logic/python_terms.py` (modify, additive) | transfer tables, `register_transfer`, `to_transfer`, `from_transfer`; the `Fraction`/`rdiv` entry; `_dims_to_term` / `_dims_from_term` (the ONE place that knows the dims slot has two functors); `_quantity_to_term` / `_quantity_from_term`; module docstring gains a TRANSFER section |
| `clausal/modules/units.py` (modify, additive, after `make_quantity`) | `_quantity_number_impl`, `quantity_number = _UnitsPredicate("quantity_number")` arity 2 |
| `tests/value_terms/test_quantity_transfer.py` (create) | the transfer layer, in Python: tables, fall-through, `rdiv`, the encoding table, marshal, sort, order-insensitive read, ratio-through-read, the two seam pins |
| `tests/test_quantity_number.py` (create) | `quantity_number/2` through the engine (`_load_module` + `call`), all seven modes |

---

### Task 0: Baseline and the blind-spot list (no code change)

**Files:**
- Read only. Output goes to `/home/node/.claude/jobs/af5b4bbe/tmp/` (the gate script's home) — NOT into the repo.

**Interfaces:**
- Produces: `qt-baseline.raw` (the failure SET before any edit) and `qt-red-in-touched.txt` (already-red tests in the files this plan touches), consumed by Task 5.

The branch baseline is RED (order of 145 failures). A failure-set diff cannot see a regression in a test that is already red, so the tests that are red in the touched files are enumerated BEFORE the first edit and each one's reason recorded.

- [ ] **Step 1: Confirm the tree and that the gate script runs THIS worktree**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
git branch --show-current            # expect feat/iso-l3-lowering-2026-09-14
git status --short | wc -l           # expect 0
git rev-parse --short HEAD           # record it: this is TREE-SHA for the baseline
grep -n '^WT=' /home/node/.claude/jobs/af5b4bbe/tmp/gate_iso_l3.sh   # expect this worktree's path
ls /home/node/.claude/jobs/af5b4bbe/tmp/nocleanup.py /home/node/.claude/jobs/af5b4bbe/tmp/failure_diff.py
```

Expected: branch as above, clean, both helper files present. If `nocleanup.py` is missing the gate would run ZERO tests and report exit 1 — stop and find it before continuing.

- [ ] **Step 2: Run the baseline in the background and wait for it**

```bash
rm -f /home/node/.claude/jobs/af5b4bbe/tmp/qt-baseline.raw
nohup /home/node/.claude/jobs/af5b4bbe/tmp/gate_iso_l3.sh /home/node/.claude/jobs/af5b4bbe/tmp/qt-baseline.raw >/dev/null 2>&1 &
```

Wait for the file to contain a line starting with `EXIT=` (the run takes on the order of 15–25 minutes). Then:

```bash
grep -e '^TREE-SHA' -e '^IMPORTED' -e '^PLUGIN-OK' -e '^RUN-EXIT' /home/node/.claude/jobs/af5b4bbe/tmp/qt-baseline.raw
grep -c '^FAILED' /home/node/.claude/jobs/af5b4bbe/tmp/qt-baseline.raw
tail -3 /home/node/.claude/jobs/af5b4bbe/tmp/qt-baseline.raw
```

Expected: `TREE-SHA` equals the sha recorded in Step 1; `IMPORTED` names a path under the worktree; `PLUGIN-OK nocleanup`; a FAILED count in the low hundreds (NOT zero — zero means the extraction is broken, not that the tree is green); the summary line shows on the order of 16,000 passed.

- [ ] **Step 3: Enumerate the already-red tests in the touched files**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
sed 's/\x1b\[[0-9;]*[mK]//g' /home/node/.claude/jobs/af5b4bbe/tmp/qt-baseline.raw \
  | grep -E '^(FAILED|ERROR) (tests/value_terms/|tests/test_units|tests/test_quantity|tests/test_currency|tests/test_funnel_lint)' \
  | tee /home/node/.claude/jobs/af5b4bbe/tmp/qt-red-in-touched.txt
echo "red-in-touched: $(wc -l < /home/node/.claude/jobs/af5b4bbe/tmp/qt-red-in-touched.txt)"
```

Expected: a count, printed. If it is 0, run the positive control below so the zero is a measurement, not a broken grep:

```bash
sed 's/\x1b\[[0-9;]*[mK]//g' /home/node/.claude/jobs/af5b4bbe/tmp/qt-baseline.raw | grep -c '^FAILED tests/'
```

Expected: the same low-hundreds count as Step 2 (proves the ANSI-strip + prefix grep works on this file).

For each red test in the touched files, run it alone and write its one-line reason after its name in `qt-red-in-touched.txt`:

```bash
/workspace/clausal/venv/bin/python -m pytest "<nodeid>" -q --tb=line 2>&1 | tail -3
```

- [ ] **Step 4: Measure the fixture values the tests will assert**

The plan's expected values below were derived from the spec's measurements; confirm them on this tree before writing tests that assert them:

```bash
/workspace/clausal/venv/bin/python - <<'EOF'
import clausal, marshal
from decimal import Decimal
from fractions import Fraction
assert clausal.__file__.startswith("/workspace/clausal-bug-fix/.claude/worktrees/iso-l3/"), clausal.__file__
from clausal.terms import Quantity
from clausal.modules import units
from clausal.modules.countries import european_union as eu
q1 = Quantity(5, units.kilometre);            print("5 km      ", repr(q1.value), dict(q1.dims))
q2 = Quantity(Decimal("1550.00"), eu.euro);   print("1550.00 eur", repr(q2.value), dict(q2.dims))
q3 = Quantity(3, units.percent);              print("3 percent ", repr(q3.value), dict(q3.dims))
q4 = Quantity(300, units.basis_point);        print("300 bp    ", repr(q4.value), dict(q4.dims), "== 3 percent:", q4 == q3)
q5 = Quantity(Fraction(10, 3), units.metre);  print("10/3 metre", repr(q5.value), dict(q5.dims))
q6 = Quantity(1, units.metre) * Quantity(1, units.second); print("m*s       ", dict(q6.dims))
print("percent ratio", repr(units.percent.value), dict(units.percent.dims))
try:
    marshal.dumps(q1); print("MARSHAL OF OBJECT: succeeded (UNEXPECTED)")
except Exception as e:
    print("marshal of object raises:", type(e).__name__)
EOF
```

Expected (record the actual output in the task's commit message if anything differs, and adjust the test constants to the MEASURED values):

```
5 km        5000 {'metre': 1}
1550.00 eur Decimal('1550.00') {'euro': 1}
3 percent   Decimal('0.03') {}
300 bp      Decimal('0.0300') {} == 3 percent: True
10/3 metre  Fraction(10, 3) {'metre': 1}
m*s         {'metre': 1, 'second': 1}   (order may differ; the dict is order-insensitive)
percent ratio Decimal('0.01') {}
marshal of object raises: ValueError
```

- [ ] **Step 5: Nothing to commit.** Record in your working notes: baseline sha, FAILED count, red-in-touched count.

---

### Task 1: The transfer layer and the `Fraction` → `rdiv/2` entry

**Files:**
- Modify: `clausal/logic/python_terms.py` — add after the `register(tuple, TUPLE_TAG, ...)` line (currently line ~191) and before `_SCALARS`; add `from fractions import Fraction` to the imports.
- Create: `tests/value_terms/test_quantity_transfer.py`

**Interfaces:**
- Consumes: `to_term(value, *, strict)`, `from_term(value)`, `TO_TERM`, `FROM_TERM`, `TUPLE_TAG`, `_SCALARS`, `_already_a_term`, `_is_already_engine_term` — all already in the module.
- Produces (later tasks rely on these exact names):
  - `TO_TRANSFER: dict[type, Any]`, `FROM_TRANSFER: dict[str, Any]`
  - `register_transfer(cls: type, functor: str, to_fn, from_fn) -> None`
  - `to_transfer(value) -> Any` — raises `TypeError` for a `Var` and for an unregistered non-engine class
  - `from_transfer(value) -> Any` — a malformed or unregistered term comes back UNCHANGED (same policy as `from_term`)
  - the `Fraction` entry: `Fraction(-10, 3)` ⇄ `('rdiv', -10, 3)`

- [ ] **Step 1: Write the failing tests**

Create `tests/value_terms/test_quantity_transfer.py`:

```python
"""The TRANSFER form: for boundaries that cannot carry an object.

Spec: docs/superpowers/specs/2026-09-16-quantity-transfer-form-design.md.
The transfer layer sits BESIDE the seam registry. A same-interpreter seam
passes the object (ruled 2026-09-15); only a subinterpreter, a process
boundary or a bytecode cache needs the term. So ``to_term``/``from_term``
must keep passing a Quantity through, and ``to_transfer``/``from_transfer``
must not.
"""
import datetime
import marshal
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.python_terms import (
    FROM_TERM, FROM_TRANSFER, TO_TERM, TO_TRANSFER,
    from_term, from_transfer, register_transfer, to_term, to_transfer,
)


# ── the layer itself ─────────────────────────────────────────────────────────

def test_the_transfer_tables_are_separate_from_the_seam_tables():
    assert TO_TRANSFER is not TO_TERM
    assert FROM_TRANSFER is not FROM_TERM
    assert Fraction in TO_TRANSFER and Fraction not in TO_TERM
    assert "rdiv" in FROM_TRANSFER and "rdiv" not in FROM_TERM


def test_to_transfer_falls_through_to_the_seam_registry_for_a_decimal():
    assert to_transfer(Decimal("10.01")) == ("decimal", 1001, 2)


def test_to_transfer_falls_through_for_a_date_and_a_scalar():
    assert to_transfer(datetime.date(2026, 9, 16)) == ("date", 2026, 9, 16)
    assert to_transfer(7) == 7


def test_to_transfer_REFUSES_a_logic_variable():
    from clausal.logic.variables import Var
    with pytest.raises(TypeError, match="logic variable"):
        to_transfer(Var())


def test_to_transfer_is_strict_about_an_unregistered_class():
    class Nope:
        pass
    with pytest.raises(TypeError, match="no registered conversion"):
        to_transfer(Nope())


def test_to_transfer_recurses_through_a_list_a_dict_and_a_data_tuple():
    assert to_transfer([Fraction(1, 2)]) == [("rdiv", 1, 2)]
    assert to_transfer({"k": Fraction(1, 2)}) == {"k": ("rdiv", 1, 2)}
    assert to_transfer((Fraction(1, 2), 3)) == ("()", ("rdiv", 1, 2), 3)


def test_from_transfer_recurses_the_same_way():
    assert from_transfer([("rdiv", 1, 2)]) == [Fraction(1, 2)]
    assert from_transfer({"k": ("rdiv", 1, 2)}) == {"k": Fraction(1, 2)}
    assert from_transfer(("()", ("rdiv", 1, 2), 3)) == (Fraction(1, 2), 3)


def test_from_transfer_falls_through_to_the_seam_registry():
    assert from_transfer(("decimal", 1001, 2)) == Decimal("10.01")
    assert from_transfer(("date", 2026, 9, 16)) == datetime.date(2026, 9, 16)


def test_from_transfer_leaves_an_unregistered_functor_UNCHANGED():
    t = ("cite", ("art52",))
    assert from_transfer(t) is t


def test_registering_a_transfer_type_twice_is_REFUSED():
    with pytest.raises(ValueError, match="already"):
        register_transfer(Fraction, "rdiv2", lambda v: v, lambda t: t)


def test_registering_a_transfer_functor_twice_is_refused_too():
    class Fresh:
        pass
    with pytest.raises(ValueError, match="already"):
        register_transfer(Fresh, "rdiv", lambda v: v, lambda t: t)


def test_a_transfer_entry_may_not_shadow_a_seam_entry():
    class Fresh2:
        pass
    with pytest.raises(ValueError, match="already"):
        register_transfer(Decimal, "decimal2", lambda v: v, lambda t: t)
    with pytest.raises(ValueError, match="already"):
        register_transfer(Fresh2, "decimal", lambda v: v, lambda t: t)


# ── Fraction <-> rdiv/2 ───────────────────────────────────────────────────────

def test_a_fraction_becomes_rdiv_with_the_sign_on_the_numerator():
    assert to_transfer(Fraction(-10, 3)) == ("rdiv", -10, 3)


def test_rdiv_comes_back_as_the_same_fraction():
    assert from_transfer(("rdiv", -10, 3)) == Fraction(-10, 3)


def test_an_rdiv_that_is_not_in_lowest_terms_or_has_a_bad_denominator_is_unchanged():
    # from_transfer's policy is from_term's: a look-alike is not a term
    for t in (("rdiv", 2, 4), ("rdiv", 1, 1), ("rdiv", 1, 0), ("rdiv", 1, -3),
              ("rdiv", "1", 3), ("rdiv", 1), ("rdiv", 1.5, 2), ("rdiv", True, 2)):
        assert from_transfer(t) is t, t


def test_an_rdiv_term_is_marshal_clean():
    t = to_transfer(Fraction(-10, 3))
    assert marshal.loads(marshal.dumps(t)) == t


# ── the seam is UNCHANGED for a Fraction ─────────────────────────────────────

def test_the_seam_still_passes_a_fraction_through_on_the_implicit_path():
    f = Fraction(1, 3)
    assert to_term(f, strict=False) is f


def test_the_seam_still_refuses_a_fraction_on_the_strict_path():
    with pytest.raises(TypeError, match="no registered conversion"):
        to_term(Fraction(1, 3), strict=True)


def test_the_seam_leaves_an_rdiv_term_alone():
    t = ("rdiv", 1, 3)
    assert from_term(t) is t
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/value_terms/test_quantity_transfer.py -q 2>&1 | tail -3
```

Expected: collection error `ImportError: cannot import name 'FROM_TRANSFER'`. (One error, not 20 failures — that is fine; it proves the names do not exist yet.)

- [ ] **Step 3: Implement the layer**

In `clausal/logic/python_terms.py`:

Add to the imports (after `from decimal import Decimal`):

```python
from fractions import Fraction
```

Extend `__all__`:

```python
__all__ = ["to_term", "from_term", "register", "TO_TERM", "FROM_TERM",
           "to_transfer", "from_transfer", "register_transfer",
           "TO_TRANSFER", "FROM_TRANSFER"]
```

Insert the following block immediately AFTER the existing `register(tuple, TUPLE_TAG, _tuple_to_term, _tuple_from_term)` line and BEFORE the `_SCALARS` definition. (`_SCALARS`, `_is_already_engine_term` and `_already_a_term` are defined below this point in the file; the functions here reference them only at call time, which is fine.)

```python
# ═══════════════════════════════════════════════════════════════════════════
# THE TRANSFER LAYER -- beside the seam registry, not inside it
# ═══════════════════════════════════════════════════════════════════════════
#
# A same-interpreter seam PASSES THE OBJECT (ruled 2026-09-15): a quantity
# stands in for a number and must reach ``#=/2`` as itself. Only a boundary
# that cannot carry an object -- a subinterpreter, a process, a bytecode
# cache -- needs a term. Those entries live HERE, in their own tables, so
# that nothing consulting the seam registry (``py.datetime``'s wrapper, a
# ``++`` hook) can ever convert a quantity at a seam. ``to_transfer`` and
# ``from_transfer`` consult these tables FIRST and fall through to the seam
# converters, which is what makes a Decimal magnitude or a date inside a
# quantity free: one dispatcher, every registered shape.
#
# The transfer tables are also where a ``Fraction`` lives. It cannot be a
# seam entry: the engine has no arithmetic on an ``rdiv`` term yet (that is
# sequenced with the CLP(Q) C port), so a divided money value crossing a
# seam as a term would silently stop computing.
#
# Spec: docs/superpowers/specs/2026-09-16-quantity-transfer-form-design.md

#: Python type -> the function yielding its TRANSFER term. Exact type, as
#: for ``TO_TERM``, and for the same reason.
TO_TRANSFER: "dict[type, Any]" = {}

#: Functor string -> the function rebuilding the Python value from a
#: transfer term.
FROM_TRANSFER: "dict[str, Any]" = {}


def register_transfer(cls: type, functor: str, to_fn, from_fn) -> None:
    """Add a transfer-only conversion. OVERRIDING IS REFUSED, and so is
    shadowing a SEAM entry: one class, one shape, whichever layer owns it."""
    if cls in TO_TRANSFER or cls in TO_TERM:
        raise ValueError(
            f"register_transfer: {cls.__name__} already has a conversion; "
            f"overriding is not allowed")
    if functor in FROM_TRANSFER or functor in FROM_TERM:
        raise ValueError(
            f"register_transfer: functor {functor!r} is already registered; "
            f"overriding is not allowed")
    TO_TRANSFER[cls] = to_fn
    FROM_TRANSFER[functor] = from_fn


def _fraction_to_term(f: Fraction) -> tuple:
    """``Fraction`` -> ``('rdiv', N, D)``. A Fraction is always in lowest terms
    with the sign on the numerator, and an integral one never reaches here as
    a Fraction (the engine presents it as an int), so nothing normalises."""
    return ("rdiv", f.numerator, f.denominator)


def _fraction_from_term(t: tuple) -> Fraction:
    """The reverse. Anything that is not ``rdiv(int, int)`` in lowest terms
    with ``D > 1`` is a look-alike and raises, which ``from_transfer`` turns
    into "unchanged" -- the same policy as ``from_term``."""
    _, n, d = t                              # ValueError if the arity is wrong
    for x in (n, d):
        if type(x) is not int:               # bool is a subclass; refuse it
            raise TypeError("rdiv components must be ints")
    if d <= 1:
        raise ValueError("rdiv denominator must be > 1")
    f = Fraction(n, d)
    if (f.numerator, f.denominator) != (n, d):
        raise ValueError("rdiv is not in lowest terms")
    return f


register_transfer(Fraction, "rdiv", _fraction_to_term, _fraction_from_term)


def _already_a_transfer_term(value: tuple) -> bool:
    """A tuple already in transfer form must not be wrapped as data -- the
    same DOCUMENTED HAZARD as ``_already_a_term``, one layer up."""
    if _already_a_term(value):
        return True
    return type(value[0]) is str and value[0] in FROM_TRANSFER


def to_transfer(value: Any) -> Any:
    """*value* as a TRANSFER term, recursively.

    Differs from ``to_term`` in exactly two ways: it consults ``TO_TRANSFER``
    first, and it does NOT wave an engine-owned object through -- a transfer
    is the one place a Quantity must not pass as itself. It is always strict:
    a caller asking for a transfer form has nowhere to put an object.
    """
    if isinstance(value, _SCALARS):
        return value
    from clausal.logic.variables import Var  # noqa: PLC0415
    if isinstance(value, Var):
        raise TypeError("to_transfer: a logic variable has no transfer form; "
                        "bind it or leave it out of the transferred term")
    convert = TO_TRANSFER.get(type(value))
    if convert is not None:
        return convert(value)
    if isinstance(value, list):
        return [to_transfer(v) for v in value]
    if isinstance(value, dict):
        return {to_transfer(k): to_transfer(v) for k, v in value.items()}
    if isinstance(value, tuple):
        if _already_a_transfer_term(value):
            return value
        return (TUPLE_TAG,) + tuple(to_transfer(e) for e in value)
    if _is_already_engine_term(value):
        # An engine term type with no transfer entry (an AttVar, say). It IS
        # the representation; nothing to convert.
        return value
    return to_term(value, strict=True)


def from_transfer(value: Any) -> Any:
    """A TRANSFER term back to its Python value, recursively.

    ``FROM_TRANSFER`` first, then the seam registry. A term with no registered
    functor, or a look-alike whose components do not fit, comes back
    UNCHANGED -- the same policy as ``from_term``, for the same reason.
    """
    if isinstance(value, _SCALARS):
        return value
    if isinstance(value, list):
        return [from_transfer(v) for v in value]
    if isinstance(value, dict):
        return {from_transfer(k): from_transfer(v) for k, v in value.items()}
    if type(value) is not tuple or not value or type(value[0]) is not str:
        return value
    if value[0] == TUPLE_TAG:
        return tuple(from_transfer(e) for e in value[1:])
    rebuild = FROM_TRANSFER.get(value[0])
    if rebuild is None:
        return from_term(value)
    try:
        return rebuild(value)
    except (TypeError, ValueError, OverflowError):
        return value
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/value_terms/test_quantity_transfer.py tests/value_terms/test_python_to_term.py -q 2>&1 | tail -3
```

Expected: all pass in both files (the second file is the seam's own suite: it must be untouched by this task). If `test_python_to_term.py` had red tests in Task 0's list, they stay red with the SAME reason; anything else is a regression of this task.

- [ ] **Step 5: Commit**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
git branch --show-current
git add clausal/logic/python_terms.py tests/value_terms/test_quantity_transfer.py
git commit -m "python_terms: a TRANSFER layer beside the seam registry, and Fraction <-> rdiv/2

TO_TRANSFER/FROM_TRANSFER with to_transfer/from_transfer that consult them
first and fall through to the seam converters. A seam passes the object
(ruled 2026-09-15); only a boundary that cannot carry one needs the term,
so those entries live in their own tables where no seam consumer can reach
them. Fraction is the first entry: rdiv(N, D), sign on N, refused as a seam
entry because the engine has no arithmetic on the term yet.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01G3Bi6ruQWgu7WHKrYWPTT9"
```

---

### Task 2: `Quantity` → term (emit), and the dims-slot helper

**Files:**
- Modify: `clausal/logic/python_terms.py` — append after `from_transfer` (end of the transfer block).
- Modify: `tests/value_terms/test_quantity_transfer.py` — append.

**Interfaces:**
- Consumes: `to_transfer`, `register_transfer` (Task 1); `clausal.terms.Quantity` with `.value` and `.dims` (a `MappingProxyType` over an atom-keyed dict).
- Produces:
  - `_dims_to_term(dims: Mapping[str, int]) -> tuple` — `('dimensionless',)` for empty, else `('dimensions', *sorted(dims.items()))`
  - `_dims_from_term(t) -> dict[str, int]` — raises `TypeError`/`ValueError` on anything else (Task 3 uses it)
  - `_quantity_to_term(q) -> tuple` registered under functor `"quantity"`; `_quantity_from_term` is a STUB in this task that raises `NotImplementedError` and is replaced in Task 3.

- [ ] **Step 1: Confirm a module-level import of `Quantity` is cycle-free**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -c "
import sys, clausal
assert clausal.__file__.startswith('/workspace/clausal-bug-fix/.claude/worktrees/iso-l3/'), clausal.__file__
print('terms loaded before python_terms:', 'clausal.terms' in sys.modules)
import clausal.logic.python_terms
print('python_terms imported OK')
"
```

Expected: `terms loaded before python_terms: True` (importing the `clausal` package already loads `clausal.terms`, so a top-level `from clausal.terms import Quantity` inside `python_terms` cannot start a cycle). If it prints `False`, use the lazy form in Step 3 instead (import `Quantity` inside `_ensure_quantity_registered()` and call that at the top of `to_transfer`/`from_transfer`).

- [ ] **Step 2: Write the failing tests** (append to `tests/value_terms/test_quantity_transfer.py`)

```python
# ── Quantity -> term (EMIT) ───────────────────────────────────────────────────

from clausal.logic.python_terms import _dims_from_term, _dims_to_term  # noqa: E402
from clausal.modules import units  # noqa: E402
from clausal.modules.countries import european_union as eu  # noqa: E402
from clausal.terms import Quantity  # noqa: E402


def test_the_dims_slot_helper_emits_dimensionless_for_an_empty_map():
    assert _dims_to_term({}) == ("dimensionless",)


def test_the_dims_slot_helper_SORTS_on_emit():
    assert _dims_to_term({"second": -2, "metre": 1}) == \
        ("dimensions", ("metre", 1), ("second", -2))


def test_five_kilometre_emits_as_5000_metre_with_ratio_ONE():
    # The object has no ratio slot: the ratio is always 1 on emit (spec §3).
    q = Quantity(5, units.kilometre)
    assert to_transfer(q) == \
        ("quantity", 5000, ("unit", 1, ("dimensions", ("metre", 1))))


def test_money_emits_its_decimal_magnitude_WITH_its_scale():
    q = Quantity(Decimal("1550.00"), eu.euro)
    assert to_transfer(q) == \
        ("quantity", ("decimal", 155000, 2), ("unit", 1, ("dimensions", ("euro", 1))))


def test_three_percent_emits_as_a_dimensionless_decimal():
    q = Quantity(3, units.percent)
    assert to_transfer(q) == \
        ("quantity", ("decimal", 3, 2), ("unit", 1, ("dimensionless",)))


def test_a_divided_value_emits_an_rdiv_magnitude():
    q = Quantity(Fraction(10, 3), units.metre)
    assert to_transfer(q) == \
        ("quantity", ("rdiv", 10, 3), ("unit", 1, ("dimensions", ("metre", 1))))


def test_a_two_dimension_quantity_emits_its_dims_sorted():
    q = Quantity(1, units.metre) * Quantity(1, units.second)
    assert to_transfer(q) == \
        ("quantity", 1, ("unit", 1, ("dimensions", ("metre", 1), ("second", 1))))


def test_a_quantity_inside_a_list_converts_too():
    q = Quantity(5, units.kilometre)
    assert to_transfer([q]) == \
        [("quantity", 5000, ("unit", 1, ("dimensions", ("metre", 1))))]


def test_every_emitted_transfer_term_is_marshal_clean_and_the_object_is_NOT():
    qs = [Quantity(5, units.kilometre), Quantity(Decimal("1550.00"), eu.euro),
          Quantity(3, units.percent), Quantity(Fraction(10, 3), units.metre),
          Quantity(1, units.metre) * Quantity(1, units.second)]
    for q in qs:
        t = to_transfer(q)
        assert marshal.loads(marshal.dumps(t)) == t, t
    with pytest.raises(ValueError):          # positive control
        marshal.dumps(qs[0])


# ── the seam is UNCHANGED for a Quantity ─────────────────────────────────────

def test_the_seam_still_passes_a_quantity_through_as_ITSELF():
    q = Quantity(5, units.kilometre)
    assert to_term(q, strict=True) is q
    assert to_term(q, strict=False) is q
    assert Quantity not in TO_TERM
```

- [ ] **Step 3: Run the new tests to verify they fail**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/value_terms/test_quantity_transfer.py -q 2>&1 | tail -3
```

Expected: collection error `ImportError: cannot import name '_dims_from_term'`.

- [ ] **Step 4: Implement emit** (append to the transfer block in `python_terms.py`, after `from_transfer`)

```python
# ── the dims slot: dimensions/N OR the atom dimensionless ──────────────────
#
# The dims slot carries TWO functors (spec §3, section-4 answer §4): the
# word ``dimensionless`` already names the concept, so the empty case is that
# atom rather than a degenerate ``('dimensions',)``. The cost is that "the
# dims slot has functor dimensions" is not free -- so it is said HERE, once,
# and every site goes through these two functions.

def _dims_to_term(dims) -> tuple:
    """An atom-keyed dims mapping -> its transfer term, SORTED by atom.

    The stored dict is order-insensitive; the sort is a boundary step so an
    emitted term is one term. ``dims.items()`` pairs are already
    ``('metre', 1)`` -- functor-first ``metre(1)`` -- so nothing is rebuilt."""
    if not dims:
        return ("dimensionless",)
    return ("dimensions", *sorted(dims.items()))


def _dims_from_term(t) -> dict:
    """The reverse: ``('dimensionless',)`` or ``('dimensions', *pairs)`` ->
    an atom-keyed dict. Order-insensitive. Raises on anything else."""
    if type(t) is not tuple or not t or type(t[0]) is not str:
        raise TypeError("dims slot is not a term")
    if t == ("dimensionless",):
        return {}
    if t[0] != "dimensions" or len(t) < 2:
        raise TypeError("dims slot is neither dimensionless nor dimensions/N")
    dims: dict = {}
    for pair in t[1:]:
        if (type(pair) is not tuple or len(pair) != 2
                or type(pair[0]) is not str or type(pair[1]) is not int
                or pair[1] == 0 or pair[0] in dims):
            raise TypeError(f"not a dimension pair: {pair!r}")
        dims[pair[0]] = pair[1]
    return dims


# ── Quantity <-> quantity/2 ──────────────────────────────────────────────────

from clausal.terms import Quantity  # noqa: E402  (cycle-free: the package loads terms first)


def _quantity_to_term(q: Quantity) -> tuple:
    """``quantity(Magnitude, unit(1, Dims))``. The ratio is ALWAYS 1 on emit:
    the object normalised at construction and keeps no ratio, so ``5
    kilometre`` emits as 5000 metre. The magnitude goes through
    ``to_transfer`` so a Decimal keeps its scale and a Fraction becomes
    rdiv."""
    return ("quantity", to_transfer(q.value), ("unit", 1, _dims_to_term(q.dims)))


def _quantity_from_term(t: tuple) -> Quantity:
    raise NotImplementedError("read side lands in the next commit")


register_transfer(Quantity, "quantity", _quantity_to_term, _quantity_from_term)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/value_terms/ -q 2>&1 | tail -3
```

Expected: all tests in `tests/value_terms/` pass except any listed in Task 0's red-in-touched file (same reasons). Note `from_transfer(('quantity', ...))` now hits the stub; `NotImplementedError` is NOT in `from_transfer`'s caught set, so it propagates — that is intended for this commit and is closed in Task 3.

- [ ] **Step 6: Commit**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
git branch --show-current
git add clausal/logic/python_terms.py tests/value_terms/test_quantity_transfer.py
git commit -m "transfer form: Quantity EMITS quantity(M, unit(1, Dims)), dims sorted, marshal-clean

One helper pair owns the two-functor dims slot (dimensions/N or the atom
dimensionless). The ratio is always 1 on emit because the object keeps
none. The seam is pinned unchanged: to_term still returns the object.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01G3Bi6ruQWgu7WHKrYWPTT9"
```

---

### Task 3: term → `Quantity` (read), ratio multiplied through exactly

**Files:**
- Modify: `clausal/logic/python_terms.py` — replace the `_quantity_from_term` stub.
- Modify: `tests/value_terms/test_quantity_transfer.py` — append.

**Interfaces:**
- Consumes: `_dims_from_term`, `from_transfer` (Tasks 1–2); `Quantity(value, dims_dict)` accepts an atom-keyed dict; `Quantity._num_pair(a, b)` (staticmethod) coerces a float/Decimal/Fraction pair so multiplication stays exact.
- Produces: `_quantity_from_term(t) -> Quantity`, raising `TypeError`/`ValueError` on a malformed term (which `from_transfer` turns into "unchanged"). Task 4 relies on: `from_transfer(t)` returns a `Quantity` for a well-formed term and returns `t` itself otherwise.

- [ ] **Step 1: Write the failing tests** (append)

```python
# ── term -> Quantity (READ) ───────────────────────────────────────────────────

def test_an_emitted_term_reads_back_to_an_EQUAL_object():
    for q in (Quantity(5, units.kilometre), Quantity(Decimal("1550.00"), eu.euro),
              Quantity(3, units.percent), Quantity(Fraction(10, 3), units.metre),
              Quantity(1, units.metre) * Quantity(1, units.second)):
        back = from_transfer(to_transfer(q))
        assert isinstance(back, Quantity)
        assert back == q, q
        assert hash(back) == hash(q)


def test_an_AUTHORED_ratio_is_multiplied_through_on_read():
    # written by an author: 5 in a unit whose ratio to the standard unit is 1000
    t = ("quantity", 5, ("unit", 1000, ("dimensions", ("metre", 1))))
    assert from_transfer(t) == Quantity(5, units.kilometre)


def test_a_decimal_ratio_stays_EXACT_on_read():
    # 3 percent, written with the ratio rather than pre-scaled
    t = ("quantity", 3, ("unit", ("decimal", 1, 2), ("dimensionless",)))
    q = from_transfer(t)
    assert q == Quantity(3, units.percent)
    assert isinstance(q.value, Decimal) and q.value == Decimal("0.03")


def test_an_rdiv_ratio_and_an_rdiv_magnitude_compose_exactly():
    t = ("quantity", ("rdiv", 1, 3), ("unit", ("rdiv", 1, 2), ("dimensions", ("metre", 1))))
    q = from_transfer(t)
    assert q.value == Fraction(1, 6) and isinstance(q.value, Fraction)


def test_read_is_ORDER_INSENSITIVE_in_the_dims_slot():
    sorted_t = ("quantity", 1, ("unit", 1, ("dimensions", ("metre", 1), ("second", 1))))
    unsorted = ("quantity", 1, ("unit", 1, ("dimensions", ("second", 1), ("metre", 1))))
    assert from_transfer(unsorted) == from_transfer(sorted_t)


def test_a_dimensionless_term_reads_to_an_empty_dims_map():
    q = from_transfer(("quantity", 4, ("unit", 1, ("dimensionless",))))
    assert isinstance(q, Quantity) and dict(q.dims) == {} and q.value == 4


def test_a_MALFORMED_quantity_term_comes_back_unchanged():
    bad = [
        ("quantity", 5),                                              # arity
        ("quantity", 5, ("unit", 1)),                                 # unit arity
        ("quantity", 5, ("units", 1, ("dimensionless",))),            # wrong functor
        ("quantity", 5, ("unit", 1, ("dimensions",))),                # empty dimensions/N
        ("quantity", 5, ("unit", 1, ("dimensions", ("metre", 0)))),   # zero exponent
        ("quantity", 5, ("unit", 1, ("dimensions", ("metre", 1), ("metre", 2)))),  # dup
        ("quantity", "5", ("unit", 1, ("dimensionless",))),           # magnitude not a number
        ("quantity", 5, ("unit", "1", ("dimensionless",))),           # ratio not a number
        ("quantity", True, ("unit", 1, ("dimensionless",))),          # bool is not a number
        ("quantity", 5, ("unit", 1, ("dimensions", ("metre", "1")))), # exponent not int
    ]
    for t in bad:
        assert from_transfer(t) is t, t


def test_the_seam_leaves_a_quantity_term_ALONE():
    t = ("quantity", 5000, ("unit", 1, ("dimensions", ("metre", 1))))
    assert from_term(t) is t
    assert "quantity" not in FROM_TERM
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/value_terms/test_quantity_transfer.py -q -k "read or READ or ratio or MALFORMED or ORDER or dimensionless_term or seam_leaves_a_quantity" 2>&1 | tail -3
```

Expected: the read tests fail with `NotImplementedError` (from the stub); the seam-pin passes already.

- [ ] **Step 3: Replace the stub**

```python
_NUMBER_TYPES = (int, float, Decimal, Fraction)


def _transfer_number(x):
    """A magnitude or ratio slot -> a Python number, or raise."""
    n = from_transfer(x)
    if isinstance(n, bool) or not isinstance(n, _NUMBER_TYPES):
        raise TypeError(f"not a number term: {x!r}")
    return n


def _quantity_from_term(t: tuple) -> Quantity:
    """``('quantity', M, ('unit', R, Dims))`` -> the object, with ``R``
    multiplied through EXACTLY: an int magnitude with a Decimal ratio stays
    Decimal, a Fraction with a Fraction stays Fraction (``_num_pair`` is the
    class's own coercion). The object then normalises as it always does --
    an integral Fraction presents as an int, a currency magnitude becomes
    Decimal -- so an emitted term reads back to an EQUAL object."""
    _, magnitude, unit = t                   # ValueError if the arity is wrong
    if type(unit) is not tuple or len(unit) != 3 or unit[0] != "unit":
        raise TypeError("the unit slot must be unit/2")
    _, ratio, dims_term = unit
    m = _transfer_number(magnitude)
    r = _transfer_number(ratio)
    dims = _dims_from_term(dims_term)
    if r == 1:
        value = m
    else:
        a, b = Quantity._num_pair(m, r)
        value = a * b
    return Quantity(value, dims)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/value_terms/ tests/test_dims_keyed_by_atoms.py tests/test_quantity_dims_storage.py -q 2>&1 | tail -3
```

Expected: all pass (modulo Task 0's red list, same reasons).

- [ ] **Step 5: Commit**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
git branch --show-current
git add clausal/logic/python_terms.py tests/value_terms/test_quantity_transfer.py
git commit -m "transfer form: a quantity term READS back to the object, ratio multiplied through exactly

An authored ratio (5 in a unit of ratio 1000) is a read-side affordance:
_num_pair keeps int x Decimal and Fraction x Fraction exact, and the object
then normalises as it always does. A malformed term comes back unchanged,
the same policy as from_term. The seam is pinned: from_term leaves a
quantity term alone.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01G3Bi6ruQWgu7WHKrYWPTT9"
```

---

### Task 4: `quantity_number/2`

**Files:**
- Modify: `clausal/modules/units.py` — add `_quantity_number_impl` next to `_make_dimensioned_impl` (currently ~line 551) and the registration line right after `make_quantity._register(3, ...)` (~line 652).
- Create: `tests/test_quantity_number.py`

**Interfaces:**
- Consumes: `to_transfer`, `from_transfer` (Tasks 1–3, imported lazily inside the impl); `deref`, `is_var`, `unify` (already imported in `units.py`); `_UnitsPredicate`, `_simple_to_trampoline` (already in `units.py`); `clausal.logic.solve._deref_walk` (lazy import, as `builtins/io.py` does); `clausal.logic.exceptions.LogicException`, `type_error(expected, culprit, context)`, `instantiation_error(context)`.
- Produces: the predicate `quantity_number/2`, importable as `-import_from(py.units, [quantity_number])`. Modes, verbatim from spec §4:

      (-Term, +Object)   Term unifies with to_transfer(Object); ratio 1
      (+Term, -Object)   Object unifies with from_transfer(Term); ratio multiplied through
      (+Term, +Object)   build from Term, unify the objects (value equality)
      (-, -)             instantiation_error
      Term bound, malformed        type_error(quantity, Term)   -- RAISED, never quiet failure
      Term bound to a Quantity obj treated as the object itself
      Object bound, not a Quantity plain failure

- [ ] **Step 1: Write the failing tests**

Create `tests/test_quantity_number.py`:

```python
"""quantity_number/2 -- the EXPLICIT conversion between a quantity's transfer
term and the object (spec 2026-09-16-quantity-transfer-form-design.md §4).

Driven through the engine, not through Python calls: every test loads a
.clausal module and runs a goal with call().
"""
from decimal import Decimal

import pytest

from clausal import Var
from clausal.import_hook import _load_module
from clausal.logic.atoms import mint
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import deref
from clausal.modules import units
from clausal.terms import Quantity


def _load(tmp_path, src, name):
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return _load_module(name, str(p)).__dict__["$module"]


PRELUDE = (
    "-import_from(py.units, [kilometre, percent, basis_point, quantity_number])\n"
    "-private([quantity(A, B), unit(A, B), dimensions(A), metre(A), dimensionless, decimal(A, B)])\n"
)
# MEASURED 2026-09-16 (controller probe, this tree): with these declarations
# `X is quantity(5, unit(1000, dimensions(metre(1))))` binds X to the tuple
# ('quantity', 5, ('unit', 1000, ('dimensions', ('metre', 1)))), `dimensionless`
# arrives as ('dimensionless',), and a bound R inlines. `is` is unification in
# .clausal source (`=` is Python syntax, `==` is arithmetic equality). `metre` is
# NOT imported here on purpose: an imported unit name in argument position builds
# a Quantity, not the dimension pair metre(1). Each functor arity needs its own
# declaration, so multi-dimension terms in source are out; Task 3 covers them.


def _solutions(mod, functor, *args):
    return [tuple(deref(a) for a in args) for _ in call(functor, *args, module=mod)]


def test_object_to_term_emits_ratio_one(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "emit(T) <- (eval_(5(kilometre), Q), quantity_number(T, Q))\n", "qn_emit")
    t = Var()
    sols = _solutions(mod, "emit", t)
    assert sols == [(("quantity", 5000, ("unit", 1, ("dimensions", ("metre", 1)))),)]


def test_term_to_object_multiplies_the_ratio_through(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "read(Q) <- quantity_number(quantity(5, unit(1000, dimensions(metre(1)))), Q)\n",
        "qn_read")
    q = Var()
    sols = _solutions(mod, "read", q)
    assert len(sols) == 1 and sols[0][0] == Quantity(5, units.kilometre)


def test_both_bound_compares_by_VALUE(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "same <- (eval_(5(kilometre), Q), quantity_number(quantity(5, unit(1000, dimensions(metre(1)))), Q))\n"
        "pct <- (eval_(300(basis_point), Q), quantity_number(quantity(3, unit(decimal(1, 2), dimensionless)), Q))\n"
        "diff <- (eval_(6(kilometre), Q), quantity_number(quantity(5, unit(1000, dimensions(metre(1)))), Q))\n",
        "qn_both")
    assert _solutions(mod, "same") == [()]
    assert _solutions(mod, "pct") == [()]
    assert _solutions(mod, "diff") == []


def test_both_unbound_is_an_instantiation_error(tmp_path):
    mod = _load(tmp_path, PRELUDE + "bad(T, Q) <- quantity_number(T, Q)\n", "qn_inst")
    with pytest.raises(LogicException) as ei:
        list(call("bad", Var(), Var(), module=mod))
    assert ei.value.term.args[0] == mint("instantiation_error")


def test_a_malformed_term_RAISES_a_type_error_rather_than_failing_quietly(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "bad(Q) <- quantity_number(quantity(5, units(1, dimensionless)), Q)\n", "qn_type")
    with pytest.raises(LogicException) as ei:
        list(call("bad", Var(), module=mod))
    inner = ei.value.term.args[0]
    assert inner.functor == "type_error" and inner.args[0] == mint("quantity")


def test_a_term_slot_holding_a_bound_variable_still_reads(tmp_path):
    # the term is walked (deep deref) before it is read
    mod = _load(tmp_path, PRELUDE +
        "read(Q) <- (R is 1000, quantity_number(quantity(5, unit(R, dimensions(metre(1)))), Q))\n",
        "qn_deref")
    q = Var()
    sols = _solutions(mod, "read", q)
    assert len(sols) == 1 and sols[0][0] == Quantity(5, units.kilometre)


def test_a_term_slot_holding_an_UNBOUND_variable_is_an_instantiation_error(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "partial(Q) <- quantity_number(quantity(5, unit(R, dimensions(metre(1)))), Q)\n",
        "qn_partial")
    with pytest.raises(LogicException) as ei:
        list(call("partial", Var(), module=mod))
    assert ei.value.term.args[0] == mint("instantiation_error")


def test_the_object_on_the_term_side_is_taken_as_itself(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "same <- (eval_(5(kilometre), Q), quantity_number(Q, Q))\n", "qn_obj")
    assert _solutions(mod, "same") == [()]


def test_a_non_quantity_on_the_object_side_just_fails(tmp_path):
    mod = _load(tmp_path, PRELUDE + "nope(T) <- quantity_number(T, 7)\n", "qn_fail")
    assert _solutions(mod, "nope", Var()) == []


def test_the_relation_is_reachable_by_import_only(tmp_path):
    # no import: the name is not a builtin
    mod = _load(tmp_path, "-import_from(py.units, [metre])\n"
                          "emit(T) <- (eval_(5(metre), Q), quantity_number(T, Q))\n", "qn_noimp")
    with pytest.raises(LogicException):
        list(call("emit", Var(), module=mod))
```

Note on the last test: if the engine's behaviour for an undefined predicate is an `existence_error` raised at LOAD time rather than at call time, move the `pytest.raises` around `_load`. Either is acceptable; the point pinned is that the name is not global.

- [ ] **Step 2: Run to verify they fail**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/test_quantity_number.py -q 2>&1 | tail -5
```

Expected: every test fails at load or call with an error naming `quantity_number` as unknown/not exported from `py.units` (the last test may already pass; that is fine).

- [ ] **Step 3: Implement**

In `clausal/modules/units.py`, directly after `_make_dimensioned_impl`:

```python
def _quantity_number_impl(term, number, trail):
    """quantity_number(QuantityTerm, Number): the EXPLICIT conversion between
    a quantity's transfer term and the object (spec 2026-09-16, §4).

    In Clausal ``Number`` is the OBJECT: a quantity stands in for a number
    and must reach ``#=/2`` as itself. A Prolog with no units binds the
    magnitude scaled to the standard unit instead; that half lives in the
    exporter's per-dialect prelude, not here.

    Modes: (-T, +Q) emits, ratio 1; (+T, -Q) reads, ratio multiplied
    through; (+T, +Q) compares by value; (-, -) instantiation_error; a
    bound but malformed T is a type_error -- RAISED, because a malformed
    term that failed quietly would be the "goal just stops holding" shape.
    """
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, instantiation_error, type_error)
    from clausal.logic.python_terms import from_transfer, to_transfer  # noqa: PLC0415
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    from clausal.logic.variables import Var as _Var  # noqa: PLC0415

    t, n = deref(term), deref(number)
    if is_var(t):
        if is_var(n):
            raise LogicException(instantiation_error("quantity_number/2"))
        if not isinstance(n, Quantity):
            return                              # the relation does not hold
        if unify(t, to_transfer(n), trail):
            yield None
        return
    if isinstance(t, Quantity):
        built = t                               # the object, taken as itself
    else:
        walked = _deref_walk(t)                 # bound vars inside the term
        if _holds_var(walked):
            raise LogicException(instantiation_error("quantity_number/2"))
        built = from_transfer(walked)
        if not isinstance(built, Quantity):
            raise LogicException(type_error("quantity", walked, "quantity_number/2"))
    if unify(n, built, trail):
        yield None


def _holds_var(term) -> bool:
    """True if an UNBOUND variable sits anywhere inside a walked term."""
    if is_var(term):
        return True
    if isinstance(term, (tuple, list)):
        return any(_holds_var(e) for e in term)
    if isinstance(term, dict):
        return any(_holds_var(k) or _holds_var(v) for k, v in term.items())
    return False
```

(If `_Var` ends up unused, drop that import line; `is_var` is what the walk uses.)

And directly after `make_quantity._register(3, _simple_to_trampoline(_make_dimensioned_impl))`:

```python
quantity_number = _UnitsPredicate("quantity_number")
quantity_number._register(2, _simple_to_trampoline(_quantity_number_impl))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/test_quantity_number.py tests/test_units.py tests/value_terms/ -q 2>&1 | tail -3
```

Expected: `tests/test_quantity_number.py` all pass; `tests/test_units.py` unchanged against Task 0's red list.

MEASURED already (see the PRELUDE note): the term arrives as the tuple. If it nevertheless does not arrive at the predicate as the tuple `('quantity', 5, ('unit', 1000, ('dimensions', ('metre', 1))))` — check by printing `repr(t)` inside the impl once — then the reader's shape for a compound differs from the wire form and this task must STOP and report: it is the spec's assumption ("post-FLIP every compound is a cell") and the fix is not in this plan.

- [ ] **Step 5: Commit**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
git branch --show-current
git add clausal/modules/units.py tests/test_quantity_number.py
git commit -m "units: quantity_number/2, the explicit transfer-term <-> object relation

Seven modes per the spec: emit with ratio 1, read with the ratio multiplied
through, compare by value when both are bound, instantiation_error for
(-,-) or an unbound slot, type_error(quantity, T) for a malformed term --
raised, never a quiet failure. The Prolog-side half (magnitude scaled to
the standard unit) belongs to the exporter's prelude.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01G3Bi6ruQWgu7WHKrYWPTT9"
```

---

### Task 5: Docstring, gate, review, handoff

**Files:**
- Modify: `clausal/logic/python_terms.py` — module docstring, add a TRANSFER section.
- Modify: `implementation_plans/SESSION-HANDOFF-2026-09-16-engine-lane-END.md` — mark NEXT item 2 done.
- Memory: `/home/node/.claude/projects/-workspace-clausal-bug-fix/memory/predicatemeta-retirement-design.md` + `MEMORY.md` index line.

**Interfaces:**
- Consumes: `qt-baseline.raw`, `qt-red-in-touched.txt` (Task 0); `gate_iso_l3.sh`, `failure_diff.py`.
- Produces: the gate verdict (NEW must be 0), a roborev review, the updated handoff.

- [ ] **Step 1: Add the docstring section** — in the module docstring of `python_terms.py`, after the "TWO MODES" section and before "THE DOCUMENTED HAZARD":

```
THE TRANSFER LAYER
==================
``TO_TRANSFER`` / ``FROM_TRANSFER`` and ``to_transfer`` / ``from_transfer``
sit BESIDE the seam registry. A same-interpreter seam PASSES THE OBJECT
(ruled 2026-09-15) -- a quantity stands in for a number and must reach
``#=/2`` as itself -- so the entries a subinterpreter, a process boundary or
a bytecode cache need (``Quantity`` as ``quantity/2``, ``Fraction`` as
``rdiv/2``) live in their own tables where no seam consumer can reach them.
The transfer functions consult their tables first and fall through to the
seam converters, so a Decimal or a date inside a quantity needs no second
entry. Spec: docs/superpowers/specs/2026-09-16-quantity-transfer-form-design.md
```

- [ ] **Step 2: Run the fast checks**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/value_terms/ tests/test_quantity_number.py tests/test_funnel_lint.py tests/test_units.py tests/test_units_clp.py tests/test_currency.py tests/test_currency_money.py tests/test_dims_keyed_by_atoms.py -q -p no:randomly 2>&1 | tail -3
```

Expected: only failures that appear in `qt-red-in-touched.txt`, with the same reasons. `test_funnel_lint` passes (nothing was inserted in `terms.py`).

- [ ] **Step 3: Commit the docstring**

```bash
git branch --show-current
git add clausal/logic/python_terms.py
git commit -m "python_terms: document the transfer layer in the module docstring

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01G3Bi6ruQWgu7WHKrYWPTT9"
```

- [ ] **Step 4: Run the full gate and diff the failure SETS**

```bash
rm -f /home/node/.claude/jobs/af5b4bbe/tmp/qt-candidate.raw
nohup /home/node/.claude/jobs/af5b4bbe/tmp/gate_iso_l3.sh /home/node/.claude/jobs/af5b4bbe/tmp/qt-candidate.raw >/dev/null 2>&1 &
```

Wait for `EXIT=` in the file, then:

```bash
grep -e '^TREE-SHA' -e '^IMPORTED' -e '^PLUGIN-OK' -e '^RUN-EXIT' /home/node/.claude/jobs/af5b4bbe/tmp/qt-candidate.raw
/workspace/clausal/venv/bin/python /home/node/.claude/jobs/af5b4bbe/tmp/failure_diff.py \
    /home/node/.claude/jobs/af5b4bbe/tmp/qt-baseline.raw /home/node/.claude/jobs/af5b4bbe/tmp/qt-candidate.raw
```

Expected: `TREE-SHA` is the Task 5 Step 3 commit; both runs FINISHED; baseline and candidate failure-set sizes printed and both non-zero; **NEW = 0**; the passed count rose by exactly the number of tests this plan added (count them: `grep -c '^def test_' tests/value_terms/test_quantity_transfer.py tests/test_quantity_number.py`). If NEW is not 0, every NEW name is a regression of this plan — fix it in the task that owns the file, re-run, and do not proceed.

Then the blind-spot check: for every test in `qt-red-in-touched.txt`, run it alone again and confirm its failure reason is the SAME as recorded in Task 0. A red test whose reason changed is a regression the set-diff cannot see.

- [ ] **Step 5: Review**

Run the roborev branch review (`/roborev-review-branch` skill) on the range `98fc4b92..HEAD`. Verify each finding against the tree before acting (one grep or one mutation settles it); fix real ones in the owning task's files and commit; record wrong ones in the handoff with the reason.

- [ ] **Step 6: Handoff and memory**

Append to `implementation_plans/SESSION-HANDOFF-2026-09-16-engine-lane-END.md`, under the "LANDED" note at the top:

```
NEXT item 2 (the transfer form + quantity_number/2) is BUILT on this branch:
<first sha>..<last sha>, gated NEW 0 against qt-baseline (<baseline sha>),
<N> tests added. Spec docs/superpowers/specs/2026-09-16-quantity-transfer-form-design.md,
plan docs/superpowers/plans/2026-09-16-quantity-transfer-form.md. Not promoted:
it lands with the dates-are-terms work, behind the harness lane's date
migration. The exporter's Prolog-side quantity_number/2 is still theirs.
```

Update the memory file's "**PROMOTED 2026-09-16**" paragraph: replace "Item 2 of the handoff (transfer form, `quantity_number/2`) is the next unbuilt piece." with "The transfer form + `quantity_number/2` were BUILT <date> on the feature branch (<range>), gated NEW 0; they land with the dates work." Update the `MEMORY.md` index line's tail the same way.

```bash
git branch --show-current
git add implementation_plans/SESSION-HANDOFF-2026-09-16-engine-lane-END.md
git commit -m "handoff: the transfer form and quantity_number/2 are built and gated

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01G3Bi6ruQWgu7WHKrYWPTT9"
```

- [ ] **Step 7: Tell harness-date-migration** (SendMessage to `harness-date-migration`): the range landed on the branch, `python_terms.py` edits are additive and `to_term`/`from_term`/`py/datetime.py` are untouched, and nothing changed for their harness. One message, first line self-contained.

---

## Self-review against the spec

| spec section | task |
|---|---|
| §2.2 tables, entry points, fall-through, `register_transfer` no-override, Var refused | Task 1 |
| §2.2 "seam functions not edited", two pins | Task 2 (`to_term(q) is q`), Task 3 (`from_term(quantity term) is t`), Task 1 (Fraction pins) |
| §3 encoding table incl. sorted dims, `dimensionless`, `unit/2`, `quantity/2`, `rdiv` sign | Tasks 1–3 |
| §3 emit ratio always 1 | Task 2 |
| §3 read: ratio through `_num_pair`, order-insensitive dims, atom-keyed dict | Task 3 |
| §3 one helper owns the two-functor dims slot | Task 2 |
| §3 marshal-clean with positive control, the three examples + rdiv + two-dim | Task 2 |
| §4 seven modes, errors raised not quiet | Task 4 |
| §5 file placement | file map |
| §6 gate: baseline, red-in-touched list, NEW 0, funnel lint, no domain axis, roborev | Task 0, Task 5 |
| §7 not built | nothing here wires a consumer, touches the compiler, the exporter, or `terms.py` |
| §8 date-migration interaction | Global constraints (no seam edits) + Task 5 Step 7 |

Type consistency: `to_transfer(value)` / `from_transfer(value)` / `register_transfer(cls, functor, to_fn, from_fn)` / `_dims_to_term(dims)` / `_dims_from_term(t)` / `_quantity_to_term(q)` / `_quantity_from_term(t)` / `_transfer_number(x)` / `_quantity_number_impl(term, number, trail)` / `_holds_var(term)` are spelled identically in every task.
