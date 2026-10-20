# fix(A10-F001): .pl importer emits dead `Cut()` goal for body-position `!` instead of rejecting

**Problem.** `prolog_to_clausal._emit_goal` (clausal/tools/prolog_to_clausal.py:271-273)
has an early branch `! → "Cut()"` that preempts the intended rejection in
`_emit_atom` (:533). A `.pl` file with a body cut loads cleanly; the first
query dies with `KeyError: Predicate Cut/0 not found`. Violates the cut-free
standing contract and `docs/import.md`'s promised
`SyntaxError: Cut (!/0) cannot be translated to Clausal.` Term-position cuts
(`f(!)`) DO get the clear error — only the common body-goal case leaks.

**Repro/test.** `tests/audit_2026_07_05/test_10_rewriting_import.py::test_F001_pl_cut_rejected_at_import`
(xfail strict=False).

**Fix.** In `_emit_goal`, replace the `return "Cut()"` branch with the same
`PrologTranslationError` raised by `_emit_atom` (reuse the message). Check
`git log` for whether `Cut()` was a deliberate placeholder for a planned
builtin; no `Cut` predicate exists anywhere in-tree today. Note the module
docstring (:41) already says cut is "intentionally" rejected.

**Scope note.** File is formally outside A10's stay-within list (translator);
reached via A10's PrologLoader. Coordinate with A12 dedupe.
