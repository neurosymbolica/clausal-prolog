# Phase 3 Decomposition + P3-1 (Atom Pivot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax. Only §P3-1 below is executable now; P3-2/P3-3 are scoped
> outlines to be planned just-in-time after P3-1 merges.

**Spec:** `implementation_plans/tagged-tuple-term-representation.md` §1a/§1b/§4/§5/§6/§7
(user-approved rulings 2026-09-03/04). Recon reports behind this plan's file:line claims
were verified 2026-09-04 against main `8a6419f3`.

## Why three sub-plans, and in this order

Phase 3's scope list is ~9 workstreams across compiler, runtime, C, and tests
(~2–3 engineer-weeks — too large for one reviewable plan). Dependency-minimal order:

1. **P3-1 Atom pivot** (this document, fully planned): atoms lower to interned global
   strs; identity machinery deleted; cons rule retired; `-hide` lands. Self-contained,
   and doing it FIRST means P3-2's cell patterns are pure literals from day one (no
   class-atom args inside cells to churn twice).
2. **P3-2 Cell default flip** (outline below): the `-tagged_terms` bridge promoted to
   the unconditional representation; head-dispatch reachability + slot-0 indexing +
   cross-module exchange + OWA flag + kwarg backfill; bridge machinery deleted.
3. **P3-3 State relocation + goal form** (outline below): predicate state moves into
   the per-module `Database` (made authoritative; today it syncs Database→class);
   module-qualified goals for cell terms; specialization stops minting classes.

## PROPOSED RULINGS — need user sign-off before P3-1 EXECUTION starts

- **R1 (⟨SEP⟩ codepoint): U+E000** (first private-use codepoint), not NUL — NUL inside
  C strings is a footgun for every C twin that ever touches a mangled functor, and PUA
  renders visibly in debuggers. One-line change to `clausal.toklex.pl`'s `reserved`
  class (currently the U+0001 placeholder) rides in Task 6.
- **R2 (atom/1 semantics): `atom(X)` becomes true for every `str`** (the §5 collapse,
  made concrete): `atom/1` and `string/1` end up co-extensional for strings;
  `string/1` is retained as a compatibility alias with its deprecation/`atomic`
  relationship audited in Phase 4 as planned. (Recon: `atom_chars/2` has ALREADY
  emitted plain strs for its chars→atom direction — `chars.py:386` — so today's
  semantics are internally inconsistent; the collapse fixes an existing blur.)
- **R3 (surface deferral):** Phase 3 operates entirely on the existing Python-syntax
  `.clausal` pipeline. New-surface migration (PrologReader-read modules, double-quote →
  char-list source discrimination, no-dots/bracketed-bodies) is a SEPARATE later phase
  gated on the user's parked surface rulings. Consequence inside P3-1: in the current
  surface, a `"red"` literal and a bare `red` atom compile to the SAME runtime value
  ("red"); the double-quote/char-list distinction §1b describes exists only in the new
  surface when it arrives.
- **R4 (qualified-goal spelling, ratify at P3-3 planning, flagged early):** explicit
  qualified cell `(":", "module_name", GoalCell)` (ISO `m:G` analog) plus
  `solve(goal, module=...)`; an unqualified cell goal resolves against the calling
  module's Database and raises a clear existence/context error otherwise. Modeled on
  the existing dotted-chain resolution in `solve.py:783-889`.

---

# P3-1 — Atom Pivot Implementation Plan

**Goal:** Bare atoms become interned global Python strs (identity = spelling);
per-module atom classes, the identity/shadowing machinery, and the C str~char-list cons
rule are deleted/retired; `-hide` gives modules compiler-renamed private atoms.

