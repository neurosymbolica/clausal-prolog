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
  solution and `(parent, _DONE)` at exhaustion; sub-predicate calls
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
Each `FunctionDef` is compiled via `ast.fix_missing_locations` +
`compile()` + `exec()` into an actual Python function. The
`base_globals` dict becomes the function's `__globals__`.

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
| `_ast_helpers.py`         | AST leaf-builders (`_name`, `_call`, `_if`, `_assign_mark`, `_fresh`) and naming constants. |
| `_vars.py`                | Variable helpers: `_var_python_name`, `_collect_vars`, `_collect_bound_vars`.               |
| `compile_ctx.py`          | `CompileCtx` dataclass — bundles `db`, `var_context`, `trail_name`, `self_name`, `parent_name`. Partial migration; many helpers still take the tuple directly. |
| `head_list_unify.py`      | **Runtime** helpers for bidirectional list-pattern unification, plus `_tramp_call` simple↔trampoline bridge. Not compile-time. |
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
| `_monolith.py`            | **Legacy residue.** Holds hoisted runtime-helper aliases (`_fd_eq_fn`, `_DictTerm_t`, …), the `_compile_context_local` thread-local, and re-export shims. Slated for retirement (deferred refactor). |
| `__init__.py`             | Public API re-exports. `__getattr__` delegates unknown attributes to `_monolith` for tests that still import private helpers. |

---

## 4. Key data structures

### `Clause` (from `clausal.logic.database`)

```
Clause:
    head: Any              # Compound, functor-dataclass instance, or Call(LoadName, args)
    body: list[Any]        # goal terms (And, Or, Call, Unify, …)
```

Heads may include list patterns, Compound functors, or dataclass
instances (for named-field predicates). Bodies are a flat list —
conjunction is represented as sequential elements, not nested `And`
(destructive-reuse explicitly flattens `And` during its preprocess).

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

### `CompileCtx` (dataclass, `compile_ctx.py`)

```
CompileCtx:
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
                while _st_N is not _DONE:
                    <k_stmts>
                    yield (parent, None)               # solution
                    _st_N = (yield (_gen_N, None))     # next
            finally:
                trail.undo(_mark)
    yield (parent, _DONE)                              # exhaustion
```

- Sub-predicate calls go through `StepGenerator` + `yield` handoff.
  The Python call stack does **not** grow — the `clausal.logic.trampoline`
  driver pumps the generators.
- Every compiled trampoline function speaks the *Step protocol*:
  - Each solution: `yield (parent, None)`
  - Exhaustion: `yield (parent, _DONE)`
  - Sub-call: `yield (child_gen, None)`; receive `None` to continue,
    `_DONE` to know the child exhausted.
- Default for all predicates. Supports unbounded recursion depth.

### When they interact

