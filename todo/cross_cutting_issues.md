# Cross-Cutting Issues

Issues identified across multiple C extensions and modules. These affect the
codebase as a whole and should be addressed uniformly, not piecemeal.

## Correctness

### 1. Trail cast without type check (all C extensions)

Every C extension casts `trail_obj` to `TrailObject *` without calling
`Trail_Check(trail_obj)`. Passing a non-Trail object causes undefined behavior.

**Affected files:** `_constraints_dif.c`, `_tabling_core.c`, `_list_unify.c`,
`_clpfd_propagate.c`, `_arithmetic_core.c`, `_lists_core.c`

**Fix:** Add `Trail_Check()` guard at entry to every exported function that
receives a trail. Must be done project-wide.

### 2. PyObject_IsInstance error returns (-1) not checked (~13 sites)

Call sites compare `PyObject_IsInstance()` result to `== 1`, silently swallowing
`-1` (error) returns. Can cause undefined behavior.

**Affected:** `_variables.c` (most sites now fixed), but audit all C extensions.

**Fix:** Check `if (r < 0) return -1;` before comparing.

### 3. Cumulative constraint uses stale domain snapshots

`CumulativeConstraint.propagate()` snapshots start/end bounds at top of the
function, then uses stale values when computing compulsory parts for later tasks.

**Effect:** Weaker filtering per AC-3 pass; extra iterations needed. Not unsound.

**File:** `clausal/logic/clpfd.py`, `CumulativeConstraint` class.

**Fix:** Re-read bounds from live FD state inside inner loop.

## Thread Safety

### 4. Static caches not thread-safe under free-threaded Python

Lazy-init of module caches using `static` locals without atomics. Race condition
under free-threaded builds (3.13t+).

**Affected:** `c_is_term_instance`, `py_term_field_names`, `str_name` interned
string in `_variables.c`. Rest of codebase uses `FT_ATOMIC_LOAD_PTR` /
`FT_ATOMIC_STORE_PTR`.

**Fix:** Use atomic load/store for all lazy-init static pointers.

### 5. No sub-interpreter support (all C extensions)

All C extensions use `m_size = -1` (global state), incompatible with PEP 684
sub-interpreters. Would need `Py_mod_multiple_interpreters` flag and per-module
state structs.

**Priority:** Low — only matters if sub-interpreter support is required.

## Maintenance

### 6. PyTuple_GET_SIZE macro without type guards

Several places use unchecked `PyTuple_GET_SIZE` on values assumed to be tuples.
Segfault risk if assumptions are violated.

**Fix:** Use `PyTuple_Size()` (checked) or add explicit `PyTuple_Check()`.

### 7. PredicateMeta registration order dependency

`predicate.py` and `_helpers.py` have implicit import-order dependencies for
C code registration. Refactoring import order can silently break results.

**Fix:** Lazy import + register if NULL, or raise clear error on missing
registration.

### 8. int64 ceiling on integer bounds

All C extensions using `PyLong_AsLongLong` can't handle arbitrary-precision
integers. Domain bounds beyond ±2^63 overflow.

**Affected:** CLP(FD) domain ops, variable IDs, coefficient merging.

**Priority:** Low — Python fallback handles correctly. Only matters for
large-integer workloads.

## Resolved

- ~~`c_is_ground` dataclass bug~~ — already fixed (py_term_field_names fallback)
- ~~TuplesIn unbounded domain skip~~ — fixed: now builds allowed domain from
  relation and intersects
