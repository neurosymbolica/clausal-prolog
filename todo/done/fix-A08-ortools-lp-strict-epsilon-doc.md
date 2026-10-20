# fix(A08): document (or replace) the LP adapter's 1e-6 strict-inequality fudge

**Finding:** A08-F017 (design/doc-drift, low)

## Issue
`clportools_lp.py:346-354` compiles `x < c` as `x <= c - 1e-6` and `x > c` as
`x >= c + 1e-6` — a hard-coded absolute epsilon that is wrong for
small-magnitude models (cuts feasible points) and meaningless for large ones.
`ArithNeq` raises a bare `TypeError` with no explanation that LP cannot
express `!=`.

## Options
- Document the epsilon in the ortools docs page + a named constant.
- For integer vars, use exact `<= c-1` / `>= c+1`.
- Reject strict comparisons on continuous vars with a clear error message.

## Acceptance
Behaviour documented or replaced; error message for `!=` explains the LP
limitation.
