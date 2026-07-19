# Bare-query compilation globals miss injected builtins (latent NameError)

## STATUS: TODO (filed 2026-07-19; found during the Unknown-builtin work, 2026-07-17)

## What was found
`predicate_builtins` (clausal/import_hook.py, "Builtins injected into every predicate
module") seeds module namespaces with name-referenced runtime bindings: `Quantity`,
`PyThunk`, `BoolEq`, `BoolImpl`, `Var`, `Compound`, ... and now `Unknown`.

But the BARE-QUERY compilation path derives the compiled code's globals **only from
`module.module_dict`**, which does not necessarily carry those injections. During the
Unknown work this surfaced as a NameError when `Unknown` (emitted by
`term_to_ast_expr` as a bare `Name`) reached query compilation; the fix baked
`"Unknown": Unknown` unconditionally into BOTH `base_globals` dicts in
`clausal/logic/compiler/predicate.py` (`compile_predicate_trampoline` and
`compile_predicate_shallow` — see the comment at the trampoline-path entry).

`Unknown` is therefore covered, but the gap is GENERIC: any other injected builtin
referenced by NAME inside a query term (rather than appearing as an already-constructed
constant) can hit the same NameError in a bare query even though the same term compiles
fine inside a module clause.

## Task
1. Enumerate which `predicate_builtins` entries can legitimately appear as `Name` /
   `LoadName` references in compiled query/clause bodies (audit `term_to_ast_expr`
   emission cases + goal-expansion outputs).
2. Either bake those into `base_globals` like `Unknown`, or (cleaner) derive query
   globals as `predicate_builtins | module_dict` in one place so future injections
   can't regress.
3. Regression tests: a bare query referencing each such name (the Unknown test in
   `tests/test_unknown_builtin.py` shows the shape).

## Pointers
- clausal/import_hook.py — the injection block (~lines 212-250)
- clausal/logic/compiler/predicate.py — the two `base_globals` dicts + the
  "query path, whose globals derive only from the module dict" comment
- clausal/logic/compiler/terms_to_ast.py — `term_to_ast_expr` Name-emission cases
