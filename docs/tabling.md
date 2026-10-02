# Tabling (SLG resolution)

Tabling memoises subgoal calls and their computed answers. when a recursive call encounters a subgoal that is already being evaluated, the caller *suspends* and waits for answers rather than re-entering the computation. This prevents infinite loops on left-recursive and mutually recursive predicates and is a prerequisite for well-founded semantics.

The implementation lives in `clausal.logic.tabling`.

---

## The problem

Plain SLD resolution (depth-first, left-to-right) diverges on left-recursive definitions. Consider transitive closure over an acyclic graph:

```seam
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

Mark a predicate as tabled with the [`-table` directive](directives.md):

```seam
-table(path/2)

path(X, Y) <- edge(X, Y)
path(X, Y) <- (
    path(X, Z),
    edge(Z, Y)
)
```

The directive must appear before any clauses for that predicate. Multiple predicates can be tabled in the same module:

```seam
-table(reach_a/2)
-table(reach_b/2)

reach_a(X, X),
reach_b(X, X),
```

Tabled predicates are queried exactly like non-tabled ones — the tabling wrapper is transparent. In a `.seam` file, query with the goal-position seam:

```python
# in the same .seam file, below the clauses
def main():
    for Y in --path(1, Y):
        print(Y)            # 2, 3, 4
```

From a plain `.py` file (which cannot use `--`), use `solve(goal, module=m)` or `call` — see [Python integration](python_integration.md).

### Invalidation

Tabled answers are cached for the lifetime of the module. If the underlying clauses change (via [`assertz`, `asserta`, or `retract`](database_ops.md) on a tabled predicate — which must be declared `-dynamic`), all cached answers for that predicate are automatically invalidated. The next query recomputes from scratch.

To invalidate manually, call the builtins:

```python
if --abolish_table(path, 2): ...     # clear one predicate's cache
if --abolish_all_tables(): ...       # clear all
```

The same builtins work in a clause body (`abolish_all_tables()` — a zero-arity builtin goal is written with parentheses). The `Database` object also has `abolish_table(functor, arity)` / `abolish_all_tables()` methods, but `Database` is internal (see [Public API](public-api.md)).

---

??? abstract "Design"

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
    - type-tags `bool`/`float`/`complex` leaves so `1`, `True` and `1.0` stay distinct keys
    - recursively normalises lists, cells (plain tuples), dicts and sets

    The table store maps `(functor, arity, variant_key)` → `TableEntry`.

    ### Answer freezing

    when a solution is found, the current arg bindings are *frozen* — fully dereferenced into a ground tuple — and stored in the `TableEntry`. Duplicate answers (by value) are suppressed via a set. Later consumers unify the original query args against each frozen answer.

    ### TableEntry

    ```python
    class TableEntry:
        status: str                   # "evaluating" | "complete"
        answers: list[tuple]          # frozen answer tuples, in discovery order
        answer_set: set               # for O(1) duplicate detection
        suspended: list               # SuspendedConsumer instances
        conditions: list              # parallel to answers: frozenset[frozenset[DelayedNegation]] | _FAILED
        _current_delays: set          # accumulates DelayedNegation during current derivation
        scc_deps: set                 # evaluating ancestors consumed (mutual recursion / SCC completion)
    ```

    `conditions[i]` is a **disjunction of delay sets**, one inner set per derivation of the answer: it holds an empty inner set when some derivation is delay-free (the answer is true), only non-empty inner sets when every derivation is conditional (WFS undefined), or the `_FAILED` sentinel when every derivation was invalidated. Read it through `truth_value(i)` (`True`, `Undefined` or `False`) and `delays_for(i)` (the union of the live delay sets) rather than directly.

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

??? abstract "Implementation"

    ### Trampoline-mode wrapper

    The primary implementation (`make_tabled_wrapper_trampoline`) wraps a trampoline-mode dispatch function. It follows the trampoline protocol: yields `(target, value)` tuples.

    **Leader path:**

    1. Create a `TableEntry` with status `"evaluating"`. Push it onto the leader context stack.
    2. Spawn a `StepGenerator` over the original dispatch.
    3. Drive it via the trampoline protocol. Each time the inner dispatch yields a solution, freeze the args, snapshot `entry._current_delays` as the answer's condition set, and `add_answer` to the table. If the answer is new, yield it to the leader's caller.
    4. when the inner dispatch is exhausted, enter the *completion phase*.
    5. After completion, run `_resolve_conditions` to simplify delayed negations (WFS).
    6. Pop the leader from the context stack and mark `"complete"`.

    **Consumer path:**

    1. Yield all currently known answers from the table entry.
    2. Register a `SuspendedConsumer` on the entry.
    3. Yield `(parent, _TABLING_SUSPEND)`. The trampoline intercepts this sentinel and sends `DONE` to the consumer's parent, so the parent's while-loop exits normally.
    4. when the leader resumes the consumer (sending `_TABLING_RESUME`), yield any answers accumulated since the last suspension.
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
    5. Run `_resolve_conditions(entry, table_store)` to resolve WFS delayed negations.
    6. Pop the leader context stack.
    7. Mark the table entry `"complete"`.

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
    | `_FAILED` | internal | Marks an invalidated conditional answer (WFS) |

    `_TABLING_SUSPEND` and `_TABLING_RESUME` are distinct from the trampoline's `DONE` sentinel. The trampoline and `solutions()` function intercept `_TABLING_SUSPEND` and convert it to `DONE` so that non-tabling-aware code (callers of the tabled predicate) never sees these sentinels.

    ---

## Database integration

### Directive handling

The `-table(pred/arity)` directive is parsed by the [import hook](import.md) alongside `-dynamic` and `-discontiguous`. It calls `db.mark_tabled(functor, arity)`, which records the predicate in `Database._tabled`.

The target must be a predicate the declaring module compiles — one with clauses there, or a `-dynamic` one that will get them. `-table` on an imported predicate, on a `-specialize` alias, or on a clause-less declaration is refused at load by `compiler_v2._refuse_untablable_target`, because marking `Database._tabled` in a module that never compiles the predicate wraps nothing at all.

### Compilation pipeline

Tabled predicates are wrapped with `make_tabled_wrapper_trampoline` in `compiler._install` — the one place a compiled dispatch function is installed, reached by module load and by every runtime recompile alike. `ensure_tabled_wrapper` makes it idempotent, so the load-time second pass (`compiler_v2` step 6) does not stack a second wrapper on the first.

Installing there is what makes tabling survive `assertz`/`asserta`/`retract`: those recompile the predicate, and a recompile that installed the raw dispatch would silently drop memoisation — and, for a left-recursive predicate, termination with it.

### Table store

`Database._table_store` is a `dict` mapping `(functor, arity, variant_key)` → `TableEntry`. It is exposed as `db.table_store` (read-only property).

### Auto-invalidation

when `assertz`, `asserta`, or `retract` modify a tabled predicate's clauses, the database automatically clears all table entries for that predicate:

```python
if self.is_tabled(functor, arity):
    self.abolish_table(functor, arity)
