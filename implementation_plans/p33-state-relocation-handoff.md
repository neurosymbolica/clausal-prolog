# HAND-OFF: plan and execute P3-3 (state relocation + qualified goals)

**For the next Claude instance.** You are continuing the tagged-tuple program. Read this
file, then `implementation_plans/phase3-decomposition-and-p31-atom-pivot.md` (the P3-3
outline near the bottom — it now points back here), then
`implementation_plans/tagged-tuple-term-representation.md` §1/§1a/§1b (the §1b STATUS
block records exactly what P3-2 shipped) before doing anything. Your job: write the full
P3-3 implementation plan (same No-Placeholders discipline as the P3-1/P3-2 plans — either
is your template; `implementation_plans/p32-cell-default-flip.md` is the more recent one),
ratify the R4 detail (below) with the user, get sign-off on any new rulings, then execute
via subagent-driven development. CLONE ONLY (`/workspace/clausal-bug-fix`); never touch
`/workspace/clausal` until the final sync.

## Where the program stands (branch `feat/p32-cell-flip`, HEAD past `aac9895a`, 2026-09-05)

- Phases 0–2: done (fast path, funnel, `-tagged_terms` bridge — since deleted).
- toklex L0 + PrologReader L1/L2: done.
- **P3-1 atom pivot: MERGED to clone main** (309f9dad, 2026-09-04). Atoms are interned
  global strs; `-hide` shipped; strict-atoms per-module.
- **P3-2 cell default flip: COMPLETE on this branch**, pending final whole-branch review
  and merge (28 commits `ef10baa4..aac9895a` plus the close-out doc commits). Cells (plain
  tagged tuples) are now the unconditional compiled representation in every module — the
  `-tagged_terms` flag and all its plumbing are gone. Full detail: task briefs/reports in
  `.superpowers/sdd/p32-cell-default-flip/`; STATUS note + ruling summary in
  `implementation_plans/tagged-tuple-term-representation.md` §1b; memory:
  `tagged-tuple-term-design-parked`.
- Perf gate PASSED at P3-2 close: `bench_fib` flat, `bench_struct_tabling` 0.606
  head/base (39% win). Full-suite reconciliation EMPTY (twice) vs the pre-P3-2 baseline.

**Do this first, before planning:** confirm P3-2 has actually merged to clone main by the
time you start (`git log --oneline main | grep -i "P3-2"` or check for
`feat/p32-cell-flip` having been fast-forwarded/merged). If it hasn't yet, either wait or
branch P3-3 from the P3-2 branch tip and rebase later — do not silently plan against a
branch that might still change under review.

## User rulings in force (carried into P3-3)

- **R1–R9** (P3-1/P3-2): SEP=US 0x1F (R1-revised, user-ratified 2026-09-05 — supersedes the original U+E000); `atom(X)` true for every str; Phase 3 runs on the
  existing Python-syntax pipeline (reader-surface migration is a later, user-owned phase);
  own-module cross-module gate deleted; data-functor classes stop minting (instance-side
  cell emission removed ENTIRELY — every surviving `PredicateMeta` instance at runtime is
  Python-minted, never `.clausal`-sourced); ISO `name/arity` predicate exports;
  `-implicit_functors` net-new OWA directive, default OFF; str-side charlist coalesce
  retired; `-tagged_terms` deleted.
- **R4 (qualified-goal spelling) — RATIFY THE DETAIL AT P3-3 PLANNING, NOT BEFORE.** The
  outline commits to the SHAPE: qualified goals as `(":", module, Goal)` plus
  `solve(..., module=)`, calling-module as the default when unqualified. What is NOT yet
  ratified: how a qualified goal resolves `module` (a live module object? a name string
  looked up in `sys.modules`? something Database-keyed, given P3-3's own state-relocation
  work?), how it interacts with `call/N` once `call/N` accepts cells (see the cell-GOAL
  boundary below), and whether `_tabled_entry_for_goal`'s existing dotted-chain walk (cited
  in the outline as the model) is actually the right precedent once Database becomes
  authoritative. Bring a concrete proposal to the user, don't assume the outline's shape is
  the final word on mechanism.
- **User ruling 2026-09-05, standing:** "we can do C changes now if they make sense" —
  relaxes the historical P3-2 no-C-changes-expected default. P3-2 needed exactly one
  scoped C change under this ruling (Task 2C — see the recon below); it remains in force
  for P3-3. Don't assume no-C-changes; measure and ask if a C change would help.

## P3-3 scope (from the committed outline — this is the phase you plan)

