# A brace term held as data is a set literal in the seam and the translator, so it cannot be meta-called as a CLP(Q) block

Found 2026-11-03, closing todo/done/brace-goal-is-not-callable-2026-10-11.md
(which fixed the native front end). Needs a ruling.

## What

In the seam, `{C1, C2}` in goal position is a CLP(Q) constraint set
(operator ruling 2026-09-30), but in DATA position it is a set
(`SetTerm`), and a set of comparison nodes cannot be built:

    t(X) <- (G is {X > 1}, call(G), X is 2)     ->  TypeError: unhashable type: 'Gt'

The legacy `.pl` translator (`CLAUSAL_PL_FRONTEND=translator`) emits a data
`{...}` as that seam set literal, so on that front end:

    t(X) :- G = {X > 1, X < 3}, call(G), X = 2.   ->  TypeError: unhashable type: 'Gt'
    t(L) :- findall(X, (G = {X = 2}, call(G)), L). ->  TypeError: unhashable type: 'Unify'
    t(X) :- call({}, (X >= 1, X =< 1)).            ->  type_error(callable, {}) (the empty dict)

Scryer (library(clpq) loaded) answers `X = 2`, `L = [2]`, `X = 1`.

The seam's own held form works today: `G is clpq.rational(X > 1), call(G)`
posts (both solvers).

## Options

1. Leave it: the seam's held form is `clpq.rational(C)`; the translator is
   legacy. At least turn the `TypeError` into a load or ISO error naming
   the problem.
2. The translator emits a data-position `{C}` as the cell `'{}'(C)` when
   library(clpq) is imported, and imports `{}/1` from
   `clausal.stdlib.clpq_braces` (the seam's `-import_from` cannot name
   `{}` today: "import list items must be names").
3. The seam reads a data-position set of comparisons as a CLP(Q) block
   term: a change to the 2026-09-30 ruling ("a set in data position is
   still a set").
