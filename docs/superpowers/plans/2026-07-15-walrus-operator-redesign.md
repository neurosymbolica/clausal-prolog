# Walrus Operator Redesign Implementation Plan (revised)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the `:=` spelling of eager arithmetic, replace it with a reserved `eval_(EXPR, RESULT)` builtin (same backend), migrate every in-repo use per cluster, and document `is`-chains as the inline-naming idiom.

**Architecture:** `eval_/2` is recognized in goal position (reserved-functor pattern, `terms_to_goalop.py:294+`) and compiles to the existing `Evaluate` node → `ArithEval` IR — the `:=` backend survives, only the surface syntax changes. `:=` currently warns (Phase 1) and later becomes a `SyntaxError` with a migration hint (Phase 2). `Evaluate`/`ArithEval` are NOT pruned.

**Tech Stack:** Python 3.13, Clausal templating/pythonic_ast/compiler, pytest.

## Global Constraints

- Test command: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest ...` (referred to as `PYTEST`). Baseline: 9307 passed, 2 skipped, 44 xfailed.
- No `git commit` without explicit user approval.
- Idiom rule: `==` relational constraint; `eval_/2` eager Python-semantics arithmetic; `is` unification (chains for naming); `++()` arbitrary Python.
- Python-level `X := Var()` walrus in `.py` files is legitimate Python — never migrate it.
- `Evaluate` node and `ArithEval` IR are kept permanently (backend of `eval_/2`).

---

## Completed (Phase 1, first half — all green)

- [x] **Task 0:** test command + baseline (9307 passed).
- [x] **Task 1:** `DeprecationWarning` in `visit_NamedExpr` (`term_rewriting.py`; helper `_warn_walrus_deprecated`); test `test_walrus_emits_deprecation_warning`.
- [x] **Task 2:** `tests/clausal_modules/*.clausal` → `==` (20 sites).
- [x] **Task 3:** `iso_arithmetic.seam` → `==` + regenerated fwd/reverse goldens.
- [x] **Task 4a:** non-units fixtures → `==` (fibonacci, tabled_fib, clpfd_queens, ortools_cpsat, edcg_counter, meta_test); `builtins_call` lambda-naming → `is`; TRO fixtures (`deep_index`, `tro_predicates`) + `catch_test` → interim `is ++(...)` (re-migrated to `eval_/2` in Task 7); goldens for fibonacci/clpfd_queens/meta_test regenerated.

---

### Task 5: Implement `eval_/2`

**Files:**
- Modify: `clausal/logic/compiler/terms_to_goalop.py` (reserved-functor cases, near line 294)
- Test: `tests/test_compiler_goals.py` or sibling of the existing reserved-builtin tests (match where `throw`/`once` goal-position tests live), plus a `.clausal`-source behavioral test.

**Interfaces:**
- Produces: goal `eval_(EXPR, RESULT)` ≡ old `RESULT := EXPR` (ArithEval). Wrong arity → clear compile-time error consistent with sibling reserved builtins.

- [ ] **Step 1: Failing behavioral test** (module-load style, as in `test_units.py::TestNumericSugar`):

```python
def test_eval_builtin_binds(tmp_path):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    src = "Test <- (eval_(6 * 7, X), X == 42)\n"
    p = tmp_path / "eval_basic.clausal"; p.write_text(src)
    mod = _load_module("eval_basic", str(p)).__dict__["$module"]
    assert any(True for _ in call("Test", module=mod))

def test_eval_bound_target_checks(tmp_path):
    # bound-equal succeeds, bound-unequal fails (ArithEval semantics)
    ...  # same harness: "Test <- eval_(1 + 2, 3)" passes; "Test <- eval_(1 + 2, 4)" yields no solution

def test_eval_python_semantics_zero_div(tmp_path):
    # eval raises catchable ZeroDivisionError inside catch/3 (eager Python semantics)
    src = 'Test(R) <- catch(eval_(1 // 0, R), _, R is "caught")\n'
    ...
```

- [ ] **Step 2: Run — expect FAIL** (`eval_/2` unresolved → NameError-style predicate error).

- [ ] **Step 3: Implement** in `terms_to_goalop.py` beside the other reserved functors:

```python
case nodes.Call(func=nodes.LoadName(name="eval_"), args=[expr, target]):
    # eval_(EXPR, RESULT) — eager arithmetic evaluate-and-bind (Prolog is/2).
    # Same backend as the deprecated ':=' (Evaluate → ArithEval).
    return ArithEval(target=target, expr=expr)
```

Match the exact destructuring/guard style of the sibling cases (some use keyword field names or arity checks — copy the local idiom). Verify the args arrive as arith-ready nodes (they pass through the same TermTransformer visits as `Evaluate.right` did).

- [ ] **Step 4: Run — expect PASS.** Also run `PYTEST tests/test_compiler_trampoline.py tests/test_tail_recursion.py -q` (no regressions; `Evaluate`-node tests still green).

- [ ] **Step 5: Update the deprecation warning** (`_warn_walrus_deprecated`) to lead with `eval_/2`:
  "Use `eval_(EXPR, X)` for eager arithmetic (old `:=` semantics), `==` for relational constraints, `is` for unification, `is ++(...)` for arbitrary Python." Update `test_walrus_emits_deprecation_warning` to assert `"eval"` in the message.

### Task 6: Prolog bridge `eval_/2` ↔ `is/2`

**Files:**
- Modify: `clausal/tools/clausal_to_prolog.py` (near `_convert_named_expr:1008`), `clausal/tools/prolog_to_clausal.py` (`_INFIX_MAP:96` + its consumer)
- Test: `tests/test_prolog_emit.py`, `tests/test_prolog_golden.py`
- Regenerate: every `tests/fixtures/prolog_golden/*.clausal` reverse golden containing `:=`

- [ ] **Step 1: Failing tests** — clausal `eval_(N - 1, N1)` exports as `N1 is N - 1`; Prolog `N1 is N - 1` imports as `eval_(N - 1, N1)` (match assertion style of existing emit/import tests).
- [ ] **Step 2: Export**: in `clausal_to_prolog`, handle goal-position `Call` named `eval` with 2 args → `PCompound("is", (target, expr))`. Keep `_convert_named_expr` (still needed while `:=` parses; removed in Phase 2).
- [ ] **Step 3: Import**: in `prolog_to_clausal`, remove `"is": ":="` from `_INFIX_MAP`; special-case `is/2` in the term renderer to emit the call form `eval_(EXPR, RESULT)`.
- [ ] **Step 4: Regenerate reverse goldens** (`python -m clausal.tools.prolog_to_clausal <pl> -o <clausal>`) for every `prolog_golden/*.clausal` currently containing `:=`; eyeball the diffs (only `:=` lines should change, to `eval_(...)`).
- [ ] **Step 5: Run** `PYTEST tests/test_prolog_golden.py tests/test_prolog_emit.py tests/test_prolog_import.py tests/test_prolog_roundtrip.py -q` — PASS. The import path no longer generates deprecated syntax (deprecation warnings from golden-import tests disappear).

### Task 7: Re-migrate interim `is ++(...)` sites → `eval_/2`

**Files:** `tests/fixtures/deep_index.seam` (4), `tests/fixtures/tro_predicates.seam` (6), `tests/fixtures/catch_test.seam` (1)

- [ ] **Step 1:** `N1 is ++(N - 1)` → `eval_(N - 1, N1)` etc.; `RESULT is ++(X // Y)` → `eval_(X // Y, RESULT)`. Update the tro_predicates comment ("prefix is deterministic (eval_/2)").
- [ ] **Step 2:** `PYTEST tests/test_tail_recursion.py tests/test_deep_indexing.py tests/test_exceptions.py -q` — PASS, including both TRO allocation tests (1 SG each).

### Task 8: Units fixtures → `eval_/2`

**Files:** `tests/fixtures/units_basic.seam` (73), `units_clpfd.seam` (30), `units_information.seam` (22)

- [ ] **Step 1:** Mechanical rewrite `VAR := EXPR` → `eval_(EXPR, VAR)` (script the line-wise transform; sites are single-line `X := E,`/`X := E` forms — verify with grep first; `n(Unit)` sugar and `++(...)` RHS stay verbatim inside `eval`'s first arg... EXCEPT sites already of the form `X := ++(...)` which are pure Python evaluation → prefer `X is ++(...)`).
- [ ] **Step 2:** `PYTEST tests/test_units.py -q` — PASS (baseline count).
- [ ] **Step 3:** `grep -rn ':=' tests/fixtures/units_*.clausal` → empty.

### Task 9: Examples, module docstrings, embedded clausal in `tests/*.py`

**Files:** `clausal/examples/nqueens.seam`, `clausal/examples/lambdas.seam`; docstrings in `clausal/modules/units.py`, `imperial.py`, `prolog.py`, `clausal/logic/specialization.py` (audit each `grep -rlP '(?<![=<>!:]):=' clausal/` hit — skip genuine Python walrus like `solve.py`'s `X := Var()` doc examples... verify each); clausal-source string literals in `tests/*.py` and `tests/audit_2026_07_05/*.py` (edcg `{_out := _in + _x}` → `==`; arith → `==`; units/eager → `eval`).

- [ ] **Step 1:** Migrate per idiom rule; `nqueens.seam` `QS := [2, 4, 1, 3]` is list-binding → `is`; lambdas example bodies → `==`.
- [ ] **Step 2:** Run the touched suites (`test_edcg.py`, `test_dcg.py`, `test_lambdas.py`, `test_units.py`, `test_bytes_list_builtins.py`, `test_source_locations.py`, audit suites, examples loader if one exists) — PASS.
- [ ] **Step 3:** Sweep: `grep -rP '(?<![=<>!:]):=' clausal/ tests/ --include='*.clausal' --include='*.py'` → only Python-walrus and Phase-2-marked sites remain.

### Task 10: Docs

**Files:** `docs/arithmetic.md`, `docs/syntax.md`, and the other `docs/*.md` from `grep -rlP '(?<![=<>!:]):=' docs/*.md` (leave `docs/superpowers/` historical records).

- [ ] **Step 1:** Add `eval_/2` to `docs/arithmetic.md` (eager Python-semantics arithmetic; when to prefer it over `==`: units, catchable exceptions, accumulator recursion). Add an `is`-chain naming section (`VALUE is compound(a, X) is C[key]`) to `docs/syntax.md`/`docs/arithmetic.md`.
- [ ] **Step 2:** Replace `:=` examples per idiom rule; note the deprecation → removal.
- [ ] **Step 3:** `grep -rlP '(?<![=<>!:]):=' docs/*.md` → clean.

### Task 11: Phase 1 green + CHECKPOINT

- [ ] **Step 1:** Full suite `PYTEST tests/ -q` — ≥ baseline, no new failures.
- [ ] **Step 2:** `PYTEST tests/ -W error::DeprecationWarning -q` — remaining `:=`-warnings only from intentional deprecated-path tests (`test_walrus_is_arithmetic`, walrus-parse tests in `test_simple_ast.py`); everything else clean. (Python `query()` deprecations are pre-existing.)
- [ ] **Step 3:** STOP — present full diff for review + commit approval.

---

## Phase 2 — Remove `:=` (post-checkpoint; `Evaluate`/`ArithEval` stay)

### Task 12: `:=` → SyntaxError + hint

- [ ] `visit_NamedExpr` raises `SyntaxError` ("`:=` was removed. Use `eval_(EXPR, X)` for eager arithmetic (old behavior), `==` for constraints, `is` for unification."). Same in `EmbedTransformer.visit_NamedExpr` (line ~3813) if it can receive clause-context walruses — verify.
- [ ] Remove `_convert_named_expr` from `clausal_to_prolog.py`.
- [ ] Rewrite deprecated-path tests: `test_walrus_is_arithmetic` → asserts `SyntaxError`; `test_walrus_emits_deprecation_warning` → replaced by the SyntaxError test; walrus-parse tests in `test_simple_ast.py` → SyntaxError or deleted; keep all direct `Evaluate(...)`-node tests (live backend).
- [ ] Full suite + `grep -rP '(?<![=<>!:]):='` sweep → only Python walrus remains.
- [ ] Close `todo/fix_walrus_operator.md`.

## Self-review notes

- Old "prune Evaluate/ArithEval" phase cancelled by design (backend of `eval_/2`).
- Old "walrus inline naming" phase cancelled: `is`-chains already work (probes: plain, dict-accessor, three-way, negative — all pass); documented in Task 10 instead.
- Python-side `Evaluate(...)` node constructions in tests are NOT migrated — the node is permanent API now.
