# fix(A08): or_minimize/or_maximize and lp_minimize/lp_maximize ignore unify failures

**Finding:** A08-F016 (correctness, medium)
**Test:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestCpsatTranslationFidelity::test_or_minimize_unify_failure_not_ignored`

## Bug
`clportools.py:995-998, 1016-1019` and `clportools_lp.py:490-495, 514-519`
loop over `rev_map` binding every registered var to its model value but
discard the `unify(...)` return value. If a Clausal var is already bound to a
conflicting value (possible because there is no OR/LP attr hook — see
A08-F013 / investigate-A08-solver-store-sync-hooks.md), the optimizer still
yields an "optimal" solution inconsistent with the substitution.

## Fix sketch
Collect the unify result; on failure, `trail.undo(mark)` and return without
yielding (matching how `label_or`/`label_z3` treat per-solution unify
failures). Consider whether a retry with a blocking clause is wanted (probably
not for optimization — just fail).

## Acceptance
xfail test flips; guards `test_lp_maximize_classic`, `test_cpsat_linear_system`
stay green.
