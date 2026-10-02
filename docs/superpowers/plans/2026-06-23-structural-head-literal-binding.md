# Structural Head-Literal Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a `Compound` / imported-`Call` / functor-instance literal in a **ruled** clause head bind into an unbound caller `Var` (output mode), the way a bare fact already does.

**Architecture:** Extend the fact-style `Var + Unify` head normalization (already in `clausal/logic/database.py`) to ruled clauses, restricted to *structural* top-level head args. At assert time, each structural head arg is replaced by a fresh `Var` and a `Unify(Var, term)` goal is **prepended** to the body. `Unify` is bidirectional, so input mode destructures and output mode constructs/binds. First-arg indexing is unaffected because `arg_index` already recovers index keys from `Unify` body goals. Atomic head literals keep the existing match-guard path.

**Tech Stack:** Python 3.13, the clausal compiler/runtime, `pytest` (run via the `pytest` shim, NOT `python -m pytest`).

## Global Constraints

- Run tests with the `pytest` shim (the `venv` lacks the `pytest` module); the C extension is importable from the shim's interpreter.
- Full `pytest tests/` OOMs this box (3.9 GB) — always run **file-by-file or small batches**.
- Clear stale `.clausal` bytecode caches before re-running after a compiler/normalization change: `find . -path ./build -prune -o -name "__pycache__" -type d -print | grep -E "tests|fixtures|clausal_modules" | xargs rm -rf`.
- Clausal code style is not relevant here — all edits are Python.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Scope: binding fix only. Do NOT attempt to auto-mint undeclared constructors.

---

### Task 1: Normalization helpers

**Files:**
- Modify: `clausal/logic/database.py` (add two module-level helpers next to `_normalize_dataclass_fact`, ~line 362)
- Test: `tests/test_structural_head_normalization.py` (create)

**Interfaces:**
- Produces:
  - `_is_structural_head_value(val: Any) -> bool` — True for `Compound`, `Call` with `func=LoadName`, or a non-`Compound`/`Call`/`KWTerm` functor-instance; False for atomics, `Var`, `StarUnpack`, `list`, `KWTerm`.
  - `_normalize_structural_head_args(head: Any, body: list) -> tuple[Any, list]` — returns `(new_head, new_body)`; structural top-level head fields are replaced by fresh `Var`s with `Unify(var, value)` goals prepended to `body`. No-op (returns inputs) when `head` is not a user functor-instance or has no structural fields.

- [ ] **Step 1: Write the failing test**

Create `tests/test_structural_head_normalization.py`:

```python
"""Unit tests for structural head-arg normalization (clausal.logic.database)."""

from clausal.logic.database import (
    _is_structural_head_value,
    _normalize_structural_head_args,
)
from clausal.terms import Call, Compound, LoadName, Unify
from clausal.logic.variables import Var, is_var
from clausal.logic.predicate import make_predicate


class TestIsStructuralHeadValue:
    def test_compound_is_structural(self):
        # Compound signature is Compound(functor, args) — args is one sequence.
        assert _is_structural_head_value(Compound("point", [1, 2])) is True

    def test_loadname_call_is_structural(self):
        assert _is_structural_head_value(
            Call(func=LoadName(name="point"), args=[1, 2], kwargs=[])
        ) is True

    def test_atomics_are_not_structural(self):
        for v in (1, 1.5, True, False, None, "s", b"b", 3 + 2j):
            assert _is_structural_head_value(v) is False

    def test_var_and_list_not_structural(self):
        assert _is_structural_head_value(Var()) is False
        assert _is_structural_head_value([1, 2]) is False

    def test_non_loadname_call_not_structural(self):
        # A Call whose func is not a LoadName is not a data term to construct.
        assert _is_structural_head_value(
            Call(func=Var(), args=[], kwargs=[])
        ) is False


class TestNormalizeStructuralHeadArgs:
    def test_structural_field_hoisted_to_prepended_unify(self):
        pt = make_predicate("pt", ("a", "b"))
        compound = Call(func=LoadName(name="point"), args=[1, 2], kwargs=[])
        head = pt(a=Var(), b=compound)
        new_head, new_body = _normalize_structural_head_args(head, [True])
        # field b replaced by a Var
        assert is_var(new_head.b)
        # one Unify prepended, binding that Var to the original compound
        assert isinstance(new_body[0], Unify)
        assert new_body[0].left is new_head.b
        assert new_body[0].right is compound
        assert new_body[1] is True  # original body preserved after prepend

    def test_atomic_fields_left_alone(self):
        pt = make_predicate("pt", ("a", "b"))
        head = pt(a=Var(), b=20000)
        new_head, new_body = _normalize_structural_head_args(head, [True])
        assert new_head.b == 20000      # untouched
        assert new_body == [True]       # no goals added

    def test_no_structural_fields_is_noop(self):
        pt = make_predicate("pt", ("a",))
        head = pt(a=Var())
        h2, b2 = _normalize_structural_head_args(head, [True])
        assert h2 is head and b2 == [True]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_structural_head_normalization.py -q`
