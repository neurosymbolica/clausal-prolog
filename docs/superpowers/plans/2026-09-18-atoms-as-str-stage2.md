# Atoms-as-str, STAGE 2 (the atom flip) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An atom is a Python `str` in every position; the arity-0 cell `('x',)` is refused as RESERVED; a
string stays the `('$chars', s)` carrier stage 1 built.

**Architecture:** Stage 1 made every text value the carrier and armed a rule that refuses a bare `str` as
text. Stage 2 therefore only has to change what a bare `str` MEANS: it is the atom. The change goes through
the atoms API (`mint`/`is_atom`/`spelling`/`char_atom`/`is_char_atom` — ~300 call sites need no edit), the
reader (an atom literal compiles to the interned str), the C twins (the str-as-text unify/list arms go,
the 1-tuple char sites become 1-char strs), the ten armed entry points (the refusal becomes "an atom is not
text"), and the seam (a Python str crossing in IS the atom, spec §3 Q1). Everything that treated the
arity-0 cell as the atom is deleted, including the zero-field-class-as-atom legacy and the name-clash
diagnostic (spec §4).

**Tech Stack:** CPython 3.13, the engine's C extensions (`setup.py build_ext --inplace` after every C
change, in a worktree no long-lived process has imported), pytest via `/workspace/clausal/venv/bin/python`.

**Spec:** `docs/superpowers/specs/2026-09-18-atoms-as-str-design.md` (§1 representation table, §2 carrier,
§3 seam, §4 what disappears, §5 staging, §6 gates, §8 rulings Q1–Q5). Stage 1 is on the parent commits
(`feat/chars-carrier-stage1-2026-09-18` @ 1c24bd65); its handoff
`implementation_plans/SESSION-HANDOFF-2026-09-18-engine-lane-b-END.md` lists the funnels.

## Global Constraints

- Branch `feat/atoms-as-str-stage2-2026-09-18` (canonical repo), SEPARATE sha from stage 1; never merge into
  stage 1's branch; nothing lands or pushes (spec §5 step 6: landing window is the operator's).
- `[]` stays the Python list as the canonical empty list; `mint("[]")` answers `[]`; the str `'[]'` is the
  same atom (spec Q3). `key_of("[]")` answers `NIL_KEY` = `()`.
- `('x',)` is REFUSED as RESERVED with the message
  `TypeError: the 1-tuple ('x',) is reserved (a future opaque Python object reference); an atom is the str 'x'`
  (spec Q2 ruling; todo `reserve-the-1-tuple-for-opaque-python-object-references-2026-09-18.md`).
- Text is the carrier only: `chars("...")` / `('$chars', s)`; `str_chars`/`join_chars` keep the char-atom
  list as a list of 1-char strs. Code lists stay `bytes`.
- Gate per task: the neighbour set (`tests/test_chars_carrier.py`, `tests/test_atoms_as_cells*.py`,
  `tests/test_double_quotes*.py`, `tests/test_dcg*.py`, `tests/test_*standard_order*.py`, `tests/iso`,
  `tests/rewrite`, `tests/fixtures/docs/*.clausal`) plus the task's own file; run with
  `-q -p no:randomly -p no:cacheprovider --tb=line` and read the summary line, never `| tail && commit`.
- Final gate (Task 9): clean-base A/B where BASE = stage 1 tip `1c24bd65` in a detached worktree (its own
  build + the stray `clausal/logic/_trampoline` .so mirrored so both trees carry 13 extensions), candidate =
  this branch tip, same shape; NEW 0 / GONE 0 on the failure-NAME set and identical skip sets; exporter
  goldens (`tests/test_clausal_to_prolog*.py`), `tests/test_comparison_twin_parity.py`; harness
  RE-BASELINE (not a diff) at landing.

---

### Task 1: The atoms API flips; the 1-tuple is refused

**Files:**
- Modify: `clausal/logic/atoms.py:172-344` (`mint`, `key_of`, `is_atom`, `spelling`, `char_atom`, `is_char_atom`)
- Modify: `clausal/logic/cells.py` (`_cell_shape`, `compound_cell_shape`, new `refuse_reserved_1tuple`)
- Test: `tests/test_atoms_as_str_stage2.py` (new)

