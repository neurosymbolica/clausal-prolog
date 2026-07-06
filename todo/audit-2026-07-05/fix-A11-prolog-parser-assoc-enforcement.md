# fix(A11-F028/F038): parser never enforces xfx/left-precedence; op(0) doesn't remove

- F028: `_left_prec` (prolog_parser.py:342-347) is dead code; the Pratt loop
  (:150-189) accepts `a = b = c`, `2 ** 3 ** 2` (invented left-assoc; SWI:
  syntax error) and misclassifies `x :- y :- z.` as a clause whose HEAD is
  `:-(x,y)`. docs/prolog_translation.md claims "correctly resolves all
  associativity specifiers".
- F038: `:- op(0, xfx, ===)` stores a precedence-0 entry instead of REMOVING
  the operator (ISO 8.14.3.4) — `a === b.` still parses.

**Fix**: wire `_left_prec` into the loop (reject when left operand's priority
exceeds the operator's left-argument max); make define(0, …) delete the entry.

**Tests**: test_F028_xfx_not_chainable, test_F038_op_zero_removes (xfail).
