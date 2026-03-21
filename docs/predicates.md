# Clausal — Predicate System

## Defining predicates in .clausal files

Predicates are defined in `.clausal` files using Python syntax with a trailing comma. Each clause is either a **fact** (always true) or a **rule** (true when its body succeeds).

```clausal
# A fact: color/2 is true for these specific arguments
color(red, warm),
color(blue, cool),
color(green, cool),

# A rule: warm_color/1 is true when color(C, warm) succeeds
warm_color(C) <- color(C, warm)
```

Fields are inferred from the clause heads — no separate declaration needed. The predicate `color` has fields `(arg0, arg1)`, and `warm_color` has field `(arg0,)`.

### Multiple clauses

A predicate can have multiple clauses (tried in order):

```clausal
# skip
max(X, Y, X) <- (X >= Y)
max(X, Y, Y) <- (X < Y)
```

### Recursive predicates

```clausal
# skip
length([], 0),
length([_ | REST], N) <- (
    length(REST, N1),
    N := N1 + 1
)
```

---

## Python API (advanced)

> For most use cases, define predicates in `.clausal` files. This section covers the lower-level Python API for embedding or advanced use.

## Overview

In clausal, every predicate **is** a Python class. The class serves simultaneously as:

- a **term constructor** — `fib(N=0, RESULT=0)` creates a term instance
- a **clause store** — `fib._clauses` holds the list of `Clause` objects
- a **dispatch point** — `fib._get_dispatch()` returns the compiled search function

This unification eliminates the split between "functor singleton in module globals" and "predicate table in a central database" that existed in earlier versions. `from fibonacci import fib` brings both the term constructor and the dispatch machinery into the importing module.

---

## PredicateMeta

`clausal.logic.predicate.PredicateMeta` is the metaclass behind every predicate class. Declaring a predicate looks like:

```python
class fib(metaclass=PredicateMeta):
    _fields = ('n', 'result')
```

In `.clausal` files this declaration is generated automatically by the import hook from the first clause head that names the predicate's fields. You never write `metaclass=PredicateMeta` by hand in normal predicate files.

### What the metaclass generates

From `_fields`, `PredicateMeta.__new__` generates:

| Attribute | Purpose |
|---|---|
| `__slots__` | lightweight instances (one slot per field) |
| `__match_args__` | enables `match`/`case` structural decomposition |
| `__init__` | keyword-argument constructor with `_MISSING` defaults |
| `__eq__` | field-by-field equality check |
| `__repr__` | `fib(n=0, result=0)` style |
| `__hash__ = None` | mutable terms are not hashable |

`@dataclass` is deliberately **not** used. Dataclasses rewrite `__init__`, `__eq__`, and `__repr__` at decoration time in ways that can conflict with the metaclass. All field protocols are generated directly.

### Per-class predicate state

`PredicateMeta.__init__` adds these class-level attributes:

| Attribute | Type | Purpose |
|---|---|---|
| `_clauses` | `list[Clause]` | All asserted clauses for this predicate |
| `_dispatch_fn` | `Callable \| None` | Compiled search function; `None` when invalidated |
| `_lazy_recompile` | `Callable \| None` | Closure that recompiles and returns dispatch fn |
| `_signature` | `tuple[str,...] \| None` | Ordered field names (for keyword-call normalisation) |
| `_locked` | `bool` | Whether runtime `assertz`/`retract` is permitted |

These attributes are per-class (not inherited). Two predicate classes with the same name in different modules are fully independent.

---

## Term instances

Calling the class creates a **term instance** — a lightweight object that holds field values and nothing else (due to `__slots__`).

```python
fib(n=7, result=13)      # fully specified term
fib(n=7)                 # partial — result field gets a fresh Var()
fib()                    # all fields get fresh Var()
```

The partial-term behaviour is implemented in `PredicateMeta.__call__`. Fields not explicitly provided receive a fresh `Var()` via the `_MISSING` sentinel. Positional arguments are mapped to fields in order before keyword substitution.

Term instances are matched in compiled predicate bodies using Python's `match`/`case`:

```python
match (deref(arg0),):
    case (fib(n=_v0, result=_v1),):
        ...
```

`__match_args__` makes this work without explicit keyword patterns.

---

## Clause management

All mutations go through PredicateMeta class methods, which enforce locking and invalidate the compiled dispatch function:

```python
fib._assertz(clause)    # append clause at end
fib._asserta(clause)    # prepend clause at front
fib._retract(head)      # remove first clause with matching head
```

After any mutation, `_dispatch_fn` is set to `None`. The next call to `_get_dispatch()` will trigger lazy recompilation if `_lazy_recompile` is set, or raise `NotImplementedError` otherwise.

---

## Compiled dispatch

`fib._get_dispatch()` returns a callable with signature:

```python
def fib__2(arg0, arg1, trail, k):
    ...
    yield None  # one solution
```

On the first call after module load (or after `assertz`/`retract`), the lazy recompile closure runs the compiler, stores the new function in `_dispatch_fn`, and returns it. Subsequent calls return the stored function directly.

Compiled predicate bodies call other predicates via the same protocol:

```python
for _ in fib._get_dispatch()(N1, A, trail, k):
    ...
```

`fib` is resolved from the compiled function's `__globals__` — the module's globals dict. This means cross-predicate resolution is a direct name lookup, not a string search through a central registry.

---

## Locking

Predicates start **unlocked** and are locked after the module finishes loading. Once locked, `_assertz`, `_asserta`, and `_retract` raise `RuntimeError`:

```clausal
# skip
RuntimeError: Predicate fib/2 is locked. Use dynamic() to allow runtime assertion.
```

Locking prevents one module from silently modifying another module's predicates through an import — a source of hard-to-trace bugs in logic programming where predicate semantics change mid-search.

The `dynamic()` directive (planned) will unlock a predicate, signalling that it is intended to be modified at runtime. Until then, unlock programmatically with `pred_cls._unlock()`.

---

## Dynamic predicate creation

For use in tests or runtime code that needs a predicate without a module-level class definition:

```python
from clausal import make_predicate
from clausal.logic.database import Clause
from clausal.logic.variables import Var

foo = make_predicate("foo", ["a", "b"])
foo._assertz(Clause(head=foo(a=Var(), b=Var()), body=[...]))
```

`make_predicate(name, fields)` calls `PredicateMeta(name, (), {"_fields": tuple(fields)})` and returns the resulting class.

---

## Term inspection helpers

Two helpers replace `dataclasses.is_dataclass` / `dataclasses.fields` across the codebase:

```python
from clausal.logic.predicate import is_term_instance, term_field_names

is_term_instance(fib(n=0))       # True
is_term_instance(fib)            # False (class, not instance)
term_field_names(fib(n=0))       # ('n', 'result')
```

Both work for PredicateMeta instances and `@dataclass` instances — useful for code that handles terms from either source.

---

## Predicate repr

```python
>>> fib
<Predicate fib/2, 3 clause(s), compiled, locked>
>>> make_predicate("bar", ["x"])
<Predicate bar/1, 0 clause(s), uncompiled>
```

---

*See also: [Architecture](architecture.md) — how predicates fit into the execution model.*