`implementation_plans/phase3-decomposition-and-p31-atom-pivot.md`'s P3-3 section (recon:
`database.py`, `predicate.py`, `compiler/predicate.py`, `globals_env.py`, `solve.py`,
`specialization.py`, `tabling.py`): invert the sync direction — `Database` (already
per-module, `(functor, arity)`-keyed) becomes the authoritative home for
`_clauses`/`_dispatch_fn`/`_signature`/`_locked`/`_dynamic_arities`/`_clauses_source`/
tabling homes; `PredicateMeta` and adapters become read-through (preserving the frozen
zero-arg `_get_dispatch` duck type and the `$disp_<name>_<arity>` bake-in via an
equivalent direct-read); single mutation gate at the Database (closes
`todo/a-shared-predicate-has-no-single-mutation-gate.md` and
`todo/predicate-identity-is-keyed-on-spelling-not-on-the-class.md` — carry both into the
plan); `_term_to_goal`/`_infer_module`/`_goal_cache_key`/`_templatize_query_goal` learn
cell goals + the R4 qualified form, modeled on `_tabled_entry_for_goal`'s dotted-chain
walk (verify the precedent still fits before committing to it — see R4 above); `call/N`
accepts cells; specialization stops minting classes (`make_predicate`/`make_atom` callers
at `specialization.py:277,1313,1671` register Database rows instead); reflection/listing
surfaces (`reflection.py`, `inspection.py`, `compiler_v2.py`) migrate to
`(module, name, arity)` lookups.

**Stencil-seam planning input (ruled 2026-09-05, binding on this scope):** the
Database/dispatch redesign above must keep the dispatch seam **backend-pluggable**, with
**one invalidation point** and a **per-predicate backend-choice hook** — not just a
single-backend read-through. See "Stencil-seam requirement" below for why this is not
speculative.

## Recon crown jewels (from P3-2's execution — read before writing plan steps)

These interfaces exist ONLY because P3-2 built them; they did not exist when the P3-2
handoff was written, so they are not in any earlier document. Re-verify line numbers (P3-2
touched most of these files) but the shapes below are current as of `aac9895a`.

1. **The functor-signature registry** (`clausal/logic/cells.py`,
   `clausal/logic/compiler/terms_to_ast.py`). `FUNCTOR_SIGNATURES_KEY =
   "__clausal_functor_signatures__"` (`cells.py:139`) names a per-module dict, populated by
   `globals().setdefault(FUNCTOR_SIGNATURES_KEY, {}).update({...})` **emitted as an `ast.Expr`
   call, not a literal `Assign`** — this was a deliberate P3-1-era choice (multi-directive
   accumulation) that a naive grep for an `Assign` node will miss; don't rebuild this lookup,
   reuse `functor_signature_for(name, namespace)` (`terms_to_ast.py:296`, registry-first,
   `cls._fields` fallback for legacy producers) and `cell_signature_for_name`
   (`terms_to_ast.py:320`, the arity-aware wrapper `head_match`'s Call branch and the lift
   both gate on — NOT the stricter `cell_functor_for_name`, which refuses partial/keyword
   references the placer legitimately handles). `_place_signature_slots`
   (`terms_to_ast.py:474`) is the shared kwarg-placement/backfill routine both construction
   sites (and the bucket lift) funnel through. **P3-3 relevance:** if predicate state moves
   into `Database`, whatever replaces "does this name have a registered class" for DATA
   functors must keep reading this SAME registry — it is now the single source of truth for
   functor shape, decoupled from any class.
2. **The `$cells` injection point** (`clausal/logic/cells.py:184`,
   `CELLS_NAMESPACE_KEY = "$cells"`). The tuple-DATA tag (`TUPLE_TAG`) is reached at
   compile/match time via an injected `$cells` global — NOT `builtins.tuple` (the original
   spec's premise was wrong; there is no compiled-module preamble importing `builtins`, and a
   module-level binding named `builtins` would silently shadow one if there were). Injection
   sites: `clausal/logic/compiler/predicate.py:837-839` and `:1657-1659` (two duplicated pool
   entries — a known minor from P3-2 Task 3, not `INJECTED_RUNTIME_BUILTINS`; if you touch
   predicate-state bake-in, consider consolidating these onto one injection mechanism rather
   than leaving a third copy). Consumed at `head_match.py:908-910`
   (`CELLS_NAMESPACE_KEY in globals_` gates the tuple-DATA match arm; absent → wildcard,
   never a match-time `NameError`).
