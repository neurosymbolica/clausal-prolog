# Free-Threaded Python and Clausal: A Deep Analysis

Exploring how free-threaded Python (PEP 703 / `--disable-gil`) can enable
parallelism in Clausal that subinterpreters fundamentally cannot — and the
substantial C extension and architectural work required to get there safely.

---

## 1. Background: the state of free-threaded Python

### Timeline and maturity

Free-threaded CPython has progressed through three phases:

- **Python 3.13 (Oct 2024):** Phase I — experimental `--disable-gil` build.
  Single-threaded overhead ~40%. Adaptive specializing interpreter disabled
  in multi-threaded mode.
- **Python 3.14 (Oct 2025):** Phase II — officially supported but optional
  (PEP 779 accepted). Single-threaded overhead reduced to ~9%. Specializing
  adaptive interpreter re-enabled for free-threaded builds. Incremental,
  thread-safe garbage collector. Multi-threaded CPU-bound benchmarks show
  2–3× speedup over GIL-enabled builds on 4 threads.
- **Phase III (future):** Free-threaded becomes the default build. No date
  set; depends on ecosystem adoption and Stable ABI support.

### What the runtime provides

The free-threaded build replaces the GIL with:

- **Biased reference counting.** Each object tracks its owning thread. The
  owning thread uses fast non-atomic increments/decrements; other threads use
  atomic operations. Most objects are owned and freed by their creator, so
  the fast path dominates.
- **Per-object locking via critical sections.** `Py_BEGIN_CRITICAL_SECTION(obj)`
  acquires a per-object mutex. Critical sections follow a stack discipline and
  auto-suspend if the thread would block (deadlock avoidance). Built-in
  containers (list, dict, set) use internal critical sections automatically.
- **Mimalloc allocator.** Thread-safe, high-performance allocator replacing
  pymalloc. Required because the old allocator assumed GIL protection.
- **Deferred reference counting.** Certain high-traffic objects (module
  globals, type objects) defer decref to avoid contention.
- **Thread-safe incremental GC (3.14).** The cycle collector scans in small
  bursts across generations instead of stopping all threads.

### Performance characteristics

Benchmarks on Python 3.14 show a consistent picture:

| Scenario                       | Relative to GIL-enabled 3.14 |
|-------------------------------|------------------------------|
| Single-threaded (FT build)    | ~91% (i.e. ~9% overhead)     |
| 4 threads, CPU-bound (FT)     | 2–3× faster                  |
| 8 threads, CPU-bound (FT)     | 4–6× faster (workload dependent) |
| I/O-bound (FT)                | Negligible difference         |

The single-threaded overhead comes primarily from biased reference counting
and per-object locking. The JIT (also in 3.14) helps but is still maturing —
it benefits long-running hot loops more than deeply recursive code.

---

## 2. Why free-threading matters for Clausal specifically

The subinterpreters analysis (see `SUBINTERPRETER_PARALLELISM.md`) identified
that subinterpreters enforce strict object isolation — no shared Python
objects between interpreters. This makes several forms of logic programming
parallelism impossible or impractical.

Free-threaded Python removes that constraint entirely. Multiple threads can
access the same Python objects concurrently, protected by per-object locks
rather than a global lock. This enables:

| Parallelism form        | Subinterpreters | Free-threaded |
|------------------------|-----------------|---------------|
| Independent queries     | ✓               | ✓             |
| Or-parallelism          | Partial (serialization needed) | ✓ (shared clause DB) |
| And-parallelism (independent goals) | ✗ (no shared trail) | ✓ |
| And-parallelism (dependent goals) | ✗ | Possible with care |
| Shared tabling          | ✗ (separate tables) | ✓ |
| Concurrent assert/retract | ✗ | ✓ |

The key insight: **free-threaded Python is the natural fit for Prolog-style
parallelism because Prolog's execution model assumes shared mutable state
(the binding environment, the trail, the clause database).** Subinterpreters
fight this assumption; free-threading embraces it.

---

## 3. Parallelism patterns enabled by free-threading

