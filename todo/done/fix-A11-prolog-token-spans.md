# fix(A11-F029/F037): tokens carry no source span — quoted functors and spaced minus misparse

- F029: `_is_functor_paren` (prolog_parser.py:390-398) reconstructs adjacency
  as `col + len(str(token.value))` — wrong for quoted atoms (quotes/escapes
  excluded): `'foo'(1).` → ParseError. ISO: `'foo'(1)` ≡ `foo(1)`.
- F037: prefix `-` + numeric literal folded to a negative literal REGARDLESS
  of adjacency (:253-257, :322-326) — `- 1` → PNumber(-1); ISO 6.3.1.2 says
  only adjacent `-1` is a literal. Breaks the emit→parse fixpoint (`-(1)`
  emits `- 1`).

**Fix**: record end position (or full span) on Token; use it for both
adjacency checks.

**Tests**: test_F029_quoted_functor, test_F037_spaced_minus_is_compound (xfail).