3. **The deep-gate 4-tuple threading** (`clausal/logic/compiler/arg_index.py`). First-arg
   dispatch plans are `(pos, idx_dict, default_fn, deep_gate)` 4-tuples
   (`arg_index.py:1171-1172`, P3-2 Task 4 fix round 2 added the trailing `deep_gate`);
   `_runtime_arg_key(a, deep_gate)` (`:275`) only runs its bounded groundness walk
   (`_is_deeply_ground`) when `deep_gate` is `True`, computed once at bucket-build time by
   `list_dispatch._lifted_head_arg_needs_deep_gate`
   (flags on only when a lifted clause pattern carries a literal sub-value below the indexed
   root). **P3-3 relevance:** any change to how dispatch closures are built (state
   relocation touches `compiler/predicate.py`'s bake-in, which is where these closures are
   constructed and stored) must preserve or re-thread this 4th element — dropping it
   silently reintroduces either a correctness gap (no gate) or a performance regression
   (always-on gate). `todo/first-arg-index-partially-ground-instance-keys-into-bucket-2026-09-05.md`
   documents a still-open half of this same mechanism (the `is_term_instance` key branch is
   NOT wired to the flag) — worth closing alongside whatever P3-3 does to dispatch closures,
   since you'll already be in that code.
4. **`_predicate_functor_names`** (`clausal/logic/compiler_v2.py:1140`). Computes, at
   compile time, the set of functor names that are predicates (have clauses) as opposed to
   data — this is the OTHER side of R6's data/predicate split (a name in this set never goes
   through the cell-construction path). If P3-3 changes how predicates are recognized
   (Database becomes authoritative), this function's answer must stay in sync with whatever
   Database now says has clauses — a divergence here silently flips a call between "goal" and
   "data cell" emission.
5. **`STRICTNESS_EXEMPT_RUNTIME_NAMES`** (`clausal/import_hook.py:333`, a `frozenset`
   currently `{Undefined}`). Task 8's ruling inverted the strict-atoms distrust default: a
   module-namespace binding identical to `runtime_builtins[name]` is now distrusted
   (flagged as a possible cross-module leak) UNLESS `name` is in this explicit, documented
   exemption set. **P3-3 relevance:** if state relocation adds or renames anything that gets
   seeded into every module's namespace (a new `INJECTED_RUNTIME_BUILTINS` entry, a Database
   singleton reference, anything in the shape of `$cells`/`$disp_*`), it will be distrusted
   by default under this ruling — that's a loud, one-line-fix test failure, not silent
   breakage, but expect it and add the exemption deliberately rather than treating it as a
   mystery regression.

## The cell-GOAL boundary (deliberately left for P3-3 — do not assume it "just works")

P3-2 flipped cells to the default representation for DATA. It did **not** make cells valid
as GOALS. Three explicit refusal points, all still live at `aac9895a`:

- `clausal/logic/database.py:541`, `head_key(head)` — raises `TypeError` for a bare tuple
  (cell) head; only handles `Compound`, `Call(LoadName)`, and legacy dataclass-instance
  shapes. **A cell can never be a clause head today.**
- `clausal/logic/builtins/database_ops.py`, `_reject_cell_head(term_val, context)` — called
  from `assertz/1`'s normalization path specifically to turn `head_key`'s internal
  `TypeError` (which named neither the mistake nor the remedy) into the correct ISO
  diagnostic (`permission_error(modify, static_procedure, f/1)`, restored verbatim from
  pre-flip behavior) when a program tries to `assertz` a cell-headed clause. The docstring
  says outright: "Asserting INTO a cell-headed predicate is P3-3's business, not this
  task's."
- `call/N` does not accept cells as a goal shape — qualified goals (`(":", module, Goal)`),
  `solve(module=)`, and cell-headed `assertz` are ALL explicitly out of P3-2's scope (see the
  P3-2 task brief's "Explicitly OUT of scope" section, carried forward here) and are P3-3's
  to design. Do not assume any of the three "just work" because cells are now default —
  they are refused on purpose, with a real diagnostic, not silently broken.

## Parked todos that fold into P3-3 naturally

- `todo/a-shared-predicate-has-no-single-mutation-gate.md`,
  `todo/predicate-identity-is-keyed-on-spelling-not-on-the-class.md` — named explicitly by
  the P3-3 outline; the single-mutation-gate design IS this phase's `Database`-authoritative
  goal.
- `todo/first-arg-index-partially-ground-instance-keys-into-bucket-2026-09-05.md` — the
  `is_term_instance` half of the deep-gate wiring (item 3 above); touch it while you're in
  `arg_index.py`/`compiler/predicate.py` for state relocation anyway.
- `todo/owa-unknown-functor-head-args-never-indexed-2026-09-05.md` — unrelated to state
  relocation per se, but lives in the same dispatch-closure-building code P3-3 will be
  restructuring; worth a pass if the opportunity is cheap.
- `todo/registration-asserting-probes-for-inspection-builtins-2026-09-05.md` — evidence
  hardening for `term_variables/2`, `copy_term/2`, `=../2`, `functor/3`, `arg/3`,
  `numbervars/3`, `dif/2`; if reflection/inspection surfaces are touched for the
  `(module, name, arity)` migration, extend their probes at the same time.
