# Predicate-as-Class Refactor

## Motivation and Design Discussion

### The problem: cross-module predicate calls

Clausal needs a way for one `.clausal` module to call predicates defined in another. The
test framework is the immediate driver: a `test_fibonacci.clausal` file needs to call `fib/2`
from `fibonacci.clausal`. But cross-module calls are fundamental to any real program.

### Why not copy Prolog?

Prolog uses `use_module/1` and module-qualified calls (`lists:member/2`). But clausal's
audience is Python programmers, and Python already has a perfectly good import system. The
goal is to make `from fibonacci import fib` just work — bringing both the term constructor
and the predicate dispatch machinery into the importing module.

### The current architecture and why it blocks us

Today there are **two parallel namespaces** for every predicate:

1. **Module globals**: `fib` = a functor dataclass singleton (term constructor only)
2. **Database**: `("fib", 2)` = a `PredicateTable` (clause store + compiled dispatch)

These are completely separate objects. `from fibonacci import fib` brings the functor
class into the importing module, but the dispatch lives in `fibonacci.$module.db` — a
separate `Database` object that the importing module has no access to.

The `Database` is a central `dict[(str, int), PredicateTable]` injected as `_db` into every
compiled function's globals. All predicate calls compile to
`_db.table_for("fib", 2).get_dispatch()(args, trail, k)` — a string-based runtime lookup
through this central registry. Cross-module calls would require somehow merging or linking
databases.

### The solution: predicates ARE the classes

Instead of two separate objects, the predicate **is** the class:

- `fib` is a Python class (extending `Predicate` base class + `@dataclass`)
- `fib(n=0, f=0)` creates a term (a dataclass instance) — same as today
- `fib._clauses`, `fib._dispatch_fn`, `fib._signature` — the predicate machinery lives
  as class attributes
- Compiled code generates `fib._get_dispatch()(args, trail, k)` — resolving `fib` from
  the compiled function's globals (which are the module globals)
- `from fibonacci import fib` imports the class — term constructor AND dispatch come
  together

The "database" is distributed: each Predicate class holds its own clauses and dispatch.
There is no central `_db` registry for dispatch resolution.

IF we end up needing predicates/goals that have arbitrary python objects as their functor,
these could be handled with a generic predicate that takes a name or the object somehow. 
This is optional and not in the scope of this refactor.

### What Python `import` gives us for free

- Name resolution: `from fibonacci import fib` puts `fib` in module globals
- The compiler resolves `fib` by name from globals — no string lookup needed
- Re-exports, aliasing, `__all__` — all work naturally
- Circular import handling — Python's existing mechanisms apply

### Naming conventions and conflicts

Clausal's trailing-underscore convention (`X_`, `foo_`) separates variables from atoms.
Any name without a trailing underscore is a potential functor/predicate name. Python
imports can introduce names into the same namespace (e.g., `from os.path import join`).
This is normal Python name shadowing — predictable and familiar. A predicate named `join`
would shadow the import; the programmer handles this the same way they would in any Python
module.

### Locking

Predicates are **locked by default** at the end of the module code (implicit, generated code). Runtime `assertz`/`retract` raises an error unless
the predicate is explicitly unlocked (through a directive 'dynamic(predicate)'). This prevents one module from silently mutating
another module's predicates through an import — a scenario that, while technically possible
in Python, is strongly discouraged and would cause confusing bugs in logic programming
where predicate semantics change mid-search.

### Problems we are trying to avoid

1. **Two-namespace confusion**: the current split between functor-class-in-globals and
   PredicateTable-in-Database is an implementation artifact, not a design feature. It
   forces extra machinery (Database, `_db` injection, `table_for` string lookup) and
   blocks cross-module calls entirely.

2. **String-based dispatch**: `_db.table_for("fib", 2)` is a runtime string lookup on
   every predicate call. Replacing it with a direct name reference from globals is both
   simpler and faster.

3. **Central mutable registry**: the Database is a single mutable dict shared by all
   predicates in a module. Mutation via `assertz`/`retract` affects all compiled code
   that holds a reference to the same `_db`. With predicates as classes, mutation is
   scoped to the class itself, and locking prevents unintended cross-module mutation.

4. **Import doesn't compose**: today, `from fibonacci import fib` only brings the term
   constructor. Making the class carry dispatch means import does what users expect.

5. **Singleton confusion**: the current pattern `fib = fib()` replaces the class with an
   instance in module globals. This means `isinstance(term, fib)` doesn't work (because
   `fib` is an instance, not a class). The new design keeps `fib` as the class, so
   `isinstance` works naturally.