Expected: FAIL with `ImportError: cannot import name '_is_structural_head_value'`.

- [ ] **Step 3: Write minimal implementation**

In `clausal/logic/database.py`, after `_normalize_dataclass_fact` (around line 362), add:

```python
def _is_structural_head_value(val: Any) -> bool:
    """True if val is a structural term that head_to_match_pattern would compile
    to a value-rejecting MatchClass (Compound / Call(LoadName) / functor
    instance). Such head args must be hoisted into a Var + Unify body goal so an
    unbound caller binds in output mode. Atomics, Vars, StarUnpack and lists are
    handled by other compiler paths and must NOT be normalized here."""
    from clausal.logic.variables import is_var
    if is_var(val) or isinstance(val, (StarUnpack, list, KWTerm)):
        return False
    if isinstance(val, Compound):
        return True
    if isinstance(val, Call):
        return isinstance(val.func, LoadName)
    if is_term_instance(val):
        return True
    return False


def _normalize_structural_head_args(head: Any, body: list) -> tuple[Any, list]:
    """Hoist structural top-level head args into prepended Unify body goals.

    Mirrors _normalize_dataclass_fact but for structural args only (atomics keep
    the match-guard path). Each structural field is replaced by a fresh Var and a
    Unify(var, value) goal is prepended to body (prepended so destructured inner
    vars are bound before the original body runs). No-op for non-functor-instance
    heads (bare Compound/Call/KWTerm) or heads with no structural fields."""
    from clausal.logic.variables import Var
    from clausal.terms import Unify
    if not is_term_instance(head) or isinstance(head, (Compound, Call, KWTerm)):
        return head, body
    fields = term_field_names(head)
    replacements: dict[str, Any] = {}
    prepend: list = []
    for name in fields:
        val = getattr(head, name)
        if _is_structural_head_value(val):
            v = Var()
            replacements[name] = v
            prepend.append(Unify(left=v, right=val))
    if not replacements:
        return head, body
    new_kwargs = {
        name: replacements.get(name, getattr(head, name)) for name in fields
    }
    new_head = type(head)(**new_kwargs)
    return new_head, prepend + list(body)
```

Confirm `Unify` is importable from `clausal.terms` (it is — `_normalize_dataclass_fact` imports it the same way).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_structural_head_normalization.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/database.py tests/test_structural_head_normalization.py
git commit -m "feat(database): structural head-arg normalization helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Wire normalization into ruled-clause assertion + output-mode binding

**Files:**
- Modify: `clausal/logic/database.py` — `LogicModule.define_predicate` (lines ~271-280)
- Test: `tests/test_head_match_imported_compound.py` (add output-mode tests; existing fixtures `head_compound_owner.seam` / `head_compound_importer.seam` are reused — no new fixture)

**Interfaces:**
- Consumes: `_normalize_structural_head_args` from Task 1.
- Produces: ruled clauses with structural head args are stored in `Var + Unify` form; an unbound `Var` caller in that position binds to the constructed term.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_head_match_imported_compound.py`:

```python
def _bind_first(mod, pred, second):
    """Output mode: query pred(X, second) with X unbound; return derefs of X."""
    logic_mod = mod.__dict__["$module"]
    X = Var()
    found = []
    for _ in call(pred, X, second, module=logic_mod):
        found.append(deref(X))
    return found


def test_rule_structural_head_binds_unbound_caller():
    """Check(Wrap(SUB), RESULT) <- RESULT is "matched":
    Check(X, "matched") with X unbound must bind X = Wrap(_)."""
    mod = _load_importer()
    got = _bind_first(mod, "Check", "matched")
    assert len(got) == 1
    assert type(got[0]).__name__ == "Wrap"


def test_rule_matches_fact_in_output_mode():
    """Rule (Check) and fact (CheckFact) must agree in output mode."""
    mod = _load_importer()
    rule_got = _bind_first(mod, "Check", "matched")
    fact_got = _bind_first(mod, "CheckFact", "matched")
    assert len(rule_got) == len(fact_got) == 1
    assert type(rule_got[0]).__name__ == type(fact_got[0]).__name__ == "Wrap"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
