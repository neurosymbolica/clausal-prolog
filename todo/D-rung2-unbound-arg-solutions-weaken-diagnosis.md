# D — rung-2 solutions on unbound/degenerate args weaken the diagnosis

**Filed:** 2026-07-30, from the implementation of
`todo/done/B-assertion-diagnostic-stops-one-level-above-the-cause.md`.
**Repo:** clausal. **Needs a study run:** NO — reproducible against `clausal.testing`
directly (see Evidence below).
**Kind:** open design question — file it, do not solve it here.

## The question

A failing goal whose predicate's all-holes probe finds a solution that leaves the
over-constrained argument unbound — or is satisfied by a base-case fact via bare holes
(e.g. `wt_qualifying_totals([], 0, 0)`) — is reported at rung 2 (or rung 1) instead of
descending, which can be the weaker diagnosis. Should the descent also run when the found
solutions are degenerate (unbound holes / trivial base-case matches)?

## Why it matters

Rung 3's descent (`_report_descent` / `_descend`) is the rung that lists the surviving
clause heads (`no clause head unifies ... the heads are:`) and renders them
source-faithfully (e.g. a cons head `[WORKED_MINUTES, STATUS] | REST_WEEKS`). It only runs
when the all-holes probe finds **no** solutions (`clausal/testing.py:808-813`). When a
recursive predicate has a `| REST_WEEKS`-style clause head, freeing the over-constrained
list argument to a fresh hole unifies with that head (and/or with the `[]`/`0`/`0`
base-case fact), so rung 1 (per-arg probe, "the predicate DID have a solution, which did
not unify (argument 1 differs)") or rung 2 (all-holes examples) fires first and the caller
never sees the descent. The near-miss it shows — e.g. `BitOr(None, [_, work], [])` — leaves
the argument that actually failed unbound, so it carries no value about *why* the concrete
input was rejected.

## Evidence

- study13 `study_working_time_average_r1`, direct `wt_compliance(...)` and
  `wt_qualifying_totals(...)` tests: intercepted at rung 1/2 with an unbound-hole
  `BitOr(None, ...)` near-miss; descent (and therefore `no clause head unifies` /
  `| REST_WEEKS`) never fires. The `wt_qualifying_totals([], 0, 0)` base-case fact
  satisfies the bare-holes probe.
- Task 3/5 fixture adaptations in `tests/test_testing_descent.py`.

## Not decided here

Whether "degenerate solution" (unbound over-constrained arg, or trivial base-case-only
match) should be a trigger to *also* descend, and how to detect degeneracy cheaply
without regressing the rung-1 cases where the near-miss genuinely carries a value.
