# Legacy CLP(Q): a `=\=` that inequalities alone close is accepted until the next binding

Found 2026-10-28, while moving legacy's strict bounds into the simplex
(todo/done/clpq-strict-bounds-closed-by-inequalities-2026-10-11.md).  Low
severity: the store is caught at the next binding, and a strict `<` is no
longer affected (it is a strict bound now, decided on every post).

## Repro

    {X =\= Y}, {X =< Y}, {Y =< X}

succeeds on the default solver; `CLAUSAL_CLPQ=holzbaur` fails it, as
clp(q,r) does.  `X = 1` afterwards fails on legacy, as it should.

## Why

A `=\=` stays a passive disequality.  After a binding or an equality every
open one is checked by entailment (an LP for the minimum and the maximum
of its expression, screened by the current assignment); after an
inequality only when its variables are fixed, or when the store's
equalities alone decide it.  Checking each one by entailment after every
inequality cost two LPs per open disequality per post (todo/done/
clpq-strict-bounds-closed-by-inequalities-2026-10-11.md: a chain of 200
posts took minutes).

## Candidates

Detect implied equalities after an inequality (a variable or slack whose
bounds the simplex can prove tight), as clp(q,r) does, and run the
entailment check only for the disequalities over the expressions that
became fixed.
