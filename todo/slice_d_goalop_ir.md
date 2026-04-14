# Slice D — `GoalOp` IR and parallel implementation

> **Self-instruction for the next compiler-refactor session.**
> **When D7 (retirement) lands, delete this file.**
> **D1 is already done on main (see `clausal/logic/compiler/ir.py`).**

## Before doing anything

1. `cd /workspace/clausal-compiler_refactor`
2. Read `implementation_plans/COMPILER_MIGRATION_PLAN.md` §6 (lines
   377–502) — authoritative slice definition.
3. Read `implementation_plans/COMPILER_TARGET_ARCHITECTURE.md` §4
   ("`GoalOp` — the body IR", lines 351–609) — the IR design
   commitments.  D1 already embodies these; D2+ extends.
4. Read `clausal/logic/compiler/ir.py` — the GoalOp tagged union
   landed in D1.  Subclasses are `@dataclass`; traversal is
   `walk_goal_ops(ir, visit)`.
5. Skim `implementation_plans/SLICE_B_PROGRESS.md` and the Slice C
   commits (`git log --oneline --grep "Slice C"`) for the cycle-break
   idiom (function-local imports) and the ratified strategy model.
6. `git log --oneline -15` for commit narrative.
7. Verify baseline: `python -m pytest tests/
   --ignore=tests/trealla --ignore=tests/test_trealla_backend.py -q`
   → expect **10409 passed, 90 skipped** ex-trealla.

## Slice D is the biggest slice

Estimated 4–8 weeks.  Land each sub-slice as its own commit — some
sub-slices may split further.  Parallel implementation (legacy path
stays live via a feature flag) is the safety net; no retirement until
D6 ships green.

## Sub-slices

### D1. Define `GoalOp` tagged union — ✅ done (commit TBD)

`clausal/logic/compiler/ir.py` exists with:

- Base `GoalOp`.
- Binding/constraint ops: `Unify`, `Dif`, `StructuralEq`, `ArithEval`,
  `FDCompare`.
- Control-flow ops: `Sequence`, `Alternate`, `Negate`, `Branch` (with
  `reified_test: ReifiedKind | None` hint).
- Membership: `MemberIn` (with `negate` for `NotIn`).
- Call ops: `SubCall` (with `direct_bucket_ref` / `tail_recursive` /
  `destructive_reuse` optimisation hints), `MetaCall` (closed-set
  `kind` + open-dict `args`).
- Low-level: `ListPatternUnify`.
- Traversal: `walk_goal_ops(ir, visit)` — pre-order, descends through
  `Sequence`, `Alternate`, `Branch`, `Negate`, `MetaCall.args` entries.

Nothing consumes these types yet.

### D2. Prototype `terms_to_goalop` for a small subset

New module `clausal/logic/compiler/terms_to_goalop.py`.

Single entry point: `terms_to_goalop(body: list[Any]) -> GoalOp`.
Wraps the body goals in a `Sequence` and recursively converts each.

Subset to handle in D2:

- `Unify`, `DoesNotUnify` → `Unify`, `Dif`
- `Evaluate` → `ArithEval`
- `Lt`, `LtE`, `Gt`, `GtE`, `ArithEq`, `ArithNeq` → `FDCompare`
- `StructuralEq`, `StructuralNeq` → `StructuralEq(negate=...)`
- `in_`, `NotIn` → `MemberIn`
- list-body conjunction + `TupleLiteral` (goal position) →
  flattened `Sequence`

Leave `And`, `Or`, `Not`, `IfExpr`, `Call`, meta-calls for D5 —
raise `NotImplementedError` with a `NOT_YET(goal)` helper so the
parallel harness can cleanly fall back to the legacy path.

### D3. Prototype lowering for the D2 subset

Two new modules:

- `clausal/logic/compiler/lower_python_shallow.py`
- `clausal/logic/compiler/lower_python_trampoline.py`

Each exports `lower(ir: GoalOp, ctx: CompilationContext,
k_stmts: list[ast.stmt]) -> list[ast.stmt]`.

Output must be **byte-for-byte identical** to what
`compile_goal` / `compile_goal_trampoline` produce today for the same
input.  The D4 harness enforces this via AST diff.

Strategy already carries `emit_leaf_yield`, `emit_sub_call`,
`function_params`, `emit_exhaustion_yield` — reuse these from the
lowering so the IR-path stays aligned with the legacy path's emission.