find . -path ./build -prune -o -name "__pycache__" -type d -print | grep -E "tests|fixtures" | xargs rm -rf
pytest tests/test_head_match_imported_compound.py -q -k "output_mode or unbound_caller"
```
Expected: FAIL — `test_rule_structural_head_binds_unbound_caller` returns `[]` (rule not normalized); the fact half of the parity test passes.

- [ ] **Step 3: Write minimal implementation**

In `clausal/logic/database.py`, `define_predicate`, change the normalization block:

```python
        head = predicate_node.head
        body_goals = _flatten_body(predicate_node.body)
        # Normalize dataclass facts: ground field values → Var + Unify body goals.
        if body_goals == [True] and _is_normalizable_fact(head):
            head, body_goals = _normalize_dataclass_fact(head)
        else:
            # Ruled clause: hoist structural head args (Compound / Call(LoadName)
            # / functor-instance) into prepended Unify goals so an unbound caller
            # binds in output mode — the same Var+Unify shape facts use. Atomic
            # head literals keep the match-guard path.
            head, body_goals = _normalize_structural_head_args(head, body_goals)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
find . -path ./build -prune -o -name "__pycache__" -type d -print | grep -E "tests|fixtures" | xargs rm -rf
pytest tests/test_head_match_imported_compound.py -q
```
Expected: PASS — the two new tests pass AND all pre-existing input-mode / indexing tests in the file still pass.

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/database.py tests/test_head_match_imported_compound.py
git commit -m "fix(database): bind structural head literals for Var callers (output mode)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Nested-compound + indexing regression coverage

**Files:**
- Test: `tests/test_head_match_imported_compound.py` (add nested + indexing output-mode tests)

**Interfaces:**
- Consumes: behavior from Task 2.

- [ ] **Step 1: Write the failing-then-passing test**

(With Task 2 implemented this should pass; it pins nested output-mode behavior so a future change can't regress it. Input-mode indexing is already covered by the existing `test_indexer_routes_wrap_keyed_clauses` / `test_indexer_handles_nested_item_keys` in this file — do NOT duplicate them; the full-file runs in Task 2 Step 4 and Task 5 re-verify them.) Append:

```python
def test_nested_compound_head_binds_unbound_caller():
    """CheckNested(Item(REQ_ID, Met(SUB), _), RESULT) <- RESULT is REQ_ID:
    output mode constructs the nested term and binds the caller Var."""
    mod = _load_importer()
    logic_mod = mod.__dict__["$module"]
    X = Var()
    found = []
    for _ in call("CheckNested", X, Var(), module=logic_mod):
        found.append(deref(X))
    assert len(found) == 1
    assert type(found[0]).__name__ == "Item"
```

- [ ] **Step 2: Run tests (new test + full-file regression incl. existing indexing tests)**

```bash
find . -path ./build -prune -o -name "__pycache__" -type d -print | grep -E "tests|fixtures" | xargs rm -rf
pytest tests/test_head_match_imported_compound.py -q
```
Expected: PASS — the new nested test passes AND every pre-existing input-mode/indexing test still passes (re-confirms normalization didn't regress first-arg indexing).

- [ ] **Step 3: Commit**

```bash
git add tests/test_head_match_imported_compound.py
git commit -m "test(database): nested + indexed output-mode coverage for structural heads

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Undeclared-functor consistency (rule raises like fact)

**Files:**
- Test: `tests/test_structural_head_normalization.py` (add an integration test)
- Create: `tests/clausal_modules/undeclared_compound_head.seam`

**Interfaces:**
- Consumes: behavior from Task 2. Pins the intended behavior change: an undeclared bare functor in output mode raises the helpful "not in scope as a term class" error, identically for rule and fact.

- [ ] **Step 1: Write the test + fixture**

Create `tests/clausal_modules/undeclared_compound_head.seam`:

```
# `point` is never declared/imported — constructing it must raise the helpful
# "not in scope as a term class" error in output mode, for BOTH rule and fact.
ur(N, point(1, 2)) <- (N >= 0)
uf(50, point(1, 2)),
```

Append to `tests/test_structural_head_normalization.py`:

```python
import os
import pytest
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var


def _undeclared_mod():
    path = os.path.join(
        os.path.dirname(__file__), "clausal_modules", "undeclared_compound_head.seam"
    )
    return _load_module("undeclared_compound_head_mod", path).__dict__["$module"]


def _err_text(pred, *args, module):
    with pytest.raises(Exception) as exc:
        list(call(pred, *args, module=module))
    return str(exc.value)


def test_undeclared_rule_and_fact_raise_same_error_in_output_mode():
    mod = _undeclared_mod()
    rule_err = _err_text("ur", 5, Var(), module=mod)
    fact_err = _err_text("uf", 50, Var(), module=mod)
    assert "not in scope as a term class" in rule_err
    assert "not in scope as a term class" in fact_err
```

- [ ] **Step 2: Run the test**

