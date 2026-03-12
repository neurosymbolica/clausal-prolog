# V2-4b: SLG Resolution via Trampoline Suspension — Detailed Implementation Plan

## Key Insight: The Trampoline IS the Scheduler

The trampoline loop is the single point of control flow:

```python
gen, value = root.send(None)
while gen is not None:
    gen, value = gen.send(value)
```

Every `yield` from every generator passes through this loop. That means
the trampoline can **intercept any signal** and make scheduling decisions.
This is exactly the abstraction point needed for SLG suspension.

In trampoline mode, a predicate calling a sub-predicate generates:

```python
_gen = StepGenerator(dispatch, this_generator, *args, trail)
_st = yield (_gen, None)          # trampoline drives _gen, returns result
while _st is not DONE:
    <continuation>
    _st = yield (_gen, None)      # ask for next solution
```

The caller yields `(_gen, None)` to the trampoline, which drives `_gen`.
When `_gen` finds a solution, it yields `(parent, None)` → trampoline sends
`None` back to caller → `_st = None` → while-body runs. When `_gen` exhausts,
it yields `(parent, DONE)` → trampoline sends `DONE` → while-loop exits.

**For SLG**: when a tabled consumer exhausts its currently known answers, it
yields `(parent, _TABLING_SUSPEND)`. The trampoline intercepts this: it
sends `DONE` to the parent (so the compiled while-loop exits normally and
the chain unwinds back to the leader), but **saves the consumer generator**
for later resumption. The consumer generator is a Python object on the heap,
frozen at its yield point — it IS the suspended continuation.

This requires no compiler changes — only trampoline changes and a tabled
dispatch wrapper that yields the right signals.

## Key Insight: Parent Links ARE the Continuation Chain

Every trampoline-mode generator receives `parent` as a parameter — that's
how it returns control when done (`yield (parent, DONE)` or `yield (parent, None)`).

When a consumer suspends, we save it along with its `parent` reference. Later,
when the leader runs its **completion phase** and resumes the consumer, the
consumer yields `(parent, None)` for each new answer. The parent generator
may be dead (it already exited its while-loop when we sent DONE during
suspension). But we don't need to send to the dead parent — the leader
intercepts yields directed at `consumer.parent` and handles them itself.

The parent reference is the **routing key**: it tells the leader's
mini-trampoline "this yield is a solution from this consumer, not a sub-call
to drive." Any yield where `gen is consumer.parent` is a consumer result.
Any yield where `gen` is something else is a sub-call that the mini-trampoline
drives normally.

```python
# Leader's completion phase — mini-trampoline per consumer:
for sc in entry.suspended:
    gen, value = sc.generator.send(RESUME)
    while True:
        if gen is sc.parent:
            # Consumer yielded to its parent — intercept as result
            if value is None:
                answer = freeze_args(sc.args, sc.trail)
                if entry.add_answer(answer):
                    yield (parent, None)  # propagate new answer to leader's caller
            elif value is DONE or value is _TABLING_SUSPEND:
                break  # consumer exhausted or re-suspended
        else:
            # Consumer made a sub-call — drive it through trampoline normally
            gen, value = gen.send(value)
```

This works because:
1. Fresh sub-calls inside the consumer create fresh StepGenerators (alive)
2. The consumer's own StepGenerator is alive (we saved it)
3. Only the consumer's *original parent* is dead, and we never send to it
4. The parent reference uniquely identifies "yields meant for the caller"

---

## Algorithm: SLG with Trampoline Scheduling

### Terminology

- **Subgoal**: a specific call pattern, e.g., `path(a, X)`. Identified by variant key.
- **Leader**: the first generator to call a subgoal. Drives original dispatch.
- **Consumer**: a subsequent generator calling the same subgoal while the leader
  is still running. Reads cached answers, then suspends.
- **Table entry**: stores status, answers, and suspended consumer chains.
- **Completion**: after the leader's dispatch exhausts, it resumes all suspended
  consumers to process remaining unseen answers. This may discover new answers,
  requiring further completion rounds.

### The three paths in the tabled wrapper

All three paths are generators with the trampoline signature:
`def wrapper(this_generator, parent, arg0, ..., trail):`

**Path 1 — COMPLETE (cache hit)**:
```
For each stored answer:
    unify answer with args
    if success: yield (parent, None)  # solution to caller
    undo trail
yield (parent, DONE)
```
Straightforward, no scheduling needed.

