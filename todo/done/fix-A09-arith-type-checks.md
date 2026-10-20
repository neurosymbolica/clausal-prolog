# fix(A09-F011): plus/3, max_/3, min_/3 lack numeric type checks

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F011
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F011_plus_string_concat, ::test_F011_plus_mixed_raw_typeerror, ::test_F011_max_strings (xfail — flip to pass)
**Gated by:** A09-D002 (error convention); bool half is A09-F015/A01-D001.

## Bug

`_plus__3_py` (arithmetic.py:156-183) and `_max__3_py`/`_min__3_py` (199-227)
apply Python `+`/`-`/`max` with NO `_is_numeric` guard (every sibling —
abs_, sign, gcd, succ — has one): `plus("a","b",Z)` → Z="ab" (docstring says
numeric; silently wrong domain), `plus([1],[2],Z)` → [1,2], and mixed types
leak a RAW TypeError through the query (uncatchable by catch/3). The C paths
return False (fall back to Python) for non-ints, so the Python guard is the
single fix point.

## Fix direction

Add the `_is_numeric` (int/float/Quantity, not bool) guard to all three, in
every mode (including the subtraction modes of plus). Out-of-domain → fail
(or typed type_error per A09-D002 outcome — follow the convention decision).

## Acceptance

- Three xfails pass; Quantity modes still work; no raw TypeError escapes.
