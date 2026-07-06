# fix(A08): clpq `_tableaux` leaks and cross-contaminates on recycled trail ids

**Finding:** A08-F005 (memory + correctness, critical)
**Tests:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestClpqSoundness::test_no_stale_tableau_on_recycled_trail_id`,
`TestClprCoreMemory::test_clpq_post_solve_loop_no_leak`

## Bug
`clausal/logic/clpq.py:789-807` keys `_tableaux`/`_last_snapshot` by
`id(trail)` and removes entries only via a `trail.record()` undo callback.
A trail dropped without a full undo (the normal case for a completed solve)
leaves its entry behind forever, and a NEW `Trail()` allocated at the same
address inherits the stale tableau: a probe showed 200 independent queries
accumulating 200 variables (with their bounds and constraints) into one
shared tableau — cross-query constraint contamination, not just a leak.

## Fix sketch
Mirror `clpz3.get_z3_state` / `clportools.get_cpsat_state`:
`weakref.finalize(trail, _tableaux.pop, tid, None)` (plus `_last_snapshot`)
at creation time; keep the undo callback for backtrack-past-creation.

## Acceptance
Both tests flip to pass; no behavioural change for live trails.
