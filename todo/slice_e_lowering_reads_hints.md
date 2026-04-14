# Slice E4+ — lowering reads optimisation hints

> **Self-instruction for the next compiler-refactor session.**
> **When E6d retires the last legacy bypass, delete this file.**

## Before doing anything

1. `cd /workspace/clausal-compiler_refactor`
2. Read `implementation_plans/COMPILER_MIGRATION_PLAN.md` §6 and §7
   — authoritative slice definitions and status tables for D and E.
3. `git log --oneline -30` for recent commit narrative.  E1–E6b
   commits are labelled `refactor(compiler): Slice E{n} — <desc>`.
4. Verify baseline:
   - `python -m pytest tests/ --ignore=tests/trealla
     --ignore=tests/test_trealla_backend.py -q`
     → expect **10544 passed, 90 skipped**.
   - `CLAUSAL_IR_PATH=1 python -m pytest tests/ …` → same count.
   - `CLAUSAL_DISABLE_OPT=tro python -m pytest tests/ …`
     → **10535 passed, 99 skipped** (9 extra skips for the TRO-
     observability test classes tagged `@skipIf(_tro_disabled())`).
   - `CLAUSAL_DISABLE_OPT=destructive_reuse python -m pytest tests/ …`
     → 10544 passed, 90 skipped.
   - `CLAUSAL_DISABLE_OPT=call_site python -m pytest tests/ …`
     → 10544 passed, 90 skipped.

## Where we are (as of 2026-04-14)

E1/E2/E3 analyse/apply passes landed.  E4a/b/c wired the three
hints into IR lowering.  E5a/b added the per-optimisation toggle
end-to-end.  E6a closed the joint-bucket-hint gap.  E6b retired
`_inject_bucket_refs_trampoline` from the production compile path.

### IR hints on :class:`SubCall`

```
direct_bucket_ref:        str | None          # single-pos call-site
direct_joint_bucket_ref:  str | None          # joint-pos call-site (E6a)
tail_recursive:           bool                # TRO tail (E2/E4c)
tro_check_indices:        frozenset[int]      # TRO ground-check positions (E4c)
destructive_reuse:        bool                # DR variant rename (E1/E4b)
```

### Optimisation passes

All in `clausal/logic/compiler/optimisations/`, uniform
`analyse(ir, …) -> Plan` + `apply(ir, plan) -> ir` contract.
`call_site.py` also exposes `populate_runtime_from_plan(ir, plan,
ctx, base_globals)` (E6b) that writes `ctx.bucket_ref_map` /
`joint_bucket_ref_map` + injects bucket functions into
`base_globals`.

### Toggle plumbing (E5)

`CompilationContext.enabled_optimisations: frozenset[str]` —
default `frozenset({"tro", "destructive_reuse", "call_site"})`,
env-var-overridable via `CLAUSAL_DISABLE_OPT=<comma-list>`.
Gated at:
- `_run_ir_parallel` (IR-side DR, call_site analyses).
- `tro._compile_tro_body` (IR shadow).
- `_make_body_compiler_impl` (DR preprocess).
- `predicate.py` (`_detect_tro_clause` sweeps).
- `_compile_body_impl._prepopulate_call_site_runtime` (gated on
  `call_site`; no-op populator when disabled).

### Byte-parity harness (D4/D7b, E4c mirror)

`_run_ir_parallel` inside `_compile_body_impl` builds IR,
applies E1/E3 hints, lowers, and `ast.dump`-diffs against the
legacy fold.  `_compile_tro_body` carries a mirror harness
(`_maybe_cross_check_ir_tro` in `tro.py`) with E2 hints + the
SubCall arm's `_compile_tro_tail` path.

## E6 sub-slices

Status table lives in
`implementation_plans/COMPILER_MIGRATION_PLAN.md` §6/§7.  At this
point: E6a/b ✅, E6c/d ⏳.

### E6c — retire `_compile_tro_body` / `_compile_tro_tail` bypass

**Scope:** stop calling `_compile_tro_body` from
`_build_predicate_trampoline_funcdef` in `predicate.py`.  TRO
clauses route through the unified `_compile_body_impl` path;
both legacy and IR folds inside it emit the TRO tail via the
SubCall arm's `tail_recursive` read in
`_lower_goalop_shared.py`.

