# Tutorial: Parallel Queries from Python

This tutorial shows how to run Clausal queries in parallel from Python
using threads. It covers the rules you need to follow, common patterns,
and pitfalls.

!!! info "Prerequisites"
    You need free-threaded Python (`python3.14t`+) for true parallelism.
    On a GIL-enabled build the same code works correctly but threads
    serialize — useful for testing but no speedup.

---

## The golden rule

> **Each thread gets its own Trail and its own query variables.**

A `Trail` records bindings so they can be undone on backtracking. It is
not thread-safe — it's a mutable array with no internal locking. Clausal
enforces this at runtime: using a Trail from a thread other than the one
that created it raises `RuntimeError`.

```python
import threading
from clausal.logic.variables import Var, Trail, unify, deref

def worker():
    trail = Trail()       # each thread creates its own
    x = Var()             # each thread creates its own query vars
    unify(x, 42, trail)
    print(deref(x))       # 42

threads = [threading.Thread(target=worker) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

---

## Pattern 1: Independent queries in parallel

The simplest pattern. Multiple threads query the same compiled database
concurrently. Each thread has its own Trail and Vars — they share only
the (read-only) clause database.

```python
import threading
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.solve import call

def query_worker(module, results, idx):
    """Run a query in its own thread."""
    x = Var()
    solutions = []
    for trail in call("path", "a", x, module=module):
        solutions.append(deref(x))
    results[idx] = solutions

# Assume `mod` is a compiled Module with edge/2 and path/2
results = [None] * 4
threads = [
    threading.Thread(target=query_worker, args=(mod, results, i))
    for i in range(4)
]
for t in threads:
    t.start()
for t in threads:
    t.join()

# All threads got the same answers (order may vary)
for r in results:
    print(sorted(r))
```

**Why this works:** `call()` creates a fresh Trail internally if you
don't pass one. Each thread's `StepGenerator` chain is independent.
The clause database's dispatch tables are immutable snapshots — no
locking needed for reads.

---

## Pattern 2: Sharing ground terms

Ground terms (fully instantiated, no unbound Vars) are immutable and
safe to share freely:

```python
shared_data = [1, 2, [3, 4], "five"]   # ground — safe to share

def worker(idx):
    trail = Trail()
    x = Var()
    unify(x, shared_data, trail)
    assert deref(x) == shared_data      # reads the shared list
```

This is efficient because no copying happens — every thread reads the
same Python objects.

---

## Pattern 3: Collecting results from parallel searches

Use a lock or a per-index list to collect results without races:

```python
import threading
from clausal.logic.variables import Var, Trail, deref, walk
from clausal.logic.solve import call

def search_worker(module, functor, arg, results, idx):
    x = Var()
    solutions = []
    for trail in call(functor, arg, x, module=module):
        solutions.append(walk(x))   # walk() deep-dereferences
    results[idx] = solutions

# Run different queries in parallel
queries = [("path", "a"), ("path", "b"), ("path", "c"), ("path", "d")]
results = [None] * len(queries)
threads = [
    threading.Thread(
        target=search_worker,
        args=(mod, f, a, results, i)
    )
    for i, (f, a) in enumerate(queries)
]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

!!! tip "`deref` vs `walk`"
    `deref(x)` follows the top-level binding chain but doesn't recurse
    into lists or compounds.  `walk(x)` deeply substitutes all bound
    variables throughout a term.  Use `walk` when you want a fully
    ground snapshot to store across threads.

---

## What NOT to do

### Don't share a Trail between threads

```python
trail = Trail()   # created in main thread

def bad_worker():
    x = Var()
    unify(x, 42, trail)   # RuntimeError!

t = threading.Thread(target=bad_worker)
t.start()
t.join()
```

This raises `RuntimeError: Trail accessed from a different thread than
it was created in.`

### Don't race to bind the same unbound variable

Two threads calling `unify(X, a, trail1)` and `unify(X, b, trail2)` on
the same unbound `X` won't crash — the critical section serializes
them — but the semantics are unpredictable: one thread's binding wins,
the other retries and may fail if `a != b`.

```python
x = Var()   # shared, unbound

def worker_a():
    trail = Trail()
    unify(x, "hello", trail)   # may succeed

def worker_b():
    trail = Trail()
    unify(x, "world", trail)   # may fail if worker_a bound x first
```

The fix: give each thread its own copy of the query variables.

### Don't `assert`/`retract` concurrently (yet)

Phase 2 will add copy-on-write semantics for the clause database. Until
then, concurrent `assertz`/`retract` from multiple threads is not safe.
Concurrent reads are always safe.

---

## Checking the build

You can check at runtime whether you're on a free-threaded build:

```python
import sys

def is_free_threaded():
    return hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled()

if is_free_threaded():
    print("Free-threaded: true parallelism available")
else:
    print("GIL-enabled: threads will serialize")
```

To verify the C extensions are loaded (not the pure-Python fallbacks):

```python
from clausal.logic.trampoline import StepGenerator
assert StepGenerator.__module__ == '_trampoline', "C extension not loaded"
```

---

## Performance expectations

On free-threaded Python 3.14:

- **Single-threaded overhead:** ~9% slower than the GIL-enabled build
  (biased reference counting, per-object locking).
- **Independent queries:** Near-linear speedup. 4 threads querying the
  same database get ~3.5x throughput.
- **Shared variable contention:** If many threads unify with the same
  variable, the per-variable critical section becomes a bottleneck.
  Keep variables per-thread where possible.

The trampoline loop, unification, and constraint propagation all run
without the GIL. The C extensions (`_variables`, `_trampoline`) are
compiled with the appropriate atomic/locking primitives and declare
`Py_MOD_GIL_NOT_USED`.
