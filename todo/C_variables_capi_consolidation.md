# Consolidate inter-extension C code sharing via existing C API capsule

Commit that introduced this gap: `perf: move _copy_term and _collect_vars hot paths to C extension`
(also present before that commit in `_tabling_core.c`)

---

## The problem

`_variables.c` already exports a rich C API capsule (`VARIABLES_CAPI_CAPSULE_NAME`)
that includes C-callable function pointers for:

```c
capi_table.deref           = var_deref;
capi_table.is_var          = capi_is_var;
capi_table.unify_oc        = capi_unify_oc;
capi_table.is_term_instance = c_is_term_instance;
capi_table.term_field_names = capi_term_field_names;
/* ... trail_mark, trail_undo, get_attr, put_attr ... */
```

Despite this, `_tabling_core.c` does **not** use it for the functions it needs.
Instead it:

1. **Replicates the `VarObject` struct layout** to inline `var_deref`:
   ```c
   typedef struct {
       PyObject_HEAD
       PyObject *binding;
       uint64_t  var_id;
   } VarObject;
   ```
   This is a maintenance hazard — any change to `VarObject` in `_variables.c`
   silently breaks `_tabling_core.c`.

2. **Calls `c_is_term_instance` and `c_term_field_names` via Python function
   objects** (`py_is_term_instance_func`, `py_term_field_names_func`) registered
   by `tabling.py` at import time.  This incurs Python call overhead on every
   invocation and requires a separate registration handshake.

3. **Duplicates `str_functor`, `str_args`, and other interned strings** that
   `_variables.c` now caches too.

`_clpfd_propagate.c` does not appear to duplicate term-traversal logic, so it
is not affected.

---

## The fix

### Step 1 — `_tabling_core.c`: import and use the C API capsule

At module init, import the capsule from `clausal.logic.variables._variables`:

```c
#include "variables/_variables_capi.h"   /* or inline the struct definition */

static VariablesCAPI *capi = NULL;

/* In PyInit__tabling_core: */
PyObject *cap = PyCapsule_Import(VARIABLES_CAPI_CAPSULE_NAME, 0);
if (!cap) return NULL;
capi = (VariablesCAPI *)cap;
```

Then replace:
- The `VarObject` struct + `var_deref` + `is_var_type` definitions with
  `capi->deref(term)` and `capi->is_var(term)`.
- `c_is_term_instance(obj)` (Python-callable stub) with `capi->is_term_instance(obj)`.
- `c_term_field_names(obj)` (Python-callable stub) with `capi->term_field_names(obj)`.
- The `py_is_term_instance_func` / `py_term_field_names_func` registration
  machinery (both the static vars and the `_register_*` Python-callable) can be
  removed entirely.

### Step 2 — expose `VariablesCAPI` struct definition in a shared header

Currently the struct is defined inline in `_variables.c`.  Move it to
`clausal/logic/variables/_variables_capi.h` so `_tabling_core.c` can include
it.  Update `setup.py` to add `clausal/logic/variables` to `include_dirs` for
the `_tabling_core` extension.

### Step 3 (optional) — deduplicate interned strings

`_tabling_core.c` caches `str_functor`, `str_args`, `str_name`, etc.
independently.  After the capsule migration these are still needed locally in
`_tabling_core.c` (the capsule doesn't export them).  This is acceptable; the
duplication is cosmetic and the cost is two extra interned `PyObject *` per
module — negligible.

---

## Expected benefit

- Eliminates the fragile `VarObject` struct replication in `_tabling_core.c`.
- Reduces `_tabling_core.c`'s import-time registration boilerplate by ~40 lines.
- `c_is_term_instance` and `c_term_field_names` in `_tabling_core.c` become
  direct C function calls instead of `PyObject_CallOneArg` round-trips.
- The C API capsule becomes the single authoritative interface for cross-
  extension term operations, as it was designed to be.

---

## Risk

Low.  The capsule struct is stable (no changes since it was introduced).
`_tabling_core.c` is the only consumer to update.  All existing tabling tests
cover the affected code paths.
