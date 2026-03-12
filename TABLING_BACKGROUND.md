# Tabling Background: Insights & Analysis for Clausal

This document captures the detailed technical analysis done while designing
the tabling implementation. It covers the algorithm landscape, how tabling
maps onto clausal's execution model, and the specific challenges and solutions
discovered during design. Refer to `TABLING_LINEAR.md` and `TABLING_SLG.md`
for the implementation plans themselves.

---

## 1. What tabling provides

Tabling (aka memoized resolution, tabulation) gives two properties:

**Termination**: Recursive predicates over cyclic data terminate instead of
looping. Without tabling, `path(a, Y)` on the graph `a→b, b→c, c→a` loops
forever because `path` calls itself with no base-case cutoff on cycles. With
tabling, the recursive call hits the table and reads cached answers instead
of recursing — breaking the cycle.

**Memoization**: Previously computed subgoals return cached answers. `fib(30, F)`
without tabling takes O(2^30) calls. With tabling, each `fib(N, F)` is computed
once and cached — O(30) total.

These are independent benefits. Some predicates need only termination (cyclic
graphs), some need only memoization (fibonacci), some need both (same-generation
problems, transitive closure on large graphs).

---

## 2. Algorithm landscape

### Linear tabling (B-Prolog, early 2000s)

Uses **re-computation** instead of suspension. Three roles:

- **Leader**: first call for a subgoal. Drives the original dispatch in a
  fixpoint loop, collecting answers. After fixpoint (no new answers), marks
  COMPLETE and yields all answers.
- **Consumer**: recursive call that hits an incomplete table. Reads currently
  known answers from the table and returns (no recursion). This breaks cycles.
- **Cache hit**: call that hits a COMPLETE table. Yields all stored answers.

The fixpoint loop is the key mechanism:
```
repeat
    run all clauses, collecting new answers
until no new answers found
```

Each iteration may discover answers that enable new derivations in subsequent
iterations. The loop converges because the answer set is monotonically growing
and finite (for finite domains).

**Strengths**: Simple, works with standard execution, no suspension machinery.
**Weaknesses**: Redundant recomputation — each fixpoint iteration re-runs ALL
clauses, not just the ones affected by new answers. Answers are batched (not
yielded incrementally to callers).

### SLG resolution (XSB Prolog, 1990s; adopted by SWI-Prolog)

Uses **suspension and resumption**. When a consumer hits an incomplete table:
1. It yields currently known answers
2. It **suspends** — its entire continuation chain is frozen
3. It registers as a waiter on the table entry
4. When the leader discovers a new answer, suspended consumers are **resumed**
   with that answer injected at their suspension point
5. The resumed continuation runs, potentially discovering more answers

**Strengths**: No redundant recomputation. Answers yielded incrementally.
Can handle predicates with infinite answer sets (consumers see answers as
they arrive). Better worst-case for deep dependency chains.
**Weaknesses**: Requires suspension/resumption mechanism. More complex
implementation. Needs careful scheduling (completion stack).

### Hybrid: Linear tabling with early publication

An optimization of linear tabling: answers are published to the shared table
immediately when found (not just between fixpoint iterations). Consumers
iterate via `while i < len(entry.answers)` which picks up answers added
*during the same iteration* by sibling consumers.

This can reduce the number of fixpoint iterations. For example, in
`path/2` on `a→b→c→a`, the leader's first pass may discover all 3 answers
in one go: as `path(b, Y)` finds `c`, that answer is immediately visible
to `path(c, Y)`'s consumer call.

In practice, this gives SLG-like convergence speed for many common patterns
while keeping the linear tabling implementation.

---

## 3. Clausal's execution model and how tabling maps onto it

### Simple mode

Compiled predicates are Python generator functions:
```python
def pred__N(arg0, ..., argN-1, trail, k):
    match (deref(arg0), ...):
        case pattern:
            ...
            yield None  # solution
```

Sub-predicate calls use `for _ in dispatch(...)`:
```python
for _ in target._get_dispatch()(*args, trail, None):
    <continuation>
```

The `for` loop consumes the generator to exhaustion. Each `yield None` is a
solution. When the generator returns, the loop ends.

**For tabling**: the tabled wrapper replaces the dispatch function. It has the
same signature `(arg0, ..., trail, k)` and yields `None` per solution. The
wrapper internally manages the table, fixpoint loop, and answer deduplication.
No compiler changes needed — the wrapper is a drop-in replacement.

