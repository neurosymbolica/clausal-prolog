# HAND-OFF: plan and execute P3-2 (cell default flip)

**For the next Claude instance.** You are continuing the tagged-tuple program. Read this
file, then `implementation_plans/phase3-decomposition-and-p31-atom-pivot.md` (the
decomposition + the P3-2 outline at the bottom), then
`implementation_plans/tagged-tuple-term-representation.md` §1/§1b/§3/§3b/§4/§6 before
doing anything. Your job: write the full P3-2 implementation plan (same No-Placeholders
discipline as the P3-1 plan in that same file — it is your template), get the user's
go-ahead on any new rulings, then execute via subagent-driven development.
CLONE ONLY (/workspace/clausal-bug-fix); never touch /workspace/clausal.

## Where the program stands (all merged to clone main, HEAD ≈ 309f9dad, 2026-09-04)

- Phases 0–2: done (fast path, funnel, `-tagged_terms` bridge; cells beat classes 1.8×).
- toklex L0 + PrologReader L1/L2: done (§1c STATUS block tells the story).
- **P3-1 atom pivot: MERGED** (15 commits, 523ae9ef..309f9dad). Atoms are interned
  global strs; identity machinery, `$atom`, shadowing warnings, `-overwrites` deleted;
  C cons rule retired (bytes/codes block KEPT); standard order collapsed; `-hide`
  shipped (U+E000, collision diagnostics, writer demangling); strict-atoms is
  per-module (a cross-module pool leak was found and fixed — `_locally_declared_names`
  in compiler_v2.py + `_intern_atom` in import_hook.py, both-orders tests). Full-suite
  name-diff vs baseline ended EMPTY; perf FASTER (fib −6.0%, struct_tabling −5.3%).
- Memory files (`tagged-tuple-term-design-parked`, `toklex-formalism-status`,
  `phase3-parser-user-owned`) carry the same status — trust them.

**User rulings in force (approved 2026-09-04):** R1 ⟨SEP⟩=U+E000; R2 `atom(X)` true for
every str; R3 Phase 3 runs on the existing Python-syntax pipeline (reader-surface
migration is a later phase); R4 qualified goals `(":", module, Goal)` + `solve(module=)`
— R4's detail is ratified at P3-3 planning, not yours.

## P3-2 scope (from the committed outline — this is the phase you plan)

Make cell tuples the UNCONDITIONAL compiled representation (today: opt-in via the
`-tagged_terms` module flag). Workstreams: unconditional emission at the two dual
sites; head-dispatch reachability; slot-0 first-arg indexing; cross-module compound
exchange; `_valid_functor_slot` narrowed to `{str, TUPLE_TAG}` (drop deprecated Var
functors + the slot-0 deref); per-module OWA flag (net-new); compiler-side kwarg
placement + Var backfill; the fate of generated data-functor classes; deletion of the
flag machinery; parity fixtures become old-vs-new regression anchors. NO C changes
expected (cells ride the existing tuple branches — Phase 2 proved it).

## Recon anchors (verified 2026-09-04 at 8a6419f3; P3-1 may have shifted lines ±;
## re-verify each before writing plan steps — but the STRUCTURE is current)

These findings existed only in the previous instance's context — they are the crown
jewels of this handoff:

1. **terms_to_ast.py** (`clausal/logic/compiler/`): entry `term_to_ast_expr` (~:420).
   Dual cell-emission sites: Site A = source-written compound, the Call(LoadName)
   branch ~:776-808, gated `cell_functor_for_name` (falls to class ctor when kwargs
   present); Site B = live term instance ~:817-896, gated `cell_functor_for_instance`
   ~:834-845, checked BEFORE the Phase-0 `_clausal_new` fast path. Both funnel through
   `_is_cell_functor_class` ~:256-297 (PredicateMeta, has fields, no `_clauses`, no
   `_dynamic_arities`, no position field, arity>0). Flag plumbing: sealed module stack
   `_TAGGED_TERMS_STACK` ~:220, contextmanager `tagged_terms_lowering` ~:224, read via
   `tagged_terms_globals()` ~:247; opened in compiler/predicate.py ~:1257-1284 and
   ~:1827-1852 from `globals_.get(TAGGED_TERMS_FLAG)`. Directive parsing:
   term_rewriting.py `_handle_tagged_terms_directive` ~:4653 (post-P3-1 the file
   shifted; grep). Flip = delete all gating; keep the ownership helpers minus the
   `scope is None` early-outs.
