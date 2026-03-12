# Tabling (SLG resolution)

Tabling memoises subgoal calls and their computed answers. When a recursive call encounters a subgoal that is already being evaluated, the caller *suspends* and waits for answers rather than re-entering the computation. This prevents infinite loops on left-recursive and mutually recursive predicates and is a prerequisite for well-founded semantics.

The implementation lives in `clausal.logic.tabling` (V2-4b).

---

## The problem

Plain SLD resolution (depth-first, left-to-right) diverges on left-recursive definitions. Consider transitive closure over an acyclic graph:

```
-table(path/2)

edge(1, 2),
edge(2, 3),
edge(3, 4),

path(X, Y) <- edge(X, Y)
path(X, Y) <- (
    path(X, Z),
    edge(Z, Y)
)
```

The second clause is *left-recursive*: the first body goal is `path` itself. Without tabling, `path(1, Y)` immediately recurses on `path(1, Z)`, which recurses on `path(1, Z2)`, ad infinitum — even though the graph has no cycles and the answer set is finite.

Other classic programs that require tabling:

- **Same generation** — `sg(X, Y) :- parent(P, X), sg(P, Q), parent(Q, Y)` — the recursive `sg(P, Q)` generates an unbounded search tree without memoisation.
- **Mutual recursion** — `reach_a` calls `reach_b` which calls `reach_a` on a cyclic graph. Without tabling both predicates, the mutual recursion diverges.

---

## Using tabling

Mark a predicate as tabled with the `-table` directive:

```
-table(path/2)

path(X, Y) <- edge(X, Y)
path(X, Y) <- (
    path(X, Z),
    edge(Z, Y)
)
```

The directive must appear before any clauses for that predicate. Multiple predicates can be tabled in the same module:

```
-table(reach_a/2)
-table(reach_b/2)
```

Tabled predicates are queried exactly like non-tabled ones — the tabling wrapper is transparent:

```python
from clausal.logic.variables import Var, deref
from clausal.logic.solve import call

Y = Var()
for trail in call("path", 1, Y, module=lm):
    print(deref(Y))  # 2, 3, 4
```

### Invalidation

Tabled answers are cached for the lifetime of the module. If the underlying clauses change (via `assertz`, `asserta`, or `retract` on a tabled predicate), all cached answers for that predicate are automatically invalidated. The next query recomputes from scratch.

To invalidate manually:

```python
db.abolish_table("path", 2)   # clear one predicate's cache
db.abolish_all_tables()        # clear all
```

The builtins `abolish_table/2` and `abolish_all_tables/0` are also available from within clausal code.

---

## Design

### Three-path dispatch

A tabled predicate's dispatch function is wrapped so that each call takes one of three paths based on the table state:

| Path | Condition | Behaviour |
|---|---|---|
| **COMPLETE** | Table entry exists and is complete | Yield all cached answers directly. No dispatch call. |
| **CONSUMER** | Table entry exists but still evaluating | Yield currently known answers, then *suspend*. The leader will resume this consumer when new answers arrive. |
| **LEADER** | No table entry for this subgoal | Create a new table entry, drive the original dispatch, collect answers, then run the completion phase to resume suspended consumers. |

### Variant checking

Subgoal identity is determined by *variant checking*: two calls are the same subgoal if their arguments match after replacing all unbound variables with a common placeholder. `make_subgoal_key(args, trail)` normalises each argument via `_normalize_for_key`, which:

- derefs bound variables
- replaces unbound `Var` with the `_VAR` sentinel
- recursively normalises lists, `Compound` terms, and `PredicateMeta` instances

The table store maps `(functor, arity, variant_key)` → `TableEntry`.

### Answer freezing

When a solution is found, the current arg bindings are *frozen* — fully dereferenced into a ground tuple — and stored in the `TableEntry`. Duplicate answers (by value) are suppressed via a set. Later consumers unify the original query args against each frozen answer.

### TableEntry

