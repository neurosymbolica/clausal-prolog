# Free-Threaded Python Parallelism for Clausal — Implementation Plan

## Context

Clausal is a Prolog-style logic programming DSL embedded in Python with two C extensions
(`_variables.c` for unification/trails and `_trampoline.c` for search). Free-threaded
Python (PEP 703 / PEP 779, officially supported in 3.14) removes the GIL, enabling true
thread-level parallelism. This is the natural fit for Prolog-style search parallelism
because Prolog's execution model assumes shared mutable state (bindings, clause database,
tabling). The existing analysis in `implementation_plans/FREE_THREADED_PARALLELISM.md`
provides the rationale; this plan specifies the exact implementation.

---

## Phase 1: C Extension Free-Threading Compatibility (Foundation)

**Goal:** Both C extensions declare `Py_MOD_GIL_NOT_USED` and are safe to call from
multiple OS threads without the GIL. All existing tests pass identically on a
free-threaded Python build.

### 1.1 Compatibility macros header

Create a new header `clausal/logic/variables/_ft_compat.h` with portability macros:

```c
#ifndef FT_COMPAT_H
#define FT_COMPAT_H

#include <Python.h>

/*
 * Free-threaded compatibility macros.
 *
 * Under Py_GIL_DISABLED builds (3.13t+), these expand to the real
 * atomic / critical-section operations. Under normal GIL builds,
 * they collapse to plain reads/writes (the GIL provides ordering).
 */

#ifdef Py_GIL_DISABLED

#include <stdatomic.h>

/* Atomic pointer load/store — for var->binding */
#define FT_ATOMIC_LOAD_PTR(ptr)          _Py_atomic_load_ptr_relaxed(&(ptr))
#define FT_ATOMIC_STORE_PTR(ptr, val)    _Py_atomic_store_ptr_relaxed(&(ptr), (val))

/* Atomic uint64 increment — for g_next_var_id */
#define FT_ATOMIC_UINT64_T              _Atomic uint64_t
#define FT_ATOMIC_FETCH_ADD(var, n)     atomic_fetch_add_explicit(&(var), (n), memory_order_relaxed)

/* Critical sections — per-object locking */
#define FT_BEGIN_CS(obj)                Py_BEGIN_CRITICAL_SECTION(obj)
#define FT_END_CS(obj)                  Py_END_CRITICAL_SECTION(obj)
#define FT_BEGIN_CS2(a, b)              Py_BEGIN_CRITICAL_SECTION2(a, b)
#define FT_END_CS2(a, b)               Py_END_CRITICAL_SECTION2(a, b)

#else  /* GIL-enabled: all no-ops */

#define FT_ATOMIC_LOAD_PTR(ptr)          (ptr)
#define FT_ATOMIC_STORE_PTR(ptr, val)    ((ptr) = (val))

#define FT_ATOMIC_UINT64_T              uint64_t
#define FT_ATOMIC_FETCH_ADD(var, n)     ((var)++)

#define FT_BEGIN_CS(obj)                do {
#define FT_END_CS(obj)                  } while (0)
#define FT_BEGIN_CS2(a, b)              do {
#define FT_END_CS2(a, b)               } while (0)

#endif  /* Py_GIL_DISABLED */

#endif  /* FT_COMPAT_H */
```

This header is `#include`d by both `_variables.c` and `_trampoline.c`.

### 1.2 `_variables.c` — Atomic variable ID counter

**File:** `clausal/logic/variables/_variables.c`

**Line 52** — Change the type of `g_next_var_id`:

```c
// BEFORE (line 52):
static uint64_t g_next_var_id = 0;

// AFTER:
static FT_ATOMIC_UINT64_T g_next_var_id = 0;
```

**Line 106** (`Var_new`) — Change the increment:

```c
// BEFORE (line 106):
self->var_id  = g_next_var_id++;

// AFTER:
self->var_id  = FT_ATOMIC_FETCH_ADD(g_next_var_id, 1);
```

**Line 272** (`AttVar_new`) — Same change:

```c
// BEFORE (line 272):
self->base.var_id  = g_next_var_id++;

// AFTER:
self->base.var_id  = FT_ATOMIC_FETCH_ADD(g_next_var_id, 1);
```

**Why `memory_order_relaxed`:** All we need is uniqueness — no ordering guarantees between
threads' var IDs are required by the age-ordered binding convention (it just needs a
consistent total order, which relaxed atomic provides).

### 1.3 `_variables.c` — Atomic binding slot reads/writes

**`var_deref()` (lines 85-95)** — The hot path. Must use atomic loads so one thread sees
another thread's binding writes:

```c
// BEFORE (lines 85-95):
static PyObject *
var_deref(PyObject *term)
{
    while (Var_Check(term)) {
        VarObject *v = Var_CAST(term);
        if (v->binding == NULL)
            return term;
        term = v->binding;
    }
    return term;
}

// AFTER:
static PyObject *
var_deref(PyObject *term)
{
    while (Var_Check(term)) {
        VarObject *v = Var_CAST(term);
        PyObject *b = FT_ATOMIC_LOAD_PTR(v->binding);
        if (b == NULL)
            return term;
        term = b;
    }
    return term;
}
```

**`trail_bind()` (lines 548-557)** — Writes to `var->binding`. The trail_push at line 551
snapshots the old binding (reads `var->binding`), then the write happens at line 555:

```c
// BEFORE (lines 548-557):
static int
trail_bind(TrailObject *trail, VarObject *var, PyObject *value)
{
    if (trail_push(trail, var) < 0)
        return -1;
    Py_XDECREF(var->binding);
    Py_INCREF(value);
    var->binding = value;
    return 0;
}

// AFTER:
static int
trail_bind(TrailObject *trail, VarObject *var, PyObject *value)
{
    if (trail_push(trail, var) < 0)
        return -1;
    Py_INCREF(value);
    PyObject *old = var->binding;
    FT_ATOMIC_STORE_PTR(var->binding, value);
    Py_XDECREF(old);
    return 0;
}
```

**`trail_push()` (lines 530-541)** — Reads `var->binding` to snapshot it. Must use atomic load:

```c
// BEFORE (line 537-539):
    Py_XINCREF(var->binding);
    e->u.binding.var       = var;
    e->u.binding.old_value = var->binding;

// AFTER:
    PyObject *old_binding = FT_ATOMIC_LOAD_PTR(var->binding);
    Py_XINCREF(old_binding);
    e->u.binding.var       = var;
    e->u.binding.old_value = old_binding;
```

**`trail_undo_to()` (lines 629-660)** — Restores bindings. Line 637-638:

```c
// BEFORE (lines 637-638):
    Py_XDECREF(var->binding);
    var->binding = old;    /* transfer ownership: trail → var */

// AFTER:
    PyObject *cur = FT_ATOMIC_LOAD_PTR(var->binding);
    FT_ATOMIC_STORE_PTR(var->binding, old);  /* transfer ownership: trail → var */
    Py_XDECREF(cur);
```

**`Var_get_is_bound()` (lines 186-190)** — Property getter reads `self->binding`:

```c
// BEFORE (line 189):
    return PyBool_FromLong(self->binding != NULL);

// AFTER:
    return PyBool_FromLong(FT_ATOMIC_LOAD_PTR(self->binding) != NULL);
```

**`Var_dealloc()` (lines 112-118)** — Only called when refcount reaches zero, so no
concurrent access. No change needed.

**`Var_clear()` (lines 127-131)** — Called by GC. `Py_CLEAR` handles the swap atomically
in CPython. No change needed.

### 1.4 `_variables.c` — Critical sections in `do_unify()`

**`do_unify()` (lines 874-1033)** — The three binding paths need critical sections to
prevent two threads from simultaneously binding the same variable.

**Var-Var binding (lines 893-917):**

```c
// BEFORE (lines 900-917):
    VarObject *newer = (v1->var_id > v2->var_id) ? v1 : v2;
    VarObject *older = (v1->var_id > v2->var_id) ? v2 : v1;

    if (trail_bind(trail, newer, (PyObject *)older) < 0)
        return -1;

    if (AttVar_Check(newer) && AttVar_CAST(newer)->attrs != NULL) {
        if (trail_enqueue_wakeup(trail, (PyObject *)newer,
                                 (PyObject *)older) < 0)
            return -1;
    }
    return 1;

// AFTER:
    VarObject *newer = (v1->var_id > v2->var_id) ? v1 : v2;
    VarObject *older = (v1->var_id > v2->var_id) ? v2 : v1;

    FT_BEGIN_CS2(newer, older);
    /* Re-check after acquiring lock — another thread may have bound newer */
    PyObject *nb = FT_ATOMIC_LOAD_PTR(newer->binding);
    if (nb != NULL) {
        FT_END_CS2(newer, older);
        /* Variable was bound by another thread — retry unification
         * with the now-bound value. */
        return do_unify((PyObject *)newer, (PyObject *)older,
                        trail, depth, oc);
    }
    if (trail_bind(trail, newer, (PyObject *)older) < 0) {
        FT_END_CS2(newer, older);
        return -1;
    }
    if (AttVar_Check(newer) && AttVar_CAST(newer)->attrs != NULL) {
        if (trail_enqueue_wakeup(trail, (PyObject *)newer,
                                 (PyObject *)older) < 0) {
            FT_END_CS2(newer, older);
            return -1;
        }
    }
    FT_END_CS2(newer, older);
    return 1;
```

**Var-Term binding (lines 921-933) — t1 is Var:**

```c
// AFTER:
    if (t1v) {
        if (oc) {
            int found = do_occurs_check(Var_CAST(t1), t2, 0);
            if (found < 0) return -1;
            if (found)     return 0;
        }
        FT_BEGIN_CS(t1);
        PyObject *b1 = FT_ATOMIC_LOAD_PTR(Var_CAST(t1)->binding);
        if (b1 != NULL) {
            FT_END_CS(t1);
            return do_unify(t1, t2, trail, depth, oc);  /* retry with bound value */
        }
        if (trail_bind(trail, Var_CAST(t1), t2) < 0) {
            FT_END_CS(t1);
            return -1;
        }
        if (AttVar_Check(t1) && AttVar_CAST(t1)->attrs != NULL) {
            if (trail_enqueue_wakeup(trail, t1, t2) < 0) {
                FT_END_CS(t1);
                return -1;
            }
        }
        FT_END_CS(t1);
        return 1;
    }
```

**Var-Term binding (lines 935-947) — t2 is Var:** Mirror of the above with `t2`.

**Edge case: re-check after lock.** Between `var_deref()` returning an unbound variable and
the critical section being acquired, another thread may have bound that variable. The
re-check pattern (`FT_ATOMIC_LOAD_PTR` inside the CS, recurse if bound) prevents
double-binding.

**Why critical sections and not just atomics:** A single `trail_bind` involves two
operations (trail_push + store binding) that must be atomic together. An atomic
pointer store alone would lose the trail entry.

### 1.5 `_variables.c` — `g_attr_hooks` safety

**`fire_wakeups()` (line 1085)** — Replace `PyDict_GetItem` (returns borrowed ref, unsafe
under free-threading) with `PyDict_GetItemRef` (returns new strong ref, 3.13+ API):

```c
// BEFORE (line 1085):
    PyObject *hook = PyDict_GetItem(g_attr_hooks, key);
    if (!hook)
        continue;

// AFTER:
    PyObject *hook = NULL;
    int has = PyDict_GetItemRef(g_attr_hooks, key, &hook);
    if (has < 0) {
        Py_DECREF(items);
        return -1;
    }
    if (has == 0)
        continue;   /* no hook registered for this key */
    /* hook now has a strong reference — must Py_DECREF after use */
```

Don't forget to add `Py_DECREF(hook)` after the hook call result handling (after line 1096):

```c
    // After the truthy check, before the next iteration:
    Py_DECREF(hook);
```

And in the early-return paths (lines 1092, 1098, 1102), add `Py_DECREF(hook)` before returning.

**`py_register_attr_hook()` (lines 1460-1484)** — Wrap in critical section:

