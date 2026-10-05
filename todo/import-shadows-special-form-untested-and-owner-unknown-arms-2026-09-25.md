# `_import_shadows_special_form`: an untested arm and an owner-unknown hole

Parked 2026-09-25 from roborev on bd5b620f (fix/call-runs-special-form-cells),
both Low.  The function is in `clausal/logic/builtins/higher_order.py`:

```python
def _import_shadows_special_form(db, functor) -> bool:
    module_dict = getattr(db, "module_dict", None)
    if not isinstance(module_dict, dict):
        return False
    binding = module_dict.get(functor)
    if binding is None:
        return False
    if is_declared_predicate_name(binding, db=db):
        from clausal.logic.predicate import _binding_owner_db  # noqa: PLC0415
        owner = _binding_owner_db(binding, db)
        return owner is not None and owner is not db
    return type(binding) is not str and hasattr(binding, "_get_dispatch")
```

The rule it mirrors: `-import_from` rewrites a body call of an imported name
to the dotted global, so the body runs the IMPORT.  A module's OWN predicate
of that name is not rewritten, so its body still lowers the SPECIAL FORM.

## 1. No test for a module's OWN predicate named like a special form

`tests/fixtures/call_special_forms_owner.seam` defines `once(G) <- (G is 5)`.
In that module the body `once(...)` is the special form, and so is `call/N`
of the cell.  Measured on the branch after the merge of 0738b335:

```python
o = _load("call_special_forms_owner")
X = Var()
list(call("call", ("once", nodes.Unify(left=X, right=1)), module=o))  # X = 1: special form
X = Var()
list(call("once", X, module=o))                                       # X = 5: the predicate
```

No test pins the first line.  Add one to
`tests/test_call_runs_special_form_cells.py` that compares `call/1` of the
cell against a clause body `own(X) <- once(X is 1)` in the owner module.
With the `owner is not db` test removed, it must fail.

## 2. Owner unknown means "not an import", so the special form runs

`_binding_owner_db` answers None in two cases:
- an imported PredicateMeta whose `_row` is None;
- an AMBIGUOUS handle (`_owner_db_or_none`: a question, not a dispatch).

In both cases the function returns False, so `call(("once", G))` runs the
special form.  The body runs the import (the rewrite does not ask who owns
the binding).  Possible fix: decide "imported" from the IMPORT record rather
than from the owner:
- `db.adopted_arities(functor)` is non-empty for a predicate that
  `-import_from` planted (`predicate.binding_grants_arity` reads it);
- or the dotted global the rewrite targets is present in the module dict
  (`module_dict` holds `"<module>.<name>"` bound to the same object; measured
  for `own_once.once` and `py.re.findall`).

The second test is exactly the body's own condition.  To reproduce, build
such a binding by hand (`_row = None` on an imported class, or a handle with
two candidate owners) and compare `call/1` of the cell with the body.

## Related

The dotted ModulePredicate cell (`("py.re.findall", ...)`, see
`todo/module-predicate-cells-resolution-order-and-names-2026-09-25.md`) sits
awkwardly with operator ruling 2026-09-25 option (a): "a functor is never
module-qualified" (`terms_to_ast.handle_cell_functor`).  That ruling covers
predicate HANDLES, and `_goal_cell_functor` answers None for every predicate
binding, so the two do not interact.  A ModulePredicate has no handle
spelling, and the dotted name is how the cell tells py.re's findall/3 apart
from the special form.  Decide whether that is acceptable or whether
ModulePredicates need a handle.
