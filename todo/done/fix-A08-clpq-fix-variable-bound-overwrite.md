# fix(A08): clpq `Tableau.fix_variable` overwrites bounds instead of intersecting

**Finding:** A08-F001 (correctness, critical) — `docs/superpowers/audits/2026-07-05-fable-partition/08-clpqr-z3/findings.md`
**Test:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestClpqSoundness::test_qle_bound_then_unify_outside_fails`

## Bug
`clausal/logic/clpq.py:717-718` (`fix_variable`) does
`self.lo[vid] = value; self.hi[vid] = value` unconditionally. Bounds that live
only in the tableau (posted by the single-variable fast path of
`add_inequality` via `set_bound`, which never refreshes the `QVar` attribute)
are silently destroyed, so `in_q(X,0,100); q_le(X,5); X is 50` succeeds.

## Fix sketch
In `fix_variable`, before assigning, check
`value` against `self.lo.get(vid)` / `self.hi.get(vid)` and return False when
outside (same check `_q_hook` performs against the attr bounds). Optionally
also keep `QVar` in sync when `set_bound` tightens a user var (put_attr from
`q_le`/`q_ge` single-var path) so hook-level checks stay accurate.

## Acceptance
- The xfail test above flips to pass (remove the marker).
- `test_backtracking_restores_tableau_bound`, `test_classic_lp_maximize_310`
  and the rest of `test_08_clpqr_z3.py` stay green.
