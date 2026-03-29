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
