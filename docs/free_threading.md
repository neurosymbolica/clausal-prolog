# Free-Threaded Python Support

Clausal's C extensions (`_variables` and `_trampoline`) are compatible with
free-threaded Python (PEP 703 / PEP 779, `python3.14t`+). Under a
free-threaded build, the GIL is disabled and multiple threads execute Python
bytecode in parallel. This page documents the threading contract: what is
safe to share, what must be per-thread, and how the C extensions achieve
thread safety.

!!! note "Build requirement"
    Free-threaded Python is a separate build variant. Install it via
    `pyenv install 3.14.3t` or use your distribution's `python3.14t`
    package. Both C extensions declare `Py_MOD_GIL_NOT_USED` and work
    correctly on both GIL-enabled and free-threaded builds.

---

## Threading contract

### Safe to share between threads

| Object | Why it's safe |
|--------|---------------|
| `Var` / `AttVar` | Binding slots use atomic loads/stores. `unify()` uses per-object critical sections to prevent double-binding. |
| Ground terms (`int`, `str`, `list` of ground, `Compound` of ground) | Immutable once constructed. No synchronization needed. |
| Clause database (reads) | Compiled dispatch tables are immutable snapshots. Concurrent goal resolution is safe. |
| Attribute hook registry | `register_attr_hook` / `unregister_attr_hook` are protected by a critical section on the internal dict. |

### Must be per-thread

| Object | Why | Enforcement |
|--------|-----|-------------|
| `Trail` | Records bindings for backtracking. The `entries` array, `length`, and `capacity` are unprotected mutable state. | **Runtime check.** Each Trail records its creating thread's ID. Any mutation from a different thread raises `RuntimeError`. |
| Wakeup lists | Scoped to a single `unify()` call on a single Trail. | Internal; never exposed to user code. |

### Caller responsibilities

- **Each parallel search branch needs its own Trail.** Create a fresh `Trail()` per thread or per branch.
- **Query variables should be per-branch.** Each thread should create its own `Var()` instances for query arguments. Sharing an unbound query variable between threads means both threads race to bind it.
- **Shared variables are safe to read** (`deref`, `walk`, `is_var`) from any thread, even concurrently.
- **Binding races are serialized.** If two threads call `unify(X, a, trail1)` and `unify(X, b, trail2)` on the same unbound `X` simultaneously, the critical section serializes them: one thread binds `X`, the other retries with the now-bound value.
- **Constraint hooks must be re-entrant.** [CLP(ℤ), dif/2](constraints.md), and user-defined attribute hooks are called from within `unify()`. Under free-threading, hooks from different threads may interleave.

---

## What the C extensions do under free-threading

### `_variables.c`

| Mechanism | What it protects |
|-----------|-----------------|
| **Atomic var ID counter** (`_Atomic uint64_t g_next_var_id`) | Concurrent `Var()` creation gets globally unique IDs without locking. Uses `atomic_fetch_add` with relaxed ordering. |
| **Atomic binding slot** (`FT_ATOMIC_LOAD_PTR` / `FT_ATOMIC_STORE_PTR` on `var->binding`) | `var_deref()` reads binding chains atomically. `trail_bind()` stores new bindings atomically with correct INCREF/DECREF ordering. `trail_undo_to()` restores bindings atomically. |
| **Per-object critical sections in `do_unify()`** | Var-Var binding locks both variables (via `PyCriticalSection2_Begin`, deadlock-free canonical order). Var-Term binding locks the variable. After acquiring the lock, the code re-checks the binding — if another thread bound the variable in the interim, it releases the lock and retries with the now-bound value. |
| **Critical section on `g_attr_hooks`** | `register_attr_hook()` and `unregister_attr_hook()` lock the global dict. `fire_wakeups()` uses `PyDict_GetItemRef` (strong reference) to safely read hooks that may be concurrently modified. |
| **Trail thread ownership** | `Trail_new()` stores `PyThread_get_thread_ident()`. `trail_push`, `trail_push_attr`, `trail_push_callback`, `Trail_undo`, and `Trail_reset` all call `trail_check_owner()` and raise `RuntimeError` on mismatch. |

### `_trampoline.c`

The trampoline is per-search-branch by design: each thread creates its own
`StepGenerator` chain with its own Trail. No shared mutable state exists
in the trampoline. The extension declares `Py_MOD_GIL_NOT_USED` so it
doesn't force the GIL back on.

### GIL-build overhead

On GIL-enabled builds, all free-threading machinery compiles to no-ops:

- Atomic loads/stores become plain pointer reads/writes.
- Critical sections become `((void)0)`.
- The `FtCriticalSection` local variables are dummy `struct { int _dummy; }` — optimized away.
- Trail ownership checks remain active (they are useful for catching bugs on any build).

There is **zero runtime overhead** on GIL builds except for the Trail ownership check (one `PyThread_get_thread_ident()` comparison per `unify` and `undo` call).

---

## Portability macros (`_ft_compat.h`)

The `clausal/logic/variables/_ft_compat.h` header provides portability
macros that expand to real operations under `Py_GIL_DISABLED` and no-ops
under GIL builds:

| Macro | Free-threaded expansion | GIL expansion |
|-------|------------------------|---------------|
| `FT_ATOMIC_LOAD_PTR(ptr)` | `_Py_atomic_load_ptr_relaxed(&ptr)` | `(ptr)` |
| `FT_ATOMIC_STORE_PTR(ptr, val)` | `_Py_atomic_store_ptr_relaxed(&ptr, val)` | `ptr = val` |
| `FT_ATOMIC_UINT64_T` | `_Atomic uint64_t` | `uint64_t` |
| `FT_ATOMIC_FETCH_ADD(var, n)` | `atomic_fetch_add_explicit(...)` | `(var)++` |
| `FT_CS_BEGIN(cs, obj)` | `PyCriticalSection_Begin(cs, obj)` | `((void)(cs))` |
| `FT_CS_END(cs)` | `PyCriticalSection_End(cs)` | `((void)(cs))` |
| `FT_CS2_BEGIN(cs, a, b)` | `PyCriticalSection2_Begin(cs, a, b)` | `((void)(cs))` |
| `FT_CS2_END(cs)` | `PyCriticalSection2_End(cs)` | `((void)(cs))` |

!!! warning "CPython internal APIs"
    `_Py_atomic_load_ptr_relaxed` and `_Py_atomic_store_ptr_relaxed` are
    CPython internal APIs (prefixed with `_Py_`). They are guaranteed to
    exist on `Py_GIL_DISABLED` builds but may change between CPython
    versions. The `_ft_compat.h` macros isolate this dependency to one file.

---

## Dynamic predicates under free-threading

[`assert` and `retract`](database_ops.md) mutate the clause database. Phase 2 of the
implementation plan adds copy-on-write semantics with a write lock:

- **Readers** (goal resolution) see an immutable snapshot of the clause list.
  No locking on the read path.
- **Writers** (`assertz`, `asserta`, `retract`) acquire a per-database lock,
  build a new clause list, and atomically swap the pointer.

Until Phase 2 is implemented, concurrent `assert`/`retract` from multiple
threads is not safe. Concurrent reads are safe.

---

## Future: or-parallelism and and-parallelism

Phases 3-5 of the implementation plan will add:

- **Or-parallelism** — fork the binding environment at choice points and
  explore clause alternatives in parallel using a thread pool.
- **Independent and-parallelism** — run body goals with disjoint variable
  sets in parallel.
- **Concurrent tabling** — multiple threads contribute to and consume from
  shared memo tables.

See `implementation_plans/FREE_THREADED_PARALLELISM.md` for the full design.