```c
// AFTER:
static PyObject *
py_register_attr_hook(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *key, *callable;
    if (!PyArg_ParseTuple(args, "OO", &key, &callable))
        return NULL;

    FT_BEGIN_CS(g_attr_hooks);
    if (callable == Py_None) {
        if (PyDict_DelItem(g_attr_hooks, key) < 0) {
            if (PyErr_ExceptionMatches(PyExc_KeyError))
                PyErr_Clear();
            else {
                FT_END_CS(g_attr_hooks);
                return NULL;
            }
        }
    } else {
        if (!PyCallable_Check(callable)) {
            FT_END_CS(g_attr_hooks);
            PyErr_SetString(PyExc_TypeError,
                            "register_attr_hook(): callable must be callable or None");
            return NULL;
        }
        if (PyDict_SetItem(g_attr_hooks, key, callable) < 0) {
            FT_END_CS(g_attr_hooks);
            return NULL;
        }
    }
    FT_END_CS(g_attr_hooks);
    Py_RETURN_NONE;
}
```

**Note on `FT_BEGIN_CS` inside `py_register_attr_hook`:** The critical section macros
expand to `do {` on GIL builds, so the braces must match. Ensure every early-return path
has `FT_END_CS` before it. Alternatively, use a goto-cleanup pattern.

### 1.6 `_variables.c` — Declare `Py_mod_gil`

**Lines 1585-1619** (`PyInit__variables`) — Add after `PyModule_Create`:

```c
PyMODINIT_FUNC
PyInit__variables(void)
{
    // ... existing type-ready code (lines 1588-1594) ...

    g_attr_hooks = PyDict_New();
    if (!g_attr_hooks) return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) goto error;

#ifdef Py_GIL_DISABLED
    PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED);
#endif

    // ... rest of existing code (lines 1602-1614) ...
```

### 1.7 `_trampoline.c` — Declare `Py_mod_gil`

**File:** `clausal/logic/_trampoline.c`

**Lines 378-406** (`PyInit__trampoline`) — Add after `PyModule_Create`:

```c
    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;

#ifdef Py_GIL_DISABLED
    PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED);
#endif
```

**No other changes needed** in `_trampoline.c`:
- `g_DONE` (line 21) is a singleton created once in module init, never mutated — safe.
- `StepGenObject.gen` and `.started` (lines 27-29) are per-instance state. Under
  or-parallelism, each thread creates its own `StepGenerator` — no sharing.
- `StepGenType` (line 33) is immutable after `PyType_Ready` — safe.

### 1.8 `_trampoline.c` — Include the compat header

Add at the top:
```c
#include "variables/_ft_compat.h"
```

(Or place the header in a shared location. Since `_trampoline.c` doesn't actually need
any FT macros in Phase 1, this is optional but future-proofs the include.)

### 1.9 `setup.py` — Build flags

**File:** `setup.py`

```python
import sysconfig
from setuptools import setup, Extension

extra_compile_args = ["-O2", "-Wall", "-Wextra"]

# Free-threaded Python builds need the Py_GIL_DISABLED define
# so our #ifdef guards activate. setuptools sets it automatically
# for 3.13t+, but we also add it explicitly for clarity.
if sysconfig.get_config_var("Py_GIL_DISABLED"):
    extra_compile_args.append("-DPy_GIL_DISABLED=1")

ext_variables = Extension(
    "clausal.logic.variables._variables",
    sources=["clausal/logic/variables/_variables.c"],
    extra_compile_args=extra_compile_args,
)

ext_trampoline = Extension(
    "clausal.logic._trampoline",
    sources=["clausal/logic/_trampoline.c"],
    extra_compile_args=extra_compile_args,
)

setup(ext_modules=[ext_variables, ext_trampoline])
```

### 1.10 `trampoline.py` — Enable C extension import

**File:** `clausal/logic/trampoline.py` (line 53)

```python
# BEFORE (lines 53-55):
if False:  # C extension disabled — using pure-Python implementation
    from clausal.logic._trampoline import DONE, StepGenerator, trampoline, solutions  # type: ignore[import-untyped]
else:

# AFTER:
try:
    from clausal.logic._trampoline import DONE, StepGenerator, trampoline, solutions  # type: ignore[import-untyped]
except ImportError:
```

