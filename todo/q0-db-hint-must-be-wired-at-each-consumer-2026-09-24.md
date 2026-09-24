# The Q0 db= hint is additive — each consumer must pass its db as it migrates

**Filed:** 2026-09-24, with the Q0/X3 accessors (roborev Medium on that branch).

The era-agnostic resolvers (`resolve_predicate_row`, `is_declared_predicate`,
`is_declared_predicate_name`, `predicate_binding_name`,
`predicate_arities_for`, all via `_resolve_mangled_owner`) take an optional
`db=` — the CALLER's database — so a handle to a module the `.clausal` runner
popped from `sys.modules` still resolves locally (ruling Q0). When it landed,
NO production caller passed it; before the flip no predicate binding is a
handle, so nothing needed it. Likewise `mint_predicate_handle(db, functor)`
(ruling X3) had no production caller.

**This is a flip checklist item, not optional:** after the flip a resolver
call WITHOUT `db=` silently answers None for every local handle in a popped
test module (43/46 measured descents).

Wire at: F1 rows 58/59 (`_find_pred_cls`/`_namespace_dispatch`), row 60
(`_indicator_row`), and every flip-time call site in `compiler_v2`,
`database.py`, `io.py`, `seam.py`, `constants.py`, `import_diagnostics.py`,
`predicate_diagnostics.py` that has a db in scope (roborev listed them). The
flip itself mints bindings with `mint_predicate_handle`.

Check for done: `grep -rn "resolve_predicate_row\|is_declared_predicate\|predicate_binding_name\|predicate_arities_for" clausal` — every call with a db in scope passes it.