2. **THE BIG GAP #1 — head-pattern reachability**: source-written compound heads NEVER
   reach head_match's cell/class pattern branches in practice — they are hoisted to
   Var + body Unify by `_normalize_structural_head_args` at assert time; only the
   arg-index bucket-lift (`list_dispatch.py` `_lift_clause_at_pos` ~:50-115, from
   `_get_head_arg` ~:39-47) puts structure back, and it only recognizes
   Compound/is_term_instance shapes. Pinned by
   tests/test_tagged_terms.py::TestHeadPatternReachability. Flip requires teaching the
   lift (or the hoisting) cell shapes — this is the crux task of P3-2.
3. **THE BIG GAP #2 — cross-module compound exchange**: the bridge's own-module gate
   (terms_to_ast.py ~:331-338, ~:355-358 — imported functor keeps class emission) was
   a deliberate bridge limitation (directive docstring term_rewriting.py ~:4676-4683).
   Post-P3-1, functors are global strs — the natural answer is that cell emission no
   longer needs module ownership at all. Decide + justify in the plan.
4. **arg_index.py**: `_arg_to_index_key` ~:84-142 and runtime twin `_runtime_arg_key`
   ~:145-179 have NO tuple/cell branch (tuples fall to `_INDEX_VAR`, everything lands
   in the fallback bucket; `_INDEX_THRESHOLD = 4`). The bridge deliberately could NOT
   flag-gate a fix (the key fn runs at dispatch time with no module context) — adding
   the slot-0 branch is safe exactly once cells are unconditional. Pinned by
   tests/test_tagged_terms.py::TestHeadPatternReachability::test_index_dispatch_routes_every_cell_to_the_all_clauses_fallback.
   Design §3.1: slot 0 becomes the index key.
5. **cells.py**: `_valid_functor_slot` ~:100-108 currently allows `{str, TUPLE_TAG,
   unbound Var}` — narrow to `{str, TUPLE_TAG}` (§1b deprecation), remove the slot-0
   deref from `is_cell`/`_cell_shape` (~:111-130) and the `_helpers.py` funnel branches
   (~:260-420, shared `_cell_functor` ~:312-323). The plain-tuple-starting-with-str
   ambiguity docs become moot once cells are unconditional — update them.
6. **head_match.py**: `_cell_match_pattern` ~:72-92 emits
   `MatchSequence([MatchValue(functor), *args])`; two gated call sites ~:638-664 and
   ~:701-718. Codegen trap (§4): the tuple data tag must be a DOTTED value pattern
   `case (builtins.tuple, ...)` — never bare `tuple` (capture!) or `__builtins__`.
7. **kwarg placement + backfill**: goal-position kwarg reordering exists
   (terms_to_goalop.py ~:398-421 via `db.signature_for`); CONSTRUCTION backfill lives
   only in `PredicateMeta.__call__` (predicate.py ~:731-781, `_MISSING`→fresh Var) —
   the bridge kept keyword construction on class emission because of it. P3-2 moves
   this to the compiler: resolve kwargs against the declared signature, emit Var()
   calls for omitted positions in the cell literal.
8. **OWA flag**: NET-NEW — no existing machinery; only the directive-parsing pattern
   (`-tagged_terms`/`-strict_atoms` handlers in term_rewriting.py) to imitate.
   Wrong-arity today raises in `PredicateMeta.__call__` ~:753-773.
