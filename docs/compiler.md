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
| PredicateMeta term `fib(n=_v, ...)` | `MatchClass(fib, patterns)` — structural match |
| List `[HEAD, *TAIL]` | `MatchAs(name="_lcapN")` + deferred list guard (see below) |
| `DictTerm({"k": V, ...})` | `MatchAs(name="_dcapN")` + dict unify guard |
| `SetTerm({1, 2, 3})` | `MatchAs(name="_scapN")` + set unify guard |

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
| `DoesNotUnify(l, r)` | `if _dif(l, r, trail): k_stmts` — dif/2 constraint (see [constraints.md](constraints.md)) |
| `Evaluate(l, r)` | same as `Unify` but `r` is compiled via `arith_to_ast_expr` (arithmetic evaluation) |
| `ArithEq(l, r)` | `if _fd_eq(l, r, trail): k_stmts` — CLP(FD) arithmetic equality |
| `ArithNeq(l, r)` | `if _fd_ne(l, r, trail): k_stmts` — CLP(FD) arithmetic disequality |
| `Lt/LtE/Gt/GtE` | `if _fd_lt/_fd_le/_fd_gt/_fd_ge(l, r, trail): k_stmts` — CLP(FD) comparison |
| `And(l, r)` | `compile_goal(l, ..., compile_goal(r, ..., k))` (right-nested) |
| `Or(l, r)` | two independent mark/undo blocks; both branches inline |
| `Not(goal)` | inner goal as sub-generator + flag; succeed only if inner fails. If inner is a call to a tabled predicate, emits `_naf_tabled` call instead (well-founded semantics). |
| `IfExpr(test, body, orelse)` | Reified ITE: three-way check for reifiable conditions, single-evaluation `_found` flag for general conditions. See [reified_ite.md](reified_ite.md). |
| `Call(LoadName("Once"), [goal])` | Sub-generator + `for` loop with `break` after first yield. Bindings escape to continuation. |
| `Call(LoadName("FindAll"), [tmpl, goal, bag])` | Sub-generator collects `_deref_walk(tmpl)` per solution, undoes inner bindings, unifies result list with `bag`. Always succeeds (empty list on failure). |
| `Call(LoadName("BagOf"), [tmpl, goal, bag])` | Same as `FindAll`, but fails if no solutions (empty result list). |
| `Call(LoadName("SetOf"), [tmpl, goal, bag])` | Same as `BagOf`, plus deduplication via `_set_of_dedup` before unifying with `bag`. |
| `Call(LoadName("ForAll"), [cond, action])` | Desugared to `not (cond and not action)` — uses existing NAF compilation. |
| `In(elem, coll)` | `for _x in deref(coll): mark ...; if unify(elem, _x, trail): k; undo` |
| `NotIn(elem, coll)` | found-flag pattern |
| `Call(LoadName(f), args)` | `for _ in f._get_dispatch()(args, trail, k): k_stmts` |

The Call case is the core cross-predicate dispatch. `f` is the predicate name; it is resolved from the compiled function's `__globals__` at runtime, not by a string lookup in a central registry.

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

- `head_types`: `{name: cls}` for any `PredicateMeta` class found in clause heads (needed for `case fib(n=_v):` structural match patterns).
- `py_thunks`: `{key: fn}` for any `PyThunk` lambda found in clause bodies (the `++expr` Python-escape syntax).
- `call_targets`: `set[(fname, arity)]` for every `Call(LoadName(f), ...)` node found in clause bodies.

**`_inject_resolved_targets(targets, base_globals, db, globals_)`** — resolution loop that ensures each called `(fname, arity)` pair has a `_get_dispatch()`-compatible object in `base_globals`:

1. If `fname` is already in `base_globals` and is a `PredicateMeta` class → already present; apply locked dispatch caching (see below) and continue.
2. If `fname` is a known builtin → inject a `BuiltinPredicate` adapter.
3. If `db` is not `None` and `fname` is in the database → inject a `_DbDispatchAdapter` wrapping `db.get_dispatch`.
4. Dotted names (`mod.Pred`) are resolved via attribute traversal through the module dict.

### Locked dispatch caching

For predicates that are **locked** (non-dynamic, `_locked = True`) at compilation time, `_inject_resolved_targets` also captures the dispatch function directly into `base_globals` under a stable key:

```python
_disp_key("Edge", 2)  →  "_disp_Edge_2"
base_globals["_disp_Edge_2"] = Edge._dispatch_fn
```

