# Move predicate.py term inspection helpers to C

## Context

`clausal/logic/predicate.py` (325 lines) defines the `PredicateMeta` metaclass
and several helper functions that are called from almost every part of the
runtime: compiled predicates, builtins, tabling, constraint solvers.

### Profile data (indirect — called from many hot paths)

| Function | Called from | Benchmark | Calls |
|----------|-----------|-----------|-------|
| `_get_dispatch` | every predicate call | fib | 242,784 |
| `_get_dispatch` | every predicate call | nqueens | 124,618 |
| `term_field_names` | tabling, inspection, _deref_walk | tabling | 2,571 |
| `is_term_instance` | type checks, _normalize_for_key | nqueens | 196,195 |

`is_term_instance` is called 196K times in nqueens alone.  It checks
`isinstance(type(obj), PredicateMeta)` which is a Python metaclass check.

## What to move

```python
# clausal/logic/predicate.py

def is_term_instance(obj):
    """Check if obj is an instance of a PredicateMeta-created class."""
    return isinstance(type(obj), PredicateMeta)

def term_field_names(obj):
    """Return field names tuple for a term instance."""
    return type(obj)._fields

def is_atom(obj):
    """Check if obj is a zero-arity term (atom)."""
    return is_term_instance(obj) and not type(obj)._fields

def _get_dispatch(cls):
    """Get or compile the dispatch function for a predicate class."""
    # This involves compilation — only the lookup part benefits from C
```

Also from `clausal/logic/builtins/_helpers.py`:

```python
def _is_ground(term):
    """Recursively check if term contains no unbound Vars."""
    term = deref(term)
    if is_var(term):
        return False
    if term is None or isinstance(term, (bool, int, float, str, bytes)):
        return True
    if isinstance(term, (list, tuple)):
        return all(_is_ground(e) for e in term)
    if isinstance(term, Compound):
        return all(_is_ground(a) for a in term.args)
    if is_term_instance(term):
        return all(_is_ground(getattr(term, f)) for f in term_field_names(term))
    return True

def _functor_name(term):  # extract functor string
def _arity(term):         # compute arity
def _nth_arg(term, n):    # get n-th argument
def _args_list(term):     # get all arguments as list
```

## Build approach

These are small functions.  Best approach: add them to `_variables.c` (which
already has `deref`, `is_var`, `unify`) since they operate on the same term
types.  This avoids a new .so file and allows direct C-level calls between
functions.

The `PredicateMeta` type reference needs to be passed in at module init time
or looked up lazily:

```c
static PyObject *PredicateMeta_type = NULL;  // cached at init

static int is_term_instance(PyObject *obj) {
    if (PredicateMeta_type == NULL) return 0;
    return PyObject_IsInstance((PyObject *)Py_TYPE(obj), PredicateMeta_type);
}
```

For `_is_ground`, implement as recursive C with the same logic but using direct
C API calls (`PyList_Check`, `PyTuple_Check`, `PyLong_Check`, etc.).

## Gotchas

1. **`PredicateMeta` is defined in Python** (predicate.py).  The C code needs a
   reference to it.  Pass it via a module-level `_register_predicate_meta(cls)`
   function called from predicate.py at import time.

2. **`term_field_names` accesses `type(obj)._fields`**.  In C this is
   `PyObject_GetAttrString(Py_TYPE(obj), "_fields")`.  Cache the `_fields`
   string object for performance.

3. **`_get_dispatch` involves compilation** — only the fast path (already
   compiled, just return cached function) benefits from C.  The compilation
   path must stay in Python.

4. **`_is_ground` is recursive** over arbitrary term depth.  C recursion is fine
   for typical Prolog terms (depth < 100).  Add a depth limit if concerned about
   stack overflow on pathological inputs.

## Overlaps

- `C_tabling_key.md` — `_normalize_for_key` and `_deref_walk` both call
  `is_term_instance` and `term_field_names`.  If those are moved to C first,
  they can call the C versions directly.
- `C_head_list_unify.md` — `_head_list_unify_output` calls `deref` and `is_var`
  which are already in C.

## How to verify