**Architecture:** Flip the single classification point (`visit_Name`'s atom branch) to
emit `Constant("name")`; stop minting zero-field PredicateMeta classes; teach the small
set of atom readers (`atom/1`, `is_atom`, standard order) that a str IS an atom; delete
the machinery whose reason-to-exist (per-module identity) is gone; retire the cons rule
in C and its Python shadow (`SegString.__unify__`) in lockstep; add `-hide` as
compile-time literal mangling. This plan CHANGES observable semantics deliberately —
the full-suite gate is therefore a *reconciled* diff (every changed test name maps to a
planned inversion recorded in the ledger), not an empty one.

**Tech Stack:** Python + one scoped C change (`_variables.c`), pytest, existing bench
harnesses for the perf gate.

## Global Constraints

- CLONE ONLY, worktree of `/workspace/clausal-bug-fix`; venv python from the worktree;
  NEVER `git add -A`/`git stash`; commit trailers (Co-Authored-By + Claude-Session, as
  on every recent commit).
- **C changes present** (Task 5): `setup.py build_ext --inplace` in the worktree before
  any suite run after Task 5, AND in the clone root after merge.
- Baseline: capture fresh at branch base (do NOT reuse the toklex-era baseline; other
  sessions have advanced main). Full-suite gates compare failure-NAME sets; from Task 3
  onward the gate is **diff == the ledger's expected-inversions list**, exactly.
- Perf gate: interleaved A/B (old main vs branch head) on `bench_struct_tabling` and
  `bench_fib` — no metric regresses >3% (Phase-1 precedent).
- `_get_dispatch` protocol untouched (frozen, ~22 out-of-tree implementors).
- `eval_harness` is GATE_CORE — not touched by this plan; if any task drifts into it, STOP.
- Semantic inversions are LEGITIMATE only where §1b/§5 rules them; every pinned-test
  change cites the ruling in a comment.

## File Structure (primary; task briefs carry exact line refs from recon)

```
clausal/templating/term_rewriting.py   visit_Name atom branch; -module/-private minting;
                                       -hide directive (new); strict-atoms diagnostic text
clausal/logic/compiler_v2.py           _process_bare_atom_refs / _process_declarations /
                                       _check_atom_shadowing (delete) / warning classes
clausal/logic/predicate.py             register_atom_identity block (delete);
                                       _make_atom_identity_unify (delete); is_atom util
clausal/logic/compiler/terms_to_ast.py atom_identity_lowering/$atom (delete); is_atom branch
clausal/logic/solve.py                 atom_identity_lowering call sites (delete)
clausal/logic/builtins/type_checks.py  atom/1, atomic/1 (str-accepting)
clausal/logic/builtins/_helpers.py     _standard_order_key collapse
clausal/logic/variables/_variables.c   cons-rule block retirement (~:1168-1311)
clausal/terms.py                       SegString.__unify__ lockstep change
clausal/logic/builtins/dcg.py          audit only (+ regression tests)
clausal/logic/runtime/_list_unify.c    audit only
clausal/tools/toklex/specs/clausal.toklex.pl   reserved class -> U+E000 (R1)
tests/ (many)                          planned inversions, each citing §1b/§5
```

### Task 0: Q5 corpus scan + $atom-shape check (gate for everything after)

Scripted scan answering design-doc §8 Q5: does anything genuinely need per-module atom
*identity* that `-hide` cannot express? Scan `packages/`, `tests/fixtures/*.clausal`,
the domains corpus for: cross-module same-spelling atoms deliberately kept distinct
(the `-private` shadow pattern), `is`/`id()` identity comparisons on atoms, and consumers
of `ClausalAtomShadowingWarning` semantics. Also: grep tests for `$atom(` codegen-shape
assertions (recon found zero direct references to `register_atom_identity` — confirm).
**Deliverable:** a report in the SDD workspace + a ledger entry; if a genuine
irreplaceable per-module-identity consumer surfaces, STOP and surface to the user
(it would falsify §1b's global-by-spelling ruling). Expected outcome per recon: only
the deliberately-pinning tests (inverted later, Task 3) and the `-private` shadow
fixtures (which `-hide` re-expresses).

### Task 1: str-as-atom acceptance (runtime readers, dual-accept)

Make every atom READER accept plain strs while class atoms still exist (transitional
within the branch; classes die in Task 2):
- `type_checks.py:66-71` `atom/1`: true for `isinstance(x, str)` (R2) OR zero-field
  class (transitional); `atomic/1` already accepts both (`:123-151`) — add a test.
- `predicate.py` `is_atom` util + `_helpers.py` accessors: str-atom aware where they
  answer functor/arity questions for atoms (`functor_arity("red") == ("red", 0)`).
- TDD: new tests in `tests/test_global_atoms_default.py` (new class,
  `TestStrAtomsAcceptance`) asserting `atom("red")`, `functor_arity`, unification
  `"red" = "red"` succeeds / `"red" = "blue"` fails, `atom_chars("ab", ['a','b'])`
  round-trips (already-true behaviors get pinned, new ones added).
Gate: full covering set green; full-suite name-diff EMPTY (acceptance is additive).

### Task 2: the lowering flip + minting stop

- `term_rewriting.py:1786-1810` `visit_Name` atom branch: emit
  `Constant(value=identifier)` instead of `Name` (compile-time str constants are
  auto-interned; `sys.intern` explicitly where dynamic). The Kleene alias fold
  (`:1729-1732`, `_TRUTH_ALIASES`) stays ahead of the atom branch — verify order.
- `-module`/`-private` handling (`:4474-4600`): stop minting zero-field atom classes
  (predicate classes with fields are untouched); atoms declared there still register
  in `transformer.atoms` for strictness.
- `compiler_v2.py:861-1047`: `_process_bare_atom_refs` keeps STRICTNESS (undeclared
  atom → NameError, `-implicit_atoms` escape unchanged) but auto-mint now means
  "accept the spelling", not "create a class"; the global pool
  (`import_hook.py:185`) consulted for builtin atoms only as needed; `$intern_atom`
  (`import_hook.py:66-116`) simplifies to the str.
- `terms_to_ast.py:814-815` `is_atom(term)` emission branch: atoms that are strs hit
  the scalar Constant branch (`:494`) naturally — remove/adjust the class-atom branch.
- Strict-atoms diagnostic text (`compiler_v2.py:946-981`): reword the "five legitimate
  ways" for the new model.
- Tests: compile-and-run fixtures asserting `red` in module A unifies with `red` from
  module B (the INVERSION of today's pinned behavior — this task flips
  `test_bare_atoms_share_identity_across_modules`-adjacent semantics for
  module-declared atoms too; the wholesale pinned-test inversion is Task 3, but tests
  newly written here assert the new model from the start).
Gate: covering set green EXCEPT the identity-pinning tests (list them in the ledger as
expected-red until Task 3); no other new failures.

### Task 3: identity-machinery deletion + pinned-test inversion

- Delete: `register_atom_identity`/`atom_by_id`/`_ATOM_IDENTITY_TABLE`
  (`predicate.py:1258-1291` + `__all__`), `atom_identity_lowering`/`atom_identity_expr`
  (`terms_to_ast.py:145-194`), call sites `solve.py:384,426-428`, `$atom` global
  (`compiler/predicate.py:313-317`), docstring/shape mentions
  (`compiler/predicate.py:1268,1838`, `_lower_goalop_shared.py:116` — check for real
  shape-matching code at each), `_make_atom_identity_unify` + warned-set
  (`predicate.py:338-398`), `ClausalAtomIdentityMismatchWarning` +
  `ClausalAtomShadowingWarning` + `_check_atom_shadowing`
  (`compiler_v2.py:46-121,1050-1139`).
- Invert the pinned tests, each edit citing §1b: `test_atom_identity_warning.py`
  (cross-module same-name atoms now UNIFY; warning machinery gone — most of the file
  becomes a small "atoms are global" test set), `test_atom_shadowing.py` (shadowing
  can't exist; keep `-overwrites` parsing tests only if the directive survives for
  predicates — check its non-atom uses first), `test_global_atoms_default.py`
  (`test_module_decl_atom_is_not_global` and `test_private_shadows_global` invert;
  `-private` atoms now = global atoms until Task 6 gives `-hide` the private story).
- Fixture pairs (`global_atoms_*`, `strict_atoms_*`, `atomshadow_*`): update
  expectations, don't delete files (they now pin the NEW semantics).
Gate: full-suite name-diff == exactly the ledger's expected-inversions list.

### Task 4: standard-order collapse

`_helpers.py:530-535`: drop the `is_atom` class branch + `0/1` discriminator — one
`_ORD_ATOM` str path. (Design-doc §5's "atoms sort via the compound branch" is STALE —
recon traced the collapse to Phase 1 commit f0d68d2f; the close-out task corrects the
doc.) Audit `sort/2`/`msort`/`keysort`/`setof` goldens; expected observable change:
only the str-vs-same-spelled-class tie edge, which no longer exists. Gate: name-diff
still == expected-inversions (likely unchanged by this task).

### Task 5: cons-rule retirement (the C change)

- `_variables.c` `do_unify` str↔list block (~`:1168-1279` + swapped continuation to
  ~`:1311`): remove; str-vs-list unification falls through to the generic
  rich-compare failure. The adjacent bytes↔list block (~`:1282+`): KEEP (codes model
  untouched by §1b — note for the reviewer).
- `clausal/terms.py` `SegString.__unify__` (~`:1147`): lockstep — SegString stays the
  char-LIST optimization (unifies with lists/SegLists as today) but must no longer
  unify a bare `str` with a char list. Trace every SegString unify path.
- Audits with regression tests: `_list_unify.c` normalization helpers
  (`maybe_promote_to_str` etc. — confirm they operate WITHIN list-world, not across
  the retired str~list bridge); `dcg.py` `phrase/2,3` (double-check no runtime
  reliance on bare-str-as-char-list; add a `phrase` test over an explicit char list
  AND one asserting a bare str goal errs/fails cleanly rather than silently
  cons-unifying).
- The Phase 2 bridge's deferred cons-rule guard test: find it (grep `cons` in
  tests/test_tagged_terms*.py) and flip it to assert retirement.
- Expected inversions: any test asserting `"abc"` unifies with `['a','b','c']` — enumerate
  via grep BEFORE the change; each goes to the ledger.
- `build_ext --inplace` before every suite run from here on.
Gate: name-diff == updated expected-inversions; interleaved perf A/B on
`bench_struct_tabling` shows no regression (this block sat in the unify hot path —
removal should be neutral-to-positive).

### Task 6: `-hide` (mangling + R1 separator)

- New directive `-hide([a, b])` parsed alongside `-private` (`term_rewriting.py`
  directive dispatcher): registers the atoms as module-atoms AND marks them hidden.
- Mangling: `HIDDEN_SEP = ""` defined ONCE (propose `clausal/logic/atoms.py`, a
  tiny new module also exporting `mangle(module_name, atom) -> str` and
  `demangle_for_display(s)`); `visit_Name` substitutes
  `Constant(mangle(module, name))` for hidden atoms in the owning module. Other
  modules cannot spell it (the reader rejects U+E000 — R1 updates
  `clausal.toklex.pl`'s `reserved` class from the U+0001 placeholder; the CURRENT
  Python-syntax surface cannot produce it either since identifiers/str literals with
  U+E000 are… str literals CAN contain it — document as the same out-of-warranty
  forgery §1b already accepts for `atom_chars/2`).
- `-private` relationship: `-private` keeps its current (visibility-advisory,
  now-global-identity) meaning; `-hide` is the new stronger tool. Migration note in
  docs close-out.
- Printing: the reified renderer + `repr` paths render `m.name` human form for mangled
  atoms (find the renderer's atom case; one substitution point).
- Tests: hidden atom unifies within module; other module's same spelling does NOT
  reach it; `atom_chars` forgery works (documented out-of-warranty, pinned as such);
  renderer shows human form; toklex clausal-dialect test updated for U+E000.
Gate: name-diff == expected-inversions.

### Task 7: whole-suite reconciliation + perf gate

- Reconcile: final full-suite name-diff vs baseline must equal the ledger's
  accumulated expected-inversions EXACTLY; every line traced to a §-ruling citation.
- Sweep for stragglers: grep the §7 coupled surfaces (`is_atom`, zero-field
  `PredicateMeta` constructions, `make_atom` callers — `predicate.py:1308`) for
  now-dead atom-class paths; delete or convert with tests.
- Interleaved perf A/B (both benches) recorded in the ledger.
- Scryer-corpus reader tests + toklex suites must be untouched-green (different
  subsystem, shared repo).

### Task 8: close-out

Design doc: §5 stale-order-claim correction; §1a/§1b STATUS note (atom pivot
IMPLEMENTED, R1/R2 rulings recorded, cons rule retired); strict-atoms migration note
updated for `-hide`; memory + final report with the reconciled-inversion list.

---

# P3-2 — Cell Default Flip (DONE 2026-09-05; outline below kept for record)

**DONE.** Full plan: `implementation_plans/p32-cell-default-flip.md` (Tasks 0-10).
Ledger + task reports: `.superpowers/sdd/p32-cell-default-flip/`. Status note +
ruling summary: `implementation_plans/tagged-tuple-term-representation.md` §1b
STATUS block. Memory: `tagged-tuple-term-design-parked` (P3-2 COMPLETE entry).
Executed on branch `feat/p32-cell-flip`, 28 commits `ef10baa4..aac9895a` plus the
close-out doc commits. One-line summary: cells became the unconditional compiled
representation in every module (the `-tagged_terms` flag deleted); both
load-bearing gaps the bridge documented were closed (head-pattern reachability via
`_lift_clause_at_pos`/`_walk_head` cell branches; cross-module exchange via R5's
own-module-gate deletion); slot-0 first-arg indexing shipped with a compile-time
deep-gate; instance-side cell emission was removed entirely (a deviation past the
outline below — R6 REVISED); `-implicit_functors` shipped as the net-new
per-module OWA directive (R7), default off; one authorized C change (Task 2C,
`_variables.c` tuple branches in `c_copy_term`/`c_collect_vars`/`c_is_ground`);
perf gate passed (`bench_struct_tabling` 0.606 head/base, `bench_fib` flat).
**Next: P3-3** — read `implementation_plans/p33-state-relocation-handoff.md` first.

<details>
<summary>Original outline (plan after P3-1 merges) — superseded by the executed
plan above; kept for the historical record of what was scoped before execution</summary>

Scope from recon (`terms_to_ast.py`, `head_match.py`, `arg_index.py`,
`list_dispatch.py`, `cells.py`, `_helpers.py`):
unconditional cell emission at Sites A/B (delete `_TAGGED_TERMS_STACK`/directive/flag
plumbing); **solve the two load-bearing gaps the bridge documented**: (1) head-pattern
reachability — teach `_normalize_structural_head_args`/`_lift_clause_at_pos`/
`_get_head_arg` cell shapes so source-written compound heads reach cell dispatch;
(2) cross-module compound exchange — the own-module gate (`terms_to_ast.py:331-358`)
must yield a global answer (str functors are global post-P3-1, which is exactly why
this plan follows the atom pivot); slot-0 indexing branch in
`_arg_to_index_key`/`_runtime_arg_key` (safe only now that cells are unconditional —
the bridge's own test documents this); narrow `_valid_functor_slot` to `{str, TUPLE_TAG}`
(drop deprecated Var functors, remove the deref from `is_cell`/funnel); per-module OWA
flag (net-new directive; construction-checking default stays ON); compiler-side kwarg
placement + Var backfill for signature-known partial construction (replacing the
`PredicateMeta.__call__` carve-out); decide the fate of generated data-functor classes
(the flagged-module constructor-mismatch trap becomes universal — likely stop
generating pure-data functor classes, keep predicate classes until P3-3); parity
corpus fixtures become old-golden vs new-default regression anchors; C untouched
(cells ride existing tuple branches — Phase 2 proved it).

</details>

# P3-3 — State Relocation + Qualified Goals (outline; plan after P3-2)

Scope from recon (`database.py`, `predicate.py`, `compiler/predicate.py`,
`globals_env.py`, `solve.py`, `specialization.py`, `tabling.py`): invert the sync
direction — `Database` (already per-module, `(functor, arity)`-keyed) becomes the
authoritative home for `_clauses`/`_dispatch_fn`/`_signature`/`_locked`/
`_dynamic_arities`/`_clauses_source`/tabling homes; `PredicateMeta` and adapters become
read-through (preserving the frozen zero-arg `_get_dispatch` duck type and the
`$disp_<name>_<arity>` bake-in via an equivalent direct-read); single mutation gate at
the Database (closes `todo/a-shared-predicate-has-no-single-mutation-gate.md` and
`todo/predicate-identity-is-keyed-on-spelling-not-on-the-class.md` — carry both into
the plan); `_term_to_goal`/`_infer_module`/`_goal_cache_key`/`_templatize_query_goal`
learn cell goals + the R4 qualified form (`(":", module, Goal)` + `solve(..., module=)`),
modeled on `_tabled_entry_for_goal`'s dotted-chain walk; `call/N` accepts cells;
specialization stops minting classes (`make_predicate`/`make_atom` callers at
`specialization.py:277,1313,1671` register Database rows instead); reflection/listing
surfaces (`reflection.py`, `inspection.py`, `compiler_v2.py`) migrate to
`(module, name, arity)` lookups.

**Full hand-off (recon crown jewels, process discipline, parked todos that fold in
naturally): read `implementation_plans/p33-state-relocation-handoff.md` before
planning P3-3** (added at P3-2 close-out, 2026-09-05).

**Stencil-seam planning input (ruled 2026-09-05, ratified as binding on this
outline):** the Database/dispatch redesign above must keep the dispatch seam
**backend-pluggable**, with **one invalidation point** and a **per-predicate
backend-choice hook** — not just a single-backend read-through. This is not
speculative: `implementation_plans/copy-patch-cells-assessment-2026-09-05.md`
found the parked copy-and-patch stencil JIT's own integration seam
(`compiler/predicate.py` stencil-backend selection, `_dispatch_fn` swap) is the
one piece of that ~67.5k-line branch that cannot be revived by re-extraction —
it must be rewritten against whatever P3-3 builds, so P3-3 is the one chance to
shape the seam so that rewrite is small instead of another bespoke adapter.
Revival itself is out of P3-3's scope (own plan, after P3-3 — see
`implementation_plans/stencil-v2-scoping-memo.md`); the requirement is scoping
input only.