Trampoline code can call shallow-compiled predicates via
`_tramp_call(dispatch, args, trail)` (in `head_list_unify.py`, despite
its name — it's a cross-strategy bridge). Internally it runs a
mini-trampoline around the shallow generator.

Shallow code compiling a meta-predicate (once, catch, findall) may
actually invoke the shallow goal compiler recursively — even when
called from a trampoline context, control_constructs helpers
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
refs; `_dispatch_call_trampoline` emits them when the
`_compile_context_local.bucket_ref_map` knows about the target.

---

## 7. List patterns and bidirectional unification

Head list patterns like `append([HEAD, *TAIL], B, [HEAD, *RESULT])`
need *bidirectional* unification because the third argument may be
either a concrete list (input-mode) or an unbound Var (output-mode).
Python `match` can only *destructure* sequences, so the list pattern
compiles as a `MatchAs` wildcard capture plus a runtime guard.

Two phases per list-pattern guard, implemented in
`head_list_unify.py` and emitted by `head_match.compile_head_to_match_case`:

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
`head_list_unify._body_multi_star_unify`.

Extended block comment: the top of `head_list_unify.py` has the
full design rationale with worked examples.

---

## 8. State

Compilation holds a small amount of mutable state beyond the
clause-tree and output AST.

| State                                  | Owned by                             | Lifetime                                    | Purpose                                                                  |
|----------------------------------------|--------------------------------------|---------------------------------------------|--------------------------------------------------------------------------|
| `var_context: dict`                    | Caller of `compile_body` / `compile_goal` | One clause compilation                      | Var._id → Python local name mapping.                                    |
| `_compile_counter: list[int]`          | `_ast_helpers.py`                    | Process lifetime (module global)            | Fresh-name generator state (`_fresh("_m")` → `_m42`, `_m43`, …).         |
| `_compile_context_local: threading.local` | `_monolith.py`                    | Per-thread, set by `compile_predicate_*`    | `locked_dispatch_keys` (Phase 7 dispatch caching), `bucket_ref_map` / `joint_bucket_ref_map` (Phase 10d/10f call-site specialisation). |
| `_tro_state: list`                     | `predicate.py` → `base_globals`      | Per compiled function                       | `[flag, arg0, ..., argN-1]` — the TRO signal used by "signal"-mode TRO. |
| `base_globals: dict`                   | `predicate.py`                       | Per compiled function (becomes `__globals__`) | All runtime helpers, term-class refs, resolved call targets, dispatch caches. |

**The thread-local needs care.** `compile_predicate_trampoline` saves
and restores it via `try/finally` because compilation can recurse
(a predicate might be compiled in response to another predicate's
compilation).  Same for `compile_predicate_shallow`.

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
  resumes when sent any value other than `_DONE`.
- Exhaustion: `yield (parent, _DONE)` exactly once, after which the
  generator returns.
- Sub-call protocol: `yield (child_gen, None)` suspends until the
  caller sends back `None` (child produced a solution) or `_DONE`
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

4. **Trampoline generators yield `(parent, _DONE)` exactly once per
   call, after all solutions.** Enforced by `_build_predicate_trampoline_funcdef`
   appending the `_DONE` yield at the end of the funcdef.

5. **TRO rewrites preserve observable behaviour.** Enforced by
   `_tro_args_safe` refusing rewrite when any prefix goal is
   non-deterministic, and `_detect_tro_clause` requiring the tail call
   to be self-recursive (no alien `parent` changes).

6. **Destructive-reuse is safe.** Enforced by the compile-time checks
   in `_find_destructive_reuse_goals` (source var not head-aliased,
   dead after the call, preceded only by deterministic goals) plus
   the runtime `sys.getrefcount` guard inside `_append_dr__3` etc.

---

## 11. Gotchas and non-obvious decisions

Things a new contributor would otherwise have to reverse-engineer.

- **`_monolith.py` is a compatibility layer.** It predates the module
  split. It holds the ~50 runtime-helper aliases (`_fd_eq_fn`,
  `_DictTerm_t`, …) that generated code references via `base_globals`,
  plus the `_compile_context_local` thread-local. Slated for
  retirement; not yet removed because submodules still reach into it
  via `_m.*` lazy attribute access in a few places (mostly
  `_m._EXTRA_FUNCDEF` and `_m.compile_goal` / `_m.compile_goal_trampoline`
  in cross-strategy calls).

- **`_m.compile_goal` / `_m.compile_goal_trampoline` are lazy accessors.**
  `control_constructs.py`, `ite_reified.py`, `tro.py` all reference
  the goal compilers through a `_m` alias on the `_monolith` module.
  This is because the goal compilers (in `goal_shallow.py` /
  `goal_trampoline.py`) are loaded *after* these modules — the lazy
  attribute lookup defers binding until call time, side-stepping the
  module-load-order cycle.

- **`predicate.py` bulk-copies `_monolith`'s globals.**
  `for _n in dir(_m): globals().setdefault(_n, getattr(_m, _n))`.
  This is how the ~50 hoisted runtime-helper aliases become visible
  to the function bodies in `predicate.py` without individual
  enumeration. Ugly but localised.

- **`forall/2` rewrites to `\+(Cond, \+ Action)` and recurses into
  the *shallow* compile_goal even in trampoline mode.** Documented
  in both `goal_shallow.forall` and `goal_trampoline.forall` arms —
  the rewrite produces only deterministic or simple-negation code,
  so shallow compilation is safe even inside a trampoline predicate.

- **Shallow/trampoline share most meta-predicate compilers.**
  `_compile_once`, `_compile_catch` (plus its `_trampoline` twin),
  `_compile_find_all_core`, etc. live in `control_constructs.py`
  and are used by both strategies. Their inner goal compilation
  uses `compile_goal` (shallow), so `once(foo(X))` inside a
  trampoline predicate runs `foo` in shallow mode. Intentional —
  see the notes in `control_constructs.py`.

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

Importable from `clausal.logic.compiler`:

- `compile_predicate_trampoline(functor, arity, clauses, db=None, body_compiler=None, globals_=None, pred_cls=None) -> Callable` — the main entrypoint.
- `compile_predicate_shallow(functor, arity, clauses, db=None, body_compiler=None, globals_=None, pred_cls=None) -> Callable` — short-stack strategy.
- `compile_predicate(functor, arity, clauses, db=None, ...) -> Callable` — deprecated alias for `compile_predicate_shallow`.
- `compile_predicate_trampoline_ast(...)`, `compile_predicate_shallow_ast(...)`, `compile_predicate_ast(...)` — return the AST `FunctionDef` without executing `compile()`. Used by `clausal.tools.visualize`.
- `compile_goal(goal, db, var_context, trail_name, k_stmts) -> list[ast.stmt]` — shallow body-goal dispatcher.
- `compile_goal_trampoline(goal, db, var_context, trail_name, k_stmts, self_name, parent_name) -> list[ast.stmt]` — trampoline body-goal dispatcher.
- `compile_body(goals, db, var_context, trail_name) -> list[ast.stmt]` / `compile_body_trampoline(...)` — body compilation entry points.
- `term_to_ast_expr(term, var_context, *, eval_arith=True) -> ast.expr` — lower a term.
- `arith_to_ast_expr(term, var_context) -> ast.expr` — lower an arithmetic expression to native Python ops.
- `head_to_match_pattern(...) -> ast.pattern` — clause head → `match` case pattern.
- `compile_head_to_match_case(head, body_stmts, var_context, arity, ...) -> ast.match_case` — full case arm.

Private helpers are re-exported via `__init__.__getattr__` for any
tests / tools that import them directly; these are not considered
stable.

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
