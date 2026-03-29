# Move dif/2 and constraint helpers to C — DONE

Completed 2026-03-29.

## What was done

All five functions moved to `clausal/logic/_constraints_dif.c`:

- `_collect_free_vars(term)` — recursive term walk collecting unbound Vars
- `_structural_unify_oc(t1, t2, trail)` — structural unify with occurs check
- `dif(x, y, trail)` — post disequality constraint
- `_dif_hook(attr_value, bound_to, trail)` — attribute hook (fires on unify)
- `reify_eq(x, y, trail)` — three-valued equality

## C API capsule

Added `_variables_capi.h` and a `PyCapsule` export from `_variables.c` so that
`_constraints_dif.c` calls internal functions directly in C — no Python call
protocol overhead:

- `var_deref()` — direct binding-chain walk, borrowed ref
- `Var_Check()` — direct type check macro
- `trail_mark()` / `trail_undo()` — direct struct field access
- `get_attr()` / `put_attr()` — direct AttVar dict manipulation
- `unify_oc()` — direct `do_unify_and_wake` with occurs check
- `is_term_instance()` / `term_field_names()` — direct predicate helpers

## Files changed

- **New**: `clausal/logic/_constraints_dif.c` — C extension
- **New**: `clausal/logic/variables/_variables_capi.h` — shared C API header
- **Modified**: `clausal/logic/variables/_variables.c` — exports capsule
- **Modified**: `clausal/logic/constraints.py` — imports C versions when available
- **Modified**: `setup.py` — registers new extension module

## Gotcha resolutions

1. **Hook registration**: The C `_dif_hook` is exposed as a `METH_VARARGS`
   PyCFunction on the module.  `constraints.py` re-registers it via
   `register_attr_hook(DIF_KEY, _c_dif_hook)` — same pattern as CLP(FD).

2. **Recursive term walk**: `collect_walk()` uses direct `VarAPI->deref()` and
   `Var_Check()` — no Python frame creation per recursion step.

3. **Structural unify with occurs check**: `c_structural_unify_oc()` handles
   Compound, term instances, and lists in C, falling through to the C API's
   `unify_oc()` for Var/scalar/tuple cases.

4. **Trail manipulation**: Uses `VarAPI->trail_mark()` / `trail_undo()` which
   access `trail->length` directly and call `trail_undo_to()` in C.

## How to verify

```bash
python -m pytest tests/ -k "dif or disequality or constraint" -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

All 8211 tests pass (331 dif/constraint-specific).
