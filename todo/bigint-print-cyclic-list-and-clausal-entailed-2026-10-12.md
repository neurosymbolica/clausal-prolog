# Shared-code edges found by the CLP(Q) port's final reviews (2026-10-12; legacy behaves the same)

1. **Integers past CPython's 4300-digit str limit.** `render_error_term` (`exceptions.py:141`) and
   the CLI answer printer call `str(int)`, so an error whose culprit is a larger integer, or any
   answer binding one, raises ValueError. Examples: `X is 10^5000, msort(X, L)`, or `X is 10^5000`
   alone at `-g`. Route these through the Decimal path that chars.py already uses.
2. **A cyclic list raises RecursionError.** `terms.py:666` (`_proper_list`, "cyclic partial list")
   reaches it from length/2, dump_q and bb_inf. ISO wants type_error(list, L) or failure.
3. **API-only cyclic AST nodes raise RecursionError.** clpfd's `_arith_cells_to_nodes` does not
   check Pow, IsoPow, FloorDiv or IsoRdiv for cycles: `x = Add(1, Pow(x, 2)); q_ge(V, x)` raises
   RecursionError. The surface builds cells, which are checked.
4. **FIXED 2026-10-20 (commit 273e4d58)** the builtin reads a relation cell; pinned in
   tests/test_clpq_entailed_relation_cells.py::test_clausal_program_under_each_solver.
   **`entailed/1` in .clausal always answers false, on both solvers.** The builtin
   (`constraints.py:269`) matches AST nodes, but the argument arrives as a cell. This is the same
   family as the .pl `entailed` gap in todo/clpq-prolog-surface-gaps-entailed-dump-tabling-2026-10-12.md.