**Path 2 — LEADER (first call, no entry)**:
```
Create TableEntry(EVALUATING)
Drive original_dispatch via trampoline protocol — collecting answers:
    for each solution from original_dispatch:
        freeze answer, add to table (dedup)
        if new: yield (parent, None) to caller  — INCREMENTAL
Run completion phase:
    for each suspended consumer:
        resume consumer, drive via mini-trampoline
        intercept yields to consumer.parent as results
        new answers may trigger further completion rounds
Mark COMPLETE
yield (parent, DONE)
```

The leader yields solutions **incrementally** as they're found.
After original_dispatch exhausts, the completion phase resumes consumers.

**Path 3 — CONSUMER (recursive call, EVALUATING)**:
```
For each currently stored answer:
    unify with args → yield (parent, None)
    undo trail
Register self as suspended waiter on the table entry
yield (parent, _TABLING_SUSPEND)   ← SUSPEND signal
(Frozen here until leader's completion phase resumes us)
When resumed:
    For each new answer since last seen:
        unify with args → yield (parent, None)
        undo trail
    yield (parent, DONE)   ← or re-suspend if still evaluating
```

### How SUSPEND propagates through the trampoline

When the consumer yields `(parent, _TABLING_SUSPEND)`:

1. The trampoline sees `gen = parent, value = _TABLING_SUSPEND`
2. Instead of forwarding `_TABLING_SUSPEND` to `parent`, it sends `DONE`
3. `parent`'s while-loop exits: `_st = DONE` → loop ends
4. `parent` continues processing (next goal, next clause)
5. Control propagates up through intermediates back to the leader
6. The consumer's generator is saved in `entry.suspended`

The consumer is now parked. The leader keeps running. When the leader's
original_dispatch exhausts, the completion phase runs.

### The completion phase

After original_dispatch yields `(leader, DONE)`, the leader enters completion:

```python
# Completion loop — iterate until no new answers
while entry.suspended:
    pending = list(entry.suspended)
    entry.suspended.clear()
    for sc in pending:
        if sc.answers_seen >= len(entry.answers):
            continue  # no new answers for this consumer
        gen, value = sc.generator.send(_TABLING_RESUME)
        # Mini-trampoline: drive consumer, intercept parent-directed yields
        while True:
            if gen is sc.parent:
                if value is None:
                    # Consumer solution — freeze and publish
                    answer = freeze_args(sc.args, sc.trail)
                    if entry.add_answer(answer):
                        yield (parent, None)  # new answer to leader's caller
                elif value is DONE:
                    break
                elif value is _TABLING_SUSPEND:
                    # Consumer re-suspends (still wants more answers later)
                    entry.suspended.append(sc)
                    break
                # Ask consumer for next result
                gen, value = sc.generator.send(None)
            else:
                # Sub-call from consumer body — drive normally
                gen, value = gen.send(value)
    # If new answers were discovered, re-check suspended consumers
    # (they may have re-suspended waiting for these new answers)
```

**Why this works**:
- `sc.parent` is the routing key — it identifies yields from the consumer
  vs sub-calls the consumer makes to other predicates
- Sub-calls create fresh StepGenerators which are alive and drivable
- The dead `sc.parent` is never sent to — only used for identity comparison
- New answers discovered during completion may enable further derivations
  in other suspended consumers → the outer while-loop iterates

---

## Implementation

### Phase 0: Switch to Python trampoline

Temporarily bypass the C extension so we can modify the trampoline freely:

```python
# In trampoline.py, comment out or gate the C import:
# try:
#     from clausal.logic._trampoline import DONE, StepGenerator, trampoline, solutions
# except ImportError:
DONE: object = object()
# ... pure Python implementations
```

Once stable, translate back to C.

### Phase 1: `clausal/logic/tabling.py` — Core infrastructure

Shared between linear and SLG (identical to `TABLING_LINEAR.md` Phase 1):