```

`compiler._install` abolishes as well, when it re-establishes the wrapper on a recompile. That covers the mutation paths that never call `Database.assertz`/`retract` — the `retract/1` builtin deletes straight out of the owning database's clause list and clears the dispatch, and the next call recompiles through `_install`.

---

## Why generators make tabling natural

The [architecture doc](architecture.md) notes that tabling is easier on generators than on a WAM. Here is why concretely:

**Suspension is free.** when a consumer needs to wait for more answers, it simply yields a sentinel and its execution state is frozen in the generator frame. On a WAM, this requires explicitly saving the entire environment stack, choice points, and register file.

**Resumption is a send.** The leader resumes a consumer by calling `generator.send(_TABLING_RESUME)`. The consumer picks up exactly where it left off. On a WAM, this requires restoring the saved state and re-entering the engine loop at the right instruction pointer.

**The trampoline handles routing.** The existing trampoline protocol already decouples generators from the call stack. The tabling wrapper just adds a new sentinel (`_TABLING_SUSPEND`) that the trampoline intercepts. No changes to the core trampoline or compiler were needed.

---

## Well-founded semantics

when a program recurses through negation — e.g. `win(X) <- move(X, Y) and not win(Y)` with symmetric moves — standard NAF gives unsound answers because it checks immediately whether the negated goal succeeds, but that goal is still being evaluated (circular dependency). [Well-Founded Semantics (WFS)](wfs.md) provides a principled three-valued semantics (true / false / undefined) that handles this correctly.

### How it works

when evaluating `not P(args)` where `P` is tabled:

- **Complete table**: standard NAF — check if any answer matches, negate.
- **Evaluating table** (cycle detected): **delay** the negation. The derivation continues conditionally — the answer is recorded with a `DelayedNegation` condition attached.

After the SLG leader finishes driving all consumers and no new answers appear, `_resolve_conditions` runs:

1. Delayed `not P(args)` targeting a completed table with no matching answer → negation **true** → condition removed (answer becomes unconditional).
2. Delayed `not P(args)` targeting a completed table with an unconditional matching answer → negation **false** → answer invalidated.
3. Remaining conditional answers form **unfounded sets** — truth value **undefined**.

### Example: symmetric game

```seam
-table(win/1)

move(1, 2),
move(2, 1),

