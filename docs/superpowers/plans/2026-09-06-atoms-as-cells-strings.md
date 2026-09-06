# Atoms as arity-0 cells; plain `str` is a string — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an atom the 1-tuple cell `("bar",)` and a plain Python `str` a string with Scryer char-list semantics, landing green at every commit (spec §10: Plan 0 + Plan 1 = Stage A widen → Stage B flip → Stage C cleanup).

**Architecture:** Stage A writes every atom-touching site in terms of five helpers in `clausal/logic/atoms.py` — `mint`, `is_atom`, `spelling`, `char_atom`, `is_char_atom` — whose Plan 0 bodies describe *today's* representation (str), so each Stage A task is additive and green. Stage B is one task that rewrites those five bodies plus the compiler's atom emission, the literal rule, the `str`-demotion and the C twins, then migrates the suite's own assertions. Stage C deletes the dual-acceptance code and rewrites the docs.

**Tech Stack:** Python 3.13, CPython C extensions (`_variables.c`, `_list_unify.c`, `_lists_core.c`, `_chars_core.c`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-06-atoms-as-cells-strings-design.md` (rulings R-S1/R-S2/R-S3′/R-S4; §5 term model; §6 semantics; §7 literals; §9 boundaries; §10 sequencing; §13 acceptance rows). Census evidence: `implementation_plans/strings-representation-options-2026-09-06.md` §7 and the three census reports the controller holds (file:line cited inline below).

## Global Constraints

- Work ONLY in `/workspace/clausal-bug-fix/.claude/worktrees/p33-state-reloc` (branch `feat/double-quotes-ratchet`); every command from there with `/workspace/clausal/venv/bin/python`. Verify once per task: `/workspace/clausal/venv/bin/python -c "import clausal; print(clausal.__file__)"` prints a path under the worktree.
- NEVER `git add -A`; NEVER `git stash`; never stage `todo/`. Explicit paths. Commit trailer (two lines): `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_01G7xiWqatWtL6zNQDc7nspk`.
- The worktree-isolation hook refuses compound shell commands, `cd … &&`, heredocs and `git -C`. One plain command per Bash call; use the Edit/Write tools for multi-line edits.
- After ANY `.c` change: `/workspace/clausal/venv/bin/python setup.py build_ext --inplace` (rc 0) before testing.
- **Suite gate (every task):** `/workspace/clausal/venv/bin/python -m pytest tests/ -q --tb=no --continue-on-collection-errors -p no:cacheprovider` → failing-name set byte-identical to `.superpowers/sdd/p33-state-relocation/task-3-base-failed-names.txt` (145 names; two known load-flakes `test_F026_multi_star_splits_bounded_for_moderate_input` and `test_06_clpfd.py::TestOracles::test_queens8_count` re-run alone before being read as regressions). Extract names with `-rf` output filtered to lines starting `FAILED`, strip everything from ` - ` on, sort. Assert the run actually executed (count of collected tests > 5000) before trusting a diff.
- **Equality, never identity** for atoms and functors (spec §2 bridge-entry ruling, §5.2). No new `is` comparison of an atom anywhere; every existing one is removed in Task 9.
- **Slot 0 of a cell stays a plain `str`** (the spelling). Atoms are `("bar",)`; never nest an atom in slot 0.
- **THE DISCIPLINE** (`clausal/logic/cells.py:53–64`, pinned by `tests/test_funnel_accessors.py::TestCellFunnelAwareness`) is unchanged: a non-empty tuple whose slot 0 is a `str` is a cell by shape.
- Stage A tasks are ADDITIVE: a `str` atom keeps working everywhere; a `("foo",)` atom starts working. No Stage A task may make a `str` stop being an atom — that is Stage B's single move.
- Python/C twins change together, in the same task, with the twin-parity tests run (`tests/test_python_fallbacks.py`, `tests/test_list_unify*.py`).
- Information barrier: no downstream project names, corpus domain names or battery sizes in any commit, test, docstring or comment.
- Perf gate (Task 14): interleaved A/B, 5 rounds each, fresh subprocesses, against the pre-plan tree `a8a2d2f7`; under the 3% bar on `bench_struct_tabling`, `bench_fib`, and the list/string and `++` benches named there.

---

### Task 0: baseline, workspace, build

**Files:** none in the tree (workspace only).

- [ ] **Step 1:** `/workspace/clausal/venv/bin/python setup.py build_ext --inplace` — rc 0.
- [ ] **Step 2:** Run the suite gate command; write the sorted failing names to `.superpowers/sdd/2026-09-06-atoms-as-cells-strings/baseline_failures.txt` (create the directory with the SDD workspace script or `mkdir -p`).
- [ ] **Step 3:** `diff` it against `.superpowers/sdd/p33-state-relocation/task-3-base-failed-names.txt` — must be empty. If not, STOP and report (the ratchet branch is expected to add zero failures).
- [ ] **Step 4:** Record BASE `git rev-parse HEAD` in the ledger. No commit.

---

## Plan 0 — the API

### Task 1: `clausal/logic/atoms.py` public atom API (today's representation)

**Files:**
- Modify: `clausal/logic/atoms.py` (append after `demangle_for_display`, extend `__all__`)
- Modify: `clausal/logic/predicate.py:1700–1718` (`make_atom`), `:1584–1602` (`is_atom_value`)
- Test: `tests/test_atoms_api.py` (new)

**Interfaces (Produces — every later task consumes these exact names):**
```python
from clausal.logic.atoms import mint, is_atom, spelling, char_atom, is_char_atom
mint(spelling: str) -> atom          # canonical atom for a spelling; TypeError if not str
is_atom(term) -> bool                # the TERM test (not the zero-field-class test)
spelling(atom) -> str                # TypeError("not an atom: …") if not is_atom
char_atom(ch: str) -> atom           # mint for a 1-char spelling; ValueError if len != 1
is_char_atom(term) -> bool           # is_atom(term) and len(spelling) == 1
```
Plan 0 bodies (today's representation; Stage B rewrites exactly these five bodies and nothing else in this block):

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_atoms_api.py
"""Public atom API (spec §6.1). Representation-agnostic: these tests hold
before and after the Stage B flip; only the ``_repr_probe`` tests pin the
current representation and are rewritten by Stage B."""
import pytest
from clausal.logic.atoms import mint, is_atom, spelling, char_atom, is_char_atom
from clausal.logic.predicate import make_atom, is_atom_value


def test_mint_roundtrips_spelling():
    a = mint("foo")
    assert is_atom(a)
    assert spelling(a) == "foo"


def test_mint_is_equal_for_equal_spellings():
    assert mint("foo") == mint("foo")
    assert mint("foo") != mint("bar")


def test_mint_rejects_non_str():
    with pytest.raises(TypeError):
        mint(3)


def test_spelling_rejects_non_atom():
    with pytest.raises(TypeError):
        spelling(3)


def test_char_atom_is_a_one_char_atom():
    c = char_atom("x")
    assert is_atom(c) and is_char_atom(c) and spelling(c) == "x"
    assert not is_char_atom(mint("xy"))
    with pytest.raises(ValueError):
        char_atom("xy")


def test_make_atom_delegates_to_mint():
    assert make_atom("foo") == mint("foo")


def test_is_atom_value_accepts_minted_atom():
    assert is_atom_value(mint("foo"))


def test_repr_probe_plan0_str():
    # Plan 0: today's representation. Stage B replaces this test with the
    # cell probe (see Task 12).
    assert mint("foo") == "foo"
```

- [ ] **Step 2:** Run `pytest tests/test_atoms_api.py -q` → FAIL (ImportError on `mint`).
- [ ] **Step 3: Implement** — append to `clausal/logic/atoms.py`:

```python
# ── Public atom API (spec 2026-09-06-atoms-as-cells-strings-design §6.1) ──
#
# Plan 0 bodies: an atom IS its spelling (a plain str) on this tree.  Stage B
# of the same plan rewrites the five bodies below to the arity-0 cell
# ``(spelling,)`` — callers written against these names survive that flip
# unchanged.  Equality is the semantics; ``mint`` returns a canonical object
# as an optimisation only (never rely on ``is``).

def mint(spelling: str):
    """Return the canonical atom for *spelling*."""
    if type(spelling) is not str:
        raise TypeError(f"mint: spelling must be a str, got {type(spelling).__name__}")
    return sys.intern(spelling)


def is_atom(term) -> bool:
    """True iff *term* is an atom (the TERM test; a zero-field predicate class
    is not an atom — see ``predicate.is_atom_value`` for the value-level
    widening that still admits one)."""
    return type(term) is str


def spelling(atom) -> str:
    """The spelling of *atom*; ``TypeError`` for a non-atom."""
    if not is_atom(atom):
        raise TypeError(f"not an atom: {atom!r}")
    return atom


def char_atom(ch: str):
    """The atom whose spelling is the single character *ch*."""
    if type(ch) is not str or len(ch) != 1:
        raise ValueError(f"char_atom: expected a 1-char str, got {ch!r}")
    return mint(ch)


def is_char_atom(term) -> bool:
    """True iff *term* is an atom whose spelling is one character."""
    return is_atom(term) and len(spelling(term)) == 1
```
Extend `__all__` with the five names. In `predicate.py`, `make_atom` body → `from clausal.logic.atoms import mint; return mint(name)` (keep the docstring, add one line saying it delegates). `is_atom_value` body → `from clausal.logic.atoms import is_atom as _term_is_atom; return _term_is_atom(obj) or is_atom(obj)` (the second `is_atom` is the existing zero-field-class test in that module).

- [ ] **Step 4:** `pytest tests/test_atoms_api.py -q` → PASS. Suite gate → empty diff.
- [ ] **Step 5:** Commit: `git add clausal/logic/atoms.py clausal/logic/predicate.py tests/test_atoms_api.py` / `git commit -m "atoms: public mint/is_atom/spelling/char_atom/is_char_atom API (Plan 0, today's representation)"`.

---

## Stage A — widen (every task green; a `("foo",)` atom starts working beside the `str` atom)

Stage A convention: wherever a site today tests `isinstance(x, str)` meaning "is an atom", it becomes `is_atom_value(x)` (or `atoms.is_atom(x)` where classes are impossible); wherever it produces an atom from text it calls `mint(text)`; wherever it produces a char it calls `char_atom(c)`; wherever it tests "is a 1-char str" meaning "is a char" it calls `is_char_atom(e)`. Under Plan 0 bodies every one of these is behaviour-preserving, which is what keeps Stage A green.

### Task 2: type checks and the funnel accept the cell atom

**Files:**
- Modify: `clausal/logic/builtins/type_checks.py` (`atom/1` :68–79, `atomic/1` :139–167, `_check_type` :340–381, `must_be/2` :384–413, `can_be/2` :415–440)
- Modify: `clausal/logic/builtins/_helpers.py` (`_standard_order_key` :559–624 — see Task 3; here only `_functor_name` wrappers :360–394 are unchanged)
- Test: `tests/test_atoms_as_cells.py` (new; grows through Stage A)

**Interfaces:** Consumes `is_atom`, `spelling`, `mint` (Task 1).

- [ ] **Step 1: Failing tests**

```python
# tests/test_atoms_as_cells.py
"""Stage A probes: a 1-tuple ("foo",) is accepted as an atom beside today's
str atom (spec §6.3, §6.4).  Each test names the spec row it pins."""
import pytest
from clausal.logic.solve import solve
from clausal.logic.exceptions import LogicException

CELL = ("foo",)


def _true(goal):
    return len(list(solve(goal))) == 1


def test_atom_1_accepts_cell_atom():           # §6.3 row atom/1
    assert _true(("atom", CELL))


def test_atomic_1_accepts_cell_atom():         # §6.3 row atomic/1
    assert _true(("atomic", CELL))


def test_compound_1_rejects_cell_atom():       # §6.3 arity-0 is not compound
    assert not _true(("compound", CELL))


def test_callable_1_accepts_cell_atom():       # §6.3 row callable/1
    assert _true(("callable_", CELL))


def test_must_be_atom_accepts_cell_atom_and_cell_type_name():
    assert _true(("must_be", ("atom",), CELL))
    assert _true(("must_be", "atom", CELL))


def test_must_be_compound_accepts_cell():
    assert _true(("must_be", ("compound",), ("f", 1)))
    with pytest.raises(LogicException):
        list(solve(("must_be", ("compound",), CELL)))
```

- [ ] **Step 2:** run → FAIL (`atomic`, `must_be` with a tuple Type).
- [ ] **Step 3: Implement.** In `type_checks.py`:
  - `_atomic__1`: after the `is_term_instance` rejection add `if _term_is_atom(x_val): yield None; return` (import `from clausal.logic.atoms import is_atom as _term_is_atom, spelling as _spelling`) — before the primitives line, so a tuple atom is accepted while a plain tuple `(1, 2)` still falls off the end.
  - `_check_type`: the `("atom", "string", "str")` entry splits into `"atom"` → `is_atom_value(term)` and `("string", "str")` → `isinstance(term, str) or (isinstance(term, SegString) and _is_ground(term))`. (Under Plan 0 both answers are unchanged for a `str`.) The `"compound"` branch gains `if _is_compound(term) and (_arity(term) or 0) > 0: return True`. The `"callable"` branch gains `or _is_compound(term)`.
  - `must_be/2` and `can_be/2`: replace `if not isinstance(type_val, str): raise …` with
    ```python
    if _term_is_atom(type_val):
        type_val = _spelling(type_val)
    elif not isinstance(type_val, str):
        raise LogicException(type_error("atom", type_val, "must_be/2"))
    ```
    (the `isinstance(type_val, str)` arm is the Plan 0 str atom; Stage B deletes it).
- [ ] **Step 4:** focused tests PASS; suite gate empty.
- [ ] **Step 5:** Commit `type_checks.py`, `tests/test_atoms_as_cells.py`: `"type checks: accept the arity-0 cell as an atom (Stage A)"`.

### Task 3: standard order — atoms in the atom band, cells in the compound band

**Files:**
- Modify: `clausal/logic/builtins/_helpers.py:559–624` (`_standard_order_key`)
- Test: `tests/test_atoms_as_cells.py` (append) and `tests/test_standard_order.py` if it exists (grep `_standard_order_key` under tests/ first; add there if so).

**Interfaces:** Produces the key shape of spec §6.5, consumed by `sort/2`, `msort/2`, `sort_by/max_by/min_by`, `setof` unchanged.

- [ ] **Step 1: Failing tests** (append):

```python
from clausal.logic.builtins._helpers import _standard_order_key as K, _ORD_ATOM, _ORD_COMPOUND, _ORD_SEQ


def test_cell_atom_keys_in_atom_band():        # §6.5
    assert K(("bar",)) == (_ORD_ATOM, "bar")
    assert K(("bar",)) == K("bar")


def test_cell_keys_in_compound_band_arity_first():
    k = K(("f", 1, 2))
    assert k[0] == _ORD_COMPOUND and k[1] == 2 and k[2] == (0, "f")
    assert K(("f", 1, 2)) < K(("a", 1, 2, 3))          # arity before name
    assert K(("f", 1, 2)) > K([1, 2, 3])                # sequences before compounds
    assert K(("f", 1)) != K(["f", 1])


def test_msort_orders_number_atom_list_cell():   # §13 row 16 (Stage A form)
    from clausal.logic.variables import Var, deref
    out = Var()
    answers = list(solve(("msort", [("f", "x"), [1], ("b",), 1], out)))
    assert len(answers) == 1
    assert deref(out) == [1, ("b",), [1], ("f", "x")]
```

- [ ] **Step 2:** run → FAIL (cell keys in `_ORD_SEQ`).
- [ ] **Step 3: Implement.** In `_standard_order_key`, BEFORE the `isinstance(term, (list, tuple))` line insert:

```python
    if type(term) is tuple and term and type(term[0]) is str:
        # A cell (spec §5.1).  Arity 0 is an atom (spec §6.5): same key as
        # the str spelling so a str atom and a cell atom are one atom in the
        # order.  Arity > 0 keys like ``Compound`` — arity first, then name
        # (ISO 7.2.1), positional flavour — never as a sequence.
        if len(term) == 1:
            return (_ORD_ATOM, term[0])
        return (_ORD_COMPOUND, len(term) - 1, (0, term[0]), _CF_POSITIONAL,
                tuple(_standard_order_key(a) for a in term[1:]))
    if type(term) is tuple and term and term[0] is TUPLE_TAG:
        return (_ORD_COMPOUND, len(term) - 1, (1, ""), _CF_POSITIONAL,
                tuple(_standard_order_key(a) for a in term[1:]))
```
Import `TUPLE_TAG` from `clausal.logic.cells` (check for an import cycle: `_helpers.py` already imports from `clausal.terms`; `cells.py` imports nothing from builtins — safe). Update the docstring's band description.

- [ ] **Step 4:** focused PASS; suite gate empty (watch `tests/test_dict_set_builtins.py`, `test_lists*.py`, `setof` tests — any failure there is a real pre-existing consumer of the sequence-band order; report it, do not paper over it).
- [ ] **Step 5:** Commit `_helpers.py`, tests: `"standard order: cells key arity-first in the compound band; arity-0 keys as the atom"`.

### Task 4: writers — arity-0 cells print bare; `writeq/1`, `write_canonical/1`; ISO atom quoting

**Files:**
- Modify: `clausal/terms.py` (`term_str` :2364–2450 cell branch; `term_pformat` :2571–2584; `term_html` :2721–2730) — add module-level helpers `atom_needs_quotes`, `quote_atom`, `quote_string`
- Modify: `clausal/logic/builtins/io.py` (`_format_term_for_io` :20–47; `_format_clause_term` :135–160; add `writeq/1`, `write_canonical/1`)
- Modify: `clausal/reflection.py:595–613` (cell branch arity-0 case)
- Test: `tests/test_writers_atoms_strings.py` (new)

**Interfaces (Produces):**
```python
# clausal/terms.py
def atom_needs_quotes(s: str) -> bool     # ISO 6.4.2: bare iff [a-z][A-Za-z0-9_]*, or all graphic chars, or a solo ("[]", "{}", "!", ";"); "" and "," need quotes
def quote_atom(s: str) -> str             # "'" + s with \\ and \' and control chars escaped + "'"
def quote_string(s: str) -> str           # '"' + s with \\ and \" and control chars escaped + '"'
def term_str(t, style=None, _bd=0, *, quoted=True) -> str   # NEW keyword; quoted=False is the write/1 family
def term_canonical(t) -> str             # write_canonical/1 renderer (spec §6.7): quoted atoms, NO space after commas, no operators,
                                         # every list as the '.'/2 cons structure ending in [] ('.'(1,'.'(2,[]))); Var as term_str prints it;
                                         # Stage A: a str is an atom → quoted spelling; Task 11 turns the str branch into the cons form.
```
`_format_term_for_io(val)` = `term_str(val, quoted=False)` for cells and lists; `str` is text; everything else `str(val)` as today.

- [ ] **Step 1: Failing tests**

```python
# tests/test_writers_atoms_strings.py
"""Spec §6.7: display of atoms (arity-0 cells), strings and chars."""
import io, contextlib
import pytest
from clausal.terms import term_str, term_pformat, term_html, atom_needs_quotes, quote_atom
from clausal.logic.solve import solve


@pytest.mark.parametrize("s,bare", [
    ("foo", True), ("fooBar_1", True), ("Foo", False), ("foo bar", False),
    ("", False), ("[]", True), ("{}", True), ("!", True), (";", True), (",", False),
    ("+", True), ("=..", True), ("hello-world", False), ("_x", False), ("1a", False),
])
def test_atom_needs_quotes(s, bare):
    assert atom_needs_quotes(s) is (not bare)


def test_quote_atom_escapes():
    assert quote_atom("it's") == r"'it\'s'"
    assert quote_atom("a\\b") == r"'a\\b'"
    assert quote_atom("a\nb") == r"'a\nb'"


def test_term_str_arity0_cell_is_bare_spelling():
    assert term_str(("flag",)) == "flag"
    assert term_str(("foo bar",)) == "'foo bar'"
    assert term_str(("foo", ("bar",), 1)) == "foo(bar, 1)"


def test_term_pformat_and_html_arity0():
    assert term_pformat(("flag",)) == "flag"
    assert "flag" in term_html(("flag",)) and "flag()" not in term_html(("flag",))


def test_write_family_prints_cell_atom_bare():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        list(solve(("write", ("flag",))))
        list(solve(("write", ("foo", ("foo bar",)))))
    assert buf.getvalue() == "flagfoo(foo bar)"


def test_writeq_quotes_and_write_canonical_is_cons_form():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        list(solve(("writeq", ("foo bar",))))
        list(solve(("write_canonical", ("foo", ("foo bar",), 1))))
        list(solve(("write_canonical", [1, 2])))
        list(solve(("write_canonical", [])))
    assert buf.getvalue() == "'foo bar'foo('foo bar',1)'.'(1,'.'(2,[]))[]"


def test_term_canonical_partial_list_and_nesting():
    from clausal.terms import term_canonical
    from clausal.logic.variables import Var
    assert term_canonical(("f", [("a",), ("b c",)])) == "f('.'(a,'.'('b c',[])))"
    t = term_canonical([1, Var()])
    assert t.startswith("'.'(1,_") and t.endswith(")")


def test_term_str_hidden_atom_display_unchanged():
    assert term_str(("m\x1fbar",)) == "m.bar"
```

- [ ] **Step 2:** run → FAIL (`flag()`; no `atom_needs_quotes`; no `writeq`).
- [ ] **Step 3: Implement.**
  - `terms.py`: add
    ```python
    _GRAPHIC_CHARS = frozenset("#$&*+-./:<=>?@^~\\")
    _SOLO_ATOMS = frozenset({"[]", "{}", "!", ";"})

    def atom_needs_quotes(s: str) -> bool:
        if s in _SOLO_ATOMS:
            return False
        if not s:
            return True
        if s[0].islower() and all(c.isalnum() or c == "_" for c in s):
            return False
        if all(c in _GRAPHIC_CHARS for c in s):
            return False
        return True

    def _escape_quoted(s: str, quote: str) -> str:
        out = []
        for c in s:
            if c == "\\": out.append("\\\\")
            elif c == quote: out.append("\\" + quote)
            elif c == "\n": out.append("\\n")
            elif c == "\t": out.append("\\t")
            elif ord(c) < 0x20 or c == "\x7f": out.append(f"\\x{ord(c):02x}\\")
            else: out.append(c)
        return "".join(out)

    def quote_atom(s: str) -> str: return "'" + _escape_quoted(s, "'") + "'"
    def quote_string(s: str) -> str: return '"' + _escape_quoted(s, '"') + '"'
    ```
  - `term_str`: add `quoted: bool = True` keyword; thread it through every recursive call (`term_str(a, style, _bd + 1, quoted=quoted)`). In the cell branch, before building `functor_s`:
    ```python
        if len(t) == 1:
            display = demangle_for_display(functor) if is_mangled(functor) else functor
            if quoted and not is_mangled(functor) and atom_needs_quotes(display):
                display = quote_atom(display)
            return _c(display, 'atom', style)
    ```
    (The `str` branch is untouched in Stage A — a `str` is still an atom and keeps its `repr` rendering; Stage B replaces it with `quote_string`/text.)
  - `term_pformat`: the cell branch's `if not args: return flat` already delegates to `term_str`; nothing else. `term_html`: add `if len(t) == 1: return _html_c(esc(term_str(t)), 'atom')` at the top of the cell branch.
  - `io.py`: `_format_term_for_io` cell branch → `return _term_str(val, quoted=False)`; `_format_clause_term` cell branch likewise stays `_term_str(val)` (listing is the quoted family). Add:
    ```python
    @_builtin("writeq", 1)
    def _writeq__1(term, trail, k):
        """writeq(Term) — write Term quoted so the reader reads it back (ISO 8.14.2)."""
        from clausal.logic.solve import _deref_walk
        _sys.stdout.write(_term_str(_deref_walk(term), quoted=True))
        _sys.stdout.flush()
        yield None

    @_builtin("write_canonical", 1)
    def _write_canonical__1(term, trail, k):
        """write_canonical(Term) — ISO 8.14.2 canonical form: quoted atoms, no operators,
        no spaces, every list as its '.'/2 structure (Scryer: write_canonical("hello")
        prints '.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))."""
        from clausal.logic.solve import _deref_walk
        _sys.stdout.write(_term_canonical(_deref_walk(term)))
        _sys.stdout.flush()
        yield None
    ```
  - `terms.py`: add `term_canonical(t)` next to `term_str`:
    ```python
    def term_canonical(t: Any) -> str:
        """write_canonical/1 rendering (spec §6.7): quoted, operator-free, no spaces,
        lists as '.'/2 cons cells.  Same dispatch order as term_str."""
        t = deref(t) if not isinstance(t, (str, bytes, int, float)) else t
        if t is None or t is ... or isinstance(t, (bool, Decimal, int, float, complex)):
            return term_str(t)
        if isinstance(t, str):
            # Stage A: a str is an atom.  Task 11 replaces this branch with the
            # cons form of the string's char list.
            display = demangle_for_display(t) if is_mangled(t) else t
            return quote_atom(display) if (not is_mangled(t) and atom_needs_quotes(display)) else display
        if isinstance(t, bytes):
            return repr(t)
        if isinstance(t, list):
            out = "[]"
            for e in reversed(t):
                out = "'.'(" + term_canonical(e) + "," + out + ")"
            return out
        if isinstance(t, (SegList, SegString)):
            return term_canonical(t.__walk__())
        if isinstance(t, Var):
            return term_str(t)
        if type(t) is tuple and t and type(t[0]) is str:
            functor = t[0]
            display = demangle_for_display(functor) if is_mangled(functor) else functor
            head = quote_atom(display) if (not is_mangled(functor) and atom_needs_quotes(display)) else display
            if len(t) == 1:
                return head
            return head + "(" + ",".join(term_canonical(a) for a in t[1:]) + ")"
        if type(t) is tuple and t and t[0] is TUPLE_TAG:
            return "(" + ",".join(term_canonical(e) for e in t[1:]) + ")"
        if isinstance(t, Compound):
            f = deref(t.functor)
            head = term_canonical(f) if not isinstance(f, str) else (quote_atom(f) if atom_needs_quotes(f) else f)
            return head + "(" + ",".join(term_canonical(a) for a in t.args) + ")"
        return term_str(t)
    ```
    (A `SegList`/`SegString` that walks to itself — non-ground — prints its elements with holes as `Var`s: walk, then if still a Seg*, render each concrete segment's elements and each `VarSeg` as `term_str` of the hole; keep it simple and note it in the report.)
  - `reflection.py` cell branch: `if len(value) == 1: return self._name_ast(demangle_for_display(value[0]))` before the `ast.Call` construction (an arity-0 cell renders as the bare name, exactly as the `Atom` case).
- [ ] **Step 4:** focused PASS; suite gate empty. (`tests/test_listing.py`, `tests/test_io.py`, `tests/test_reflection_render.py` are the consumers to watch.)
- [ ] **Step 5:** Commit: `"writers: arity-0 cell prints as the atom; writeq/1 and write_canonical/1; ISO atom quoting helpers"`.

### Task 5: the name position — `functor/3`, `=..`, `listing/1`, `resolve_module`, `global_atom/2`, `gensym/2`, exception terms speak atoms

**Files:**
- Modify: `clausal/logic/builtins/inspection.py` (`_construct_named` :244–271, `functor/3` :273–318, `unpack/2` :362–406, `global_atom/2` :496–575, `gensym/2` :476–491)
- Modify: `clausal/logic/builtins/io.py:344–410` (`listing/1`)
- Modify: `clausal/logic/solve.py:587–648` (`resolve_module`)
- Modify: `clausal/logic/exceptions.py:194–236` (the seven constructors)
- Modify: `clausal/logic/builtins/database_ops.py:534` (`abolish_table/2` name arg)
- Test: `tests/test_atoms_as_cells.py` (append)

**Interfaces:** Consumes `mint`, `is_atom`, `spelling` (Task 1). Produces: `functor/3` and `=..` CONSTRUCT CELLS (never `Compound`) — `functor(T, N, 2)` binds `T = (spelling, V1, V2)`; `T =.. [N, 1]` binds `T = (spelling, 1)`; both hand back `mint(slot0)` as the name.

- [ ] **Step 1: Failing tests** (append to `tests/test_atoms_as_cells.py`):

```python
from clausal.logic.variables import Var, deref
from clausal.logic.atoms import mint


def _one(goal):
    answers = list(solve(goal)); assert len(answers) == 1; return answers[0]


def test_functor_3_constructs_a_cell_and_names_an_atom():      # §6.4, §13 rows 7–8
    T = Var(); _one(("functor", T, mint("foo"), 2))
    t = deref(T); assert type(t) is tuple and t[0] == "foo" and len(t) == 3
    N, A = Var(), Var(); _one(("functor", ("foo", 1), N, A))
    assert deref(N) == mint("foo") and deref(A) == 1
    T0 = Var(); _one(("functor", T0, mint("foo"), 0)); assert deref(T0) == mint("foo")


def test_univ_constructs_a_cell_and_round_trips():             # §13 rows 10–11
    T = Var(); _one(("unpack", T, [mint("foo"), 1]))
    assert deref(T) == ("foo", 1)
    L = Var(); _one(("unpack", ("foo", 1, ("bar",)), L))
    assert deref(L) == [mint("foo"), 1, ("bar",)]
    T2 = Var(); _one(("unpack", T2, deref(L))); assert deref(T2) == ("foo", 1, ("bar",))


def test_functor_3_rejects_number_name_with_arity():
    with pytest.raises(LogicException):
        list(solve(("functor", Var(), 3, 2)))


def test_gensym_and_global_atom_mint_atoms():
    A = Var(); _one(("gensym", mint("g"), A)); assert is_atom_value(deref(A))
    G = Var(); _one(("global_atom", mint("zzq_probe"), G)); assert deref(G) == mint("zzq_probe")
    _one(("global_atom", mint("zzq_probe"), mint("zzq_probe")))        # guard mode by equality


def test_type_error_term_carries_atom_args():
    from clausal.logic.exceptions import type_error
    t = type_error("atom", 3, "who")
    assert t.args[0].args[0] == mint("atom")


def test_listing_accepts_cell_atom(capsys):
    list(solve(("listing", ("atom",))))          # the builtin atom/1 exists in every db
```
(For `listing`: use any predicate name that exists in the default module of the test — `atom` is registered as a builtin; if `listing` of a builtin raises `existence_error` on this tree, define a one-clause fixture module with `_load_inline_clausal` from `tests/test_double_quotes_directive.py` and list that predicate instead.)

- [ ] **Step 2:** run → FAIL (Compound constructed; `global_atom` requires `str`).
- [ ] **Step 3: Implement.**
  - `_construct_named(name_val, args, who)`: keep the `PredicateMeta` exact-arity branch; then
    ```python
        if _term_is_atom(name_val):
            return (spelling(name_val), *args)          # a cell, never Compound
        raise LogicException(type_error("atom", name_val, who))
    ```
    (`_term_is_atom` = `atoms.is_atom`; under Plan 0 a `str` passes it, so today's `isinstance(name_val, str)` arm is subsumed.) BEFORE that branch, the `'.'`/2 case (spec §5.4 — never build a `(".", H, T)` cell):
    ```python
        if _term_is_atom(name_val) and spelling(name_val) == "." and len(args) == 2:
            return _cons(args[0], args[1])
    ```
    with a module-level helper in `inspection.py`:
    ```python
    def _cons(head, tail):
        """[Head | Tail] in the engine's list shapes: list, str, or a partial SegList."""
        tail = deref(tail)
        if isinstance(tail, list):
            return [head] + tail
        if isinstance(tail, str):
            h = deref(head)
            if is_char_atom(h):
                return spelling(h) + tail
            return [head] + [char_atom(c) for c in tail]
        if is_var(tail):
            return SegList([ConcreteSeg([head]), VarSeg(tail)])
        if isinstance(tail, (SegList, SegString)):
            return SegList([ConcreteSeg([head]), *_segments_of(tail)])
        raise LogicException(type_error("list", tail, who))
    ```
    Read `clausal/terms.py` for the real `SegList`/`ConcreteSeg`/`VarSeg` constructors and the SegString→segments accessor before writing `_segments_of`; keep the helper to the shapes above. `functor(T, '.', 2)` reaches `_construct_named` with two fresh Vars → the `is_var(tail)` arm. Tests (append):
    ```python
    def test_cons_construction_never_builds_a_dot_cell():          # §5.4, §13 row 18c
        T = Var(); _one(("unpack", T, [mint("."), char_atom("a"), "bc"])); assert deref(T) == "abc"
        T2 = Var(); _one(("unpack", T2, [mint("."), 1, [2]])); assert deref(T2) == [1, 2]
        T3 = Var(); _one(("functor", T3, mint("."), 2))
        from clausal.terms import SegList; assert isinstance(deref(T3), SegList)
        T4 = Var(); _one(("unpack", T4, [mint("."), 1, []])); assert deref(T4) == [1]
    ``` Grep `tests/` for `Compound(` assertions on `functor/3`/`unpack/2` results and update them to the cell shape in this task.
  - `functor/3` construction `arity_val == 0` → `constructed = name_val` stays (atomic names pass through). Add before it: `if not _term_is_atom(name_val) and not isinstance(name_val, (int, float, bool)) and name_val is not None: raise LogicException(type_error("atomic", name_val, "functor/3"))` — a list/string/dict name is `type_error(atomic)` (spec §6.4). Inspection mode: after `f_val = _functor_name(term_val)`, `if type(f_val) is str: f_val = mint(f_val)`.
  - `unpack/2` decomposition: same `mint` wrap of `f_val`. Construction: `len(args_vals) == 0` → `constructed = f_val` only if `_term_is_atom(f_val)` or a number/bool/None, else `type_error("atomic", f_val, "unpack/2")`; with args → `_construct_named`.
  - `global_atom/2`: `name_val` bound → `if _term_is_atom(name_val): key = spelling(name_val) else: return`; guard mode `predicate_builtins.get(key) == atom_val`; mint mode `predicate_builtins.setdefault(key, mint(key))`; reverse mode: `if _term_is_atom(atom_val): cls_name = spelling(atom_val)`; enumerate mode unchanged. All `is` → `==`.
  - `gensym/2`: `prefix_d` must satisfy `_term_is_atom`; `result = mint(f"{spelling(prefix_d)}_{count}")`; counter dict keyed by the spelling.
  - `exceptions.py`: each constructor wraps its atom-typed arguments with `mint(...)`: `type_error` → `(mint(expected_type), culprit)`; `instantiation_error` → `(mint("instantiation_error"), context)`; `existence_error` → `mint(obj_type)`; `permission_error` → `mint(operation), mint(obj_type)`; `domain_error` → `mint(domain)`; `evaluation_error` → `mint(error_type)`. `context` stays as passed (a message string, spec §6.4). Add `from clausal.logic.atoms import mint` (check for an import cycle — `atoms.py` imports only `sys`; safe).
  - `listing/1`: the `isinstance(val, str)` branches (:351, :388) become `is_atom_value(val)` with `name = spelling(val) if _term_is_atom(val) else val` (Plan 0: a str atom's spelling is itself).
  - `resolve_module`: at the top of designator handling, `if _term_is_atom(target): target = spelling(target)` — a written module designator arrives as an atom; the Python-API `str` path stays.
  - `abolish_table/2`: read `functor` through `spelling` when `_term_is_atom`.
- [ ] **Step 4:** focused PASS; suite gate — expect churn in `tests/test_term_inspection.py`, `tests/conformity/test_iso_term_manipulation.py`, `tests/test_exceptions.py` where results were asserted as `Compound`/bare str; fix those assertions to the cell/atom shape in this task (they are the spec's rows 7–12), and list every changed assertion in the report.
- [ ] **Step 5:** Commit: `"name position speaks atoms: functor/3 and =.. construct cells; global_atom/gensym/listing/resolve_module/exception terms via mint/spelling"`.

### Task 6: the chars family on atoms; `_chars_core.c` results as atoms

**Files:**
- Modify: `clausal/logic/builtins/chars.py` (`_atom_to_str` :48–72; `char_type/2` :155–249; `char_code/2` :250–290; `atom_chars/2` :348–390; `atom_codes/2` :395–434; `atom_concat/3` :439–508; `sub_atom/5` :512–608; `upcase_atom/2`, `downcase_atom/2`, `atom_length/2`)
- Modify: `clausal/logic/builtins/_chars_core.c` (`type_name_objs` :86, `ascii_char_objs` :97–112, unify sites :181, :199, :250, :296, :301, :490)
- Test: `tests/test_chars.py` (append a `TestCellAtoms` class)

**Interfaces:** Consumes `mint`, `char_atom`, `is_char_atom`, `spelling`. Produces C helper `atom_from_str(PyObject *s) -> PyObject*` (new ref) in `_chars_core.c` — Plan 0 body `return Py_NewRef(s);` — Stage B rewrites it to `PyTuple_Pack(1, s)`.

- [ ] **Step 1: Failing tests** (append to `tests/test_chars.py`):

```python
class TestCellAtoms:
    """Spec §6.6 with a 1-tuple atom input (Stage A: outputs still str)."""
    def test_atom_length_accepts_cell_atom(self):
        N = Var(); assert len(list(solve(("atom_length", ("abc",), N)))) == 1 and deref(N) == 3

    def test_atom_chars_accepts_cell_atom_and_char_atoms(self):
        L = Var(); list(solve(("atom_chars", ("ab",), L)))
        assert deref(L) == [char_atom("a"), char_atom("b")]
        A = Var(); list(solve(("atom_chars", A, [char_atom("a"), char_atom("b")])))
        assert deref(A) == mint("ab")

    def test_atom_concat_cell_atoms(self):
        X = Var(); list(solve(("atom_concat", ("a",), ("b",), X))); assert deref(X) == mint("ab")

    def test_sub_atom_cell_atom(self):
        S = Var(); answers = list(solve(("sub_atom", ("abc",), 1, 1, 1, S)))
        assert len(answers) == 1 and deref(S) == mint("b")

    def test_char_code_cell_char(self):
        C = Var(); list(solve(("char_code", ("a",), C))); assert deref(C) == 97
        Ch = Var(); list(solve(("char_code", Ch, 97))); assert deref(Ch) == char_atom("a")

    def test_char_type_cell_char_and_cell_type(self):
        assert len(list(solve(("char_type", ("a",), ("alpha",))))) == 1
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.**
  - `_atom_to_str`: first line `if _term_is_atom(val): return spelling(val)` (subsumes the `str` arm under Plan 0; keep the zero-arity class arm and the ground-`SegString` arm for now — Stage B deletes the `SegString` arm).
  - Every `unify(target, <str expression>)` that produces an ATOM becomes `unify(target, mint(<str expression>))`: `upcase_atom` :306, `downcase_atom` :321, `atom_chars` :385, `atom_codes` :430, `atom_concat` :470/:476/:483/:488–505 (Python fallback), `sub_atom` Python fallbacks (`unify(sub, s, …)`). Chars produced become `char_atom(c)`: `atom_chars` :366 → `[char_atom(c) for c in atom_str]`; `char_code` :288 → `char_atom(chr(vn))`; `char_type` chars enumeration (Python fallback) → `char_atom`. Char INPUT validation: `atom_chars` :379–381 → `if not is_char_atom(e): type_error("character", …)`; `char_code`/`char_type` single-char check → accept `is_char_atom(vc)` (spelling) OR the Plan 0 1-char `str`. Type names in `char_type/2` (`vt`) → read through `spelling` when `_term_is_atom(vt)`.
  - `_chars_core.c`: add near the top
    ```c
    /* atom_from_str(s): the atom whose spelling is *s* (new reference).
     * Plan 0 body — an atom IS its spelling.  Stage B of the atoms-as-cells
     * plan rewrites this to PyTuple_Pack(1, s).  Keep every result that is
     * an ATOM (not a code, not a position) going through here. */
    static inline PyObject *atom_from_str(PyObject *s) { return Py_NewRef(s); }
    ```
    Build `type_name_objs[t]` and `ascii_char_objs[i]` through `atom_from_str` at init (:86–112); wrap the `prefix`/`suffix` (:289–291), `s_obj` (:474) and the `ch_obj` (:250) results with it before `call_unify`. Char/atom INPUTS to the C helpers (`c_str`, `atom_str`, `vs`) are already passed as `str` by the Python side (`_atom_to_str` extracts the spelling), so no input change in C. `python setup.py build_ext --inplace`.
- [ ] **Step 4:** focused PASS; suite gate empty; `tests/test_chars.py` fully green (it exercises both the C and Python fallback paths — run it once more with `CLAUSAL_NO_C=1` if that switch exists; otherwise note the fallback path is covered by the parametrised fallback tests in `tests/test_python_fallbacks.py`).
- [ ] **Step 5:** Commit: `"chars family: atoms in, atoms out via mint/char_atom; _chars_core atom_from_str"`.

### Task 7: list machinery — chars are `char_atom`, promotion tests `is_char_atom` (Python + C twins)

**Files:**
- Modify: `clausal/logic/runtime/_seg_helpers.py:66–96` (`maybe_promote_to_str`)
- Modify: `clausal/logic/runtime/list_unify.py` (`:185–198` star splat; every `isinstance(e, str) and len(e) == 1`)
- Modify: `clausal/logic/runtime/body_star_unify.py` (all 21 `isinstance(x, str)` char tests; str→chars splats)
- Modify: `clausal/logic/builtins/lists.py` (`_as_items` :56–79, `_seq_result` :126–143)
- Modify: `clausal/terms.py` `SegString` (`__walk__` :1064–1087, `__unify__` :1182–1200, `__eq__` :1301–1309)
- Modify: `clausal/logic/runtime/_list_unify.c` (`seq_getitem` :66–76, `maybe_promote_to_str` :111–137, str-star splat :403–416, str segment :571–572)
- Modify: `clausal/logic/_lists_core.c` (`make_seq_result` :66–80; every site that reads a char out of a `str`)
- Test: `tests/test_atoms_as_cells.py` (append), twin parity `tests/test_python_fallbacks.py`

**Interfaces:** Consumes `char_atom`, `is_char_atom`. Produces C helpers, one copy per `.c` file (they do not share a header): `static inline PyObject *char_atom_obj(PyObject *ch1)` (new ref; Plan 0 `Py_NewRef(ch1)`) and `static inline int is_char_atom_obj(PyObject *e)` (Plan 0: `PyUnicode_Check(e) && PyUnicode_GET_LENGTH(e) == 1`) — Stage B rewrites both bodies in every copy.

- [ ] **Step 1: Failing tests** — under Plan 0 these are behaviour-preserving, so the tests pin the HELPER usage: a Python-level probe that monkeypatches `clausal.logic.atoms.char_atom` is fragile; instead pin through the twin-parity harness: extend `tests/test_python_fallbacks.py` with a case that unifies `["a", "b"]` (list of Plan 0 chars) against a `*`-pattern and asserts the C and Python twins produce the same promoted result, and a case where a list of TWO-char strs is NOT promoted. Both pass today; they become the regression net for Stage B. Also append to `tests/test_atoms_as_cells.py`:
```python
def test_maybe_promote_uses_is_char_atom(monkeypatch):
    from clausal.logic.runtime import _seg_helpers
    assert _seg_helpers.maybe_promote_to_str([char_atom("a"), char_atom("b")]) == "ab"
    assert _seg_helpers.maybe_promote_to_str(["ab", "c"]) == ["ab", "c"]
```
- [ ] **Step 2:** Implement, site by site (mechanical; list every changed line in the report):
  - Python: `isinstance(e, str) and len(e) == 1` → `is_char_atom(e)`; `list(s)` used to split a `str` into chars → `[char_atom(c) for c in s]`; `"".join(chars)` where `chars` are char atoms → `"".join(spelling(c) for c in chars)`. `SegString.__walk__` list validation → `is_char_atom(elem)`, join spellings; `__unify__` ground list arm → `unify([char_atom(c) for c in walked], other, trail)`; `ConcreteSeg(list(seg))` → `ConcreteSeg([char_atom(c) for c in seg])`; `__eq__` list arm → `all(is_char_atom(c) …) and w == "".join(spelling(c) …)`.
  - C: add the two helpers to each of `_list_unify.c` and `_lists_core.c`; `seq_getitem` str branch → `PyObject *ch = PySequence_GetItem(seq, i); PyObject *a = char_atom_obj(ch); Py_DECREF(ch); return a;`; `maybe_promote_to_str`/`make_seq_result` element test → `is_char_atom_obj(e)` and the join builds a list of spellings first (Plan 0: spelling is the element itself — write the join as a loop that appends `spelling_of(e)` where `spelling_of` is a third helper `static inline PyObject *char_spelling_obj(PyObject *e)` (borrowed; Plan 0 `return e;`, Stage B `return PyTuple_GET_ITEM(e, 0);`); str-star splat :403 → `char_atom_obj(PyUnicode_Substring(...))`. `build_ext`.
- [ ] **Step 3:** focused + twin parity PASS; suite gate empty.
- [ ] **Step 4:** Commit: `"list machinery: chars via char_atom/is_char_atom in Python and C twins (Stage A, behaviour-preserving)"`.

### Task 8: boundaries — one `to_python` conversion for `py.*` and `++`; JSON keys mint, `json.parse/3` atoms option

**Files:**
- Modify: `clausal/modules/py/_helpers.py:42–71` (`_deep_deref` → `to_python`; keep `_deep_deref` as an alias)
- Modify: `clausal/logic/compiler/terms_to_ast.py:1177–1205` (thunk arguments `$deref` → `$to_python`)
- Modify: `clausal/logic/compiler/predicate.py` (`INJECTED_RUNTIME_BUILTINS`: add `$to_python`) — grep `"$deref"` there to find the injection table
- Modify: `clausal/modules/py/json.py:46–72`, `:78–91` (`parse/2`), add `parse/3`
- Test: `tests/test_json_module.py` (append), `tests/test_python_boundary.py` (new)

**Interfaces (Produces):**
```python
# clausal/modules/py/_helpers.py
def to_python(val):   # outbound: atom → spelling str; str → str; list/tuple/DictTerm/dict recursed (keys converted); everything else raw
_deep_deref = to_python
```
`$to_python` is the injected runtime name the thunk lowering calls; `$deref` stays for every other site.

- [ ] **Step 1: Failing tests**
```python
# tests/test_python_boundary.py
"""Spec §9.1: one outbound conversion for py.* wrappers and ++ thunks."""
from clausal.modules.py._helpers import to_python
from clausal.logic.atoms import mint
from clausal.terms import DictTerm


def test_to_python_unwraps_atoms_everywhere():
    assert to_python(mint("bar")) == "bar"
    assert to_python([mint("a"), ("f", mint("b"))]) == ["a", ("f", "b")]
    assert to_python(DictTerm({mint("k"): mint("v")})) == {"k": "v"}


def test_thunk_argument_is_converted():
    # a ++ thunk receiving an atom sees its spelling (Plan 0: same object; the
    # assertion pins the ROUTE — the compiled body must call $to_python)
    import ast
    from clausal.logic.compiler.terms_to_ast import term_to_ast_expr
    from clausal.terms import PyThunk
    from clausal.logic.variables import Var
    v = Var()
    expr = term_to_ast_expr(PyThunk(lambda x: x, [v]), {})
    assert "$to_python" in ast.dump(expr)
```
and in `tests/test_json_module.py`:
```python
def test_json_parse_3_atoms_option_mints_listed_strings():
    T = Var()
    list(solve(("py.json.parse", '{"k": "red", "j": "text"}', T, [("atoms", ["red"])])))
    d = deref(T)
    assert d[mint("k")] == mint("red") and d[mint("j")] == "text"
```
(Check how the module-qualified goal is spelled in the existing `test_json_module.py` tests and use that spelling.)

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.**
  - `_helpers.py`: rename `_deep_deref` → `to_python`; add at the top `if _term_is_atom(val): return spelling(val)` after the `deref`; in the DictTerm/dict arms convert keys too: `{to_python(k): to_python(v) …}`; `_deep_deref = to_python` alias so the 11 in-file callers and out-of-tree wrappers keep working.
  - `terms_to_ast.py` thunk lowering: `_name("$deref")` → `_name("$to_python")` (both occurrences in that block). Inject `$to_python` next to `$deref` in `INJECTED_RUNTIME_BUILTINS` (`from clausal.modules.py._helpers import to_python` lazily — `modules/py` imports `clausal.terms`; verify no cycle by importing `clausal.logic.compiler.predicate` fresh in a subprocess).
  - `json.py`: `_python_to_clausal(obj, atoms=frozenset())` — dict keys `mint(k)`; `str` values `mint(obj) if obj in atoms else obj`; `_clausal_to_python`: atom → `spelling`; DictTerm keys → `to_python(k)`; a cell of arity ≥ 1 → `raise LogicException(type_error("json_term", term, "py.json.generate/2"))`. `parse/3`: third arg a list of `(atoms, List)` options; anything else → `domain_error("json_option", …)`.
- [ ] **Step 4:** focused PASS; suite gate empty (`tests/test_json_module.py`, `tests/test_http_module.py`, `tests/test_files_module.py` are the consumers).
- [ ] **Step 5:** Commit: `"boundaries: to_python for py.* and ++ thunks; JSON keys mint, parse/3 atoms option"`.

### Task 9: compiler-side acceptors and the identity pins

**Files:**
- Modify: `clausal/import_hook.py:123–166` (`_intern_atom`), `clausal/logic/compiler_v2.py:1428–1436`, `:1486–1494`, `:1636–1644`, `:1683–1693`, `:494–501`
- Modify: `clausal/logic/compiler/terms_to_ast.py:390–405` (`_functor_from_binding`), `:1066–1077` (zero-arity class → Constant)
- Modify: `clausal/logic/compiler/head_match.py:788–800` (resolved atom → cell pattern)
- Modify: `clausal/logic/compiler/globals_env.py:478–492`
- Modify: `clausal/logic/atoms.py` (`is_mangled`, `demangle`, `demangle_for_display` accept an atom)
- Modify: `clausal/logic/builtins/higher_order.py:112–126` (`_resolve_named_goal` — no change needed for cells; verify `call(("foo",), 1)` folds; add the test)
- Test: `tests/test_atoms_as_cells.py` (append), `tests/test_first_arg_index.py` (append one cell-atom head/caller probe)

- [ ] **Step 1: Failing tests** (append):
```python
def test_call_n_folds_cell_atom_goal():
    # atom/1 is a builtin: call(atom, foo) == atom(foo)
    assert _true(("call", ("atom",), ("foo",)))


def test_is_mangled_accepts_atom():
    from clausal.logic.atoms import is_mangled, mangle, demangle_for_display
    a = mint(mangle("m", "bar"))
    assert is_mangled(a) and demangle_for_display(a) == "m.bar"


def test_head_match_on_resolved_cell_atom(tmp_path):
    # a clause head whose first arg is a declared atom must still dispatch when
    # the module binding is a cell atom (head_match resolved-name branch)
    src = "-private([red])\ncolour(red),\n"
    mod = _load_inline_clausal("_hm_cell_atom", src)
    mod.__dict__["red"] = ("red",)          # simulate the Stage B binding shape
    assert len(list(solve(("colour", ("red",)), mod))) == 1
```
(Import `_load_inline_clausal` from `tests/test_double_quotes_directive.py`; if the simulated binding is set after compile the test must force a recompile — read how `tests/test_first_arg_index.py` triggers compilation and follow it; if a recompile cannot be forced from outside, drop this test and rely on Task 11's flip tests.)

- [ ] **Step 2:** Implement:
  - Every `predicate_builtins.get(name) is existing` / `is atom_val` → `==`; every `predicate_builtins.setdefault(name, name)` → `predicate_builtins.setdefault(name, mint(name))`; `leaked_pool_atom` shape test `isinstance(existing, str) and existing == name` → `is_atom_value(existing) and spelling_or_self(existing) == name` (write a local `_spelling_or_self(x)` = `spelling(x) if _term_is_atom(x) else x` in each file — two lines, no shared helper needed). `compiler_v2.py:1693` `module_dict[name] = sys.intern(name)` → `mint(name)` (a declared functor's name used as a value is the atom; the comment about not registering it in the pool stays true — `mint` is not the pool).
  - `_functor_from_binding`: accept `_term_is_atom(binding)` → return `spelling(binding)`.
  - `terms_to_ast.py:1076` zero-arity class → `ast.Constant(value=mint(term.__name__))` — under Plan 0 identical output.
  - `head_match.py:797`: `if _term_is_atom(resolved): return _cell_match_pattern(spelling(resolved), [])` BEFORE the `isinstance(resolved, str)` MatchValue line (Plan 0: a str resolved value takes the new branch too, producing the cell pattern for a `str` — WRONG under Plan 0, since the runtime value is a str). So gate it: `if type(resolved) is tuple and len(resolved) == 1 and type(resolved[0]) is str:` — the literal cell shape, not `is_atom` — with a comment that Stage B replaces the gate by `is_atom` once a str is no longer an atom.
  - `globals_env.py:487`: `type(binding) is str` → `is_atom_value(binding)` (a PredicateMeta is excluded by the `is_atom_value` class case? It is NOT — `is_atom_value` admits a zero-field class. Use `atoms.is_atom(binding)` here: under Plan 0 that is `type is str`, identical.)
  - `atoms.py`: `is_mangled(value)` → `if is_atom(value): value = spelling(value)` first; same in `demangle` and `demangle_for_display`. (Plan 0: no-op.)
- [ ] **Step 3:** focused + suite gate.
- [ ] **Step 4:** Commit: `"compiler: atom bindings compared by equality; acceptors for the cell atom (Stage A)"`.

### Task 10: quote map, `-double_quotes` mode threading, `"foo"(1)` refused

**Files:**
- Modify: `clausal/templating/term_rewriting.py` (`EmbedTransformer.__init__` :3726–3809 — new state; `_make_term_transformer` :4238–4259; `TermTransformer.__init__` :1209–1289 — new kwargs; `visit_Constant` :1585–1588 unchanged this task; call-sugar rewrite :1435–1440; `_handle_double_quotes_directive` :4921–4959)
- Create: `clausal/templating/quote_map.py`
- Test: `tests/test_quote_map.py` (new), `tests/test_double_quotes_directive.py` (append)

**Interfaces (Produces):**
```python
# clausal/templating/quote_map.py
def build_quote_map(source_lines: list[str]) -> dict[tuple[int, int], str]
    # key: (lineno, byte col_offset) of each STRING token's start AND end (end keyed by (end_lineno, end_byte_col));
    # value: the quote character after any prefix: "'" or '"'.  f-strings are not STRING tokens and are absent.
def quote_of(qmap, node: ast.Constant) -> str | None
    # "'" / '"' from the node's start; None if absent (e.g. a synthetic Constant); raises SyntaxError
    # "mixed quote styles in one literal" when the start and end tokens disagree.
```
`TermTransformer` gains `quote_map` and `double_quotes_mode` kwargs ("atom" | "chars"); `EmbedTransformer` holds `_quote_map` (built once from `source_lines`) and `_double_quotes_mode` (starts `"atom"` — the engine default until Plan 2; the directive sets it in file order).

- [ ] **Step 1: Failing tests**
```python
# tests/test_quote_map.py
import ast
from clausal.templating.quote_map import build_quote_map, quote_of


def _map_and_node(src):
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)
    node = tree.body[0].value
    return build_quote_map(lines), node


def test_single_and_double():
    qmap, node = _map_and_node("x = 'a'\n"[4:])
    assert quote_of(qmap, node) == "'"
    qmap, node = _map_and_node('"a"\n')
    assert quote_of(qmap, node) == '"'


def test_prefixes_and_triple():
    for src, q in (("r'a'\n", "'"), ('u"a"\n', '"'), ('"""a"""\n', '"'), ("b'x'\n", "'")):
        qmap, node = _map_and_node(src)
        assert quote_of(qmap, node) == q


def test_byte_offsets_after_non_ascii():
    qmap, node = _map_and_node('f("é", "b")\n')
    second = node.args[1]
    assert quote_of(qmap, second) == '"'


def test_implicit_concat_same_style_ok_mixed_raises():
    qmap, node = _map_and_node('"a" "b"\n')
    assert quote_of(qmap, node) == '"'
    import pytest
    qmap, node = _map_and_node('"a" \'b\'\n')
    with pytest.raises(SyntaxError):
        quote_of(qmap, node)
```
and in `tests/test_double_quotes_directive.py`:
```python
def test_double_quoted_string_as_functor_is_refused():
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal("_dq_functor", 'p("foo"(1)),\n')
    assert "functor" in str(exc_info.value)


def test_single_quoted_functor_sugar_still_works():
    mod = _load_inline_clausal("_sq_functor", "q('+'(1, 2)),\n")
    assert len(list(solve(("q", ("+", 1, 2)), mod))) == 1
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.**
  - `quote_map.py`: `tokenize.generate_tokens(iter(source_lines).__next__)`; for each `tokenize.STRING` token: `prefix_len = len(tok.string) - len(tok.string.lstrip("bBrRuU"))`; `q = tok.string[prefix_len]`; key start `(tok.start[0], len(source_lines[tok.start[0]-1][:tok.start[1]].encode("utf-8")))` and end `(tok.end[0], len(source_lines[tok.end[0]-1][:tok.end[1]].encode("utf-8")))` both → `q`. Wrap tokenize errors: return `{}` (a file tokenize cannot read is already rejected by `ast.parse`). `quote_of`: look up `(node.lineno, node.col_offset)` and `(node.end_lineno, node.end_col_offset)`; if both present and differ → `SyntaxError("mixed quote styles in one literal")` positioned at the node.
  - `EmbedTransformer.__init__`: `self._quote_map = build_quote_map(source_lines) if source_lines else {}`; `self._double_quotes_mode = "atom"`. `_make_term_transformer` passes both. `TermTransformer.__init__` stores them as `self._quote_map`, `self._double_quotes_mode`.
  - Call sugar :1435–1440: before the rewrite, `if quote_of(transformer._quote_map, call.func) == '"': raise SyntaxError(_positioned("a double-quoted string is never a functor (ISO 6.3.3): write 'foo'(…) or foo(…)", call.func))` — use whatever positioned-`SyntaxError` helper the file already has for atom-as-functor diagnostics (grep `_atom_as_functor_message`).
  - `_handle_double_quotes_directive`: `mode == "atom"` → `transformer._double_quotes_mode = "atom"; return Pass()`; `mode == "chars"` → still the "not yet supported" `SyntaxError` this task (Stage B accepts it); keep the other refusals.
- [ ] **Step 4:** focused PASS; suite gate empty.
- [ ] **Step 5:** Commit: `"compiler: quote map + double_quotes mode threading; \"foo\"(1) refused (ISO functor rule)"`.

---

## Stage B — THE FLIP (one task; the only red window is inside this task's working tree, never a commit)

### Task 11: atoms become `("bar",)`, `str` becomes a string

**Files:** everything named in the checklist below. **Model:** the most capable available. This task is large by necessity — every item is a body rewrite whose call sites Stage A already prepared. Work the checklist in order; run the focused tests after each block; run the suite gate only at the end (it is red mid-way by construction). Commit ONCE (or as a series of commits on a local scratch sequence squashed before the review package — the reviewer sees one diff).

**Interfaces (Produces):** `mint("bar") == ("bar",)`; `is_atom(("bar",))` True, `is_atom("bar")` False; `spelling(("bar",)) == "bar"`; `char_atom("a") == ("a",)`; a `.clausal` bare name or `'x'` literal compiles to `("x",)`; a `"x"` literal compiles to `("x",)` under `-double_quotes(atom)` (the default) and to `"x"` under `-double_quotes(chars)`; `mod.bar == ("bar",)`; `CLAUSAL_BYTECODE_TAG == 9`.

- [ ] **B1 — the five bodies** (`clausal/logic/atoms.py`): 
```python
_ATOMS: dict[str, tuple] = {}

def mint(spelling: str):
    if type(spelling) is not str:
        raise TypeError(...)
    a = _ATOMS.get(spelling)
    if a is None:
        s = sys.intern(spelling)
        a = _ATOMS.setdefault(s, (s,))
    return a

def is_atom(term) -> bool:
    return type(term) is tuple and len(term) == 1 and type(term[0]) is str

def spelling(atom) -> str:
    if not is_atom(atom): raise TypeError(f"not an atom: {atom!r}")
    return atom[0]

def char_atom(ch): (validate) return mint(ch)
def is_char_atom(term): return is_atom(term) and len(term[0]) == 1
```
Replace `test_repr_probe_plan0_str` in `tests/test_atoms_api.py` with `assert mint("foo") == ("foo",) and mint("foo") is mint("foo")` (the `is` here pins the CANONICAL-INSTANCE optimisation of `mint` itself, the one place identity is allowed to be observed). `predicate.is_atom_value(obj)` → `_term_is_atom(obj) or is_atom(obj)` is already right; its docstring is rewritten.

- [ ] **B2 — compiler emission** (`term_rewriting.py`):
  - `visit_Name` atom branches :1915–1921 → `Constant(value=(mangle(...),))` and `Constant(value=(identifier,))`.
  - `visit_Constant` :1585–1588 →
    ```python
    def visit_Constant(transformer, constant):
        value = constant.value
        if type(value) is str:
            q = quote_of(transformer._quote_map, constant)
            if q == '"' and transformer._double_quotes_mode == "chars":
                return constant                      # a string
            return replace(Constant(value=(sys.intern(value),)), constant)   # an atom
        return constant
    ```
    (A synthetic `Constant` with no position → `q is None` → atom, the safe reading for compiler-built spellings.) Audit every direct `Constant(value=<str>)` construction in the file that is NOT a spelling (keyword names :1497–1505, `LoadName` names :1368/:1921/:1942, `_reg_atom` translations :6283–6296, dict-key `$intern_atom` argument :1627–1634): those are consumed as identifier `str`s by their own runtime and must stay `str`. The DCG terminal `Constant` case :2965–2972 is left as it is (a `str` literal terminal is destructured into chars regardless of quote style in this plan — parked for Plan 2, note it in the docstring).
  - `_make_atom_str_assign_ast` :2656–2710: the generated line becomes `{atom_name} = $mint({value!r})` — build the RHS as `Call(Name("$mint"), [Constant(value)])` after `parse()` (a `$` name cannot be parsed from text; replace the parsed `Assign.value` node). Inject `$mint` (= `atoms.mint`) into `INJECTED_RUNTIME_BUILTINS` beside `$intern_atom`.
  - `_handle_double_quotes_directive`: `chars` → `transformer._double_quotes_mode = "chars"; return Pass()`. Update the docstring (R-S4 text stays; "chars is refused until the flip" goes).
  - `compiler_v2._process_bare_atom_refs` :1494, `_process_declarations` :1642, `_imported_reference` :501, `import_hook._intern_atom` :147/:166: already `mint(name)` from Task 9 — verify.
  - `terms_to_ast.py:1076`: already `mint(...)` from Task 9 — verify.
  - `head_match.py:797` gate → `if _term_is_atom(resolved):` (replace the literal-shape gate from Task 9).
  - `CLAUSAL_BYTECODE_TAG = 9` with a comment line `8 -> 9 (atoms-as-cells Stage B): atom Constants are ("bar",) cells; a stale .pyc binds foo = 'foo', a STRING`.

- [ ] **B3 — `str` demotion (Python):**
  - `type_checks.py`: `_check_type` `("string","str")` unchanged; `"atom"` → `is_atom_value` (now excludes `str`); `must_be`/`can_be` Type arg: delete the `isinstance(type_val, str)` arm (a string Type → `type_error(atom)`); `callable_/1`: delete the `isinstance(x_val, str)` branch and `_str_is_callable`; `atomic/1`: remove `str` from the primitives tuple (a string is a list).
  - `chars._atom_to_str`: delete the ground-`SegString` arm (a string is not an atom; ISO `type_error(atom)`).
  - `higher_order._resolve_named_goal` :123–126, `solve._term_to_goal` :211–219, `cells.resolve_qualified_goal_cell` :453–454: delete the `type(x) is str` wraps; in `_resolve_named_goal` a `str` goal → `raise LogicException(type_error("callable", goal_val, "call/N"))`; in `_term_to_goal` likewise `"solve/1"`.
  - `_helpers.py` funnel wrappers `_functor_name/_arity/_nth_arg/_args_list/_is_compound` (:360–394): add a `type(term) is str` arm BEFORE delegating to the pre-cell impl — `_functor_name`: `"[]" if not term else "."`; `_arity`: `0 if not term else 2`; `_nth_arg`: `1 → char_atom(term[0])`, `2 → term[1:]`, else `IndexError`; `_args_list`: `[] if not term else [char_atom(term[0]), term[1:]]`; `_is_compound`: `bool(term)` (a non-empty list is not compound today either — keep `False`; check `_is_compound_py([1])` and mirror it). The C impls are never reached for a `str` after this.
  - `_standard_order_key`: the `isinstance(term, str)` line → `return (_ORD_SEQ, tuple((_ORD_ATOM, c) for c in term))` (string keys as its char list; §6.5). `sort/2` dedup (`lists.py:519–522`) → dedup by key equality (`_standard_order_key(a) == _standard_order_key(b)`), keeping the first occurrence.
  - `arg_index.py`: `_INDEXABLE_TYPES = (int, float, bytes, bool, type(None))` (drop `str`); `_runtime_arg_key` fast path `if t is int or t is str: return a` → `if t is int: return a`; `_bytelist_to_bytes_or_none` unchanged. Verify `""`, `[]`, `b""` all key `_INDEX_VAR` (empty bytes: `isinstance(b"", bytes)` → keys `b""`; so `[]` must too — an empty list currently returns `None` from `_bytelist…` → `_INDEX_VAR`; make `""` and `[]` and `b""` agree by keying all three `_INDEX_VAR`: add `if a == b"" or a == "" : return _INDEX_VAR` guards in both twins). Rewrite the R8 rationale comment.
  - `SegString`: `__walk__` accepts only char atoms in a list segment (the Plan 0 `str` arm inside the element loop goes); `__unify__` list arm → `return unify(walked, other, trail)` (the C arm does the work now).
  - `is_list/1`, `is_chars/1`, `length/2`, `_as_items`: unchanged (a `str` IS a list).
  - `exceptions.py`: unchanged (Task 5 minted).
  - `io.py` `_format_term_for_io`: `str` → text (as today, minus the `is_mangled` check, which cannot fire on a string); `_format_clause_term` `str` → `quote_string(val)`; cells/lists → `term_str(val, quoted=False)`. `term_canonical`'s `str` branch → the cons form of the char list (`'.'(h,'.'(e,…,[]))`; `""` → `[]`), spec §6.7 / §13 row 18b.
  - `terms.py term_str` `str` branch → `quote_string(t)` if `quoted` else `t`; the `list` branch → `if t and all(is_char_atom(e) for e in t): return quote_string("".join(spelling(e) for e in t)) if quoted else "".join(...)` (spec §6.7 row 4) — `[]`/`""`: `""` is a `str` → hits the str branch → renders `""`? Spec says `[]`. Add `if t == "": return "[]"` at the top of the str branch. `term_html`: same shape.
  - `reflection._ClauseRenderer.term`: `str` → `ast.Constant(value)` (a string; the renderer's caller `render_source` post-processes with the `fmt/emit.py:320` `_prefer_double_quotes` shape — call it on the rendered text so every string constant is double-quoted, and have `render_source` prepend `-double_quotes(chars)` when it emitted at least one string).
  - `testing._atomize_declared_atoms` / `_reify_value` :1517–1545, :1595–1610: the `isinstance(value, str)` guess → `if _term_is_atom(value) and (spelling(value) in declared or is_mangled(value)): return Atom(name=spelling(value))`; a plain `str` is a string and is returned as is.

- [ ] **B4 — C twins:**
  - `_variables.c`: reinstate the str↔list arm at :1168 (both orientations), modelled on the bytes arms :1188–1258:
    ```c
    /* ---- String ↔ List unification (spec §6.2): a str denotes the list of
     * its char atoms ("h",).  Var element → bind to the char atom; a 1-tuple
     * element whose slot 0 is a 1-char str → compare code points, no
     * allocation; anything else → delegate to do_unify(char_atom, elem). */
    if (PyUnicode_Check(t1) && PyList_Check(t2)) {
        Py_ssize_t n = PyUnicode_GET_LENGTH(t1);
        if (n != PyList_GET_SIZE(t2)) return 0;
        if (n == 0) return 1;
        int kind = PyUnicode_KIND(t1); const void *data = PyUnicode_DATA(t1);
        for (Py_ssize_t i = 0; i < n; i++) {
            Py_UCS4 c1 = PyUnicode_READ(kind, data, i);
            PyObject *elem_raw = PyList_GetItemRef(t2, i);
            if (elem_raw == NULL) return -1;
            PyObject *elem = var_deref(elem_raw);
            if (Var_Check(elem)) {
                PyObject *a = char_atom_from_ucs4(c1);
                if (!a) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(a, elem, trail, depth + 1, oc);
                Py_DECREF(a); Py_DECREF(elem_raw);
                if (r != 1) return r;
            } else if (PyTuple_CheckExact(elem) && PyTuple_GET_SIZE(elem) == 1
                       && PyUnicode_Check(PyTuple_GET_ITEM(elem, 0))
                       && PyUnicode_GET_LENGTH(PyTuple_GET_ITEM(elem, 0)) == 1) {
                Py_UCS4 c2 = PyUnicode_READ_CHAR(PyTuple_GET_ITEM(elem, 0), 0);
                Py_DECREF(elem_raw);
                if (c1 != c2) return 0;
            } else {
                PyObject *a = char_atom_from_ucs4(c1);
                if (!a) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(a, elem, trail, depth + 1, oc);
                Py_DECREF(a); Py_DECREF(elem_raw);
                if (r != 1) return r;
            }
        }
        return 1;
    }
    /* symmetric arm: PyList_Check(t1) && PyUnicode_Check(t2) — same loop with roles swapped */
    ```
    with `static PyObject *char_atom_from_ucs4(Py_UCS4 c)` returning a new ref from a 128-entry static cache of `("x",)` tuples for ASCII (built at module init) and `PyTuple_Pack(1, PyUnicode_FromOrdinal(c))` otherwise. The mixed list/tuple guard :1310 stays (it now runs after the str arms and still makes `("a",) = "a"` fail).
  - `_list_unify.c`, `_lists_core.c`: `char_atom_obj` → `PyTuple_Pack(1, ch1)`; `is_char_atom_obj` → the 1-tuple/1-char test above; `char_spelling_obj` → `PyTuple_GET_ITEM(e, 0)`. Delete the `star_was_str` gate (:366–372, :696–707) and its Python twin (`list_unify.py:185–198`): promotion now fires unconditionally, which is correct because a list of char atoms IS the string (spec §6.2). `_chars_core.c`: `atom_from_str` → `PyTuple_Pack(1, s)` after `PyUnicode_InternInPlace(&s)` on a fresh copy (never intern a borrowed object in place — `Py_INCREF` first).
  - `build_ext`; `tests/test_python_fallbacks.py` twin parity green.

- [ ] **B5 — reader and `.pl` loader:**
  - `prolog_reader.py:155–161`: `PAtom → mint(node.name)`; `PString → node.value` (a `str`). Update the locked contract text at :13–24 and `tests/toklex/test_driver.py` / `tests/test_prolog_reader*.py` expectations.
  - `prolog_to_clausal.py:616`: `PString` → `quote_string(term.value)`; the module emitter writes `-double_quotes(chars)` as its first directive when any `PString` was emitted; a quoted `PAtom` → `quote_atom` (single quotes; bare names unchanged). `PrologLoader` tests in `tests/test_prolog_to_clausal.py` updated: a `.pl` string loads as a string.

- [ ] **B6 — engine-internal `.clausal` fixtures and the suite's own assertions.** Run the suite gate; work the red set down with these rules, and no other change: (a) an assertion comparing an atom result to a bare `str` → compare to `mint("…")` (or `("…",)`); (b) an assertion that a value `is` another → `==`; (c) a fixture that means STRINGS by `"…"` (DCG char lists excepted — unchanged this plan) gets `-double_quotes(chars)` as its first directive; (d) a Python-side test building a goal with a `str` where an atom was meant → `mint`; (e) `test_double_quotes_chars_is_refused_until_the_flip` → renamed `…_is_accepted_after_the_flip`, asserting `string(X)` for `X = "hello"` in a chars module and `atom(X)` in an atom module (spec §13 row 26); (f) `tests/test_atoms_as_cells.py` Stage A probes that asserted the Plan 0 shape (`char_atom("a") == "a"`-style) are updated to the cell shape; (g) `test_string_list_unification.py`, `test_string_head_patterns.py`, `test_segstring.py`, `test_chars.py`: chars are `("a",)` now — update expected values, keep the cases. Every other red is a REGRESSION: fix the engine, not the test, and list it in the report. Target: failing-name set byte-identical to the baseline.

- [ ] **B7 — the spec's acceptance rows as tests:** `tests/test_atoms_as_cells_flip.py` (new) pins §13 rows 1–30 verbatim (one test per row, named `test_row_NN_…`), each written as a `.clausal` snippet loaded through `_load_inline_clausal` where the row is source-level (rows 1–6, 24–27, 30) and as a Python `solve` where it is builtin-level.

- [ ] **B8 — commit** (single diff for review): `"THE FLIP: atoms are arity-0 cells, str is a string (Scryer chars); 'x' atom / \"x\" per -double_quotes; bytecode tag 9"`.

---

## Stage C — cleanup, docs, gates

### Task 12: delete the dual-acceptance leftovers; rename the class test

**Files:**
- Modify: `clausal/logic/predicate.py` (`is_atom` → `is_zero_field_class`, keep `is_atom` as a deprecated alias for the C symbol only inside the module), its 7 importers (`solve.py`, `builtins/chars.py`, `builtins/inspection.py`, `builtins/type_checks.py`, `builtins/_helpers.py`, `compiler/_lower_goalop_shared.py`, `compiler/terms_to_ast.py`)
- Modify: `clausal/logic/builtins/type_checks.py`, `chars.py`, `inspection.py`, `_helpers.py`, `higher_order.py`, `io.py`: every `isinstance(x, str)` that survived Stage B and still means "atom" (grep `isinstance(.*, str)` in `clausal/logic/builtins/` and classify each: string-meaning stays, atom-meaning is dead code → delete)
- Modify: `clausal/logic/compiler/head_match.py:357–366` (comment), `clausal/logic/runtime/list_unify.py`, `_list_unify.c` (comments referencing the retired cons rule / `star_was_str`)
- Test: existing suite

- [ ] **Step 1:** `grep -rn "is_atom\b" clausal --include=*.py` — rename the class test to `is_zero_field_class` at the definition and the 7 importers; `predicate.__all__` exports both names for one release with `is_atom = is_zero_field_class` and a deprecation comment (the C extension registers the symbol `is_atom`; leave the C name alone).
- [ ] **Step 2:** Classify and delete dead `str`-as-atom arms; rewrite the three stale comments.
- [ ] **Step 3:** Suite gate empty; `tests/test_funnel_lint.py` green.
- [ ] **Step 4:** Commit: `"cleanup: retire str-as-atom arms; is_zero_field_class"`.

### Task 13: documentation

**Files:**
- Rewrite: `docs/syntax.md:620–664` (the "Atoms vs strings" section — atoms are cells, `'x'` atom, `"x"` per `-double_quotes`, strings are char lists, `"foo"(1)` refused, no string atoms), `docs/strings_as_lists.md` (chars are atoms `("a",)`; `"" = []`; promotion), `docs/dicts_sets.md:154–156` (now true — atom and string keys distinct), `docs/directives.md:559–580` (`-double_quotes` both modes, the ratchet lifetime), `docs/builtins.md` (chars family `type_error(atom)` on strings; `writeq/1`, `write_canonical/1`; `functor/3`, `=..` name position; `json.parse/3` atoms option), `docs/type_checking.md` (`atom/1`, `string/1`, `atomic/1`, `callable/1` table of spec §6.3), `docs/io.md` (write vs writeq), `docs/python_integration.md` (`to_python`: atoms cross out as text, text comes back as strings; `mint`/`spelling`/`is_atom` API; `mod.bar` is `("bar",)`), `docs/importing_prolog.md` (`.pl` strings load as strings)
- Test: `tests/fixtures/docs/*.clausal` doc-snippet fixtures — update the ones the rewritten sections quote; the doc-snippet runner in the suite must stay at the baseline failure set.

- [ ] **Step 1:** Rewrite each section from the spec (§5–§9); every code example runnable; no downstream names.
- [ ] **Step 2:** Suite gate empty (doc-snippet tests).
- [ ] **Step 3:** Commit: `"docs: atoms as cells, strings as char lists, -double_quotes ratchet, writeq"`.

### Task 14: perf gate and final review package

**Files:** none (measurement + report under `.superpowers/sdd/2026-09-06-atoms-as-cells-strings/perf-report.md`).

- [ ] **Step 1:** Build a second worktree at `a8a2d2f7` (pre-plan tree) with `build_ext`; interleave A (pre) / B (post) runs, 5 rounds each, fresh subprocesses, for `bench_struct_tabling`, `bench_fib`, and the list/string benches in `benchmarks/workloads.py` (grep `def bench_` for names containing `list`, `string`, `str`, `append`, `dcg`), plus one `++`-heavy bench (grep for a workload calling a thunk; if none exists, add `bench_thunk_atoms(n)` that calls `++len(X)` on an atom-bearing list n times — commit it as part of this task).
- [ ] **Step 2:** Report medians, spreads, B/A per bench. Bar: 3%. If the thunk bench exceeds the bar, apply the spec §9.1 fallback (thunk arguments unwrap a TOP-LEVEL atom only: `$to_python` → `$unwrap_atom` = `spelling(x) if is_atom(x) else x`), re-measure, and record the ruling in the ledger and in `docs/python_integration.md`.
- [ ] **Step 3:** Round-trip and refusal gates of spec §12 are covered by `tests/test_atoms_as_cells_flip.py` (Task 11 B7) — confirm each is present by name in the report.
- [ ] **Step 4:** Commit the report file only if the workspace directory is tracked (it is git-ignored — do not commit it); hand the final review package to the whole-branch reviewer.

---

## After this plan (not tasks here)

- Controller: announcement to downstream lanes (spec §11) through the coordination channel; the `todo/` parked-questions file (spec §14) in the canonical repo.
- Plan 2 (default → `chars`) and Plan 3 (delete `-double_quotes/1`) are separate short plans gated on downstream reports.

## Self-review record

- Spec coverage: §5.1 (Task 1, 11-B1), §5.2 (Task 9, 11-B1), §5.3 (Task 9), §6.1 (Task 1), §6.2 (Task 7, 11-B4), §6.3 (Task 2, 11-B3), §6.4 (Task 5, 11-B3), §6.5 (Task 3, 11-B3), §6.6 (Task 6), §6.7 (Task 4, 11-B3), §6.8 (Task 8; DictTerm needs no code — keys are `mint`ed by `$intern_atom`), §6.9 (11-B3), §7 (Task 10, 11-B2/B5), §8 (no change), §9.1 (Task 8), §9.2 (Task 8), §9.3 (11-B2), §9.4 (Task 8 alias + docs Task 13), §9.5 (none needed), §9.7 (11-B5), §10 Plan 0/1 (Tasks 1–13), §12 gates (Task 14 + every task's suite gate), §13 rows (11-B7).
- Type consistency: `mint/is_atom/spelling/char_atom/is_char_atom` (Task 1) used verbatim in Tasks 2–11; `_term_is_atom` is the local import alias for `atoms.is_atom` wherever `predicate.is_atom` (the class test) is also imported; C helpers `atom_from_str` (Task 6), `char_atom_obj`/`is_char_atom_obj`/`char_spelling_obj` (Task 7), `char_atom_from_ucs4` (Task 11) as named; `to_python`/`$to_python` (Task 8); `quote_map.build_quote_map`/`quote_of` (Task 10); `term_str(..., quoted=)` (Task 4).
