# Slice C — Explicit `Strategy` protocol

> **Self-instruction for the next compiler-refactor session.**
> **When this slice lands, delete this file.**

## Before doing anything

1. `cd /workspace/clausal-compiler_refactor`
2. Read `implementation_plans/COMPILER_MIGRATION_PLAN.md` §5 (lines 307–376) — authoritative slice definition.
3. Skim `implementation_plans/COMPILER_TARGET_ARCHITECTURE.md` §9 for the target Strategy shape.
4. Skim `implementation_plans/SLICE_B_PROGRESS.md` — ctx is everywhere; `_monolith` retired; FreshNames deterministic; C extensions under `runtime/`.
5. `git log --oneline -15` for commit narrative.
6. Verify baseline: `python -m pytest tests/ --ignore=tests/trealla --ignore=tests/test_trealla_backend.py -q` → expect 10409 passed, 90 skipped.

## Goal

Replace scattered strategy-specific branching with a `Strategy` protocol carried on `CompilationContext`. Shallow and trampoline become interchangeable strategy objects; `compile_predicate_shallow` / `compile_predicate_trampoline` become one-line wrappers over a unified `compile_predicate(..., *, strategy)`.

## Concrete work

### 1. `clausal/logic/compiler/strategy.py` (new)

`Strategy` Protocol plus two implementations (`ShallowStrategy`, `TrampolineStrategy`), ~30 lines each.

Methods per plan §5:

- `emit_leaf_yield(ctx) -> ast.stmt` — `yield None` vs `yield (parent, None)`
- `emit_exhaustion_yield(ctx) -> ast.stmt | None` — `None` vs `yield (parent, _DONE)`
- `emit_sub_call(ctx, fname, arity, arg_exprs, k_stmts) -> list[ast.stmt]` — for-loop vs StepGenerator loop
- `preprocess_clause(clause) -> list[Any]` — identity vs destructive-reuse rewrite
- `function_params(ctx, arg_names) -> list[str]` — adds `this_generator` / `_tramp_parent` for trampoline
- `supports_tro: bool`
- `supports_destructive_reuse: bool`

### 2. `CompilationContext` gains `strategy: Strategy | None = None`

Default `None`; external callers supply it via the `compile_predicate_*` entry points. Helpers that need the strategy read `ctx.strategy` and fail loudly if absent.

### 3. Migrate shared-helper call sites

In `_compile_body_impl`, `_compile_predicate_call_impl`, `_make_body_compiler_impl`, etc.:

Drop explicit `body_compile_fn` / `preprocess_clause` / `emit_dispatch` / `leaf_yield` kwargs. Read from `ctx.strategy.<method>()` instead.

### 4. Migrate branching sites across submodules

Files to sweep: `goal_shallow.py`, `goal_trampoline.py`, `ite_reified.py`, `control_constructs.py`, `tro.py`.

Anywhere a helper currently exists in both shallow and trampoline variants, collapse into a single ctx-native helper that reads the strategy. Favour *one implementation* over twin files.

### 5. Public entry points

- `compile_predicate(functor, arity, clauses, *, strategy, ...)` — new unified entry point.
- `compile_predicate_shallow(...)` and `compile_predicate_trampoline(...)` become thin wrappers (`strategy=ShallowStrategy()` / `TrampolineStrategy()`).
- Legacy name preservation: external callers in `solve.py`, tests, `compiler_v2.py` unchanged.

### 6. Validation before commit

- Full test suite green (10409 passed, 90 skipped ex-trealla).
- **AST diff test (byte-identical):**
  ```
  git stash  # optional: compare pre/post-slice
  python show_generated.py > /tmp/pre
  git stash pop
  python show_generated.py > /tmp/post
  diff /tmp/pre /tmp/post      # must be empty
  ```
- **Strategy-exchange test:** on a small corpus (e.g. `append/3`, `reach/2`, a CLP(FD) example, a catch-heavy predicate), compile each with both strategies and assert the solution enumeration is identical.

## Cycle-break idiom

When module cycles arise (e.g. `strategy.py` wants to import from both `goal_shallow` and `goal_trampoline`, and they import strategy back): use **function-local imports** inside the consuming function. Don't invent a shim module. Don't relocate helpers unless independently justified. This is the ratified pattern from B4/B6.

## Risk and reversibility

**Medium risk.** Most dedup work already anticipates this structure; the migration is kwarg-to-method-call. **Reversible** — revert by putting back the kwargs.

## Deliverables

Single commit (or two if diff >~600 lines):

- Title: `refactor(compiler): Slice C — explicit Strategy protocol`
- Trailer: `Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>`
- Git flag: `git -c user.email=mikeamycoder@gmail.com -c user.name='Mike Amy' commit ...`

Update `implementation_plans/COMPILER_MIGRATION_PLAN.md` §5 status to `✅ done`, or create `implementation_plans/SLICE_C_PROGRESS.md` mirroring `SLICE_B_PROGRESS.md` if the slice splits into sub-slices.

**Delete this `todo/` file** (`todo/slice_c_strategy_protocol.md`) as part of the final commit.

## Parallel work caution

Another agent is converting `.clausal` fixture tests to Clausal format and deduping. It should not touch Python infrastructure unit tests (`test_callsite_specialization.py`, `test_runtime_compiler_boundary.py`, `test_lambdas.py`), but `git status` before committing to be sure.

## Stop-the-line

If the diff blows up beyond ~800 lines or three+ cycles need unusual handling, **stop and report** rather than commit a half-migration. Slices must land whole.

## Success criteria (from plan §5)

- `compiler/strategy.py` exists with protocol + two impls.
- Every strategy-specific decision in `goal_shallow.py` / `goal_trampoline.py` / `ite_reified.py` / `control_constructs.py` / `tro.py` routes through `ctx.strategy.<method>()`.
- `_m.compile_goal` / `_m.compile_goal_trampoline` lazy accesses stay gone (finished in B; this slice confirms).