```bash
python benchmarks/workloads.py
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: indirect speedup in all benchmarks through faster `is_term_instance`
and `term_field_names` calls.  Tabling benchmark benefits from faster
`_normalize_for_key` → `is_term_instance` chain.

---

## Implementation doubts (post-landing review)

The C implementations landed in `_variables.c` (lines 1704–2200).  All 8180
tests pass, but there are several correctness and design concerns that need
investigation before this is considered production-ready.

### 1. BUG: `c_is_ground` silently treats non-PredicateMeta dataclass instances as ground

**Severity: correctness bug (silent wrong answer)**

`c_is_ground` calls `c_is_term_instance(term)` which returns true for any
`@dataclass` instance (via `dataclasses.is_dataclass`).  It then calls
`c_term_field_names(term)` which only handles PredicateMeta instances — for
plain dataclasses it returns NULL.  The code then does:

```c
if (c_is_term_instance(term)) {
    PyObject *fields = c_term_field_names(term);
    if (!fields) return 1;  /* <-- BUG: assumes ground without checking fields */
```

This means any non-Compound, non-KWTerm `@dataclass` instance (e.g. `Add`,
`Sub`, `Call`, `Predicate`, and the ~20 other AST node types re-exported from
`pythonic_ast.nodes`) is treated as ground even if it contains unbound Vars.

**Concrete failure case:**

```python
from clausal.terms import Add
from clausal.logic.variables import Var
from clausal.logic.builtins._helpers import _is_ground

_is_ground(Add(left=Var(), right=1))  # C returns True, Python would return False
```

The Compound and KWTerm branches are checked first, so this only affects the
other ~20 `@dataclass` term types.  But those types can appear as runtime
terms (they're re-exported from `clausal.terms` and used in predicate bodies).

**Fix:** when `c_term_field_names` returns NULL, fall back to
`py_term_field_names(NULL, term)` (which handles the dataclass path) instead
of returning 1.  Every other function (`py_arity`, `py_nth_arg`,
`py_args_list`) already does this fallback — `c_is_ground` is the only one
that doesn't.

### 2. `c_is_term_instance` calls `dataclasses.is_dataclass()` on every non-PredicateMeta object

**Severity: performance regression on cold path**

The whole point of moving to C is speed.  For PredicateMeta instances, the
fast path (`PyObject_IsInstance` on `Py_TYPE(obj)`) avoids Python calls.  But
for every object that is NOT a PredicateMeta instance, the code falls through
to call `dataclasses.is_dataclass(obj)` — a full Python function call.

This is the *common* case for many callers: `_is_ground` recurses into lists,
ints, strings — none of which are PredicateMeta instances.  Each one pays for
a Python call that will return False.

**Fix options:**
- Add C-level fast-reject: check `hasattr(type(obj), '__dataclass_fields__')`
  via `PyObject_GetAttrString(Py_TYPE(obj), "__dataclass_fields__")` which is
  a single C attribute lookup (much faster than calling into Python).
  `dataclasses.is_dataclass` internally checks for this attribute.
- Or: check type identity against a known set of dataclass term types
  registered at init time (like we do for Compound/KWTerm).

### 3. `PyObject_IsInstance` error returns (-1) silently swallowed

**Severity: masked errors**

`PyObject_IsInstance` returns 1 (match), 0 (no match), or -1 (error, with
exception set).  Throughout the code, the result is compared with `== 1`:

```c
if (PyObject_IsInstance((PyObject *)Py_TYPE(obj), PredicateMeta_type) == 1)
```

If `PyObject_IsInstance` raises (e.g. PredicateMeta's `__instancecheck__`
throws), the -1 is treated as "not an instance" and execution continues with
an exception set on the thread state.  This will either:
- Cause a confusing error later when another C API call checks for pending
  exceptions, or
- Be silently cleared somewhere downstream.

**Fix:** check for -1 explicitly and propagate:

```c
int r = PyObject_IsInstance(...);
if (r < 0) return -1;  // or return NULL for PyObject* functions
if (r) { ... }
```

This applies to ~13 call sites in the new code.

### 4. `PyTuple_GET_SIZE` on `Compound.args` without type guard

**Severity: potential segfault on malformed input**

Several places do:

```c
PyObject *args = PyObject_GetAttrString(term, "args");
Py_ssize_t n = PyTuple_GET_SIZE(args);
```

`PyTuple_GET_SIZE` is an unchecked macro — if `args` is not a tuple (e.g.
someone passes a list, or a Compound subclass overrides `args`), this is
undefined behavior / segfault.

The Compound dataclass declares `args: tuple` so it *should* always be a
tuple, but Python type annotations aren't enforced at runtime.

**Fix:** either use `PyTuple_Size` (checked, raises TypeError) or add an
explicit `PyTuple_Check` guard.  Same issue applies to `dc_fields` in
`py_term_field_names` and to `fields` in `c_is_ground`/`py_is_atom` where
`_fields` is assumed to be a tuple.

### 5. Static caches for `dataclasses` module are not thread-safe

**Severity: race condition under free-threaded Python (3.13t+)**

The code uses `static` local variables to cache the dataclasses module and
function pointers:

```c
static PyObject *dataclasses_mod = NULL;
static PyObject *is_dc_func = NULL;
if (!dataclasses_mod) {
    dataclasses_mod = PyImport_ImportModule("dataclasses");
    ...
}
```

Under free-threaded builds (which this codebase explicitly supports — see
`_ft_compat.h`), two threads can race through the NULL check simultaneously.
One thread could see a partially-written pointer.  The rest of `_variables.c`
uses `FT_ATOMIC_LOAD_PTR` / `FT_ATOMIC_STORE_PTR` for exactly this kind of
shared state, but the new predicate helper code doesn't.

This affects `c_is_term_instance` (two statics), `py_term_field_names` (two
statics), and the `str_name` interned string in `py_term_field_names`.

**Fix:** either:
- Initialize these caches in `PyInit__variables` (module init is single-threaded), or
- Use `FT_ATOMIC_LOAD_PTR` / `FT_ATOMIC_STORE_PTR` for the lazy init pattern.

### 6. Dead code: `empty ? 1 : 1` in `c_is_ground`

**Severity: cosmetic / code smell**

```c
/* Zero-arity PredicateMeta atoms (classes) */
if (PyType_Check(term) && PredicateMeta_type &&
    PyObject_IsInstance(term, PredicateMeta_type) == 1) {
    PyObject *fields = PyObject_GetAttr(term, str_fields);
    if (!fields) { PyErr_Clear(); return 1; }
    int empty = (PyTuple_GET_SIZE(fields) == 0);
    Py_DECREF(fields);
    return empty ? 1 : 1;  /* both branches return 1 */
}
```

The ternary is meaningless — both branches return 1.  The original Python
code checked `isinstance(term, type) and isinstance(term, PredicateMeta) and
not term._fields` and returned True only for zero-arity atoms.  The C code
returns "ground" for ALL PredicateMeta classes, including non-zero-arity ones.

This is actually semantically correct (classes are ground — they don't contain
Vars), but the dead ternary suggests the author intended to distinguish
zero-arity from non-zero-arity and got confused.  Either simplify to
`return 1;` or add a comment explaining why all PredicateMeta classes are
ground.

### 7. `_register_predicate_meta` / `_register_term_types` registration order fragility

**Severity: import-time coupling**

`predicate.py` now imports directly from `_variables._variables` at module
scope:

```python
from clausal.logic.variables._variables import (
    _register_predicate_meta,
    is_term_instance,
    ...
)
_register_predicate_meta(PredicateMeta)
```

And `_helpers.py` does:

```python
from clausal.logic.variables._variables import (
    _register_term_types,
    ...
)
from clausal.terms import Compound, KWTerm
_register_term_types(Compound, KWTerm)
```

If `_helpers.py` is imported before `predicate.py` (e.g. by a test that
imports builtins directly), the C functions will run without PredicateMeta
registered, causing `is_term_instance` to always return False for
PredicateMeta instances.

Currently this doesn't happen because `_helpers.py` imports from
`clausal.logic.predicate`, which triggers predicate.py's registration first.
But the dependency is implicit and non-obvious — a future refactor that
changes import order could break it silently (no error, just wrong results).

**Fix:** add a defensive check: if `PredicateMeta_type` is NULL when
`c_is_term_instance` is called, try to import and register it lazily, or
raise a clear RuntimeError.

### 8. Error messages degraded vs. Python originals

**Severity: developer experience**

The Python `_nth_arg` raised:
```
IndexError: arg index 5 out of range for fib(n=0, f=1)
```

The C version raises:
```
IndexError: arg index 5 out of range
```

The term repr is lost.  This matters for debugging — when a builtin predicate
fails with an index error, knowing which term was involved is essential.

**Fix:** use `PyObject_Repr(term)` in the error format string:
```c
PyObject *r = PyObject_Repr(term);
PyErr_Format(PyExc_IndexError, "arg index %zd out of range for %U", n, r);
Py_XDECREF(r);
```
