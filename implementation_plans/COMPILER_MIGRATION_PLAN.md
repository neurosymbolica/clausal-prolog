# Compiler migration plan

From today's `clausal/logic/compiler/` (as described in
`README.md`) to the end state described in
`implementation_plans/COMPILER_TARGET_ARCHITECTURE.md`.

This plan groups the work into **eight slices (A–H)**. Each slice
stands on its own: it lands as a coherent set of commits, leaves
the tree green, and delivers a concrete piece of the target. Slices
have explicit dependencies — but not all of them — so several can
run in parallel if there's reason.

---

## 0. Goals and non-goals

**Goals of this plan:**

- Describe **order, scope, and validation** for each slice.
- Identify risky slices and propose mitigations (parallel
  implementation, feature flags, diff-based regression checks).
- Keep the tree green — every commit passes all tests. Every
  slice leaves the compiler strictly more rigorous than it was.
- Make each slice **reversible** without tangling into later work.

**Non-goals:**

- Line-by-line code changes. This is a plan, not a patch series.
- Performance tuning. The target architecture should not be slower
  than today's; verifying that is part of each slice's validation,
  but optimisation work sits on top of the migration.
- New features. The migration preserves today's observable
  behaviour. Feature additions (JIT, new backends, continuation-TCO)
  come after.

---

## 1. Principles

Eight principles guide the slicing. If a proposed slice violates
one, it's too big or too small.

### M1. Every slice lands with a green test suite

The full compiler-core test subset (~900 tests) plus the full
non-trealla suite (~10,400 tests) passes before a slice ships. No
"temporarily broken" commits even between slices.

### M2. Each slice has a reversible commit boundary

If a slice turns out wrong, `git revert` removes it cleanly.  No
slice depends on internal state left behind by a previous slice
in a way that a revert would corrupt.

### M3. No half-migrated state survives a slice

A slice either fully moves some concern to the new architecture, or
leaves it alone. We don't leave two-ways-to-do-X in the repo between
slices — inside a slice, yes; across slice boundaries, no.

### M4. Parallel implementation for risky slices

The biggest slice (GoalOp IR) runs **in parallel** with the existing
compile path. A feature flag selects which path compiles each
predicate. Both must produce equivalent output (byte-equal AST, or
behavioural equivalence on a test corpus) before the old path
retires.

### M5. Validation is diff-based where possible

For slices that refactor without changing semantics, diff the
compiled AST output before and after. Identical AST → zero semantic
risk. Differences → explicit review.

### M6. Documentation follows behaviour

README and target architecture docs stay in sync with the code.
When a slice lands, the docs for affected parts update with it —
not later in a separate pass.

### M7. The runtime/compile-time boundary is an acceptance criterion

Every slice that touches the package layout must end with
`clausal/logic/compiler/` not importing anything from
`clausal/logic/runtime/` (or whatever the runtime package is
called). CI enforces.

### M8. Each slice has explicit success criteria

Before starting a slice we know what "done" means. A slice isn't
finished because we ran out of time — it's finished when the
criteria are met.

---

## 2. Dependency graph

```
        ┌────────────────────────────────────┐
        │  A. Runtime/compiler separation    │
        │     (physical split, mechanical)   │
        └──────────────────┬─────────────────┘
                           │
        ┌──────────────────┴─────────────────┐
        │  B. CompilationContext completion  │
        │     (finish deferred #2,           │
        │      retire _monolith)             │
        └──────────────────┬─────────────────┘
                           │
               ┌───────────┼───────────┐
               │           │           │
               ▼           ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  C.      │ │  E.      │ │  H.      │
        │  Strategy│ │  Optim.  │ │  Public  │
        │  protocol│ │  passes  │ │  API     │
        └────┬─────┘ └──────────┘ └──────────┘
             │
             ▼
      ┌──────────────────────┐
      │  D. GoalOp IR        │
      │  (parallel impl,     │
      │   feature-flagged)   │
      └──────────┬───────────┘
                 │
         ┌───────┴─────────┐
         ▼                 ▼
   ┌──────────┐      ┌──────────┐
   │ F. Phase │      │ G. Source│
   │   asser- │      │   loc-   │
   │   tions  │      │   ations │
   └──────────┘      └──────────┘
```

Legend:

- **Linear dependency:** A must complete before B.
- **Fan-out:** After B, slices C / E / H can run in parallel.
  D depends on C (the strategy protocol).
- **Fan-in for cleanups:** F and G both depend on D (GoalOp is where
  phase-boundary invariants become expressible and where source
  locations get threaded).

---

## 3. Slice A — Runtime/compiler package separation

**Goal:** Physically separate code that runs *during* predicate
compilation from code that runs *inside* compiled predicates.

**Target end state** (from `COMPILER_TARGET_ARCHITECTURE.md` §7):

```
clausal/logic/
├── compiler/            ← compile-time only
└── runtime/             ← used by compiled code only
    ├── __init__.py
    ├── list_unify.py            – was head_list_unify.py (runtime half)
    ├── body_star_unify.py       – runtime body-Is helpers
    ├── tramp_call.py            – _tramp_call bridge
    └── _list_unify.c            – C-accelerated variants
```