```bash
find . -path ./build -prune -o -name "__pycache__" -type d -print | grep -E "tests|clausal_modules" | xargs rm -rf
pytest tests/test_structural_head_normalization.py -q -k "undeclared"
```
Expected: PASS. If the fact path does NOT raise the same way (e.g. it raises a different error or none), STOP and report — the spec's consistency claim needs revisiting before asserting it. Do not weaken the test to force a pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_structural_head_normalization.py tests/clausal_modules/undeclared_compound_head.seam
git commit -m "test(database): undeclared-functor output mode raises consistently (rule == fact)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Remove WARNING comments, close audit, regression sweep

**Files:**
- Modify: `clausal/logic/compiler/head_match.py` (remove the 3 `WARNING (== / structural-match-vs-unification bug class)` comment blocks at the Compound / imported-`Call` / functor-instance branches)
- Modify: `todo/equality-vs-unification-audit.md` (mark #8-#10 FIXED; update the table + Follow-up)
- Modify: `docs/superpowers/specs/2026-06-23-structural-head-literal-binding-design.md` (Status → Implemented)
- Modify: `todo/compound-head-literal-output-mode.md` (mark resolved, pointing at this work; note undeclared-constructor part remains)

- [ ] **Step 1: Remove the WARNING comment blocks**

In `clausal/logic/compiler/head_match.py`, delete the three comment paragraphs that begin `# WARNING (== / structural-match-vs-unification bug class)` (at the `isinstance(term, Compound)` branch, the `isinstance(term, Call) and isinstance(term.func, LoadName)` branch, and the `is_term_instance(term)` branch). Leave the surrounding code and the non-WARNING comments intact. The MatchClass code stays — it is still the correct input-mode pattern; the bug is now prevented upstream by normalization, so the warnings are obsolete. Add a one-line note at each site instead:

```python
    # Structural head args are hoisted to Var + Unify at assert time
    # (_normalize_structural_head_args), so this MatchClass only ever sees a
    # ground (input-mode) caller; output-mode binding is handled by the Unify.
```

- [ ] **Step 2: Update the audit + spec + todo docs**

In `todo/equality-vs-unification-audit.md`: change rows #8/#9/#10 status from "KNOWN GAP" to "FIXED — structural head normalization (this plan)"; update the "Known gap — structural head literals" section to a "Fixed" note that points to `docs/superpowers/plans/2026-06-23-structural-head-literal-binding.md`, and keep the undeclared-constructor caveat. Update the Follow-up bullet accordingly.

In `docs/superpowers/specs/2026-06-23-structural-head-literal-binding-design.md`: set `**Status:**` to `Implemented 2026-06-23` (fill the commit range after the final commit).

In `todo/compound-head-literal-output-mode.md`: add a top note `RESOLVED 2026-06-23 (binding fix)` explaining declared/imported constructors now bind in output mode; the undeclared-bare-functor construction remains the separate data-constructor design.

- [ ] **Step 3: Regression sweep (file-by-file / small batches)**

```bash
find . -path ./build -prune -o -name "__pycache__" -type d -print | grep -E "tests|fixtures|clausal_modules" | xargs rm -rf
pytest tests/test_structural_head_normalization.py tests/test_head_match_imported_compound.py tests/test_numeric_head_literal.py tests/test_compiler.py tests/test_first_arg_index.py tests/test_groundness_dispatch.py -q
pytest tests/test_compiled_programs.py tests/test_string_head_patterns.py tests/test_bytes_head_dispatch.py tests/test_dict_set_compiler.py tests/test_search.py tests/test_builtins.py tests/test_import.py tests/test_directives.py -q
pytest tests/test_dcg.py tests/test_tabling.py tests/test_clpfd.py tests/test_reified_ite.py tests/test_meta.py tests/test_module_imports.py -q
```
Expected: all PASS. If any fail, STOP and debug with `superpowers:systematic-debugging` before proceeding — do not paper over.

- [ ] **Step 4: Commit**

```bash
git add clausal/logic/compiler/head_match.py todo/equality-vs-unification-audit.md docs/superpowers/specs/2026-06-23-structural-head-literal-binding-design.md todo/compound-head-literal-output-mode.md
git commit -m "docs/cleanup: close structural head-literal binding (#8-#10)

Remove obsolete WARNING comments now that normalization prevents the bug
upstream; mark audit findings #8-#10 and the spec/todo as resolved.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes / known-separate paths (do NOT expand scope)

- **Runtime `assertz`/`asserta`** (`clausal/logic/builtins/database_ops.py`) build clauses and call `db.assertz` directly, bypassing `define_predicate` normalization. Runtime-asserted structural-head clauses therefore still take the old path. This matches today's behavior (runtime facts also aren't normalized) and is out of scope for this plan. If a future need arises, route `_clause_from_term` through `_normalize_structural_head_args` — but that needs its own tests and is not part of this fix.
- **Atomic head literals** remain on the match-guard path by design (already fixed in commits `71d7062f` / `c8807d36`).
