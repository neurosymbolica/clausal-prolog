# A ground `Seg*` keys in the opaque standard-order band

Filed 2026-09-07 by the Task 15 fix-round-1 ledger (deferred there, not
fixed).

`_standard_order_key` (`clausal/logic/builtins/_helpers.py`) has no `Seg*`
branch, so a `SegString` / `SegList` / `SegBytes` falls off the end into
`(_ORD_OTHER, _OpaqueOrder(term))` — ordered by type name, then by the
value's own `<`, then by `repr`.

Every type check next door walks it first (`normalize_seg_input`) and
answers for what it walks to: a ground `SegString(["ab"])` is `string`,
`is_list`, `is_chars` and — since Task 15 item 2 — `compound`, exactly as
the equal `"ab"` is. The ORDER does not follow: `msort(["ab",
SegString(["ab"])], L)` puts them in different bands, and `sort/2` does not
dedup them, though they are one term.

## Fix shape

Walk at the top of `_standard_order_key`, next to the `deref`:
`term = normalize_seg_input(deref(term))`. A ground `Seg*` then keys as the
`str`/`list` it walks to and everything follows; a NON-ground one still has
no key better than the opaque band (it holds unbound variables, so it is
not a ground term at all — arguably it should key in the var band by its
first hole, which is a separate question).

## Why it was deferred

The walk costs a call per element per comparison key, and every `sort/2`,
`msort/2`, `setof/3` and `*_by` pays it whether or not a `Seg*` is present.
No in-tree caller sorts `Seg*` values — they are a runtime unification
shape, not something a program builds and sorts — so the cost is certain
and the benefit is not. Measure before adopting: the cheap version is a
`isinstance(term, (SegList, SegString, SegBytes))` guard immediately before
the opaque fallthrough, which pays nothing on the common paths.

## Fixed 2026-09-26 (dumb-seam step (b), branch feat/dumb-seam-step-a-b-2026-09-26)

The cheap version: an ``isinstance(term, (SegList, SegString, SegBytes))``
guard immediately before the opaque fallthrough in what is now the public
``clausal.term_key`` (``_standard_order_key`` kept as the in-tree alias).
A ground ``Seg*`` is walked with ``walk_seg`` (keeps the chars carrier, so a
text Seg* keys as its char list, never as an atom) and keyed as the term it
walks to; a non-ground one keeps the opaque band.  No cost on any other
path.  Tests: ``tests/test_public_converters.py`` (``sort/2`` now says a
ground ``SegString(["ab"])`` and ``"ab"`` are one term).