### D4. Parallel-implementation harness

Feature flag (prefer `CompilationContext.use_ir_path: bool`; fall back
to an env var `CLAUSAL_IR_PATH=1` for CI).

When the flag is on:

1. Try `ir = terms_to_goalop(clause.body)` — if it raises
   `NotImplementedError`, log and fall back to legacy.
2. Otherwise `new_stmts = lower_python_<strategy>(ir, ctx, k_stmts)`.
3. Assert `ast.dump(new_stmts) == ast.dump(legacy_stmts)`.
4. Return `new_stmts`.

Land a test corpus under `tests/test_ir_path_corpus.py` — pick ~50
clauses from existing `.clausal` modules spanning the D2 subset.
Each predicate compiled with both paths; AST diff asserted.

When the subset is incomplete, the `NotImplementedError` fallback
keeps the full test suite green.

### D5. Expand `terms_to_goalop` coverage

One construct per sub-sub-slice (D5a … D5n), each landing as a small
commit with its own corpus test:

- D5a: `And` → `Sequence` normalisation (flatten right-leaning trees)
- D5b: `Or` → `Alternate`
- D5c: `Not` → `Negate` (including `_is_tabled_naf` detection on the
  inner — map tabled NAF to a `MetaCall(kind="naf_tabled")` or keep
  as `Negate` with a flag; decide during D5c)
- D5d: `IfExpr` → `Branch`, with `reified_test` populated when
  `_is_reifiable(test)` matches
- D5e: `Call(LoadName)` / `Call(LoadAttr)` → `SubCall` (no hints yet —
  hints land in D6).  **Note:** the D4 harness reuses the parent ctx's
  `bucket_ref_map` / `joint_bucket_ref_map` between the legacy and IR
  runs.  D2-subset ops never touch those dicts, but `SubCall` lowering
  will — either deep-clone them for the IR run, or verify that bucket-
  ref mutation is order-independent before this sub-slice lands.
- D5f: meta-predicate calls (`once`, `call_nth`, `count_all`,
  `setup_call_cleanup`, `call_cleanup`, `freeze`, `when`, `findall`,
  `bagof`, `setof`, `throw`, `catch`, `catch_error`, `catch_recover`,
  `forall`, `halt`) → `MetaCall(kind=..., args=...)`
- D5g: list patterns (`SegList` heads, star-list body `Unify`) →
  `ListPatternUnify`

Each addition flips a `NotImplementedError` to a real conversion; AST
diff stays green throughout.  Coverage progresses toward 100%.

### D5 follow-ups (carry into D6 / D7)

- `SubCall` lowering currently delegates to legacy
  `_compile_predicate_call_impl` (lambda hoist + term→ast + strategy
  `emit_sub_call`).  Pragmatic for D5e — means SubCall isn't truly
  decoupled from legacy yet.  D7 retirement must migrate the body of
  `_compile_predicate_call_impl` into `_lower_goalop_shared` (or a
  sibling), same move as the reified-ITE helper.
- `SubCall.args` carries raw `Lambda` nodes; hoisting happens inside
  the lowering.  Consistent with the loose `Term` alias but worth
  revisiting in D6 — lambdas arguably belong as explicit IR children
  rather than hidden inside a term-list.
- `_META_NAMES` in `terms_to_goalop` duplicates the closed set in
  `ir.MetaKind` minus `forall`'s rewrite.  When D5f lands, unify the
  two (or delete `_META_NAMES` in favour of direct dispatch to the
  `MetaCall` conversion arm).
- D5e was called out as the biggest D5 sub-slice.  The diff is only
  ~150 lines because the shared-legacy-impl trick skipped real
  lowering work.  D6 (hints: `direct_bucket_ref`, `tail_recursive`,
  `destructive_reuse`) and D7 (retirement) will pay that back.
- **D5f MetaCall.args carries raw terms**, not `GoalOp` children.
  `walk_goal_ops` cannot descend into meta-call inners today.  Probably
  fine for D6 analysis passes (none currently look inside meta-calls)
  but verify when they migrate, and tighten the schema post-D7.
- **D5f forall rewrites at lowering time** (`Not(And(cond, Not(action)))`
  + shallow re-dispatch) to match legacy byte-for-byte.  Post-D7,
  consider rewriting at `terms_to_goalop` time instead so the IR is
  uniform.
