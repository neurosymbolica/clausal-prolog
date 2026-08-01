# A non-numeric operand vs a var *inside an expr tree* still posts silently

**Filed** 2026-08-01, flagged by roborev (job 269 on `e8024a6c`) and confirmed
by probe. **Status:** reproduced minimally, not fixed. Records the A12-F002
family sweep as incomplete:

| operand shape        | `==`      | `!=`      | `<` `=<` `>` `>=` |
|----------------------|-----------|-----------|-------------------|
| bare var vs ground   | guarded   | guarded   | guarded           |
| var inside expr tree | **open**  | **open**  | **open**          |

## The behaviour

The guards (`_reject_nonnumeric_eq` / `_reject_nonnumeric_order`) check only
the exactly-one-`Var` case. With the var one level down in an arithmetic
expression tree, both sides deref to non-Vars and the guard returns early:

```python
fd_eq(Add(left=X, right=1), "banana", trail)   # True — posts
unify(X, 5, trail)                             # True — 5+1 == "banana" "holds"
```

`_linearise("banana")` returns None, so `X + 1 == "banana"` falls through to
`EqConstraint(Add(X,1), "banana")`, and per the A06-F014 note a non-integer
atom reaching `_expr_domain`'s catch-all is treated as an unconstrained
integer — the string side is never enforced and answers are silently wrong
(worse than the bare-var case, which at least rejected everything). Confirmed
for `==`, `!=`, and `<`; reachable from user source via the compiler's
`fd_eq`/`fd_ne`/`fd_lt` lowering.

## Likely shape of the fix

Either walk expr-tree leaves in the two guards (reject when any *ground
non-tree side* of the comparison is non-`numbers.Real` while the other side
is/contains a var), or type-check `_expr_domain`'s catch-all so a non-integer
leaf raises instead of becoming an unconstrained integer. The second catches
strings *inside* trees too (`X + "a"`), the first is cheaper at post time;
check A06-F014's test expectations before choosing.

## Repro

Unit-level, as above — verified against clone main 2026-08-01 (post
`e8024a6c`, with the bare-var guards in place for all of `==`/`!=`/orderings).
