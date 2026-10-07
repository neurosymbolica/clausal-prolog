# Tutorial: Writing Thread-Safe Seam Predicates

This tutorial explains how to write seam (`.seam`) predicates that are safe
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

```seam
# These are all safe for concurrent queries:

list_concat([], YS, YS),
list_concat([H, *XS], YS, [H, *ZS]) <- list_concat(XS, YS, ZS)

factorial(0, 1),
factorial(N, F) <- (
    N > 0,
    N1 == N - 1,
    factorial(N1, F1),
    F == N * F1
)

test("concat") <- list_concat([1], [2, 3], [1, 2, 3])
test("factorial") <- factorial(5, 120)
```

!!! tip "Use `==` for arithmetic"
    Prefer `N1 == N - 1` over `eval_(N - 1, N1)`. The `==` operator uses
    CLP(ℤ) constraints, making predicates bidirectional where possible.
    `eval_/2` forces eager evaluation in one direction only.

Each thread creates its own Vars and Trail when it calls these
predicates. The clause database is read-only during resolution —
multiple threads can walk the same dispatch tables concurrently.

### Tabled predicates

Tabled predicates memoize their answers. A completed table is kept on
the module and reused: a second query for the same call does not run the
clauses again.

```seam
-table(path/2)

edge('a', 'b'),
edge('b', 'c'),
edge('c', 'a'),

path(X, Y) <- edge(X, Y)
path(X, Y) <- (path(X, Z), edge(Z, Y))

test("a reaches every node, despite the cycle") <- (
    findall(Y, path('a', Y), YS),
    msort(YS, ['a', 'b', 'c'])
)
```

Multiple threads can query `path` with the GIL enabled. Concurrent tabled
queries under free-threading are not yet covered by the thread-safety tests
(see [Free-Threaded Python Support](free_threading.md)); shared, concurrently
filled tables are later work.

### [CLP(ℤ)](constraints.md) / [CLP(B)](clpb.md) / [CLP(ℝ)](clpr.md) predicates

Constraint predicates attach attributes to variables. Under
free-threading, the per-variable critical section in `unify()` protects
attribute access. As long as each thread works with its own constraint
variables (the normal case), constraint solving is safe.

```seam
-private([safe_queens(QS), no_attack(Q, QS, D)])

n_queens(N, QUEENS) <- (
    length(QUEENS, N),
    in_domain(QUEENS, 1, N),
    all_different(QUEENS),
    safe_queens(QUEENS),
    label(QUEENS)
)

safe_queens([]),
safe_queens([Q, *QS]) <- (
    no_attack(Q, QS, 1),
    safe_queens(QS)
)

no_attack(_, [], _),
no_attack(Q, [Q1, *QS], D) <- (
    Q != Q1 + D,
    Q != Q1 - D,
    D1 == D + 1,
    no_attack(Q, QS, D1)
)

test("6 queens") <- n_queens(6, [2, 4, 6, 1, 3, 5])
```

Multiple threads can solve N-Queens for different N values concurrently.

---

## Patterns that need care

### [Dynamic](directives.md) predicates (`assert` / `retract`)

Dynamic predicates modify the clause database at runtime; only a
predicate declared `-dynamic` accepts `assertz`/`retract`. Concurrent
`assertz` and `retract` from multiple threads is **not yet safe**
(Phase 2 will add copy-on-write locking). However, asserting facts
before launching threads and then only reading is fine. In `counters.seam`:

```seam
-module(counters, [counter(N)])
-dynamic(counter/1)

counter(0),
```

```python
from threading import Thread
from clausal import Var, once, solve
import counters

# Safe: assert all facts first, then query in parallel
for i in range(1, 100):
    once(("assertz", ("counter", i)), module=counters)

def count_counters(results):
    N = Var()
    results.append(sum(1 for _ in solve(("counter", N), module=counters)))

results = []
threads = [Thread(target=count_counters, args=(results,)) for _ in range(8)]
for t in threads: t.start()
for t in threads: t.join()
print(results)  # [100, 100, 100, 100, 100, 100, 100, 100]
```

