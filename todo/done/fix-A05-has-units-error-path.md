# fix-A05: has_units/2 raises instead of failing on bad 2nd arg (A05-F005)

**Severity: correctness (error-path).** `_has_units`
(`clausal/logic/units_constraint.py:101-120`) reads `unit_pred._dims`
unguarded (`:111`). Its docstring promises "anything else → fail", but
`has_units(D, "meters")` (or any non-units-predicate 2nd arg) raises
`AttributeError` and aborts the query instead of failing.

## Fix

```python
dims = getattr(unit_pred, "_dims", None)
if dims is None:
    return
```

(covers both "not a units predicate" and the existing
`unit_pred._dims is None` guard in one step).

## Verify

Flip `TestF005HasUnitsErrorPath::test_has_units_bad_arg_fails_cleanly`
xfail to a plain assert; the 5 units-hook controls must stay green.