6. **Over-engineering the module system**: Prolog-style `use_module`, module qualification
   (`mod:pred`), and wiring dicts add complexity that Python programmers don't need. Python
   `import` already solves the composition problem.

---

## Architecture

### PredicateMeta metaclass

Every predicate is a class with `metaclass=PredicateMeta`. The metaclass:

- Initializes class-level attributes: `_clauses`, `_dispatch_fn`, `_lazy_recompile`,
  `_signature`, `_locked`
- Provides class methods: `_get_dispatch()`, `_assertz()`, `_asserta()`, `_retract()`
- Overrides `__call__` so `fib(n=0)` fills missing fields with `Var()` (replaces the
  current singleton `__call__` pattern)

We avoid `@dataclass` — the metaclass handles field setup, `__init__`, `__eq__`,
`__match_args__`, and `__repr__` directly. This prevents surprising interactions
between dataclass machinery and our metaclass.

### Term instances

`fib(n=0, f=0)` creates an instance — a term. Instances are lightweight data.
Pattern matching (`match...case`) works via `__match_args__` set by the metaclass.

### Compiled dispatch

Body goal `fib(N1, F1)` compiles to:

```python
# simple mode
for _ in fib._get_dispatch()(N1, F1, trail, k):
    ...

# trampoline mode
_gen = fib._get_dispatch()(self, N1, F1, trail)
```

`fib` is resolved from the compiled function's globals. No `_db`, no `table_for`.

### Module globals as the namespace

The compiler receives the module's globals dict. When compiling a predicate, all other
predicates referenced in the body must be findable in that dict. The compiler injects
them into the compiled function's own globals.

### Builtins

Builtins (`member`, `append`, `between`, etc.) become importable Predicate-like objects.
Initially via an adapter that wraps existing dispatch functions; later as real Predicate
classes in `clausal.stdlib`.

---

## Implementation Plan

### Phase 0: Create PredicateMeta (non-breaking) ✅

**New file: `clausal/logic/predicate.py`**

Created `PredicateMeta` metaclass with:
- Class-level `_clauses`, `_dispatch_fn`, `_lazy_recompile`, `_signature`, `_locked`
- `_get_dispatch()` — same logic as current `PredicateTable.get_dispatch`
- `_assertz(clause)`, `_asserta(clause)`, `_retract(head)` — with lock checking
- `__call__` override for partial term creation (fill missing fields with `Var()`)
- `_functor` property = `cls.__name__`
- `_arity` property = `len(fields)`
- `_lock()`, `_unlock()`

No `@dataclass` — the metaclass handles `__init__`, `__eq__`, `__match_args__`, `__repr__`.

Tests: `tests/test_predicate_meta.py` (37 tests). Zero breakage to existing code.

### Phase 1-4: The coupled change

These must land together because they form a dependency loop: the functor class shape,
compiler dispatch generation, install target, and import hook all must agree.

#### Phase 1: `_make_functor_class_ast` generates Predicate classes

**File: `clausal/templating/term_rewriting.py`**

Change generated code from:
```python
try:
    fib
except NameError:
    @dataclass
    class fib:
        n: object = None
        ...
        def __call__(self, **kwargs): ...
    fib = fib()  # singleton
```

To:
```python
try:
    fib
except NameError:
    class fib(metaclass=PredicateMeta):
        _fields = ('n', 'f')
    # No @dataclass. No singleton. fib stays as the class.
```

`PredicateMeta` must be injected into module namespace via `predicate_builtins` in the
import hook.

#### Phase 2: Compiler dispatch generation ✅

**File: `clausal/logic/compiler.py`**

- `_dispatch_call_iter`: generates `fname._get_dispatch()(args, trail, k)` instead of
  `_db.table_for(fname, arity).get_dispatch()(args, trail, k)`
- `_dispatch_call_trampoline`: same change
- Removed `_db` from `base_globals`
- `_DbLookupAdapter` compat shim wraps `db.table_for()` with `_get_dispatch()` interface
  for predicates not yet available as PredicateMeta classes (tests, builtins)
- `_collect_call_targets(clauses)`: scans clause bodies for Call(LoadName) nodes
- `_inject_call_targets()`: injects PredicateMeta classes or `_DbLookupAdapter` shims
  into `base_globals` for each body call target
- Keyword normalization still uses `db.signature_for()` (deferred to Phase 5)
- `compile_predicate`/`compile_predicate_trampoline` signature unchanged (backward compat)

Zero regressions (1166 passed, same 16 pre-existing list edge case failures).

#### Phase 3: `_install` targets Predicate class ✅

**File: `clausal/logic/compiler.py`**