**Interfaces:**
- Produces: `mint(s) -> str` (interned; `[]` for `"[]"`), `key_of(s) -> str | NIL_KEY`, `is_atom(x) -> bool`
  (`type(x) is str`), `spelling(a) -> str` (identity for a str; `"[]"` for nil), `char_atom(ch) -> str`,
  `is_char_atom(x) -> bool` (`type(x) is str and len(x) == 1`), `cells.refuse_reserved_1tuple(x) -> None`
  (raises `TypeError` on a 1-tuple whose slot 0 is a str; the ONE spelling of the refusal), and
  `cells.is_reserved_1tuple(x) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_atoms_as_str_stage2.py
"""Stage 2 of the atoms-as-str flip (spec 2026-09-18 §1, §4, Q2, Q3): an
atom is a Python str; the arity-0 cell is RESERVED and refused."""
import pytest
from clausal.logic.atoms import (mint, key_of, is_atom, spelling, char_atom,
                                 is_char_atom, NIL_KEY)
from clausal.logic.cells import (chars, is_chars, refuse_reserved_1tuple,
                                 is_reserved_1tuple, compound_cell_shape, _cell_shape)


def test_an_atom_is_the_interned_str():
    a = mint("foo")
    assert a == "foo" and type(a) is str and is_atom(a) and spelling(a) == "foo"
    assert mint("foo") is mint("foo")            # interned: identity fast path on slot 0 stays


def test_nil_spellings_are_one_atom():
    assert mint("[]") == [] and key_of("[]") is NIL_KEY and spelling([]) == "[]" and spelling("") == "[]"


def test_a_char_atom_is_a_one_char_str():
    assert char_atom("a") == "a" and is_char_atom("a") and not is_char_atom("ab") and not is_char_atom(chars("a"))


def test_a_string_is_not_an_atom_and_an_atom_is_not_text():
    assert not is_atom(chars("foo")) and is_chars(chars("foo"))
    assert not is_chars("foo")


def test_the_1_tuple_is_reserved():
    assert is_reserved_1tuple(("x",)) and not is_reserved_1tuple(("f", 1)) and not is_reserved_1tuple(chars("x"))
    with pytest.raises(TypeError, match="reserved"):
        refuse_reserved_1tuple(("x",))
    with pytest.raises(TypeError, match="reserved"):
        _cell_shape(("x",))
    assert compound_cell_shape("x") == (False, None)
    assert compound_cell_shape(("f", 1)) == (True, "f")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_atoms_as_str_stage2.py -q -p no:randomly -p no:cacheprovider --tb=line`
Expected: FAIL (`mint("foo") == ("foo",)`, `refuse_reserved_1tuple` not importable).

- [ ] **Step 3: Flip the atoms API**

```python
# clausal/logic/atoms.py -- replace the bodies (docstrings kept, first lines updated)
def mint(spelling: str):
    if type(spelling) is not str:
        raise TypeError(f"mint: spelling must be a str, got {type(spelling).__name__}")
    if spelling == NIL_SPELLING:
        return []
    return sys.intern(spelling)          # STAGE 2: the atom IS the interned str

def key_of(spelling: str):
    if type(spelling) is not str:
        raise TypeError(f"key_of: spelling must be a str, got {type(spelling).__name__}")
    if spelling == NIL_SPELLING:
        return NIL_KEY
    return sys.intern(spelling)

def is_atom(term) -> bool:
    return type(term) is str            # STAGE 2 (spec §1): an atom is a Python str; a string is the carrier

def spelling(atom) -> str:
    if type(atom) is str:
        return atom
    if type(atom) in (list, str, bytes, tuple) and len(atom) == 0:
        return NIL_SPELLING
    raise TypeError(f"not an atom: {atom!r}")

def char_atom(ch: str):
    if type(ch) is not str or len(ch) != 1:
        raise ValueError(f"char_atom: expected a 1-char str, got {ch!r}")
    return ch

def is_char_atom(term) -> bool:
    return type(term) is str and len(term) == 1
```

```python
# clausal/logic/cells.py -- beside CHARS_TAG
def is_reserved_1tuple(x: Any) -> bool:
    """True for the arity-0 str-headed tuple ``('x',)`` -- the OLD atom cell, RESERVED after stage 2."""
    return type(x) is tuple and len(x) == 1 and type(x[0]) is str


def refuse_reserved_1tuple(x: Any) -> None:
    if is_reserved_1tuple(x):
        raise TypeError(
            f"the 1-tuple {x!r} is reserved (a future opaque Python object reference); "
            f"an atom is the str {x[0]!r} -- write mint({x[0]!r}) or the bare name")
```

