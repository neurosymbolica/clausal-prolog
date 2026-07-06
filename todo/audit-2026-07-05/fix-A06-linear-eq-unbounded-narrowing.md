# fix(A06-F002): output-mode linear == never grounds unbounded vars

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F002
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestOutputModeLinearEq (3 xfail — flip to pass)

## Bug

Sum/ScalarProduct narrowing computes each var's "other side" bounds as
`total_sum - own_contribution`. When the var's own domain is the CLP(Z)
default (-inf, inf), that is inf - inf = nan, and the nan guard skips
narrowing — even when every OTHER operand is ground:

    Double(X, Y) <- (Y == 2 * X)
    Double(X, 8)          # X stays unbound; SWI: X = 4
    X == -Y, Y is 3       # X stays unbound; expected X = -3

Contradicts docs/constraints.md + cheat-sheet: "`==` posts a CLP(ℤ)
constraint — works in all directions, with unbound vars". Sites:
clpfd.py:898-903 (SumConstraint), :962-966 (ScalarProduct), :532-537 +
:587-590 (bignum helpers), _clpfd_propagate.c:1681-1687 (sum_propagate),
:1849-1855 (scalar_propagate).

## Fix direction

Compute the other-side bounds by summing over j != i directly (skip the
subtraction trick), treating any infinite other-side bound as inf without
poisoning the finite case. O(n^2) worst case per pass, or keep O(n) by
tracking (finite_sum, count_of_pos_inf, count_of_neg_inf): var i's
other-side max is finite iff the only inf contribution is its own.

## Acceptance

- 3 xfails pass; `test_bounded_output_mode_works` and `test_input_mode_works`
  stay green; sendmore/queens counts unchanged.
- `X == Y + Z` with Y,Z later ground binds X; chain through several vars works.