- **D5g ListPatternUnify is shape-opaque for multi-star** — the
  single-vs-multi distinction is re-derived at lowering time by
  `_compile_star_is`.  D6 analysis passes cannot reason about
  list-pattern arity without re-parsing.  Fine today; revisit if an
  analysis pass needs it.
- ~~**D5g defers `False` as goal conjunct**~~: resolved by D5j —
  `Fail` IR op landed; lowering returns `[]` which truncates the
  Sequence fold byte-identically to legacy.
- **D5 `_META_NAMES` safety-net frozenset** in `terms_to_goalop`
  duplicates the explicit meta arms.  Delete alongside legacy in D7.
- **D5h tabled-ITE kwargs asymmetry**: legacy
  `_compile_general_ite_{shallow,trampoline}` emits `_naf_tabled(...)`
  with `test.args` only, dropping `test.kwargs` from the arg tuple
  while still counting them in arity (looks like a latent legacy bug).
  The D5h IR path pulls `args` off the `SubCall`, which
  `terms_to_goalop` has already normalised via `db.signature_for` to
  include kwargs in positional order.  No test in the suite exercises
  a tabled predicate call with kwargs inside an `IfExpr` test, so the
  AST-diff gate stays green today.  If it ever fires: either match the
  buggy legacy shape in IR lowering, or fix legacy too.  The `Not`
  path is consistent — `_compile_tabled_naf_simple` normalises kwargs
  itself.
- ~~**D5h corpus coverage gap**~~: resolved by D5i — corpus now loads
  `tests/fixtures/wfs_win.clausal` (Not + tabled call → MetaCall) and
  `tests/fixtures/tabled_ite.clausal` (IfExpr test on tabled call →
  Branch with `tabled_naf=True`) under `CLAUSAL_IR_PATH=1`.

### D5h. Tabled-NAF — ✅ done

- `Not(Call(tabled_pred))` → `MetaCall(kind="naf_tabled", args={"call": Call})`
  (Option A).  Shared lowering in `_lower_meta_call` forwards to
  `_compile_tabled_naf_simple`.
- `IfExpr(test=Call(tabled_pred), ...)` → `Branch(test=SubCall(...),
  then=..., else_=..., reified_test=None, tabled_naf=True)`.
  Strategy-specific Branch arms in `lower_python_{shallow,trampoline}`
  reconstruct the `_naf_tabled(fname, arity, [args...], trail,
  _table_store)` call from the `SubCall` fields when `tabled_naf` is
  true.  Byte-identical to legacy `_compile_general_ite_{shallow,
  trampoline}` under `use_tabled_naf`.

Validated: `CLAUSAL_IR_PATH=1` full suite passes (10470 + 90 skipped),
including `test_wfs`, `test_tabling`, `test_slg_termination`, and the
tabled-ITE tests in `test_reified_ite`.  The D4 AST-diff harness now
catches tabled-NAF drift in addition to the D2–D5g subset.

### D5i. Tabled-NAF corpus gating — ✅ done

`tests/test_ir_path_corpus.py` now parametrises over `(subdir, filename)`
tuples and includes `fixtures/wfs_win.clausal` (Not + tabled call →
`MetaCall(naf_tabled)`) and `fixtures/tabled_ite.clausal`
(`IfExpr(test=Call(tabled))` → `Branch(tabled_naf=True)`).  Default CI
now gates tabled-NAF AST drift without the global `CLAUSAL_IR_PATH=1`
env-var dance.

Validated: `pytest tests/test_ir_path_corpus.py` → 12 passed; full
ex-trealla suite → 10472 passed, 90 skipped.

### D5j. Long-tail body shapes (PyThunk + False + nested TupleLiteral) — ✅ done

Three small, complementary additions that drove the corpus IR-fallback
count from 53 → 0:

- New `Fail` IR op — `False` as a body goal (whether at conjunction
  top or inside an `Or`/`Not`/`IfExpr` arm) lowers to `[]`, truncating
  the surrounding `Sequence` right-to-left fold byte-identically to
  legacy `_dispatch_goal(False, k) == []`.
- New `PyThunkOp` IR op — `PyThunk` as a body goal lowers via
  `term_to_ast_expr` to a single `ast.Expr(call)` + continuation, the
  same fast-path both legacy `_dispatch_goal`s already share.
