# ModulePredicate goal cells: resolution order, and the name a cell carries

Found 2026-09-25 (fix/call-runs-special-form-cells-2026-09-25), which made a
ModulePredicate cell callable (`higher_order._goal_object_dispatch`) and
buildable in term position (`terms_to_ast._goal_cell_functor`).

## 1. Resolution order -- FIXED on the branch, recorded here

The clause body calls the name's BINDING (`-import_from` rewrites the call to
the dotted global, e.g. `py.random.permutation`), and so does `solve.call`
("Phase 5").  `call/N`'s resolver asked the db's row and the BUILTINS first.
Four py.* ModulePredicates share a name/arity with a builtin (measured by
walking every `clausal.modules.py.*` ModulePredicate against
`_BUILTINS`/`_DB_BUILTINS`):

```
[('http', 'get', 3), ('json', 'get', 3), ('random', 'permutation', 2),
 ('units', 'has_units', 2)]
```

```prolog
-import_from(py.random, [permutation])
h1(P) <- permutation([1, 2, 3], P)                   % body: 1 answer (shuffle)
h2(P) <- call(("permutation", [1, 2, 3], P))         % was 6 (builtin)
h3(P) <- (G is permutation([1, 2, 3], P), call(G))   % was 6 (builtin)
```

Fix (`_resolve_named_goal`), before the db lookups:

```python
    _module_dict = getattr(db, "module_dict", None)
    dispatch = (_goal_object_dispatch(db, _module_dict.get(functor), arity)
                if isinstance(_module_dict, dict) else None)
    if dispatch is not None:
        return dispatch, call_args
    dispatch = db.get_dispatch(functor, arity)
```

Now h1 = h2 = h3 = 1 answer.  Test:
`test_a_module_predicate_binding_wins_over_a_same_named_builtin`.  Builtins are
NOT in a module's dict (measured: `length`, `findall`, `call` are absent), so
this cannot pick a BuiltinPredicate object by accident.

## 2. The name a term-position cell carries -- OPEN edges

`G is match(P, S)` builds `("match", P, S)`, the BASE name, when the module
binds `match` to that same object and `match/N` is not a special form.
Otherwise the cell keeps the DOTTED name the import rewrote the call to:

```prolog
-import_from(py.re, [findall])            % G is findall(P, S, L)
%   -> ("py.re.findall", P, S, L)   -- the bare findall/3 cell is the SPECIAL FORM
-import_from(py.re, [alias(search, rs)])  % G is rs("b", "abc", M)
%   -> ("py.re.search", "b", "abc", M)   -- "search" is not bound here
```

Both run correctly through call/1 IN THAT MODULE (measured; tests
`test_an_imported_findall_stays_the_regex_predicate`,
`test_an_aliased_module_predicate_term_runs`).  Open:

- A cell carries a NAME, so it means what that name means in the module that
  CALLS it.  `("match", P, S)` handed to a module that did not import py.re's
  `match` fails there: before ruling 2 silently, on current main with
  existence_error(procedure, match/2).  A predicate cell has the same
  property, and handles solve it for predicates (a mangled handle in slot 0).
  ModulePredicates have no handle spelling.  Should a ModulePredicate cell
  carry one (for example `py.re.match`, always dotted, resolved through
  `sys.modules` when the calling module does not bind it)?
- The dotted spelling shows in printed terms: `py.re.findall('\\d', "a1b2", L)`.
  writeq / clause/2 output should decide whether that is acceptable.
- `_goal_cell_functor` only fires for NON-callable `_get_dispatch` objects.
  A callable out-of-tree implementor (packages/, about 22 of them) is still
  CALLED in term position, as it always was.  Whether any of them want the
  cell instead is their owners' question (the protocol is frozen).