9. **Data-functor class fate**: the bridge's "flagged module's own class constructor
   matches nothing" trap (term_rewriting.py docstring ~:4684-4691; pinned in
   test_tagged_terms.py ~:347-357) becomes universal at flip — the plan must decide
   whether pure-data functor classes are still generated at all (predicate classes
   stay until P3-3's state relocation). NOTE from P3-1's final review: a 0-arity
   predicate declared with call syntax `p()` legitimately still mints a PredicateMeta
   — don't confuse it with data-functor minting.
10. **Bridge pieces**: interning hook (cells.py ~:213-441, default OFF — leave OFF,
    the measured shape was negative); parity fixtures
    (tests/fixtures/*_tagged.clausal + tests/tagged_terms_support.py `normalize_term`,
    simplified for str atoms in P3-1 T7) become the old-golden vs new-default
    regression anchors; everything gated on the flag is deleted machinery.
11. **P3-1 leftovers that interact with P3-2**:
    - `todo/first-arg-indexing-str-caller-still-reaches-list-fact-2026-09-04.md` —
      FIRST follow-up (semantic hole: str caller reaches a list-headed fact through
      one indexing path; repro inside). Fixing it may fold naturally into workstream 4.
    - `todo/pythonic-ast-names-leak-into-strict-atom-namespace-2026-09-04.md` —
      scheduled with P3-2 (bootstrap pool seeds `Add`/`Call`/... as resolvable atoms).
    - tests/test_tagged_terms.py: P3-1 inverted its atom-related pins; the CELL
      machinery pins are still flag-era and are your regression base.

## Hazards (spec §6, still live for P3-2)

`_get_dispatch` protocol frozen (~22 out-of-tree implementors — packages/clausal-scipy
etc.); `clausal-provenance/engine.py` reconstructs via class+kwargs (~10 sites) — the
seam is P5's, but don't break imports; source-level `(a, b)` overload (goal=conjunction
vs data) — emitter tags exactly the data occurrences; dict/set pairs stay plain
2-tuples until Phase 4 (do NOT migrate them in P3-2).

## Process discipline (unchanged; violations have been logged before)

- SDD: worktree per plan (`git worktree add .claude/worktrees/<name> -b feat/<name>`
  from clone HEAD — NOT origin), EnterWorktree(path), build_ext --inplace, fresh
  baseline capture (full suite, failure-NAME set, `--continue-on-collection-errors`,
  /workspace/clausal/venv/bin/python FROM the worktree), ledger in the sdd-workspace,
  task briefs, per-task review + fix loops, whole-branch final review (top-tier model),
  merge only after an EMPTY (or fully reconciled + ledgered) name-diff.
- P3-2 should mostly be an EMPTY-diff phase (representation flip, not semantics) —
  except goldens that pin class-codegen shapes; use the P3-1 reconciliation pattern
  (expected-inversions ledger) for those.
- NEVER `git add -A`; NEVER `git stash`; explicit staging; commit trailers
  (Co-Authored-By: Claude <model> + Claude-Session line — copy from any recent commit).
- **Subagent caveat learned this session**: implementer subagents repeatedly ran the
  full suite with run_in_background and then stalled "waiting for a notification" that
  never comes. Put FOREGROUND ONLY in every dispatch; when a subagent goes quiet with
  uncommitted work, SendMessage it a finish instruction (state is always recoverable —
  check git status + the scratchpad output files).
- Reviews: instruct reviewers to PROBE, not trust (this session's reviews caught a
  mis-swept fixture, a strictness leak, a writer leak, and a twin-parity crash that
  implementer sweeps had all missed). Spot-check inversion ledgers adversarially.
- Perf gate: interleaved A/B vs the branch base on bench_struct_tabling + bench_fib,
  >3% regression fails. P3-2 is where cells become default — the Phase-2 measurement
  (B/A = 0.561 walker-heavy) predicts a WIN; verify it materializes end-to-end.
- <harness-library> is GATE_CORE — off limits. `_get_dispatch` signature frozen.

## After P3-2

P3-3 (state relocation + qualified goals) — outline in the decomposition doc; its recon
(Database sync-direction inversion, `$disp_` bake-in, `_DbDispatchAdapter` precedent,
two parked identity/mutation-gate todos) is summarized there. Then Phase 4 (dict pairs +
atom/string audit) and Phase 5 (TermProxy seam per §5a + packages/ + docs).
