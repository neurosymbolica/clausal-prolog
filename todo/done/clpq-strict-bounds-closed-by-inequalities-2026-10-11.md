# CLP(Q): a strict bound closed by an inequality is not caught

**Status: FIXED 2026-10-28 (commit 3b690b9e).** The legacy simplex keeps each bound's strictness and reads a strict bound as a delta-rational (Dutertre and de Moura), so feasibility decides strictness on every post, with no LP: both stores below fail, `{X > 0, X =< 2}, bb_inf([X], X, I)` gives `I = 1`, and a 200-variable `<` chain posts in 0.04 s and labels in 5.7 s (21 s before). Pinned in tests/test_clpq_legacy_strict_bounds.py (`test_a_closed_strict_bound_fails`, `test_bb_inf_respects_a_strict_bound`, the 24-order `test_a_sum_of_nonnegatives_below_zero_fails_in_every_order`, and a seeded differential against the port) and tests/test_clpq_box_bounded_optimum.py::test_a_strict_inequality_the_store_closes_fails[bound_last] (xfail removed). Still passive, and so still caught only at the next binding: a true `=\=` that inequalities alone close (`{X =\= Y, X =< Y, Y =< X}`).

A strict `<` is stored as `=<` plus a disequality (`X - Y =\= 0`).  The
disequality is checked in three ways:

- cheaply, after every change, once every variable in it is fixed;
- by entailment (an LP for the minimum, and the maximum unless it came
  from `<`), after any binding or equality, skipped when the current
  assignment already gives the expression another value.

It is not checked after an inequality, a new disequality or `in_q/3`,
since that cost two LPs per open disequality on every post: a chain of
200 `<` posts took over three minutes.  So these succeed although no
solution exists, and are only caught later, when a variable is bound:

    {X < Y, X >= 3, Y =< 3}
    {X < Y}, in_q(X, 3, 10), in_q(Y, 0, 3)

A z3 fuzz (2026-10-11) counted 54 such stores in 6,000, and 46 in
12,000 with bindings mixed in; none wrongly failed.  On the parent of this series, 667 of 1,500 were wrong.

Related, and older, fixed 2026-10-22: `entailed/1` ignored disequalities
(after `{X < Y}`, neither `entailed(X < Y)` nor `entailed(X =\= Y)` held);
pinned in tests/test_clpq_entailed_strict.py.  Also fixed then: an `in_q/3`
that closes a strict bound on one variable to a point (`{X > 0}, in_q(X,
-1, 0)`) binds the variable, so it fails; the two-variable stores above
still succeed.  A fuzz against the port (2026-10-22, about 16,000 stores)
found 28 such accepted stores, every one with a strict relation in it.

The general fix is strict bounds inside the simplex.  SMT solvers do this
with delta-rationals (Dutertre and de Moura): a strict bound `x < c` is
`x =< c - d` for a symbolic infinitesimal `d`.  Feasibility then decides
strictness on every post, with no LPs.  Holzbaur's CLP(Q) keeps a
strictness flag on each bound to the same end.

Cost note: labeling a 200-variable `<` chain takes about 19 s (100: 3 s):
each binding re-checks every open disequality, and the simplex's current
assignment sits on the strict bounds, so the cheap screen rarely skips the
LP.  The parent of this
series could not label such a chain at all (it failed).

Also older than this series: `bb_inf/3` ignores strict bounds.
`{X > 0, X =< 2}, bb_inf([X], X, I)` fails; it should give `I = 1`.
`_bb_solve` never looks at the disequalities, picks X = 0, and binding
the optimum then fails on `X =\= 0`.
