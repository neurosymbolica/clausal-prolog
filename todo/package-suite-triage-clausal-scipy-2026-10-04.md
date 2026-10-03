# clausal-scipy: package-suite failures triaged (2026-10-04)

Box run on 1c5ee5a0: **26 failed**. After feat/package-followups-2026-10-04:
**0 failed**.

| Group | Class | Count | Representative node id | Status |
|---|---|---|---|---|
| Quantity dims are keyed by the unit ATOM (`"metre"`); tests compared against `{_u.metre: 1}` | ENGINE-SEMANTICS DRIFT | 22 | `packages/clausal-scipy/tests/test_scipy_constants.py::TestSpeedOfLight::test_dims` | fixed (tests compare atom keys) |
| a ModulePredicate called at an unregistered arity RAISES `existence_error(procedure, N/A)` (F005); tests expected silent failure | ENGINE-SEMANTICS DRIFT | 2 | `packages/clausal-scipy/tests/test_scipy_special.py::TestPredicateMeta::test_unknown_arity_fails` | fixed (tests assert the error) |
| `derivative/3` handed back scipy's raw `_RichResult` (a dict SUBCLASS, so `isinstance(out, dict)` let it through) holding NumPy scalars; `OK == True` failed on `np.True_` | PACKAGE BUG | 2 | `packages/clausal-scipy/tests/fixtures/scipy_differentiate_tests.seam::derivative result has success field` | fixed (`type(out) is dict`; 0-d NumPy scalars become Python scalars) |

Remaining failures: none.

Related (P1, same branch): `module_signatures` now lists `stats_dist`,
`stats_freeze_dist`, the five `stats_frozen_*` and scipy_interpolate
`free` (empty arity set).
