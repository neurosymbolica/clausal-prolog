# Slice E4+ — lowering reads optimisation hints

> **Self-instruction for the next compiler-refactor session.**
> **When E6 (legacy bypass retirement) lands, delete this file.**

## Before doing anything

1. `cd /workspace/clausal-compiler_refactor`
2. Read `implementation_plans/COMPILER_MIGRATION_PLAN.md` §6 and §7
   — authoritative slice definitions, include status tables for D
   and E.
3. Read `todo/slice_d_goalop_ir.md` — per-sub-slice progress log
   for D (still in bake for D7c; E4+ unblocks that deletion).
4. `git log --oneline -20` for recent commit narrative.  E1/E2/E3
   commits are labelled `refactor(compiler): Slice E{1,2,3} —
   <pass> as analyse/apply pass`.
5. Verify baseline:
   - `python -m pytest tests/ --ignore=tests/trealla
     --ignore=tests/test_trealla_backend.py -q`
     → expect **10534 passed, 90 skipped**.
   - `CLAUSAL_IR_PATH=1 python -m pytest tests/ …` → same pass
     count; D6 cross-checks run explicitly under the env var.

## Where we are

E1/E2/E3 complete.  Three D6 analyses live in
`clausal/logic/compiler/optimisations/` with uniform shape:

- `destructive_reuse.py` — `DRPlan` + `analyse(ir, head, db=None)`
  + `apply(ir, plan) -> ir`
- `tro.py` — `TROPlan(eligible, check_indices)` + `analyse(ir,
  head, functor, arity, db=None)` + `apply(ir, plan)`
- `call_site.py` — `CallSitePlan(hints, joint_hints)` +
  `analyse(ir, head, base_globals, db=None)` + `apply(ir, plan)`

Each `apply` writes hints onto :class:`SubCall`:
`destructive_reuse: bool`, `tail_recursive: bool`,
`direct_bucket_ref: str | None`.  Tests cover round-trip,
no-op, hashability, legacy-parity.

**Lowering does not yet read any of these hints.**  Legacy
bypasses still drive codegen.  E4+ fixes that.

## E4+ sub-slices (proposed order)

Work in order of increasing risk.

### E4a — bucket-ref hint reading

**Scope:** change `_dispatch_call_trampoline` to prefer
`subcall.direct_bucket_ref` (when set) over the
`ctx.bucket_ref_map` lookup, OR wire the IR path's SubCall
lowering to emit the direct bucket reference directly when the
hint is present.

**Why smallest:** the map approach already works transparently
via shared ctx; reading the hint is mostly a plumbing change.
D6c's byte-parity test guarantees the hint's gkey equals what
legacy writes to the map.