The `else:` block stays as-is (it's the pure-Python fallback).

### 1.11 New test file: `tests/test_free_threading.py`

```python
"""Stress tests for free-threaded Python compatibility.

These tests verify that Clausal's C extensions are safe under concurrent
access. They pass under GIL-enabled builds too (threads just serialize).
Under free-threaded builds (python3.13t+), they exercise true parallelism.
"""

import sys
import threading
import pytest

from clausal.logic.variables import (
    Var, Trail, deref, is_var, unify, register_attr_hook,
    unregister_attr_hook, put_attr, get_attr,
)


def is_free_threaded():
    """True if running on a free-threaded Python build."""
    return hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled()


# ── 1. Concurrent Var creation: unique IDs ────────────────────────────────

class TestConcurrentVarCreation:
    """Multiple threads creating Vars must get globally unique var_ids."""

    def test_unique_ids_under_contention(self):
        NUM_THREADS = 8
        VARS_PER_THREAD = 10_000
        all_ids: list[set[int]] = [set() for _ in range(NUM_THREADS)]
        barrier = threading.Barrier(NUM_THREADS)

        def worker(idx):
            barrier.wait()  # synchronize start for maximum contention
            for _ in range(VARS_PER_THREAD):
                v = Var()
                all_ids[idx].add(v._id)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All IDs globally unique
        merged = set()
        for s in all_ids:
            assert len(s) == VARS_PER_THREAD, "Thread lost some Var IDs"
            overlap = merged & s
            assert not overlap, f"Duplicate var IDs across threads: {overlap}"
            merged |= s

        assert len(merged) == NUM_THREADS * VARS_PER_THREAD


# ── 2. Concurrent independent unification ─────────────────────────────────

class TestConcurrentUnification:
    """Each thread runs unification on its own Vars and Trail.
    No shared variables — tests that the C extension doesn't corrupt
    internal state under concurrent calls."""

    def test_independent_unify_threads(self):
        NUM_THREADS = 8
        ITERS = 5_000
        errors: list[str] = []
        barrier = threading.Barrier(NUM_THREADS)

        def worker(idx):
            barrier.wait()
            for i in range(ITERS):
                trail = Trail()
                x, y, z = Var(), Var(), Var()
                # unify(x, [y, z]) then unify(y, 42) then unify(z, "hello")
                assert unify(x, [y, z], trail)
                assert unify(y, 42, trail)
                assert unify(z, "hello", trail)
                assert deref(x) == [42, "hello"]
                assert deref(y) == 42
                assert deref(z) == "hello"
                # Undo and verify
                trail.undo(0)
                assert is_var(x)
                assert is_var(y)
                assert is_var(z)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_unify_shared_ground_terms(self):
        """Multiple threads unify their own Vars against the same ground list."""
        NUM_THREADS = 8
        shared_ground = [1, 2, [3, 4], "five"]
        barrier = threading.Barrier(NUM_THREADS)
        results = [None] * NUM_THREADS

        def worker(idx):
            barrier.wait()
            trail = Trail()
            x = Var()
            assert unify(x, shared_ground, trail)
            results[idx] = deref(x)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for r in results:
            assert r == shared_ground


# ── 3. Concurrent attr hook registration ──────────────────────────────────

class TestConcurrentAttrHooks:
    """Tests register/unregister_attr_hook under contention."""

    def test_concurrent_register_unregister(self):
        NUM_THREADS = 8
        ITERS = 2_000
        barrier = threading.Barrier(NUM_THREADS)

        def worker(idx):
            key = f"test_hook_{idx}"
            barrier.wait()
            for i in range(ITERS):
                register_attr_hook(key, lambda av, bt, t: True)
                unregister_attr_hook(key)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_hook_fires_under_contention(self):
        """Register a hook, then unify AttVars from multiple threads."""
        hook_calls = []
        lock = threading.Lock()

        def counting_hook(attr_val, bound_to, trail):
            with lock:
                hook_calls.append(attr_val)
            return True

        register_attr_hook("test_counting", counting_hook)
        try:
            NUM_THREADS = 4
            ITERS = 500
            barrier = threading.Barrier(NUM_THREADS)

            def worker(idx):
                barrier.wait()
                for i in range(ITERS):
                    trail = Trail()
                    v = Var()
                    put_attr(v, "test_counting", idx * 10000 + i, trail)
                    unify(v, 99, trail)

            threads = [threading.Thread(target=worker, args=(i,))
                       for i in range(NUM_THREADS)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(hook_calls) == NUM_THREADS * ITERS
        finally:
            unregister_attr_hook("test_counting")


# ── 4. Concurrent read-only queries against shared Database ───────────────

class TestConcurrentDatabaseReads:
    """Multiple threads resolve goals against the same compiled Database."""

    def test_concurrent_call(self):
        from clausal.logic.compiler import compile_predicate_trampoline
        from clausal.logic.database import Clause, Database, Module
        from clausal.logic.solve import call
        from clausal.terms import Compound, Unify as Is

        mod = Module("test_concurrent")
        db = mod.db

        # Assert 100 facts: num(0), num(1), ..., num(99)
        for i in range(100):
            v = Var()
            db.assertz(Clause(
                head=Compound("num", (v,)),
                body=[Is(left=v, right=i)],
            ))
        compile_predicate_trampoline("num", 1,
                                     db.clauses_for("num", 1), db)

        NUM_THREADS = 8
        barrier = threading.Barrier(NUM_THREADS)
        results = [None] * NUM_THREADS

        def worker(idx):
            barrier.wait()
            solutions = []
            x = Var()
            for trail in call("num", x, module=mod):
                solutions.append(deref(x))
            results[idx] = sorted(solutions)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected = list(range(100))
        for r in results:
            assert r == expected, f"Thread got wrong results: {r[:5]}..."


# ── 5. Trail isolation ────────────────────────────────────────────────────

class TestTrailIsolation:
    """Verify that Trail objects are independent — undo on one
    trail doesn't affect variables bound via another trail."""

    def test_two_trails_independent(self):
        x = Var()
        t1, t2 = Trail(), Trail()

        unify(x, 42, t1)
        assert deref(x) == 42

        t1.undo(0)
        assert is_var(x)

        unify(x, "hello", t2)
        assert deref(x) == "hello"

        t2.undo(0)
        assert is_var(x)
```

### 1.12 Phase 1 verification

1. **Build:** `python3.13t -m pip install -e .` (or `python3.14t`)
2. **Existing tests:** `python3.13t -m pytest tests/ -x` — all must pass
3. **New tests:** `python3.13t -m pytest tests/test_free_threading.py -v`
4. **TSAN (optional):** Build CPython with TSAN, rebuild extension, run stress tests

---

## Phase 2: Thread-Safe Python Layer

**Goal:** Python-level shared mutable state (Database, PredicateMeta, TableEntry) is safe
for concurrent access. Write operations use copy-on-write semantics.

### 2.1 Copy-on-write `Database` mutations

**File:** `clausal/logic/database.py`

Add `import threading` at the top.

**`__init__` (line 42)** — Add a write lock:

```python
def __init__(self, module_dict: dict | None = None) -> None:
    self._clauses: dict[tuple[str, int], list[Clause]] = {}
    self._signatures: dict[tuple[str, int], tuple | None] = {}
    self._dispatch: dict[tuple[str, int], Callable | None] = {}
    self._lazy_recompile: dict[tuple[str, int], Callable] = {}
    self._dynamic: set[tuple[str, int]] = set()
    self._discontiguous: set[tuple[str, int]] = set()
    self._tabled: set[tuple[str, int]] = set()
    self._shallow: set[tuple[str, int]] = set()
    self._table_store: dict = {}
    self.module_dict: dict | None = module_dict
    self._write_lock = threading.Lock()  # NEW
```

**`assertz()` (lines 54-64)** — Copy-on-write instead of in-place append:

```python
def assertz(self, clause: Clause) -> None:
    functor, arity = head_key(clause.head)
    key = (functor, arity)
    with self._write_lock:
        old = self._clauses.get(key, [])
        self._clauses[key] = old + [clause]   # new list — readers see old or new, never partial
        if key in self._dispatch:
            self._dispatch[key] = None
        if key in self._tabled:
            self.abolish_table(functor, arity)
```

**`asserta()` (lines 66-78)** — Same pattern:

```python
def asserta(self, clause: Clause) -> None:
    functor, arity = head_key(clause.head)
    key = (functor, arity)
    with self._write_lock:
        old = self._clauses.get(key, [])
        self._clauses[key] = [clause] + old
        if key in self._dispatch:
            self._dispatch[key] = None
        if key in self._tabled:
            self.abolish_table(functor, arity)
```

**`retract()` (lines 80-99)** — Build a new list excluding the retracted clause:

```python
def retract(self, head: Any) -> bool:
    functor, arity = head_key(head)
    key = (functor, arity)
    with self._write_lock:
        clauses = self._clauses.get(key)
        if clauses is None:
            return False
        for i, clause in enumerate(clauses):
            if clause.head == head:
                self._clauses[key] = clauses[:i] + clauses[i+1:]
                if key in self._dispatch:
                    self._dispatch[key] = None
                if key in self._tabled:
                    self.abolish_table(functor, arity)
                return True
    return False
```

**`clauses_for()` (lines 101-103)** — Currently returns `list(...)` copy. Under
copy-on-write, the stored list is never mutated, so we can return it directly for
read performance. But returning a copy is safer and the function is not on the hot path:

```python
def clauses_for(self, functor: str, arity: int) -> list[Clause]:
    """Return clauses for (functor, arity), or []. The returned list must not be mutated."""
    return self._clauses.get((functor, arity), [])
```

(Since we now do copy-on-write, the list at `_clauses[key]` is never mutated in place,
so returning it directly is safe. Callers already don't mutate it.)

**`get_dispatch()` (lines 146-164)** — Double-checked locking for lazy recompile:

```python
def get_dispatch(self, functor: str, arity: int) -> Callable | None:
    key = (functor, arity)
    fn = self._dispatch.get(key)
    if fn is None and key in self._dispatch:
        with self._write_lock:
            # Double-check after lock
            fn = self._dispatch.get(key)
            if fn is None and key in self._dispatch:
                lazy = self._lazy_recompile.get(key)
                if lazy is not None:
                    fn = lazy()
                    self._dispatch[key] = fn
    if fn is not None:
        return fn
    from clausal.logic.builtins import get_builtin_dispatch
    return get_builtin_dispatch(functor, arity, self)
```

**`abolish_table()` (lines 205-214)** — Already called under `_write_lock` from
assertz/retract. Keep as-is.

### 2.2 Copy-on-write `PredicateMeta` mutations

**File:** `clausal/logic/predicate.py`

Add `import threading` at the top.

**`__init__` (lines 113-120)** — Add write lock:

```python
def __init__(cls, name: str, bases: tuple, namespace: dict, **kwargs: Any) -> None:
    super().__init__(name, bases, namespace, **kwargs)
    cls._clauses: list = []
    cls._dispatch_fn: Callable | None = None
    cls._lazy_recompile: Callable | None = None
    cls._signature: tuple[str, ...] | None = None
    cls._locked: bool = False
    cls._write_lock = threading.Lock()  # NEW
```

**`_assertz()` (lines 161-169):**

```python
def _assertz(cls, clause: Any) -> None:
    if cls._locked:
        raise RuntimeError(
            f"Predicate {cls.__name__}/{cls._arity} is locked. "
            "Use dynamic() to allow runtime assertion."
        )
    with cls._write_lock:
        cls._clauses = cls._clauses + [clause]  # new list
        cls._dispatch_fn = None
```

**`_asserta()` (lines 171-179):**

```python
def _asserta(cls, clause: Any) -> None:
    if cls._locked:
        raise RuntimeError(
            f"Predicate {cls.__name__}/{cls._arity} is locked. "
            "Use dynamic() to allow runtime assertion."
        )
    with cls._write_lock:
        cls._clauses = [clause] + cls._clauses  # new list
        cls._dispatch_fn = None
```

**`_retract()` (lines 181-196):**

```python
def _retract(cls, head: Any) -> bool:
    if cls._locked:
        raise RuntimeError(
            f"Predicate {cls.__name__}/{cls._arity} is locked. "
            "Use dynamic() to allow runtime retraction."
        )
    with cls._write_lock:
        for i, clause in enumerate(cls._clauses):
            if clause.head == head:
                cls._clauses = cls._clauses[:i] + cls._clauses[i+1:]
                cls._dispatch_fn = None
                return True
    return False
```

**`_get_dispatch()` (lines 200-214):**

```python
def _get_dispatch(cls) -> Callable:
    fn = cls._dispatch_fn
    if fn is not None:
        return fn
    with cls._write_lock:
        fn = cls._dispatch_fn
        if fn is not None:
            return fn
        if cls._lazy_recompile is not None:
            fn = cls._lazy_recompile()
            cls._dispatch_fn = fn
            return fn
        raise NotImplementedError(
            f"Predicate {cls.__name__}/{cls._arity} has no compiled "
            "dispatch function. The compiler must be run first."
        )
```

### 2.3 Per-entry lock for `TableEntry`

**File:** `clausal/logic/tabling.py`

**`TableEntry.__init__` (lines 107-113):**

```python
def __init__(self):
    self.status: str = "evaluating"
    self.answers: list[tuple] = []
    self.answer_set: set[tuple] = set()
    self.suspended: list = []
    self.conditions: list = []
    self._current_delays: set[DelayedNegation] = set()
    self._lock = threading.Lock()  # NEW
```

Add `"_lock"` to `__slots__` (line 104).

**`add_answer()` (lines 115-122):**

```python
def add_answer(self, answer: tuple, delay_set: frozenset | None = None) -> bool:
    with self._lock:
        if answer in self.answer_set:
            return False
        self.answer_set.add(answer)
        self.answers.append(answer)
        self.conditions.append(delay_set if delay_set is not None else frozenset())
        return True
```

### 2.4 Module-level mutable state audit

Files checked — **no additional changes needed:**

| File | Global | Status |
|------|--------|--------|
| `clausal/logic/builtins/_registry.py` | `_BUILTINS`, `_DB_BUILTINS`, `_BUILTIN_FIELDS`, `_BUILTIN_CLASSES` | Populated at import time via decorators, read-only during execution. Safe. |
| `clausal/logic/clpfd.py` | `FD_KEY`, `DEFAULT_MIN`, `DEFAULT_MAX`, `_REIFY_OPS`, `_FD_OPS` | Module constants. Safe. |
| `clausal/logic/constraints.py` | `DIF_KEY` | String constant. Safe. |
| `clausal/logic/compiler.py` | `_compile_context_local` (line 73) | Already `threading.local`. Safe. |
| `clausal/logic/tabling.py` | `_leader_ctx` (line 84) | Already `threading.local`. Safe. |
| `clausal/logic/trampoline.py` | `DONE` | Immutable singleton. Safe. |
| `clausal/logic/variables/__init__.py` | `Var = AttVar` | Alias assignment at import. Safe. |

### 2.5 Phase 2 testing

Add to `tests/test_free_threading.py`:

```python
class TestConcurrentAssertRetract:
    """Stress test: multiple threads assert/retract while others query."""

    def test_concurrent_assertz_and_query(self):
        from clausal.logic.compiler import compile_predicate_trampoline
        from clausal.logic.database import Clause, Database, Module
        from clausal.logic.solve import call
        from clausal.terms import Compound, Unify as Is

        mod = Module("test_cow")
        db = mod.db
        db.mark_dynamic("dyn", 1)

        # Seed with one fact
        v = Var()
        db.assertz(Clause(head=Compound("dyn", (v,)), body=[Is(left=v, right=0)]))
        compile_predicate_trampoline("dyn", 1, db.clauses_for("dyn", 1), db)

        NUM_WRITERS = 2
        NUM_READERS = 4
        WRITE_ITERS = 200
        READ_ITERS = 500
        errors = []

        def writer(idx):
            for i in range(WRITE_ITERS):
                v = Var()
                db.assertz(Clause(
                    head=Compound("dyn", (v,)),
                    body=[Is(left=v, right=(idx + 1) * 10000 + i)],
                ))

        def reader(idx):
            for _ in range(READ_ITERS):
                x = Var()
                sols = []
                try:
                    for trail in call("dyn", x, module=mod):
                        sols.append(deref(x))
                except Exception as e:
                    errors.append(str(e))
                # Should always get at least the seed fact (0)
                if 0 not in sols:
                    errors.append(f"Reader {idx}: seed fact 0 not found in {sols[:5]}")

        threads = (
            [threading.Thread(target=writer, args=(i,)) for i in range(NUM_WRITERS)] +
            [threading.Thread(target=reader, args=(i,)) for i in range(NUM_READERS)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors: {errors[:3]}"
```

### 2.6 Phase 2 verification

1. `python3.13t -m pytest tests/ -x` — all existing tests pass
2. `python3.13t -m pytest tests/test_free_threading.py -v` — new concurrent tests pass

---

## Phase 3: Or-Parallelism

**Goal:** Users can run clause alternatives in parallel using a thread pool, getting
real speedup for search-heavy problems (N-queens, graph coloring, etc.).

### 3.1 New file: `clausal/logic/parallel.py`

```python
"""clausal.logic.parallel — or-parallel and and-parallel search.

Provides utilities for forking the binding environment at choice points
and exploring clause alternatives in parallel using Python threads.
Requires free-threaded Python (3.13t+) for true parallelism; falls back
to sequential execution under GIL-enabled builds.
"""

from __future__ import annotations

import sys
import threading
import concurrent.futures
from typing import Any, Callable, Iterator

from clausal.logic.variables import Var, AttVar, Trail, deref, is_var, unify
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.trampoline import StepGenerator, DONE
from clausal.terms import Compound


def is_free_threaded() -> bool:
    """Return True if running on a free-threaded Python build with GIL disabled."""
    return hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled()


# ── Binding environment snapshot ──────────────────────────────────────────


def fork_bindings(
    trail: Trail,
    vars_in_scope: list[Any],
) -> tuple[Trail, dict[int, Var], Callable]:
    """Create a forked binding environment for a parallel worker.

    Given a list of Var objects in scope at the fork point, creates:
    1. A new Trail for the worker
    2. Fresh Var copies for all unbound variables
    3. A remap function that translates terms from the original namespace
       to the forked namespace

    Returns (new_trail, var_map, remap_fn) where:
    - new_trail: empty Trail for the worker
    - var_map: {original_var._id: new_var}
    - remap_fn: callable that deep-copies a term through the mapping

    Ground values (ints, strings, lists of ground values, etc.) are shared
    directly — they are immutable and safe to read from any thread.
    """
    new_trail = Trail()
    var_map: dict[int, Var] = {}

    def remap(term: Any) -> Any:
        """Deep-copy a term, replacing Vars with their forked copies."""
        term = deref(term)
        if is_var(term):
            vid = term._id
            if vid not in var_map:
                var_map[vid] = Var()
            return var_map[vid]
        if isinstance(term, (bool, int, float, str, bytes, complex, type(None))):
            return term  # immutable scalars — share directly
        if isinstance(term, list):
            return [remap(e) for e in term]
        if isinstance(term, tuple):
            return tuple(remap(e) for e in term)
        if isinstance(term, Compound):
            return Compound(term.functor, tuple(remap(a) for a in term.args))
        if is_term_instance(term):
            return type(term)(**{
                f: remap(getattr(term, f))
                for f in term_field_names(term)
            })
        return term  # unknown type — assume immutable, share directly

    # Remap all vars in scope to populate var_map
    remapped_vars = [remap(v) for v in vars_in_scope]

    # Now bind the new Vars to mirror the original bindings
    for orig_var in vars_in_scope:
        orig_deref = deref(orig_var)
        if not is_var(orig_deref):
            # Original was bound to a ground/compound value — bind the copy
            new_var = var_map.get(orig_var._id)
            if new_var is not None and is_var(new_var):
                unify(new_var, remap(orig_deref), new_trail)

    return new_trail, var_map, remap


def merge_bindings_back(
    var_map: dict[int, Var],
    original_vars: list[Any],
    trail: Trail,
) -> bool:
    """Merge forked bindings back into the original namespace.

    For each original Var that was unbound at fork time, if the forked
    copy is now bound, unify the original with the forked value.

    Returns True if all merges succeed, False if any unification fails.
    """
    for orig_var in original_vars:
        if not is_var(orig_var):
            continue
        orig_deref = deref(orig_var)
        if not is_var(orig_deref):
            continue  # already bound in original
        vid = orig_var._id
        if vid not in var_map:
            continue
        new_var = var_map[vid]
        new_deref = deref(new_var)
        if not is_var(new_deref):
            if not unify(orig_var, new_deref, trail):
                return False
    return True


# ── Or-parallel search ────────────────────────────────────────────────────


class OrParallelSearch:
    """Execute clause alternatives in parallel using a thread pool.

    Usage:
        search = OrParallelSearch(max_workers=4)
        for solution in search.parallel_solve(goal, module):
            print(solution)
    """

    def __init__(
        self,
        max_workers: int | None = None,
        depth_threshold: int = 3,
        min_branches: int = 2,
    ):
        self.max_workers = max_workers
        self.depth_threshold = depth_threshold
        self.min_branches = min_branches
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None

    def _get_executor(self) -> concurrent.futures.ThreadPoolExecutor:
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            )
        return self._executor

    def should_fork(self, depth: int, num_alternatives: int) -> bool:
        """Granularity control: decide whether to parallelize this choice point."""
        if not is_free_threaded():
            return False  # No point forking under GIL
        return (depth <= self.depth_threshold and
                num_alternatives >= self.min_branches)

    def shutdown(self):
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
```

### 3.2 Cancellation support in `_drive_trampoline()`

**File:** `clausal/logic/solve.py`

Add optional `cancel_event` parameter to `_drive_trampoline()` (line 66):

```python
def _drive_trampoline(
    dispatch_fn: Any, trail: Trail, *args: Any,
    cancel_event: threading.Event | None = None,
) -> Iterator[Trail]:
    """Drive a trampoline-protocol dispatch function, yielding trail per solution.

    If cancel_event is provided and becomes set, the search aborts early.
    """
    from clausal.logic.tabling import _TABLING_SUSPEND
    from clausal.logic.exceptions import LogicException

    sg = StepGenerator(dispatch_fn, None, *args, trail)
    gen, value = sg.send(None)
    while True:
        # Cancellation check — natural polling point at each trampoline step
        if cancel_event is not None and cancel_event.is_set():
            return
        if gen is None:
            if value is DONE:
                return
            yield trail
            gen, value = sg.send(None)
        else:
            try:
                if value is _TABLING_SUSPEND:
                    gen, value = gen.send(DONE)
                else:
                    gen, value = gen.send(value)
            except LogicException as exc:
                target = gen.parent if hasattr(gen, 'parent') else None
                while target is not None:
                    try:
                        gen, value = target.throw(exc)
                        break
                    except LogicException:
                        target = target.parent if hasattr(target, 'parent') else None
                else:
                    raise exc
```

Add `import threading` to the imports at the top of `solve.py`.

### 3.3 New test file: `tests/test_or_parallelism.py`

```python
"""Tests for or-parallel search."""

import threading
import pytest

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.parallel import fork_bindings, merge_bindings_back, is_free_threaded


class TestForkBindings:
    """Unit tests for binding environment forking."""

    def test_fork_unbound_vars(self):
        """Forking unbound vars creates independent copies."""
        x, y = Var(), Var()
        new_trail, var_map, remap = fork_bindings(Trail(), [x, y])

        assert x._id in var_map
        assert y._id in var_map
        assert var_map[x._id]._id != x._id  # different Var
        assert is_var(var_map[x._id])

    def test_fork_bound_var(self):
        """Forking a bound var copies the binding."""
        x = Var()
        trail = Trail()
        unify(x, 42, trail)

        new_trail, var_map, remap = fork_bindings(trail, [x])
        new_x = var_map[x._id]
        assert deref(new_x) == 42

    def test_fork_compound_binding(self):
        """Forking a var bound to [Y, Z] creates independent copies of Y, Z."""
        x, y, z = Var(), Var(), Var()
        trail = Trail()
        unify(x, [y, z], trail)
        unify(y, 1, trail)

        new_trail, var_map, remap = fork_bindings(trail, [x, y, z])
        new_x = var_map[x._id]
        new_z = var_map[z._id]

        # new_x should be bound to [1, new_z] where new_z is unbound
        val = deref(new_x)
        assert isinstance(val, list)
        assert val[0] == 1
        assert is_var(val[1])

    def test_fork_independence(self):
        """Binding a forked var doesn't affect the original."""
        x = Var()
        trail = Trail()

        new_trail, var_map, remap = fork_bindings(trail, [x])
        new_x = var_map[x._id]
        unify(new_x, 99, new_trail)

        assert deref(new_x) == 99
        assert is_var(x)  # original unaffected

    def test_ground_terms_shared(self):
        """Ground terms are shared, not copied."""
        big_list = list(range(1000))
        x = Var()
        trail = Trail()
        unify(x, big_list, trail)

        new_trail, var_map, remap = fork_bindings(trail, [x])
        new_x = var_map[x._id]
        # The list contents should be equal
        assert deref(new_x) == big_list


class TestMergeBindings:
    """Unit tests for merging forked bindings back."""

    def test_merge_simple(self):
        x = Var()
        trail = Trail()

        new_trail, var_map, remap = fork_bindings(trail, [x])
        unify(var_map[x._id], 42, new_trail)

        assert merge_bindings_back(var_map, [x], trail)
        assert deref(x) == 42

    def test_merge_conflict(self):
        """If original is already bound to something different, merge fails."""
        x = Var()
        trail = Trail()

        new_trail, var_map, remap = fork_bindings(trail, [x])
        unify(var_map[x._id], 42, new_trail)
        unify(x, 99, trail)  # bind original to different value

        result = merge_bindings_back(var_map, [x], trail)
        assert not result  # merge fails — 42 != 99
```

### 3.4 Phase 3 verification

1. `python3.13t -m pytest tests/test_or_parallelism.py -v` — fork/merge tests pass
2. Manual benchmark: N-queens with parallel search vs sequential

---

## Phase 4: Independent And-Parallelism

**Goal:** The compiler detects independent body goals (disjoint variable sets) and can
generate fork-join code to execute them in parallel.

### 4.1 Independence analysis in `compiler.py`

**File:** `clausal/logic/compiler.py`

Add a new function near the existing `_collect_var_ids()` (~line 4978):

```python
def _find_independent_groups(body_goals: list, var_context: dict) -> list[list[int]]:
    """Partition body goals into maximal independent groups.

    Two goals are independent if they share no unbound variables.
    Returns a list of groups, each a list of goal indices.
    Goals within a group MAY run in parallel; groups must run sequentially.

    Conservative: goals touching attributed variables (CLP constraints) are
    always treated as dependent, because constraints create implicit links.

    Example:
        body = [a(X), b(Y), c(X, Y)]
        → [[0, 1], [2]]  (a(X) and b(Y) are independent; c depends on both)
    """
    goal_vars: list[set] = []
    for goal in body_goals:
        ids = set()
        _collect_var_ids(goal, ids)
        goal_vars.append(ids)

    # Build groups greedily left-to-right
    groups: list[list[int]] = []
    current_group: list[int] = []
    current_vars: set = set()

    for i, gvars in enumerate(goal_vars):
        if current_vars & gvars:
            # Dependent on current group — start new sequential group
            if current_group:
                groups.append(current_group)
            current_group = [i]
            current_vars = gvars.copy()
        else:
            # Independent — add to current parallel group
            current_group.append(i)
            current_vars |= gvars

    if current_group:
        groups.append(current_group)

    return groups
```

### 4.2 Phase 4 testing

```python
class TestIndependenceAnalysis:
    def test_disjoint_vars(self):
        # a(X), b(Y) → one group of two
        from clausal.logic.compiler import _find_independent_groups
        # ... (needs mock goals with known var IDs)

    def test_shared_vars(self):
        # a(X), b(X) → two singleton groups
        ...

    def test_mixed(self):
        # a(X), b(Y), c(X, Y) → [[0,1], [2]]
        ...
```

---

## Phase 5: Concurrent Tabling

**Goal:** Multiple threads can contribute to and consume from the same tabling memo tables.

### 5.1 Condition-variable-based `TableEntry`

**File:** `clausal/logic/tabling.py`

Replace `self._lock = threading.Lock()` with a `Condition`:

```python
class TableEntry:
    __slots__ = ("status", "answers", "answer_set", "suspended",
                 "conditions", "_current_delays", "_lock", "_condition")

    def __init__(self):
        self.status: str = "evaluating"
        self.answers: list[tuple] = []
        self.answer_set: set[tuple] = set()
        self.suspended: list = []
        self.conditions: list = []
        self._current_delays: set[DelayedNegation] = set()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

    def add_answer(self, answer: tuple, delay_set: frozenset | None = None) -> bool:
        with self._condition:
            if answer in self.answer_set:
                return False
            self.answer_set.add(answer)
            self.answers.append(answer)
            self.conditions.append(delay_set if delay_set is not None else frozenset())
            self._condition.notify_all()  # wake waiting consumers
            return True

    def wait_for_new_answers(self, seen_count: int, timeout: float = 1.0) -> bool:
        """Block until new answers are available or table is complete.
        Returns True if there are new answers to consume."""
        with self._condition:
            while len(self.answers) <= seen_count and self.status == "evaluating":
                if not self._condition.wait(timeout=timeout):
                    continue  # timeout — re-check
            return len(self.answers) > seen_count

    def mark_complete(self):
        with self._condition:
            self.status = "complete"
            self._condition.notify_all()
```

### 5.2 Phase 5 testing

```python
class TestConcurrentTabling:
    def test_concurrent_table_reads(self):
        """Multiple threads query the same tabled predicate after it's complete."""
        ...

    def test_producer_consumer_tabling(self):
        """One thread drives a tabled predicate (leader), others consume answers."""
        ...
```

---

## File Change Summary

| Phase | File | Change |
|-------|------|--------|
| 1 | `clausal/logic/variables/_ft_compat.h` | **New** — portability macros |
| 1 | `clausal/logic/variables/_variables.c` | Atomic var_id (L52,106,272), atomic binding slots (L85-95, 530-541, 548-557, 629-660, 186-190), critical sections in do_unify (L893-947), g_attr_hooks safety (L1085, 1460-1484), Py_mod_gil (L1586+) |
| 1 | `clausal/logic/_trampoline.c` | Py_mod_gil slot (L378+) |
| 1 | `setup.py` | Conditional `-DPy_GIL_DISABLED=1` flag |
| 1 | `clausal/logic/trampoline.py` | Enable C extension (L53): `if False:` → `try:/except ImportError:` |
| 1 | `tests/test_free_threading.py` | **New** — concurrent Var creation, unification, hooks, DB reads |
| 2 | `clausal/logic/database.py` | `_write_lock`, copy-on-write assertz/asserta/retract (L42-164) |
| 2 | `clausal/logic/predicate.py` | `_write_lock`, copy-on-write _assertz/_asserta/_retract/_get_dispatch (L113-214) |
| 2 | `clausal/logic/tabling.py` | `_lock` on TableEntry, locked add_answer (L102-122) |
| 3 | `clausal/logic/parallel.py` | **New** — fork_bindings, merge_bindings_back, OrParallelSearch |
| 3 | `clausal/logic/solve.py` | `cancel_event` param in _drive_trampoline (L66+) |
| 3 | `tests/test_or_parallelism.py` | **New** — fork/merge/search tests |
| 4 | `clausal/logic/compiler.py` | _find_independent_groups (near L4978) |
| 4 | `tests/test_and_parallelism.py` | **New** |
| 5 | `clausal/logic/tabling.py` | Condition variables, wait_for_new_answers, mark_complete |
| 5 | `tests/test_concurrent_tabling.py` | **New** |

## Key Risks

1. **`_Py_atomic_*` / `Py_BEGIN_CRITICAL_SECTION` are 3.13+ internal APIs** — the `_ft_compat.h` macros handle fallback for GIL builds
2. **Re-check after lock in do_unify** — between `var_deref` returning unbound and the CS acquisition, another thread may bind the variable; the re-check + recursive retry handles this
3. **Constraint propagation re-entrancy** — hooks re-enter the engine; per-trail scoping of wakeup_list (already implemented at L1128-1138 in _variables.c) ensures isolation
4. **`PyDict_GetItemRef` vs `PyDict_GetItem`** — the former is 3.13+ only; guard with `#if PY_VERSION_HEX >= 0x030D0000` and fall back to `PyDict_GetItemWithError` + `Py_XINCREF` for older builds

## Verification

1. **Phase 1:** `python3.13t -m pytest tests/ -x` + `python3.13t -m pytest tests/test_free_threading.py -v`
2. **Phase 2:** Same as Phase 1, plus `TestConcurrentAssertRetract`
3. **Phase 3:** `python3.13t -m pytest tests/test_or_parallelism.py -v`
4. **TSAN:** Build CPython with `-fsanitize=thread`, rebuild extension with TSAN, run stress tests
5. **Benchmark:** N-queens (8/10/12) sequential vs 4-thread parallel — expect 2-3x speedup on free-threaded build
