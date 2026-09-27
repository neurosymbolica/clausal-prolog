#ifndef FT_COMPAT_H
#define FT_COMPAT_H

#include <Python.h>

/*
 * Free-threaded compatibility macros.
 *
 * Under Py_GIL_DISABLED builds (3.13t+), these expand to the real
 * atomic / critical-section operations. Under normal GIL builds,
 * they collapse to plain reads/writes (the GIL provides ordering).
 *
 * ── Threading contract ──────────────────────────────────────────────
 *
 * SAFE TO SHARE between threads (read-only, or internally synchronized):
 *   - Var / AttVar objects  — bindings use atomic stores; unify() uses
 *     per-object critical sections to prevent double-binding.
 *   - Ground terms (int, str, tuple of ground) —
 *     immutable once constructed.
 *   - Clause database (for reads) — compiled dispatch tables are
 *     immutable snapshots; assert/retract use copy-on-write with a
 *     write lock (Phase 2).
 *   - The attr hook registry (g_attr_hooks) — protected by a critical
 *     section on the dict object.
 *
 * MUST BE PER-THREAD (not thread-safe, enforced by runtime check):
 *   - Trail objects — record bindings for backtracking.  Each thread
 *     must create its own Trail.  Passing a Trail to another thread
 *     raises RuntimeError.  The creating thread's ID is stored at
 *     construction and checked on every mutation.
 *   - Wakeup lists — scoped to a single unify() call on a single
 *     trail; never cross threads.
 *
 * CALLER RESPONSIBILITY:
 *   - Each parallel search branch needs its own Trail.
 *   - Variables may be shared, but only one thread should bind a given
 *     unbound variable.  The critical section in do_unify() serializes
 *     concurrent bind attempts, but the semantics of "two threads
 *     racing to bind the same variable to different values" is that
 *     one wins and the other retries with the now-bound value.
 *   - Constraint propagation hooks (CLP(FD), dif, etc.) re-enter the
 *     engine from within unify().  They must be re-entrant.
 *
 * ── Critical section implementation note ────────────────────────────
 *
 * CPython's Py_BEGIN_CRITICAL_SECTION / Py_END_CRITICAL_SECTION macros
 * are brace-structured: BEGIN opens a '{' and END closes it with '}'.
 * This makes them incompatible with early-return patterns (multiple
 * END calls for one BEGIN cause mismatched braces).
 *
 * Instead, we use the lower-level PyCriticalSection / PyCriticalSection2
 * structs and their Begin/End functions directly.  Callers declare a
 * local FtCriticalSection variable, which works with any control flow.
 */

#ifdef Py_GIL_DISABLED

#include <stdatomic.h>

/* Atomic pointer load/store — for var->binding */
#define FT_ATOMIC_LOAD_PTR(ptr)          _Py_atomic_load_ptr_relaxed(&(ptr))
#define FT_ATOMIC_STORE_PTR(ptr, val)    _Py_atomic_store_ptr_relaxed(&(ptr), (val))

/* Atomic uint64 increment — for g_next_var_id */
#define FT_ATOMIC_UINT64_T              _Atomic uint64_t
#define FT_ATOMIC_FETCH_ADD(var, n)     atomic_fetch_add_explicit(&(var), (n), memory_order_relaxed)

/* Critical sections — direct function API (not the brace macros).
 *
 * Usage:
 *   FtCriticalSection cs;
 *   FT_CS_BEGIN(&cs, obj);
 *   ... code with early returns is OK if each path calls FT_CS_END ...
 *   FT_CS_END(&cs);
 *
 *   FtCriticalSection2 cs2;
 *   FT_CS2_BEGIN(&cs2, a, b);
 *   ...
 *   FT_CS2_END(&cs2);
 */
typedef PyCriticalSection  FtCriticalSection;
typedef PyCriticalSection2 FtCriticalSection2;

#define FT_CS_BEGIN(cs, obj)         PyCriticalSection_Begin((cs), _PyObject_CAST(obj))
#define FT_CS_END(cs)                PyCriticalSection_End((cs))
#define FT_CS2_BEGIN(cs, a, b)       PyCriticalSection2_Begin((cs), _PyObject_CAST(a), _PyObject_CAST(b))
#define FT_CS2_END(cs)               PyCriticalSection2_End((cs))

#else  /* GIL-enabled: all no-ops */

#define FT_ATOMIC_LOAD_PTR(ptr)          (ptr)
#define FT_ATOMIC_STORE_PTR(ptr, val)    ((ptr) = (val))

#define FT_ATOMIC_UINT64_T              uint64_t
#define FT_ATOMIC_FETCH_ADD(var, n)     ((var)++)

/* On GIL builds the cs/cs2 variables are unused; cast to void to suppress
 * warnings.  PyCriticalSection is forward-declared but incomplete (no
 * fields) on GIL builds, so we define our own concrete dummy types. */
typedef struct { int _dummy; } FtCriticalSection;
typedef struct { int _dummy; } FtCriticalSection2;

#define FT_CS_BEGIN(cs, obj)         ((void)(cs))
#define FT_CS_END(cs)                ((void)(cs))
#define FT_CS2_BEGIN(cs, a, b)       ((void)(cs))
#define FT_CS2_END(cs)               ((void)(cs))

#endif  /* Py_GIL_DISABLED */

#endif  /* FT_COMPAT_H */