**Current state:** Runtime helpers live in
`clausal/logic/compiler/head_list_unify.py`. That file contains both
runtime functions (executed in compiled code) and the compile-time
fallback import of `_list_unify.c`. The runtime code is also
bundled with the compiler package, so `import clausal.logic.compiler`
pulls in runtime too.

**Work:**

1. Create `clausal/logic/runtime/` with `__init__.py`.
2. Move from `compiler/head_list_unify.py` → `runtime/list_unify.py`:
   - `_head_list_unify_input_py`, `_head_list_unify_output_py`
   - `_head_multi_star_error`
   - The C-extension fallback import logic
3. Move `_body_star_unify`, `_build_star_list`,
   `_build_multi_star_list`, `_in_iter`, `_body_multi_star_unify`
   → `runtime/body_star_unify.py`.
4. Move `_tramp_call` → `runtime/tramp_call.py`.
5. Compiled-code references these by name via `base_globals` — no
   change to generated code. What changes: the `predicate.py`
   `base_globals` construction imports from `runtime/` instead of
   the old compiler-internal location.
6. Move `_list_unify.c`, `_trampoline.c` physically to `runtime/`
   and update `setup.py` extension paths. (`_trampoline.c` may
   belong in `runtime/` or stay with its current Python wrapper;
   decide during the slice.)
7. Delete the old `compiler/head_list_unify.py`.

**Preconditions:** None.

**Validation:**

