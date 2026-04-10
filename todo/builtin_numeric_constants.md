# Builtin Numeric Constants

IEEE 754 and mathematical constants should be Clausal builtins, not
scattered across library wrappers.

## Constants to add

- `nan` — IEEE 754 NaN (`float('nan')`)
- `inf` — IEEE 754 positive infinity (`float('inf')`)
- `neg_inf` — IEEE 754 negative infinity (`float('-inf')`)
- `pi` — 3.14159... (`math.pi`)
- `e` — 2.71828... (`math.e`)

## Current state

- `nan`, `inf`, `neg_inf` are exported from `py.torch` via `__getattr__`
- `pi` is exported from `py.scipy_constants`
- None are available as builtins

## Why builtins

These are as fundamental as `True`/`False`. Any numeric code might need
them — pure Clausal arithmetic, scipy, torch, sympy. Requiring a library
import for `nan` is wrong.

## Once added

- Remove `nan`/`inf`/`neg_inf` from `py.torch`'s export list
- Remove `pi` from `py.scipy_constants` (or keep as alias)
- Update docs and tests to use bare constants
