# `clausal.logic.compiler` — architecture guide

This document is the entry point for anyone navigating the compiler.
It describes **what** the compiler does, **where** each piece lives,
**how** the pieces interact, and **why** the design is the way it is.

If you're just looking for an API reference, the public surface is at
the end under *Public API*. Everything before that is oriented around
understanding the compiler as a system.

---

## 1. What this compiler does

It takes a list of `Clause` objects defining a predicate and produces
a Python **generator function** that, when driven, enumerates the
predicate's solutions by non-deterministic search with backtracking.

Input:

```
functor: str
arity:   int
clauses: list[Clause]              # head + body goals
db:      Database | None           # for dispatch lookups + signatures
globals_: dict                     # the .clausal module's globals
```

Output:

```
fn:      Callable                  # installed on db and pred_cls
```

Two output shapes exist, selected per-predicate at compile time:

- **Shallow** (`compile_predicate_shallow`) — a plain Python generator.
  Each solution is surfaced via `yield None`.  Sub-predicate calls
  use Python `for` loops over sub-generators, so the Python call
  stack grows with predicate recursion depth.  Used for bounded-depth
  predicates (fact tables, leaf predicates) declared with the
  `-shallow([...])` directive.
- **Trampoline** (`compile_predicate_trampoline`) — a generator that
  speaks the *Step protocol*: it yields `(parent, None)` for each
  solution and `(parent, DONE)` at exhaustion; sub-predicate calls
  suspend via `StepGenerator(...)` + `yield (gen, None)` so the
  Python call stack stays flat under recursion. The **production
  default**; drives everything unless `-shallow` says otherwise.

See §5 *The two strategies* for the semantic details.

---

## 2. The pipeline

The flow from clauses to installed dispatch function has seven
conceptual phases. Entry point: `predicate.compile_predicate_trampoline`
(or `compile_predicate_shallow`).

```
  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
  │ 1 Globals    │ ──▶  │ 2 Analysis   │ ──▶  │ 3 Dispatch   │
  │   gathering  │      │  (indexing / │      │  selection   │
  │              │      │   TRO)       │      │              │
  └──────────────┘      └──────────────┘      └──────────────┘
                                                      │
                                                      ▼
  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
  │ 7 Install    │ ◀──  │ 6 Codegen    │ ◀──  │ 4+5 Per-     │
  │   (db/class) │      │   (AST →     │      │   bucket     │
  │              │      │   function)  │      │   compile    │
  └──────────────┘      └──────────────┘      └──────────────┘
```

Expanded:

**Phase 1 — Globals gathering** (`globals_env.py`)
One pass over all clauses collects: user-defined term-class types
(needed for `match` pattern resolution), `PyThunk` lambdas (for
f-string escapes and `++()`), and call targets — `(fname, arity)`
tuples for every `Call` / qualified `Call(LoadAttr)` in clause
bodies. See `_collect_globals_info`. These populate `base_globals`,
the dict that becomes the compiled function's `__globals__`.

Targets are then **resolved** (`_inject_resolved_targets`): each
`(fname, arity)` is mapped to the actual `PredicateMeta` class, a
`BuiltinPredicate` adapter, a `_DbDispatchAdapter` shim, or an
imported Python constant. Locked predicates additionally have their
dispatch function cached under `_disp_{fname}_{arity}` so generated
code can skip `fname._get_dispatch()`.

**Phase 2 — Analysis** (`arg_index.py`, `tro.py`)
Two analyses run over the clause list:

- **Indexing analysis** (`_analyze_index_positions`, then
  `_analyze_joint_index_positions` if arity ≥ 2). Picks which
  argument positions (and pairs) make good dispatch keys based on
  selectivity. Output: a list of `(pos, idx_dict, default_fn)` plans
  sorted by selectivity.
- **TRO analysis** (`_detect_tro_clause`, `_get_tro_check_indices`).
  Identifies clauses whose body ends with a self-recursive `Call`
  preceded only by deterministic goals. These can be compiled to a
  *tail-call rewrite* instead of a sub-generator invocation — see §6.

**Phase 3 — Dispatch selection** (`predicate.py`)
Based on the analyses, `compile_predicate_trampoline` picks a dispatch
shape:

