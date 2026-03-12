# Clausal — Predicate Compiler

## Overview

`clausal.logic.compiler` translates predicate clauses into Python generator functions. Each compiled function implements a complete search over all clauses of a predicate: attempting each clause in order, setting up variable bindings via the Trail, running the clause body, yielding solutions, and undoing bindings on backtracking.

Two compilation strategies are available:

| Strategy | Function | Stack growth | Use for |
|---|---|---|---|
| Simple / short-stack | `compile_predicate` | O(depth) | fact tables, bounded recursion |
| Trampoline / stack-safe | `compile_predicate_trampoline` | O(1) | deep or left-recursive predicates |

---

## Simple mode

### Compiled function shape

```python
def fib__2(arg0, arg1, trail, k):
    # clause 1: fib(N=0, RESULT=0)
    _v0 = deref(arg0)
    _v1 = deref(arg1)
    match (_v0, _v1):
        case (_v0_pat, _v1_pat):
            mark = trail.mark()
            if unify(_v0_pat, 0, trail) and unify(_v1_pat, 0, trail):
                yield None          # ← solution
            trail.undo(mark)
    # clause 2: ...
    ...
```

- Arguments: positional args for each predicate parameter, then `trail`, then `k` (a continuation; currently always `None` in the top-level driver, reserved for future use).
- One `match`/`case` arm per clause.
- `deref` is applied to all match subjects before the `match` to resolve any Var bindings already on the trail.
- Each arm opens a trail mark, attempts unification, runs the body (which may itself `yield`), then restores the trail regardless of success.

### Head pattern compilation

`compile_head_to_match_case` produces the patterns for a single `match` arm. Head arguments can be:

| Head position value | Generated pattern |
|---|---|
| `Var()` (unbound) | `MatchAs(name="_vN")` — capture into local name |
| Integer / string literal | `MatchValue(IntLiteral(N))` — exact match |
| PredicateMeta term `fib(n=_v, ...)` | `MatchClass(fib, patterns)` — structural match |
| List `[HEAD, *TAIL]` | `MatchAs(name="_listN")` + deferred list guard (see below) |

**Repeated head variables**: if the same logic variable appears in two different head positions, the second occurrence gets a generated alias name (`_vN__dupM`). The body is wrapped in `if unify(original, alias, trail):` before the continuation runs.

**List patterns**: lists in head positions are compiled as wildcard captures (`MatchAs`) rather than `MatchSequence`. A separate "list guard" records the pattern structure. Two runtime functions handle list unification bidirectionally:

- `_head_list_unify_input(target, before_vars, star_var, after_vars, trail)` — if `target` is a list, destructures and unifies each part. Returns `True` on success, `None` on unbound Var (defer), `False` on mismatch.
- `_head_list_unify_output` — run after the clause body, constructs the list from bound variables and unifies against the (now-bound) Var.

Multi-star patterns (`[*A, *B]`, `[X, *A, *B, Y]`) generate nested range loops over split points.

### Body goal compilation

`compile_goal(goal, db, var_context, trail_name, k_stmts)` recursively compiles body goals into Python AST statement lists. The continuation `k_stmts` is a list of statements to execute when a solution is found.

| Goal type | Compilation |
|---|---|
| `True` | pass-through to `k_stmts` |
| `False` | empty (no solution) |
| `Unify(l, r)` | `mark = trail.mark(); if unify(l, r, trail): k_stmts; trail.undo(mark)` |
| `NotUnify(l, r)` | `mark = ...; if not unify(l, r, trail): k_stmts; trail.undo(mark)` |
| `Evaluate(l, r)` | same as `Unify` but `r` is compiled via `arith_to_ast_expr` (arithmetic evaluation) |
| `Eq(l, r)` | `if deref(l) == deref(r): k_stmts` |
| `NotEq(l, r)` | `if deref(l) != deref(r): k_stmts` |
| `Lt/LtE/Gt/GtE` | arithmetic comparison via `arith_to_ast_expr` |
| `And(l, r)` | `compile_goal(l, ..., compile_goal(r, ..., k))` (right-nested) |
| `Or(l, r)` | two independent mark/undo blocks; both branches inline |
| `Not(goal)` | inner goal as sub-generator + flag; succeed only if inner fails |
| `In(elem, coll)` | `for _x in deref(coll): mark ...; if unify(elem, _x, trail): k; undo` |
| `NotIn(elem, coll)` | found-flag pattern |
| `Call(LoadName(f), args)` | `for _ in f._get_dispatch()(args, trail, k): k_stmts` |

