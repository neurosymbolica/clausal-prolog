# investigate(A08, Opus): CLP(Q) bound enforcement through Gaussian elimination + B&B on parametric vars

**Findings:** A08-F002 (critical), A08-F006 (high); related: A08-F001
**Tests:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestClpqSoundness::test_parametric_bounds_infeasible_eq_fails`, `::test_bb_inf_parametric_int_var`

## Problem
The Tableau tracks bounds in `lo`/`hi` for every variable, but:
1. `add_equality` deliberately skips checking the pivot's bounds when it
   becomes parametric (`clpq.py:315-318`), and nothing later enforces them —
   `X,Y in [0,10], X+Y == 100` is ACCEPTED (unsound satisfiability), and a
   subsequent `maximize` on the poisoned store fails as if unbounded.
2. `_propagate_determined` (`:366-368`) and `fix_variable` (`:717-718`)
   OVERWRITE `lo`/`hi` instead of intersecting.
3. `optimize`/`_restore_feasibility` consult bounds only for row/non-basic
   vars, so `set_bound` on a parametric var is a no-op — which breaks
   branch-and-bound (`_bb_solve`) whenever the branching integer variable was
   Gaussian-eliminated: B&B recurses to `_BB_MAX_DEPTH` and fails on feasible
   problems (bb_inf/int_minimize).

## Direction (Holzbaur 1994)
In the reference solved-form algorithm, *bounded* variables are never plain
parametric: a bounded variable that gets eliminated must either have its
bounds transferred to the substituted expression (add the parametric
definition as a bounded ROW so the simplex sees it: `x_row = pc + pk` with
`lo <= x_row <= hi`) or trigger a dual-simplex feasibility pass at
elimination time. Design decision needed on representation: (a) turn bounded
parametric vars into slack-like rows; (b) run a feasibility LP over
`parametric` after each elimination; (c) full rework of the
basic/nonbasic/parametric split to Holzbaur's solved form. Same machinery
then makes B&B's `set_bound` on parametric vars meaningful.

Also fold in: `_BB_MAX_DEPTH = 50` silently truncates the search (possible
suboptimal/failed answers on deep problems) — replace with a proper
completeness argument or an explicit error.

## Acceptance
Both xfail tests flip; `test_classic_lp_maximize_310`,
`test_gaussian_three_var_exactness` and tests/test_clpq.py stay green.