```
  no useful index   → one funcdef for all clauses (flat)
  single-pos index  → fallback + per-key buckets + default  (V2-1)
  joint (i, j)      → joint dict + single-i + single-j + fallback  (9b)
  secondary (i → j) → two-level hierarchical dispatch  (9c)
  groundness-keyed  → selector checks each position, picks first ground  (V2-2)
```

All dispatch wrappers (`_make_*_dispatch_*`) live in `arg_index.py`.

**Phases 4 + 5 — Per-bucket compilation**
Each bucket of clauses (including the fallback and the per-index
defaults) is compiled independently into a `FunctionDef`:

- **Phase 4: head → match pattern** (`head_match.py`).  For each
  clause, the head term becomes a Python `match`-statement case
  pattern. List patterns (e.g. `[H, *T]`) compile specially — see
  §7 *List patterns and bidirectional unification*.
- **Phase 5: body compilation** (`goal_shallow.py` /
  `goal_trampoline.py`). The body goal list is compiled
  right-to-left: each goal wraps the next as its continuation
  (`k_stmts`). The innermost `k_stmts` is the leaf-yield (solution
  surfacing).

  `body_compiler = _make_body_compiler_trampoline(db)` returns a
  `(clause, var_context) -> list[stmt]` closure that handles per-clause
  body compilation. The trampoline variant also runs *destructive-reuse
  rewrite* as a preprocess step (see §6).

**Phase 6 — Codegen**  (`clausal.codegen.functiondef_to_function`)
Each `FunctionDef` is compiled via `compile()` + `exec()` into an
actual Python function. The `base_globals` dict becomes the
function's `__globals__`. Source positions on emitted AST nodes
come from the `at_position` scope stack threaded through lowering
(Slice G; see §10 "Source-location invariant"); synthetic
scaffolding inherits the enclosing `FunctionDef`'s position via
`propagate_synthetic_positions` and is marked `_g_synthetic=True`
for the strict-walker check (`assert_all_nodes_located`).

**Phase 7 — Install**  (`predicate._install`)
The top-level dispatch wrapper is registered with the database
(`db.set_dispatch(functor, arity, fn)`) and/or installed on the
`PredicateMeta` class (`pred_cls._dispatch_fn = fn`).

---

## 3. Module map

Each submodule has a docstring at the top describing its scope in
more detail. Listed roughly in the order the pipeline touches them.

