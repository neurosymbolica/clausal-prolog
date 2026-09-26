# Clausal — Predicate Compiler

## Overview

`clausal.logic.compiler` translates predicate clauses into Python generator functions. Each compiled function implements a complete search over all clauses of a predicate: attempting each clause in order, setting up variable bindings via the Trail, running the clause body, yielding solutions, and undoing bindings on backtracking.

`clausal.logic.compiler_v2` orchestrates module-level compilation — coordinating imports, directives, term expansion, clause assertion, and per-predicate compilation into a single pipeline. See [Module-level pipeline](#module-level-pipeline-v2) below.

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
| Compound cell `('point', X, Y)` | `MatchSequence([MatchValue('point'), ...])` — structural match on the functor, then the arguments |
| List `[HEAD, *TAIL]` | `MatchAs(name="_lcapN")` + deferred list guard (see below) |
| [`DictTerm`](dicts_sets.md)`({"k": V, ...})` | `MatchAs(name="_dcapN")` + dict unify guard |
| [`SetTerm`](dicts_sets.md)`({1, 2, 3})` | `MatchAs(name="_scapN")` + set unify guard |

**Repeated head variables**: if the same logic variable appears in two different head positions, the second occurrence gets a generated alias name (`_vN__dupM`). The body is wrapped in `if unify(original, alias, trail):` before the continuation runs.

**Dict patterns** (`DictTerm`): dicts in head positions are compiled as wildcard captures. A "dict guard" pre-allocates `Var()` objects for variable values, constructs the expected `DictTerm`, and wraps the body in `if unify(captured, expected_dict, trail):`. This leverages the C-level `__unify__` protocol for pairwise value unification.

**Set patterns** (`SetTerm` / `SetLiteral`): sets in head positions are compiled as wildcard captures with a unify guard against a constructed `SetTerm`. Since set elements are ground, unification reduces to element equality.

**List patterns**: lists in head positions are compiled as wildcard captures (`MatchAs`) rather than `MatchSequence`. A separate "list guard" records the pattern structure. Two runtime functions handle list unification bidirectionally:

- `_head_list_unify_input(target, before_vars, star_var, after_vars, trail)` — if `target` is a list, destructures and unifies each part. Returns `True` on success, `None` on unbound Var (defer), `False` on mismatch.
- `_head_list_unify_output` — run after the clause body, constructs the list from bound variables and unifies against the (now-bound) Var.

Multi-star patterns (`[*A, *B]`, `[X, *A, *B, Y]`) generate nested range loops over split points.

**Nested star-list patterns**: when a fixed element inside a list pattern is itself a star-list (e.g. `[[HEAD, *TAIL], *ROWS]`), the compiler flattens it by replacing the inner pattern with a fresh proxy Var and emitting a separate sub-guard. `[[HEAD, *TAIL], *ROWS]` becomes:

1. Outer guard: `_head_list_unify_input(cap, [proxy], ROWS, [], trail)` — binds `proxy` to the first element
2. Inner guard: `_head_list_unify_input(proxy, [HEAD], TAIL, [], trail)` — destructures the bound proxy

A worklist handles arbitrary nesting depth (e.g. `[[[X, *Y], *Z], *W]` produces three guards).

### Body goal compilation

`compile_goal(goal, db, var_context, trail_name, k_stmts)` recursively compiles body goals into Python AST statement lists. The continuation `k_stmts` is a list of statements to execute when a solution is found.

| Goal type | Compilation |
|---|---|
| `True` | pass-through to `k_stmts` |
| `False` | empty (no solution) |
| `Unify(l, r)` | `mark = trail.mark(); if unify(l, r, trail): k_stmts; trail.undo(mark)` |
| `DoesNotUnify(l, r)` | `if _dif(l, r, trail): k_stmts` — [dif/2](constraints.md) constraint |
| `Evaluate(l, r)` | same as `Unify` but `r` is compiled via `arith_to_ast_expr` (arithmetic evaluation) |
| `ArithEq(l, r)` | `if _fd_eq(l, r, trail): k_stmts` — [CLP(ℤ)](constraints.md) arithmetic equality |
| `ArithNeq(l, r)` | `if _fd_ne(l, r, trail): k_stmts` — CLP(ℤ) arithmetic disequality |
| `Lt/LtE/Gt/GtE` | `if _fd_lt/_fd_le/_fd_gt/_fd_ge(l, r, trail): k_stmts` — CLP(ℤ) comparison |
| `And(l, r)` | `compile_goal(l, ..., compile_goal(r, ..., k))` (right-nested) |
| `Or(l, r)` | two independent mark/undo blocks; both branches inline |
| `Not(goal)` | inner goal as sub-generator + flag; succeed only if inner fails. If inner is a call to a [tabled](tabling.md) predicate, emits `_naf_tabled` call instead ([well-founded semantics](wfs.md)). |
| `IfExpr(test, body, orelse)` | [Reified ITE](reified_ite.md): three-way check for reifiable conditions, single-evaluation `_found` flag for general conditions. |
| `Call(LoadName("once"), [goal])` | Sub-generator + `for` loop with `break` after first yield. Bindings escape to continuation. |
| `Call(LoadName("findall"), [tmpl, goal, bag])` | Sub-generator collects `_deref_walk(tmpl)` per solution, undoes inner bindings, unifies result list with `bag`. Always succeeds (empty list on failure). |
| `Call(LoadName("bagof"), [tmpl, goal, bag])` | Same as `findall`, but fails if no solutions (empty result list). |
| `Call(LoadName("setof"), [tmpl, goal, bag])` | Same as `bagof`, plus deduplication via `_set_of_dedup` before unifying with `bag`. |
| `Call(LoadName("forall"), [cond, action])` | Desugared to `not (cond and not action)` — uses existing NAF compilation. |
| `in_(elem, coll)` | `for _x in deref(coll): mark ...; if unify(elem, _x, trail): k; undo` |
| `NotIn(elem, coll)` | found-flag pattern |
| `Call(LoadName(f), args)` | `StepGenerator($dispatch_at(f, N), …, args, trail)` — see [Sub-predicate calls](#sub-predicate-calls) |

The Call case is the core cross-predicate dispatch. `f` is the predicate name; its binding — the owning module's predicate handle — is resolved from the compiled function's `__globals__` at runtime, and `$dispatch_at(f, N)` turns it into the dispatch function on the owner's row at the call site's arity N.

### Variable pre-allocation

Before the continuation chain is assembled, `_preallocate_body_vars` scans all goals left-to-right and emits `_vN = Var()` allocations for any logic variable that first appears in a goal (not in a head pattern). This prevents `UnboundLocalError` that would occur if right-to-left compilation produced code that referenced a name before it was assigned.

### Globals collection and call target injection

Before generating the compiled function body, the compiler does a single pass over all clause heads and bodies to collect three categories of objects that need to be in the compiled function's `__globals__`:

```python
head_types, py_thunks, call_targets = _collect_globals_info(clauses)
base_globals.update(head_types)
base_globals.update(py_thunks)
_inject_resolved_targets(call_targets, base_globals, db, globals_)
```

**`_collect_globals_info(clauses)`** — single tree walk returning:

- `head_types`: `{name: cls}` for any class found in clause heads (needed for `MatchClass` patterns — `Compound` and dataclass heads; a cell head needs none).
- `py_thunks`: `{key: fn}` for any `PyThunk` lambda found in clause bodies (the `++expr` Python-escape syntax).
- `call_targets`: `set[(fname, arity)]` for every `Call(LoadName(f), ...)` node found in clause bodies.

**`_inject_resolved_targets(targets, base_globals, db, globals_)`** — resolution loop that ensures each called `(fname, arity)` pair has a binding in `base_globals` that `$dispatch_at` can resolve:

1. If `fname` is already in `base_globals` and is a predicate binding at this arity — the owner's handle, or a class no Clausal database owns → already present; apply locked dispatch caching (see below) and continue.
2. If `fname` is a known builtin → inject a `BuiltinPredicate` adapter.
3. If `db` is not `None` and `fname` is in the database → inject a `_DbDispatchAdapter` wrapping `db.get_dispatch`.
4. Dotted names (`mod.Pred`) are resolved via attribute traversal through the module dict.

### Locked dispatch caching

For predicates that are **locked** (non-dynamic, `row.locked` is `True`) at compilation time, `_inject_resolved_targets` also captures the dispatch function directly into `base_globals` under a stable key:

```python
_disp_key("edge", 2)  →  "$disp_edge_2"
base_globals["$disp_edge_2"] = resolve_predicate_row(edge, arity=2, db=db).dispatch_fn
```

The code-generation functions (`_dispatch_call_trampoline`, `_dispatch_call_iter`) check the current compilation context for cached keys. when a callee's dispatch key is present, the generated `StepGenerator` construction uses the cached local directly instead of resolving the binding through `$dispatch_at` at every invocation:

```python
# Unlocked / dynamic predicate (default):
_gen = StepGenerator($dispatch_at(foo, 2), this_generator, arg0, arg1, trail)

# Locked predicate — cached dispatch closure:
_gen = StepGenerator($disp_foo_2, this_generator, arg0, arg1, trail)
```

`$disp_foo_2` is a reference to a pre-captured dispatch function in the compiled function's `__globals__` — the binding-to-row resolution is eliminated on every call site.

**when dispatch caching fires:** Locking happens *after* initial module compilation, so intra-module calls within the same `.clausal` file are compiled before their callees are locked. Dispatch caching fires for cross-module calls (where the imported module is already locked), for explicit recompilations after locking, and for predicates compiled via `compile_predicate` / `compile_predicate_trampoline` after the callee's `_lock()` has been called.

**Safety:** On lazy recompile (triggered by `assertz`/`retract`), the whole compilation reruns with the updated clause list, so any cached dispatch functions are refreshed. Dynamic predicates (`row.locked` is `False`) never get cached; they always go through `$dispatch_at`.

### Call-site bucket specialisation

Locked dispatch caching captures the dispatch *closure* for locked callees. Call-site specialisation goes one step further: when the argument in an indexed position is a statically-known literal at the call site, the dispatch closure is bypassed and the call references a per-bucket *call-site wrapper* directly (`_make_call_site_bucket_trampoline` completes the SIGNAL-mode bucket to the full trampoline contract — terminal DONE yield plus TRO re-dispatch). Tabled predicates are never specialised: their `_index_plans` is empty because a direct bucket ref would bypass the tabling wrapper.

`_inject_bucket_refs_trampoline` runs after `_inject_resolved_targets`. It scans each clause body for `Call` nodes whose callee is locked and has `_index_plans`. For each such call site it converts the term-level argument to an AST expression, extracts a static key via `_static_call_key`, and — if the key appears in the callee's bucket dict — injects the bucket function into `base_globals` under a readable string key:

```python
base_globals["color.bucket(pos=0, 'red')"] = resolve_predicate_row(color, arity=1, db=db).index_plans[0]["red"]
```

`_dispatch_call_trampoline` then emits an `ast.Name` referencing that key instead of either `$disp_color_1` or `$dispatch_at(color, 1)`:

```python
# static literal 'red' in indexed position 0 — direct bucket ref:
_gen = StepGenerator(color.bucket(pos=0, 'red'), this_generator, 'red', trail)

# arg is a variable — falls back to cached dispatch closure:
_gen = StepGenerator($disp_color_1, this_generator, X_, trail)
```

Joint bucket pairs (when both indexed positions hold static literals) are also specialisable.

See [Call-Site Bucket Specialisation](indexing.md#call-site-bucket-specialisation) in the indexing docs for the full design and invariants.

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
_gen = StepGenerator($dispatch_at(fib, 2), this_generator, N1, A, trail)
_st = yield (_gen, None)
while _st is not DONE:
    # body continuation: current solution available
    ...
    _st = yield (_gen, None)
```

`StepGenerator` wraps the child dispatch function. `this_generator` is passed as the child's `parent`, so the child yields `(this_generator, None)` on solution and `(this_generator, DONE)` on exhaustion. The trampoline routes these back to us.

when `fib` is locked at compilation time, the dispatch function is pre-captured into `base_globals` as `$disp_fib_2`, and the generated code uses `$disp_fib_2` directly instead of `$dispatch_at(fib, 2)`:

```python
_gen = StepGenerator($disp_fib_2, this_generator, N1, A, trail)
```

### Tail recursion optimization (TRO)

when the last goal in a clause body is a self-recursive `Call` and all preceding goals are deterministic (at most one solution, no `StepGenerator` allocation), the compiler replaces the recursive `StepGenerator` allocation with argument reassignment and a loop restart. This reduces the per-recursion memory cost from O(n) generator objects to O(1).

**Eligible pattern** — accumulator-style recursion:

```clausal
acc_sum([], ACC, ACC),
acc_sum([H, *T], ACC, RESULT) <- (
    NEWACC == ACC + H,
    acc_sum(T, NEWACC, RESULT)
)
```

Clause 2 qualifies: the prefix goals (`Evaluate`) are deterministic, and the tail call is to `acc_sum` itself. The compiled code uses a `while True` loop:

```python
def AccSum__3(this_generator, parent, arg0, arg1, arg2, trail):
    while True:
        _d0, _d1, _d2 = deref(arg0), deref(arg1), deref(arg2)
        _tro = False
        # clause 1 (base case) — unchanged
        match (_d0, _d1, _d2):
            case ...:
                ...
                yield (parent, None)
        # clause 2 (TRO)
        match (_d0, _d1, _d2):
            case ...:
                mark = trail.mark()
                try:
                    ...  # deterministic prefix
                    _tro_arg0 = deref(T)
                    _tro_arg1 = deref(NEWACC)
                    _tro_arg2 = deref(RESULT)
                    _tro = True
                finally:
                    trail.undo(mark)
        if _tro:
            arg0, arg1, arg2 = _tro_arg0, _tro_arg1, _tro_arg2
            continue
        break
    yield (parent, DONE)
```

**Deterministic goals** (eligible as prefix before a TRO tail call): `Evaluate`, `Unify`, `DoesNotUnify`, `ArithEq`, `ArithNeq`, comparisons (`>`, `<`, `>=`, `<=`), `in_`, `NotIn`, `Not` (NAF), `And` of deterministic goals, `IfExpr`, `once`, `findall`, `bagof`, `setof`.

**Not eligible**: clauses where any prefix goal is a predicate `Call` (nondeterministic — the `StepGenerator` while-loop has multiple solutions that cannot be resumed after a TRO restart) or `Or`.

**Safety check**: tail call arguments that are variables from head pattern decomposition (e.g., `T` from `[H, *T]`) are only allowed when there is at least one deterministic prefix goal, which implies the decomposed argument was ground. A **runtime ground-check** (`is_var()`) on these specific captured args provides provable correctness: if any checked arg is an unbound Var, execution falls back to a normal `StepGenerator` call. Passthrough variables (same `Var` at the same position in head and tail call) are always safe and skip the runtime check.

**Indexed predicates**: TRO works across both groundness-keyed dispatch and list structural dispatch:

- **Groundness dispatch**: bucket functions use "signal mode" — setting a shared `_tro_state` list instead of looping internally. The dispatch closure checks `_tro_state[0]` after each `yield from` and re-dispatches with new args, potentially selecting a different bucket (e.g., the base-case bucket for key=0 after counting down from N).
- **List structural dispatch**: a TRO-aware body compiler is passed to `_build_list_dispatch_guard`. The `while True` loop wraps the entire dispatch guard, so TRO restarts re-evaluate the nil/cons/var branching with the new args.
- **Fallback functions** (all clauses, called when no arg is ground) use "loop mode" TRO — the same internal `while True` + `continue` as non-indexed predicates.

**Limitations**:

- Disabled for [tabled](tabling.md) predicates (SLG tabling has its own suspension protocol).
- Self-recursion only — mutual recursion (A→B→A) is not detected.
- Nondeterministic prefix goals (predicate calls before the tail call) prevent TRO.

Detection: `_detect_tro_clause`, `_is_deterministic_goal`, `_tro_args_safe`.
Code generation: `_compile_tro_body`, `_compile_tro_tail`.

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

### WFS: tabled NAF

when `Not(operand=Call(LoadName(f), ...))` targets a tabled predicate (detected via `db.is_tabled(f, arity)`), the compiler emits a call to `_naf_tabled` instead of the inline NAF generator pattern:

```python
_m = trail.mark()
if _naf_tabled("f", arity, (arg0, ..., argN), trail, _table_store):
    k_stmts
trail.undo(_m)
```

`_naf_tabled` is a plain function (not a generator) that checks the table store and either performs standard NAF (complete table), delays the negation (evaluating table — cycle through negation), or treats an absent entry as "no answers". This works identically from both simple and trampoline compiled code.

`_naf_tabled` and `_table_store` (a reference to `db.table_store`) are injected into `base_globals` when `db` is not None. Non-tabled predicates fall through to the existing inline NAF codegen.

---

## Meta-predicates

`findall/3`, `bagof/3`, `setof/3`, and `forall/2` are compiled as **special forms** — not as builtin predicate calls, but as inline AST patterns emitted directly by `compile_goal`. This is necessary because the inner goal must be compiled at compile time (not dispatched at runtime).

### findall/3

`findall(Template, Goal, Bag)` collects all solutions of `Goal`, snapshots `Template` for each, and unifies the resulting list with `Bag`. It always succeeds — if `Goal` has no solutions, `Bag` unifies with `[]`.

Generated code pattern:

```python
_fa_results = []
_fa_m = trail.mark()
def _fa_gen():
    <compiled Goal with k_stmts = [yield None]>
    return; yield
for _ in _fa_gen():
    _fa_results.append(_deref_walk(<template_expr>))
trail.undo(_fa_m)
_fa_um = trail.mark()
if unify(<bag_expr>, _fa_results, trail):
    <k_stmts>
trail.undo(_fa_um)
```

Key details:
- The inner goal compiles in **simple mode** as a sub-generator (same pattern as `once` and NAF).
- `_deref_walk` (from `clausal.logic.solve`) recursively dereferences the template, capturing a ground snapshot of each solution.
- The trail mark/undo around the sub-generator ensures inner bindings don't leak.
- `_deref_walk` and `_set_of_dedup` are injected into `base_globals`.

### bagof/3

Same as `findall` but wraps the unify+continuation block in `if _fa_results:`, so it **fails** when the inner goal has no solutions.

### setof/3

Same as `bagof` with an additional deduplication step before unification:

```python
_fa_results = _set_of_dedup(_fa_results)
```

`_set_of_dedup` tries `dict.fromkeys` for hashable items, falling back to O(n²) equality-based dedup for non-hashable terms.

### forall/2

`forall(Cond, Action)` succeeds if for every solution of `Cond`, `Action` also succeeds. Desugared at compile time to:

```python
not (Cond and not Action)
```

No new codegen — piggybacks on existing NAF compilation.

---

## First-argument indexing

when a predicate has 4 or more clauses, `compile_predicate` and `compile_predicate_trampoline` automatically build a first-argument index. Clauses are partitioned by the first argument's value: ground-first-arg calls jump directly to the matching clause subset via a dict lookup, while unbound-Var-first-arg calls fall back to the full unindexed path.

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
    pred_cls: str | None = None,
    body_compiler = None,
) -> Callable
```

- `db=None` is allowed; a `_GlobalsDb` proxy is used for signature lookups from `globals_`.
- `pred_cls` is the predicate's HANDLE (a loaded module's predicates are rows in its `Database`, bound to handles); the install goes through the mutation gate onto the row it names. (It was a `PredicateMeta` class until W4b-3 slice 7 deleted the class.)
- `globals_` is the module globals dict; predicate names in the body resolve from this dict.
- Returns the compiled dispatch function and also installs it via `_install(db, functor, arity, fn, lazy_fn, pred_cls)`.

### _install

`_install` stores the dispatch function:
1. `db.set_dispatch(functor, arity, fn, lazy_fn)` — on the predicate's row in the Database. This is where a loaded module's predicates keep their dispatch: the module binds each one to its handle, and `$dispatch_at`/`resolve_predicate_row` read the row.
2. When `pred_cls` is given — a class no Clausal database owns — on that class's row too (a private detached one on the `db=None` path).

A lazy recompile closure is registered alongside. when `assertz`/`retract` invalidates dispatch by setting `row.dispatch_fn = None`, the next dispatch through the row (`$dispatch_at`, `db.get_dispatch`) invokes the lazy closure to recompile from the current clause list.

---

## `_GlobalsDb` — db-free compilation

when `db=None`, the compiler uses a `_GlobalsDb(globals_)` proxy that implements only `signature_for(functor, arity)`. It looks up the named predicate class from `globals_` and returns `cls._signature`. This covers keyword-argument normalisation during compilation without requiring a live Database.

---

## Generated function execution

`functiondef_to_function(funcdef_ast, globals_)` (in `clausal.codegen`) compiles a function-definition AST node and returns the resulting function object with the given globals dict. This is how `compile_predicate` turns AST into a callable.

---

## `_DbDispatchAdapter` — backward compatibility shim

when a called predicate has no predicate binding in module globals (e.g. a bare `Module` whose clauses were asserted from Python, or predicates not yet loaded), the compiler injects a `_DbDispatchAdapter`:

```python
class _DbDispatchAdapter:
    def _get_dispatch(self):
        return self._db.get_dispatch(self._functor, self._arity)
```

`$dispatch_at` accepts the `_get_dispatch()` protocol this adapter implements, so the compiled call site (`$dispatch_at(fname, N)`) is unchanged.

---

## Module-level pipeline (V2)

`clausal.logic.compiler_v2.compile_module()` orchestrates the full module compilation pipeline. The import hook (`PredicateLoader.exec_module`) drives this after executing the Phase A bytecode.

### Two-phase architecture

```clausal
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:compiler_phases"
```

**Phase A** (AST transform time):
- `EmbedTransformer` transforms `.clausal` source into Python AST
- Accumulates `_module_items`: `DirectiveItem`, `ImportFromItem`, `ImportModuleItem`, `ModuleDeclItem`, `PrivateDeclItem`
- Bytecode is cached in `__pycache__/` via `SourceLoader`

**Phase B** (module exec time):
- Bytecode execution binds each predicate name to its handle (`$declare_head`, which records the head's field names until the flip point, step 4a-bis) and collects `Predicate` nodes; it created a load-time `PredicateMeta` class per name until W4b-3 slice 5
- `compile_module()` takes over from there

### compile_module steps

```python
compile_module(predicate_nodes, module_items, module_dict, module_name)
```

| Step | What happens |
|---|---|
| 0. Imports | `_process_imports()` — execute `-import_from` and `-import_module` directives, populating `module_dict`. Bare module names (e.g. `regex`) are resolved via `clausal.modules` fallback. |
| 1. Term expansion | `run_term_expansion()` — apply `term_expansion/4` rules to predicate nodes. See [Term Expansion](term_expansion.md) |
| 1b. Goal expansion | `run_goal_expansion()` — walk clause bodies and apply built-in expansions. Currently: regex auto-binding (ALLCAPS named groups → Unify chains) and static pattern pre-compilation. See [goal_expansion](#goal-expansion-v3-3) below. |
| 2. [Directives](directives.md) | `_process_directives()` — apply `-dynamic`, `-discontiguous`, `-table`, `-shallow` metadata to the database |
| 3. Declarations | `_process_declarations()` — process `-module` and `-private` declarations: a declared atom binds its spelling, a declared data functor its interned name; a predicate keeps the handle the module body bound |
| 4. assertz clauses | Each `Predicate` node is asserted via `logic_module.define_predicate()` onto the Database row; the row's signature is stamped from the rewriter's head field names and its `declared_at` from the `$declare_head` record |
| 4a-bis. The flip point | `_flip_bindings()` registers the Database as a handle owner (every binding is already a handle; the class it rebound is deleted); the module body's `$declare_head` record retires here, so the Database answers alone from now on |
| 5. Compile | Each `(functor, arity)` is compiled via `compile_predicate_trampoline` (or `compile_predicate_shallow` for shallow predicates) |
| 6. [Tabling](tabling.md) | Tabled predicates are wrapped with `make_tabled_wrapper_trampoline` from `clausal.logic.tabling` |
| 7. Locking | Non-[dynamic](directives.md) predicates' rows are locked (`_lock_static_predicates(db)`) to prevent runtime modification |

### How predicate nodes are collected

During Phase A bytecode execution, the import hook provides closures:

- `$define_predicate(pred, lm)` — appends the `Predicate` node to a list (instead of asserting immediately as in the v1 pipeline)
- `$assert_fact(term)` — converts the ground term to a `Predicate` node and appends

This defers compilation until all clauses and directives are known, enabling term expansion to see and rewrite the full module before anything is compiled.

### .pyc caching

Phase A bytecode is cached by Python's `SourceLoader` machinery. On cache hit, `source_to_code()` doesn't run — the transform is skipped entirely. Module items (directives/imports) are re-parsed from source in a lightweight pass since they aren't part of the bytecode cache. See [caching.md](caching.md).

---

## Goal expansion

`clausal.logic.goal_expansion.run_goal_expansion()` walks clause bodies and applies built-in goal transformations between term expansion and directive processing. It recurses into `And`, `Or`, `Not`, and `IfExpr` nodes, applying expansion rules to leaf goals.

### Regex auto-binding

when a [`match/2` or `search/2`](regex.md) call has a static pattern string containing ALLCAPS or leading-underscore named groups, goal expansion rewrites it to `match/3` + `Unify` chains:

```clausal
-allow_singletons
# Named-group auto-bind (see regex.md): the second occurrence of YEAR
# and MONTH lives inside the pattern STRING, invisible to the singleton
# counter's AST-Name check — a known, documented lint gap for this
# specific pattern, not a mistake in this example.
# Source:
parse(S, YEAR, MONTH) <- match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", S)

# After expansion (conceptual):
parse(S, YEAR, MONTH) <- (
    match(_re_0, S, _groups),
    YEAR is ++_groups["YEAR"],
    MONTH is ++_groups["MONTH"]
)
```

The compiled regex pattern is injected into `module_dict` as `_re_0`, `_re_1`, etc. Identical patterns are deduplicated. Group-to-variable mapping uses `_collect_vars_from_term()` to find clause variables by field name (lowercased, stripped of leading underscore).

Lowercase named groups are NOT auto-bound — they function as regex-only groups (useful for backreferences). This gives explicit control over which groups leak into the logic variable namespace.

### Pattern pre-compilation

All static patterns (string literals) in `match` and `search` calls are pre-compiled via `re.compile()` and stored in `module_dict`. The goal's pattern argument is replaced with a `LoadName` referencing the compiled object. Dynamic patterns (f-strings, variables) are left unchanged.

### `clausal.modules` — standard library package

`clausal/modules/` is a Python package that acts as the standard library search path for Clausal module imports. A `ModulesFinder` meta path finder (registered in `import_hook.py`) redirects bare module names to `clausal.modules.<name>`, so `-import_from(regex, [match, ...])` resolves to `clausal.modules.regex` transparently.

Currently provides:
- **`regex`** — match/2,3, search/2,3, replace/4, split/3, findall/3
- **`log`** — get_logger/1,2, debug/1,2, info/1,2, warning/1,2, error/1,2, critical/1,2, log/3, set_level/2, get_level/2, is_enabled_for/2, stream_handler/2, file_handler/2, set_formatter/2, add_handler/2, remove_handler/2, basic_config/1. See [logging.md](logging.md)
- **`date_time`** — now/1, now_utc/1, today/1, date/4, time/4, datetime/7, timedelta/3, date_add/3, date_sub/3, date_diff/3, datetime_string/3, weekday/2, date_between/3, timestamp/2, datetime_string_iso/2, date_string_iso/2. All predicates produce and consume real Python `datetime` objects (`datetime.date`, `datetime.time`, `datetime.datetime`, `datetime.timedelta`) — not custom term types. See [Date & Time](date_time.md)
- **`yaml_module`** — Read/2, write/2, ReadAll/2, WriteAll/2, ReadFile/2, WriteFile/2, Get/3. Wraps PyYAML (`yaml.safe_load`/`yaml.safe_dump`); data represented as native Python dicts/lists/scalars. See [yaml.md](yaml.md)

---

*See also: [Architecture](architecture.md) — where the compiler fits in the overall pipeline · [Indexing](indexing.md) — first-argument indexing built on top of compiled dispatch · [Specialization](specialization.md) — call-site specialization via partial deduction.*