**The entanglement** (same class as E6b): legacy fold in
`_compile_body_impl` doesn't know a clause is TRO — it walks
terms and has no access to `tro.analyse` output.  If we simply
re-route TRO clauses through it, legacy emits a normal call
while IR emits the TRO tail → `ast.dump` diff blows up.

**Path forward.** The E6b playbook applies: pre-pass in
`_compile_body_impl` runs IR build + `tro.analyse` early,
populates something the legacy fold reads so it also emits the
TRO tail.  But TRO isn't a map lookup — it's a clause-wide
control-flow rewrite (the tail goal is replaced by
`_compile_tro_tail`, prefix goals fold normally).

Simplest: add a body-compiler parameter (or ctx field) that
carries the TRO plan for the current clause.  The legacy fold's
tail-goal handler then branches on the plan just like
`_compile_tro_body` does today.  Specifically:

1. `_make_body_compiler_impl` inspects the clause, runs
   `tro.analyse`, stashes the plan on a per-clause ctx field
   (e.g. `ctx.tro_plan: TROPlan | None`) + sets `ctx.tro_mode`
   (`"loop"` / `"signal"` from predicate.py).
2. `_compile_body_impl`: when `ctx.tro_plan.eligible`, split
   goals into `prefix + [tail]`, fold prefix normally, use the
   legacy `_compile_tro_tail` output as the leaf (not
   `strategy.emit_leaf_yield`).  This IS what
   `_compile_tro_body` already does, moved inline.
3. IR path: IR lowering already reads `SubCall.tail_recursive`
   and emits `_compile_tro_tail` for the tail.  Just runs
   `tro.analyse` + `apply` inside `_run_ir_parallel` (new gate).
4. Delete `_compile_tro_body` from `tro.py`.
5. `predicate.py`: delete the `_tro_list_body_compiler` branch
   and the `if use_tro and ci in tro_indices:` branch — body
   compiler handles TRO uniformly now.

**Risk:** high.  TRO clauses currently bypass `_compile_body_impl`
entirely, so no harness has run against the unified path.  The
test matrix from E5b (TRO countdown under each disable) is the
first line of defence; `tests/test_tail_recursion.py` carries
deeper cases.

**Deliverable:** `_compile_tro_body` deleted; `_compile_tro_tail`
kept (called from the SubCall arm's `tail_recursive` branch);
legacy fold inside `_compile_body_impl` TRO-aware.  Full suite
+ IR-path + per-flag sweep green.  Retirement of
`_detect_tro_clause` / `_get_tro_check_indices` waits for E6d.

### E6d — retire DR preprocess + legacy term-walking analyses

Preconditions: E6c baked.

Delete (all in `clausal/logic/compiler/`):
- `Strategy.preprocess_clause` DR rewrite (and
  `TrampolineStrategy.preprocess_clause` → falls back to
  `ShallowStrategy.preprocess_clause` which is a no-op).
  `_make_body_compiler_impl` already conditions on the flag; after
  E6d it no longer needs the `else` branch — DR rewrite lives
  entirely in IR lowering via the `destructive_reuse` hint.
- `destructive_reuse._find_destructive_reuse_goals` +
  `_apply_destructive_reuse` — only callers are the
  `preprocess_clause` rewrite path.
- `tro._detect_tro_clause` + `_get_tro_check_indices` — after E6c,
  only callers are the `tro.analyse_ir` equivalence test.
  `analyse_ir` replaces both.

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
- **Byte-parity harness is the test.**  Any E6c restructure that
  diverges legacy-fold and IR-fold AST on TRO-eligible clauses is
  wrong.  When in doubt: inspect the `ast.dump` diff in the
  AssertionError message — it tells you exactly where the two
  paths split.

## Deliverables

Per sub-slice commit, trailer:

    Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

Git identity:

    git -c user.email=mikeamycoder@gmail.com -c user.name='Mike Amy' commit ...

Update `implementation_plans/COMPILER_MIGRATION_PLAN.md` §7
status table per sub-slice.

**Delete this `todo/` file when E6d retires the last legacy
bypass.**
