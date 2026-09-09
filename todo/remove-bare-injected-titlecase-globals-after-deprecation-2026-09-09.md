# Remove the bare TitleCase runtime aliases after the deprecation window

Opened: 2026-09-09, alongside `feat/dollar-prefix-injected-runtime-names-2026-09-09`.

## Ruling

TitleCase has no role in Clausal code; a Python class is reached via
`++ClassName`.  Generated code reaches every runtime-table class through its
`$` twin (`$Var`, `$Quantity`, `$PyThunk`, `$Predicate`, `$Call`, `$Add`,
...) -- landed on that branch.  `Undefined` is the canonical Kleene value and
stays bare permanently (its lowercase alias folds into it); it is NOT part of
this removal.

## What is removed at the end of the window

1. The BARE aliases in every seeding namespace.  Both are built through
   `clausal/logic/generated_names.with_dollar_twins`, so this is one edit:
   make `with_dollar_twins` return ONLY the `$` twins (plus `BARE_ONLY`) and
   delete the "bare keys stay" clause of its docstring.
   - `INJECTED_RUNTIME_BUILTINS` (`clausal/logic/compiler/predicate.py`):
     `Var`, `Compound`, `DictTerm`, `SetTerm`, `KWTerm`, `Trail`, `PyThunk`,
     `FStringThunk`, `Quantity`, `PredicateMeta`, `BoolEq`, `BoolImpl`.
   - `runtime_builtins` (`clausal/import_hook.py`): every bare
     `simple_ast.__all__` node class (`Predicate`, `Call`, `LoadName`,
     `Add`, `Sub`, `Node`, `Module`, ... ~170 names).
   - The IPython snapshot (`_simple_ast_builtins`) inherits the change.
2. The deprecation-window guard in `_make_functor_class_ast`
   (`clausal/templating/term_rewriting.py`): the line
   `if <name> is globals().get('$<name>'): raise NameError` exists only
   because the bare alias is still in the namespace and would otherwise read
   as "user-bound, leave alone".  Once the alias is gone the guard is dead
   and goes with it.
3. The `leaked_runtime_builtin` distrust clauses in
   `clausal/import_hook._make_intern_atom` and
   `clausal/logic/compiler_v2._process_bare_atom_refs`: they exist to stop a
   bare `Add` in a zero-declaration strict module resolving to the node
   class seeded under that name.  With no bare seeding there is nothing to
   distrust; `STRICTNESS_EXEMPT_RUNTIME_NAMES` collapses to `Undefined`
   only (keep the frozenset -- it documents the one exemption).
4. `tests/test_dollar_runtime_names.py::TestBareAliasesStayForTheDeprecationWindow`
   flips to assert the bare names are ABSENT and that a bare `Var()` in user
   code raises `NameError`.
5. Comment/docstring passes: the "bare aliases stay" notes in
   `generated_names.py`, `predicate.py` (table header), `import_hook.py`
   (seeding block), and the `_process_declarations` docstring's account of
   the collision.

## Exit criterion

- No bare use of any twinned name in THIS repo's `.clausal` files,
  `.seam` files, doc snippets, or Python-hosted clause code: the TitleCase
  lint (other branch) reports zero warnings for these names on
  `tests/`, `docs/`, `examples/`, `clausal/modules/`.
- Downstream owners report zero TitleCase-lint warnings for these names
  across their trees (each owner replies with the lint's summary line).
- One full release cycle has passed since the lint started warning.

## Loud failure mode after removal

A bare `Var()` / `Compound(...)` / `Quantity(...)` in user code (a `++`
escape, an f-string, a Python-hosted helper inside a `.clausal` file) raises
`NameError: name 'Var' is not defined` at solve time (escapes are lambdas) or
at load time (module-level Python).  The TitleCase lint's message names the
fix -- `++Var` -- and the strict-atoms diagnostic already lists the five
legitimate ways to reach a name; extend the `NameError` wrapper in
`clausal/import_diagnostics.py` so a NameError on a twinned name says:
`'Var' is no longer bound in a Clausal module; reach the Python class via
++Var` -- the message must name `++Name`, never the `$` twin (the twin is
engine plumbing, not a user surface).

## Identity requirement (keep after removal)

`generated_names.dollar_ref` decides by OBJECT identity: a class gets the
twin when it IS the registered object for its name.  A same-named class
that is not (a subclass spelled `Add`, a reloaded `clausal.terms`) is
emitted as the twin with a `RuntimeWarning`, and the twin resolves to the
REGISTERED class, not to that one.  After the aliases go, that fallback is
the only thing standing between such a class and a `NameError`; the
warning names the mismatch so the owner can register or rename.  Do not
turn the fallback into silence, and do not turn it into an error without
first checking that no test or downstream tree triggers it.

## Non-goals

- `Undefined` stays bare (ruling).
- The `$`-prefixed engine helpers (`$unify`, `$deref`, `$mint`, ...) are
  unaffected; they never had bare aliases.
