# fix(A10-F009): CompareChain goals produced by TermTransformer are uncompilable

**Problem.** `TermTransformer.visit_Compare` (term_rewriting.py:706-719) lowers
`0 < X < 10` to a `CompareChain` node, whose docstring promises "each
intermediate operand is evaluated only once" — but the goal lowerer
(`terms_to_goalop`, A03) has no CompareChain case, so any clause body using a
chained comparison fails module load with a raw
`NotImplementedError: terms_to_goalop: goal shape not yet supported (CompareChain)`.
No docs mention chained comparisons either way.

**Repro/test.** test_10_rewriting_import.py::test_F009_compare_chain_goal
(xfail); guard ::test_F009_guard_single_comparisons.

**Fix (either):**
1. Support it: lower `CompareChain([c1, c2, …])` to `And(c1, And(c2, …))` —
   operand sharing is already by Var identity, so single-evaluation holds for
   free. Cheapest done at goal-expansion or terms_to_goalop level (A03 seam).
2. Reject it early: raise SyntaxError("chained comparisons are not supported;
   split into conjuncts") in `visit_Compare` — but (1) is barely more work and
   matches the node's documented intent.