### Side effects (I/O, Python calls)

Predicates that perform I/O or call Python functions with side effects
are safe in the sense that they won't crash, but the *ordering* of side
effects across threads is nondeterministic:

```seam
# Output from different threads will interleave unpredictably
log(MSG) <- ++print(MSG)

test("log succeeds once") <- log('hello')
```

Use Python-level synchronization (locks, queues) if you need ordered output.

---

## Design guidelines for parallel-friendly predicates

### 1. Prefer pure predicates

Predicates that only unify and backtrack are trivially safe. Push
side effects to the Python caller:

```seam
# Good: a pure relation; the caller does the I/O
order_total(ITEMS, TOTAL) <- (
    findall(P, in_([_, P], ITEMS), PRICES),
    sum_list(PRICES, TOTAL)
)

test("total") <- order_total([['apple', 30], ['pear', 20]], 50)
```

```python
from clausal import Var, solve
import orders

# The Python caller does the I/O
TOTAL = Var()
for trail in solve(("order_total", [["apple", 30], ["pear", 20]], TOTAL), module=orders):
    print(TOTAL.value)  # 50
```

### 2. Use ground-term arguments for shared data

Ground terms (no unbound variables) are immutable and free to share.
Pass shared data as ground arguments rather than through dynamic predicates,
as `orders_list` is passed below.

### 3. Keep query variables per-thread

Each thread should create fresh `Var()` instances for query arguments.
Don't share an unbound variable between threads:

```python
from threading import Thread
from clausal import Var, solve
import orders

orders_list = [[["apple", 30], ["pear", n]] for n in range(8)]
results = []

# Good: each thread makes its own Var
def worker(items):
    total = Var()
    for trail in solve(("order_total", items, total), module=orders):
        results.append(total.value)

threads = [Thread(target=worker, args=(items,)) for items in orders_list]
for t in threads: t.start()
for t in threads: t.join()
print(sorted(results))  # [30, 31, 32, 33, 34, 35, 36, 37]
```

Sharing one unbound `Var` between threads (a module-level `total = Var()`
used by every worker) races on its binding. A goal-position `--` query in a
`.seam` file makes fresh variables on every run, so it cannot
share one by accident; see
[Parallel Queries from Python](tutorial_parallel_python.md).

---

## Testing thread safety

You can write `.seam` tests that exercise predicate logic, and then
test concurrent execution from Python. The [`.seam` test format](testing.md)
(`test("name") <- goal`) runs sequentially in the test runner, which is
the right place to test correctness. Thread-safety stress tests belong
in Python test files (`tests/test_free_threading.py`).

### `.seam` tests for correctness

```seam
list_concat([], YS, YS),
list_concat([H, *XS], YS, [H, *ZS]) <- list_concat(XS, YS, ZS)

# Verify the predicate works correctly (sequential)
test("concat nil") <- (list_concat([], [1, 2], R), R is [1, 2])
test("concat cons") <- (list_concat([1], [2, 3], R), R is [1, 2, 3])
```

### Python tests for concurrency

```python
import threading
from clausal import Var, solve
import orders

def test_concurrent_order_total():
    """Run order_total from 8 threads at once."""
    barrier = threading.Barrier(8)
    failures = []

    def worker(idx):
        barrier.wait()
        for _ in range(1000):
            total = Var()
            answers = [total.value for _ in solve(
                ("order_total", [["apple", 30], ["pear", idx]], total), module=orders)]
            if answers != [30 + idx]:
                failures.append((idx, answers))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not failures
```

---

## Summary

| Predicate type | Thread-safe? | Notes |
|----------------|:---:|-------|
| Pure (unify + backtrack only) | Yes | Naturally safe |
| Tabled | With the GIL | Completed tables are shared; free-threaded concurrency not yet tested |
| CLP(ℤ) / CLP(B) / CLP(ℝ) | Yes | Per-thread constraint variables |
| Dynamic (`assert` / `retract`) | Read-only | Concurrent writes not yet safe |
| Side effects (I/O, `++` calls) | Safe but nondeterministic | Use Python locks for ordering |
