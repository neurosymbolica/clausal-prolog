# clausal-sympy: package-suite failures triaged (2026-10-04)

**Status: FIXED 2026-10-04 (commit d9980c58).** Fixtures and docs use `sym_equal/2`; ruled the same day with no engine change: `==` on a SymPy result is arithmetic and raises `domain_error(clpz_expression, _)`. Pinned in packages/clausal-sympy/tests/test_sympy_equality_is_arithmetic.py (the package suite: 228 passed).

Box run on 1c5ee5a0: **52 failed**. After feat/package-followups-2026-10-04:
**0 failed**.

| Group | Class | Count | Representative node id | Status |
|---|---|---|---|---|
| `R == <expr>` with `R` a SymPy result: `==` in a goal is arithmetic and raises `domain_error(clpz_expression, Expr)` instead of deferring to `SymExpr.__eq__` | ENGINE-SEMANTICS DRIFT | 52 | `packages/clausal-sympy/tests/fixtures/docs/sympy_sig_tests.seam::symbolic equality via ==` | fixed: fixtures + docs use the package's `sym_equal/2`; numeric `R == 0` and `sym_str` text compares keep `==` |

Remaining failures: none.

Needs a ruling (not done, would be an ENGINE change): should `==` with a
non-numeric Python operand that defines `__eq__` (SymExpr) defer to it, as
the package docs promised, instead of raising `domain_error`? The branch
takes the package-side route (sym_equal/2) and rewrites the docs section.
