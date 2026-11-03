# CLP(Q) on the Prolog surfaces: four gaps on both solvers (2026-10-12)

**Status: FIXED 2026-11-03 (commit b4d1c592).** All four items are fixed; the pinning tests are
named under each.

Found by the CLP(Q) port's Task 14 integration review. All four reproduce with the legacy solver and
with the port, so they predate the port.

1. **FIXED 2026-10-20 (commit 55a37b9c)** the builtin reads a relation cell; pinned in
   tests/test_clpq_entailed_relation_cells.py::test_prolog_entailed_relation.
   **In .pl, `entailed(X > 0)` is always false.** The builtin (`builtins/constraints.py:268-285`)
   matches only node classes, and the Prolog front end passes it a `('>', X, 0)` tuple. The Python
   API `entailed('>', x, 0, t)` gives True.
2. **FIXED 2026-10-22 (commit 3dead4ac)** the three are builtins on both solvers; pinned in
   tests/test_clpq_prolog_surface_builtins.py (see also
   todo/done/clpq-port-vs-sicstus-manual-23-gaps-2026-10-16.md items 2 and 3).
   **`maximize/1`, `minimize/1` and `dump/3` do not exist on the Prolog surfaces.**
   `dump([X], [x], C)` leaks `type_error(callable, <function dump at ...>)`.
3. **FIXED 2026-11-03 (commit b4d1c592)** a tabled answer is stored with its CLP(Q) residue (the
   selected solver's dump/3 projection onto its variables) and every replay re-posts it
   (`TableEntry.unify_row`); pinned in tests/test_clpq_tabled_answers.py (.pl, .clausal and seam,
   both solvers). Still open, in todo/tabled-answers-drop-their-constraints-on-replay-2026-07-05.md:
   dif/freeze/CLP(FD) residues, and the D68 live hand-over of constrained answers.
   **A tabled predicate loses its CLP(Q) constraints.** With `p(X) <- {X >= 1, X <= 5}` tabled,
   `(p(X), sup(X, S))` fails: the table copy drops the store.
4. **FIXED 2026-11-03 (commit b4d1c592)** in_q/1,3 and the objectives of sup/inf/maximize/
   minimize/bb_inf promote an FD variable first, on both solvers (DEVIATIONS.md D26); pinned in
   tests/test_clpq_fd_promotion_optima.py. Precisely: in_q(X) succeeded but gave X no bounds,
   so a later sup/2 failed; in_q(X, 0, 20) ignored the FD bounds; sup/inf did not promote at all.
   **`in_q(X)` and `sup(X, S)` fail on an FD variable that has no Q state.** Promotion happens only
   when there are bounds.