**Deliverable:** apply E3's `call_site.apply` during body
compilation (probably in `_compile_body_impl` or a new "apply
all optimisations" step right after `terms_to_goalop`), then
have lowering read the hint.  Legacy `_inject_bucket_refs_trampoline`
still runs for the map; both produce the same result.  Retirement
of the legacy pre-scan waits for E6.

### E4b — destructive_reuse hint reading

**Scope:** today `Strategy.preprocess_clause` rewrites
`Call(append)` → `Call(_dr_append__3)` **before** `terms_to_goalop`
sees the body.  Move to: build IR from the original body, run
E1's `apply` to set `SubCall.destructive_reuse=True`, have
lowering emit the dr-variant name when the hint is set.

**Tricky bit:** the `_dr_<name>__<arity>` names need to exist in
`base_globals`.  Today they get injected by the preprocess-time
rewrite via the builtin module; after E4b the rewrite moves to
lowering, so globals injection needs to happen unconditionally
(or based on hint presence).

**Deliverable:** lowering reads the hint.  Preprocess-time
rewrite still runs (legacy fallback).  Full suite + IR-cross-check
green.

### E4c — TRO hint reading

**Scope:** the hairy one.  Legacy has a dedicated body compiler
`_compile_tro_body` that bypasses `_compile_body_impl` entirely.
It's invoked from `predicate.py` for each TRO-eligible clause.
It emits the snapshot-args + set-_tro-flag tail.

IR-path equivalent: IR lowering for a `SubCall` with
`tail_recursive=True` emits the TRO tail directly (reusing the
`_compile_tro_tail` helper).  The per-predicate machinery
(`while True:` wrapper, `_tro_state` shared list) still lives
where it is today — only the per-clause body compile changes.

**Deliverable:** a TRO-eligible clause routes through
`_compile_body_impl` with E2's `apply` having set the hint, and
IR lowering emits the tail-call rewrite when it sees
`tail_recursive=True`.  `_compile_tro_body` still exists as
fallback; retirement in E6.

**Risk:** high.  TRO is the most common source of subtle
miscompilation during this refactor.  Recommend a dedicated
parallel-check (compile both ways, AST-diff) for TRO-eligible
clauses during the transition.

### E5 — per-optimisation toggle

Add `ctx.enabled_optimisations: frozenset[str]` with a default
of `frozenset({"tro", "destructive_reuse", "call_site"})`.  Each
pass gates on its name being in the set.  Test matrix: suite
green with each optimisation individually disabled.  Catches
hidden ordering dependencies between passes.

### E6 — retire legacy bypasses

Preconditions: E4a/b/c have baked.  E5 test matrix is green.

**Joint-bucket hint gap (from E4a).**  `call_site.analyse`
computes `joint_hints` but `apply` does not write them — there is
no joint-position field on :class:`SubCall` today.  Joint-
position specialisation therefore still rides
`ctx.joint_bucket_ref_map`, which is populated only by legacy
`_inject_bucket_refs_trampoline`.  **Before** deleting the
legacy pre-scan in E6, add a joint-hint conduit — either a new
``SubCall.direct_joint_bucket_ref: tuple[int, int, str] | None``
(pi, pj, gkey) field, or a richer type for
``direct_bucket_ref``, then have `apply` write joint entries and
`_dispatch_call_trampoline` read them.  Until that lands, E6 must
keep the joint-map lookup in `_dispatch_call_trampoline` alive.

**Compile-time perf note (from E4a).**  E4a runs
`call_site.analyse` on every body compile inside
`_run_ir_parallel` (walks every :class:`SubCall`, re-computes
`term_to_ast_expr(a, {})` / `_static_call_key` per arg).  Legacy
`_inject_bucket_refs_trampoline` runs once per predicate.  This
is a small per-clause regression while both paths co-exist; E6
amortises back to once-per-predicate when the legacy pre-scan is
deleted and the E3 analyse lifts to predicate scope.

Delete:
- `_compile_tro_body` + `_compile_tro_tail` (TRO's bypass path)
- `Strategy.preprocess_clause` DR rewrite
- `_inject_bucket_refs_trampoline` (legacy bucket-ref map
  population — hints are the source of truth now)
- `_find_destructive_reuse_goals` + `_detect_tro_clause` +
  `_get_tro_check_indices` legacy term-walking analyses

After E6, D7c (legacy dispatcher delete) is mechanical.

## Constraints

- **Function-local `from . import ir as _ir` inside analysis and
  lowering modules.**  `tests/test_runtime_compiler_boundary`
  scrubs `sys.modules['clausal.logic.compiler.*']` mid-session;
  module-level imports go stale.  Test files: same idiom —
  imports inside each test function.  See the D6a / D6b / D6c /
  pre-E commit messages for the full hazard write-up.
- **Don't sweep untracked files into commits.**
  `implementation_plans/LLVM_BACKEND.md` is another project's
  scratch — leave it alone, don't `git add -A`.

## Deliverables

Per sub-slice commit, trailer:

    Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

Git identity:

    git -c user.email=mikeamycoder@gmail.com -c user.name='Mike Amy' commit ...

Update `implementation_plans/COMPILER_MIGRATION_PLAN.md` §7
status table per sub-slice.

**Delete this `todo/` file when E6 retires the legacy bypasses.**
