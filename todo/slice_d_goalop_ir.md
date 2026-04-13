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

### D6. Move optimisation passes to operate on `GoalOp`

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
