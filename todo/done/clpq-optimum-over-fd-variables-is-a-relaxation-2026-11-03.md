# CLP(Q) optima over CLP(FD) variables read a relaxation (2026-11-03)

**Status: FIXED 2026-11-03 (COMMIT), option A (operator ruling
2026-11-03).** Both cases below raise now, on both solvers: an FD
variable with holes anywhere in the objective's component raises
`representation_error(fd_domain_with_holes)`, and a maximize/minimize
whose relaxed optimum gives an FD variable a non-integer raises
`representation_error(fd_relaxation_not_integral)`. Pinned by
tests/test_clpq_fd_promotion_optima.py::
test_an_optimum_the_relaxation_cannot_answer_is_refused (and
test_an_optimum_the_relaxation_answers_is_kept for the cases that still
answer). Left open, documented in D29 and docs/clpq.md: CLP(FD)
constraints between FD variables (`X #= Y + 3`) are not in the CLP(Q)
store, so an optimum clpfd's propagation refuses still fails.

Earlier status: OPEN (partly guarded). An FD variable enters CLP(Q) with its
domain's hull (DEVIATIONS.md D20, D29): a rational relaxation without the
holes and without integrality.

Guarded: maximize, minimize and bb_inf raise
`representation_error(fd_domain_with_holes)` when a variable of the
objective (or of bb_inf's integer list) has a domain with a hole
(tests/test_clpq_fd_promotion_optima.py::
test_an_optimum_over_a_domain_with_holes_is_refused). sup/2 and inf/2
answer on the hull, documented (docs/clpq.md).

Still wrong, both solvers (checked 2026-11-03):
1. `X in 1..5, {2*X >= 3}, minimize(X)` fails: the relaxation's optimum
   3/2 is bound, clpfd refuses it, though X = 2 exists.
2. `X in 0..2 \/ 8..10, {Y = X, Y =< 7}, maximize(Y)` fails: X has holes
   but is not in the objective, so it is not refused; Y = 7 binds X = 7,
   which clpfd refuses, though Y = 2 exists.

Options (a ruling is needed):
- A. Refuse more: any FD variable linked to the objective through the
  store (the port's components can list them), and any FD variable in a
  maximize/minimize whose relaxed optimum is not integral. Simple, but
  refuses programs that could be answered.
- B. Answer exactly: treat FD variables as integers and their holes as
  disjunctions, i.e. run bb_inf (branch and bound) with the FD variables
  as integer variables and branch on holes. Correct, a new algorithm
  outside 1.3.3.
- C. Document maximize/minimize over FD variables as relaxation-only
  (failure where the relaxed optimum is not an FD value) and keep the
  holes refusal for bb_inf alone.
