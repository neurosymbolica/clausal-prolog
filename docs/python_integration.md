# Clausal — Python Integration

> Most clausal programs are written as `.clausal` files and queried with `clausal.query()`. This page covers the lower-level Python API for embedding logic programming in Python applications, testing, and advanced use cases.

## Overview

Clausal predicates are callable from Python code through a clean query API. The API covers:
- calling a specific compiled predicate by name
- solving an arbitrary goal term
- collecting fully-dereferenced bindings as plain Python dicts
- extracting a single solution

All entry points are in `clausal.logic.solve`.

---

## The Trail

The `Trail` (from `clausal.logic.variables`, a C extension) is the core mechanism for variable binding and backtracking. All Var bindings are recorded on a Trail. When a search branch fails, the trail is unwound to a saved mark:

```python
from clausal.logic.variables import Trail, Var, deref

trail = Trail()
mark = trail.mark()
v = Var()
unify(v, 42, trail)   # binds v → 42 on the trail
deref(v)              # → 42
trail.undo(mark)      # undoes the binding
deref(v)              # → v  (unbound again)
```

Every solve call creates a fresh `Trail` if you don't provide one. Bindings are live as long as the generator is suspended mid-iteration. Once the generator is exhausted or you stop iterating, it is safe to call `deref` on any Var that was bound during a yielded solution.

### `trail.record(callable)` — custom undo callbacks

Any no-arg callable can be pushed onto the trail. It is called (in LIFO order) when `trail.undo()` processes that entry during backtracking. Exceptions raised by the callable are silently cleared so undo always completes.

This is the extension point for backtrackable mutations of arbitrary Python state:

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

mark = trail.mark()
trailed_put("x", 1, trail)
trailed_put("y", 2, trail)
# d == {"x": 1, "y": 2}
trail.undo(mark)
# d == {}
```

In practice most Clausal code does not need this — `++()` covers imperative Python accumulation with obvious syntax, and `DictTerm` / `SetTerm` functional updates are sufficient for logic-programming patterns.

---

## `call` — drive a named predicate

```python
from clausal.logic.solve import call

for trail in call("fib", 7, N, module=mod):
    print(deref(N))   # reads the binding while it is live
```

`call(functor, *args, module, trail=None)` dispatches directly to the compiled function for `functor/arity`. It does not parse a goal term; it is the lowest-overhead path.

Dispatch lookup order:
1. `module.module_dict[functor]._get_dispatch()` — PredicateMeta class from module globals
2. `get_builtin_predicate(functor, arity, db)._get_dispatch()` — builtin predicates
3. `module.db.get_dispatch(functor, arity)` — Database fallback (test modules, Compound-headed predicates)

Raises `KeyError` if the predicate is not found.

---

## `solve` — drive an arbitrary goal

```python
from clausal.logic.solve import solve
from clausal.terms import And, Call, LoadName, Unify
from clausal.logic.variables import Var, deref

X = Var()
N = Var()
goal = And(Call(LoadName("fib"), (N, X)), Unify(N, 7))

for trail in solve(goal, module=mod):
    print(deref(X))   # → 13
```

`solve(goal, module, trail=None)` compiles the goal on the fly as a zero-arity synthetic predicate (via `_compile_as_query`) and drives the resulting dispatch function.

### Injecting user Vars

`_compile_as_query` collects all `Var` objects reachable from the goal via `_collect_vars` and injects them into the compiled function's `__globals__` by their unique ID-based Python name (`_v<id>`). This means the compiled code references the **same** Var objects that the user holds — bindings land on the user's Vars and are readable via `deref()` during and after each yielded solution.

### Module globals in queries

If `module.module_dict` is available, it is merged into the compiled query's globals before the user Var bindings. Predicate names in the goal resolve from the module namespace, so cross-predicate calls work in ad-hoc queries the same way they do in compiled predicates.

---

## `query` — collect binding dicts

```python
from clausal.logic.solve import query

N = Var()
X = Var()
goal = Call(LoadName("fib"), (N, X))

for bindings in query(goal, {"N": N, "X": X}, module=mod):
    print(bindings)   # {"N": 0, "X": 0}, {"N": 1, "X": 1}, ...
```

`query(goal, variables, module, trail=None)` wraps `solve` and fully dereferences each variable after each solution, returning a plain dict. Unbound Vars appear as Var objects in the dict.

Full dereferencing is recursive: a `fib(n=7, result=Var())` term in a binding dict becomes `fib(n=7, result=13)` after the result Var is bound.

---

## `once` — first solution only

```python
from clausal.logic.solve import once

trail = once(Call(LoadName("fib"), (Var(), X)), module=mod)
if trail is not None:
    print(deref(X))