- `_convert` now flattens nested `TupleLiteral` into an inner
  `Sequence` (mirrors the top-level `_extend` arm).  Also handles
  `True` as an op (empty `Sequence`) for symmetry with `False`.

Validated: full ex-trealla suite green (10472 passed, 90 skipped) both
under default and `CLAUSAL_IR_PATH=1`; fixture-corpus IR-fallback
count is now 0/3723 runs.

### D6. Move optimisation passes to operate on `GoalOp`

D6 lands in three sub-slices (one per analysis pass), all under the
**option-1 verification gate**: each new IR-side analysis runs as a
parallel shadow alongside its legacy term-walking counterpart and
asserts agreement.  No behaviour change yet; the hints stay unread by
lowering until D7 promotes the IR path.  This is the same strategy
that worked through D5 — keep the legacy path the source of truth,
let the IR analyses bake under CI before flipping over.

### D6a. TRO `analyse_ir` parallel shadow — ✅ done

`tro.analyse_ir(ir, head, functor, arity)` mirrors
`_detect_tro_clause` + `_get_tro_check_indices` over a `GoalOp`
:class:`Sequence`:

- `_is_deterministic_op_ir` — IR equivalent of legacy
  `_is_deterministic_goal`; pattern-matches on `Unify` / `Dif` /
  `ArithEval` / `FDCompare` / `StructuralEq` / `MemberIn` / `Negate`
  / `Branch` / `Sequence` / `Alternate` / `MetaCall(once|findall|…)`
  / `SubCall(<DETERMINISTIC_BUILTINS>)` / `Fail` / `PyThunkOp` /
  `ListPatternUnify`.
- `_collect_bound_vars_ir` — mirror of the per-goal scan inside
  `_tro_args_safe`; descends through `Sequence` (legacy `And`),
  reads `Unify` / `ArithEval` / `ListPatternUnify` arms.  The
  star-list arm matters: legacy `Unify(left=acc2, right=[h, *acc])`
  becomes `ListPatternUnify(star_side=[h, *acc], other_side=acc2)`,
  so `other_side` carries the binding.
- `_tro_args_safe_ir` — reuses legacy's head/arg term scans
  unchanged (`SubCall.args` carries the same terms after kwarg
  normalisation).

Wired into `_detect_tro_clause` as a stop-the-line cross-check gated
by `CLAUSAL_IR_PATH=1` (`_maybe_cross_check_ir`).  The full suite under
that env var verifies thousands of real predicate compilations, well
beyond the nine targeted cases in `tests/test_tro_ir_parallel.py`.

The IR-module imports inside the analysis helpers are
**function-local** — `tests/test_runtime_compiler_boundary` scrubs
`sys.modules['clausal.logic.compiler.*']` mid-session to verify
import-discipline, and a module-level `from . import ir as _ir` would
leave us holding stale class refs while `terms_to_goalop` (lazily
imported inside `_maybe_cross_check_ir`) produces instances of the
new IR module's classes.  Same hazard, same fix, in the new test
file's per-test imports.

Validated:
- `pytest tests/test_tro_ir_parallel.py` → 9 passed
- `CLAUSAL_IR_PATH=1 pytest tests/test_tail_recursion.py` → 41 passed
- Full ex-trealla suite (default) → 10481 passed, 90 skipped
- Full ex-trealla suite under `CLAUSAL_IR_PATH=1` → 10481 passed, 90 skipped

### D6b. destructive_reuse `analyse_ir` parallel shadow — ✅ done

`destructive_reuse.analyse_ir(ir, head)` mirrors
`_find_destructive_reuse_goals` over a `GoalOp` :class:`Sequence`:

- `_collect_op_var_ids` walks every term field on an op and recurses
  into child :class:`GoalOp`s — IR equivalent of the legacy
  `_collect_var_ids(subsequent_goal, live_after)` that descends through
  a goal AST node's dataclass fields.  Covers all D5j ops (`Fail`,
  `PyThunkOp`) and the meta-call args dict (which may carry mixed
  GoalOp / term children).