The code-generation functions (`_dispatch_call_trampoline`, `_dispatch_call_iter`) check the current compilation context for cached keys. When a callee's dispatch key is present, the generated `StepGenerator` construction uses the cached local directly instead of calling `._get_dispatch()` at every invocation:

```python
# Unlocked / dynamic predicate (default):
_gen = StepGenerator(Foo._get_dispatch(), this_generator, arg0, arg1, trail)

# Locked predicate — cached dispatch closure:
_gen = StepGenerator(_disp_Foo_2, this_generator, arg0, arg1, trail)
```

`_disp_Foo_2` is a reference to a pre-captured dispatch function in the compiled function's `__globals__` — one attribute lookup is eliminated on every call site.

**When dispatch caching fires:** Locking happens *after* initial module compilation, so intra-module calls within the same `.clausal` file are compiled before their callees are locked. Dispatch caching fires for cross-module calls (where the imported module is already locked), for explicit recompilations after locking, and for predicates compiled via `compile_predicate` / `compile_predicate_trampoline` after the callee's `_lock()` has been called.

**Safety:** On lazy recompile (triggered by `assertz`/`retract`), the whole compilation reruns with the updated clause list, so any cached dispatch functions are refreshed. Dynamic predicates (`_locked = False`) never get cached; they always use `._get_dispatch()`.

### Call-site bucket specialisation

Locked dispatch caching captures the dispatch *closure* for locked callees. Call-site specialisation goes one step further: when the argument in an indexed position is a statically-known literal at the call site, the dispatch closure is bypassed entirely and the specific *bucket function* is referenced directly.

`_inject_bucket_refs_trampoline` runs after `_inject_resolved_targets`. It scans each clause body for `Call` nodes whose callee is locked and has `_index_plans`. For each such call site it converts the term-level argument to an AST expression, extracts a static key via `_static_call_key`, and — if the key appears in the callee's bucket dict — injects the bucket function into `base_globals` under a readable string key:

```python
base_globals["Color.bucket(pos=0, 'red')"] = Color._index_plans[0]["red"]
```

`_dispatch_call_trampoline` then emits an `ast.Name` referencing that key instead of either `_disp_Color_1` or `Color._get_dispatch()`:

```python
# static literal 'red' in indexed position 0 — direct bucket ref:
_gen = StepGenerator(Color.bucket(pos=0, 'red'), this_generator, 'red', trail)

# arg is a variable — falls back to cached dispatch closure:
_gen = StepGenerator(_disp_Color_1, this_generator, X_, trail)
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
_gen = StepGenerator(fib._get_dispatch(), this_generator, N1, A, trail)
_st = yield (_gen, None)
while _st is not DONE:
    # body continuation: current solution available
    ...
    _st = yield (_gen, None)
```

`StepGenerator` wraps the child dispatch function. `this_generator` is passed as the child's `parent`, so the child yields `(this_generator, None)` on solution and `(this_generator, DONE)` on exhaustion. The trampoline routes these back to us.

When `fib` is locked at compilation time, the dispatch function is pre-captured into `base_globals` as `_disp_fib_2`, and the generated code uses `_disp_fib_2` directly instead of `fib._get_dispatch()`:

```python
_gen = StepGenerator(_disp_fib_2, this_generator, N1, A, trail)
```

### Tail recursion optimization (TRO)

When the last goal in a clause body is a self-recursive `Call` and all preceding goals are deterministic (at most one solution, no `StepGenerator` allocation), the compiler replaces the recursive `StepGenerator` allocation with argument reassignment and a loop restart. This reduces the per-recursion memory cost from O(n) generator objects to O(1).

**Eligible pattern** — accumulator-style recursion:

```clausal
AccSum([], ACC, ACC),
AccSum([H, *T], ACC, RESULT) <- (
    NEWACC := ACC + H,
    AccSum(T, NEWACC, RESULT)
)
```

Clause 2 qualifies: the prefix goals (`Evaluate`) are deterministic, and the tail call is to `AccSum` itself. The compiled code uses a `while True` loop:

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

**Deterministic goals** (eligible as prefix before a TRO tail call): `Evaluate`, `Unify`, `DoesNotUnify`, `ArithEq`, `ArithNeq`, comparisons (`>`, `<`, `>=`, `<=`), `In`, `NotIn`, `Not` (NAF), `And` of deterministic goals, `IfExpr`, `Once`, `FindAll`, `BagOf`, `SetOf`.