### 3.1 Or-parallelism with shared clause database

Or-parallelism explores alternative clauses for a goal in parallel. in_
classical systems (Aurora, Muse, ACE), the central challenge is the
**multiple environment representation problem**: multiple parallel branches
need to bind the same variable to different values simultaneously.

The parallel Prolog literature describes several solutions:

- **Binding arrays** (Warren's SRI model): each worker has a private array
  indexed by variable age. Variable access is O(1) but requires conditional
  assignment checks.
- **Environment copying** (Muse, YapOr): each worker gets a copy of the
  binding environment. Simple but O(n) copy cost at each fork.
- **Stack splitting** (Gupta & Pontelli): divide untried alternatives
  statically between workers. Lower communication than copying.

**Clausal's position is unusually favorable for environment copying.** Here's
why:

Clausal's binding environment is not a contiguous WAM stack — it's a
collection of Python objects (logic variables) linked by references, with a
trail recording bindings for backtracking. "Copying the environment" in
Clausal means:

1. **Snapshot the trail** — record the current trail mark.
2. **Deep-copy the relevant variable bindings.** Since Clausal variables are
   Python objects with a `value` slot, this means creating new `Var` objects
   with the same bindings. Unbound variables in each copy are independent.
3. **Share the clause database.** The clause database, predicate dispatch
   tables, and compiled generator functions are all read-only during search
   (unless `assert`/`retract` is used). Under free-threading, multiple
   threads can read these concurrently without locking.

Each worker thread runs its own trampoline instance, exploring a different
branch. The clause database is shared read-only; only the binding
environment and trail are per-worker.

```
Thread 1 (trampoline A):          Thread 2 (trampoline B):
  trail_A, vars_A                   trail_B, vars_B
  exploring clause 1                exploring clause 2
       |                                 |
       +---- shared clause database -----+
       +---- shared predicate index -----+
```

**The copy cost is proportional to the number of bound variables at the
fork point**, not the size of the clause database. For a fork near the top
of the search tree (where or-parallelism is most valuable), this is
typically small.

#### Implementation sketch

```python
import threading
from clausal.logic.variables import Trail, copy_bindings

def or_parallel_search(goal, clause_alternatives, current_bindings):
    """Fork search across clause alternatives in parallel."""
    results = []
    lock = threading.Lock()

    def worker(clause, bindings_snapshot):
        local_trail = Trail()
        local_bindings = copy_bindings(bindings_snapshot)
        # Each worker runs its own trampoline
        for solution in trampoline_search(goal, clause, local_bindings, local_trail):
            with lock:
                results.append(solution)

    threads = []
    for clause in clause_alternatives:
        snapshot = snapshot_bindings(current_bindings)
        t = threading.Thread(target=worker, args=(clause, snapshot))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    return results
```

#### Granularity control

Spawning a thread per choice point is too expensive. The system needs a
**granularity controller** that decides when to fork:

- **Depth threshold:** Only fork at choice points within the first K levels
  of the search tree.
- **Branching factor:** Only fork when there are ≥ N alternative clauses.
- **Worker pool:** Use a fixed-size `ThreadPoolExecutor` rather than
  unbounded thread creation. Workers pull choice points from a shared
  work queue.
- **Determinism detection:** If first-argument indexing or groundness-keyed
  dispatch has already narrowed to a single clause, there's no choice point
  — don't fork.

### 3.2 Independent and-parallelism

And-parallelism runs body goals of a clause in parallel. The key distinction
is between **independent** and **dependent** goals:

- **Independent goals** share no unbound variables. They can run in parallel
  without coordination. Example: `p(X), q(Y)` where X and Y are distinct.
- **Dependent goals** share unbound variables. They require synchronization.
  Example: `p(X), q(X)` where both goals may bind X.

Independent and-parallelism is the easier case. The compiler can statically
detect independence (no shared variables) or the runtime can check at the
fork point.

```
clause body: a(X), b(Y), c(X, Y)
             ^^^^  ^^^^
             independent (disjoint vars)
                         ^^^^^^^^^^
                         depends on both — must wait
```

Under free-threading:

1. Fork `a(X)` and `b(Y)` into separate threads, each with its own trail.
2. Both threads share the same binding environment (they touch different
   variables, so no conflicts).
3. when both complete, `c(X, Y)` runs sequentially with the combined
   bindings.

**This is the RAP (Restricted And-Parallelism) model** from the &-Prolog
and Ciao systems, adapted to Python threads.

#### The constraint store complication

CLP(FD) and CLP(R) constraints create implicit dependencies. Two goals
that appear variable-independent may both post constraints to the same
constraint store. Under free-threading, the constraint store needs internal
synchronization:

- **CLP(FD) domains:** Narrowing a variable's domain must be atomic with
  respect to other threads narrowing the same domain.
- **Propagation queues:** Constraint propagation triggered by one thread
  must not race with propagation triggered by another.
- **dif/2:** The disequality store tracks pairs of variables that must not
  unify. Concurrent additions to this store need locking.

This is solvable with per-store or per-variable critical sections, but adds
complexity.

### 3.3 Concurrent tabling (shared memo tables)

Tabling (SLG resolution) memoises subgoal calls and their answers. Under
free-threading, multiple threads can contribute answers to and consume
answers from the same table simultaneously. This enables **concurrent
bottom-up evaluation** — a significant win for Datalog-style programs.

The `TableEntry` objects (tracking status, cached answers, and suspended
consumers) become shared mutable state. Required synchronization:

- **Answer insertion:** Must be atomic. Use a lock on the table entry, or
  a lock-free concurrent set if answers are ground terms (hashable,
  immutable once created).
- **Status transitions:** `evaluating → complete` must be visible to all
  threads. Use an `Event` or condition variable to wake suspended consumers.
- **Suspended consumers:** A consumer that finds an incomplete table
  suspends (yields in the generator). Under free-threading, the suspension
  can be implemented as a thread wait on a condition variable rather than a
  cooperative generator yield.

**The interaction with well-founded semantics is delicate.** Delayed
negation and conditional answer resolution assume a sequential completion
order. Concurrent completion changes the order in which tables are completed,
potentially affecting which atoms are classified as undefined. The
correctness condition is: **the final set of unconditional answers must be
the same regardless of completion order.** This holds for well-founded
semantics (the semantics is declarative, order-independent), but the
implementation must ensure no race between delayed negation checks and
answer insertion.

### 3.4 Speculative parallelism with pruning

Prolog's cut (`!`) and Clausal's committed-choice constructs (if-then-else)
prune search branches. Under or-parallelism, a cut in one branch must
cancel all parallel branches to its right. This is the **pruning problem**
in parallel Prolog.

Under free-threading, pruning is a cancellation problem:

- Each or-parallel worker checks a shared `cancelled` flag (an atomic
  boolean or `threading.Event`).
- when a branch executes a cut (or the if-then-else commits), it sets the
  flag.
- Other workers poll the flag at each trampoline step and abort if set.
- The trampoline already provides a natural polling point — the driver loop
  checks the flag before dispatching the next continuation.

This is speculative execution: branches speculatively run in parallel,
and wasted work is discarded on pruning. The Muse system demonstrated
that speculative or-parallelism is efficient in practice — most branches
produce useful work before being pruned.

### 3.5 Concurrent assert/retract

Dynamic predicates (`assert`, `retract`) modify the clause database at
runtime. Under free-threading, these become concurrent writes to a shared
data structure.

Options:

- **Reader-writer lock on the clause database.** Reads (normal goal
  resolution) acquire a shared lock; writes (assert/retract) acquire an
  exclusive lock. This allows concurrent reads but serializes writes.
- **Copy-on-write.** Each assert/retract creates a new version of the
  affected predicate's clause list. Readers see a consistent snapshot.
  This is lockless for readers but requires garbage collection of old
  versions.
- **Per-predicate locking.** Finer-grained than a global database lock.
  assertz/retract on predicate `p/2` doesn't block resolution of `q/3`.

The copy-on-write approach aligns well with Clausal's existing predicate
dispatch tables, which are already structured as immutable lookup tables
rebuilt on modification.

---

## 4. C extension thread safety: `clausal.logic.variables`

This is the critical engineering work. The C extension handles unification,
trails, and attributed variables — all of which involve mutable state that
will be accessed from multiple threads.

### 4.1 Audit categories

Every piece of mutable state in the C extension falls into one of these
categories:

| State | Sharing pattern | Thread-safety strategy |
|-------|----------------|----------------------|
| Variable bindings (`var->value`) | Written by one thread (the binding thread), read by many | Per-variable critical section |
| Trail stack | Per-thread (each thread has its own trail) | No sharing needed — allocate per thread |
| Trail marks | Per-trail | Thread-local |
| Attribute variable stores | Potentially shared (constraints may span threads) | Per-variable critical section |
| Unification temporaries | Per-call | Stack-local, no sharing |
| Deref chains | Read-only traversal of binding chain | Safe if bindings are not concurrently modified |

The key design decision is: **which state is per-thread and which is shared?**

### 4.2 Per-thread trails

The trail records bindings so they can be undone on backtracking. in_
sequential Prolog, there is one trail. in_ or-parallel execution, each
branch has its own trail (since backtracking is branch-local).

**Recommendation:** Make trails thread-local. Each thread allocates its own
`Trail` object. The C extension should not use a global trail pointer.

```c
// WRONG — global trail
static Trail *global_trail;

// RIGHT — trail passed as parameter or stored in thread-local
typedef struct {
    Trail trail;
    // ... other per-thread state
} ThreadSearchState;

static _Thread_local ThreadSearchState *thread_state;
```

Alternatively, since Clausal already passes the trail as an explicit
parameter to compiled predicates (visible in the architecture doc's
`my_predicate(this_generator, parent, arg1, arg2, trail)` signature),
thread-local storage may not be needed — just ensure each thread passes
its own trail object.

### 4.3 Variable binding under concurrency

The central operation in Prolog is `unify(X, Y)`, which may bind variables.
Under free-threading, two threads might attempt to unify the same variable
simultaneously. This must be serialized.

Clausal's binding convention (from the architecture doc) is age-ordered:
newer variables bind to older variables. This convention is important for
thread safety because it imposes a consistent binding direction, reducing
the risk of deadlock when locking two variables simultaneously.

**Recommended approach: `Py_BEGIN_CRITICAL_SECTION2`**

CPython 3.13+ provides `Py_BEGIN_CRITICAL_SECTION2(obj1, obj2)` to lock
two objects simultaneously without deadlock (it acquires locks in a
canonical order). This is ideal for `unify(X, Y)`:

```c
static int
unify_vars(PyObject *x, PyObject *y) {
    Py_BEGIN_CRITICAL_SECTION2(x, y);
    // age-ordered binding: bind newer to older
    if (var_age(x) > var_age(y)) {
        set_binding(x, y);
        trail_push(current_trail, x);
    } else {
        set_binding(y, x);
        trail_push(current_trail, y);
    }
    Py_END_CRITICAL_SECTION2(x, y);
    return 1;
}
```

**Critical section caveat:** CPython's critical sections do *not* guarantee
exclusive access if the thread blocks inside them. The sections auto-suspend
on blocking operations. This means the binding operation inside the critical
section must not call Python code that could block (no PyObject_Call, no
memory allocation that triggers GC). For the raw `set_binding` + `trail_push`
operations in C, this should be fine.

### 4.4 Deref chain safety

`deref(X)` follows the binding chain from X to its ultimate value. Under
free-threading, another thread could be modifying the chain concurrently
(binding a variable that X's chain passes through).

Analysis:

- **Binding is monotonic in ground terms.** once a variable is bound to a
  ground value, it is never rebound (except by trail undo, which only
  happens in the owning thread during backtracking). So a deref that
  reaches a ground value is safe.
- **Binding to another variable.** If X → Y and another thread binds Y → Z,
  deref(X) might see the old Y or the new Z. Both are valid — the deref
  will just take one more step on the next call.
- **Trail undo during deref.** If thread A is deref-ing X → Y while thread
  B undoes Y's binding (backtracking), thread A could see a dangling or
  stale binding. **This is the dangerous case.**

**Mitigation:** Trail undo must only be performed by the owning thread of
that trail. If trails are per-thread (as recommended in §4.2), and variables
bound in thread A's trail are only unbound by thread A, then deref from
thread B is safe — it may see the binding or not, but it won't see a
half-undone state.

For shared variables (bound in one thread, deref'd in another), the
binding slot should be written atomically. On modern architectures, a
pointer-sized write is already atomic. The C extension should use
`_Py_atomic_store_ptr` / `_Py_atomic_load_ptr` for variable binding
slots to ensure visibility across threads without tearing.

### 4.5 Attributed variables and constraint stores

Attributed variables (used for CLP(FD), CLP(R), dif/2) carry attached
constraint data. Under free-threading:

- **Reading attributes** during unification must be safe. Use
  `Py_BEGIN_CRITICAL_SECTION(var)` when reading the attribute list.
- **Modifying attributes** (e.g., narrowing a CLP(FD) domain) must be
  atomic with respect to other threads modifying the same variable's
  attributes.
- **Constraint propagation** triggered by binding an attributed variable
  calls Python-level hook functions. These hooks may modify other
  variables. Under free-threading, propagation from different threads
  could interleave. The hooks must be re-entrant.

**Recommended approach:** Each attributed variable has a per-variable lock
(provided by CPython's critical section infrastructure). Constraint
propagation acquires the lock on each variable it modifies.

### 4.6 The `_trampoline` C extension

The C-optimised trampoline also needs auditing. If it uses any static/global
state (e.g., a global pointer to the current generator), this must be
made thread-local or passed as a parameter. Since Clausal's architecture
envisions per-thread trampolines, the trampoline should be a value type
(or thread-local) rather than a singleton.

---

## 5. Thread-safety at the Python level

Beyond the C extension, several Python-level components need attention.

### 5.1 The clause database (`clausal.logic.database`)

The clause database maps `(functor, arity)` to lists of clauses with
dispatch tables. Under free-threading:

- **Read path (goal resolution):** Multiple threads resolve goals
  concurrently. The dispatch tables (groundness-keyed, first-argument
  indexed) are read-only during resolution. Safe under free-threading if
  the tables are not mutated during reads.
- **write path (assert/retract):** Mutations must be serialized. A
  reader-writer lock or copy-on-write strategy is needed (see §3.5).

**Copy-on-write is the recommended approach.** when `assert` adds a clause:

1. Acquire write lock on the predicate.
2. Create a new clause list = old list + new clause.
3. Rebuild the dispatch table for the new list.
4. Atomically swap the predicate's clause list pointer.
5. Release write lock.

Readers never see a partially-updated dispatch table.

### 5.2 The import hook and bytecode caching

`PredicateLoader` caches compiled bytecode in `__pycache__/`. File I/O
is already thread-safe at the OS level. The import machinery in CPython
uses per-module locks to prevent double-imports. No special action needed
here, as long as the import hook doesn't use module-level mutable state
during compilation.

### 5.3 Module-level mutable state

Any module-level mutable state (global variables, caches, registries) in
Clausal's Python code becomes a potential data race under free-threading.
Audit for:

- Global predicate registries
- Module-level caches (e.g., term rewriting caches)
- Mutable default arguments (a Python anti-pattern that becomes a
  concurrency hazard)

---

## 6. Performance considerations

### 6.1 The single-threaded tax

Free-threaded Python 3.14 runs ~9% slower than the GIL-enabled build for
single-threaded code. For Clausal, where the inner loop is the trampoline
dispatching generators, this means:

- **Trampoline dispatch** involves Python generator sends/yields, which
  are single-threaded operations. The 9% overhead applies here.
- **Unification** in the C extension uses the fast path of biased reference
  counting (the owning thread). Minimal overhead.
- **Constraint propagation** triggers Python callbacks, which pay the
  biased refcount cost.

For programs that don't benefit from parallelism, the free-threaded build
is strictly worse. Users should be able to choose at runtime (GIL-enabled
for sequential programs, free-threaded for parallel).

### 6.2 Cache contention and false sharing

when multiple threads access the same variable's binding slot, CPU cache
lines bounce between cores (**true sharing**). when threads access
different variables that happen to be on the same cache line, the same
bouncing occurs (**false sharing**).

Mitigation:

- **Variable allocation alignment.** Allocate variable objects with
  padding to avoid false sharing. This wastes memory but eliminates
  cache line contention. Consider this for variables identified as
  shared across threads.
- **Immutable sharing.** Ground terms (fully instantiated) are effectively
  immutable. Sharing them across threads incurs no contention. The
  optimisation is to eagerly detect ground terms and share them freely.

### 6.3 Scaling expectations

Realistic scaling expectations for Clausal under free-threading:

- **Or-parallelism:** Near-linear speedup for programs with many
  independent choice points (e.g., puzzle solvers, combinatorial search).
  Diminishing returns when branches are very short (thread overhead
  dominates) or when most branches are pruned (wasted work).
- **Independent and-parallelism:** Speedup proportional to the number of
  independent goals. Typically 2–4 goals are independent in a clause
  body, so 2–4× is realistic.
- **Tabling:** Speedup depends on the structure of the predicate dependency
  graph. Embarrassingly parallel tables (no inter-table dependencies)
  scale well. Deeply interconnected tables serialize on answer exchange.
- **Compound parallelism:** Combining or-parallelism and and-parallelism
  (as in the ACE system) gives the best speedups but is the most complex
  to implement correctly.

---

## 7. Comparison: free-threading vs. subinterpreters for Clausal

| Dimension | Subinterpreters | Free-threading |
|-----------|----------------|----------------|
| Object sharing | None — strict isolation | Full — same heap |
| Communication cost | Serialization via Queue | Direct pointer access |
| Trail sharing | Impossible | Per-thread trails, shared vars |
| Clause DB sharing | Each interp loads its own | Shared read-only (natural) |
| Tabling sharing | Separate tables per interp | Shared tables (with locking) |
| Constraint store | Separate per interp | Shared (with per-var locking) |
| C extension requirement | Multi-phase init (PEP 489) | Thread-safe operations |
| Single-thread overhead | None (separate GILs) | ~9% (biased refcount) |
| Ecosystem maturity | Stable in 3.14 | Supported in 3.14, evolving |
| Debugging complexity | Low (isolation = safety) | High (data races, deadlocks) |
| Best use case | Independent batch queries | Shared-state search parallelism |

**Recommendation:** Use subinterpreters for embarrassingly parallel workloads
(independent queries, test parallelism). Use free-threading for search
parallelism within a single query (or-parallelism, and-parallelism, shared
tabling). The two are not mutually exclusive — they serve different use
cases.

---

## 8. Implementation roadmap

### Phase 1: Foundation (C extension thread safety)

- [ ] Audit `clausal.logic.variables` for static/global mutable state.
- [ ] Make trails explicitly per-thread (parameter-passed or thread-local).
- [ ] Add `Py_BEGIN_CRITICAL_SECTION` / `Py_BEGIN_CRITICAL_SECTION2` around
      variable binding operations in `unify()`.
- [ ] Use `_Py_atomic_store_ptr` / `_Py_atomic_load_ptr` for the variable
      binding slot.
- [ ] Audit `_trampoline` C extension similarly.
- [ ] Build and test with `--disable-gil`. Run the existing 88-test suite
      under free-threading with ThreadSanitizer.
- [ ] Mark both C extensions as free-threading compatible
      (`Py_mod_gil` slot with `Py_MOD_GIL_NOT_USED`).

### Phase 2: Thread-safe Python layer

- [ ] Implement copy-on-write for the clause database (assert/retract).
- [ ] Audit module-level mutable state across all `clausal.*` modules.
- [ ] Add per-table locking to `clausal.logic.tabling`.
- [ ] Add per-variable locking to constraint stores (CLP(FD), CLP(R), dif/2).
- [ ] Thread-safe predicate dispatch table reads.

### Phase 3: Or-parallelism

- [ ] Implement `copy_bindings(snapshot)` — snapshot the binding environment
      at a choice point.
- [ ] Implement parallel choice point exploration with a `ThreadPoolExecutor`.
- [ ] Granularity controller (depth threshold, branching factor, worker pool
      sizing).
- [ ] Pruning support (shared cancellation flags checked at trampoline steps).
- [ ] Prolog-semantics compliance: ensure solutions are returned in the
      correct (left-to-right clause) order, or provide an option for
      unordered results.

### Phase 4: Independent and-parallelism

- [ ] Static analysis in the compiler to detect independent body goals
      (disjoint variable sets).
- [ ] Runtime independence check for goals with partially-ground arguments.
- [ ] Fork-join execution of independent goals in separate threads.
- [ ] Barrier synchronisation before dependent continuation goals.

### Phase 5: Concurrent tabling

- [ ] Thread-safe answer insertion into `TableEntry`.
- [ ] Condition-variable-based consumer suspension (replacing cooperative
      generator yields for cross-thread waiting).
- [ ] Concurrent completion detection.
- [ ] Validate well-founded semantics under concurrent completion ordering.

---

## 9. Risks and open questions

### Correctness risks

- **Race in deref during trail undo.** If the per-thread trail discipline
  is violated (a thread undoes another thread's bindings), deref can read
  stale data. Strict enforcement of "only undo your own trail" is critical.
- **Constraint propagation re-entrancy.** CLP hooks may call back into the
  logic engine, potentially from a different thread's context. The
  trampoline and constraint machinery must be re-entrant.
- **Well-founded semantics under concurrency.** The three-valued model
  (true/false/undefined) is declaratively order-independent, but the
  implementation's delayed negation machinery may have implicit ordering
  assumptions. Needs formal verification or extensive testing.

### Performance risks

- **Lock contention on hot variables.** If many threads unify with the same
  variable simultaneously (e.g., a shared accumulator), the per-variable
  lock becomes a bottleneck. This is inherent to dependent and-parallelism
  and cannot be eliminated — only mitigated by choosing independence-heavy
  decompositions.
- **Biased refcount slow path.** Variables created in one thread but
  heavily used in another hit the atomic refcount path. For short-lived
  search branches, this may negate the parallelism benefit.
- **Generator overhead.** Python generators are not optimised for
  cross-thread access. If the trampoline dispatches generators created
  by other threads, the generator frame access may incur contention.

### Ecosystem risks

- **Free-threaded build availability.** Not all platforms ship FT builds
  yet. Users must explicitly install the FT variant.
- **Dependency compatibility.** If any C extension Clausal depends on
  (directly or transitively) doesn't support free-threading, importing it
  forces the GIL back on. This silently negates all parallelism.
- **Debugging difficulty.** Data races in C extensions are hard to
  diagnose. ThreadSanitizer support in CPython is improving but not
  complete.

---

## 10. Conclusion

Free-threaded Python is the right long-term technology for parallel logic
programming in Clausal. It enables the forms of parallelism — shared-trail
or-parallelism, independent and-parallelism, concurrent tabling — that
subinterpreters structurally cannot support.

The work is substantial but well-scoped: the C extension needs per-object
locking and per-thread trails, the Python layer needs copy-on-write for
the clause database and locking for the tabling system, and the compiler
needs independence analysis for and-parallelism.

The recommended sequencing is: C extension safety (Phase 1) → Python layer
safety (Phase 2) → or-parallelism (Phase 3) → and-parallelism (Phase 4)
→ concurrent tabling (Phase 5). Each phase delivers incremental value and
can be shipped independently.

Clausal's architecture — CPS + trampoline, generator-based choice points,
explicit trail passing — is well-suited to this migration. The trampoline
provides a natural polling point for cancellation, the explicit trail
parameter enables per-thread trails without global state, and the
generator-based execution model maps cleanly onto Python's threading
primitives.