**Limitation**: the `for` loop consumes the consumer generator fully. Once
the consumer returns, the loop exits and the caller moves on. There is no way
to "re-enter" the consumer later to inject new answers. This is why simple mode
is limited to linear tabling (fixpoint re-computation).

### Trampoline mode

Compiled predicates yield `(target, value)` tuples:
```python
def pred__N(this_generator, parent, arg0, ..., trail):
    match (deref(arg0), ...):
        case pattern:
            ...
            yield (parent, None)   # solution
    yield (parent, DONE)           # exhausted
```

Sub-predicate calls use the coroutine pattern:
```python
_gen = StepGenerator(target._get_dispatch(), this_generator, *args, trail)
_st = yield (_gen, None)
while _st is not DONE:
    <continuation>
    _st = yield (_gen, None)
```

Every yield passes through the central trampoline loop:
```python
gen, value = root.send(None)
while gen is not None:
    gen, value = gen.send(value)
```

**This is the key insight for SLG**: the trampoline is a single point of
control flow. Every signal from every generator passes through it. It can
intercept any signal and make scheduling decisions. The trampoline IS the
coroutine scheduler that SLG needs.

### Why the trampoline enables true SLG

In the trampoline protocol, generators don't call each other directly. They
yield to the trampoline, which routes signals between them. This means:

1. **Generators are already suspended** between yields — Python generators
   freeze their entire local state at each `yield`. This IS the delimited
   continuation that SLG needs.

2. **The trampoline can intercept any signal** — if a consumer yields
   `(parent, _TABLING_SUSPEND)` instead of `(parent, DONE)`, the trampoline
   can handle it differently: send `DONE` to the parent (so the compiled
   while-loop exits), but save the consumer's generator for later resumption.

3. **No compiler changes needed for basic SLG** — the compiled while-loop
   only checks `_st is not DONE`. The trampoline translates `_TABLING_SUSPEND`
   to `DONE` before the parent sees it. The parent doesn't know the difference.

4. **The consumer's generator persists** — it's a Python object on the heap.
   Even after the parent moves on, the consumer generator is still frozen at
   its yield point. We can resume it later by calling `.send()`.

### Re-entering suspended consumers: parent links as routing keys