`_install` now accepts optional `pred_cls` parameter. When provided (a PredicateMeta
class), sets `pred_cls._dispatch_fn` and `pred_cls._lazy_recompile` in addition to the
existing `table.dispatch_fn` path. PredicateMeta class is auto-detected from
`base_globals` (via `_collect_head_types` which finds it from clause head instances).

#### Phase 4: Import hook ✅

**File: `clausal/import_hook.py`**

- `_define_predicate(predicate_node, logic_module, module_dict)`: syncs clause
  to `pred_cls._clauses` and sets `pred_cls._signature` from `pred_cls._fields`.
  Passes `module_dict` as `globals_` to `compile_predicate` for cross-predicate
  resolution via module namespace.
- `_assert_fact(term, logic_module, module_dict)`: same sync to pred class.
- Both `$define_predicate` and `$assert_fact` are now per-module closures in
  `exec_module` (capturing `module_dict` and `logic_module`).
- `PredicateMeta` already in `predicate_builtins` (from Phase 1).
- Database kept in sync (backward compat until Phase 7 cleanup).

Zero regressions (1166 passed, same 16 pre-existing list edge case failures).

### Phase 5: solve.py ✅

**File: `clausal/logic/solve.py`**

- `call()`: looks up PredicateMeta class from `module.module_dict` by functor name
  first (using `_get_dispatch()`), falls back to `module.db.table_for()` for
  test modules and builtins that don't have module_dict.
- `_compile_as_query(goal, module)`: now accepts `Module` instead of `Database`.
  When `module.module_dict` is available, merges it into `globals_` so predicate
  names resolve from the module namespace (cross-predicate resolution without
  `_db` string lookup).
- `solve()`: passes `module` (not `module.db`) to `_compile_as_query`.
- `Module.__init__` accepts optional `module_dict` parameter. Import hook sets
  `module_dict=module.__dict__` when creating the LogicModule.
- `query()`, `once()`: unchanged (delegate to `solve`).

Zero regressions (1166 passed, same 16 pre-existing list edge case failures).

### Phase 6: Builtins ✅

**File: `clausal/logic/builtins.py`**

Created `BuiltinPredicate` adapter class with `_get_dispatch()` interface. Supports
both stateless builtins (dispatch fn stored directly) and DB-dependent builtins
(factory stored, called lazily on first `_get_dispatch()`).

- `get_builtin_predicate(functor, arity, db)` → `BuiltinPredicate | None`
- `_inject_call_targets` in compiler.py now tries `BuiltinPredicate` before
  falling back to `_DbLookupAdapter`
- `solve.py`'s `call()` tries builtin lookup before Database fallback

`get_builtin_dispatch` kept for backward compat (`Database.table_for` still uses it).

Zero regressions (1167 passed, same 16 pre-existing failures).

### Phase 7: Cleanup (partial) ✅

**Completed:**
- Removed `__dataclass_fields__` compat shim from PredicateMeta (and `_FakeField` class)
- Created `is_term_instance()` and `term_field_names()` utility functions in `predicate.py`
- Replaced all `dataclasses.is_dataclass()` / `dataclasses.fields()` call sites across
  `database.py`, `solve.py`, `builtins.py`, `compiler.py` with the new helpers
- Fixed `vary/3` builtin to work with PredicateMeta instances (no longer uses
  `dataclasses.replace`)
- Updated `test_predicate_meta.py`: replaced `TestDataclassCompat` with `TestTermHelpers`

**Deferred:**
- `PredicateTable` class kept for backward compat — many compiler tests use
  `Compound` heads (not PredicateMeta). Full removal requires converting all test
  predicates to PredicateMeta or adding a dynamic predicate creation helper.
- `Database` kept as-is — still used for clause storage, builtin lookup, and
  signature registry by tests and the import hook.

Zero regressions (1167 passed, same 16 pre-existing failures).

### Phase 8: Remove PredicateTable, simplify Database

The goal is to make PredicateMeta the single source of truth for predicate state.
`PredicateTable` goes away; `Database` becomes a thin name→class registry (or is
removed entirely once all callers resolve predicates from module globals).

**Current state (post-Phase 7):**

PredicateMeta classes and PredicateTable hold duplicate state. The import hook syncs
them in `_define_predicate` and `_assert_fact`. The compiler's `_install` writes to
both. This duplication is the main thing Phase 8 eliminates.

#### Phase 8a: `make_predicate` test helper ✅

**File: `clausal/logic/predicate.py`**

`make_predicate(name, fields)` dynamically creates a PredicateMeta class:
```python
def make_predicate(name: str, fields: list[str]) -> PredicateMeta:
    return PredicateMeta(name, (), {"_fields": tuple(fields)})
```
Exported from `clausal.logic.predicate` and re-exported from `clausal`.