In `_cell_shape` (cells.py ~line 300) add, before the slot-0 read: `if len(x) == 1: refuse_reserved_1tuple(x)`.
`compound_cell_shape` needs no change (a str is not a tuple; a 1-tuple now raises).

- [ ] **Step 4: Run the new file and the neighbour set**

Run the new file: PASS. Run the neighbour set: expect MANY failures (the reader still emits 1-tuples).
Record the count in the commit message; the next tasks bring it down. Do NOT fix them here.

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/atoms.py clausal/logic/cells.py tests/test_atoms_as_str_stage2.py
git commit -m "atoms-as-str stage 2, task 1: the atoms API answers strs; the 1-tuple is refused as RESERVED"
```

---

### Task 2: The reader and the head compiler emit str atoms; the name-clash diagnostic goes

**Files:**
- Modify: `clausal/templating/term_rewriting.py` (`visit_Constant` atom arm ~2870-2900; the 6 literal cells; `_make_atom_str_assign_ast`'s guard; `_make_functor_class_ast`'s guard)
- Modify: `clausal/logic/compiler/terms_to_ast.py` (`PredicateAsTermError` raise at ~1209 and the atom arm that emits `("x",)`)
- Modify: `clausal/logic/compiler/head_match.py` (the `"atom"` guard kind takes a str; the arity-0-cell branch at ~940 deleted; the `"str"` guard kind is for the carrier only)
- Modify: `clausal/logic/database.py` (`_is_structural_head_value`: a str is atomic — already; delete the arity-0-cell comment/branch)
- Modify: `clausal/logic/compiler/arg_index.py` (`_INDEXABLE_TYPES` gains `str`; the 1-tuple key branch deleted)
- Test: `tests/test_atoms_as_str_stage2.py`

**Interfaces:**
- Consumes: `mint`, `is_atom`, `is_reserved_1tuple` from Task 1.
- Produces: a compiled `.clausal` module whose atoms are strs at every position (head literals, body constants,
  dict keys, `-private`/`-module` declared atoms, `global_atom/2`).

- [ ] **Step 1: Write the failing tests**

```python
def _mod(tmp_path, body, hdr="-double_quotes(chars)\n-private([yes, no, a, b, foo])\n"):
    from clausal.testing import load_clausal_module
    p = tmp_path / "s2.clausal"; p.write_text(hdr + body)
    return load_clausal_module(p)

def _first(mod, name, *args):
    from clausal.logic.solve import call
    from clausal.logic.variables import deref
    for _ in call(name, *args, module=mod):
        return [deref(x) for x in args]
    return None

def test_an_atom_literal_compiles_to_the_str(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, "p(X) <- (X is foo)\nq(X) <- (X is 'foo')\nr(X) <- (X is \"foo\")\n")
    assert _first(mod, "p", Var()) == ["foo"] and _first(mod, "q", Var()) == ["foo"]
    assert _first(mod, "r", Var()) == [chars("foo")]

def test_an_atom_head_literal_matches_the_str_and_binds_output_mode(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, "p(foo, R) <- (R is yes)\np(bar, R) <- (R is no)\n", hdr="-private([yes, no, foo, bar])\n")
    assert _first(mod, "p", "foo", Var())[1] == "yes" and _first(mod, "p", mint("bar"), Var())[1] == "no"
    x = Var(); assert _first(mod, "p", x, Var())[0] == "foo"
    assert _first(mod, "p", chars("foo"), Var()) is None     # a STRING is not the atom

def test_an_atom_and_a_predicate_of_the_same_name_coexist(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, "foo,\np(X) <- (X is foo)\nq <- foo\n", hdr="")
    assert _first(mod, "p", Var()) == ["foo"] and _first(mod, "q") is not None

def test_first_arg_indexing_keys_an_atom_by_the_str(tmp_path):
    from clausal.logic.variables import Var
    body = "".join(f"c({a}, {i})\n" for i, a in enumerate(["a", "b", "foo", "yes", "no"]))
    mod = _mod(tmp_path, body)
    assert _first(mod, "c", "foo", Var())[1] == 2 and _first(mod, "c", chars("foo"), Var()) is None
