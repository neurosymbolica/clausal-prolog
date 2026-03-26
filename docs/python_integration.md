# Python Integration

Clausal and Python work together seamlessly. From `.clausal` files, use `++()` to call any Python expression. From Python code, use `query()` to run logic programs and collect results.

---

## `++()` — Python Escape

The `++()` operator evaluates an arbitrary Python expression at search time with logic variables automatically dereferenced.

### As a Value

Use `++expr` on the right side of `==`, `:=`, or `is` to compute a Python value:

```clausal
list_len(L, N) <- (N is ++len(L))
to_upper(S, R) <- (R is ++S.upper())
inc(X, R) <- (R is ++(X + 1))
first(L, R) <- (R is ++L[0])
get_key(D, K, R) <- (R is ++D[K])
join_words(W, R) <- (R is ++", ".join(W))
double_all(L, R) <- (R is ++[x*2 for x in L])
```

Any valid Python expression works: function calls, method calls, subscripts, comprehensions, arithmetic.

### As a Goal

Use `++expr` as a standalone goal for side effects:

```clausal
show(X) <- ++print(X)
```

When used as a goal, `++()` always succeeds once.

### Multiple Variables

All logic variables in the expression are dereferenced before evaluation:

```clausal
add_len(A, B, R) <- (R is ++(len(A) + len(B)))
```

### Per-Solution Evaluation

`PyThunk` values are evaluated fresh for each solution during backtracking:

```clausal
# skip
Item(1), Item(2), Item(3),
Doubled(R) <- (Item(X), R is ++(X * 2))
# yields R = 2, 4, 6
```

---

## Querying from Python

### `query` — collect binding dicts

The most common entry point. Returns fully-dereferenced bindings as plain Python dicts:

```python
from clausal.logic.solve import query
from clausal.logic.variables import Var
from clausal.terms import Call, LoadName

N = Var()
X = Var()
goal = Call(LoadName("fib"), (N, X))

for bindings in query(goal, {"N": N, "X": X}, module=mod):
    print(bindings)   # {"N": 0, "X": 0}, {"N": 1, "X": 1}, ...
```

Unbound Vars appear as `Var` objects in the dict. Full dereferencing is recursive: nested compound terms are walked.

### `once` — first solution only

```python
from clausal.logic.solve import once

trail = once(goal, module=mod)
if trail is not None:
    print(deref(X))
```

Returns the `Trail` for the first solution, or `None` if the goal fails.

### `call` — drive a named predicate

Lowest-overhead path — dispatches directly to the compiled function:

```python
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

N = Var()
for trail in call("fib", 7, N, module=mod):
    print(deref(N))   # reads the binding while it is live
```

### `solve` — drive an arbitrary goal

```python
from clausal.logic.solve import solve

for trail in solve(goal, module=mod):
    print(deref(X))
```

### `query_wfs` — results with truth annotations

For programs with [Well-Founded Semantics](wfs.md) (recursion through negation on tabled predicates):

```python
from clausal.logic.solve import query_wfs

results = query_wfs(goal, {"X": X}, module=mod)
for r in results:
    print(r["X"], r["_truth"])  # True or "undefined"
```

Returns a **list** (not iterator) of binding dicts, each with a `"_truth"` key.

---

## Python Objects as Terms

Any Python object works as a ground term. The C `unify` function handles non-Var objects via Python's `==`:

```python
import datetime as dt
from clausal.logic.variables import Var, Trail, unify, deref

trail = Trail()
v = Var()
unify(v, dt.date(2026, 3, 16), trail)
deref(v)  # → datetime.date(2026, 3, 16)
```

This means `datetime`, `Decimal`, `pathlib.Path`, and any other Python type with `__eq__` works as a logic term without wrapping. Call methods via `++()`:

```clausal
-import_from(date_time, [Date])

IsoDate(Y, M, D, S) <- (
    Date(Y, M, D, DT),
    S is ++DT.isoformat()
)
```

---

## Using `Module` Directly

For tests or programmatic use without the import hook:

```python
from clausal.logic.database import Module, Clause
from clausal.logic.predicate import make_predicate
from clausal.logic.compiler import compile_predicate
from clausal.logic.variables import Var

fib = make_predicate("fib", ["n", "result"])
fib._assertz(Clause(head=fib(n=Var(), result=Var()), body=[True]))
compile_predicate("fib", 2, fib._clauses, pred_cls=fib)

mod = Module("test", module_dict={"fib": fib})
```

---

??? abstract "Low-Level API Details"

    ### The Trail

    The `Trail` (from `clausal.logic.variables`, a C extension) records variable bindings for backtracking:

    ```python
    from clausal.logic.variables import Trail, Var, unify, deref

    trail = Trail()
    mark = trail.mark()
    v = Var()
    unify(v, 42, trail)   # binds v → 42
    deref(v)              # → 42
    trail.undo(mark)      # undoes the binding
    deref(v)              # → v  (unbound again)
    ```

    ### Custom Undo Callbacks

    `trail.record(callable)` pushes a no-arg callable for backtrackable mutations:

    ```python
    d = {}
    _ABSENT = object()

    def trailed_put(key, value, trail):
        old = d.get(key, _ABSENT)
        def undo():
            if old is _ABSENT:
                d.pop(key, None)
            else:
                d[key] = old
        trail.record(undo)
        d[key] = value
    ```

    ### Dispatch Lookup Order

    `call(functor, *args, module)` resolves predicates in this order:

    1. `module.module_dict[functor]._get_dispatch()` — PredicateMeta class from module globals
    2. `get_builtin_predicate(functor, arity, db)._get_dispatch()` — builtin predicates
    3. `module.db.get_dispatch(functor, arity)` — Database fallback

    ### `structural_unify`

    `clausal.logic.builtins.structural_unify(t1, t2, trail)` is a Python-level recursive unifier for `Compound`, `KWTerm`, PredicateMeta instances, and `@dataclass` instances. The C `unify` handles `Var` binding, tuples, lists, and atomic equality.

    ### Term Dereferencing

    `deref(var)` unwraps one level. For full recursive dereferencing:

    ```python
    from clausal.logic.solve import _deref_walk

    _deref_walk(term)  # recursively dereferences Compound, lists, etc.
    ```

    ### Builtin Predicate Classes

    Every builtin has a constructable `PredicateMeta` class:

    ```python
    from clausal.logic.builtins import get_builtin_class

    Append = get_builtin_class("Append")
    t = Append([1, 2], [3], Var())   # → Append(l1=[1, 2], l2=[3], l3=Var())
    ```

    Multi-arity builtins (`MapList`, `phrase`) use `MultiArityBuiltin`.

    ### Assert/Retract from Python

    When called from a `.clausal` module, these builtins:

    1. Check that the target predicate is not locked
    2. Assert/retract the clause on the Database
    3. Look up the PredicateMeta class from `db.module_dict`
    4. Sync `pred_cls._clauses` with the database
    5. Recompile with module globals

    ### `++()` Implementation

    The `++` syntax is detected by `visit_UnaryOp` in `term_rewriting.py` as `UAdd(UAdd(expr))`. The compiler emits a `_pyt_<id>(deref(...))` call wrapping the expression in a `PyThunk` lambda.

---

*See also: [I/O](io.md) — Write, Writeln, f-strings for formatted output.*
*See also: [Predicates](predicates.md) — defining predicates in `.clausal` files.*
