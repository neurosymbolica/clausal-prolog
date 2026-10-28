# Legacy CLP(Q): a strict inequality is `=<` plus a passive disequality, so `{X<Y, Y<X}` is accepted (A08-F004, A08-F008, A08-D004)

**Status: FIXED 2026-10-28 (commit 3b690b9e).** Legacy keeps strict bounds in the simplex as delta-rationals (A08-D004's recommended direction), so `{X<Y, Y<X}` fails at the post that closes it; the strict disequality is gone. Pinned in tests/test_clpq_legacy_strict_bounds.py::test_a_closed_strict_bound_fails and tests/audit_2026_07_05/test_08_clpqr_z3.py::TestClpqSoundness::test_strict_cycle_fails (xfail removed).

Previously: open on the default (legacy) solver for the `{X<Y, Y<X}` cycle only; fixed under `CLAUSAL_CLPQ=holzbaur`. The `entailed/1` half (A08-F008) was fixed on legacy 2026-10-22: `entailed` now finds a strict relation or a disequality the stored disequalities imply (`Tableau.face_removed`); pinned in tests/test_clpq_entailed_strict.py, and the two entailed tests below lost their xfail markers.
Triaged 2026-10-20, moved from the 2026-07-05 audit folder (was
`investigate-A08-clpq-strict-inequalities.md`). Re-ran the pinning tests in
tests/audit_2026_07_05/test_08_clpqr_z3.py:

| test | legacy (default) | `CLAUSAL_CLPQ=holzbaur` |
|---|---|---|
| `TestClpqSoundness::test_strict_cycle_fails` | **XFAIL** | XPASS |
| `TestClpqSoundness::test_strict_then_alias_unify_fails` | XPASS | XPASS |
| `TestClpqSoundness::test_ne_then_alias_unify_fails` | XPASS | XPASS |
| `TestClpqSemanticsVsReference::test_entailed_diseq_after_ne` | XFAIL; PASSED since 2026-10-22 | XPASS |
| `TestClpqSemanticsVsReference::test_entailed_strict_after_strict` | XFAIL; PASSED since 2026-10-22 | XPASS |

The interim aliasing fixes (a)/(b) below landed on legacy in the
2026-10-11 series (8eb14281 "every binding and equality checks every
disequality", 6706d454). Left on legacy: the `{X<Y, Y<X}` cycle (and
`entailed/1` of a stored strictness or disequality, fixed 2026-10-22). The port keeps
Holzbaur's strictness on each bound, which is design decision A08-D004's
recommended direction. Related open todo on the same solver:
todo/done/clpq-strict-bounds-closed-by-inequalities-2026-10-11.md.

The original audit text follows.

**Findings:** A08-F004 (high), A08-F008 (low); design question A08-D004 (parked)
**Tests:** `tests/audit_2026_07_05/test_08_clpqr_z3.py` — `test_strict_cycle_fails`, `test_strict_then_alias_unify_fails`, `test_ne_then_alias_unify_fails`, `test_entailed_diseq_after_ne`, `test_entailed_strict_after_strict`

## Problem
`q_lt` = `q_le` + passive linear disequality; `q_ne` stores
`('linear', coeffs, const)` checked only in `fix_variable`. Consequences:
- `{X<Y, Y<X}` accepted (unsat);
- `{X<Y}, X is Y` and `{X!=Y}, X is Y` accepted — the var-var `_q_hook` path
  adds the equality but never calls `_check_diseqs`, and `_check_diseqs`
  cannot detect that the two columns are now aliased;
- `entailed('<'...)` and `entailed('\\='...)` are incomplete w.r.t. the
  stored diseqs/strictness (SICStus answers true).

## Direction
Holzbaur (1994) represents strict bounds with epsilon-augmented rationals
(lexicographic pairs `a + b*eps`), making `{X<Y, Y<X}` fail at posting and
strict entailment exact. Interim cheaper fixes: (a) call `_check_diseqs`
from the `_q_hook` var-var path after `add_equality`; (b) in `_check_diseqs`,
substitute parametric definitions into the diseq's linear form — if the form
reduces to a constant equal to `constant`, fail (catches aliasing and affine
pinning); (c) `entailed` can consult diseqs for the `\\=` case. The full
epsilon rework should ride with the F002 bound-enforcement redesign.

## Oracle note
No Prolog CLP(Q) oracle is runnable on this box (see
investigate-A08-clpq-prolog-oracle.md); the repro systems here are
hand-checkable unsatisfiable systems.