```

- [ ] **Step 2: Run to verify they fail** (the reader still emits `("foo",)`; the name-clash raises).

- [ ] **Step 3: Implement**

`term_rewriting.visit_Constant`: where it returns `Constant(value=(mangled_or_name,))` for an atom, return
`Constant(value=sys.intern(name))` instead (keep the `'[]'` → `List(elts=[])` substitution). Every
`("...",)` literal cell in the file (6) becomes the bare str. In `terms_to_ast.py` delete the
`PredicateAsTermError` raise and the two guards that fed it (spec §4): a bare name in argument position is
the str whether or not a predicate of that name exists. In `head_match.head_to_match_pattern`: the branch
`if isinstance(term, str) or is_chars(term):` splits — a carrier keeps the `"str"` capture+unify guard; a
`str` takes the `"atom"` capture+unify guard (`list_guards.append(("atom", cap_name, term))`, the branch that
used to serve the 1-tuple, now deleted). In `arg_index.py`: `_INDEXABLE_TYPES = (int, float, bytes, bool,
type(None), str)`; delete the `len(arg) == 1` 1-tuple key branch (a 1-tuple raises in `_cell_shape` anyway).

- [ ] **Step 4: Run the task's tests and the neighbour set**; count must drop; the carrier file must stay green.

- [ ] **Step 5: Commit**

```bash
git add clausal/templating/term_rewriting.py clausal/logic/compiler/terms_to_ast.py clausal/logic/compiler/head_match.py clausal/logic/database.py clausal/logic/compiler/arg_index.py tests/test_atoms_as_str_stage2.py
git commit -m "atoms-as-str stage 2, task 2: the reader emits str atoms; head literals take the atom guard; the name-clash diagnostic is gone"
```

---

### Task 3: The C twins — a str is an atom, a 1-char str is a char, the carrier is the only text

**Files:**
- Modify: `clausal/logic/variables/_variables.c:1276-1330` (delete the two `PyUnicode`↔`PyList` unify arms; keep the carrier unwrap at 1218), `:997` (`char spelling` builder returns the str itself), `atom_from_str`/`char_atom_obj` (return the str, not a 1-tuple)
- Modify: `clausal/logic/runtime/_list_unify.c:89,101` (`char_spelling_obj`/`is_char_atom_obj` on a 1-char str), `:138,225` (`seq_getitem`/`seq_length`: a str is NOT a sequence — only the carrier and lists/bytes), `:378-405` (`PyUnicode_Check(d)` arms → carrier only), `:549`
- Modify: `clausal/logic/_lists_core.c:74,86`, `clausal/logic/_clpfd_core.c:274` (the 1-tuple char test → 1-char str)
- Test: `tests/test_atoms_as_str_stage2.py`, `tests/test_comparison_twin_parity.py`, `tests/test_python_fallbacks.py::TestListUnifyCharTwinParity`

**Interfaces:**
- Produces: `unify("ab", [a, b])` is FALSE (an atom is not a list); `unify(chars("ab"), ["a", "b"])` is TRUE;
  `_head_list_unify_input("ab", ...)` returns False (not a sequence); the C and Python twins agree on every
  row of `tests/test_python_fallbacks.py::TestListUnifyCharTwinParity`.

- [ ] **Step 1: Write the failing tests**

```python
def test_c_unify_does_not_read_an_atom_as_a_list():
    from clausal.logic.variables import unify, Trail
    t = Trail()
    assert not unify("ab", ["a", "b"], t) and unify(chars("ab"), ["a", "b"], t)
    assert unify("ab", "ab", t) and not unify("ab", chars("ab"), t)

def test_c_and_python_list_twins_agree_on_an_atom_target():
    from clausal.logic.runtime.list_unify import _head_list_unify_input_py
    from clausal.logic.runtime._list_unify import _head_list_unify_input
    from clausal.logic.variables import Var, Trail
    for fn in (_head_list_unify_input_py, _head_list_unify_input):
        assert fn("ab", [Var()], Var(), [], Trail()) is False          # an atom is not a sequence
        h, tl, t = Var(), Var(), Trail()
        assert fn(chars("ab"), [h], tl, [], t) is True and deref(h) == "a" and deref(tl) == chars("b")
