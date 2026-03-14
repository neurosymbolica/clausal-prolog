# Clausal — Python Integration

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

## `query_wfs` — results with truth annotations (V2-7)

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

```
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
Unzip/3         PairKeys/2      PairValues/2
```

**Compiler special forms** — compiled inline, not dispatched as builtins:

```
FindAll/3       BagOf/3         SetOf/3         ForAll/2
```

**DB-dependent builtins** — stored in `_DB_BUILTINS` as factory callables; instantiated lazily with the live `Database`:

```
Assert/1        AssertFirst/1   Retract/1       Signature/3
Vary/3          Extend/3        UnboundKeys/2
```

`BuiltinPredicate` wraps a dispatch function (or a db-bound factory result) with the same `_get_dispatch()` protocol as PredicateMeta classes. This means compiled predicate bodies call builtins via the same code path as user predicates.

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
