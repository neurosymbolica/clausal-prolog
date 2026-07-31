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

## Landed (2026-07-31)

**Decision: degeneracy = non-groundness of the probe solution, checked with the
canonical `_is_ground`** (`clausal.logic.builtins._helpers`; verified it walks
operator nodes such as the `BitOr` cons-head near-miss). Two triggers, both in
`_report_nearest` (`clausal/testing.py`):

- **Rung 1:** a slot whose near-miss value contains unbound holes is recorded but
  skipped; scanning continues for a slot with a *concrete* near-miss (which is
  reported exactly as before). If only degenerate slots solved, the weak rung-1
  line is rendered first (it survives a budget blow), then `_report_descent` runs
  with the honest intro "the predicate has solutions with argument N freed, but
  none binds argument N to a concrete value"; findings replace the near-miss,
  `"none"` leaves the old rendering as the fallback.
- **Rung 2:** if none of the all-holes examples binds every hole (e.g. a
  var-coupled fact matching the bare-holes probe as `pairq(_, _, _, _)`), same
  pattern with intro "…none binds every argument to a concrete value"; findings
  clear the anonymised examples.

`_report_descent` gained an `intro` parameter (rung-3 default reproduces the old
strings byte-for-byte) and a bool return. The descent itself only states facts
about the concrete arguments, so its findings are truthful at every rung.

**Verified against the evidence shapes:** the pinned `wt_qualifying_totals`
study-13 shape now yields the head listing with the source-faithful
`[WORKED_MINUTES, STATUS] | REST_WEEKS` head instead of
`BitOr(None, [2880, _], [])`; lone one-sided constraint bounds
(`X < 10, X < 0` — previously satisfiable-with-X-unbound, which forced the
descent fixtures to use contradictory pairs) now descend to the failing conjunct
with its concrete binding (`X < 0`, `X = 5`).

**Deliberate boundary:** a GROUND near-miss keeps rung 1 even when it is only a
trivial base-case match (`wt_qualifying_totals([], TOTAL, N)` with outputs
free) — every cheap "trivial match" discriminator considered regresses fact-table
predicates, where a ground near-miss is exactly the right diagnosis. Pinned by
`test_ground_base_case_near_miss_keeps_rung_1` /
`test_ground_fact_near_miss_keeps_rung_1`.

Tests: 6 new in `tests/test_testing_descent.py` (§ "degenerate rung-1/2
solutions descend"). Full clone suite 10823 passed, only the standing
doc-snippet failure.