**Not eligible**: clauses where any prefix goal is a predicate `Call` (nondeterministic — the `StepGenerator` while-loop has multiple solutions that cannot be resumed after a TRO restart) or `Or`.

**Safety check**: tail call arguments that are variables from head pattern decomposition (e.g., `T` from `[H, *T]`) are only allowed when there is at least one deterministic prefix goal, which implies the decomposed argument was ground. A **runtime ground-check** (`is_var()`) on these specific captured args provides provable correctness: if any checked arg is an unbound Var, execution falls back to a normal `StepGenerator` call. Passthrough variables (same `Var` at the same position in head and tail call) are always safe and skip the runtime check.

**Indexed predicates**: TRO works across both groundness-keyed dispatch and list structural dispatch:

- **Groundness dispatch**: bucket functions use "signal mode" — setting a shared `_tro_state` list instead of looping internally. The dispatch closure checks `_tro_state[0]` after each `yield from` and re-dispatches with new args, potentially selecting a different bucket (e.g., the base-case bucket for key=0 after counting down from N).
- **List structural dispatch**: a TRO-aware body compiler is passed to `_build_list_dispatch_guard`. The `while True` loop wraps the entire dispatch guard, so TRO restarts re-evaluate the nil/cons/var branching with the new args.
- **Fallback functions** (all clauses, called when no arg is ground) use "loop mode" TRO — the same internal `while True` + `continue` as non-indexed predicates.

**Limitations**:

- Disabled for tabled predicates (SLG tabling has its own suspension protocol).
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

When `Not(operand=Call(LoadName(f), ...))` targets a tabled predicate (detected via `db.is_tabled(f, arity)`), the compiler emits a call to `_naf_tabled` instead of the inline NAF generator pattern:

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

`FindAll/3`, `BagOf/3`, `SetOf/3`, and `ForAll/2` are compiled as **special forms** — not as builtin predicate calls, but as inline AST patterns emitted directly by `compile_goal`. This is necessary because the inner goal must be compiled at compile time (not dispatched at runtime).

### FindAll/3

`FindAll(Template, Goal, Bag)` collects all solutions of `Goal`, snapshots `Template` for each, and unifies the resulting list with `Bag`. It always succeeds — if `Goal` has no solutions, `Bag` unifies with `[]`.

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
- The inner goal compiles in **simple mode** as a sub-generator (same pattern as `Once` and NAF).
- `_deref_walk` (from `clausal.logic.solve`) recursively dereferences the template, capturing a ground snapshot of each solution.
- The trail mark/undo around the sub-generator ensures inner bindings don't leak.
- `_deref_walk` and `_set_of_dedup` are injected into `base_globals`.

### BagOf/3

Same as `FindAll` but wraps the unify+continuation block in `if _fa_results:`, so it **fails** when the inner goal has no solutions.

### SetOf/3

Same as `BagOf` with an additional deduplication step before unification:

```python
_fa_results = _set_of_dedup(_fa_results)
```

`_set_of_dedup` tries `dict.fromkeys` for hashable items, falling back to O(n²) equality-based dedup for non-hashable terms.

### ForAll/2

`ForAll(Cond, Action)` succeeds if for every solution of `Cond`, `Action` also succeeds. Desugared at compile time to:

```python
not (Cond and not Action)
```

No new codegen — piggybacks on existing NAF compilation.

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

---

## Module-level pipeline (V2)

`clausal.logic.compiler_v2.compile_module()` orchestrates the full module compilation pipeline. The import hook (`PredicateLoader.exec_module`) drives this after executing the Phase A bytecode.

### Two-phase architecture

```clausal
# skip
Phase A: Source → EmbedTransformer → module_items + Python AST bytecode
Phase B: compile_module(predicate_nodes, module_items, module_dict) → compiled predicates
```

**Phase A** (AST transform time):
- `EmbedTransformer` transforms `.clausal` source into Python AST
- Accumulates `_module_items`: `DirectiveItem`, `ImportFromItem`, `ImportModuleItem`, `ModuleDeclItem`, `PrivateDeclItem`
- Bytecode is cached in `__pycache__/` via `SourceLoader`

**Phase B** (module exec time):
- Bytecode execution creates PredicateMeta classes and collects `Predicate` nodes
- `compile_module()` takes over from there

### compile_module steps

```python
compile_module(predicate_nodes, module_items, module_dict, module_name)
```

