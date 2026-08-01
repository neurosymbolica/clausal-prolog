# `X != <non-numeric>` succeeds, then rejects every later binding

**Filed** 2026-08-01, flagged by roborev (job 266 on `4bbc85d8`, the
ordering-comparator fix) and confirmed by probe. **Status:** reproduced
minimally, not fixed. Completes the sweep of the A12-F002 defect family:
`==` guarded (with a date/Quantity gap, see
todo/eq-comparison-with-date-or-quantity-operand-posts-broken-var.md),
`<`/`=<`/`>`/`>=` guarded by `_reject_nonnumeric_order`, `!=` never guarded.

## The behaviour

```python
fd_ne(X, "banana", trail)   # True — posts NeConstraint(X, "banana")
unify(X, "apple", trail)    # False — every non-integer binding rejected
```

So `X != "banana", X is "apple"` silently loses its solution. User-level
`!=` compiles to `fd_ne` (`terms_to_goalop.py`, `nodes.ArithNeq`), so this is
reachable from rulebases. Note two extra wrinkles the ordering fix did not
have:

- Under `_USE_C_PROPAGATE`, `fd_ne` is bound **raw** to the C impl
  (`fd_ne = _c_fd_ne`) with no Python wrapper, so there is currently no seam
  where a guard runs — fixing it means adding a wrapper like `fd_lt`/`fd_le`
  got.
- `fd_ne` also has no ground-incomparable `except TypeError` conversion the
  way `fd_lt`/`fd_le` do; check whether ground `!=` needs one while there.

## Design question (parked, per convention)

`!=` is *arithmetic* disequality and `dif/2` (structural disequality,
`nodes.DoesNotUnify`) already exists for the general case. So the consistent
treatment is the same guard the other comparators got: exactly-one-var with a
ground non-`numbers.Real` operand raises a catchable type error. Open
choices: `evaluable` (matching `==`, both being arithmetic (in)equality) vs
`orderable` (matching the ordering guard) for the error kind, and the context
name for `!=` (`"(=/=)/2"`?  check what the codebase already calls it in
diagnostics). Alternatively `!=` against a non-numeric could degenerate to
`dif` — but that contradicts `==`'s type-error precedent for atoms/strings.

## Repro

Unit-level, as above — `fd_ne` from `clausal.logic.clpfd`, verified against
clone main 2026-08-01 (post `4bbc85d8`).