- `_head_aliased_var_ids_ir` + `_collect_unify_pairs_ir` mirror the
  legacy alias closure — only top-level `Unify` ops contribute (legacy
  matches `Unify` / `And` only; `Or` / `Not` / `IfExpr` arms are not
  descended).  Sequence is descended for parity with legacy `And`
  recursion.
- Determinism reuses :func:`tro._is_deterministic_op_ir` (D6a).

Wired into `_find_destructive_reuse_goals` as a stop-the-line
cross-check gated by `CLAUSAL_IR_PATH=1`
(`destructive_reuse._maybe_cross_check_ir`).  Index sets aren't
directly comparable — legacy indexes the post-flatten body, IR
indexes `Sequence.ops` — so both are projected to the canonical
`(fname, arity, occurrence#)` form before comparison.

Validated:
- `pytest tests/test_dr_ir_parallel.py` → 11 passed
- `CLAUSAL_IR_PATH=1 pytest tests/test_destructive_reuse.py` → 33 passed
- Full ex-trealla suite (default) → 10492 passed, 90 skipped
- Full ex-trealla suite under `CLAUSAL_IR_PATH=1` → 10492 passed, 90 skipped

### D6c. Call-site bucket-ref `analyse_ir` parallel shadow — ⏳ pending

- `_detect_tro_clause` → `tro.analyse(ir) -> TROPlan` (writes
  `SubCall.tail_recursive = True` on the tail call).
- `_find_destructive_reuse_goals` → `destructive_reuse.analyse(ir)`
  (writes `SubCall.destructive_reuse = True` on eligible calls).
- Call-site bucket-ref specialisation writes
  `SubCall.direct_bucket_ref = gkey`.

The lowering reads the hints; analysis no longer walks term trees.

Introduce `map_goal_ops(ir, visit) -> GoalOp` (rewrite-capable
traversal) when the first analysis needs it.

### D7. Retire the legacy path

Preconditions:

- Test corpus 100% IR-coverage.
- Full test suite green with `ctx.use_ir_path = True` default for a
  full release cycle.
- No reported regressions.

Actions:

- Flip `use_ir_path` default to `True` in `CompilationContext`.
- After one more release cycle: delete `goal_shallow._dispatch_goal`,
  `goal_trampoline._dispatch_goal_trampoline`, and all their
  pattern-match helpers.  Entry points (`compile_goal`,
  `compile_body`, etc.) keep their legacy signatures but now just
  call `terms_to_goalop` + `lower_python_<strategy>`.

## Cycle-break idiom

`ir.py` is a leaf today.  `terms_to_goalop.py` imports from
`clausal.terms` / `clausal.pythonic_ast.nodes` and from `ir`.  The
lowering modules import from `ir` and from strategy/compile_ctx.

If `terms_to_goalop` or a lowering module wants to call back into
`goal_shallow` / `goal_trampoline` (e.g. during D4's legacy fallback),
use **function-local imports** — the ratified B4/B6 idiom.  Don't
create shim modules.

## Validation

- Every sub-slice must keep the full test suite green (10409 passed,
  90 skipped ex-trealla).
- D4 onward: AST diff between legacy and IR paths asserted on every
  compile during the transition.
- Each D sub-slice with code changes lands under commit title
  `refactor(compiler): Slice D<letter> — <what>`.

## Risk and reversibility

**High risk** — the IR is new architecture; silent miscompilation is
possible.  Mitigation: parallel implementation, AST-diff CI gate,
release-cycle bake before retirement.

**Reversibility** — complete through D6 (feature flag flips off);
after D7 retirement, reverting the deletion commit restores the
legacy path.

## Stop-the-line

If D2's subset produces AST diffs against the legacy path, **stop and
report** rather than commit a green-looking harness that silently
masks a lowering bug.  Re-examine the byte-level diff until it is
empty.

If a D5 sub-slice introduces >~500 lines of lowering and still diffs,
**stop** — the IR shape probably needs a small adjustment before
extending further.

## Deliverables

Per sub-slice commit, trailer:

    Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

Git identity:

    git -c user.email=mikeamycoder@gmail.com -c user.name='Mike Amy' commit ...

Update `implementation_plans/COMPILER_MIGRATION_PLAN.md` §6 status
per-sub-slice; or create `implementation_plans/SLICE_D_PROGRESS.md`
mirroring `SLICE_B_PROGRESS.md` once D5 kicks off.

**Delete this `todo/` file** when D7 retires the legacy path.