When a consumer suspends and the trampoline sends DONE to its parent,
the parent's while-loop exits and the chain unwinds back to the leader.
The consumer is parked (saved in the table entry's `suspended` list).

The apparent challenge: when the leader later wants to resume the consumer,
the consumer yields `(parent, None)` for each new answer — but the parent
generator is dead (it already exited its while-loop and continued).

**The solution: the parent reference is a routing key, not a send target.**

Every trampoline-mode generator receives `parent` as a parameter — it's
how generators return control to their caller. When a consumer is created,
it captures `parent` = the StepGenerator that spawned it. When the consumer
suspends, we save this reference alongside the consumer's generator.

During the leader's **completion phase**, the leader resumes the consumer
and runs a **mini-trampoline** that intercepts all yields. The mini-trampoline
uses `consumer.parent` as a routing key:

- `gen is consumer.parent` → this is a result from the consumer (solution,
  DONE, or re-suspend). Handle it directly.
- `gen` is something else → this is a sub-call the consumer made. Drive it
  through the trampoline normally (it's a fresh StepGenerator, alive and well).

```python
# Leader's completion phase:
for sc in entry.suspended:
    gen, value = sc.generator.send(RESUME)
    while True:
        if gen is sc.parent:
            # Consumer yielding to its (dead) parent — intercept
            if value is None:
                # solution — freeze and publish
                ...
            elif value is DONE:
                break
        else:
            # Sub-call — drive normally
            gen, value = gen.send(value)
```

**Why this works**:
1. The consumer's generator is alive (saved as a Python heap object)
2. Fresh sub-calls inside the consumer create fresh StepGenerators (alive)
3. The dead parent is NEVER sent to — only used as an identity check
4. The parent reference uniquely identifies "yields meant for my caller"
   vs "yields to sub-calls I need driven"

This eliminates the need for a complex completion stack or scheduler. The
leader simply runs a local trampoline loop per consumer, using `is` identity
on the parent reference to route yields. No suspension/resumption machinery
in `solutions()` beyond the three-line `_TABLING_SUSPEND → DONE` interception.

### The practical middle ground

For the initial implementation, linear tabling through simple mode gives:
- Termination and memoization (the primary goals)
- Early answer publication (consumers see answers during same fixpoint iteration)

The upgrade to true SLG adds:
1. Trampoline compilation for tabled predicates
2. `_TABLING_SUSPEND` signal + three-line interception in `solutions()`
3. Completion phase in the leader using the parent-link mini-trampoline

---

## 4. Parent links and the continuation chain

Every trampoline-mode generator receives two special parameters:
- `this_generator`: its own StepGenerator wrapper (for self-referencing)
- `parent`: the StepGenerator that spawned it (for returning results)

These form a linked list: each generator points to its parent, all the way
up to the root (where `parent = None`).

```
root (parent=None)
  → leader_wrapper (parent=root)
    → original_dispatch (parent=leader)
      → intermediate_body (parent=original_dispatch)
        → consumer_wrapper (parent=intermediate_body)
```

When a generator yields `(parent, value)`, the trampoline sends `value` to
`parent`. This is how results propagate up the chain: `yield (parent, None)`
means "I found a solution for my caller."

**For SLG tabling, parent links serve three purposes:**

1. **Suspension signal routing**: The consumer yields `(parent, _TABLING_SUSPEND)`.
   The trampoline sees `gen = parent` and intercepts `_TABLING_SUSPEND` before
   it reaches parent, replacing it with `DONE`.

2. **Generator preservation**: The consumer's StepGenerator is a Python heap
   object. Even after the parent moves on, the consumer's generator is still
   alive, frozen at its yield point. It can be resumed later by calling
   `.send()` on it.

3. **Completion-phase routing key**: When the leader resumes a consumer during
   completion, the consumer yields to its parent (which is dead). The leader
   runs a mini-trampoline that uses `gen is consumer.parent` as an identity
   check to distinguish "results for me" from "sub-calls that need driving."
   The dead parent is never sent to — only compared by identity.

This is the critical mechanism that makes SLG tractable in this codebase.
Without parent links, the leader would need a complex scheduler to track
which yields belong to which consumer. With parent links, it's a simple
`is` check in a loop.

---

## 5. Subgoal variant checking

Two calls are **variants** if they have the same structure with variables in
the same positions:

| Call A | Call B | Variant? | Key |
|--------|--------|----------|-----|
| `path(a, X)` | `path(a, Y)` | Yes | `(a, _VAR)` |
| `path(a, X)` | `path(b, X)` | No | `(a, _VAR)` vs `(b, _VAR)` |
| `fib(5, X)` | `fib(5, Y)` | Yes | `(5, _VAR)` |
| `fib(X, Y)` | `fib(5, Y)` | No | `(_VAR, _VAR)` vs `(5, _VAR)` |

The key computation must:
- `deref` all Vars (follow trail bindings)
- Replace unbound Vars with a sentinel (`_VAR`)
- Recurse into compound structures (lists, Compound, dataclass instances)
- Produce hashable, comparable values (tuples, not lists)

```python
def _normalize_for_key(term):
    term = deref(term)
    if is_var(term):
        return _VAR
    if isinstance(term, list):
        return ("__list__",) + tuple(_normalize_for_key(e) for e in term)
    if isinstance(term, Compound):
        return (term.functor,) + tuple(_normalize_for_key(a) for a in term.args)
    if is_term_instance(term):
        return (type(term).__name__,) + tuple(
            _normalize_for_key(getattr(term, f)) for f in term_field_names(term)
        )
    return term  # scalars, None, bool, etc.
```

Lists are tagged with `"__list__"` to distinguish `[1, 2]` from `Compound("f", (1, 2))`.

---

## 6. Answer freezing and consumption

### Freezing

At each solution, capture a ground snapshot of the args as they're currently
bound through the trail:

```python
def freeze_args(args, trail):
    from clausal.logic.solve import _deref_walk
    return tuple(_deref_walk(a) for a in args)
```

`_deref_walk` from `solve.py` recursively dereferences all Vars, walking into
Compound, KWTerm, dataclass, and list structures. Unbound Vars remain as Var
objects in the frozen answer (non-ground answers).

Frozen answers are stored as tuples for hashability (dedup via `answer_set`).

**Non-ground answers**: For V2-4, most tabled predicates produce ground answers
(fib, path with ground nodes). Non-ground answers (e.g., `member(X, [1,2,3])`
producing `X=1`, `X=2`, `X=3`) work correctly because `_deref_walk` resolves
bound Vars and leaves unbound ones. However, dedup of non-ground answers
requires care — two frozen answers with different unbound Var objects should
be considered the same if they have the same structure. This is a future
enhancement; for now, each Var is a distinct object so non-ground answers
may have duplicates (harmless but wasteful).

### Consumption

When yielding from the table, unify each stored answer with the caller's args:

```python
for stored in entry.answers:
    mark = trail.mark()
    if _unify_answer(args, stored, trail):
        yield None  # solution (simple mode) or yield (parent, None) (trampoline)
    trail.undo(mark)
```

The mark/undo ensures each answer attempt is independent. If unification
succeeds, the caller's Vars are bound through the trail. After yielding
(the caller processes the solution), undo restores the trail for the next
answer attempt.

---

## 7. Fixpoint convergence and early publication

### Basic fixpoint (linear tabling)

```python
changed = True
while changed:
    old_count = len(entry.answers)
    mark = trail.mark()
    for _ in original_dispatch(*args, trail, None):
        answer = freeze_args(args, trail)
        entry.add_answer(answer)  # dedup via answer_set
    trail.undo(mark)
    changed = len(entry.answers) > old_count
```

**Convergence proof**: The answer set grows monotonically (answers are never
removed). Each fixpoint iteration either adds at least one new answer or
terminates. For finite domains, the total number of possible answers is
bounded, so the loop must terminate.

**Iteration count**: In the worst case, each iteration discovers one new
answer. For `path/2` on a graph with N nodes, at most N answers, so at most
N fixpoint iterations. For `fib/2` up to N, at most N answers.

### Early publication optimization

The consumer iterates by index:
```python
i = 0
while i < len(entry.answers):
    stored = entry.answers[i]
    ...
    i += 1
```

Because `entry.answers` is a shared mutable list, answers added by the leader
(or by sibling consumers within the same fixpoint iteration) are visible
immediately. The `while i < len(entry.answers)` condition re-checks the length
on each iteration, picking up newly added answers.

This can collapse multiple fixpoint iterations into one. Example:

```
path(X, Y) <- edge(X, Y).
path(X, Y) <- edge(X, Z), path(Z, Y).

Graph: a→b, b→c, c→a
```

Leader calls `path(a, Y)`:
1. Clause 1: `edge(a, b)` → answer `path(a, b)`. Published immediately.
2. Clause 2: `edge(a, b)`, consumer `path(b, Y)`:
   - Consumer is itself a leader for `path(b, Y)`
   - Its clause 1: `edge(b, c)` → answer `path(b, c)`. Published.
   - Its clause 2: `edge(b, c)`, consumer `path(c, Y)`:
     - Leader for `path(c, Y)`
     - Clause 1: `edge(c, a)` → answer `path(c, a)`. Published.
     - Clause 2: `edge(c, a)`, consumer `path(a, Y)`:
       - Hits EVALUATING table for `path(a, Y)`. Reads answers.
       - `path(a, b)` is there → yields Y=b → answer `path(c, b)`.
       - With early pub: `path(a, b)` was published in step 1, visible now.
     - Back in `path(c, Y)` leader: collects `path(c, a)` from clause 1
       and `path(c, b)` from consumer's derivation. Fixpoint check: 2 answers.
       Next iteration: consumer `path(a, Y)` now also sees... etc.

The point: answers flow between consumers within the same leader iteration
via the shared table, reducing the number of explicit fixpoint re-runs.

---

## 8. Interaction with other features

### Dynamic predicates

When `assertz`/`asserta`/`retract` modify a tabled predicate's clauses, the
cached answers may be stale. The table must be invalidated.

**Auto-invalidation** (recommended): `Database.assertz`/`asserta`/`retract`
check if the predicate is tabled and call `abolish_table` automatically.

```python
def assertz(self, clause):
    functor, arity = head_key(clause.head)
    key = (functor, arity)
    self._clauses.setdefault(key, []).append(clause)
    if key in self._dispatch:
        self._dispatch[key] = None
    if key in self._tabled:
        self.abolish_table(functor, arity)
```

### Lazy recompile

When a tabled predicate is recompiled (e.g., after dynamic assertion), the
fresh dispatch function is unwrapped. The tabling wrapper must be re-applied.

Solution: the lazy recompile closure wraps the recompiled function:

```python
def _rewrap_lazy():
    new_fn = old_lazy()  # recompile
    return make_tabled_wrapper(new_fn, functor, arity, db.table_store)
```

### Groundness-keyed dispatch (V2-2)

The tabled wrapper sits ABOVE the dispatch function (which includes indexing).
The call chain is:

```
caller → tabled_wrapper → indexed_dispatch → clause_bucket → clause_body
```

The wrapper intercepts ALL calls before they reach the indexed dispatch.
This is correct — the wrapper needs to see every call to manage the table.

### Directives

The `-table(pred/arity)` directive is already parsed and stored as
`db._tabled` metadata (V2-D). The import hook queries `db.is_tabled()` to
decide which predicates to wrap.

### .pyc caching (V2-3)

The tabling wrapper is applied AFTER bytecode execution, in
`_compile_all_pending`. The .pyc cache stores the pre-wrapper bytecode.
This is correct — the wrapper is a runtime object, not compiled into bytecode.

---

## 9. Trail state and tabling

The trail is critical for correct tabling. Key invariants:

1. **Freeze before undo**: After each solution from original_dispatch, freeze
   the answer BEFORE undoing the trail. Freezing captures the current bindings.

2. **Undo after each fixpoint iteration**: The leader's trail state must be
   clean between fixpoint iterations. `mark()`/`undo()` around the entire
   iteration ensures this.

3. **Mark/undo around each answer consumption**: When yielding cached answers,
   each `unify(args, stored_answer)` must be wrapped in mark/undo so that
   bindings from one answer don't leak into the next.

4. **Consumer trail independence**: In SLG, suspended consumers have their own
   trail marks. When resumed, their trail state must be compatible with the
   current state. This is automatically handled if consumers use `mark()`
   before yielding answers and `undo()` after each attempt.

---

## 10. Table store design

The table store is a dict on the Database:

```python
self._table_store: dict[tuple, TableEntry] = {}
```

Keys are `(functor, arity, subgoal_key)` tuples. The subgoal_key is the
variant-normalized argument tuple (see section 4).

This means different call patterns for the same predicate have separate table
entries. `path(a, X)` and `path(b, X)` are separate entries with independent
answer sets. `path(a, X)` and `path(a, Y)` share an entry (variant match).

### Table store lifetime

- Created when Database is initialized (empty dict)
- Entries added when leader creates them
- Entries persist until explicitly abolished or database is garbage-collected
- `abolish_table(f, a)` removes all entries with matching functor/arity
- `abolish_all_tables()` clears the entire store
- Dynamic assertion auto-clears affected entries

---

## 11. Comparison with WAM-based implementations

Traditional Prolog systems implement tabling at the WAM (Warren Abstract
Machine) level, with direct access to the choice point stack, trail, and
heap. They can:
- Copy terms between the heap and table store efficiently
- Freeze/thaw entire stack segments for SLG suspension
- Share structure between table entries and the heap

Clausal compiles to Python generators, not WAM instructions. The key
differences:

| Aspect | WAM-based | Clausal |
|--------|-----------|---------|
| Term storage | WAM heap | Python objects (on Python heap) |
| Trail | WAM trail (integer offsets) | C extension Trail (Var/value pairs) |
| Choice points | WAM stack frames | Generator yield points |
| Suspension | Stack freeze/thaw | Generator save/restore (Python's GC keeps them alive) |
| Answer copying | Heap-to-table copy | `_deref_walk` deep copy |
| Dispatch | WAM instruction pointer | Python function reference |

Python generators are actually a good fit for tabling because:
- They ARE delimited continuations (yield suspends, send resumes)
- They're garbage-collected heap objects (no stack management)
- The trampoline provides a scheduling point (equivalent to the WAM's instruction dispatch loop)
- `_deref_walk` provides term copying (equivalent to heap-to-table copy)

The main cost vs WAM: Python object overhead for frozen answers (each answer
is a tuple of Python objects). For large tables this could be significant.
Optimization: interning common answer patterns, using compact representations.
But for typical tabled predicates (path, fib, same-generation) the tables are
small enough that this doesn't matter.