| Module                    | Scope                                                                                       |
|---------------------------|---------------------------------------------------------------------------------------------|
| `_ast_helpers.py`         | AST leaf-builders (`_name`, `_call`, `_if`, `_assign_mark`), `FreshNames` per-compilation unique-name generator, and naming constants. |
| `_vars.py`                | Variable helpers: `_var_python_name`, `_collect_vars`, `_collect_bound_vars`.               |
| `compile_ctx.py`          | `CompilationContext` dataclass — bundles `db`, `var_context`, `trail_name`, `self_name`, `parent_name`. Partial migration; many helpers still take the tuple directly. |
| `../runtime/list_unify.py`      | **Runtime** — bidirectional list-pattern unification. Used *inside* compiled predicates (referenced via `base_globals`); not imported by the compiler's own code paths. See `clausal/logic/runtime/`. |
| `../runtime/body_star_unify.py` | **Runtime** — body-Is star-list helpers + `_in_iter`. |
| `../runtime/tramp_call.py`      | **Runtime** — simple↔trampoline bridge. |
| `terms_to_ast.py`         | `term_to_ast_expr`, `arith_to_ast_expr` — lowers a term (Var, Compound, DictTerm, …) to a Python AST expression. Also parsing helpers `_parse_star_segments`, `_is_star_list`, `_count_stars`, `_dotted_name_from_loadattr`. |
| `star_segments.py`        | Body-Is star-list compilation (`[X, *Xs] is Foo`).                                         |
| `globals_env.py`          | `_collect_globals_info`, `_inject_resolved_targets`, `_preallocate_body_vars`, `_GlobalsDb`, `_DbDispatchAdapter`. All Phase-1 globals-dict construction. |
| `head_match.py`           | `head_to_match_pattern`, `compile_head_to_match_case`, `_head_arg_patterns`, multi-star guard compilation. Phase 4. |
| `ite_reified.py`          | Reified if-then-else (Unify / DoesNotUnify / arithmetic-fd comparison test) — shallow + trampoline. Three-way branch (True / False / undetermined). |
| `tabled_naf.py`           | WFS tabled negation (`_naf_tabled` call emission). |
| `control_constructs.py`   | Compilers for meta-predicate goals: `once`, `call_nth`, `count_all`, `setup_call_cleanup`, `freeze`, `when`, `find_all_core` (findall/bagof/setof), `throw`, `catch` (+ trampoline), goal lambdas, comparisons. |
| `goal_shallow.py`         | Shallow-strategy goal + body compilation. Also hosts the **shared** dispatcher helpers (`_compile_deterministic_goal`, `_compile_shared_membership_goal`, `_compile_shared_meta_call`) and shared impls (`_compile_body_impl`, `_compile_predicate_call_impl`, etc.) re-used from trampoline. |
| `goal_trampoline.py`      | Trampoline-strategy goal + body compilation.                                                |
| `list_dispatch.py`        | Single-position list-structure dispatch (`_find_list_dispatch_pos`, `_build_list_dispatch_guard`) and `_lift_clause_at_pos`. |
| `arg_index.py`            | Argument-indexing analysis + all dispatch-builder variants (indexed, joint, secondary, groundness-keyed). Phase 2 + 3. |
| `destructive_reuse.py`    | `_find_destructive_reuse_goals` + `_apply_destructive_reuse` — trampoline-only preprocess. |
| `tro.py`                  | Tail-recursion optimisation: detection + `_compile_tro_tail` / `_compile_tro_body`. Trampoline-only. |
| `predicate.py`            | The three top-level entrypoints (`compile_predicate_trampoline/shallow/ast` + variants), `_build_predicate_{trampoline_,}funcdef`, `_install`. Owns Phase 3 + 7 and orchestrates the others. |
| `__init__.py`             | Public API re-exports. Every exposed name has an explicit import from its canonical owner (no ``__getattr__``; ``_monolith`` retired in slice B6). |

---

## 4. Key data structures

### `Clause` (from `clausal.logic.database`)

```
Clause:
    head: Any              # Compound, functor-dataclass instance, or Call(LoadName, args)
    body: list[Any]        # goal terms (And, Or, Call, Unify, …)
```

Heads may include list patterns, Compound functors, or dataclass
instances (for named-field predicates). Bodies are a flat list of
goals; by convention, conjunction is written as a Python tuple
``(G1, G2, G3)`` (which the AST sees as sequential elements) rather
than as a nested `And` tree. `And` nodes aren't forbidden —
destructive-reuse explicitly flattens them during its preprocess —
but the idiomatic form is the tuple.

Structure preservation in the body matters for external tools that
want to inspect clause bodies (e.g. a meta-interpreter or a code
walker may care that `(G1, G2, G3)` is grouped as three goals versus
a nested `And(G1, And(G2, G3))`). The compiler itself is free to
flatten or re-group internally — both forms have the same compiled
meaning — but tools shouldn't assume the body has been flattened.

### `var_context: dict[int, str]`

Maps `Var._id` → Python local name. Mutated in place as the compiler
discovers Vars. Two kinds of entries:

- **Head vars** — introduced from clause-head patterns (`_v0` from
  `case dog(name=_v0)`). Already bound when the body runs.
- **Body-only vars** — introduced inside body goals. These are either
  pre-allocated via `_preallocate_body_vars` (the default, used by
  `compile_body` / `compile_body_trampoline`) or walrus-introduced
  inline via `(_vN := Var())` in generated expressions.

**Invariant.** By the time `compile_goal` runs on a body goal inside
`compile_body`, every Var reachable from the body tree is already in
`var_context`. This prevents UnboundLocalError in generated code where
branch A walrus-binds a Var that branch B then references bare. The
invariant is enforced by `_preallocate_body_vars` (in `globals_env.py`)
which recursively walks the whole body, including ITE arms and lambda
bodies.

### `CompilationContext` (dataclass, `compile_ctx.py`)

```
CompilationContext:
    db: Database | None
    var_context: dict[int, str]
    trail_name: str
    self_name: str = "this_generator"       # trampoline-only
    parent_name: str = "_tramp_parent"      # trampoline-only
```