#### Phase 8b: `compile_predicate` / `_install` optional `db` ✅

**File: `clausal/logic/compiler.py`**

- `db` is now optional (default `None`) in `compile_predicate`,
  `compile_predicate_trampoline`, and `_install`
- New `pred_cls` explicit parameter on `compile_predicate` and
  `compile_predicate_trampoline` (in addition to auto-detection from globals_)
- `_GlobalsDb` proxy class: provides `signature_for()` from module globals
  (looks up `pred_cls._signature`) when `db=None`
- `_install`: skips PredicateTable path when `db=None`; installs on pred_cls only
- `_inject_call_targets`: skips `_DbLookupAdapter` fallback when `db=None`
- Lazy recompile closures use `pred_cls._clauses` when `db=None`

Zero regressions (1167 passed, same 16 pre-existing failures).

#### Phase 8c: Builtins sync to PredicateMeta ✅

**Files: `clausal/logic/builtins.py`, `clausal/logic/database.py`**

- `Database.__init__` now accepts `module_dict` parameter (stored as `db.module_dict`)
- `Module.__init__` passes `module_dict` to `Database()` constructor
- `_find_pred_cls(functor, module_dict)` helper: looks up PredicateMeta class
  from module_dict
- `_assertz_factory`: reads `db.module_dict`; syncs clause to `pred_cls._clauses`
  and passes `globals_=module_dict` + `pred_cls` to `compile_predicate`; checks
  locking before any mutation
- `_asserta_factory`: same pattern for insert-at-front
- `_retract_factory`: reads `db.module_dict`; after removing from `tbl._clauses`,
  also removes matching clause (by identity) from `pred_cls._clauses`; checks locking

When `db.module_dict` is None (e.g. test modules), behavior is identical to before.
Zero regressions (1167 passed, same 16 pre-existing failures).

#### Phase 8d: Import hook uses `pred_cls` as authoritative source ✅

**File: `clausal/import_hook.py`**

- `_define_predicate`: now uses `pred_cls._clauses[:] = db_clauses` to replace
  pred_cls clause list with the full (normalized) DB snapshot, rather than
  appending only the latest clause. Passes `pred_cls=` explicitly to
  `compile_predicate` to ensure both DB table and pred_cls get the dispatch fn.
- `_assert_fact`: same pattern.
- Database is still the authoritative normalization source (handles
  `_normalize_dataclass_fact`); pred_cls is synced from it.

Zero regressions (1167 passed, same 16 pre-existing failures).

#### Phase 8a-orig: `make_predicate` test helper (original plan, now done)

**File: `clausal/logic/predicate.py` (or `tests/conftest.py`)**

Most compiler/goal tests create `Database()` + `Compound` heads manually:
```python
db = Database()
db.assertz(Clause(head=Compound("foo", (Var(), Var())), body=[...]))
clauses = db.clauses_for("foo", 2)
compile_predicate("foo", 2, clauses, db)
fn = db.table_for("foo", 2).get_dispatch()
```

Create a dynamic predicate factory:
```python
def make_predicate(name: str, fields: list[str]) -> PredicateMeta:
    """Dynamically create a PredicateMeta class for testing."""
    return PredicateMeta(name, (), {"_fields": tuple(fields)})
```

This lets tests write:
```python
foo = make_predicate("foo", ["a", "b"])
foo._assertz(Clause(head=foo(a=Var(), b=Var()), body=[...]))
compile_predicate("foo", 2, foo._clauses, db=None, pred_cls=foo)
fn = foo._get_dispatch()
```

**Scope**: ~140 Database constructor calls across 7 test files. Start with
`test_compiler.py` and `test_compiled_programs.py` as they're highest-value.
The others (`test_compiler_goals.py`, `test_compiler_trampoline.py`) are bulk
conversions of the same pattern.

#### Phase 8b: `_install` targets PredicateMeta only

**File: `clausal/logic/compiler.py`**

Change `_install` to require `pred_cls` and remove the `PredicateTable` path:

```python
def _install(pred_cls, fn, lazy_recompile=None):
    pred_cls._dispatch_fn = fn
    if lazy_recompile is not None:
        pred_cls._lazy_recompile = lazy_recompile
```

Update `compile_predicate` and `compile_predicate_trampoline` to pass
`pred_cls` (detected from `base_globals` via `_collect_head_types`, or from
a new parameter). Callers that currently pass `db` but no `pred_cls` must
be updated to provide one.