```

- [ ] **Step 2: Run to verify they fail** (the str↔list arm still unifies `"ab"` with `[a, b]`).

- [ ] **Step 3: Implement** — delete the two str↔list arms in `_variables.c` (the carrier arm above them
stays); in every C helper that tested `PyTuple_CheckExact(e) && PyTuple_GET_SIZE(e) == 1` for a char, test
`PyUnicode_Check(e) && PyUnicode_GET_LENGTH(e) == 1` and return `e` as its own spelling; make
`atom_from_str`/`char_atom_obj` return a new reference to the str; in `_list_unify.c` remove `PyUnicode_Check`
from the sequence gates (a str target returns `Py_False`/is not a sequence; `is_chars_carrier` stays);
rebuild: `/workspace/clausal/venv/bin/python setup.py build_ext --inplace` in this worktree (it is imported
by nothing long-lived), then `python -c "from clausal.logic.variables import unify; ..."` as the positive
control BEFORE running pytest.

- [ ] **Step 4: Run** the task's tests, `tests/test_comparison_twin_parity.py`, `tests/test_python_fallbacks.py`, the neighbour set.

- [ ] **Step 5: Commit** (`git add` the four `.c` files and the test file; message
`atoms-as-str stage 2, task 3: the C twins -- a str is an atom, a 1-char str is a char, the carrier is the only text`).

---

### Task 4: The ten armed entry points become "an atom is not text"; the text-shape helpers follow

**Files:**
- Modify: the 10 `refuse_bare_str(` sites (`grep -rn "refuse_bare_str(" clausal --include='*.py'`):
  `builtins/lists.py::_as_items`, `runtime/_seg_helpers.py::normalize_seg_input`, `modules/py/__init__.py::to_text`,
  `modules/py/re.py::_coerce_subject`, `builtins/_helpers.py::_standard_order_key`,
  `runtime/body_star_unify.py` (2), `runtime/list_unify.py`, `builtins/type_checks.py::string/1`, `builtins/io.py::write_text`
- Modify: `clausal/logic/cells.py` (delete `BARE_STR_TEXT`, `refuse_bare_str`), `clausal/logic/clpfd.py::_text_list_eq`
  (`_TEXT_SPELLINGS = (SegString,)` plus the carrier; a str is not a text spelling),
  `clausal/logic/builtins/_helpers.py` (`_functor_name`/`_arity`/`_nth_arg`/`_args_list`/`_is_compound`: the
  `type(term) is str` arms answer ATOM: name = the str, arity 0, no args, not compound; the carrier arms stay),
  `clausal/logic/builtins/chars.py::_atom_to_str` (a str answers itself), the 5 `string_goal_error(` sites
  (a str goal is a CALL of that atom; the carrier keeps the existence_error), `builtins/type_checks.py`
  (`atom/1` true for a str; `string/1` false for a str), `runtime/_seg_helpers.py::seq_getitem`/`str_chars`
- Test: `tests/test_atoms_as_str_stage2.py`, `tests/test_chars_carrier.py` (delete `TestTheInterimRuleIsArmed`;
  the parity instrument's `"str"` arm becomes an ATOM arm asserting the *different* answers: `length/2` fails,
  `atom/1` succeeds)

**Interfaces:**
- Produces: `_as_items("ab") is None`; `normalize_seg_input("ab") == "ab"`; `to_text("ab") == "ab"` (an atom's
  spelling IS the text py-modules want, spec §3); `string/1` false and `atom/1` true for `"ab"`; `functor("ab", N, A)`
  gives `N = "ab"`, `A = 0`; `call("foo")` calls `foo/0`; `"ab" == [a, b]` is false, `"ab" @< foo` orders in the atom band.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_atom_is_not_text_at_the_funnels():
    from clausal.logic.builtins.lists import _as_items
    from clausal.logic.runtime._seg_helpers import normalize_seg_input
    from clausal.modules.py import to_text
    from clausal.logic.builtins._helpers import _functor_name, _arity, _args_list
    assert _as_items("ab") is None and _as_items(chars("ab")) == ["a", "b"]
    assert normalize_seg_input("ab") == "ab" and normalize_seg_input(chars("ab")) == "ab"
    assert to_text("ab") == "ab" and to_text(chars("ab")) == "ab"
    assert (_functor_name("ab"), _arity("ab"), _args_list("ab")) == ("ab", 0, [])
    assert (_functor_name(chars("ab")), _arity(chars("ab"))) == (".", 2)

def test_type_checks_and_goals(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, 'p(R) <- if_(atom(foo), R is yes, R is no)\nq(R) <- if_(string(foo), R is yes, R is no)\n'
                         'r(R) <- if_(atom("foo"), R is yes, R is no)\nfoo,\ns <- call(foo)\n')
    assert _first(mod, "p", Var()) == ["yes"] and _first(mod, "q", Var()) == ["no"] and _first(mod, "r", Var()) == ["no"]
    assert _first(mod, "s") is not None
```

- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** each site as the Interfaces block states; delete `refuse_bare_str`/`BARE_STR_TEXT`
  and the `CLAUSAL_BARE_STR_TEXT` mentions in `cells.py`.
- [ ] **Step 4: Run** the task's tests, `tests/test_chars_carrier.py`, `tests/iso`, the neighbour set.
- [ ] **Step 5: Commit** (`atoms-as-str stage 2, task 4: the armed entry points read a str as the atom; text is the carrier only`).

---

### Task 5: The seam — a Python str crossing in IS the atom (spec §3, Q1)

**Files:**
- Modify: `clausal/logic/python_terms.py::to_term` (delete the `type(value) is str: return chars(value)` arm;
  `_SCALARS` keeps str), `::from_term` (carrier → str stays; a str stays a str)
- Modify: `clausal/logic/to_python.py` (`wrap_text` becomes identity for a str — keep the function so the
  `$text_in` lowering needs no change; `unwrap_atom`: `_atom_spelling` is identity now; `to_python`: an atom
  crosses as itself, the carrier as its text)
- Modify: `clausal/modules/py/__init__.py::text_result` (UNCHANGED: a module RESULT is text and stays the carrier — spec §3 "text is a list of one-char strs or chars(...)")
- Modify: `clausal/logic/seam.py::text_of`/`text_value` (identity for a str)
- Test: `tests/test_atoms_as_str_stage2.py`, `tests/value_terms/test_python_to_term.py`, `tests/test_python_boundary.py`

- [ ] **Step 1: Failing tests**

```python
def test_a_python_str_crosses_in_as_the_atom_and_the_carrier_crosses_out_as_text():
    from clausal.logic.python_terms import to_term, from_term
    from clausal.logic.to_python import to_python, unwrap_atom, wrap_text
    assert to_term("ab") == "ab" and to_term({"k": "v"}) == {"k": "v"} and to_term(["ab"]) == ["ab"]
    assert from_term(chars("ab")) == "ab" and from_term("ab") == "ab"
    assert to_python("ab") == "ab" and to_python(chars("ab")) == "ab"
    assert unwrap_atom("ab") == "ab" and wrap_text("ab") == "ab"

def test_a_thunk_result_str_is_the_atom(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, 'p(R) <- (R is ++"foo".upper())\nq(R) <- if_(atom(++"x"), R is yes, R is no)\n')
    assert _first(mod, "p", Var()) == ["FOO"] and _first(mod, "q", Var()) == ["yes"]
```

- [ ] **Step 2–5:** run (fail), implement as listed, run the task's tests + `tests/value_terms` + `tests/test_python_boundary.py` + `tests/test_seam*.py`, commit
  (`atoms-as-str stage 2, task 5: a Python str crossing the seam is the atom`).

---

### Task 6: The zero-field-class-as-atom legacy and the arity-0 cell readers go (spec §4)

**Files:**
- Modify: the 13 `is_zero_field_class(` sites (`grep -rn "is_zero_field_class(" clausal --include='*.py'`):
  each atom-treatment arm is deleted (a class is never an atom); `_helpers._standard_order_key` (the
  `is_zero_field_class` band and the `len(term) == 1` cell band deleted; a str keys `(_ORD_ATOM, term)`),
  `chars.py::_atom_to_str`, `type_checks.py`, `inspection.py` (`functor/3`, `=..`: `type(f_val) is str: f_val = mint(f_val)` is now identity)
- Modify: every literal `("x",)` cell in engine code (the ~80 sites of the census: `grep -rnoE '\(\s*"[^"]{1,40}"\s*,\s*\)' clausal --include='*.py'`) → `"x"`; the seven Python 1-tuple shape tests (`terms.py` ×3, `predicate.py`, `testing.py`, `tools/iso_l3.py`, `head_match.py`) → `type(x) is str`
- Modify: `clausal/terms.py::term_str`/`term_canonical` (a str prints as an ATOM — quoted by the atom rules under `quoted=True`; the carrier prints as the string), `clausal/logic/builtins/io.py` writers likewise
- Test: `tests/test_atoms_as_str_stage2.py`, `tests/test_writers_atoms_strings.py`, `tests/iso/test_standard_order.py`

- [ ] **Step 1: Failing tests**

```python
def test_write_and_order(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, "p(S) <- term_to_string('a b', S)\nq(S) <- write_to_string(\"ab\", S)\n"
                         "r(L) <- msort([\"b\", b, [a], a, 1], L)\n")
    assert _first(mod, "p", Var()) == [chars("'a b'")] and _first(mod, "q", Var()) == [chars("[a,b]")]
    assert _first(mod, "r", Var()) == [[1, "a", "b", ["a"], chars("b")]]      # number < atoms < compounds; "b" == [b]
```

- [ ] **Step 2–5:** run (fail), implement, run the task's tests + `tests/test_writers_atoms_strings.py` + `tests/iso` + neighbours, commit
  (`atoms-as-str stage 2, task 6: the arity-0 cell readers, the literal cells and the zero-field-class-as-atom legacy are deleted`).

---

### Task 7: The exporter flips with the engine (spec Q5)

**Files:**
- Modify: `clausal/tools/clausal_to_prolog.py` (the atom/string/chars branch lines — census §7a D: 37 lines; an
  engine str is an ATOM, the carrier is the string; the 1 literal cell)
- Test: `tests/test_clausal_to_prolog*.py` goldens (`tests/fixtures/prolog_golden/*.pl`) — the emitted Prolog must NOT change

- [ ] **Step 1:** run the exporter goldens on the branch as it stands; record which fail and why (each must be an engine-str-read-as-string).
- [ ] **Step 2:** fix each branch line; **Step 3:** goldens green with NO golden regenerated (a changed `.pl` means a wrong fix); **Step 4:** commit
  (`atoms-as-str stage 2, task 7: the exporter reads a str as the atom; goldens unchanged`).

---

### Task 8: The test rewrite — `("x",)` → `"x"` by JUDGMENT, and the str-means-string tests

**Files:**
- Modify: the 97 test files holding 693 literal 1-tuples (`grep -rlE '\(\s*"[^"]{1,40}"\s*,\s*\)' tests --include='*.py'`),
  plus every test that asserts a str means a string (`unify("ab", [a, b])`, `is_list("ab")`, `length("ab", 2)` written from Python)
- Brief for the agents: `docs/superpowers/plans/STAGE2-PIN-BRIEF.md` (write it from the three edits below)

Rules (the whole content of the brief): (1) a literal `("x",)` that is an ATOM becomes `"x"`; a 1-tuple that is
a Python tuple of NAMES (`answer_names=("STATUS",)`, `fields=("term",)`, `pytest.param((...),)`) stays — read the
call; (2) a Python-side bare str that a test used as TEXT becomes `chars("...")` (most were already converted in
stage 1; the ones that slipped through the interim rule are atom-vs-string comparisons); (3) an expectation
`== ("x",)` becomes `== "x"`; never loosen, delete or skip; a row that is not one of these three is reported,
not fixed. Six parallel agents over `git grep -l` groups balanced by count; each file verified green.

- [ ] **Step 1:** write the brief; **Step 2:** dispatch; **Step 3:** run every touched file; **Step 4:** commit tests only
  (`atoms-as-str stage 2, task 8: the test rewrite -- an atom literal is the str`).

---

### Task 9: The gate and the handoff

- [ ] **Step 1:** clean-base A/B per Global Constraints (base = stage 1 tip `1c24bd65`); extract BOTH failure-name sets
  (assert non-empty) and BOTH skip sets; NEW 0 / GONE 0 required; classify anything else and go back to the task it belongs to.
- [ ] **Step 2:** `tests/test_comparison_twin_parity.py`, exporter goldens, `tests/rewrite`, `tests/iso` green.
- [ ] **Step 3:** harness RE-BASELINE request to harness-batch-lane (announcement file beside
  `CHARS-CARRIER-STAGE1-FROZEN-2026-09-18.md`): every row moves by construction; the kit's escape hatch keeps its carrier.
- [ ] **Step 4:** handoff `implementation_plans/SESSION-HANDOFF-<date>-engine-lane-stage2.md`; memory note updated; commit.
