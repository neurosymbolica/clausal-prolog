# fix(A08): CLP(R) `_imod` interval is integer-only — unsound for real operands

**Finding:** A08-F009 (correctness, high) — both `clpr.py:_imod_py` and `_clpr_core.c:py_imod`
**Tests:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestClprModInterval` (4 xfails)

## Bug
`_imod` returns `[0, |b|max - 1]` (resp. negated) — an integer-modulo bound.
For float `%`:
- real numerators: `1.5 % 2 = 1.5` lies outside `[0, 1]` -> true constraints
  fail (violates the documented outward-rounding soundness guarantee);
- `|b| < 1`: upper bound `|b|-1 < 0` gives an inverted/EMPTY interval -> every
  `X % 0.5` constraint fails at posting.

## Fix sketch
Python float `%` satisfies: result in `[0, b)` for `b > 0` and `(b, 0]` for
`b < 0` (sign of divisor). Correct sound hull for `b` in `[blo, bhi]`, `b > 0`:
`[0, _up(bhi)]` (use bhi itself, not bhi-1; the half-open bound may be kept
closed for soundness). Negative divisor: `[_dn(blo), 0]`. Mixed-sign divisor
interval already returns (-inf, inf). Fix both the C function and the Python
fallback and keep them identical.

## Acceptance
The four xfail tests flip to pass; `tests/test_clpr.py` stays green.