```python
class TableEntry:
    status: str          # "evaluating" | "complete"
    answers: list[tuple] # frozen answer tuples, in discovery order
    answer_set: set      # for O(1) duplicate detection
    suspended: list      # SuspendedConsumer instances
```

### SuspendedConsumer

```python
class SuspendedConsumer:
    generator    # the consumer's StepGenerator
    parent       # routing key for intercepting yields
    args         # call args (for unification with new answers)
    trail        # the consumer's Trail
    answers_seen # index into entry.answers — how many already yielded
```

---

## Implementation

### Trampoline-mode wrapper

The primary implementation (`make_tabled_wrapper_trampoline`) wraps a trampoline-mode dispatch function. It follows the trampoline protocol: yields `(target, value)` tuples.

**Leader path:**

1. Create a `TableEntry` with status `"evaluating"`.
2. Spawn a `StepGenerator` over the original dispatch.
3. Drive it via the trampoline protocol. Each time the inner dispatch yields a solution, freeze the args and `add_answer` to the table. If the answer is new, yield it to the leader's caller.
4. When the inner dispatch is exhausted, enter the *completion phase*.

**Consumer path:**

1. Yield all currently known answers from the table entry.
2. Register a `SuspendedConsumer` on the entry.
3. Yield `(parent, _TABLING_SUSPEND)`. The trampoline intercepts this sentinel and sends `DONE` to the consumer's parent, so the parent's while-loop exits normally.
4. When the leader resumes the consumer (sending `_TABLING_RESUME`), yield any answers accumulated since the last suspension.
5. If the table is still evaluating, re-suspend for another round.

**Completion phase:**

After the original dispatch is exhausted, the leader resumes each suspended consumer via a mini-trampoline:

1. Send `_TABLING_RESUME` to the consumer's generator.
2. Drive the consumer, intercepting yields directed at the consumer's (dead) parent:
   - `(parent, None)` → consumer found a solution → freeze and `add_answer`; if new, yield to leader's caller.
   - `(parent, DONE)` → consumer finished.
   - `(parent, _TABLING_SUSPEND)` → consumer re-suspends for the next round.
   - Other `(gen, value)` → sub-call from consumer body → forward through the mini-trampoline.
3. Repeat until a fixpoint: no new answers are discovered in a full round.
4. Send `DONE` to any remaining suspended consumers for cleanup.
5. Mark the table entry `"complete"`.

### Simple-mode wrapper

`make_tabled_wrapper_simple` provides a simpler variant for simple-mode dispatch. It uses fixpoint iteration instead of suspension:

1. Create a `TableEntry`.
2. Repeatedly run the original dispatch until no new answers appear (fixpoint).
3. Mark complete.
4. Yield all answers.

Consumer calls during evaluation yield currently known answers and return (no suspension mechanism in simple mode).

### Simple-mode adapter

`_trampoline_to_simple_adapter` bridges a trampoline-mode tabled wrapper to simple-mode callers. It creates a `StepGenerator` root and drives a mini-trampoline, yielding `None` per solution (simple protocol). It intercepts `_TABLING_SUSPEND` by sending `DONE` to the suspended generator.

### Sentinels

| Sentinel | Direction | Meaning |
|---|---|---|
| `_TABLING_SUSPEND` | consumer → trampoline | "Park me; I'm waiting for more answers" |
| `_TABLING_RESUME` | leader → consumer | "Wake up; check for new answers" |

These are distinct from the trampoline's `DONE` sentinel. The trampoline and `solutions()` function intercept `_TABLING_SUSPEND` and convert it to `DONE` so that non-tabling-aware code (callers of the tabled predicate) never sees these sentinels.

---

## Database integration

### Directive handling

The `-table(pred/arity)` directive is parsed by the import hook alongside `-dynamic` and `-discontiguous`. It calls `db.mark_tabled(functor, arity)`, which records the predicate in `Database._tabled`.

### Compilation pipeline

Tabling wrapping happens in `_compile_all_pending` (the deferred compilation entry point):

1. All predicates are compiled first (in trampoline mode).
2. In a second pass, tabled predicates are wrapped with `make_tabled_wrapper_trampoline`.

