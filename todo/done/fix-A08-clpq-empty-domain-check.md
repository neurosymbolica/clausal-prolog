# fix(A08): clpq `in_q(X, lo, hi)` accepts lo > hi (empty domain)

**Finding:** A08-F003 (correctness, high)
**Test:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestClpqSoundness::test_in_q_empty_interval_fails`

## Bug
`clausal/logic/clpq.py:1001-1004` (`_post_q_domain`, fresh-registration
branch) never compares `lo > hi`; only the already-registered branch does.
`in_q(X, 10, 0)` succeeds and leaves a poisoned variable that rejects every
later binding (unsat store reported satisfiable).

## Fix sketch
At the top of `_post_q_domain` (or in `in_q` after Fraction conversion):
`if lo is not None and hi is not None and lo > hi: return False`.

## Acceptance
xfail test flips to pass; `in_q(X, 5, 5)` still binds X to 5 (point domain).
