# Sequence//1: Both S0 and S Unbound

**Status:** Working for all standard DCG usage. Incomplete for the
fully-relational edge case.

**Affects:** `Sequence//1` in `clausal/logic/builtins/dcg.py`

## Current Implementation

`Sequence(List, S0, S)` handles two cases:

1. **S0 bound** (normal DCG usage): check that S0 starts with List, bind S
   to the remainder.
2. **S bound**: compute S0 = List ++ S, unify.

It does **not** handle the case where both S0 and S are unbound — it silently
fails.

## When This Matters

In standard DCG usage via `phrase/2,3`, S0 is always bound (it's the input
list). The both-unbound case only arises in unusual meta-programming
scenarios where Sequence is called outside the normal DCG pipeline.

## Potential Fix

When both S0 and S are unbound, the relation `S0 = List ++ S` has infinitely
many solutions (S can be anything). The correct behavior would be to:

1. Create a fresh variable for S.
2. Compute `S0 = List ++ S` (as a list with a variable tail).
3. Unify S0 with the constructed list.

However, Clausal uses Python lists (not cons-cell difference lists), so
"list with a variable tail" isn't directly representable. This is a
fundamental limitation of the Python-list representation for difference lists.

## Priority

Very low. Standard DCG usage always has S0 bound.

## Files

- `clausal/logic/builtins/dcg.py` — `_sequence__3`