```python
"""SLG tabling for clausal."""

from __future__ import annotations
from typing import Any, Callable
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.terms import Compound

# ── Sentinels ──────────────────────────────────────────────────────────────

_VAR = object()              # unbound Var placeholder in subgoal keys
_TABLING_SUSPEND = object()  # consumer → trampoline: park me
_TABLING_RESUME = object()   # leader → consumer: wake up, check for answers

# ── Table entry ───────────────────────────────────────────────────────────

class TableEntry:
    __slots__ = ("status", "answers", "answer_set", "suspended")

    def __init__(self):
        self.status: str = "evaluating"       # "evaluating" | "complete"
        self.answers: list[tuple] = []
        self.answer_set: set[tuple] = set()
        self.suspended: list = []             # list of SuspendedConsumer

    def add_answer(self, answer: tuple) -> bool:
        if answer in self.answer_set:
            return False
        self.answer_set.add(answer)
        self.answers.append(answer)
        return True


class SuspendedConsumer:
    """A consumer generator parked waiting for new answers."""
    __slots__ = ("generator", "parent", "args", "trail", "answers_seen")

    def __init__(self, generator, parent, args, trail, answers_seen):
        self.generator = generator    # the consumer's StepGenerator
        self.parent = parent          # routing key for intercepting yields
        self.args = args              # call args (for unification with new answers)
        self.trail = trail
        self.answers_seen: int = answers_seen


# ── Key computation (variant checking) ────────────────────────────────────

def _normalize_for_key(term):
    """Deref term; replace unbound Vars with _VAR sentinel."""
    term = deref(term)
    if is_var(term):
        return _VAR
    if term is None or isinstance(term, (bool, int, float, str, bytes)):
        return term
    if isinstance(term, list):
        return ("__list__",) + tuple(_normalize_for_key(e) for e in term)
    if isinstance(term, Compound):
        return (term.functor,) + tuple(_normalize_for_key(a) for a in term.args)
    if is_term_instance(term):
        return (type(term).__name__,) + tuple(
            _normalize_for_key(getattr(term, f)) for f in term_field_names(term)
        )
    return term

def make_subgoal_key(args, trail):
    """Compute variant key for a tabled call's arguments."""
    return tuple(_normalize_for_key(a) for a in args)


# ── Answer freezing ──────────────────────────────────────────────────────

def freeze_args(args, trail):
    """Capture a ground snapshot of current arg bindings."""
    from clausal.logic.solve import _deref_walk
    return tuple(_deref_walk(a) for a in args)


# ── Answer yielding ──────────────────────────────────────────────────────

def _unify_answer(args, stored, trail):
    """Unify each arg with the corresponding stored value."""
    for a, s in zip(args, stored):
        if not unify(a, s, trail):
            return False
    return True
```

### Phase 2: Simple-mode tabled wrapper (linear tabling)

Works with the current import hook (simple mode only). This is the baseline:

```python
def make_tabled_wrapper_simple(original_dispatch, functor, arity, table_store):
    """Linear tabling wrapper for simple-mode dispatch.

    Signature: dispatch(arg0, ..., trail, k) → yields None per solution.
    """

    def tabled_dispatch(*args_trail_k):
        args = args_trail_k[:arity]
        trail = args_trail_k[arity]

        key = make_subgoal_key(args, trail)
        store_key = (functor, arity, key)
        entry = table_store.get(store_key)

        # Complete — cache hit
        if entry is not None and entry.status == "complete":
            for stored in entry.answers:
                mark = trail.mark()
                if _unify_answer(args, stored, trail):
                    yield None
                trail.undo(mark)
            return

        # Consumer — yield known answers only (no suspension in simple mode)
        if entry is not None and entry.status == "evaluating":
            i = 0
            while i < len(entry.answers):
                mark = trail.mark()
                if _unify_answer(args, entry.answers[i], trail):
                    yield None
                trail.undo(mark)
                i += 1
            return

        # Leader — fixpoint loop
        entry = TableEntry()
        table_store[store_key] = entry

        changed = True
        while changed:
            old_count = len(entry.answers)
            mark = trail.mark()
            for _ in original_dispatch(*args, trail, None):
                answer = freeze_args(args, trail)
                entry.add_answer(answer)
            trail.undo(mark)
            changed = len(entry.answers) > old_count

        entry.status = "complete"
        for stored in entry.answers:
            mark = trail.mark()
            if _unify_answer(args, stored, trail):
                yield None
            trail.undo(mark)

    return tabled_dispatch
```

### Phase 3: Trampoline-mode tabled wrapper (SLG)

This is the real SLG wrapper with suspension and completion:

```python
def make_tabled_wrapper_trampoline(original_dispatch, functor, arity, table_store):
    """SLG tabling wrapper for trampoline-mode dispatch.

    Trampoline-mode signature: dispatch(this_gen, parent, arg0, ..., trail)
    Yields (target, value) tuples per trampoline protocol.
    """
    from clausal.logic.trampoline import StepGenerator, DONE

    def tabled_dispatch(this_generator, parent, *args_trail):
        args = args_trail[:arity]
        trail = args_trail[arity]

        key = make_subgoal_key(args, trail)
        store_key = (functor, arity, key)
        entry = table_store.get(store_key)

        # ── COMPLETE: yield cached answers ──
        if entry is not None and entry.status == "complete":
            for stored in entry.answers:
                mark = trail.mark()
                if _unify_answer(args, stored, trail):
                    yield (parent, None)
                trail.undo(mark)
            yield (parent, DONE)
            return

        # ── CONSUMER: yield known answers, then SUSPEND ──
        if entry is not None and entry.status == "evaluating":
            for stored in entry.answers:
                mark = trail.mark()
                if _unify_answer(args, stored, trail):
                    yield (parent, None)
                trail.undo(mark)

            # Register as suspended consumer
            sc = SuspendedConsumer(
                this_generator, parent, args, trail, len(entry.answers)
            )
            entry.suspended.append(sc)

            # SUSPEND — trampoline intercepts this, sends DONE to parent
            signal = yield (parent, _TABLING_SUSPEND)

            # Resumed by leader's completion phase with _TABLING_RESUME
            # Process any new answers that arrived while we were suspended
            while signal is _TABLING_RESUME:
                while sc.answers_seen < len(entry.answers):
                    stored = entry.answers[sc.answers_seen]
                    sc.answers_seen += 1
                    mark = trail.mark()
                    if _unify_answer(args, stored, trail):
                        yield (parent, None)
                    trail.undo(mark)
                # If table still evaluating, re-suspend
                if entry.status == "evaluating":
                    signal = yield (parent, _TABLING_SUSPEND)
                else:
                    break

            yield (parent, DONE)
            return

        # ── LEADER: drive original dispatch, then complete ──
        entry = TableEntry()
        table_store[store_key] = entry

        # Drive original dispatch through trampoline protocol
        _gen = StepGenerator(original_dispatch, this_generator, *args, trail)
        _st = yield (_gen, None)
        while _st is not DONE:
            answer = freeze_args(args, trail)
            if entry.add_answer(answer):
                yield (parent, None)  # new answer to leader's caller (incremental)
            _st = yield (_gen, None)

        # ── Completion phase ──
        # Original dispatch exhausted. Resume suspended consumers to process
        # answers they haven't seen yet. This may discover new answers,
        # requiring further rounds.
        changed = True
        while changed and entry.suspended:
            changed = False
            pending = list(entry.suspended)
            entry.suspended.clear()

            for sc in pending:
                if sc.answers_seen >= len(entry.answers):
                    # No new answers for this consumer — skip
                    continue

                old_count = len(entry.answers)

                # Resume consumer — send _TABLING_RESUME
                gen, value = sc.generator.send(_TABLING_RESUME)

                # Mini-trampoline: drive the consumer, using sc.parent as
                # the routing key to intercept consumer results vs sub-calls
                while True:
                    if gen is sc.parent:
                        # Yield directed at consumer's (dead) parent — intercept
                        if value is None:
                            # Consumer found a solution
                            answer = freeze_args(sc.args, sc.trail)
                            if entry.add_answer(answer):
                                yield (parent, None)  # propagate to leader's caller
                            # Ask consumer for next result
                            gen, value = sc.generator.send(None)
                        elif value is DONE:
                            break  # consumer finished
                        elif value is _TABLING_SUSPEND:
                            # Consumer re-suspends — save for next round
                            entry.suspended.append(sc)
                            break
                        else:
                            # Unknown value — treat as done
                            break
                    else:
                        # Sub-call from consumer body — drive through trampoline
                        gen, value = gen.send(value)

                if len(entry.answers) > old_count:
                    changed = True

        # All done — send DONE to any remaining suspended consumers
        for sc in entry.suspended:
            try:
                sc.generator.send(DONE)
            except StopIteration:
                pass
        entry.suspended.clear()

        entry.status = "complete"
        yield (parent, DONE)

    return tabled_dispatch
```

### Phase 4: Modified trampoline — `_TABLING_SUSPEND` interception

The `solutions()` function needs one small change: intercept `_TABLING_SUSPEND`
and replace it with `DONE` before forwarding to the parent.

