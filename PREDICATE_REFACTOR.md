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

#### Phase 2: Compiler dispatch generation

**File: `clausal/logic/compiler.py`**

- `_dispatch_call_iter`: generate `fname._get_dispatch()(args, trail, k)` instead of
  `_db.table_for(fname, arity).get_dispatch()(args, trail, k)`
- `_dispatch_call_trampoline`: same change
- Remove `_db` from `base_globals`
- Inject Predicate classes referenced in body goals into compiled function globals
- Keyword normalization: look up `globals_dict[fname]._signature` instead of
  `db.signature_for(fname, arity)`
- `compile_predicate` signature: receive module globals dict (or Predicate class)
  instead of Database

#### Phase 3: `_install` targets Predicate class

**File: `clausal/logic/compiler.py`**

Change `_install` to set `pred_cls._dispatch_fn` and `pred_cls._lazy_recompile` instead
of `table.dispatch_fn` and `table._lazy_recompile`.

#### Phase 4: Import hook

**File: `clausal/import_hook.py`**

- `_define_predicate`: look up Predicate class from module dict, call
  `pred_cls._assertz(clause)`, set `pred_cls._signature`, compile
- `_assert_fact`: same — look up Predicate class, call `pred_cls._assertz()`
- Add `PredicateMeta` to `predicate_builtins`

### Phase 5: solve.py

**File: `clausal/logic/solve.py`**

- `call()`: look up Predicate class from module globals by name
- `_compile_as_query()`: pass module globals to compiler instead of `db`
- `solve()`, `query()`, `once()`: adapt to new interface
- `Module` holds reference to the Python module's `__dict__`

### Phase 6: Builtins

**File: `clausal/logic/builtins.py`**

Create `BuiltinPredicate` adapter that wraps a dispatch function with a `_get_dispatch()`
method. `Database.table_for` (if still used) or a global registry creates these on demand.

Later: migrate builtins to real Predicate classes in `clausal/stdlib/`.

### Phase 7: Cleanup

- Remove `PredicateTable` class
- Simplify `Database` to a thin registry or remove entirely
- Simplify `Module` — it may just hold a reference to the module dict
- Update all tests

---

## Test Impact

### Tests that directly test PredicateTable (`tests/test_database.py`)
~10 tests. Rewrite to test Predicate class-level equivalents.

### Tests that directly test Database (`tests/test_database.py`)
~12 tests. Adapt to new thin registry or remove.

### Tests that use `db.table_for` (`tests/test_import.py`, `tests/test_compiled_programs.py`)
~40 tests. Update to use Predicate class attributes directly.

### Tests using `compile_predicate(functor, arity, clauses, db)` signature
Many compiler tests construct `Database()` + `Compound` heads. These need a helper like
`make_predicate("fib", ["n", "f"])` to dynamically create Predicate classes for testing.

### `.clausal` module tests
Functor names in globals become classes instead of singleton instances. Term construction
(`edge(1, 2)`) still works via `PredicateMeta.__call__`. Most tests need minimal changes.

---

## Key Design Decisions

- **Metaclass, not @dataclass**: `PredicateMeta` metaclass handles field setup, `__init__`,
  `__eq__`, `__match_args__`, `__repr__` directly. Avoids surprising interactions between
  `@dataclass` machinery and our metaclass (dataclasses rewrite `__init__`, `__eq__`,
  `__hash__`, `__repr__` at decoration time, which could clash).
- **Locked by default**: `_locked = True`. Runtime `assertz`/`retract` raises unless
  explicitly unlocked. Prevents accidental cross-module mutation.
- **No central Database for dispatch**: the Database becomes a thin index or goes away.
  Predicate classes are the source of truth.
- **Builtins via adapter first**: wrap existing dispatch functions before migrating to
  full Predicate classes. Minimizes blast radius.
- **`_MISSING` sentinel for partial terms**: distinguishes "not provided" from `None` in
  `__call__`. Each missing field gets a fresh `Var()`.
