# Assertion diagnostic: descend one level into the failing predicate

**Date:** 2026-07-30
**Source todo:** `todo/B-assertion-diagnostic-stops-one-level-above-the-cause.md`
**Component:** `clausal/testing.py`, `_report_nearest` (stage 3 of the failure diagnostic)

## Problem

`_report_nearest` has three rungs. Rung 1 (one-argument generalisation) carries a value
and readers act on it. Rungs 2 and 3 do not:

* **Rung 2** — the all-holes probe proves the predicate satisfiable, then prints
  *"the predicate has solutions, but none within one argument of this goal"* and shows
  **no solution at all**, even though `_has_solution` has one in hand.
* **Rung 3** — the all-holes probe is unsatisfiable, and the message is
  *"the predicate has no solution for ANY arguments at this point"* with zero
  localisation into the predicate's own clause bodies. It is a better-worded
  *"test X failed"*.

Measured over study 13's goal-level failures, recovery tracks whether the message carried
a value. Every attempt whose report contained *"no solution for ANY arguments"* failed to
recover (0/29 in the reviewer's slice; the proportion, not the exact count, is the
load-bearing claim).

## Verified reproductions

Both prototyped against the archived scratch trees, and both land on the cause the todo
predicts:

| case | goal reported today | where the descent lands |
|---|---|---|
| vat | `pro_rata_deduction_decision_resolvable(PROFILE)` | `computation.clausal:77`, `RAW_PCT > 100` with `RAW_PCT = 50` — the contradictory guard, two levels down |
| schengen | `days_used([], [2024,1,1], 0)` | `computation.clausal:58`, `window_days_used(HISTORY, REFERENCE_DATE_OBJ, WINDOW_SIZE, DAYS_USED)` with `REFERENCE_DATE_OBJ = date(2024,1,1)` — the wrong-type argument, one level down |

## Output shape

Flat leaves: one entry per clause route, showing only the deepest failing conjunct
reached plus its bindings. Compact enough to survive a token-budget squeeze.

```
goal 2 of 4 failed:
  eu.vat.pro_rata_deduction.pro_rata_deduction_decision_resolvable(PROFILE)
bindings at failure: PROFILE = {taxable_turnover_cents: 5000, ...}
the predicate has no solution for ANY arguments at this point; no clause body survives:
  computation.clausal:38  TOTAL_CENTS <= 0
    TOTAL_CENTS = 10000
  computation.clausal:77  RAW_PCT > 100
    RAW_PCT = 50
```

## Design

### 1. Shared walk (refactor, no behaviour change)

The cumulative-prefix loop in `_diagnose_into` step 1 — re-run prefixes until one yields
no solution — is extracted as:

```python
_first_failing(goals, logic_module, deadline, prefix=()) -> tuple[int | None, str | None]
```

returning the 1-based index of the first unsatisfiable conjunct and, if it raised instead,
the rendered exception. The top-level walk and the descent both call it. The top-level
report is unchanged.

### 2. Stage 4: descent (`_report_descent`)

Runs **only** on the rung-3 branch — after the all-holes probe has proved the predicate
unsatisfiable. For each clause of the failing predicate:

**Resolve the predicate.** `goal.func` carries a `LoadName`. Look it up as
`module_dict[name]`, then `module_dict[name.rsplit(".", 1)[-1]]`, then
`getattr(sys.modules[prefix], last)`. Accept only a `PredicateMeta`. Anything else — a
builtin, a Python function, a predicate with zero clauses — produces no descent and the
existing rung-3 sentence stands unchanged.

**Switch to the defining module.** A clause body's goal names resolve in the module that
*defined* the clause, not the caller's. `sys.modules[cls.__module__]["$module"]` gives it.
Verified: without this, depth-2 descent cannot resolve
`eu.vat.pro_rata_deduction.computation.decide_pro_rata_deduction` from the test file's
module dict.

**Match the head.** Prepend `Unify(left=head_arg_i, right=goal_arg_i)` goals, taking head
args from `head.args` or `term_field_names(head)`. Arity mismatch, or a keyword whose name
is not a head field, skips the clause. Goal args are passed through as terms, exactly as
the existing rung-1 and rung-2 probes do.

**Run the head prefix alone first.** If it fails, this clause was never a route — skip it
silently. If it *raises*, that is a probe artifact, not a finding: skip the clause and
never report the exception as the cause. This is not hypothetical — the schengen depth-2
probe raises `NotImplementedError: term_to_ast_expr: unsupported term type date` purely
because a live `datetime.date` gets compiled into a query.

