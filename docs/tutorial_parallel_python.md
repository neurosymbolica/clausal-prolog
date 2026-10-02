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
concurrently; they share only the (read-only) clause database.

Write the query in a `.clausal` or `.seam` file, in
[goal position](python_integration.md#goal-position-if-goal-for-in-goal).
Every run of a `--` goal makes its own variables and its own Trail, so
the function is safe to call from any thread. With `graph.seam`:

```seam
edge('a', 'b'),
edge('b', 'c'),
edge('c', 'd'),

path(X, Y) <- edge(X, Y)
path(X, Y) <- (edge(X, Z), path(Z, Y))
```

```python
# paths.seam
-import_module(graph)

def reachable_from(source):
    """Every node reachable from source; safe to call from any thread."""
    return sorted(Y for Y in --graph.path(++source, Y))
```

Launch the threads from ordinary Python:

```python
import threading
import clausal, paths

sources = ["a", "b", "c", "d"]
results = [None] * len(sources)

def query_worker(idx):
    results[idx] = paths.reachable_from(sources[idx])

threads = [threading.Thread(target=query_worker, args=(i,)) for i in range(len(sources))]
for t in threads:
    t.start()
for t in threads:
    t.join()

print(results)  # [['b', 'c', 'd'], ['c', 'd'], ['d'], []]
```

**Why this works:** each query creates a fresh Trail internally, and each
thread's `StepGenerator` chain is independent. The clause database's
dispatch tables are immutable snapshots — no locking needed for reads. See
[Free-Threaded Python Support](free_threading.md) for details on the C
extension locking design.

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

From a plain `.py` file, where `--` is not available, use `solve` and
give each thread its own `Var`. Write each thread's answers to its own
slot (or use a lock) so collection does not race:

```python
import threading
from clausal import Var, solve, to_python
import graph

def search_worker(source, results, idx):
    x = Var()                        # this thread's own query variable
    results[idx] = [to_python(x.value) for _ in solve(("path", source, x), module=graph)]

sources = ["a", "b", "c", "d"]
results = [None] * len(sources)
threads = [
    threading.Thread(target=search_worker, args=(s, results, i))
    for i, s in enumerate(sources)
]
for t in threads:
    t.start()
for t in threads:
    t.join()

print(results)  # [['b', 'c', 'd'], ['c', 'd'], ['d'], []]
```

!!! tip "Keep a snapshot, not a binding"
    A `Var`'s binding is undone when the loop moves to the next answer,
    so copy what you keep while you are inside the loop.
    `clausal.to_python(x.value)` converts the answer into plain Python
    values; `clausal.logic.variables.walk(x)` keeps it as an engine term
    with every bound variable substituted. `deref(x)` follows only the
    top-level binding.

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

### Don't [`assert`/`retract`](database_ops.md) concurrently (yet)

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
