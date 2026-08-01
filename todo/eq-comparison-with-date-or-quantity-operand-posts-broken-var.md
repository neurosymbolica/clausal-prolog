# `X == <date|Quantity>` succeeds, then rejects every later binding — even the equal one

**Filed** 2026-08-01, found while fixing
todo/nonnumeric-comparison-on-unbound-var-rejects-all-later-bindings.md (the
ordering-comparator sibling of this defect). **Status:** reproduced minimally,
not fixed.

## The behaviour

The A12-F002 guard (`_reject_nonnumeric_eq`) rejects atoms, strings,
collections and ground compounds as `==` operands against an unbound var. Its
docstring says "Numbers, Quantities, rationals/reals … all pass" — but for
dates and Quantities "passing" means posting an `EqConstraint` that the FD
unification hook then enforces as *integers only*, so the var rejects **every**
later binding, including the equal one:

```python
fd_eq(X, date(2026, 6, 1), trail)          # True
unify(X, date(2026, 6, 1), trail)          # False — same value!

fd_eq(Y, Quantity(5, {Metre: 1}), trail)   # True
unify(Y, Quantity(5, {Metre: 1}), trail)   # False — same value!
```

Same broken-var shape as A12-F002/this fix's ordering case, just a gap in the
existing guard's blocklist rather than a missing guard.

## Design question (parked, per convention)

What *should* `X == 5*metre` / `X == date(...)` mean?

1. **Catchable type error** — extend `_reject_nonnumeric_eq` to reject any
   ground non-`numbers.Real` operand (mirrors the allowlist the ordering
   guard now uses). Simplest; consistent; but contradicts the docstring's
   stated intent that Quantities pass.
2. **Bind/test like unification** — `==` on a ground Quantity/date operand
   degenerates to `is`-style unification (bind if var, compare if ground).
   Matches user intuition for money rulebases (`Amount == usd(100)`), but
   `==` is documented as *arithmetic* equality, and Quantity arithmetic
   (CLP over the scalar value + units check) is real feature work.
3. **Real residual constraint** — CLP over the Quantity's scalar with a units
   guard. Most work; only worth it if corpus rulebases need it.

The ordering comparators chose option 1 (`type_error(orderable, …)`); doing
the same here (with `evaluable`, matching the existing `==` guard's error
shape) keeps `==`/`<` consistent until someone wants option 2/3.

## Repro

Unit-level, as above — `fd_eq` from `clausal.logic.clpfd`, verified against
clone main 2026-08-01 (post `062a3d56`, with the ordering fix applied).