**Walk the body** with `_first_failing`. If the failing conjunct is a `Call` and depth
remains, recurse into it; if the recursion returns leaves, use them, otherwise this
conjunct is the leaf. A clause whose body turns out to be *satisfiable* under the head
prefix contradicts the all-holes probe that got us here; it yields no leaf and the
disagreement is noted rather than papered over.

One clause route can therefore fan out into several leaves — the flat list is leaves, not
routes.

**Emit the leaf** as `file:line  <source text>` plus up to 4 bindings, one per line.

### 3. Source text and variable names

Reify the descended clause from its own file with `_reified_goals`, **tail-aligned**.
`_normalize_structural_head_args` *prepends* `Unify` goals for structural head arguments,
so a runtime body can be longer than its source; `_reified_goals` currently declines on
any count mismatch. Compute `k = len(runtime) - len(source)` and accept the alignment only
when `k >= 0` **and** the first `k` runtime goals are `Unify` instances. Otherwise fall
back to `term_str` on the runtime conjunct, which renders variables as `_` — degraded but
honest.

Line number: the reified goal's own position, falling back to the clause's start line.

Bindings: `_collect_named([leaf], [reified_leaf])` with the leaf's prefix re-established,
then deref — the same path `_report_bindings` uses.

### 4. Bounds

* `DIAG_MAX_DESCENT_DEPTH = 2`
* `DIAG_MAX_DESCENT_CLAUSES = 4` per predicate; a truncated clause list is **noted**, not
  silently dropped
* `DIAG_MAX_DESCENT_LEAVES = 6` in total across the whole descent, since depth 2 with four
  clauses per level could otherwise emit sixteen; truncation is likewise noted
* 4 bindings per leaf
* a `(functor, arity)` cycle guard along the descent path
* the existing `deadline` is checked per clause and `_DiagBudgetExceeded` propagates to
  `diagnose_failure`, which already appends the budget note

No second budget is introduced — `$CLAUSAL_TEST_DIAG_BUDGET` remains the only one.

### 5. Rung 2

The satisfiability check at the all-holes probe becomes a solution iterator. Take up to 3
solutions, deref the holes, and render each as the goal with all arguments substituted
(reified `Goal` → `render_source`, with per-argument `_render_value` as fallback). The
message becomes:

```
the predicate has solutions, but none within one argument of this goal — two or more
arguments differ; the predicate does have:
  <solution 1>
  <solution 2>
```

### 6. Error handling

The descent raises nothing except `_DiagBudgetExceeded`, `RecursionError` and `_FATAL`.
Every other exception is swallowed per clause and that clause is skipped. If no leaves are
produced at all, the current rung-3 sentence prints unchanged — the worst case is today's
behaviour.

### 7. New `GoalDiagnostic` fields

`descent: list[str]` and `nearest_examples: list[str]`, rendered by `lines()` after
`nearest`.

## Testing

Unit tests follow the convention in `tests/test_testing_diagnostics.py`: write `.clausal`
fixtures into `tmp_path`, run through `main`, assert on report content.

1. Contradictory guards in one clause — the leaf names the guard and shows its binding.
2. Two clauses failing at different conjuncts — two leaves.
3. One-level-down nesting — the leaf is the inner predicate's conjunct.
4. **Two-file fixture** — covers the cross-module resolution and the module switch.
5. Builtin or unresolvable predicate — message unchanged, no descent.
6. Predicate with zero clauses — message unchanged, no descent.
7. Depth cap — a three-level chain stops at two.
8. Clause cap — six clauses yield four leaves plus the truncation note.
9. Rung 2 — the rendered solutions appear.

End-to-end verification against the three archived trees under
`/workspace/clausify-executor-train/_reruns/study13/`
(`study_schengen_max_stay_r1`, `study_vat_pro_rata_deduction_r2`,
`study_working_time_average_r1`): run `python -m clausal.testing` on each and assert the
printed conjunct names the known cause. No model, no GPU.

Regression gate: the full suite's failure *set* must not grow. Baseline on clone `main` is
one standing failure, `tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks`.

## Non-goals

* No change to the pass/fail verdict — the diagnostic still only explains an
  already-decided failure.
* No new budget knob.
* No descent beyond depth 2.
* Rung 1 is untouched.

## Leak surface

Everything printed derives from the producer's own rulebase and its own tests. Nothing
here touches sealed-oracle data.