```

`once(goal, module, trail=None)` returns the `Trail` for the first solution, or `None` if the goal fails. Bindings on the returned Trail are live (the generator is not exhausted after the first yield — `once` just stops iterating). If you need the bindings to outlive the Trail, dereference your Vars before discarding the Trail.

---

## `query_wfs` — results with truth annotations

```python
from clausal.logic.solve import query_wfs

results = query_wfs(goal, {"X": X}, module=mod)
for r in results:
    print(r["X"], r["_truth"])  # True or "undefined"
```

`query_wfs(goal, variables, module, trail=None)` returns a **list** (not iterator) of binding dicts, each annotated with a `"_truth"` key. For programs with well-founded semantics (recursion through negation on tabled predicates), answers may have truth value `"undefined"` — atoms that are neither provably true nor provably false. Standard (non-WFS) answers have truth value `True`.

This is the entry point for inspecting WFS truth values. The standard `query()` / `call()` / `solve()` functions yield all non-failed answers without truth annotation.

---

## Builtins

Built-in predicates are available in every module without explicit import. They fall into two categories:

**Stateless builtins** — stored in `_BUILTINS` as dispatch functions:

```clausal
In/2            InCheck/2       Append/3        Length/2
Reverse/2       Last/2          GetItem/3       Flatten/2
Sort/2          MergeSort/2     Permutation/2   Select/3
Between/3       Succ/2          Plus/3          Abs/2
Max/3           Min/3           SumList/2       MaxList/2
MinList/2       IsVar/1         IsBound/1       IsStr/1
IsNumber/1      IsInt/1         IsFloat/1       IsCompound/1
IsCallable/1    IsList/1        IsGround/1      Functor/3
Arg/3           Unpack/2        Dif/2           InDomain/3
Label/1         AllDifferent/1  Equivalent/2    CallGoal/1
CallGoal/2      CallGoal/3      CallGoal/4      CallGoal/5
CallGoal/6      CallGoal/7      CallGoal/8      Call/1
Call/2          Call/3          Call/4          Call/5
Call/6          Call/7          Call/8          MapList/2
MapList/3       Filter/3        Exclude/3       FoldLeft/4
Unzip/3         PairKeys/2      PairValues/2    Sign/2
Gcd/3           DivMod/4        CopyTerm/2      TermVariables/2
NumberVars/3    Write/1         Writeln/1       PrintTerm/1
Nl/0            Tab/1           WriteToString/2 TermToString/2
```

**Compiler special forms** — compiled inline, not dispatched as builtins:

```clausal
FindAll/3       BagOf/3         SetOf/3         ForAll/2
```

**DB-dependent builtins** — stored in `_DB_BUILTINS` as factory callables; instantiated lazily with the live `Database`:

```clausal
Assert/1        AssertFirst/1   Retract/1       Signature/3
Vary/3          Extend/3        UnboundKeys/2
```

`BuiltinPredicate` wraps a dispatch function (or a db-bound factory result) with the same `_get_dispatch()` protocol as PredicateMeta classes. This means compiled predicate bodies call builtins via the same code path as user predicates.

### Builtin predicate classes

Every builtin also has a constructable `PredicateMeta` class, so you can build term trees in Python without resorting to `Call(func=LoadName(...), ...)`:

```python
from clausal.logic.builtins import get_builtin_class
from clausal.logic.variables import Var

Append = get_builtin_class("Append")
Between = get_builtin_class("Between")

# Positional args
t = Append([1, 2], [3], Var())  # → Append(l1=[1, 2], l2=[3], l3=Var())

# Keyword args with partial fill — missing fields become Var()
t2 = Between(low=1, high=10)    # → Between(low=1, high=10, x=Var())

# Pattern matching
match t:
    case Append(a, b, c):
        ...
```

Multi-arity builtins (`MapList`, `phrase`) use a `MultiArityBuiltin` wrapper that routes construction and dispatch by argument count. See [builtins.md](builtins.md#builtin-predicate-classes) for full details.

Field names are auto-extracted from implementation function signatures (e.g. `Append` has fields `(l1, l2, l3)`, `Between` has `(low, high, x)`). The `_BUILTIN_FIELDS` registry maps `(functor, arity)` to field name tuples.

---

## Assert / AssertFirst / Retract from Python

When called from a predicate body in a `.clausal` module, these builtins:
1. Check that the target predicate is not locked.
2. Assert/retract the clause on the Database.
3. Look up the PredicateMeta class from `db.module_dict` by functor name.
4. Sync `pred_cls._clauses` with the database's clause list.
5. Recompile the predicate via `compile_predicate` with the module globals, installing the new dispatch function on the PredicateMeta class.

When `db.module_dict` is `None` (as in test modules created without a module dict), step 3-5 are skipped and only the database is updated.

---

## `structural_unify`

`clausal.logic.builtins.structural_unify(t1, t2, trail)` is a Python-level recursive unifier that handles term representations the C extension's `unify` does not recurse into:

- `Compound(functor, args)` — functor equality + pairwise arg unification
- `KWTerm` — key equality + pairwise value unification
- PredicateMeta instances — field-by-field unification
- `@dataclass` instances — same

The C `unify` handles `Var` binding, tuple unification, list unification, and atomic equality. Use `structural_unify` when you need to unify two full term structures that may contain nested compounds or user-defined predicate terms.

---

## Using `Module` directly (without import hook)

For tests or programmatic use, create a `Module` directly:

```python
from clausal.logic.database import Module, Clause
from clausal.logic.predicate import make_predicate
from clausal.logic.compiler import compile_predicate
from clausal.logic.variables import Var
from clausal.terms import Unify

