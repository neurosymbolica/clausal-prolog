# V2-4a: Linear Tabling — Detailed Implementation Plan

## Algorithm Overview

Linear tabling (B-Prolog style) uses **re-computation** instead of suspension.
When a recursive call hits an incomplete table, it reads currently known answers
and fails (no recursion). The **leader** re-runs the entire computation until no
new answers appear (fixpoint). Simple, works with standard generators.

```
caller → tabled_wrapper → original_dispatch (compiled function)
                            ↓ (body goals)
                          tabled_wrapper (recursive call → consumer path)
```

Three paths:
1. **Leader** (first call, no table entry): Create entry, run fixpoint loop, mark COMPLETE, yield answers.
2. **Consumer** (recursive call, status=COMPUTING): Yield current answers from table. Return. Breaks cycle.
3. **Cache hit** (status=COMPLETE): Yield all stored answers. No recomputation.

### Fixpoint iteration (leader)

```python
entry = TableEntry(COMPUTING, answers=[])
repeat:
    old_count = len(entry.answers)
    mark = trail.mark()
    for _ in original_dispatch(*args, trail, None):
        answer = freeze_args(args, trail)
        if answer not in entry.answer_set:
            entry.answer_set.add(answer)
            entry.answers.append(answer)
    trail.undo(mark)
until len(entry.answers) == old_count  # fixpoint
entry.status = COMPLETE
yield from _yield_answers(entry.answers, args, trail)
```

### Tradeoffs

- **Pro**: Works with existing simple-mode generators — no trampoline changes needed
- **Pro**: ~200-300 lines of new code
- **Pro**: Handles all target use cases (path/2 termination, fib/2 memoization)
- **Con**: Re-computation overhead in fixpoint iteration
- **Con**: Answers collected to fixpoint before yielding to caller (batch, not incremental)

### Path to SLG (see `TABLING_SLG.md`)

This plan is Phase 1-4 of the phased SLG roadmap. ALL infrastructure built
here is reused by SLG:
- `TableEntry`, `_normalize_for_key`, `make_subgoal_key`, `freeze_args` — reused directly
- `_table_store` on Database — reused directly
- `abolish_table`/`abolish_all_tables` builtins — reused directly
- Import hook wrapping — structure reused (swap `make_tabled_wrapper_simple` → `make_tabled_wrapper_trampoline`)
- Test suite — all tests remain valid

The SLG upgrade path (Phases 5-7 in `TABLING_SLG.md`):
1. Add `make_tabled_wrapper_trampoline` (linear tabling through trampoline protocol)
2. Switch tabled predicates to `compile_predicate_trampoline` in import hook
3. Add `_TABLING_SUSPEND` signal + modified `solutions()` for true SLG suspension

---

## Phase 1: `clausal/logic/tabling.py` (NEW)

### Data structures

```python
_VAR = object()  # sentinel for unbound Vars in subgoal keys

class TableEntry:
    __slots__ = ("status", "answers", "answer_set")

    def __init__(self):
        self.status = "computing"       # "computing" | "complete"
        self.answers: list[tuple] = []  # ordered list of frozen answers
        self.answer_set: set[tuple] = set()  # for O(1) dedup

    def add_answer(self, answer: tuple) -> bool:
        """Add answer if new. Returns True if added."""
        if answer in self.answer_set:
            return False
        self.answer_set.add(answer)
        self.answers.append(answer)
        return True
```

### Key computation (variant checking)

Two calls are **variants** if they have the same structure with variables in
the same positions. `path(a, X)` and `path(a, Y)` → same key.

```python
def _normalize_for_key(term):
    """Deref term; replace unbound Vars with _VAR sentinel. Recurse into structures."""
    from clausal.logic.variables import deref, is_var
    term = deref(term)
    if is_var(term):
        return _VAR
    if term is None or isinstance(term, (bool, int, float, str, bytes)):
        return term
    if isinstance(term, list):
        return tuple(_normalize_for_key(e) for e in term)  # lists → tuples for hashability
    if isinstance(term, Compound):
        return (term.functor,) + tuple(_normalize_for_key(a) for a in term.args)
    if is_term_instance(term):
        return (type(term).__name__,) + tuple(
            _normalize_for_key(getattr(term, f)) for f in term_field_names(term)
        )
    return term  # other ground values pass through

def make_subgoal_key(args, trail):
    """Compute variant key for a tabled call's arguments."""
    return tuple(_normalize_for_key(a) for a in args)
```

