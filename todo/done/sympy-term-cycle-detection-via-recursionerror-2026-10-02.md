# sympy_term/2: cycle detection by catching RecursionError is imprecise

Filed 2026-10-02, from the last review round on the clausal-sympy `sympy_term/2` merge.

`sympy_term(S, X+1), X = S` builds a cyclic binding that the engine's occurs check does not see,
because the cycle passes through a SymPy object. Following the dereference then recursed without
bound. The fix landed with the merge catches `RecursionError` and turns it into `ValueError`:
`sympy_term/2` raises `type_error(sympy_expression, _)`, and the other sympy predicates fail.

Open (Low):
- The detection is imprecise. It costs ~1000 frames before it fires, gives a false positive on a
  long ACYCLIC chain of tagged expressions, and would hide a genuine SymPy-internal
  `RecursionError` under the same error. A visited-set walk in `_detag_vars` / `_untag_vars`
  would be exact.
- No test covers the cyclic case through `sympy_term/2`'s own Term -> Sympy direction (only
  through `simplify/2`), so the documented `type_error(sympy_expression, _)` there is unverified.

**Status: FIXED 2026-11-04 (branch t4-sympy-safety).** `_to_sympy_ctx` tracks the Vars on its
current path and raises `_CyclicTerm` (a `ValueError`) at the first repeat; the `RecursionError`
catch is gone. This also covers the plain cycle `X = f(X)`, which used to throw
`resource_error(stack)`. Pinned by `TestCyclicTerms` in
`packages/clausal-sympy/tests/test_sympy_module.py`, which includes the Term -> Sympy direction
and a 60-deep acyclic tag chain. Whether a plain cycle should instead keep `resource_error` is
with the operator.