`_DbLookupAdapter` can be removed once all call sites resolve predicates
from globals or from `BuiltinPredicate` objects.

#### Phase 8c: Builtins use PredicateMeta class methods

**File: `clausal/logic/builtins.py`**

The `assertz`, `asserta`, and `retract` builtins currently operate on the
Database directly:
- `db.assertz(clause)` → `tbl._clauses`
- `db._tables.get(key)` → direct table access in retract

Change them to operate on PredicateMeta classes:
- Look up `pred_cls` from module globals (passed via closure or a new
  `module_dict` parameter on the db-builtin factory)
- `pred_cls._assertz(clause)` / `pred_cls._asserta(clause)`
- `pred_cls._retract(head)` with unification-based matching (upgrade
  the current structural-equality retract on PredicateMeta)
- Recompile via `compile_predicate` using `pred_cls._clauses`

The `signature` builtin should read `pred_cls._signature` directly.

#### Phase 8d: Import hook drops Database sync

**File: `clausal/import_hook.py`**

Once `_install` targets PredicateMeta only and builtins use class methods:
- `_define_predicate`: assert clause directly to `pred_cls._assertz`,
  set `pred_cls._signature`, compile from `pred_cls._clauses`
- `_assert_fact`: same pattern
- `Module.__init__` no longer needs to create a `Database`
- `Module.db` becomes optional/deprecated (kept for test compat if needed)

#### Phase 8e: Remove PredicateTable and simplify Database

**File: `clausal/logic/database.py`**

- Delete `PredicateTable` class entirely
- `Database` becomes a thin `dict[str, PredicateMeta]` registry mapping
  predicate names to their classes. Only needed for:
  - `signature_for` (can move to `pred_cls._signature` lookups)
  - Builtin fallback (already handled by `BuiltinPredicate`)
  - `_DbLookupAdapter` removal (no more table_for)
- If `Database` has no remaining callers, remove it too. `Module` becomes
  a wrapper around the module dict.

#### Phase 8f: Update tests

**Files: `tests/test_database.py`, `tests/test_compiler.py`, etc.**

- `TestPredicateTable` (~10 tests): delete or rewrite as `TestPredicateMeta`
  clause management tests (already covered in `test_predicate_meta.py`)
- `TestDatabase` (~12 tests): rewrite to test the thin registry, or delete
  if Database is fully removed
- Compiler tests (~140 Database() calls): convert to `make_predicate()` pattern
- Import hook tests: update `logic_mod.db.is_defined()` checks to
  `hasattr(mod, predicate_name)` + `isinstance(mod.name, PredicateMeta)`
- Search/builtin tests using `Module()`: update to pass `module_dict`

**Migration order**: 8a → 8b → 8c → 8d → 8e → 8f (each step can be
committed and tested independently; tests updated incrementally as the
code they test changes)

#### Risks and mitigations

- **Compound-headed clauses in tests**: many compiler tests use
  `Compound("foo", (Var(),))` heads. After Phase 8a, convert these to
  PredicateMeta instances. The compiler already handles both; the change
  is in test setup, not compiler logic.
- **retract unification**: current retract uses `structural_unify` on
  Compound facts with Var+Is normalization. PredicateMeta instances need
  the same unification path. `_retract` on PredicateMeta currently uses
  structural equality only — needs upgrading to unification-based.
- **Backward compat for `Module.db`**: keep `Module.db` as a deprecated
  property that raises or returns a shim, to catch stale callers.
- **`compile_predicate` signature**: currently `(functor, arity, clauses, db, ...)`
  with `db` required. Make `db` optional (default `None`) and add `pred_cls`
  parameter. This allows incremental migration.

---

## Key Design Decisions

- **Metaclass, not @dataclass**: `PredicateMeta` metaclass handles field setup, `__init__`,
  `__eq__`, `__match_args__`, `__repr__` directly. Avoids surprising interactions between
  `@dataclass` machinery and our metaclass (dataclasses rewrite `__init__`, `__eq__`,
  `__hash__`, `__repr__` at decoration time, which could clash).
- **Locked by default**: `_locked = True`. Runtime `assertz`/`retract` raises unless
  explicitly unlocked. Prevents accidental cross-module mutation.
- **No central Database for dispatch**: PredicateMeta classes are the source of truth.
  Database is a legacy artifact being removed in Phase 8.
- **Builtins via `BuiltinPredicate` adapter**: wraps existing dispatch functions with
  the `_get_dispatch()` protocol. Later: migrate to real Predicate classes in stdlib.
- **`_MISSING` sentinel for partial terms**: distinguishes "not provided" from `None` in
  `__call__`. Each missing field gets a fresh `Var()`.