The Call case is the core cross-predicate dispatch. `f` is the predicate name; it is resolved from the compiled function's `__globals__` at runtime, not by a string lookup in a central registry.

### Variable pre-allocation

Before the continuation chain is assembled, `_preallocate_body_vars` scans all goals left-to-right and emits `_vN = Var()` allocations for any logic variable that first appears in a goal (not in a head pattern). This prevents `UnboundLocalError` that would occur if right-to-left compilation produced code that referenced a name before it was assigned.

### Call target injection

`_inject_call_targets(functor, arity, clauses, db, globals_)` scans clause bodies for `Call(LoadName(f), ...)` nodes and ensures that each `f` resolves to something with `_get_dispatch()` in the compiled function's globals:

1. If `f` is already in `globals_` and is a `PredicateMeta` class → nothing to do.
2. If `f` is a known builtin → inject a `BuiltinPredicate` adapter.
3. If `db` is not `None` and `f` is in the database → inject a `_DbDispatchAdapter` wrapping `db.get_dispatch`.

`_collect_head_types` also scans clause heads for user-defined PredicateMeta instances and injects the class itself into globals (needed for `case fib(n=_v):` patterns in compiled match arms).

---

## Trampoline mode

### Compiled function shape

```python
def fib__2(this_generator, parent, arg0, arg1, trail):
    # clause 1
    match ...:
        case ...:
            mark = trail.mark()
            if unify(...):
                yield (parent, None)   # ← solution
            trail.undo(mark)
    yield (parent, DONE)   # ← search exhausted
```

- First arg is `this_generator` — a `StepGenerator` wrapper that called this function. `StepGenerator` creates itself first, then calls `func(self, parent, ...)`, so the generator body has a reference to its own wrapper without needing any bootstrap step.
- Second arg is `parent` — the `StepGenerator` of the calling predicate (or `None` at the root).
- No `k` arg — continuations are communicated via `yield (gen, value)` tuples.
- `yield (parent, None)` signals one solution to the parent.
- `yield (parent, DONE)` signals search exhaustion.

### StepGenerator protocol

Every trampoline-compiled generator is wrapped in a `StepGenerator`:

```python
from clausal.logic.trampoline import StepGenerator

root = StepGenerator(fib__2, None, 10, result_var, trail)
gen, value = root.send(None)
```

`StepGenerator.__init__(func, *args)` calls `func(self, *args)`, passing itself as the first argument (`this_generator`). This eliminates the old `self = yield` bootstrap round-trip — the generator has its own wrapper reference from the very first statement.

`send(value)` handles first-call bootstrapping transparently: the first call does `next(inner_gen)` (ignoring the value), subsequent calls delegate to `inner_gen.send(value)`.

A C extension (`_trampoline`) provides an optimised `StepGenerator` for production use. The pure-Python version in `clausal.logic.trampoline` is the fallback.

### Tuple protocol

Generators yield plain `(target, value)` tuples to steer the trampoline:

| Tuple | Meaning |
|---|---|
| `(this_generator, v)` | Resume self with value `v` (iterative step / tail call) |
| `(child, v)` | Start or resume a child `StepGenerator` |
| `(parent, None)` | Solution found — parent resumes us for more |
| `(parent, DONE)` | Search exhausted |
| `(None, v)` | Root computation complete (only at top level) |

Plain tuples get Python's `UNPACK_SEQUENCE` opcode — faster than attribute access on a dataclass.

### Sub-predicate calls

