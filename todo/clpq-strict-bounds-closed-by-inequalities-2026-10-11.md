# CLP(Q): a strict bound closed by an inequality is not caught

A strict `<` is stored as `=<` plus a disequality (`X - Y =\= 0`).  The
disequality is checked in three ways:

- cheaply, after every change, once every variable in it is fixed;
- by entailment (an LP for the minimum and maximum of its expression),
  when a variable in it is bound;
- by entailment, after a posted equality.

It is not checked after an inequality, a new disequality or `in_q/3`,
since that cost two LPs per open disequality on every post: a chain of
200 `<` posts took over three minutes.  So these succeed although no
solution exists, and are only caught later, when a variable is bound:

    {X < Y, X >= 3, Y =< 3}
    {X < Y}, in_q(X, 3, 10), in_q(Y, 0, 3)

A z3 fuzz (2026-10-11) counted 88 such stores in 9,000; none wrongly
failed.  On the parent of this series, 667 of 1,500 were wrong.

Related, and older: `entailed/2` ignores disequalities.  After `{X < Y}`,
neither `entailed(X < Y)` nor `entailed(X =\= Y)` holds.

The general fix is strict bounds inside the simplex.  SMT solvers do this
with delta-rationals (Dutertre and de Moura): a strict bound `x < c` is
`x =< c - d` for a symbolic infinitesimal `d`.  Feasibility then decides
strictness on every post, with no LPs.  Holzbaur's CLP(Q) keeps a
strictness flag on each bound to the same end.

Cost note: labeling a 200-variable `<` chain now takes about 6 s, because
of two LPs per binding per disequality it touches.  The parent of this
series could not label such a chain at all (it failed).
