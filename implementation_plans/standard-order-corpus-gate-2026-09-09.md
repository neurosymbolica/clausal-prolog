# Corpus gate REQUEST — standard order of terms

**Status: NOT RUN. This gate cannot be executed in the engine repository.**

`find /workspace/clausal -name '*.clausal' -path '*corpus*'` returns nothing; the domain
files live on the other side of the information barrier. So this file is a REQUEST to a lane
that holds a corpus (a downstream user or a downstream user), not a result. Do not read a green
full-suite gate as corpus coverage — the suite does not contain downstream code and structurally
cannot see this class of change.

## What changed that needs measuring

Branch `feat/iso-standard-order-2026-09-09`, base `46712278` (clone and canonical main).

Two commits change `sort/2` and `msort/2` OUTPUT:

- `9a81d1c0` — the ISO 7.2.1 tiebreak. Equal-value numbers of different types are now
  distinct terms, so `sort/2` no longer DEDUPS them. `sort([1, 1.0, True])` returns three
  elements where it returned one. This closed audit finding A09-F022, which had been sitting
  as an xfail since July.
- `f0dbabb3` — the native fast path is now gated by exact type. Lists that previously took
  Python's own ordering may now take the key path, which orders compounds ARITY-FIRST per
  ISO rather than elementwise.

## The three categories, and which one blocks

Run downstream code at `46712278` and at this branch's tip, and diff. Sort every difference into:

**(a) equal-value int/float no longer collapsing in `sort/2`.** INTENDED. Report a count, not
a veto.

**(b) `Decimal(1)` no longer collapsing with `1`.** INTENDED, from the transitivity fix in
`2a423863`. Report a count.

**(c) anything else.** A BUG. This blocks landing outright — it means the order changed
somewhere the design did not intend.

## Two things that should IMPROVE, and are worth confirming

- `sort/2` and `msort/2` CRASHED on any list mixing dimensions, or mixing quantities with
  plain numbers: `Quantity.__lt__` raises `UnitsMismatch`, which is not a `TypeError`, so the
  old fast path's handler never fired and it escaped to the caller. If any corpus site was
  hitting that, it should now sort instead of raising.
- `sort/2` was INPUT-ORDER DEPENDENT for equal-value int/float — `[1, 1.0]` and `[1.0, 1]`
  each sorted to themselves. Any site whose output depended on input order there was
  unstable before and is deterministic now.

## Backing out

Each risk reverts independently:

- the tiebreak alone: revert `_NUMERIC_RANK` in `clausal/logic/builtins/_helpers.py` to a
  constant — one line, leaves Tasks 3-5 intact;
- the fast-path gate alone: revert `f0dbabb3`;
- the transitivity fix alone: revert `2a423863`.

The comparison predicates (`@<`, `@>`, `@=<`, `@>=`, `compare/3`, `'=..'`) are purely
additive and are not implicated by any corpus difference.