- All tests pass.
- A new CI check: `grep -r "from clausal.logic.compiler" clausal/logic/runtime/` returns nothing. Runtime must not import from compiler.
- Module import test: `import clausal.logic.runtime` succeeds
  standalone (doesn't pull in compiler).

**Success criteria:**

- `clausal/logic/runtime/` exists with the listed files.
- `clausal/logic/compiler/` no longer contains runtime-only code.
- CI enforces the no-reverse-import rule.

**Risk:** Low. Mechanical move. The names in `base_globals` are
what compiled code sees — as long as those names keep mapping to
the same functions, nothing breaks.

**Reversibility:** Trivial — `git revert` restores the single
commit; nothing downstream depends on runtime having moved.

**Estimated size:** ~1 day. Single PR.

---

## 4. Slice B — `CompilationContext` completion and `_monolith` retirement

**Goal:** Finish what deferred-refactor #2 started. Every compile
function takes `CompilationContext` (already renamed from `CompileCtx`)
or gets ctx via its caller. Thread-local state moves onto ctx. The
`_monolith.py` compatibility layer is deleted.

**Current state:**

- `CompilationContext` dataclass exists (`compile_ctx.py`).
- `_compile_body_impl` takes ctx. Most other helpers take the
  `(db, var_context, trail_name, …)` tuple.
- `_compile_context_local: threading.local` holds
  `locked_dispatch_keys`, `bucket_ref_map`, `joint_bucket_ref_map`.
- `_monolith.py` re-exports ~50 aliases (`_fd_eq_fn`, `_DictTerm_t`
  etc.) into the namespace; `predicate.py` bulk-copies them via
  `for _n in dir(_m)`.
- `__init__.py` delegates unknown attributes to `_monolith`.
- `_m.compile_goal` / `_m.compile_goal_trampoline` lazy access in
  `control_constructs.py`, `ite_reified.py`, `tro.py`.

**Work:**

1. Migrate internal helpers to accept `ctx` (not the tuple).
   Change in cohorts, smallest call-graphs first:
   - Leaf helpers: `_compile_arith_cmp`, `_deref_cmp`, the existing
     `_compile_body_impl` (already done).
   - Mid-layer: `_compile_star_is` et al.; the per-arm helpers in
     `control_constructs.py`; `_compile_reified_ite_*`.
   - Top layer: `compile_goal`, `compile_goal_trampoline`
     dispatchers. Public entry points keep legacy signatures but
     construct ctx at their boundary and pass down.
2. Move thread-local state onto ctx:
   - `ctx.locked_dispatch_keys: frozenset[str]`
   - `ctx.bucket_ref_map: dict[BucketRefKey, str]`
   - `ctx.joint_bucket_ref_map: dict[JointBucketRefKey, str]`
   Remove `_compile_context_local` from `_monolith.py`.
3. Delete `_m.compile_goal` / `_m.compile_goal_trampoline` lazy
   access. Replace with explicit imports from `goal_shallow` /
   `goal_trampoline`. Any cycles are broken by moving the
   appropriate function, not by lazy access.
4. Move the ~50 hoisted runtime-helper aliases out of `_monolith`:
   - Inline each into the submodule that uses it (in most cases
     `predicate.py` — where `base_globals` is constructed).
   - Delete `_monolith.py`.
   - `__init__.py` stops doing `__getattr__` delegation. Private
     helpers that tests / tools import directly get explicit
     re-exports (a curated list, not auto-forwarding) or the
     importer migrates to the precise location.
5. Per-compilation `FreshNames` instance replaces the module-level
   `_compile_counter: list[int]` in `_ast_helpers.py`. `ctx.fresh`
   is the only fresh-name source during a compilation.

**Preconditions:** Slice A complete (so `runtime/` helpers are no
longer coming from `compiler/`; their imports in `predicate.py`
point to the new location).

**Validation:**

- Full test suite green.
- Diff test: compile a fixed set of predicates before and after the
  slice; AST output should be **identical** (same `_v0`, `_m1`
  etc. names because `FreshNames` is deterministic per ctx).
- Grep test: `grep -r "_compile_context_local" clausal/` returns
  nothing. `grep -r "_m\." clausal/logic/compiler/` returns nothing.
  `grep -r "_monolith" clausal/logic/compiler/` returns nothing.

**Success criteria:**

- `clausal/logic/compiler/_monolith.py` does not exist.
- `clausal/logic/compiler/compile_ctx.py` → `context.py` (rename).
- No thread-locals in the compiler package.
- `__init__.py` has ~15 lines of explicit re-exports, no
  `__getattr__`.

**Risk:** Medium. Lots of call sites. Mechanical but touches
everything.

**Mitigation:** Break into sub-slices B1…B5, one per migration
cohort above. Each sub-slice stands on its own.

**Reversibility:** Each sub-slice reverts cleanly; the final
sub-slice (deleting `_monolith`) only lands once every caller has
migrated.

**Estimated size:** ~1–2 weeks across 5 sub-slices.

---

## 5. Slice C — Explicit `Strategy` protocol ✅ done

**Goal:** Replace the scattered strategy-specific code with the
`Strategy` protocol from the target architecture (§9).

**Current state:**

- Shallow and trampoline strategies live in separate files
  (`goal_shallow.py`, `goal_trampoline.py`) with co-located helpers.
- Strategy "hooks" are implicit: `_yield_none_stmt()` vs
  `_yield_step_stmt(...)`; `compile_goal` vs `compile_goal_trampoline`;
  `_dr_preprocess` vs identity; function_params constructed
  differently at assembly time.

**Work:**

1. Define `Strategy` protocol in `compiler/strategy.py`.
2. Implement `ShallowStrategy`, `TrampolineStrategy` — small
   classes (~30 lines each) that provide:
   - `emit_leaf_yield(ctx) -> ast.stmt`
   - `emit_exhaustion_yield(ctx) -> ast.stmt | None`
   - `emit_sub_call(ctx, fname, arity, arg_exprs, k_stmts) -> list[ast.stmt]`
   - `preprocess_clause(clause) -> list[Any]`
   - `function_params(ctx, arg_names) -> list[str]`
   - `supports_tro: bool`
   - `supports_destructive_reuse: bool`
3. Migrate call sites that currently switch between shallow /
   trampoline variants of the same concept — they now take a
   `Strategy` argument (usually `ctx.strategy`) and call its
   methods.
4. `compile_predicate_trampoline` and `compile_predicate_shallow`
   become ~5-line wrappers that pick the strategy and call a
   unified `compile_predicate(functor, arity, clauses, *, strategy, …)`.
5. Deduped helpers from earlier work (`_compile_body_impl`,
   `_compile_predicate_call_impl`, etc.) switch from taking
   explicit `compile_goal_fn` / `emit_dispatch` / `preprocess_clause`
   kwargs to reading them from `ctx.strategy`.

**Preconditions:** Slice B complete (ctx is everywhere; strategy
lives on ctx).

**Validation:**

- Full test suite green.
- AST diff test: compiled output identical before and after.
- Strategy exchange test: compile the same predicate with each
  strategy, assert both produce valid generators that enumerate
  the same solution set on a test corpus.

**Success criteria:**

- `compiler/strategy.py` exists with protocol + two impls.
- Every strategy-specific decision in `goal_shallow.py` /
  `goal_trampoline.py` / `ite_reified.py` / `control_constructs.py`
  / `tro.py` routes through `ctx.strategy.<method>()`.
- The `_m.compile_goal` / `_m.compile_goal_trampoline` lazy
  accesses are gone (finished in B, but this slice confirms they
  stay gone).

**Risk:** Medium. Most of the dedup work I've done already anticipates
this structure; turning the kwargs into `ctx.strategy.method()`
calls is the migration.

**Reversibility:** Straightforward — the new `Strategy` abstraction
lives behind a known set of method calls; reverting means putting
back the kwargs.

**Estimated size:** ~1 week.

---

## 6. Slice D — `GoalOp` IR and parallel implementation

**Goal:** Introduce the target-agnostic IR, validate it by running
both paths in parallel, and retire the old path once equivalence
is demonstrated.

**This is the biggest slice.** It also unblocks F and G.

**Status (2026-04-13):** D1 through D7b complete; D7c (legacy
delete) deferred for bake.  See `todo/slice_d_goalop_ir.md` for
the per-sub-slice progress log and validation evidence:

| Sub-slice | What | Status |
|---|---|---|
| D1 | `GoalOp` tagged union | ✅ |
| D2–D3 | `terms_to_goalop` + lowering for the binding/constraint subset | ✅ |
| D4 | Parallel-implementation harness with AST-diff stop-the-line | ✅ |
| D5a–j | Coverage expansion (And/Or/Not/IfExpr/SubCall/MetaCall/list-patterns/tabled-NAF/Fail/PyThunkOp/nested-TupleLiteral) | ✅ |
| D6a | TRO `analyse_ir` parallel shadow | ✅ |
| D6b | destructive_reuse `analyse_ir` parallel shadow | ✅ |
| D6c | Call-site bucket-ref `analyse_ir` parallel shadow | ✅ |
| D6d | Tighten cross-check coverage (thread `db`; "IR ⊇ legacy" audit) | ✅ |
| D7a | Flip `use_ir_path` default to `True` | ✅ baking |
| D7b | Promote IR path to source-of-truth | ✅ baking |
| D7c | Delete legacy `_dispatch_goal` / `_dispatch_goal_trampoline` | ⏳ deferred |

D7c is intentionally held: the value of D7b is the parallel
verification gate, which D7c removes.  Letting both paths run for
one release cycle of green CI catches any latent IR bug before
the safety net comes off.  Slice F (invariants) lands during the
bake.

**Current state:** Goal compilation pattern-matches directly on
`clausal.pythonic_ast.nodes` / `clausal.terms` types inside
`compile_goal` and its children. No intermediate representation.

**Work — as nested sub-slices:**

### D1. Define `GoalOp` tagged union

Single PR. `compiler/ir.py`. Every op type with docstring and
fields. No implementation of anything that uses them yet. This
lands as pure type definitions + a `walk_goal_ops(ir, visit)`
helper for traversal.

### D2. Prototype `terms_to_goalop` for a small subset

Handle: Unify, DoesNotUnify, Evaluate, arithmetic compares (Lt,
LtE, Gt, GtE, ArithEq, ArithNeq), StructuralEq, StructuralNeq,
Sequence (from list-body and from TupleLiteral), in_, NotIn.
Leave And, Or, Not, IfExpr, Call, MetaCall for later.

Output: a function that takes a clause body and produces a
`GoalOp` tree for the handled subset, raising `NotImplementedError`
for anything else.

### D3. Prototype lowering for the subset

Write `lower_python_shallow(ir, ctx, k_stmts)` and
`lower_python_trampoline(ir, ctx, k_stmts)` that consume the
D2 subset and emit `list[ast.stmt]`. Output should be
byte-for-byte identical to what today's `compile_goal` produces
for the same inputs.

### D4. Parallel-implementation harness

A feature flag (env var or `ctx.use_ir_path: bool`) selects between:

- **Legacy path:** `compile_goal(clause_body, ...)` → AST (today).
- **IR path:** `terms_to_goalop(clause_body, ...)` →
  `lower_python_<strategy>(ir, ctx)` → AST.

For each compiled predicate in test, run **both paths** and
assert AST equivalence. An initial test corpus of ~50 varied
predicates (drawn from `tests/`) proves the subset is complete.
When the subset is below 100% coverage, the IR path
`raise NotImplementedError` falls back to the legacy path.

### D5. Expand `terms_to_goalop` coverage

Extend one construct at a time: And → Sequence normalisation,
Or → Alternate, Not → Negate, IfExpr → Branch with `reified_test`
detection, Call/LoadName → MetaCall (kind enumeration) or SubCall,
list patterns → ListPatternUnify.

Each addition lands as a small PR with its own corpus test.
Coverage progresses toward 100%.

### D6. Move optimisation passes to operate on `GoalOp`

- `_detect_tro_clause` → `tro.analyse(ir) -> TROPlan`
- `_find_destructive_reuse_goals` → `destructive_reuse.analyse(ir) -> set[GoalOpId]`
- Call-site bucket-ref specialisation rewrites `SubCall` nodes'
  `direct_bucket_ref` field.

Each optimisation in turn, gated by its own sub-slice.

### D7. Retire the legacy path

D7 split into three sub-slices during execution:

**D7a. Flip `use_ir_path` default to `True`.**  Smallest meaningful
step: `CompilationContext.use_ir_path` defaults from `False` to
`True`.  The D4 IR shadow + D6 cross-checks now run on every
compile, not just under `CLAUSAL_IR_PATH=1`.  No behaviour change —
lowering still uses legacy results.  ~5% test-suite overhead from
always-on shadowing.  Reversible: one-line revert.

**D7b. Promote IR path to source-of-truth.**  `_compile_body_impl`
returns the IR-produced statements when `_run_ir_parallel`
succeeds; legacy fold runs alongside as the verification gate.
Provably safe because every IR run since D4 has asserted
byte-for-byte equality with legacy *before* returning.

**D7c. Delete the legacy dispatcher.**  Pull out
`goal_shallow._dispatch_goal`, `goal_trampoline._dispatch_goal_trampoline`,
their pattern-match helpers, and the parallel cross-check
machinery.  Public entry points (`compile_goal`, `compile_body`,
etc.) keep their signatures but reduce to
`terms_to_goalop` + `lower_python_<strategy>`.

D7c blocks on the bake: each round of CI under D7a/D7b is a
parallel-verification gate that D7c removes.  Held until either
(a) one full release cycle of green CI, or (b) Slice E lands and
moves the optimisation hint reads onto SubCall hints — at which
point the legacy path becomes the only remaining consumer of the
old code and deletion is mechanical.

**Preconditions:** Slice C complete (Strategy exists; lowering is
strategy-aware).

**Validation:**

- Each D-sub-slice: AST diff — new path produces identical output
  to old path for its covered subset.
- Full test suite green through every sub-slice (legacy path is
  the fallback).
- Performance benchmark: compilation time with IR path should be
  within 20% of legacy path. Significantly slower would indicate
  the lowering is doing extra work we haven't accounted for.

**Success criteria:**

- `ir.py` exists with the full `GoalOp` hierarchy.
- `terms_to_goalop.py` + `lower_python_shallow.py` +
  `lower_python_trampoline.py` exist and handle every goal shape.
- Legacy `compile_goal` and `compile_goal_trampoline` are gone.
- All analyses and optimisations operate on `GoalOp`.

**Risk:** High. The IR is new architecture. Mistakes in the
lowering cause silent miscompilation — tests catch most but not
all.

**Mitigation:**

- Parallel implementation throughout D1–D6 (legacy path is the
  safety net). No retirement until every D5 addition has been
  shipped green.
- AST-diff assertion runs on every compilation in CI during the
  transition. Any divergence fails the build.
- Retirement waits for a full release cycle of default-on IR path
  before deleting the legacy code.

**Reversibility:** Complete through D6 — feature flag flips back.
After D7 (retirement), reverting the retirement commit restores
the legacy path.

**Estimated size:** ~4–8 weeks. This is the most ambitious slice.

---

## 7. Slice E — Optimisations as independent passes

**Goal:** Each optimisation becomes its own pass file with clear
before/after contract on `GoalOp` trees.

**Target structure:**

```
compiler/optimisations/
├── __init__.py
├── indexing.py          – groundness / joint / secondary / first-arg
├── tro.py               – tail recursion optimisation
├── destructive_reuse.py – dead-source container reuse
└── call_site.py         – bucket-ref specialisation
```

**Current state:**

- `tro.py` exists as a submodule but mixes analysis + rewrite +
  lowering-concern.
- `destructive_reuse.py` exists but similar mix.
- Indexing (`arg_index.py`) is analysis + runtime dispatch builder
  mixed.
- Call-site specialisation is spread across
  `_inject_bucket_refs_trampoline` + `_compile_context_local` +
  `_dispatch_call_trampoline`.

**Work:**

1. Each optimisation splits into:
   - `analyse(ir) -> Plan` — pure analysis on IR.
   - `apply(ir, plan) -> ir` — rewrites IR nodes with optimisation
     hints.
   - (Runtime-dispatch construction stays in `phases/plan.py`
     for indexing, because it happens pre-IR.)
2. Each pass runs in a well-defined position in the pipeline
   (after body IR, before lowering; DR before TRO; call-site
   specialisation last).
3. Each pass has a **round-trip test**: apply the pass to an IR
   tree, apply it again — result must be idempotent.
4. Each pass has a **no-op test**: on a corpus of predicates
   where the optimisation doesn't apply, output must be identical
   to input.
5. Each pass has a **correctness test**: compile a small test
   suite with the optimisation on and off; behaviour must be
   equivalent (same solutions enumerated).

**Preconditions:** Slice D complete through D7b (IR is
source-of-truth; D6 analyses exist as parallel shadows).  D7c is
**not** a precondition — Slice E moves the optimisation hint
reads onto SubCall hints, which is what *enables* clean D7c.

**Scheduling note (2026-04-13):** Slice F is scheduled before
Slice E in the post-D7b order; see §13.  E's reorganisation is
substantial and it's the path to D7c, but F is small / additive
/ high-payoff and acts as a safety net while D7b bakes.

**Pre-E follow-up — meta-call inner coverage.**  `walk_goal_ops`
does not descend into `MetaCall.args`, so the D6 analyses miss
`SubCall`s nested inside `once(...)` / `findall(...)` / etc.
Legacy has the same blind spot, so the D6 cross-checks still
agree, but it's a real coverage hole D7c will inherit.  Close
this before E so the unified `analyse(ir) → Plan` shape lands
with full meta-call recursion from day one.

**Validation:**

- Full test suite green with all optimisations on.
- Full test suite green with each optimisation **individually**
  disabled (a test matrix).
- Performance benchmark: compilation time should not increase;
  compiled-predicate runtime for hot workloads should not
  regress.

**Success criteria:**

- `compiler/optimisations/` directory exists.
- Each optimisation is a single file.
- Each has a documented before/after contract.
- Each can be disabled via a `ctx.enabled_optimisations: frozenset[str]`
  field (useful for debugging and benchmarking).

**Risk:** Medium. Reorganisation of existing logic; no new
functionality. But subtle ordering dependencies between
optimisations could hide latent bugs.

**Mitigation:** The disable-each-optimisation-individually test
matrix exposes bad interactions.

**Reversibility:** Straightforward file moves; revertable per-pass.

**Estimated size:** ~2 weeks.

---

## 8. Slice F — Phase-boundary invariant assertions

**Goal:** Make the invariants named in `README.md` §10 and the
target architecture §8 into actual runtime checks at phase
boundaries.

**Current state:** Invariants are documented in comments and
docstrings. Violations are detected (if at all) by generated code
failing at runtime with cryptic errors.

**Work:**

1. Define `InvariantError` — a distinct exception class.
2. Write per-phase assertion functions:
   - `assert_body_vars_preallocated(ctx, clauses)` — phase 5 pre
   - `assert_call_targets_resolved(ctx)` — phase 2 post
   - `assert_mark_undo_paired(funcdef)` — phase 6 post (walks AST)
   - `assert_trampoline_done_yield_present(funcdef)` — phase 6 post
3. Wire into the pipeline functions — each phase function runs its
   pre/post assertions.
4. Assertions are **always on** in tests and CI. In production
   builds they can be disabled via `-O` (standard Python
   `__debug__` gating), but we default to on even in production
   until we have confidence.
5. When an assertion fires, error message includes: phase name,
   predicate identity, offending clause index, specific violation.

**Preconditions:** Slice D complete through D7b (IR is
source-of-truth; phase boundaries are stable enough to assert
against).  D7c is not a precondition.

**Scheduling note (2026-04-13):** F is the **immediate next
slice** after D7b.  The IR promotion makes phase boundaries
crisp; F locks them in with runtime assertions.  Small,
additive, low-risk — acts as a safety net while D7b bakes
toward D7c.

**Status (2026-04-13):** F1 through F4 complete.  Invariants 5
(TRO safety) and 6 (DR safety) are already enforced inline by
the analyses themselves; adding runtime assertions would just
re-run the analysis with no marginal value.  F is functionally
done.

| Sub-slice | Invariant | Status |
|---|---|---|
| F1 | #1 body-vars-preallocated (Phase 5 entry) | ✅ |
| F2 | #2 call-targets-resolved (Phase 1 exit) | ✅ |
| F3 | #3 mark/undo paired (Phase 6 post) | ✅ |
| F4 | #4 trampoline DONE yield (Phase 6 post, emit_done=True) | ✅ |
| F5 | #5 TRO safety | ⏭ enforced inline by `_tro_args_safe` |
| F6 | #6 DR safety | ⏭ enforced inline by `_find_destructive_reuse_goals` |

F3 surfaced a real latent dead-mark in `_compile_setup_call_cleanup`
(allocated `_scc_m = trail.mark()` that no `undo` consumed) —
removed; behaviour-preserving (verified by full suite green at
10504 passed / 90 skipped under both default and
`CLAUSAL_IR_PATH=1`).

**Validation:**

- Introduce each assertion; run the test suite; ensure no
  assertion fires spuriously.
- Targeted negative tests: deliberately break an invariant in a
  test predicate; confirm the correct assertion fires with a
  readable message.

**Success criteria:**

- All six invariants from README §10 have corresponding
  assertions.
- Test suite green with assertions on.
- A `tests/test_invariant_errors.py` file exercises each
  assertion's failure mode.

**Risk:** Low. Assertions are additive; if none fire, nothing
else changes.

**Reversibility:** Trivial (assertions are pure additions).

**Estimated size:** ~3–5 days.

---

## 9. Slice G — Source-location fidelity

**Goal:** Resolve `todo/ast_source_locations.md`. Every emitted AST
node carries the source position of the term it was compiled
from. `fix_missing_locations` becomes an assertion that no
location is missing, rather than a silent fill-in-with-zeros.

**Current state:** `fix_missing_locations(funcdef)` is called at
the end of each predicate-compile. It silently labels every
generated AST node with the outer `FunctionDef`'s line/column
(usually 0:0). Tracebacks from compiled code are useless.

**Work:**

1. **Write the failing test first.** Compile a predicate whose body
   contains a Python-raising goal (e.g. division by zero). Assert
   that the traceback's innermost frame inside the compiled
   function points at the **source line** of the goal. Expect
   this to fail today — that's the starting point.
2. Thread source positions through `terms_to_goalop` — every
   `GoalOp` node carries a `position: Position | None` field
   inherited from the term it was lowered from.
3. Thread source positions through lowering — emitted `ast.*`
   nodes get `lineno` / `col_offset` from the `GoalOp.position`.
4. Replace `ast.fix_missing_locations(funcdef)` with a walker
   that asserts every node has a location set. If any don't, it's
   a bug in the lowering that needs fixing, not silent filling.
5. Expand the test: several predicate shapes (ITE, catch,
   sub-call, list-pattern) each verify traceback line numbers.

**Preconditions:** Slice D complete (GoalOp is where positions
live).

**Validation:**

- The new tests pass.
- Full test suite green.
- Manual check: compile `clausal/examples/` predicates; trigger
  errors; tracebacks point at `.clausal` source lines.

**Success criteria:**

- No `fix_missing_locations` calls remain in the compiler.
- Every `GoalOp` has an explicit `position` field.
- Every emitted `ast.*` node has `lineno` / `col_offset` set.
- Tracebacks from compiled predicates are useful.

**Risk:** Low–medium. Threading through positions is mechanical,
but getting every code path is tedious; the invariant-assertion
walker catches misses.

**Reversibility:** Straightforward — revert restores the old
`fix_missing_locations` call.

**Estimated size:** ~1 week.

---

## 10. Slice H — Public API cleanup

**Goal:** The public `clausal.logic.compiler` surface is
**explicit, documented, stable, and small**.

**Current state:**

- `__init__.py` delegates unknown attributes to `_monolith` via
  `__getattr__`. Private helpers leak through.
- Many tests import `from clausal.logic.compiler import _body_multi_star_unify`
  etc. — implementation details of the old monolith.
- `solve.py`, `compiler_v2.py`, `visualize.py`, `term_expansion.py`
  and `database_ops.py` import various compile functions.

**Work:**

1. Catalogue every `from clausal.logic.compiler import X` in the
   codebase. Classify each X:
   - **Public API** — legitimate caller of a documented function.
   - **Leaked private** — test imports a private helper; should
     be fixed to import from the precise submodule or from
     `clausal.logic.runtime` as appropriate.
2. Update each leaked import to its new canonical location.
3. Define `__all__` in `compiler/__init__.py`:
   - `compile_predicate`, `compile_predicate_ast`
   - `compile_predicate_trampoline`, `compile_predicate_shallow`
     (back-compat aliases)
   - `compile_predicate_trampoline_ast`, `compile_predicate_shallow_ast`
   - `Strategy`, `ShallowStrategy`, `TrampolineStrategy`
   - `CompilationContext`
   - `CompiledPredicate`, `DispatchPlan`
4. Remove `__getattr__` delegation.
5. Document each public name: docstring on function, type
   annotations, one-liner in `README.md` §12 *Public API*.

**Preconditions:** Slices B (to retire `_monolith`), D (to have
the final set of types in place).

**Validation:**

- Full test suite green.
- `grep -r "from clausal.logic.compiler import _" clausal tests`
  returns nothing outside the compiler package itself.
- `grep -r "getattr.*clausal.logic.compiler" clausal tests`
  returns nothing.

**Success criteria:**

- `__init__.py` has an explicit `__all__` and no `__getattr__`.
- No external file imports a private name from the compiler.

**Risk:** Low. Mostly mechanical.

**Reversibility:** Trivial — restore the `__getattr__` shim if
needed; each import fix reverts cleanly.

**Estimated size:** ~3 days.

---

## 11. Validation strategy across the migration

### Per-slice

Each slice has specific validation listed above. Common to all:

- Full test suite (10,400 non-trealla tests) passes.
- AST diff: for slices that refactor without semantic change,
  output is byte-for-byte identical to before.
- Grep-based structural assertions (no `_m.`, no `_monolith`,
  no `__getattr__`, etc.) become CI checks as they're
  established.

### Cross-slice

- **Parallel-implementation harness (slice D):** A CI job compiles
  a fixed test corpus under every feature-flag combination and
  asserts output equivalence. Surviving every combination is the
  criterion for retiring the legacy path.

- **Performance benchmark suite:** A small set of representative
  predicates (append/3, reach/2, a mid-size logic puzzle, a
  CLP(FD) constraint problem) compiled and run before and after
  each slice. Compilation time + predicate-call throughput
  tracked over the migration. Regressions require investigation
  before the slice ships.

- **Documentation synchronisation check:** Before a slice merges,
  run a markdown-link-check over `clausal/logic/compiler/README.md`
  and `implementation_plans/COMPILER_TARGET_ARCHITECTURE.md`.
  Any stale file path or class-name reference is a blocker.

### End-to-end

After slice H (final), one verification pass:

1. The README describes the code as it exists — no aspirational
   bits left.
2. Every principle P1–P10 from the target architecture holds.
3. The deferred-refactor list in `COMPILER_MODULE_SPLIT.md` is
   reduced to "no outstanding items" or moved to `todo/` if any
   genuinely new follow-ups emerged.
4. A new contributor can be pointed at the README, read it
   linearly, and arrive at working knowledge of the compiler
   in a reading session.

---

## 12. Risk summary and mitigations

| Slice | Risk level | Mitigation                                                                |
|-------|------------|---------------------------------------------------------------------------|
| A     | Low        | Mechanical move; CI enforces no reverse-import.                           |
| B     | Medium     | Break into 5 sub-slices; AST diff ensures no semantic change.             |
| C     | Medium     | Leverages existing dedup; AST diff applies.                               |
| D     | **High**   | Parallel implementation throughout; one-release default-on before retire. |
| E     | Medium     | Individual-disable matrix exposes bad interactions.                       |
| F     | Low        | Assertions are additive.                                                  |
| G     | Low–med    | Failing test first; invariant walker catches misses.                      |
| H     | Low        | Grep-based checks; per-import fixes.                                      |

The single high-risk slice is D (GoalOp IR). Everything else is
low or medium risk. D's risk is mitigated by parallel implementation
— the legacy path remains available and correct throughout D1–D6,
only retiring after D7 when equivalence is demonstrated.

---

## 13. Ordering and parallelism options

### Original plan

The dependency graph (§2) allows:

- **Conservative order:** A → B → C → D → E → F → G → H.
  Linear, single-thread.

- **Moderately parallel:**
  - Sequential: A → B
  - Parallel after B: C, E, H
  - After C: D
  - After D: F, G (parallel)

- **Aggressive:** A, B begin concurrently if B's sub-slices
  can be sequenced to not depend on A (they can for some —
  internal `_monolith` cleanup doesn't need A). Not recommended
  — the coordination cost is high relative to the savings.

Original recommendation: **moderately parallel**. A and B
together take 2–3 weeks. Then C / E / H run in parallel (~1–2
weeks each), while D starts on its sub-slices independently
(~4–8 weeks). F and G land in the tail after D.

Total calendar time: ~8–12 weeks under the moderate plan, ~6–10
weeks if D is the bottleneck and others finish earlier.

Total engineering effort: ~12–16 person-weeks, dominated by D.

### Actual ordering as executed (2026-04-13 update)

A, B, C completed.  D ran linearly through D1 → D7b, with E and H
deferred until after D's heavy lifting was complete (the parallel
C/E/H approach was not pursued — D drove the schedule).

Post-D7b ordering, with D7c held for bake:

```
  D7b (✅ done, baking)
       │
       ├─ F  ← immediate next: small, additive, safety-net
       │
       ├─ pre-E follow-up: meta-call inner coverage (item #2)
       │
       └─ E  ← unblocks clean D7c
              │
              └─ D7c (delete legacy dispatcher)
                     │
                     └─ G, H  (parallel, both small)
```

**Rationale for F-before-E.**  E reorganises optimisation passes
into a uniform `analyse(ir) → Plan` shape with hint-reading
lowering — substantial reorg, ~2 weeks per the slice estimate.
F is small (~3–5 days) and lands runtime invariant assertions at
phase boundaries.  Doing F first means the bake under D7a/D7b
runs with stricter correctness gates while waiting for E to land.

**D7c gating.**  D7c blocks on either the bake completing or E
landing (whichever comes first).  E is the cleaner trigger:
once optimisation hints live on `SubCall` and lowering reads
them, the legacy dispatcher's only consumers are gone and the
delete is mechanical.

---

## 14. What's not in this plan

Explicitly out of scope for the migration:

- **Performance optimisations beyond preserving today's perf.**
  JIT indexing, continuation-TCO, inline-body-in-dispatch all
  have todo/ files — they come **after** the target architecture
  is in place. They become easier to implement once the pipeline
  has clear phases and the IR exists.

- **New backends (C / LLVM / WASM).** Architecturally supported
  by the target, but a future workstream on its own.

- **Source-level changes to `.clausal`.** The parser and term
  definitions are unchanged. Only the compiler package is
  affected.

- **Tests that import private compiler helpers** may change
  imports (slice H) but not test logic.

- **External callers** (`solve.py`, `compiler_v2.py`,
  `visualize.py`) change imports if necessary; their internal
  logic is unaffected.

- **Database and predicate-class interactions.** The contract
  with `Database.set_dispatch()` and `PredicateMeta._dispatch_fn`
  stays the same. Slice B's ctx migration doesn't affect this
  boundary.

---

## 15. Exit criteria for the whole migration

The migration is complete when, and only when, all of the
following hold:

- Every principle P1–P10 from the target architecture document
  is realised in the code.
- Every section of `README.md` describes code that exists, with
  no caveats or "currently differs" notes.
- CI enforces the runtime/compile-time boundary, the
  no-reverse-import rule, and the phase-boundary invariants.
- The test suite passes in all feature-flag combinations that
  still exist (after slice D retires the legacy path, this
  collapses to the single post-migration path).
- Performance benchmark results show no regression beyond 5%
  on any measured workload.
- The migration-specific feature flags (`use_ir_path`, etc.)
  are removed from the code.
- Documentation and code agree — descriptive language only, no
  aspirational language remaining in the README.

When these hold, the target architecture is the architecture.
Further work (new backends, new optimisations) is independent
of the migration.

---

## 16. A word on the human cost

This plan is ~3 months of focused engineering effort. Not a
weekend project. The biggest slice (D) has an inherent pace —
you can't rush the IR design without paying for it in bugs
later. Every slice has a gate (tests, review, benchmarks) that
takes time regardless of how fast the coding goes.

The pay-off is commensurate:

- A compiler a new contributor can understand in hours rather
  than weeks.
- An architecture that accommodates the planned futures
  (JIT, C backend, continuation-TCO) without a rewrite.
- Confidence, grounded in assertions and diff-based validation,
  that the compiler does what it says.

The alternative — keep iterating on the current architecture —
doesn't get us there. Every refactor I've done on this branch
so far has been surface improvements: dedup, split, extract.
They're good. They're also the near-fruit. The remaining
improvements require the structure this plan builds.

If the plan looks sound, the migration can start at slice A
whenever you're ready. No slice before A has any dependency,
and A is a clean, low-risk first step.
