# Failed and wrong-value goals have no derivation trace — RAISED goals do

**Filed:** 2026-08-02, from an external authoring harness team.

## The asymmetry

A goal that RAISES gets excellent reporting: innermost failing call, arity remedies,
bindings at the point of the exception. A goal that FAILS logically, or that succeeds
with a WRONG VALUE, shows only the top-level mismatch:

```
max_additional_days ... MAX == 90 / bindings at failure: MAX = 0
```

The actual defect is routinely 2–3 levels down, failing silently inside a `findall`.

## Measured incident

A rolling date-window authoring run — FOUR full retry allowances (original + 2 resumes
and a rewind, 28+ attempts, heavy byte-identical stalling) against one unchanging
report shape:

```
max_additional_days ... MAX == 90 / bindings at failure: MAX = 0
```

The actual defect chain, reconstructed post-mortem:

- the model calls kit `window_days_used(EXTENDED_HISTORY, CURRENT_DATE, ...)` with a
  date OBJECT where the kit wants `[Y,M,D]` (`REF_YMD`), and/or builds interval terms
  containing UNBOUND variables (`[ENTRY_TRIPLE, EXIT_TRIPLE]` with `ENTRY_TRIPLE` never
  bound in the clause);
- `intervals_wf` and the offset arithmetic FAIL logically, quietly;
- the `findall` collapses to `[0]`, `max_list` returns 0, every eligible fixture scores
  ineligible;
- from the repair prompt: `MAX = 0`, nothing else, for every attempt.

A separate trigger-threshold authoring run is stuck in the same class: `triggered` vs
`not_triggered` with 4/7 byte-identical stalls against a `distinct_days_total` shape.

Neither run could locate the defect from the report. The engine's failure trace for
RAISED goals would have named `window_days_used` or `intervals_wf` on attempt 1.

## The gap

The engine's goal-level diagnostic (`diagnose_failure`, the conjunct-level reporter)
fires on RAISED goals and produces the innermost failing call. It does not fire on
FAIL or on wrong-value success, because there is no exception carrying a stack trace —
the engine just produced no solution (or the wrong solution) and backtracked. The
information about which sub-goal pruned the last candidate is discarded by the
resolution engine before the test harness sees the result.

## Candidate designs

**Candidate 1 — why-provenance for the failing conjunct.**
When a goal FAILS (no solution) or returns a wrong value that a test assertion
catches, annotate the failure with the deepest conjunct that last failed inside the
resolution. This is the full engine-level fix: the resolver tracks the "blame" conjunct
as it backtracks and surfaces it at the top-level failure point. Scope: Clausal engine
internals; no harness changes required. This is the correct fix for the whole class.

**Candidate 2 — opt-in diagnostic re-run on FAIL or wrong value.**
On a FAIL or wrong-value outcome, re-run the goal in a tracing mode that records the
last failing conjunct before backtracking completes. The harness already has a 10-second
diagnostic re-run budget (`$CLAUSAL_TEST_DIAG_BUDGET`) used for RAISED goals; extend
that budget to cover FAIL and wrong-value goals as well. The re-run would be opt-in
(controlled by the same env var or a companion `$CLAUSAL_TEST_DIAG_FAIL`) to avoid
slowing normal test runs. The trace depth can be capped (e.g. 5 conjuncts) to bound
cost. This is a harness-facing interface contract: the engine exposes a trace mode, the
harness enables it on diagnostic re-runs.

**Candidate 3 — findall collapse sentinel.**
A narrower variant: when a `findall` body fails for all candidates and produces an
empty list (or a list of zeros), emit a diagnostic note naming the body goal and the
failure reason rather than silently returning `[]`. This does not give full
why-provenance but would have surfaced the `window_days_used`/`intervals_wf` failure
on attempt 1 in both measured cases. Scope is limited to `findall` and is a smaller
change than candidate 1 or 2; it does not cover wrong-value goals outside `findall`.

The asymmetry with RAISED goals means any of the three candidates produces strictly
more signal than today for the most common repair-blocking class observed in the
training harness.

## Outcome

Implemented **candidate 3 (findall collapse sentinel)** plus the minimal
**wrong-value bridge** needed to reach it — the smallest change that closes the
measured incident. All in `clausal/testing.py`, tests in
`tests/test_testing_descent.py`. No engine internals touched; this stays inside
the existing test-harness diagnostic re-run (bounded by `$CLAUSAL_TEST_DIAG_BUDGET`,
no second budget knob).

### Why the existing rung-3 descent didn't already cover this

Reproduced the incident shape first (a `findall` whose body predicate fails on a
wrong-type argument for every candidate, feeding `max_list` → a `==` compare) and
confirmed today's report is exactly `MAX == 90` / `bindings at failure: MAX = 0`
with nothing about the findall. Traced the code path:

1. `_first_failing` walks the Test body's cumulative prefixes. Conjunct 1,
   `max_additional_days(MAX)`, **succeeds** — because `findall/3` ALWAYS succeeds
   (an empty body result binds the bag to `[]`), and `max_list_or_zero([], 0)`
   then returns 0. Conjunct 2, `MAX == 90`, is the first that fails.
2. The failing conjunct is therefore the **comparison**, not a predicate call, so
   `_report_nearest` takes its "this conjunct is not a predicate call" branch and
   the rung-3 descent (`_report_descent`) — which only ever fires on a failing
   `Call` — is never invoked.
3. Even if descent HAD been pointed at `max_additional_days`, its clause body
   re-runs **satisfiable** (the collapsed findall still succeeds), so
   `_first_failing` inside `_clause_leaves` would have found nothing to blame and
   written the clause off as non-determinism. The failure was swallowed twice: by
   `findall`'s unconditional success at the top level, and by the same success
   again inside descent.

So the gap is two-part and both parts are needed to reach the culprit.

### What I implemented

- **findall-collapse sentinel** (`_findall_parts`, `_findall_collapsed`,
  `_findall_collapse_finding`, `_scan_body_for_findall_collapse`): during descent,
  when a clause body re-runs satisfiable, scan its conjuncts for a `findall(Tmpl,
  Goal, List)` whose result bag looks like a swallowed failure (`[]` or all-zeros)
  AND whose body `Goal` has no solution for the current bindings. Run `Goal`'s own
  conjuncts through the existing `_first_failing` walker and render the first
  failing body conjunct as a leaf (source line + bindings), using the same
  `_descent_leaf_line`/`_leaf_bindings`/reify machinery the ordinary descent uses.
  A healthy findall (produces useful solutions) is never blamed — the sentinel
  requires both a collapsed-looking bag and a body that fails for every candidate.
  The scan also recurses (bounded by `DIAG_MAX_DESCENT_DEPTH`) into any other
  satisfiable predicate `Call` in the body, so a wrapper predicate that merely
  forwards to a findall-bearing one is still traced to the collapse.
- **wrong-value bridge** (`_report_wrong_value`, `_wrong_value_producer`,
  `_collect_var_ids`): when the failing conjunct is not a `Call` (a comparison /
  unification) and the ordinary descent added nothing, find the earliest prefix
  `Call` that shares a runtime `Var` **object identity** with the failing goal —
  the producer of the wrong value — and descend into it (which now reaches the
  findall sentinel). Matching is by raw Var identity, deliberately without deref,
  because the prefix has already bound the shared Var to its wrong value by the
  time the bridge runs.

Report now, on attempt 1:

```
goal 2 of 2 failed:
  MAX == 90
bindings at failure: MAX = 0
no solution (this conjunct is not a predicate call, ...)
  the value it compares was produced by max_additional_days(...), which succeeded
  with a wrong value; that producer's failing route:
  a findall whose body failed for every candidate — it silently collapsed to an
  empty result:
    repro.clausal:13  window_days_used(bad_atom, D)
```

### Out of scope

- Full engine-level blame tracking (candidate 1) and extending the RAISED-only
  re-run to a general FAIL/wrong-value trace mode (candidate 2) were not needed for
  the measured incidents and are strictly larger; not done.
- Wrong-value cases whose producer is not a findall-bearing predicate (e.g. a plain
  arithmetic miscomputation with no swallowing construct) still report only the
  honest top-level mismatch — the bridge descends but finds no swallowed failure and
  stays quiet, which is correct (no fabricated blame).
- Did not touch exception propagation through `findall` — the adjacent open todo
  `todo/catch3-does-not-catch-an-exception-from-a-trampolined-subgoal.md` remains its
  own task; this change reads a findall's result and re-runs its body but does not
  alter how exceptions escape it.

### Tests / verification

- New tests in `tests/test_testing_descent.py`:
  `test_findall_collapse_behind_wrong_value_is_named`,
  `test_findall_collapse_via_nested_producer` (wrapper predicate one level above
  the findall, exercising the recursive descent step),
  `test_healthy_findall_is_not_blamed`.
- Roborev review (job 319) raised three Low findings, all addressed: extracted the
  duplicated `DIAG_MAX_DESCENT_LEAVES` cap into `_cap_leaves`; removed a dead
  speculative branch in `_flatten_reified` (verified the reified findall body is a
  Python tuple, not a comma-`Goal`); made the nested-producer test genuinely one
  level deeper to match its comment (and cover the recursive path).
- Full suite (pyenv 3.13.3, `--ignore=tests/test_clportools.py`, per-test timeout
  disabled to avoid the load-marginal abort): **10874 passed, 2 failed, 136 skipped,
  44 xfailed**. The two failures are the known-standing baseline
  (`test_F026_multi_star_splits_bounded_for_moderate_input` and
  `tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks`) — 0 new
  regressions.
