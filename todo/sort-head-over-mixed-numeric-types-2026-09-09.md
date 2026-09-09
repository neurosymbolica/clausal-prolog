# The at-risk shape for the ISO tiebreak: sort, then take the head

Filed 2026-09-09, after the ISO 7.2.1 float-before-int tiebreak landed in `ecd6bef1`.
No known instance in downstream code today. This records the SHAPE so the next person
does not have to rediscover it.

## The shape

    findall([M, ID], (...), PAIRS),
    sort(PAIRS, SORTED),
    SORTED is [[BEST_M, BEST_ID], *_]      % the answer IS the head

A predicate whose answer is the first element of a sorted list, keyed on a number,
where the numbers may not all share a numeric TYPE.

## Why it changed

Before `9a81d1c0`, equal-value numbers of different types had the SAME standard-order
key, so a tie on the first element fell through to the second and resolved by id.
ISO 7.2.1 says a float PRECEDES an int of equal value, so the first elements no longer
tie and the second element is never consulted.

    [8, ratio_b] vs [8.0, ratio_a]  ->  before: ratio_a (by id)    after: ratio_a (by rank)
    [8, ratio_a] vs [8.0, ratio_b]  ->  before: ratio_a (by id)    after: ratio_b (by rank)

The answer moves only when BOTH hold: a tie in value spanning two numeric types, AND
the float-typed entry has the later id. Nothing is raised and no type changes, so it
is silent.

## How the one candidate was cleared

The one candidate site found in a survey of downstream sort/msort/predsort/keysort
call sites (downstream survey, 2026-09-09) is immune BY CONSTRUCTION rather than by
test coverage: the arithmetic bottoms out in floor division over integer basis points
and an integer scale, so `int * int // int` is `int` in every case and all values
compared at that site share a type.

**The residual, stated honestly:** that immunity rests on a documented convention
that the inputs are integers in one minor currency unit — a comment in a data file,
not a type check. A caller passing a float amount for one entry and an int for
another could reach it.

## What to check if this shape appears again

Not "are the tests green" — that only covers the inputs the tests reach. Ask instead
whether the keys can differ in numeric TYPE at all. If they cannot, the site is immune
by construction and no test is needed. If they can, the site needs a tie-breaking rule
that does not depend on the standard order.

Related: [[a01-d001-tabling-half-2026-09-09]] and
`docs/superpowers/specs/2026-09-09-standard-order-of-terms-design.md` §4.