- `todo/python-c-twin-var-functor-compound-divergence-2026-09-05.md`,
  `todo/unify-c-tuple-branch-still-inclusive-pytuple-check-2026-09-05.md` — pre-existing,
  representation-adjacent, not P3-3's remit specifically, but filed alongside P3-2's
  close-out and worth a glance if C is being touched anyway.

## Stencil-seam requirement (evidence-based, not speculative)

`implementation_plans/copy-patch-cells-assessment-2026-09-05.md` (read-only assessment of
the parked copy-and-patch stencil JIT under the cell representation, memory:
`copy-patch-backend-status`) found that of the ~67.5k lines on the parked branch, the
**integration seam** (`compiler/predicate.py` stencil-backend selection, `_dispatch_fn`
swap, ~1,196 LOC) is the one piece that cannot be revived by re-extraction — everything
else (the 102-template stencil library, the C stitcher/ABI, the bench harness, ~80% of the
lowering pass) ports with little or no change, but the seam must be rewritten against
whatever P3-3 builds. That makes P3-3 the one opportunity to shape the seam so a future
stencil-backend rewrite is small: keep dispatch **backend-pluggable**, with **one
invalidation point** (today's `_dispatch_fn` mutation is scattered; consolidate it) and a
**per-predicate backend-choice hook** (so a future stencil-eligible predicate can opt into a
different dispatch implementation without a parallel adapter layer). This is a scoping
input, not a request to build or plan the stencil revival itself — that stays its own plan,
timing user-decided, and is explicitly out of P3-3's scope (see
`implementation_plans/stencil-v2-scoping-memo.md` for the revival shape and timing).

## Process discipline (carried forward; violations have been logged before)

- SDD: worktree per plan (`git worktree add .claude/worktrees/<name> -b feat/<name>` from
  clone HEAD — NOT origin), `EnterWorktree(path)`, `build_ext --inplace`, fresh baseline
  capture (full suite, failure-NAME set, `--continue-on-collection-errors`,
  `/workspace/clausal/venv/bin/python` FROM the worktree), ledger in the sdd-workspace, task
  briefs, per-task review + fix loops, whole-branch final review (top-tier model), merge
  only after an EMPTY (or fully reconciled + ledgered) name-diff.
- **NEVER `git add -A`** — the clone is shared with other instances/sessions; `-A` sweeps
  their in-progress todos and WIP into your commit. Stage explicit paths.
- **NEVER `git stash`** — same reason: the stash is a single shared stack across
  worktrees/sessions. A P3-2 task implementer used `stash`/`pop` for TDD-red verification
  despite this standing ban (checked immediately: no residue that time, but it was luck, not
  safety — another session's `stash pop` racing yours silently destroys or corrupts entries
  neither of you can recover). If you need a "does this fail before my fix" check, use a
  throwaway branch, a diff-and-revert-in-place, or a separate worktree — never the shared
  stash.
- **FOREGROUND ONLY** for subagent test runs. Implementer subagents have repeatedly run the
  full suite with `run_in_background` and then stalled "waiting for a notification" that
  never comes. Put this in every dispatch; if a subagent goes quiet with uncommitted work,
  message it a finish instruction — state is always recoverable (check `git status` + the
  scratchpad output files).
- Reviews: instruct reviewers to PROBE, not trust. P3-2's reviews caught real regressions a
  green suite and implementer self-review both missed (the `callable_` alias-mismatch false
  coverage claim being the sharpest example — see
  `todo/registration-asserting-probes-for-inspection-builtins-2026-09-05.md`). Spot-check
  inversion ledgers adversarially.
- Perf gate: interleaved A/B vs the branch base on `bench_struct_tabling` and `bench_fib`,
  >3% regression fails. Assert `'feat/p33...' in clausal.__file__` (or equivalent) before
  ANY bench run from outside the worktree — a P3-2 bench script silently imported canonical
  `/workspace/clausal` once and produced a reproducible 70x-wrong first result.
- `<harness-library>` is GATE_CORE — off limits. `_get_dispatch` signature frozen (~22 out-of-tree
  implementors).
- User ruling in force since 2026-09-05: C changes are allowed where they make sense — this
  relaxes any assumption that a phase defaults to "no C changes."

## After P3-3

Phase 4 (dict/set pair tagging `(tuple, k, v)` + the atom/string audit — do NOT migrate
dict/set pairs before Phase 4, per the spec's §6 hazard 2, re-affirmed at P3-2 close-out)
and Phase 5 (the Python seam — `implementation_plans/python-seam-classes-as-functors.md`
now supersedes §5a's TermProxy design as the intended seam answer; `packages/` migration;
docs). The stencil-v2 revival (see `implementation_plans/stencil-v2-scoping-memo.md`) gets
its own full plan after P3-3, once the dispatch seam this phase builds is real.
