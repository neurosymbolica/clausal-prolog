# Cross-Cutting Issues

Issues identified across multiple C extensions and modules. These affect the
codebase as a whole and should be addressed uniformly, not piecemeal.

## Correctness

### 1. Trail cast without type check (all C extensions) — RESOLVED

**Verified resolved project-wide (2026-09-02):** every remaining cast site is
guarded. `_constraints_dif.c` — all 4 `Trail_CAST` sites have `Trail_Check`
at function entry; `_tabling_core.c` — its single cast (`py_unify_answer`)
is guarded; `_list_unify.c` — casts nothing (threads the trail through to
the Python `unify`, which validates — same clean pattern as
`_clpfd_propagate.c`).

**Audited clean (2026-07-05, A06-F017):** `_arithmetic_core.c` — all 14
exported functions call `Trail_Check(trail_obj)` before `Trail_CAST`
(regression guard: `test_06_clpfd.py::TestArithmeticCore::test_trail_type_checked`).
`_clpfd_propagate.c` — never casts a trail; it threads the trail through to
the Python variables API (`unify`/`put_attr`), which validates.

**Fixed (A09-F020):** `_lists_core.c`, `_chars_core.c` — all 5 entry points
guarded.

**Fix:** Add `Trail_Check()` guard at entry to every exported function that
receives a trail. Must be done project-wide.

### 2. PyObject_IsInstance error returns (-1) not checked — RESOLVED

**Verified resolved project-wide (2026-09-02):** every `PyObject_IsInstance`
call site in `_variables.c` (25), `_constraints_dif.c` (6, incl. all
`is_compound` callers), `_tabling_core.c` (1) and `_arithmetic_core.c`
(via the error-propagating `is_quantity` wrapper) checks `< 0` before
comparing. No other C file calls it.

### 3. Cumulative constraint uses stale domain snapshots — FIXED

`CumulativeConstraint.propagate()` snapshots start/end bounds at top of the
function, then uses stale values when computing compulsory parts for later tasks.

**Effect:** Weaker filtering per AC-3 pass; extra iterations needed. Not unsound.

**File:** `clausal/logic/clpfd.py`, `CumulativeConstraint` class.

**FIXED 2026-09-02:** after `_narrow_if_changed` narrows task *i*, its
`tasks_info` snapshot is refreshed in place, so tasks processed later in the
same pass (and the final compulsory-part check) see the narrowed bounds.
Pinned by `TestCumulativeSinglePassStrength` in
`tests/test_global_constraints.py`, which drives ONE `propagate()` pass and
asserts the cascaded filtering happens within it.

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

### 6. PyList/PyTuple_GET_SIZE macro without type guards

Several places use unchecked `PyList_GET_SIZE` / `PyTuple_GET_SIZE` on values
assumed to be lists/tuples. Segfault risk if assumptions are violated.

**Fixed:** `_lists_core.c` member_find/memberchk_find/append_split_find/
select_find/nth0_find (A09-F021 — `PyList_Check(items)` at each entry).

**Fix:** Use `PyList_Size()` / `PyTuple_Size()` (checked) or add explicit
`PyList_Check()` / `PyTuple_Check()`.

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

## Package Extraction

### Prolog backend AVAILABLE flag should distinguish bridge vs embedded

Each backend __init__.py exposes a single `AVAILABLE` bool that tracks
whether the embedded engine (C ext / Rust ext / ctypes lib) is loaded.
But backends are also usable in bridge mode (subprocess to the prolog
binary on PATH) which requires no native compilation.

A user who has `tpl` on PATH but hasn't compiled `libtpl.so` currently
sees `AVAILABLE=False` even though bridge-mode queries would work fine.

Proposal: expose `EMBEDDED_AVAILABLE` and `BRIDGE_AVAILABLE` (or a
capabilities dict), so callers can pick the right mode. The bridge path
only needs `shutil.which("tpl")` / `shutil.which("scryer-prolog")` /
`shutil.which("gprolog")` to succeed.

Affects: clausal-trealla, clausal-gprolog, clausal-scryer.
