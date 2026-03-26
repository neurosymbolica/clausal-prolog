# Tutorial: Writing Thread-Safe Clausal Predicates

This tutorial explains how to write `.clausal` predicates that are safe
for concurrent use from multiple Python threads. It covers which predicates
are naturally safe, which need care, and the design patterns that work well
with parallelism.

!!! info "This page is about predicate design"
    For how to *launch* parallel queries from Python, see
    [Parallel Queries from Python](tutorial_parallel_python.md).
    For the low-level C extension details, see
    [Free-Threaded Python Support](free_threading.md).

---

## Which predicates are already thread-safe?

### Pure predicates (no side effects)

Any predicate that only unifies, backtracks, and calls other pure
predicates is safe for concurrent use. The C extension handles all the
locking internally.

```clausal
# skip
# These are all safe for concurrent queries:

Append([], YS, YS),
Append([H, *XS], YS, [H, *ZS]) <- Append(XS, YS, ZS)

Member(X, [X, *_]),
Member(X, [_, *T]) <- Member(X, T)

Factorial(0, 1),
Factorial(N, F) <- (
    N > 0,
    N1 == N - 1,
    Factorial(N1, F1),
    F == N * F1
)
```

!!! tip "Use `==` for arithmetic"
    Prefer `N1 == N - 1` over `N1 := N - 1`. The `==` operator uses
    CLP(FD) constraints, making predicates bidirectional where possible.
    `:=` forces eager evaluation in one direction only.

Each thread creates its own Vars and Trail when it calls these
predicates. The clause database is read-only during resolution —
multiple threads can walk the same dispatch tables concurrently.

### Tabled predicates

Tabled predicates memoize their answers. Currently, each query creates
its own table entries, so tabling is safe for concurrent use. Phase 5
of the parallelism roadmap will add shared memo tables where multiple
threads contribute answers to the same table.

```clausal
# skip
-private([A, B, C, D])
-table(Path/2)

Edge(A, B),
Edge(B, C),
Edge(C, D)

Path(X, Y) <- Edge(X, Y)
Path(X, Y) <- (Path(X, Z) and Edge(Z, Y))
```

Multiple threads can query `Path` concurrently. Each thread builds
its own memo table independently.

### CLP(FD) / CLP(B) / CLP(R) predicates

Constraint predicates attach attributes to variables. Under
free-threading, the per-variable critical section in `unify()` protects
attribute access. As long as each thread works with its own constraint
variables (the normal case), constraint solving is safe.

```clausal
# skip
-use(clpfd)

NQueens(N, QS) <- (
    Length(QS, N),
    QS ins 1..N,
    AllDifferent(QS),
    SafeQueens(QS),
    Label(QS)
)
```

Multiple threads can solve N-Queens for different N values concurrently.

---

## Patterns that need care

### Dynamic predicates (`assert` / `retract`)

Dynamic predicates modify the clause database at runtime. Concurrent
`assertz` and `retract` from multiple threads is **not yet safe**
(Phase 2 will add copy-on-write locking). However, asserting facts
before launching threads and then only reading is fine:

```clausal
# skip
-dynamic(counter/1)

# Set up facts before parallel queries:
counter(0)
counter(1)
counter(2)
```

```python
# skip
# Safe: assert all facts first, then query in parallel
for i in range(100):
    mod.db.assertz(...)

# Now launch threads that only READ
threads = [Thread(target=query_counter, args=(mod,)) for _ in range(8)]
```

### Side effects (I/O, Python calls)

Predicates that perform I/O or call Python functions with side effects
are safe in the sense that they won't crash, but the *ordering* of side
effects across threads is nondeterministic:

```clausal
# skip
# Output from different threads will interleave unpredictably
Log(MSG) <- py_call(print, MSG)
```

Use Python-level synchronization (locks, queues) if you need ordered output.

---

## Design guidelines for parallel-friendly predicates

### 1. Prefer pure predicates

Predicates that only unify and backtrack are trivially safe. Push
side effects to the Python caller:

```clausal
# skip
# Good: pure predicate, caller handles I/O
Solve(Input, Output) <- (
    parse(Input, Parsed),
    process(Parsed, Output)
)
```

```python
# skip
# Python caller does the I/O
for trail in call("Solve", data, result, module=mod):
    print(deref(result))  # I/O in Python, not in Clausal
```

### 2. Use ground-term arguments for shared data

Ground terms (no unbound variables) are immutable and free to share.
Pass shared data as ground arguments rather than through dynamic predicates:

```python
# skip
# Good: pass the lookup table as a ground list
big_table = [(k, v) for k, v in dataset.items()]

def worker():
    result = Var()
    for trail in call("Lookup", "key42", big_table, result, module=mod):
        print(deref(result))
```

### 3. Keep query variables per-thread

Each thread should create fresh `Var()` instances for query arguments.
Don't share an unbound variable between threads:

```python
# skip
# Good: fresh Var per thread
def worker():
    x = Var()
    for trail in call("MyPred", x, module=mod):
        results.append(deref(x))

# Bad: shared unbound Var
x = Var()
def worker():
    for trail in call("MyPred", x, module=mod):  # races on x
        ...
```

---

## Testing thread safety

You can write `.clausal` tests that exercise predicate logic, and then
test concurrent execution from Python. The `.clausal` test format
(`Test("name") <- goal`) runs sequentially in the test runner, which is
the right place to test correctness. Thread-safety stress tests belong
in Python test files (`tests/test_free_threading.py`).

### `.clausal` tests for correctness

```clausal
# skip
# Verify the predicate works correctly (sequential)
Test("append nil") <- (MyAppend([], [1, 2], R) and R is [1, 2])
Test("append cons") <- (MyAppend([1], [2, 3], R) and R is [1, 2, 3])
```

### Python tests for concurrency

```python
# skip
def test_concurrent_append():
    """Run Append from 8 threads concurrently."""
    barrier = threading.Barrier(8)

    def worker(idx):
        barrier.wait()
        for _ in range(1000):
            trail = Trail()
            r = Var()
            unify(r, None, trail)  # placeholder
            # ... call Append and verify result ...

    threads = [Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
```

---

## Summary

| Predicate type | Thread-safe? | Notes |
|----------------|:---:|-------|
| Pure (unify + backtrack only) | Yes | Naturally safe |
| Tabled | Yes | Each thread gets independent tables |
| CLP(FD) / CLP(B) / CLP(R) | Yes | Per-thread constraint variables |
| Dynamic (`assert` / `retract`) | Read-only | Concurrent writes not yet safe |
| Side effects (I/O, `py_call`) | Safe but nondeterministic | Use Python locks for ordering |
