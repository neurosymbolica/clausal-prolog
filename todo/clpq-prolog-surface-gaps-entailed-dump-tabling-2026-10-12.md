# CLP(Q) on the Prolog surfaces: four gaps on both solvers (2026-10-12)

Found by the CLP(Q) port's Task 14 integration review. All four reproduce with the legacy solver and
with the port, so they predate the port.

1. **FIXED 2026-10-20 (commit 55a37b9c)** the builtin reads a relation cell; pinned in
   tests/test_clpq_entailed_relation_cells.py::test_prolog_entailed_relation.
   **In .pl, `entailed(X > 0)` is always false.** The builtin (`builtins/constraints.py:268-285`)
   matches only node classes, and the Prolog front end passes it a `('>', X, 0)` tuple. The Python
   API `entailed('>', x, 0, t)` gives True.
2. **`maximize/1`, `minimize/1` and `dump/3` do not exist on the Prolog surfaces.**
   `dump([X], [x], C)` leaks `type_error(callable, <function dump at ...>)`.
3. **A tabled predicate loses its CLP(Q) constraints.** With `p(X) <- {X >= 1, X <= 5}` tabled,
   `(p(X), sup(X, S))` fails: the table copy drops the store.
4. **`in_q(X)` and `sup(X, S)` fail on an FD variable that has no Q state.** Promotion happens only
   when there are bounds.
