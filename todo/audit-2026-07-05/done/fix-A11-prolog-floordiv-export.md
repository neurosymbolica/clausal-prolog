# fix(A11-F031): Clausal // (floor) exported as Prolog // (truncating)

`clausal_to_prolog.py:787-802` maps python_ast.FloorDiv → `"//"`. For
`A=-7, B=2`: Python floor-div −4, ISO/SWI `//` −3 — silent semantics flip.
Asymmetric with the forward direction, which routes `//` through
prolog.TruncDiv for exactly this reason. (Python `%` → `mod` is correct —
both floored.)

**Fix** (A11-D009): emit `div` (SWI/Scryer floored division) or
`(A - A mod B) // B` per dialect.

**Test**: test_F031_floordiv_export_semantics (xfail).