Bundles the values that most compile functions need. Partial
migration: `_compile_body_impl` and a few other recently-deduped
helpers take `ctx`; most still take the unpacked tuple. Full
migration is tracked as a deferred refactor.

`self_name` / `parent_name` are kept as fields (rather than hard-coded
constants) so nested compilations can shadow them when they need a
distinct pair — e.g. a NAF mini-trampoline uses `_naf_self` /
`_naf_parent` to keep its suspended generators distinguishable from
the enclosing function's ones. They default to the standard
`this_generator` / `_tramp_parent` names for top-level bodies.

### `k_stmts: list[ast.stmt]` — the continuation

Not a global — it's the per-call *continuation* passed to
`compile_goal(goal, ..., k_stmts)`. Each goal wraps `k_stmts` with
its own execution pattern; the innermost `k_stmts` for a body is a
single leaf-yield (`yield None` or `yield (parent, None)`).

Bodies compile right-to-left so the last goal's code contains
`k_stmts = [leaf_yield]`, and each earlier goal's code places the
resulting stmt list into *its* `k_stmts`. The leaf yield is the
solution-surfacing point.

---

## 5. The two strategies

### Shallow — `compile_predicate_shallow`

```
def functor__arity(arg0, ..., argN, trail, k):
    match (deref(arg0), ..., deref(argN)):
        case (...):                  # one arm per clause
            _mark = trail.mark()
            try:
                <body: nested for-loops over sub-predicate generators>
                yield None           # each solution
            finally:
                trail.undo(_mark)
```

- Sub-predicate calls: `for _ in pred_fn(args, trail, k): <k_stmts>`
- Pure Python generator semantics. Stack grows with recursion depth.
- Safe for: fact tables, leaf predicates, anything with bounded
  call depth. Declared via `-shallow([pred/arity, ...])` in `.clausal`.

### Trampoline — `compile_predicate_trampoline`

```
def functor__arity(this_generator, parent, arg0, ..., argN, trail):
    match (deref(arg0), ..., deref(argN)):
        case (...):
            _mark = trail.mark()
            try:
                _gen_N = StepGenerator(sub_dispatch, this_generator, ..., trail)
                _st_N = (yield (_gen_N, None))        # suspend
                while _st_N is not DONE:
                    <k_stmts>
                    yield (parent, None)               # solution
                    _st_N = (yield (_gen_N, None))     # next
            finally:
                trail.undo(_mark)
    yield (parent, DONE)                              # exhaustion
```

- Sub-predicate calls go through `StepGenerator` + `yield` handoff.
  The Python call stack does **not** grow — the `clausal.logic.trampoline`
  driver pumps the generators.
- Every compiled trampoline function speaks the *Step protocol*:
  - Each solution: `yield (parent, None)`
  - Exhaustion: `yield (parent, DONE)`
  - Sub-call: `yield (child_gen, None)`; receive `None` to continue,
    `DONE` to know the child exhausted.
- Default for all predicates. Supports unbounded recursion depth.

### How solutions reach the caller

When a deeply-nested trampoline predicate finds a solution, the
solution signal ``(parent, None)`` does **not** short-circuit
directly to the top of the search chain. Instead, it traverses
level-by-level:

1. Innermost generator yields ``(parent_1, None)`` — one trampoline hop.
2. Trampoline loop does ``parent_1.send(None)``; ``parent_1`` resumes
   at its ``_st_N = yield (child, None)``, runs its own ``k_stmts``
   (whatever work was queued after the child's call), and eventually
   yields ``(parent_2, None)`` for its own parent — another hop.
3. Repeat up to the root.

Each hop is O(1) — a single ``gen.send()`` call in the C trampoline's
tight ``while(1)`` loop, no Python call-stack growth. So the overall
cost is O(depth) in number of trampoline iterations per solution, but
with a tiny per-hop constant factor. This is qualitatively different
from a ``yield from`` chain, which incurs both Python frame overhead
and linear resume cost at every level.

**What does NOT happen today:** continuation-level tail-call optimisation,
where a predicate whose body has no work after a sub-call could pass
*its own parent* as the child's parent — letting the child yield
directly to the grandparent and skip this level entirely. That would
collapse pass-through frames (O(1) per solution regardless of depth).
The compiler doesn't do this yet. TRO (see §6) handles a narrower case
— self-recursive tail calls within the same predicate — but not general
pass-through elision. Deferred as a future optimisation; see
`todo/continuation_tco.md`.

Greenlets are **not** used in the main search path. A
``continuation_search.py`` module exists but isn't wired into the
trampoline — it's dead code at time of writing. The solution-surfacing
path from a compiled predicate back to a Python ``for``-loop caller
goes through ``trampoline()`` / ``solutions()`` (in
``clausal.logic.trampoline``), which is a plain C loop driving the
generator chain; the Python caller sees solutions one at a time as the
root generator yields ``(None, value)`` to the trampoline's top.

### Cross-strategy interactions

Trampoline code can call shallow-compiled predicates via
``_tramp_call(dispatch, args, trail)`` (in ``clausal.logic.runtime.list_unify``,
despite its name — it's a cross-strategy bridge). Internally it runs
a mini-trampoline around the shallow generator.

Shallow code compiling a meta-predicate (``once``, ``catch``,
``findall``) invokes the shallow goal compiler recursively — even
when called from a trampoline context, ``control_constructs`` helpers
compile their inner goals in shallow mode because the meta-predicate
produces at most one solution per call. **This is a deliberate choice**:
it keeps the code simpler at the cost of using Python's stack for
the inner goal. It relies on the inner goal having bounded depth in
practice.

---

## 6. Optimisations

Applied per-predicate during compilation. Each has a trigger and a
runtime invariant.

### First-argument / groundness-keyed dispatch (V2-1, V2-2)

`arg_index._analyze_index_positions` picks up to three arg positions
that are "selective" — i.e., the clauses partition cleanly by the
runtime key at that position. `_make_groundness_dispatch_*` emits a
selector: at call time, check each plan's position in selectivity
order; the first ground argument triggers its index lookup.

Fires when: ≥ `_INDEX_THRESHOLD` (4) clauses, at least one position
has a majority-ground key distribution.

### Joint and secondary indexing (Phase 9b, 9c)

When arity ≥ 2 and a single-position key doesn't cover enough clauses,
`_analyze_joint_index_positions` tries the product key `(arg_i, arg_j)`.
If coverage still drops below `_JOINT_COVERAGE_THRESHOLD` (0.8),
`_build_secondary_index` attempts a two-level hierarchical dispatch
(split on `arg_i` first, then `arg_j` within each bucket).

### Tail Recursion Optimisation (TRO)

`tro._detect_tro_clause` spots clauses whose body ends with a
self-recursive `Call` preceded only by deterministic goals (`_is_deterministic_goal`
at most one solution, no StepGenerator). `_compile_tro_tail` replaces
the recursive call with an argument-reassignment + loop restart,
avoiding a new StepGenerator allocation per recursion level.

Two modes:
- `"loop"` — the whole predicate funcdef is wrapped in `while True:`
  and TRO clauses restart via `continue`.
- `"signal"` — used inside indexed buckets (where the bucket function
  might be one of several alternatives); sets a shared `_tro_state`
  list signalling the caller to restart.

Trampoline-only.

### Destructive-reuse rewrite

Container-builtin calls (`append/3`, `dict_put/4`, `set_union/3`) have
`_dr_*__N` variants that mutate the source container in-place when the
source is provably dead (no alias in the head, no later use in the body,
no non-deterministic goals between).

`destructive_reuse._find_destructive_reuse_goals` does the analysis;
`_apply_destructive_reuse` rewrites eligible `Call` nodes to
`_dr_append__3` etc. Runs as a preprocess in
`_make_body_compiler_trampoline` before body compilation.

Trampoline-only (the DR builtins are all trampoline-mode).

### Call-site bucket-ref specialisation (Phase 10d/10f)

When a call site's indexed arguments are statically-known constants
(`foo(1, X)`), the compiler emits a direct reference to the predicate's
bucket-function for that key instead of the general dispatch wrapper.
`_inject_bucket_refs_trampoline` populates `base_globals` with these
refs; `_dispatch_call_trampoline` emits them when
`ctx.bucket_ref_map` knows about the target.

---

## 7. List patterns and bidirectional unification

Head list patterns like `append([HEAD, *TAIL], B, [HEAD, *RESULT])`
need *bidirectional* unification because the third argument may be
either a concrete list (input-mode) or an unbound Var (output-mode).
Python `match` can only *destructure* sequences, so the list pattern
compiles as a `MatchAs` wildcard capture plus a runtime guard.

Two phases per list-pattern guard, implemented in
`clausal.logic.runtime.list_unify` and emitted by `head_match.compile_head_to_match_case`:

1. **Input phase** (before the body runs):
   `_head_list_unify_input(target, before_vars, star_var, after_vars, trail)`
   → `True` if target is a list and all vars unified; `None` if target
   is an unbound Var (defer); `False` if target is incompatible.

2. **Output phase** (at each solution yield):
   `_head_list_unify_output(...)` constructs the list from bound vars
   and unifies with target. Called only for guards that returned `None`
   in phase 1. The AST rewriter `_wrap_yields_with_output_guards`
   wraps every `yield` in the body with the output-phase check.

Multi-star patterns (`[*A, X, *B]`) go through
`head_match._compile_multi_star_guard` and
`clausal.logic.runtime.body_star_unify._body_multi_star_unify`.

Extended block comment: the top of `clausal.logic.runtime.list_unify` has the
full design rationale with worked examples.

---

## 8. State

Compilation holds a small amount of mutable state beyond the
clause-tree and output AST.

| State                                  | Owned by                             | Lifetime                                    | Purpose                                                                  |
|----------------------------------------|--------------------------------------|---------------------------------------------|--------------------------------------------------------------------------|
| `var_context: dict`                    | Caller of `compile_body` / `compile_goal` | One clause compilation                      | Var._id → Python local name mapping.                                    |
| `ctx.fresh: FreshNames`                | `CompilationContext`                 | One compilation invocation                  | Fresh-name generator state (`ctx.fresh("_m")` → `_m1`, `_m2`, …; resets per compilation for deterministic AST output). |
| `ctx.locked_dispatch_keys / .bucket_ref_map / .joint_bucket_ref_map` | `CompilationContext` (`ctx_template` in `predicate.py`) | One compilation invocation | Phase 7 dispatch caching + Phase 10d/10f call-site bucket-ref specialisation. |
| `_tro_state: list`                     | `predicate.py` → `base_globals`      | Per compiled function                       | `[flag, arg0, ..., argN-1]` — the TRO signal used by "signal"-mode TRO. |
| `base_globals: dict`                   | `predicate.py`                       | Per compiled function (becomes `__globals__`) | All runtime helpers, term-class refs, resolved call targets, dispatch caches. |

All compile-time state lives on `CompilationContext` (retired from
a thread-local in slice B2c; see
`implementation_plans/SLICE_B_PROGRESS.md`).

---

## 9. Runtime contract

What a compiled predicate function expects from its caller, and what
it promises back.

### Trampoline

Signature: `functor__arity(this_generator, parent, arg0, ..., argN, trail)`.

**Caller provides:**
- `this_generator` — a `StepGenerator` that wraps this very function,
  so nested sub-calls can pass it as their `parent`. `StepGenerator`
  itself handles this automatically.
- `parent` — a `StepGenerator` to yield solutions to, or `None` at the
  top of the search stack (where the `trampoline(...)` driver owns it).
- args — dereferenced once at entry (the `match` subject uses
  `deref(argN)`).
- `trail` — a `Trail` instance for unification bookkeeping.

**Function promises:**
- Every solution: `yield (parent, None)`. The generator suspends and
  resumes when sent any value other than `DONE`.
- Exhaustion: `yield (parent, DONE)` exactly once, after which the
  generator returns.
- Sub-call protocol: `yield (child_gen, None)` suspends until the
  caller sends back `None` (child produced a solution) or `DONE`
  (child exhausted).
- Trail discipline: every mark has a matching undo on the same code
  path. `try/finally` is used for `_mark` blocks that bracket a
  whole clause body.

### Shallow

Signature: `functor__arity(arg0, ..., argN, trail, k)`.

- Pure Python generator. `yield None` per solution.
- `k` is an unused parameter kept for legacy reasons — the continuation
  is inlined into the generated body as `k_stmts` at compile time.
- Sub-calls are `for _ in pred_fn(args, trail, k): <k_stmts>` — no
  Step protocol.

---

## 10. Invariants

Things that are true at phase boundaries, and where they are enforced.

1. **Every Var reachable from a clause body is in `var_context` before
   `compile_goal` runs on any body goal.**
   Enforced by `_preallocate_body_vars` in `compile_body` /
   `compile_body_trampoline`. Used to avoid UnboundLocalError in
   generated code when branches reference the same Var (ITE, Or).

2. **Every call target in clause bodies is resolvable in `base_globals`.**
   Enforced by `_collect_globals_info` + `_inject_resolved_targets` in
   Phase 1. If a target cannot be resolved, a `_DbDispatchAdapter` is
   injected as a shim that raises at runtime rather than at compile
   time.

3. **Every `_mark = trail.mark()` has a matching `trail.undo(_mark)`
   on every code path.**
   Enforced by construction in the emitting helpers (`_assign_mark` +
   `_undo_stmt` come in pairs; ITE and catch arms wrap with
   `try/finally` or emit the undo on every branch).

4. **Trampoline generators yield `(parent, DONE)` exactly once per
   call, after all solutions.** Enforced by `_build_predicate_trampoline_funcdef`
   appending the `DONE` yield at the end of the funcdef.

5. **TRO rewrites preserve observable behaviour.** Enforced by
   `_tro_args_safe` refusing rewrite when any prefix goal is
   non-deterministic, and `_detect_tro_clause` requiring the tail call
   to be self-recursive (no alien `parent` changes).

6. **Destructive-reuse is safe.** Enforced by the compile-time checks
   in `_find_destructive_reuse_goals` (source var not head-aliased,
   dead after the call, preceded only by deterministic goals) plus
   the runtime `sys.getrefcount` guard inside `_append_dr__3` etc.

7. **Every emitted AST node carries a source position** (Slice G).
   Either a real position threaded from the originating `.clausal` /
   `.pl` term via the `at_position` scope stack (see
   `_ast_helpers._POSITION_STACK`, entered by `CompilationContext
   .at_position(pos)` around every IR → AST emission), or — for
   genuinely synthesised compiler scaffolding (arg nodes, dispatch
   `Match` boilerplate, trampoline `DONE` yield, bucket selectors)
   — inherited from the enclosing `FunctionDef`'s position via
   `propagate_synthetic_positions` and marked `_g_synthetic=True`.
   Enforced by `assert_all_nodes_located(..., allow_synthetic=True)`
   run on every compiled `FunctionDef` via `maybe_assert_located`.
   No `ast.fix_missing_locations` anywhere in the compiler — the
   strict walker is the single source of truth and surfaces any
   un-located node as a loud emitter bug (set
   `CLAUSAL_ASSERT_LOCATIONS=0` to disable in emergencies).

---

## 11. Gotchas and non-obvious decisions

Things a new contributor would otherwise have to reverse-engineer.

- **Module-load cycles are broken with function-local imports, not
  a shared shim.** Slice B6 retired ``_monolith.py`` entirely.
  Where a cycle exists (``destructive_reuse`` calling
  ``tro._is_deterministic_goal``; ``control_constructs._lower_inner``
  importing ``lower_python_shallow``; ``_lower_goalop_shared``
  importing ``control_constructs``), the consumer uses a
  function-local import.  Python's import cache makes the per-call
  overhead a single dict lookup.

- **Phase-0.5a runtime-helper aliases live in `predicate.py`.**
  `_dif_fn`, `_fd_eq_fn`, `_DictTerm_t`, `_KWTerm_s`, …  (~50 names
  used to populate `base_globals` for compiled predicates).  They're
  imported individually from their canonical source modules
  (`clausal.logic.constraints`, `clausal.logic.clpfd`,
  `clausal.logic.runtime.*`, etc.).  Previously these lived in
  `_monolith.py` and reached `predicate.py` via
  `for _n in dir(_m): globals().setdefault(_n, getattr(_m, _n))` —
  a bulk-copy hack that slice B1a retired (see
  `implementation_plans/SLICE_B_PROGRESS.md`).

- **`forall/2` rewrites to `not (Cond, not Action)` and lowers via
  the shallow IR pipeline even in trampoline mode.** (In Prolog
  notation this is `\+(Cond, \+ Action)`.) Documented in
  ``_lower_goalop_shared._lower_meta_call`` — the rewrite produces
  only deterministic or simple-negation code, so shallow lowering
  is safe even inside a trampoline predicate.

- **Shallow/trampoline share most meta-predicate compilers.**
  `_compile_once`, `_compile_catch` (whose trampoline branch uses
  `_lower_inner_trampoline`), `_compile_find_all_core`, etc. live
  in `control_constructs.py` and are used by both strategies.
  Their inner goal compilation routes through
  `_lower_inner` (shallow), so `once(foo(X))` inside a trampoline
  predicate runs `foo` in shallow mode. Intentional — see the notes
  in `control_constructs.py`.

- **Freshly-compiled predicates see themselves in `base_globals`.**
  When predicate `Foo` is compiled, `base_globals["Foo"]` is the
  `PredicateMeta` class. Self-recursive calls therefore resolve to
  the class, whose `_get_dispatch()` returns the freshly-installed
  dispatch function — working around the "use before defined"
  chicken-and-egg for recursive calls.

- **Generated function names are `{functor}__{arity}` plus suffixes
  per bucket.** E.g. `append__3`, `append__3__p0_b1` (position-0,
  bucket-1), `append__3__p0_dflt` (position-0 default), etc. The
  suffixes are for debugging / stack-trace readability.

---

## 12. Public API

The stable surface is enumerated in `__init__.__all__`.  Importable
from `clausal.logic.compiler`:

**Predicate compilation entrypoints** (return a callable predicate):

- `compile_predicate_trampoline(functor, arity, clauses, db=None, body_compiler=None, globals_=None, pred_cls=None) -> Callable` — the main entrypoint.  Long-lived computations use the trampoline strategy for bounded stack.
- `compile_predicate_shallow(functor, arity, clauses, db=None, ...) -> Callable` — short-stack strategy (faster steady-state, deep recursion may overflow).
- `compile_predicate(functor, arity, clauses, db=None, ...) -> Callable` — alias for `compile_predicate_shallow`; kept for back-compat.

**AST variants** (return the generated `ast.FunctionDef` without
executing `compile()`; consumed by `clausal.tools.visualize`):

- `compile_predicate_trampoline_ast(...)`, `compile_predicate_shallow_ast(...)`, `compile_predicate_ast(...)`.

**Strategy & context**:

- `Strategy` — protocol that `compile_predicate(...)` dispatches through.
- `ShallowStrategy`, `TrampolineStrategy` — the two built-in implementations.
- `CompilationContext` — dataclass bundling the per-compilation state threaded through the AST lowerers.

**Runtime sentinel**:

- `DONE` — re-exported from `clausal.logic.trampoline`; single-shot
  goal-completion marker yielded by generated predicate generators.

Everything else in this package is a package-internal helper.  Tests
and tools that need to reach private helpers (e.g. `_extract_arg_key`,
`_collect_globals_info`) should import them from their owning
submodule (`clausal.logic.compiler.arg_index`, `.globals_env`, …),
not from the top-level package.  The `_monolith` re-export hub and
`__getattr__` delegation were retired in slice B6; the remaining
private re-exports were removed in slice H.

---

## 13. Further reading

- `implementation_plans/COMPILER_MODULE_SPLIT.md` — the history of
  how this package came to be split from a single 8725-line file.
  Contains the audit findings and deferred-refactor list.
- `implementation_plans/COMPILER_OPTIMIZATION.md` — design notes
  for the indexing and dispatch optimisations (partially stale;
  path references predate the module split, symbol names are current).
- `implementation_plans/COMPILER_REFACTOR.md` — notes on the
  earlier pipeline split (module loading: `EmbedTransformer` →
  `compile_module`), separate from this work.

### Pending / speculative

Open design questions tracked in `todo/`:

- `todo/continuation_tco.md` — continuation-level TCO so a solution
  yield can skip pass-through wrapper frames entirely (referenced
  from §5).
- `todo/jit_indexing.md` — profile and tune indexing thresholds,
  add a user directive for explicit indexing control, and eventually
  a JIT recompilation path for hot predicates.
- `todo/inline_body_in_dispatch.md` — inline single-clause bucket
  bodies directly into the dispatch wrapper, eliminating a generator
  frame per call.