```python
def solutions(root):
    """Yield each solution from root until DONE.

    Handles SLG tabling: _TABLING_SUSPEND is intercepted and converted to
    DONE so the parent's while-loop exits normally. The consumer remains
    saved in the table entry's suspended list for later resumption.
    """
    from clausal.logic.tabling import _TABLING_SUSPEND

    gen, value = root.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return
            yield value
            gen, value = root.send(None)
        else:
            # Intercept _TABLING_SUSPEND → send DONE to parent instead
            if value is _TABLING_SUSPEND:
                gen, value = gen.send(DONE)
            else:
                gen, value = gen.send(value)
```

That's it. **Three lines added to `solutions()`**: an `if` branch that
replaces `_TABLING_SUSPEND` with `DONE` before sending. The consumer is
already saved in the table entry (the consumer wrapper does this before
yielding `_TABLING_SUSPEND`). The leader's completion phase handles
resumption entirely within its own generator — no scheduler needed in
the trampoline.

The `trampoline()` function (single-answer variant) needs the same change
for completeness, though it's less commonly used with tabling.

### Phase 5: Database integration

Same as `TABLING_LINEAR.md`:
- `Database.__init__`: add `self._table_store: dict = {}`
- `Database.table_store` property
- `Database.abolish_table(functor, arity)`
- `Database.abolish_all_tables()`
- Auto-invalidation in `assertz`/`asserta`/`retract` when predicate is tabled

### Phase 6: Import hook wiring

Modify `_compile_all_pending` to:
1. Compile tabled predicates with `compile_predicate_trampoline`
2. Wrap with `make_tabled_wrapper_trampoline` after all compilation

```python
def _compile_all_pending(pending, db, module_dict):
    from clausal.logic.tabling import make_tabled_wrapper_trampoline
    from clausal.logic.compiler import compile_predicate, compile_predicate_trampoline

    for (functor, arity), pred_cls in pending.items():
        clauses = db.clauses_for(functor, arity)
        if db.is_tabled(functor, arity):
            compile_predicate_trampoline(functor, arity, clauses, db,
                                         globals_=module_dict, pred_cls=pred_cls)
        else:
            compile_predicate(functor, arity, clauses, db,
                              globals_=module_dict, pred_cls=pred_cls)

    # Wrap tabled predicates AFTER all compilation
    for (functor, arity), pred_cls in pending.items():
        if db.is_tabled(functor, arity):
            original_fn = pred_cls._get_dispatch() if pred_cls else db.get_dispatch(functor, arity)
            wrapped = make_tabled_wrapper_trampoline(
                original_fn, functor, arity, db.table_store)
            if pred_cls is not None:
                pred_cls._dispatch_fn = wrapped
            db.set_dispatch(functor, arity, wrapped)
```

**Important**: non-tabled predicates that CALL tabled predicates are compiled
in simple mode. Their `for _ in dispatch(...)` loop drives the tabled wrapper,
which is a trampoline-mode generator. This needs a bridge — the tabled wrapper
must also work when called from simple mode. Two options:

**Option A**: The tabled wrapper detects whether it's being called in simple
mode (no `this_generator`/`parent` args) or trampoline mode, and adapts.

**Option B**: Compile ALL predicates in a module that contains any tabled
predicate using trampoline mode.

**Option C** (recommended): The tabled wrapper is always trampoline-mode.
Wrap it in a **simple-mode adapter** for callers that use `for _ in dispatch(...)`:

```python
def _trampoline_to_simple_adapter(trampoline_dispatch, arity):
    """Adapt a trampoline-mode dispatch to simple-mode calling convention."""
    from clausal.logic.trampoline import StepGenerator, solutions

    def adapted(*args_trail_k):
        args = args_trail_k[:arity]
        trail = args_trail_k[arity]
        # k = args_trail_k[arity + 1]  # ignored
        root = StepGenerator(trampoline_dispatch, None, *args, trail)
        for _ in solutions(root):
            yield None

    return adapted
```

Install the adapted wrapper as the dispatch function. Simple-mode callers
see a normal generator. The adapter creates a StepGenerator and drives it
via `solutions()`, which handles `_TABLING_SUSPEND` interception.

### Phase 7: Builtins

Same as `TABLING_LINEAR.md`:
- `abolish_table/2` — `@_db_builtin("abolish_table", 2)`
- `abolish_all_tables/0` — `@_db_builtin("abolish_all_tables", 0)`