# Create a predicate programmatically
fib = make_predicate("fib", ["n", "result"])
fib._assertz(Clause(head=fib(n=Var(), result=Var()), body=[True]))
compile_predicate("fib", 2, fib._clauses, pred_cls=fib)

# Create a module that knows about this predicate
mod = Module("test", module_dict={"fib": fib})

# Query it
from clausal.logic.solve import call
from clausal.logic.variables import deref

N, R = Var(), Var()
for trail in call("fib", N, R, module=mod):
    print(deref(N), deref(R))
```

When `module_dict` is provided, `solve` and `call` resolve predicates from that dict first.

---

## Term dereferencing

`deref(var)` unwraps one level of binding (from `clausal.logic.variables`, C extension). For full recursive dereferencing, use `_deref_walk` from `clausal.logic.solve`:

```python
from clausal.logic.solve import _deref_walk

t = fib(n=Var(), result=Var())
# ... after binding via trail ...
_deref_walk(t)  # → fib(n=7, result=13)
```

`_deref_walk` handles `Compound`, PredicateMeta instances, lists, and scalars recursively.

---

## Python Objects as Terms

Any Python object can serve as a ground term in clausal. The C `unify` function handles non-Var, non-special objects via Python's `==` operator. This means standard library types like `datetime.date`, `datetime.datetime`, `datetime.time`, and `datetime.timedelta` work as first-class terms without any wrapping:

```python
import datetime as dt
from clausal.logic.variables import Var, Trail, unify, deref

trail = Trail()
v = Var()
unify(v, dt.date(2026, 3, 16), trail)
deref(v)  # → datetime.date(2026, 3, 16)

# Same date unifies; different dates fail
unify(dt.date(2026, 3, 16), dt.date(2026, 3, 16), trail)  # → True
unify(dt.date(2026, 3, 16), dt.date(2026, 3, 17), trail)  # → False
```

The `date_time` standard library module provides relational predicates (`Date/4`, `DateTime/7`, etc.) for constructing and decomposing these objects. But the objects themselves are ordinary Python — you can call any method via `++()` interop:

```clausal
-import_from(date_time, [Date, FormatDate])

IsoDate(Y, M, D, S) <- (
    Date(Y, M, D, DT),
    S is ++DT.isoformat()
)
```

---

## `++()` — Python Escape

The `++()` operator evaluates an arbitrary Python expression at search time with logic variables automatically dereferenced. It wraps the expression in a `PyThunk` lambda that is called with deref'd values.

### As a Value

Use `++expr` on the right side of `is` to compute a Python value:

```clausal
list_len(L, N) <- (N is ++len(L))
to_upper(S, R) <- (R is ++S.upper())
inc(X, R) <- (R is ++(X + 1))
first(L, R) <- (R is ++L[0])
get_key(D, K, R) <- (R is ++D[K])
join_words(W, R) <- (R is ++", ".join(W))
double_all(L, R) <- (R is ++[x*2 for x in L])
```

Any valid Python expression works inside `++()`: function calls, method calls, subscripts, dict access, list comprehensions, arithmetic, and string formatting.

### As a Goal

Use `++expr` as a standalone goal for side effects:

```clausal
show(X) <- ++print(X)
```

When used as a goal, `++()` evaluates the expression (for its side effect) and always succeeds once.

Goals and values can be mixed in a clause body:

```clausal
process(X, R) <- (
    ++print(X),
    R is ++(X * 2)
)
```

### Multiple Variables

All logic variables in the expression are dereferenced before evaluation:

```clausal
add_len(A, B, R) <- (R is ++(len(A) + len(B)))
```

### Per-Solution Evaluation

`PyThunk` values are evaluated fresh for each solution during backtracking:

```clausal
Item(1), Item(2), Item(3),
Doubled(R) <- (Item(X), R is ++(X * 2))
# yields R = 2, 4, 6
```

### Implementation

The `++` syntax is detected by `visit_UnaryOp` in `term_rewriting.py` as `UAdd(UAdd(expr))`. The compiler emits a `_pyt_<id>(deref(...))` call wrapping the expression in a `PyThunk` lambda from `clausal/terms.py`.
