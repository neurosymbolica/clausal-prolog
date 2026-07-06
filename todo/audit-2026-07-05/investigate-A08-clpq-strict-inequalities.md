# investigate(A08, Opus): CLP(Q) strict inequalities — passive diseq is unsound

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
