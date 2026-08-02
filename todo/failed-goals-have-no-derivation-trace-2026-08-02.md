# Failed and wrong-value goals have no derivation trace — RAISED goals do

**Filed:** 2026-08-02, from the formalizer-training harness team (clausify-executor-train).

## The asymmetry

A goal that RAISES gets excellent reporting: innermost failing call, arity remedies,
bindings at the point of the exception. A goal that FAILS logically, or that succeeds
with a WRONG VALUE, shows only the top-level mismatch:

```
max_additional_days ... MAX == 90 / bindings at failure: MAX = 0
```

The actual defect is routinely 2–3 levels down, failing silently inside a `findall`.

## Measured incident

`schengen_max_stay_r1` — FOUR full repair budgets (original + 2 resumes + a P3b
rewind, 28+ attempts, heavy byte-identical stalling) against one unchanging report
shape:

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

`posted_workers_long_term_trigger_r1` is stuck in the same class: `triggered` vs
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
