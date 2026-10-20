# fix-A01: terms.__all__ omits public names (A01-F011, doc-drift)

`clausal/terms.py:2220-2260` — `__all__` exports `SegString` and `SegBytes`
but not `SegList`, and omits `ConcreteSeg`, `VarSeg`, `Quantity`,
`UnitsMismatch`, and `PartialTermError`, all of which are public API:
`PartialTermError` is the documented catchable exception for partial-Seg*
operations (its own docstring tells callers to catch it), `Quantity`/
`UnitsMismatch` are the units feature's surface, and Seg* construction needs
`ConcreteSeg`/`VarSeg`.

## Fix

Add the six names to `__all__` (keep grouping comments consistent).
Double-check nothing intentionally private is implied by the omission —
`SegList` being absent while `SegString`/`SegBytes` are present reads as
drift, not policy (git blame if in doubt).

## Verify

Flip `TestF011AllExports::test_public_term_types_exported`.
