# A non-numeric comparison on an unbound var succeeds, then rejects every later binding

**Filed** 2026-08-01, found while documenting residual comparison semantics for the
corpus cheatsheet. **Status:** reproduced minimally, not fixed.

## The behaviour

Numeric comparisons on an unbound var are sound residual constraints:
`X > 3, X == 10` → 1 solution; `X > 3, X == 2` → 0. Correct CLP semantics.

String comparisons are not. `X < "banana"` with unbound `X` **succeeds** (1 solution,
`X` left an AttVar with `attrs={}`), but the posted state then rejects **every** later
binding — including ones that satisfy the comparison:

```clausal
strlt_ok(X)  <- ( X < "banana", X is "apple" )   # 0 solutions — WRONG, "apple" < "banana"
strlt_bad(X) <- ( X < "banana", X is "zebra" )   # 0 solutions — right answer, wrong reason
```

So a rulebase that compares a not-yet-bound var against a string silently loses all
solutions, with no diagnostic. Same defect shape as A12-F002 (`fd_eq` posting an FD eq
against a ground non-numeric made "a broken var — one that equals anything EXCEPT the
operand"); `fd_eq` got `_reject_nonnumeric_eq` for it, but the ordering comparators
(`fd_lt`/`fd_le`/`fd_gt`/`fd_ge`) apparently did not get the equivalent guard.

## Likely shape of the fix

Mirror A12-F002 in the ordering comparators: a ground non-numeric operand against a var
is a catchable type error (or, if string ordering constraints are wanted someday, a real
constraint — but the current half-state is the worst option). Check the date/Quantity
comparison paths for the same hole while there.

## Repro

`/tmp/shadowbug/strcmp2.clausal` (rebuilt in seconds; source above). Verified against
clone main 2026-08-01 (post `3c49283a`).