| Step | What happens |
|---|---|
| 0. Imports | `_process_imports()` — execute `-import_from` and `-import_module` directives, populating `module_dict`. Bare module names (e.g. `regex`) are resolved via `clausal.modules` fallback. |
| 1. Term expansion | `run_term_expansion()` — apply `TermExpansion/4` rules to predicate nodes. See [Import System](import.md) |
| 1b. Goal expansion | `run_goal_expansion()` — walk clause bodies and apply built-in expansions. Currently: regex auto-binding (ALLCAPS named groups → Unify chains) and static pattern pre-compilation. See [goal_expansion](#goal-expansion-v3-3) below. |
| 2. Directives | `_process_directives()` — apply `-dynamic`, `-discontiguous`, `-table`, `-shallow` metadata to the database |
| 3. Declarations | `_process_declarations()` — process `-module` and `-private` declarations, create PredicateMeta classes for declared functors |
| 4. Assert clauses | Each `Predicate` node is asserted via `logic_module.define_predicate()`. Clauses are synced to `pred_cls._clauses` |
| 5. Compile | Each `(functor, arity)` is compiled via `compile_predicate_trampoline` (or `compile_predicate_shallow` for shallow predicates) |
| 6. Tabling | Tabled predicates are wrapped with `make_tabled_wrapper_trampoline` from `clausal.logic.tabling` |
| 7. Locking | Non-dynamic predicates are locked (`pred_cls._lock()`) to prevent runtime modification |

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

When a `Match/2` or `Search/2` call has a static pattern string containing ALLCAPS or trailing-underscore named groups, goal expansion rewrites it to `Match/3` + `Unify` chains:

```clausal
# Source:
parse(S, YEAR, MONTH) <- Match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", S)

# After expansion (conceptual):
parse(S, YEAR, MONTH) <- (
    Match(_re_0, S, _groups),
    YEAR is ++_groups["YEAR"],
    MONTH is ++_groups["MONTH"]
)
```

The compiled regex pattern is injected into `module_dict` as `_re_0`, `_re_1`, etc. Identical patterns are deduplicated. Group-to-variable mapping uses `_collect_vars_from_term()` to find clause variables by field name (lowercased, stripped of trailing underscore).

Lowercase named groups are NOT auto-bound — they function as regex-only groups (useful for backreferences). This gives explicit control over which groups leak into the logic variable namespace.

### Pattern pre-compilation

All static patterns (string literals) in `Match` and `Search` calls are pre-compiled via `re.compile()` and stored in `module_dict`. The goal's pattern argument is replaced with a `LoadName` referencing the compiled object. Dynamic patterns (f-strings, variables) are left unchanged.

### `clausal.modules` — standard library package

`clausal/modules/` is a Python package that acts as the standard library search path for Clausal module imports. A `ModulesFinder` meta path finder (registered in `import_hook.py`) redirects bare module names to `clausal.modules.<name>`, so `-import_from(regex, [Match, ...])` resolves to `clausal.modules.regex` transparently.

Currently provides:
- **`regex`** — Match/2,3, Search/2,3, Replace/4, Split/3, FindAll/3
- **`log`** — GetLogger/1,2, Debug/1,2, Info/1,2, Warning/1,2, Error/1,2, Critical/1,2, Log/3, SetLevel/2, GetLevel/2, IsEnabledFor/2, StreamHandler/2, FileHandler/2, SetFormatter/2, AddHandler/2, RemoveHandler/2, BasicConfig/1. See [logging.md](logging.md)
- **`date_time`** — Now/1, NowUTC/1, Today/1, Date/4, Time/4, DateTime/7, TimeDelta/3, DateAdd/3, DateSub/3, DateDiff/3, FormatDate/3, ParseDate/3, DayOfWeek/2, DateBetween/3. All predicates produce and consume real Python `datetime` objects (`datetime.date`, `datetime.time`, `datetime.datetime`, `datetime.timedelta`) — not custom term types. See [Date & Time](date_time.md)
- **`yaml_module`** — Read/2, Write/2, ReadAll/2, WriteAll/2, ReadFile/2, WriteFile/2, Get/3. Wraps PyYAML (`yaml.safe_load`/`yaml.safe_dump`); data represented as native Python dicts/lists/scalars. See [yaml.md](yaml.md)

---

*See also: [Architecture](architecture.md) — where the compiler fits in the overall pipeline · [Indexing](indexing.md) — first-argument indexing built on top of compiled dispatch · [Specialization](specialization.md) — call-site specialization via partial deduction.*
