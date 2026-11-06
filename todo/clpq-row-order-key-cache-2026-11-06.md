# CLP(Q) port: keep each row's order keys beside its terms

**Date:** 2026-11-06.  **Status: open, an idea; not started.**  The D24
chain-unification floor was accepted (operator ruling 2026-11-06,
DEVIATIONS.md D24, Low 8); this is the next step if it is ever wanted.

## Why

Unifying `X1 =< ... =< Xn` with `n` constrained `Yi` runs 1.3.3's back
substitution: n(n - 1) rows rewritten, about n^3/3 terms read.  With the
loops in C (`clausal/logic/clpq/_linear_forms_core.c`) each term costs
about 100 ns, nearly all of it `order_key(variable)`: the variable's
attribute dictionary, its `SolverState`, the order variable, each a cache
miss.  The port is 4.6 times legacy at n = 200 and 5.6 times at n = 400.

## The idea

A merge already knows every output term's order key (it compared them).
Keep them on the new row (`LinearForm.keys`, a list beside `terms`), so
the next merge, coefficient scan or substitution reads keys from one
contiguous list and touches no variable.  Expected: the per-term cost
falls to a few ns, near legacy at n = 400 (the term work is still n^3).

## The hazards (why it is not done)

A cached key is stale whenever the key `order_key` would return now
differs from the one recorded.  That happens when:

1. **An order value is bound.**  project.pl's `order/3`
   (`projection.variable_order`) binds unbound order values to
   integers: every key `(0, id)` of that variable becomes `(1, n)`, in
   every row that holds it.  `arrange/2` then re-sorts the rows
   (`renormalize_all`), but rows outside the arranged component, and rows
   on the trail, keep their old keys.
2. **A state loses its order.**  `projection._drop_linear` sets
   `variable_order=None`: `order_key` becomes None, and a merge that
   reached it must fail (return None), which a cached key would not.
3. **Backtracking undoes either.**  The trail restores the attribute or
   unbinds the order variable, but a row made after the change and kept
   (a row the undo puts back was made before it, so its keys are older
   still) holds keys of the undone world.  Undo must invalidate too: a
   global epoch bumped on every order binding and every `variable_order`
   change, and bumped again by a `trail.record` callback when either is
   undone, with each row's keys stamped by the epoch they were read in.
4. **A variable is bound.**  The D3 stand-in carries the bound
   variable's `variable_order`, so its key is unchanged, but any path
   that leaves a bound variable in a row (none known; CHECK_ROW_INDEX
   checks the row index for the same thing) would read a key the
   variable no longer has.
5. **Order values that are not ints.**  A key `(1, value)` compares by
   `value`'s `__eq__`/`__lt__`, which may run Python code; a cached key
   must keep the same object, not a copy, so comparisons stay Python's.

## Acceptance

The differential corpus unchanged (`CLPQ_DIFFERENTIAL=full`, 14 passed);
a check mode (like `CLAUSAL_CLPQ_CHECK_ROW_INDEX`) that recomputes every
cached key and raises on a mismatch, with tests/clpq_port passing under
it; tests for each hazard above (projection with `ordering/1`, dump/3
then more posts, backtracking across `order/3` and `_drop_linear`); the
D24 probe measured before and after.