### Phase 8: Test fixtures and test suite

Same tests as `TABLING_LINEAR.md`, plus SLG-specific tests:

- **Cyclic path terminates** (path/2 on cyclic graph)
- **Fibonacci memoized** (fib/2 in O(n))
- **Cache hit** (second query uses COMPLETE table)
- **Ground query** (fib(5, 5) succeeds, fib(5, 6) fails)
- **Abolish table** (invalidation and recomputation)
- **Dynamic + tabled interaction** (auto-invalidation)
- **Multiple tabled predicates**
- **Same-generation problem** (classic SLG benchmark — tests completion phase)
- **Table entry status transitions** (unit tests)
- **Incremental answer yielding** (verify answers arrive during computation,
  not just at the end — distinguishes SLG from linear)

---

## Architecture Summary

```
Simple-mode caller:
    for _ in dispatch(*args, trail, k):
        <continuation>
            │
            ▼
    simple-mode adapter (creates StepGenerator, drives via solutions())
            │
            ▼
    solutions() loop ── intercepts _TABLING_SUSPEND → sends DONE
            │
            ▼
    tabled_dispatch (trampoline-mode wrapper)
        ├── COMPLETE: yield cached answers
        ├── CONSUMER: yield known, register, yield _TABLING_SUSPEND
        └── LEADER: drive original_dispatch, then completion phase
                │
                ├── original_dispatch (trampoline-mode compiled predicate)
                │       │
                │       └── body calls tabled pred → new CONSUMER
                │
                └── completion phase (mini-trampoline per consumer)
                        │
                        └── consumer.parent = routing key (intercept, don't send)
```

---

## Files to modify

| File | Change |
|------|--------|
| `clausal/logic/tabling.py` | **NEW** — TableEntry, SuspendedConsumer, make_tabled_wrapper_simple, make_tabled_wrapper_trampoline, key/freeze utilities |
| `clausal/logic/trampoline.py` | Phase 0: Python fallback. Phase 4: `_TABLING_SUSPEND` interception in `solutions()` |
| `clausal/logic/database.py` | `_table_store`, `table_store`, `abolish_table`, `abolish_all_tables`, auto-invalidate |
| `clausal/import_hook.py` | Phase 6: compile tabled predicates in trampoline mode, wrap after compilation, simple-mode adapter |
| `clausal/logic/builtins.py` | `abolish_table/2`, `abolish_all_tables/0` |
| `tests/test_tabling.py` | **NEW** — comprehensive test suite |
| `tests/fixtures/tabled_fib.clausal` | **NEW** |
| `tests/fixtures/tabled_path.clausal` | **NEW** |

---

## Phased Delivery

| Phase | What | Can test? | Depends on |
|-------|------|-----------|------------|
| 0 | Python trampoline fallback | Existing tests pass | — |
| 1 | Core infra in tabling.py | Unit tests for TableEntry, keys, freeze | — |
| 2 | `make_tabled_wrapper_simple` | path/2 terminates, fib/2 memoized | Phase 1 |
| 3 | Database + import hook + builtins (simple mode) | Full integration tests | Phase 2 |
| 4 | `_TABLING_SUSPEND` in `solutions()` | Existing trampoline tests still pass | Phase 0 |
| 5 | `make_tabled_wrapper_trampoline` + adapter | Same tests as Phase 3, via trampoline | Phase 1, 4 |
| 6 | Import hook: tabled predicates → trampoline mode | Full integration tests | Phase 5 |
| 7 | Builtins + SLG-specific tests | Same-generation, incremental answer tests | Phase 6 |

**Phases 1-3 are linear tabling** — working and testable immediately.
**Phases 4-7 upgrade to SLG** — incrementally, each phase testable.

---

## Verification

```bash
# No regressions
python3 -m pytest --ignore=tests/test_continuation_search.py -q

# Tabling tests
python3 -m pytest tests/test_tabling.py -v

# Smoke: fib(30) and cyclic path
python3 -c "
from clausal.import_hook import _load_module
from clausal.logic.variables import Var, deref
from clausal.logic.solve import call
m = _load_module('tabled_fib', 'tests/fixtures/tabled_fib.clausal')
F = Var()
for trail in call('fib', 30, F, module=m.\$module):
    print(f'fib(30) = {deref(F)}')
    break
"
```
