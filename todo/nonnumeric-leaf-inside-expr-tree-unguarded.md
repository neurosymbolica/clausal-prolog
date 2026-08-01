# A non-numeric leaf *inside* an expr tree still posts silently

**Filed** 2026-08-01, the deliberately-unfixed residue of
todo/nonnumeric-operand-vs-var-inside-expr-tree-unguarded.md (fixed for the
operand-vs-tree case). **Status:** reproduced, not fixed.

## The behaviour

The guards now catch a ground non-numeric on the *other side* of a
var-containing tree (`X + 1 == "banana"` raises). But garbage as a *leaf of
the tree itself* still slips through:

```python
fd_eq(Add(left=X, right="a"), 5, trail)   # True — posts
```

`_linearise` fails on the string leaf, execution falls to
`EqConstraint(Add(X, "a"), 5)`, and the `_expr_domain` catch-all treats the
string as an unconstrained integer (the A06-F014 note) — silently wrong
answers. Same for `!=` and the orderings.

## Why it was not fixed alongside the operand case

Rejecting every ground non-`numbers.Real` leaf during the guard's tree walk
was considered and deliberately not done: it is not established that all
non-Real leaves in constraint-position trees are illegal (e.g. Quantity
leaves in units arithmetic — `X == Amount * 2` with a ground Quantity — have
no test coverage either way, and `_eval_ground`/Quantity `__mul__` do handle
them outside constraint position). Blanket leaf rejection could outlaw
currently-working tree shapes. The safer fix shape is option 2 from the
parent todo: type-check `_expr_domain`'s catch-all (and the equivalent C-side
path) so an unknown leaf raises instead of becoming an unconstrained integer
— that is enforcement at the point where the "unconstrained integer"
assumption is actually made. Decide leaf legality (esp. Quantity/Decimal
leaves) before implementing; A06-F014's sum_/scalar_product precedent
(`_is_fd_sum_element`) rejects non-integer elements up front.

## Repro

Unit-level, as above — verified against clone main 2026-08-01 (with the
operand-vs-tree guards in place).