win(X) <- (move(X, Y), not win(Y))
```

`win(1)` depends on `not win(2)`, and `win(2)` depends on `not win(1)`. Both are unfounded — WFS assigns truth value `undefined` to both.

### Example: asymmetric game

```seam
-table(win/1)

move('a', 'b'),
move('b', 'a'),
move('a', 'c'),

win(X) <- (move(X, Y), not win(Y))
```

- `win('c')` = false (no moves from `'c'`)
- `win('a')` = true (via `move('a', 'c')`, `not win('c')` succeeds)
- `win('b')` = false (`not win('a')` fails because `win('a')` is true)

### Truth value inspection

`TableEntry.truth_value(i)` returns `True`, `False`, or the strong-Kleene `Undefined` singleton for the i-th answer based on its conditions. The [`query_wfs()`](wfs.md#the-query_wfs-api) function in `clausal.logic.solve` returns results annotated with `"_truth"` keys.

### Compiler integration

The compiler detects a negated call to a tabled predicate (`not p(...)`) and emits:

```python
_m = trail.mark()
if _naf_tabled("pred", arity, (arg0, ..., argN), trail, _table_store):
    k_stmts
trail.undo(_m)
```

`_naf_tabled` is a plain function (not a generator) — it returns `True` (negation succeeds, possibly conditionally) or `False` (negation fails). It works identically from both simple and trampoline compiled code.

Non-tabled predicates fall through to the existing inline NAF codegen (no behavior change).

### Data structures

- **`DelayedNegation(functor, arity, key, frozen_args)`** — represents a conditional dependency.
- **`TableEntry.conditions`** — list parallel to `answers`, each entry a set of delay sets (one per derivation). An empty inner set = unconditional. `_FAILED` sentinel = invalidated.
- **`TableEntry._current_delays`** — accumulates delays during the current derivation.
- **Leader context stack** — thread-local stack of `TableEntry` objects. `push_leader`/`pop_leader`/`current_leader` helpers. `_naf_tabled` attaches delays to the current leader.

---

## Limitations

- **Variant-only tabling.** Two calls are the same subgoal only if their arguments are structurally identical (modulo unbound variables). Subsumption-based tabling (where `p(1, X)` subsumes `p(1, 2)`) is not implemented.
- **No answer subsumption.** All answers are kept. There is no mechanism for lattice-based answer combination (e.g., keeping only the maximum).
- **Side effects during incomplete evaluation.** Python code called from within a tabled predicate may observe intermediate state when the table is still evaluating. This is documented, not prevented.

---

??? info "Test coverage"

    Tests are in `tests/test_tabling.py` (46 tests), `tests/test_slg_termination.py` (20 tests), and `tests/test_wfs.py` (31 tests).

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

    **WFS tests** (`test_wfs.py`):
    - `DelayedNegation`: equality, hashing, repr
    - `TableEntry` conditions: default unconditional, with delays, truth values (true/false/undefined)
    - Leader context stack: empty, push/pop, nesting
    - `_naf_tabled`: complete table (match/no match), skips failed, evaluating table delays, no entry, var args
    - `_resolve_conditions`: unconditional passthrough, resolve to true, resolve to false, unfounded self-reference, multiple delays partial resolution
    - Positive-only regression: tabled fib and cyclic path still work
    - Complete table NAF: immediate check on complete table
    - Symmetric win/move: both win(1) and win(2) are undefined
    - Asymmetric win/move: win('a') is true
    - No negation cycle: tabled with NAF but no cycle → standard behavior
    - `query_wfs` API: returns list with truth annotations

    **Fixtures:**
    - `tests/fixtures/tabled_fib.seam` — tabled fibonacci
    - `tests/fixtures/tabled_path.seam` — tabled cyclic path (1→2→3→1)
    - `tests/fixtures/tabled_left_rec.seam` — left-recursive path on acyclic graph (1→2→3→4)
    - `tests/fixtures/tabled_same_gen.seam` — same-generation problem
    - `tests/fixtures/tabled_mutual_rec.seam` — mutual recursion via alternating link types
    - `tests/fixtures/wfs_win.seam` — symmetric win/move (WFS: both undefined)
    - `tests/fixtures/wfs_win_asym.seam` — asymmetric win/move (WFS: win('a') true)

---

*See also: [Well-Founded Semantics](wfs.md) — three-valued semantics for programs with negation cycles · [Constraints](constraints.md) — attributed variables, the mechanism underlying tabling suspension · [Meta-Interpreters](metainterpreters.md) — iterative deepening as a pure-Prolog alternative to tabling for cyclic programs · [Scryer Prolog Embedding](scryer.md) — Scryer also provides tabling via `library(tabling)` · [Trealla Prolog Embedding](trealla.md) — fast lightweight alternative (no tabling support).*