### Answer freezing

```python
def freeze_args(args, trail):
    """Capture a ground snapshot of current arg bindings."""
    return tuple(_deep_deref(a) for a in args)

def _deep_deref(term):
    """Recursively deref all Vars. Reuses logic from solve._deref_walk."""
    from clausal.logic.variables import deref, is_var
    term = deref(term)
    if is_var(term):
        return term  # unbound Var stays as-is (non-ground answer)
    if term is None or isinstance(term, (bool, int, float, str, bytes)):
        return term
    if isinstance(term, list):
        return [_deep_deref(e) for e in term]
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(_deep_deref(a) for a in term.args))
    if is_term_instance(term):
        return type(term)(**{
            f: _deep_deref(getattr(term, f)) for f in term_field_names(term)
        })
    return term
```

Note: `_deep_deref` is essentially `solve._deref_walk`. We can import it
directly or duplicate (it's small). Prefer import to avoid drift.

### Answer consumption

```python
def _yield_answers(answers, args, trail):
    """Unify each stored answer with caller's args, yield on success."""
    from clausal.logic.variables import unify
    for stored in answers:
        mark = trail.mark()
        ok = all(unify(a, s, trail) for a, s in zip(args, stored))
        if ok:
            yield None
        trail.undo(mark)
```

### Wrapper factory

```python
def make_tabled_wrapper(original_dispatch, functor, arity, table_store):
    """Wrap a compiled simple-mode dispatch fn with linear tabling."""

    def tabled_dispatch(*args_trail_k):
        # Unpack: simple-mode signature is (arg0, ..., argN-1, trail, k)
        args = args_trail_k[:arity]
        trail = args_trail_k[arity]
        # k = args_trail_k[arity + 1]  # not used by wrapper

        key = make_subgoal_key(args, trail)
        store_key = (functor, arity, key)
        entry = table_store.get(store_key)

        # Path 3: Cache hit (COMPLETE)
        if entry is not None and entry.status == "complete":
            yield from _yield_answers(entry.answers, args, trail)
            return

        # Path 2: Consumer (COMPUTING — recursive call)
        if entry is not None and entry.status == "computing":
            yield from _yield_answers(entry.answers, args, trail)
            return

        # Path 1: Leader — compute to fixpoint
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
        yield from _yield_answers(entry.answers, args, trail)

    return tabled_dispatch
```

**Important**: The wrapper has the same signature as simple-mode dispatch
`(arg0, ..., trail, k)` so it's a drop-in replacement. The `k` parameter
is ignored (tabling collects all answers then yields them).

### Trampoline mode

Linear tabling does **not** need a trampoline-mode wrapper. The wrapper
always runs the original dispatch in simple mode (via `for _ in original_dispatch(...)`).
If the underlying predicate was compiled in trampoline mode, we'd need a
trampoline driver inside the wrapper. For V2-4a, we compile tabled predicates
in simple mode only. This is fine because:
- The tabling wrapper itself prevents unbounded recursion (consumer path breaks cycles)
- Stack depth is bounded by fixpoint iteration count, not recursion depth

If trampoline mode is needed later (e.g., very deep non-recursive call chains
within a tabled predicate's body), the wrapper can be extended to drive a
StepGenerator internally.

---

## Phase 2: Database integration

### `clausal/logic/database.py` changes

```python
class Database:
    def __init__(self, module_dict=None):
        # ... existing fields ...
        self._table_store: dict = {}   # NEW

    # NEW properties and methods:

    @property
    def table_store(self) -> dict:
        """The shared table store for tabled predicates."""
        return self._table_store

    def abolish_table(self, functor: str, arity: int) -> None:
        """Remove all cached answers for predicate functor/arity."""
        to_remove = [k for k in self._table_store if k[0] == functor and k[1] == arity]
        for k in to_remove:
            del self._table_store[k]

    def abolish_all_tables(self) -> None:
        """Clear all tabling caches."""
        self._table_store.clear()
```

### Dynamic predicate interaction

When `assertz`/`asserta`/`retract` modify a tabled predicate, its cached
answers may be stale. Two options:

1. **Auto-invalidate**: `assertz`/`retract` calls `abolish_table` if the predicate is tabled
2. **Manual invalidation**: User must call `abolish_table` after mutation

**Recommendation**: Option 1 (auto-invalidate). Add to `assertz`/`asserta`/`retract`:

```python
def assertz(self, clause):
    functor, arity = head_key(clause.head)
    key = (functor, arity)
    self._clauses.setdefault(key, []).append(clause)
    if key in self._dispatch:
        self._dispatch[key] = None
    # Auto-invalidate tabling cache if predicate is tabled.
    if key in self._tabled:
        self.abolish_table(functor, arity)
```

Same for `asserta` and `retract`.

---

## Phase 3: Import hook wiring

### `clausal/import_hook.py` changes

Modify `_compile_all_pending` to wrap tabled predicates after compilation:

```python
def _compile_all_pending(pending, db, module_dict):
    """Compile each pending predicate once (after all clauses asserted)."""
    for (functor, arity), pred_cls in pending.items():
        clauses = db.clauses_for(functor, arity)
        compile_predicate(functor, arity, clauses, db,
                          globals_=module_dict, pred_cls=pred_cls)

    # Phase 2: wrap tabled predicates AFTER all compilation
    # (so cross-predicate references in compiled code are resolved)
    from clausal.logic.tabling import make_tabled_wrapper
    for (functor, arity), pred_cls in pending.items():
        if db.is_tabled(functor, arity):
            if pred_cls is not None:
                original_fn = pred_cls._get_dispatch()
            else:
                original_fn = db.get_dispatch(functor, arity)
            wrapped = make_tabled_wrapper(original_fn, functor, arity, db.table_store)
            if pred_cls is not None:
                pred_cls._dispatch_fn = wrapped
            db.set_dispatch(functor, arity, wrapped)
```

**Two-pass approach**: All predicates compiled first, then tabled ones wrapped.
This ensures that when `fib` calls `fib` recursively, the call target in
compiled globals resolves to the tabled wrapper (because `pred_cls._dispatch_fn`
is updated to the wrapper, and `_get_dispatch()` returns it).

### Lazy recompile interaction

When a tabled+dynamic predicate is recompiled via lazy recompile, the
recompilation produces a fresh unwrapped dispatch function. The tabling
wrapper must be re-applied. Two approaches:

1. **Wrap in lazy recompile closure**: Modify `_recompile_simple` to re-wrap if tabled
2. **Wrap in `_get_dispatch`**: Override `_get_dispatch` on tabled PredicateMeta classes

**Recommendation**: Option 1. In the lazy recompile closure, check if the
predicate is tabled and re-wrap:

```python
# In _compile_all_pending, after wrapping:
# Store a new lazy_recompile that re-wraps after recompilation
if db.is_tabled(functor, arity):
    old_lazy = pred_cls._lazy_recompile if pred_cls else db._lazy_recompile.get((functor, arity))
    def _rewrap_lazy(old_lazy=old_lazy, functor=functor, arity=arity):
        new_fn = old_lazy()  # recompile
        return make_tabled_wrapper(new_fn, functor, arity, db.table_store)
    if pred_cls is not None:
        pred_cls._lazy_recompile = _rewrap_lazy
    db._lazy_recompile[(functor, arity)] = _rewrap_lazy
```

---

## Phase 4: Builtins

### `clausal/logic/builtins.py` additions

```python
@_db_builtin("abolish_table", 2)
def _abolish_table_factory(db):
    """abolish_table(Functor, Arity) — clear tabling cache for a predicate."""
    def _abolish_table__2(functor_arg, arity_arg, trail, k):
        f = deref(functor_arg)
        a = deref(arity_arg)
        if not isinstance(f, str) or not isinstance(a, int):
            return  # fail silently if args aren't ground
        db.abolish_table(f, a)
        yield None
    return _abolish_table__2


@_db_builtin("abolish_all_tables", 0)
def _abolish_all_tables_factory(db):
    """abolish_all_tables — clear all tabling caches."""
    def _abolish_all_tables__0(trail, k):
        db.abolish_all_tables()
        yield None
    return _abolish_all_tables__0
```

---

## Phase 5: Test fixtures

### `tests/fixtures/tabled_fib.clausal`

```
-table(fib/2)

fib(N=0, RESULT=0),
fib(1, 1),
fib(N, RESULT) <- (
    N > 1,
    N1 := N - 1,
    N2 := N - 2,
    fib(N1, A),
    fib(N2, B),
    RESULT := A + B
)
```

### `tests/fixtures/tabled_path.clausal`

```
-table(path/2)

edge(FROM=1, TO=2),
edge(2, 3),
edge(3, 1),

path(X, Y) <- edge(X, Y)
path(X, Y) <- (
    edge(X, Z),
    path(Z, Y)
)
```

---

## Phase 6: Test suite (`tests/test_tabling.py`)

### Test cases

1. **`test_table_entry_basics`** — Unit: TableEntry, add_answer dedup, status transitions
2. **`test_subgoal_key_variants`** — Unit: `path(a, X)` and `path(a, Y)` produce same key
3. **`test_subgoal_key_different`** — Unit: `path(a, X)` and `path(b, X)` produce different keys
4. **`test_freeze_args`** — Unit: freeze produces ground copy, original Vars unaffected
5. **`test_path_cyclic_terminates`** — Integration: `path(1, Y)` on cyclic graph terminates, finds {2, 3, 1}
6. **`test_fib_tabled_correct`** — Integration: `fib(10, F)` → 55, `fib(0, F)` → 0, `fib(1, F)` → 1
7. **`test_fib_tabled_performance`** — Integration: `fib(30, F)` completes in < 2s (exponential without tabling)
8. **`test_cache_hit`** — Integration: second `fib(10, F)` call uses COMPLETE cache
9. **`test_ground_query_tabled`** — Integration: `fib(5, 5)` succeeds; `fib(5, 6)` fails
10. **`test_abolish_table_clears`** — Integration: compute fib(5), abolish, recompute → same answer
11. **`test_dynamic_tabled_interaction`** — Integration: assert new edge, abolish table, recompute path
12. **`test_non_tabled_unaffected`** — Integration: non-tabled predicates still work alongside tabled
13. **`test_multiple_tabled_predicates`** — Integration: fib and path both tabled in same module
14. **`test_auto_invalidate_on_assert`** — Integration: assertz on tabled pred clears its cache automatically

### Test structure

```python
import pytest
from clausal.import_hook import _load_module
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.solve import call
from clausal.logic.tabling import (
    TableEntry, make_subgoal_key, freeze_args, _normalize_for_key, _VAR,
)

FIXTURES = Path(__file__).parent / "fixtures"

class TestTableEntryUnit:
    def test_add_answer_dedup(self): ...
    def test_status_transitions(self): ...

class TestSubgoalKey:
    def test_variant_same_key(self): ...
    def test_different_args_different_key(self): ...

class TestFreezeArgs:
    def test_ground_freeze(self): ...

class TestTabledPath:
    @pytest.fixture
    def path_mod(self):
        return _load_module("tabled_path", str(FIXTURES / "tabled_path.clausal"))

    def test_cyclic_terminates(self, path_mod): ...
    def test_all_paths_found(self, path_mod): ...

class TestTabledFib:
    @pytest.fixture
    def fib_mod(self):
        return _load_module("tabled_fib", str(FIXTURES / "tabled_fib.clausal"))

    def test_fib_10(self, fib_mod): ...
    def test_fib_30_fast(self, fib_mod): ...
    def test_cache_hit(self, fib_mod): ...
    def test_ground_query(self, fib_mod): ...
    def test_abolish_and_recompute(self, fib_mod): ...
```

---

## Files to modify

| File | Change |
|------|--------|
| `clausal/logic/tabling.py` | **NEW** — TableEntry, make_tabled_wrapper, key/freeze utilities |
| `clausal/logic/database.py` | Add `_table_store`, `table_store`, `abolish_table`, `abolish_all_tables`; auto-invalidate in assertz/asserta/retract |
| `clausal/import_hook.py` | Two-pass `_compile_all_pending`: compile then wrap tabled; rewrap in lazy recompile |
| `clausal/logic/builtins.py` | Add `abolish_table/2`, `abolish_all_tables/0` |
| `tests/test_tabling.py` | **NEW** — ~14 tests |
| `tests/fixtures/tabled_fib.clausal` | **NEW** |
| `tests/fixtures/tabled_path.clausal` | **NEW** |

---

## Verification

```bash
# No regressions
python3 -m pytest --ignore=tests/test_continuation_search.py -q

# Tabling tests
python3 -m pytest tests/test_tabling.py -v

# Smoke: fib(30) < 2s
python3 -c "
from clausal.import_hook import _load_module
from clausal.logic.variables import Var, deref
from clausal.logic.solve import call
import time
m = _load_module('tabled_fib', 'tests/fixtures/tabled_fib.clausal')
F = Var()
t0 = time.time()
for trail in call('fib', 30, F, module=m.\$module):
    print(f'fib(30) = {deref(F)}, took {time.time()-t0:.3f}s')
    break
"
```