```python
_gen = StepGenerator(fib._get_dispatch(), this_generator, N1, A, trail)
_st = yield (_gen, None)
while _st is not DONE:
    # body continuation: current solution available
    ...
    _st = yield (_gen, None)
```

`StepGenerator` wraps the child dispatch function. `this_generator` is passed as the child's `parent`, so the child yields `(this_generator, None)` on solution and `(this_generator, DONE)` on exhaustion. The trampoline routes these back to us.

### Trampoline driver

The trampoline loop is simple:

```python
def trampoline(root: StepGenerator) -> Any:
    gen, value = root.send(None)
    while gen is not None:
        gen, value = gen.send(value)
    return value
```

No `started` set, no `resume` helper — `StepGenerator.send()` handles bootstrapping internally. The `solutions()` function yields each solution value:

```python
def solutions(root: StepGenerator):
    gen, value = root.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return
            yield value
            gen, value = root.send(None)
        else:
            gen, value = gen.send(value)
```

Both `trampoline` and `solutions` are available from `clausal.logic.trampoline` (preferring C extension, falling back to Python).

### NAF in trampoline mode

Negation-as-failure (`Not`) in trampoline mode compiles the inner goal in **simple mode** (a plain `for`-loop driver), not trampoline mode. This avoids the complexity of suspending and resuming the inner generator through the trampoline.

---

## First-argument indexing

When a predicate has 4 or more clauses, `compile_predicate` and `compile_predicate_trampoline` automatically build a first-argument index. Clauses are partitioned by the first argument's value: ground-first-arg calls jump directly to the matching clause subset via a dict lookup, while unbound-Var-first-arg calls fall back to the full unindexed path.

See [`docs/indexing.md`](indexing.md) for the full design, including bucket merging, trampoline `yield from` semantics, and the `emit_done` parameter.

---

## `compile_predicate` entry point

```python
compile_predicate(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database | None = None,
    *,
    globals_: dict | None = None,
    pred_cls: PredicateMeta | None = None,
    body_compiler = None,
) -> Callable
```

- `db=None` is allowed; a `_GlobalsDb` proxy is used for signature lookups from `globals_`.
- `pred_cls` explicitly identifies the PredicateMeta class to install the dispatch function on.
- `globals_` is the module globals dict; predicate names in the body resolve from this dict.
- Returns the compiled dispatch function and also installs it via `_install(pred_cls, fn, lazy_fn)`.

### _install

`_install` stores the dispatch function in two places:
1. `pred_cls._dispatch_fn = fn` — the PredicateMeta class holds dispatch directly.
2. `db.set_dispatch(functor, arity, fn, lazy_fn)` — the Database entry is also updated (kept for backward compatibility with code that looks up dispatch through the Database).

A lazy recompile closure is also registered in both locations. When `assertz`/`retract` invalidates dispatch by setting `_dispatch_fn = None`, the next call to `_get_dispatch()` invokes the lazy closure to recompile from the current clause list.

---

## `_GlobalsDb` — db-free compilation

When `db=None`, the compiler uses a `_GlobalsDb(globals_)` proxy that implements only `signature_for(functor, arity)`. It looks up the named predicate class from `globals_` and returns `cls._signature`. This covers keyword-argument normalisation during compilation without requiring a live Database.

---

## Generated function execution

`functiondef_to_function(funcdef_ast, globals_)` (in `clausal.codegen`) compiles a function-definition AST node and returns the resulting function object with the given globals dict. This is how `compile_predicate` turns AST into a callable.

---

## `_DbDispatchAdapter` — backward compatibility shim

When a called predicate is not a PredicateMeta class in module globals (e.g. in tests that use `Compound`-headed clauses, or for predicates not yet loaded), the compiler injects a `_DbDispatchAdapter`:

```python
class _DbDispatchAdapter:
    def _get_dispatch(self):
        return self._db.get_dispatch(self._functor, self._arity)
```

This gives the same `_get_dispatch()` call interface as a real PredicateMeta class, so the compiled call site (`fname._get_dispatch()(args, trail, k)`) is unchanged.