The two-pass approach ensures all cross-predicate references resolve before wrapping. This is important because the tabling wrapper captures the original dispatch function — if predicate `A` calls predicate `B`, `B`'s dispatch must be installed before `A`'s wrapper captures it.

### Table store

`Database._table_store` is a `dict` mapping `(functor, arity, variant_key)` → `TableEntry`. It is exposed as `db.table_store` (read-only property).

### Auto-invalidation

When `assertz`, `asserta`, or `retract` modify a tabled predicate's clauses, the database automatically clears all table entries for that predicate:

```python
if self.is_tabled(functor, arity):
    self.abolish_table(functor, arity)
```

---

## Why generators make tabling natural

The architecture doc notes that tabling is easier on generators than on a WAM. Here is why concretely:

**Suspension is free.** When a consumer needs to wait for more answers, it simply yields a sentinel and its execution state is frozen in the generator frame. On a WAM, this requires explicitly saving the entire environment stack, choice points, and register file.

**Resumption is a send.** The leader resumes a consumer by calling `generator.send(_TABLING_RESUME)`. The consumer picks up exactly where it left off. On a WAM, this requires restoring the saved state and re-entering the engine loop at the right instruction pointer.

**The trampoline handles routing.** The existing trampoline protocol already decouples generators from the call stack. The tabling wrapper just adds a new sentinel (`_TABLING_SUSPEND`) that the trampoline intercepts. No changes to the core trampoline or compiler were needed.

---

## Limitations

- **No well-founded semantics yet.** Tabling handles positive recursion (left-recursion, mutual recursion). Negation through cycles (`\+ p, p :- \+ p`) is not yet handled correctly — it requires WFS scheduling.
- **Variant-only tabling.** Two calls are the same subgoal only if their arguments are structurally identical (modulo unbound variables). Subsumption-based tabling (where `p(1, X)` subsumes `p(1, 2)`) is not implemented.
- **No answer subsumption.** All answers are kept. There is no mechanism for lattice-based answer combination (e.g., keeping only the maximum).
- **Side effects during incomplete evaluation.** Python code called from within a tabled predicate may observe intermediate state when the table is still evaluating. This is documented, not prevented.

---

## Test coverage

Tests are in `tests/test_tabling.py` (46 tests) and `tests/test_slg_termination.py` (20 tests).

**Unit tests** (`test_tabling.py`):
- `TableEntry` state management, duplicate suppression, ordering
- Key computation: ground scalars, bound/unbound vars, lists, compounds, variant matching
- Answer freezing and unification
- Simple-mode wrapper: basic dispatch, cache hit
- Trampoline-mode wrapper: basic, multiple answers, adapter
- Database integration: table store, abolish, auto-invalidation on assertz/retract

**Integration tests** (`test_tabling.py`):
- Tabled fibonacci (fib/2): basic, zero, one, cache hit, ground query success/failure
- Cyclic path (1→2→3→1): termination, all pairs, per-node queries, ground queries, table completion
- Multiple tabled predicates (anc/2 + desc/2): mutual use, correctness
- Import hook: directive metadata, predicate wrapping, non-tabled predicates unaffected
- Abolish and recompute

**SLG termination tests** (`test_slg_termination.py`):
- Left-recursive transitive closure on an acyclic graph — the canonical example that diverges without tabling
- Same generation (Bancilhon et al. 1986) — reflexive, sibling, cousin, cross-level, negative cases
- Mutual recursion through two tabled predicates on a cyclic graph

**Fixtures:**
- `tests/fixtures/tabled_fib.clausal` — tabled fibonacci
- `tests/fixtures/tabled_path.clausal` — tabled cyclic path (1→2→3→1)
- `tests/fixtures/tabled_left_rec.clausal` — left-recursive path on acyclic graph (1→2→3→4)
- `tests/fixtures/tabled_same_gen.clausal` — same-generation problem
- `tests/fixtures/tabled_mutual_rec.clausal` — mutual recursion via alternating link types
