# P3-2 — Cell Default Flip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cell tuples become the UNCONDITIONAL compiled representation of compound data
terms — the `-tagged_terms` bridge's opt-in machinery is deleted, its two documented
load-bearing gaps (head-pattern reachability, cross-module exchange) are closed, slot-0
first-arg indexing lands, and the slot-0 domain narrows to `{str, TUPLE_TAG}`.

**Architecture:** Delete the flag/scope gating around the two existing dual emission
sites in `terms_to_ast.py` and the two gated pattern sites in `head_match.py` (the cell
machinery itself already works — Phase 2 proved it, P3-1 made functors global strs).
Close the reachability gap by letting the arg-index bucket lift restore `Call(LoadName)`
compounds into heads now that a cell pattern needs no class resolution. Give the
dispatch key functions a slot-0 branch (safe exactly because emission is now
unconditional). Data-functor classes stop being minted (R6 revised): declared names
bind their interned spelling str and signatures live in a per-module registry;
predicate classes stay until P3-3. NO C
changes expected — cells ride the existing tuple branches; if any task drifts into a
`.c` file, STOP and re-scope.

**Tech Stack:** Python only, pytest, existing bench harnesses for the perf gate.

**Spec:** `implementation_plans/tagged-tuple-term-representation.md` §1/§1b/§3/§3b/§4/§6;
outline + rulings context in `implementation_plans/phase3-decomposition-and-p31-atom-pivot.md`;
hand-off recon in `implementation_plans/p32-cell-flip-handoff.md`. All file:line anchors
below re-verified 2026-09-04 against clone main `5bcd66ec`.

## PROPOSED RULINGS — need user sign-off before EXECUTION starts

(R1–R4 were ratified 2026-09-04 and are in force; numbering continues.)

- **R5 (cross-module compound exchange): the own-module gate is deleted outright.**
  Post-P3-1 a functor IS its global str spelling, so a cell built in module A and a
  clause head compiled in module B agree by construction — the bridge's gate
  (`terms_to_ast.py:288-293` and `:311-315`) guarded a per-module-identity world that
  no longer exists. Consequence: imported and dotted functor references
  (`other.Wrap(1)`) also emit cells, carrying the BASE name (`"Wrap"`) as functor —
  same collapse the atom pivot made for atoms. Two modules using the same
  functor/arity spelling now exchange data freely; that is the ISO semantics this
  program exists to reach, not an accident.
- **R6 (data-functor class fate — REVISED, user ruling 2026-09-04): stop minting
  them.** `_process_declarations` (`compiler_v2.py:1049`) tuple entries for data
  functors no longer call `make_predicate`: the name binds its interned spelling
  str (the P3-1 atom treatment), so `-import_from` still finds an attribute and
  the BINDING SHAPE decides data-vs-predicate at every reference site — resolves
  to a `PredicateMeta` → predicate (class/goal emission until P3-3; `-dynamic`
  still mints predicate classes, so declare-then-assertz cannot be misread as
  data); str binding + signature-registry hit → data → cell. Signatures move off
  `cls._fields` into a per-module `__clausal_functor_signatures__` namespace dict
  emitted by the `-module`/`-private` rewrite (an assignment, so it survives the
  `.pyc` path — the flag's own trick); `-import_from` copies the exporter's
  entries. The position-field exclusion dissolves on the NAME side: it existed
  because CLASS construction dropped those fields, and a cell keeps every
  declared slot (reviewers: probe this). KNOWN COST, accepted by the ruling:
  `clausal-provenance`'s `getattr(mod, name)(**kwargs)` reconstruction stops
  being callable for data functors (the attribute is a str; imports still
  succeed) — it migrates in the parked Python-seam phase
  (`implementation_plans/python-seam-classes-as-functors.md`).
- **R7 (OWA directive spelling): `-implicit_functors`.** Parallel to
  `-implicit_atoms` (the existing per-module relaxation axis, so users learn one
  naming convention). Default OFF = construction checking stays ON: unknown functor
  or over-arity construction keeps failing exactly as today. With the flag: any
  keyword-free construction of any functor/arity in that module compiles to a cell
  (`sys.intern`ed literal functor). Keyword construction of an OWA-unknown functor
  stays a compile error (no signature to place against — spec §1).
- **R8 (str↔charlist index coalescing retires).** `_charlist_to_str_or_none`
  bucketing (`arg_index.py:43-64`, used by `_arg_to_index_key`/`_runtime_arg_key`)
  implemented the F095 strings-as-lists contract that P3-1's cons-rule retirement
  (§1b) killed: `"abc"` and `['a','b','c']` no longer unify, so co-bucketing them is
  wrong, and it is the mechanism behind the parked semantic hole in
  `todo/first-arg-indexing-str-caller-still-reaches-list-fact-2026-09-04.md` (str
  caller reaches a list-headed fact). Retire the str side; the BYTES side
  (`_bytelist_to_bytes_or_none`) stays — the bytes~list codes model was deliberately
  kept. The F095 str lift-skip in `_lift_clause_at_pos` (`list_dispatch.py`) retires
  with it (bytes skip stays). Task 4 confirms the todo's repro flips to symmetric
  1-solution behavior.
- **R9 (`-tagged_terms` directive is deleted, not deprecated).** Experimental,
  in-repo-only bridge (docstring says so); post-flip it would be a no-op lie. The
  unknown-directive error message (`term_rewriting.py:4672`) drops it from the list;
  the four `tests/fixtures/*tagged*.clausal` fixtures lose the directive line and
  become the old-golden vs new-default regression anchors.

## Global Constraints

- CLONE ONLY (`/workspace/clausal-bug-fix`); worktree per SDD
  (`git worktree add .claude/worktrees/p32-cell-flip -b feat/p32-cell-flip` from clone
  HEAD, NOT origin); `build_ext --inplace` in the worktree before the baseline run
  (C is untouched by the plan but the extension must exist to run anything);
  `/workspace/clausal/venv/bin/python` run FROM the worktree; full-suite runs with
  `--continue-on-collection-errors`; assert a run actually executed before trusting
  a diff.
- NEVER `git add -A`; NEVER `git stash`; explicit staging; commit trailers
  (Co-Authored-By + Claude-Session lines, copied from any recent commit).
- **NO C changes.** If a task appears to need one, STOP and surface it — that
  falsifies the Phase-2 "cells ride the tuple branches" result and needs a decision.
- `_get_dispatch` protocol frozen (~22 out-of-tree implementors); `eval_harness` is
  GATE_CORE — off limits; dict/set pairs stay plain 2-tuples (Phase 4, do NOT
  migrate); `clausal-provenance` reconstructs via `cls(**kwargs)` — under R6
  (revised) the attribute is a plain str for data functors, so the CALL breaks
  until the seam phase migrates it; `packages/` must still IMPORT cleanly —
  verify exactly that and no more.
- The interning hook (`cells.py:213-441`) stays default-OFF and untouched — the
  measured shape was negative.
- Full-suite gates compare failure-NAME sets vs the Task 0 baseline; from Task 2
  onward the gate is **diff == the ledger's expected-inversions list, exactly** —
  P3-2 is a representation flip, so inversions should be confined to codegen-shape
  pins, bridge-flag tests, and the R8 semantics fix; anything else is a defect.
- Perf gate: interleaved A/B (branch base vs head) on `bench_struct_tabling` +
  `bench_fib`; >3% regression on any metric fails. Phase-2 measured B/A = 0.561 on
  the walker-heavy shape — Task 9 verifies a win actually materializes end-to-end.
- Subagent dispatch briefs: FOREGROUND ONLY for suite runs (never
  run_in_background); reviewers instructed to PROBE, not trust; inversion ledgers
  spot-checked adversarially.

## File Structure

```
clausal/logic/compiler/terms_to_ast.py   scope stack → unconditional; gates lose flag/
                                         own-module/dotted early-outs; Site A kwarg
                                         placement + Var backfill; OWA emission
clausal/logic/compiler/predicate.py      flag reads at :1273-1277/:1843-1847 deleted;
                                         lift call sites (:914,:989,:1009,:1030,:1075)
                                         pass globals_
clausal/logic/compiler/head_match.py     gated cell-pattern sites unconditional; live-
                                         cell (ground tuple) head-arg pattern branch
clausal/logic/compiler/list_dispatch.py  _lift_clause_at_pos learns liftable cells;
                                         F095 str skip retires (R8)
clausal/logic/compiler/arg_index.py      slot-0 branch in both key fns; str-coalesce
                                         retirement (R8)
clausal/logic/cells.py                   TAGGED_TERMS_FLAG deleted; _valid_functor_slot
                                         → {str, TUPLE_TAG}; deref removed from
                                         _cell_shape; make_cell rejects Var functors;
                                         IMPLICIT_FUNCTORS_FLAG (new); docstrings
clausal/logic/builtins/_helpers.py       _cell_functor loses the deref + Var-functor
                                         acceptance; ambiguity comments updated
clausal/logic/predicate.py               is_data_functor instance-side gate (R6);
                                         __call__ untouched
clausal/templating/term_rewriting.py     -tagged_terms handler deleted (R9);
                                         -implicit_functors handler added (R7);
                                         emits __clausal_functor_signatures__ (R6/T1)
clausal/terms.py                         term_str/term_pformat cell branches (display)
clausal/reflection.py                    reified renderer cell branch (verify names)
clausal/import_hook.py                   predicate_builtins pool split (parked todo)
clausal/logic/compiler_v2.py             _process_declarations stops minting data-
                                         functor classes, binds spelling strs (R6/T2);
                                         pool-split consumer updates (Task 8)
tests/test_tagged_terms.py               flag-era pins inverted per ledger
tests/test_tagged_terms_parity.py        fixtures lose directive; stay as anchors
tests/tagged_terms_support.py            normalize_term unchanged (sanity only)
tests/golden/*.codegen.txt               regenerated deliberately, diffs read
tests/fixtures/*tagged*.clausal          directive lines removed
tests/audit_2026_05_25/test_class_C15_first_arg_indexing.py  F095 pin → §1b semantics
```

**Interfaces produced for later tasks** (single source of truth):
- `clausal.logic.predicate.is_data_functor(cls) -> bool` (Task 2) — the INSTANCE-side
  gate (compatibility: an externally-minted class instance still lowers to a cell);
  `terms_to_ast._is_cell_functor_class` becomes a thin import of it. NAME-side
  resolution: `terms_to_ast.functor_signature_for(name, namespace) ->
  tuple[str, ...] | None` (Task 1) — the `__clausal_functor_signatures__` registry
  first, `cls._fields` fallback while generated classes still exist (the fallback's
  data-functor half dies in Task 2).
- `terms_to_ast.lowering_scope(globals_)` / `lowering_globals()` (Task 2) — renamed,
  always-on successors of `tagged_terms_lowering`/`tagged_terms_globals`.
- `cell_functor_for_name(name, arity, resolve_globals=None) -> str | None` and
  `cell_functor_for_instance(term) -> str | None` keep their signatures (Task 2
  changes their internals only) — head_match and list_dispatch consume them.
- `_lift_clause_at_pos(clause, pos, globals_=None)` (Task 3) — new third parameter,
  default None preserves old refusal behavior for callers that cannot supply one.

---

### Task 0: worktree + baseline + anchor re-verification

- [ ] Worktree from clone HEAD; `EnterWorktree`; `setup.py build_ext --inplace`.
- [ ] Fresh full-suite baseline (failure-NAME set) captured to the SDD workspace
      ledger; expect ≈ the known ~142 pre-existing names (solver-dep + doc-snippet +
      C17-perf flake); two runs if the first looks anomalous.
- [ ] Scripted grep sweep confirming the plan's anchors still hold at the branch
      base (they were verified at `5bcd66ec`; other sessions commit to this clone):
      `_TAGGED_TERMS_STACK`, `cell_functor_for_name`, own-module gate comment,
      `_handle_tagged_terms_directive`, `_valid_functor_slot`, `_charlist_to_str_or_none`,
      `_lift_clause_at_pos`, `PredicateMeta.__call__`. Any drift → update the task
      briefs before dispatching, not after.
- [ ] Start the inversion ledger file in the SDD workspace (P3-1 format: test name →
      ruling citation → task).

### Task 1: signature-resolved construction (kwarg placement + Var backfill)

Still flag-gated — this task is ADDITIVE inside the bridge so it lands with an empty
suite diff, before the flip makes it load-bearing.

- [ ] `term_rewriting.py`: the `-module`/`-private` rewrite additionally emits a
      module-level `__clausal_functor_signatures__ = {"point": ("x", "y"), ...}`
      assignment covering every `(name, fields)` entry (predicates included —
      harmless, since the data/predicate split is decided by binding shape, not
      by the registry); `-import_from` handling copies the imported names'
      entries into the importer's dict. Key constant `FUNCTOR_SIGNATURES_KEY`
      lives in `cells.py`, beside the (doomed) `TAGGED_TERMS_FLAG`.
- [ ] `terms_to_ast.py`: `functor_signature_for(name, namespace)` — consult the
      namespace's registry first, fall back to a resolved class's `_fields`
      while generated classes still exist; `cell_functor_for_name` and Site A's
      placer route through it.
- [ ] `terms_to_ast.py` Site A (`:748-765`): today `if not kw_exprs:` guards the cell
      branch and `cell_functor_for_name` requires `len(cls._fields) == arity`.
      Replace with signature placement: resolve via `functor_signature_for`; when it
      answers for a data functor, build the positional slot list from it — positional args
      fill leading slots (over-arity = compile-time `SyntaxError` carrying the same
      functor/arity text `_term_arity_error` uses); keyword args fill their named
      slots (unknown field name = compile-time error naming the field and the
      declared tuple, mirroring `_term_construction_error`); every unfilled slot
      becomes a fresh `_call(_name("Var"))` expression. Emit
      `cell_literal_ast(functor, placed_exprs)`. Duplicate slot (positional +
      keyword for the same field) = compile-time error.
- [ ] `cell_functor_for_name`: drop the internal saturation check
      (`len(cls._fields) != arity → None`) in favor of a
      `(functor, fields) | None` return consumed by Site A's placer — or keep the
      bool contract and add a sibling `cell_fields_for_name`; implementer's choice,
      but head_match's call site (`head_match.py:651`, saturated-only by
      construction) must keep compiling unchanged.
- [ ] Tests (new class `TestSignatureConstruction` in `tests/test_tagged_terms.py`,
      flagged fixture): `point(y=2, x=1)` builds `("point", 1, 2)`; `point(1)`
      builds `("point", 1, Var)` (assert var-ness, not identity); `point()` builds
      two fresh Vars; `point(1, 2, 3)` and `point(z=1)` raise at compile with the
      functor named; parity: the same constructions in the unflagged twin build
      class instances whose fields match slot-for-slot (use
      `tagged_terms_support.normalize_term`).
- [ ] Run the covering set (`tests/test_tagged_terms*.py`,
      `tests/test_funnel_accessors.py`) then full suite: name-diff vs baseline EMPTY.
- [ ] Commit.

### Task 2: THE FLIP — unconditional emission + flag machinery deletion

The phase's pivot commit. Everything gated on the flag is deleted; the scope stack
survives RENAMED as the always-on compile-scope (it is how Site A knows which
namespace resolves a bare functor name — threading `globals_` through every
`term_to_ast_expr` recursion would be a 100-site signature change for zero benefit).

- [ ] `predicate.py`: add `is_data_functor(cls)` — the `_is_cell_functor_class` body
      verbatim (`PredicateMeta`, `_fields` non-empty, no `_clauses`, no
      `_dynamic_arities`, no `_position`/`position` field) — exported near
      `is_term_instance`. `terms_to_ast._is_cell_functor_class` becomes
      `from clausal.logic.predicate import is_data_functor` (keep the local alias so
      head_match's import path is one hop).
- [ ] `terms_to_ast.py`: rename `_TAGGED_TERMS_STACK`/`tagged_terms_lowering`/
      `tagged_terms_globals` → `_LOWERING_SCOPE_STACK`/`lowering_scope`/
      `lowering_globals`; docstrings rewritten (no more flag talk — the stack now
      answers only "which namespace resolves bare names in this compile").
      `cell_functor_for_name`: DELETE the own-module gate (R5) and the
      `scope is None → None` early-out — with no scope AND no `resolve_globals`
      there is nothing to resolve against, so return None (unchanged net behavior
      for scopeless callers); DELETE the dotted-name early-out: resolve
      `other.Wrap` by walking attributes from the namespace root (mirror
      `_dotted_name_from_loadattr` handling at Site A `:735`), and return the BASE
      class's `__name__` (R5). `cell_functor_for_instance`: delete the scope check
      and own-module gate entirely — `type(term)` + `is_data_functor` is the whole
      test.
- [ ] `compiler/predicate.py:1273-1277` and `:1843-1852`: delete the
      `TAGGED_TERMS_FLAG` read; both entrypoints always enter
      `lowering_scope(globals_)`. Delete the `TAGGED_TERMS_FLAG` import (`:80`).
- [ ] `compiler_v2.py _process_declarations` (`:1049`): tuple entries STOP minting
      (R6 revised) — delete the `make_predicate` call + `__module__` stamping and
      bind `predicate_builtins.setdefault(name, sys.intern(name))` instead, the
      same shape the atom entries above it use; the existing don't-clobber guard
      (never overwrite a real `PredicateMeta` — an in-file predicate class minted
      by `_make_functor_class_ast`) stays, which is exactly what keeps predicates
      as classes. `PredicateMeta.__call__` is untouched.
- [ ] `cell_functor_for_name` switches to `functor_signature_for` as its source of
      truth: namespace binding is a `PredicateMeta` → None (predicate — class/goal
      emission until P3-3); registry answers → the functor str. Delete the
      `cls._fields` data-functor fallback half. Both orders tested: a name that is
      BOTH a registry entry and a predicate class (declared in `-module` AND given
      clauses) emits as a predicate.
- [ ] `term_rewriting.py`: delete `_handle_tagged_terms_directive` (`:4979-5060`),
      its dispatch lines (`:4664-4665`), `transformer._tagged_terms` (`:3596`,
      `:5049`), the `TAGGED_TERMS_FLAG` import (`:31`); update the unknown-directive
      message (`:4672`) to drop `-tagged_terms` (R9). `cells.py`: delete
      `TAGGED_TERMS_FLAG` (`:97`) and its docstring block.
- [ ] Fixtures: remove the `-tagged_terms` line from
      `tests/fixtures/{tagged_shapes_tagged,struct_tabling_tagged,head_list_compound_tagged}.clausal`
      (and `tagged_shapes.clausal` if it carries one — verify). The parity suite
      (`tests/test_tagged_terms_parity.py`, 14 tests) keeps running: both twins now
      compile identically, and the recorded class-era ANSWERS are the regression
      anchor — that is the "old-golden vs new-default" role. Update its module
      docstring to say so.
- [ ] Goldens: `CLAUSAL_REGEN_GOLDEN=1 pytest tests/test_tagged_terms.py -k golden`,
      then READ the diff of all 5 `tests/golden/*.codegen.txt`: expected shape —
      cell literals replacing class constructor calls in bodies; head arms still
      class/capture patterns (reachability is Task 3); NO other drift. Any
      unexplained hunk → stop and investigate before committing.
- [ ] Invert the flag-era pins, each edit citing the ruling in a comment
      (ledger entries for every name):
      * `TestDirective` (4 tests) → directive now unknown: assert the SyntaxError
        and its message (R9).
      * `TestCellEmission::test_unflagged_sibling_constructs_class_terms`,
        `TestHeadPatterns::test_source_compound_unflagged_stays_a_class_pattern`,
        `::test_live_instance_unflagged_stays_a_class_pattern`,
        `::test_another_modules_functor_keeps_the_class_pattern` (R5),
        `::test_partial_construction_keeps_the_class_pattern` (Task 1 semantics) —
        all invert to cell expectations.
      * `TestCellHeadDispatch::test_the_flagged_modules_own_class_constructor_matches_nothing`
        → the constructor no longer exists (R6): rewrite to pin `m.point == "point"`
        (a declared data functor binds its spelling) and that `("point", 3, 4)`
        matches. Same for `TestBucketPatternIntegration::test_a_class_instance_caller_finds_nothing`;
        sweep the suite for tests constructing DATA terms via `m.<functor>(...)`
        and rewrite them to literal cells (each in the ledger, R6).
      * `TestGateSymmetry` scope tests (`test_an_unflagged_compile_inside_a_flagged_scope_emits_no_cells`
        etc.) → deleted with the gate; the position-field pair stays (gate logic
        lives on in `is_data_functor`).
      * `TestDefaultPathGolden` → regenerated goldens (see above).
      * `TestHeadPatternReachability::test_index_dispatch_routes_every_cell_to_the_all_clauses_fallback`
        keeps passing UNTIL Task 4 — it asserts `_runtime_arg_key(cell) is _INDEX_VAR`,
        still true; its class-term half (`mod.point(3,4)` keys as `("point", 2)`)
        now tests a CELL and still passes (same key). Re-read and adjust wording only.
- [ ] Mid-branch invariant to verify with a test, not assume: a cell argument
      dispatches through the all-clauses fallback (unindexed but CORRECT), and a
      cell in a body `Unify` against another cell unifies — i.e. the flip changes
      representation, not answers. The parity suite green IS that check.
- [ ] Full suite: name-diff == ledger exactly. Commit.

### Task 3: head-pattern reachability (the crux)

Source-written compound heads are hoisted to Var + body-Unify at assert time
(`database.py:487`); only the bucket lift (`list_dispatch.py:50`) restores structure,
and it refuses `Call(LoadName)` terms (`:159-162`) because pre-cells the pattern
emitter needed the class in the bucket's globals. A cell pattern is a plain literal —
no resolution needed at match time, only at LIFT time (to ask "is this a data
functor, and is it saturated?").

- [ ] `_lift_clause_at_pos(clause, pos, globals_=None)`: new parameter. Replace the
      unconditional `Call` refusal with: lift when the Call is keyword-free AND
      `cell_functor_for_name(name, len(args), globals_)` answers (base name for
      LoadAttr chains, per R5) — rebuild the head with the Call at *pos* exactly as
      the Compound branch does; otherwise keep refusing (unresolvable name, kwargs,
      predicate functor). Lift-time resolution reads the FULL module `globals_`
      passed down (it carries `__clausal_functor_signatures__`); the bucket's
      collected globals never mattered for a literal pattern — which is exactly
      why the old refusal dissolves. `head_to_match_pattern`'s Call branch
      (`head_match.py:641-676`) then emits the `('point', p1, p2)` sequence pattern
      — resolve there against the same `globals_`, which is already threaded.
- [ ] `compiler/predicate.py` lift call sites (`:914`, `:989-990`, `:1009`, `:1030`,
      `:1075`): pass the `globals_` already in scope in that function.
- [ ] `head_match.py`: add a LIVE-CELL branch to `head_to_match_pattern`, above the
      generic ground-literal (A02-F003) fallback: a `tuple` whose slot 0 is a `str`
      emits `_cell_match_pattern(t[0], [recurse(a) for a in t[1:]])`; a tuple whose
      slot 0 is `TUPLE_TAG` emits `MatchSequence` with the §4 DOTTED value pattern
      — `MatchValue(ast.Attribute(value=ast.Name('builtins'), attr='tuple'))` with
      `import builtins` guaranteed in the compiled module's preamble (grep how
      head_match emits module-level imports; `_cell_match_pattern` at `:72` may
      already carry this — verify, and NEVER a bare `tuple` name (capture) or
      `__builtins__`). This is the path an assertz'd fact with a ground cell
      argument takes after `_normalize_dataclass_fact` + lift.
- [ ] `_get_head_arg` (`list_dispatch.py:39-47`) needs no change (heads are still
      predicate instances/Compounds in P3-2 — cell HEADS are P3-3); assert that
      with a comment, not code.
- [ ] Invert `TestHeadPatternReachability::test_source_written_compounds_never_reach_a_head_pattern`
      → now asserts `case ('point', ...)`/`('seg', ...)` arms DO appear in bucket
      functions (ledger). Regenerate goldens again; read the diff — expected: cell
      sequence arms in bucket functions, body Unify goals for those positions gone.
- [ ] New tests (`TestCellHeadReachability`): 5+-clause predicate (over
      `_INDEX_THRESHOLD`) with source-written compound first args — ground caller
      selects the right clause via the bucket (assert via `capture_predicate_codegen`
      that the bucket arm is a sequence pattern, and via answers); unbound caller
      still enumerates all (output mode unbroken — the unlifted fallback path);
      imported-functor compound head arg lifts too (R5) — the pre-P3-2 refusal
      reason was exactly this case, so pin its inversion; a PREDICATE-functor
      compound head arg still refuses the lift.
- [ ] Full suite: name-diff == ledger. Commit.

### Task 4: slot-0 first-arg indexing + R8 coalesce retirement

Safe exactly now: the key functions run with no module context, and post-Task-2 every
compiled compound IS a cell, so a slot-0 branch can no longer disagree with emission.

- [ ] `arg_index.py` `_arg_to_index_key` (`:84-142`) and `_runtime_arg_key`
      (`:145-179`): insert the cell branch ABOVE the generic `(list, tuple)` branch:

      ```python
      if type(arg) is tuple and arg:
          slot0 = arg[0]
          if type(slot0) is str:
              return (slot0, len(arg) - 1)      # compound cell: same key shape as
                                                 # Compound / class-instance branches
          if slot0 is TUPLE_TAG:
              return (TUPLE_TAG, len(arg) - 1)   # tuple-data cell: length-keyed
      ```

      (import `TUPLE_TAG` from `clausal.logic.cells`; keep the existing
      `(functor, arity)` shapes so cells, `Compound`s, class-era instances and
      `Call(LoadName)` compile-time keys all land in ONE bucket — they already
      share the `(name, arity)` shape, which is why this is a small diff).
      Slot-0 Var or anything else falls through (list/tuple branch → `_INDEX_VAR`).
- [ ] R8: delete `_charlist_to_str_or_none` and its call sites in both key functions
      and `_static_call_key` (grep — the docstring at `:52` names it); KEEP
      `_bytelist_to_bytes_or_none`. Delete the `isinstance(lift_term, str)` half of
      the F095 lift-skip in `_lift_clause_at_pos` (bytes half stays, comment
      updated to cite §1b + R8). List heads consequently key `_INDEX_VAR`
      (unindexed — correct, lists were only indexable via the retired coalesce).
- [ ] Run the todo's repro (`todo/first-arg-indexing-str-caller-still-reaches-list-fact-2026-09-04.md`):
      str caller must now get 1 solution, list caller 1 solution. If the asymmetry
      SURVIVES the coalesce retirement, the todo's hypothesis was wrong — trace
      `_normalize_dataclass_fact` hoisting as the todo prescribes before writing
      any fix; do not guess. File the outcome in the todo (→ `todo/done/` if fixed).
- [ ] Inversions (ledger): `tests/audit_2026_05_25/test_class_C15_first_arg_indexing.py::test_F095_first_arg_index_coalesces_str_and_charlist`
      → rewritten to pin §1b/R8 semantics (separate buckets, 1 solution each,
      citing the ruling); `TestHeadPatternReachability::test_index_dispatch_routes_every_cell_to_the_all_clauses_fallback`
      → inverted: `_runtime_arg_key(("point", 3, 4)) == ("point", 2)`, and a
      >threshold cell-headed predicate demonstrably buckets (rename the test to
      match its new claim).
- [ ] New tests: bucket-sharing across producers — a clause asserted with a live
      cell arg and one written in source select the same bucket; tuple-data cells
      bucket by length; slot-0-Var tuple → `_INDEX_VAR`; bytes/bytelist coalescing
      still works (regression for the KEPT half).
- [ ] Memory pitfall check (`clausal-audit-probe-pitfalls`): index-fixture
      selectivity — make the fixture >_INDEX_THRESHOLD clauses with genuinely
      discriminating first args or the index never engages and the test proves
      nothing.
- [ ] Full suite: name-diff == ledger. Interleaved A/B spot-bench on
      `bench_struct_tabling` (this touched the dispatch hot path). Commit.

### Task 5: slot-0 domain narrowing to {str, TUPLE_TAG}

§1b: Var functors are DEPRECATED — they caused the bridge's one Critical, impose a
deref on every recognition, and permit category instability. Higher-order routes
through `functor/3` / `=..` / `call/N` (P3-3).

- [ ] `cells.py`: `_valid_functor_slot` (`:100-108`) → `isinstance(s, str) or s is
      TUPLE_TAG`; `_cell_shape` (`:111-131`) → NO deref: `x[0]` inspected raw
      (`type(x) is tuple and len(x) >= 1` unchanged); `make_cell` (`:133-161`) →
      Var functor now raises the TypeError (update message + docstring);
      `is_cell`/`cell_functor` docstrings lose the bound-Var-functor story; the
      module docstring's BRIDGE-ENTRY RULING and KNOWN AMBIGUITY blocks rewritten:
      the ambiguity ("a plain user tuple `("hello", 1)` is cell-shaped") is now the
      DISCIPLINE (§1: every runtime tuple is a cell; the residual untagged shapes —
      dict/set pairs — are Phase 4's, note them).
- [ ] `_helpers.py` `_cell_functor` (`:314-326`): no deref; compound iff
      `type(term) is tuple and term and type(term[0]) is str`. The Var-functor
      cell's funnel answers (arity via `_arity`, etc.) disappear — a slot-0-Var
      tuple now falls through to the pre-cell accessors like any plain tuple.
      Update the `:290-310` comment block; `functor_arity`'s Phase-2 paragraph
      trimmed to the new rule.
- [ ] Inversions (grep `test_funnel_accessors.py` + `test_tagged_terms.py` +
      `tests/test_cells*.py` for `Var` slot-0 pins — the "review fix finding #1"
      bound-Var recognition tests and `make_cell` Var-acceptance tests): each
      inverted citing §1b's deprecation; ledger. The pinned known-ambiguity test
      (`test_known_ambiguity_plain_str_tuple_pinned_by_running_assertions`) is
      re-worded to pin the discipline, same assertions.
- [ ] `tabling.py` uses `is_cell` only for interning (`:43`, `:346`) — behavior
      unchanged for str/TUPLE_TAG cells; add one regression test that a ground
      cell answer still tables + a Var-functor tuple no longer reaches
      `intern_cell` (it is not a cell).
- [ ] Full suite: name-diff == ledger. This removed a deref from every recognition
      on the hot path — note any bench movement in the ledger. Commit.

### Task 6: `-implicit_functors` per-module OWA flag (R7)

- [ ] `cells.py`: `IMPLICIT_FUNCTORS_FLAG = "__clausal_implicit_functors__"` with a
      docstring modeled on the deleted TAGGED_TERMS_FLAG's (module-namespace
      assignment, survives the `.pyc` path).
- [ ] `term_rewriting.py`: `_handle_implicit_functors_directive` — marker directive,
      bare and `()` forms, no arguments (copy the deleted tagged_terms handler's
      Assign-emitting shape verbatim; its docstring documents R7: advisory
      signatures, construction checking default-ON, kwargs still need a signature);
      dispatch line + unknown-directive message updated.
- [ ] `terms_to_ast.py` Site A: when the name does NOT resolve to a data functor
      (unknown name, or arity exceeds a known signature — decide: OWA means ANY
      arity for ANY functor, including one with a different declared arity; §1
      says "any arity/functor constructs a cell", so yes, signatures are advisory
      wholesale) AND `lowering_globals()` carries `IMPLICIT_FUNCTORS_FLAG`, emit
      `cell_literal_ast(base_name, arg_exprs)` for keyword-free constructions.
      Keyword construction of an unknown functor: compile-time error naming the
      functor and saying a signature is required for keyword placement. PREDICATE
      references (name resolves to a class WITH clauses) keep class/goal emission
      even under OWA — a goal is not data.
- [ ] Tests (`TestImplicitFunctors`, new fixture pair): flagged module constructs
      `wibble(1, 2)` with no declaration → `("wibble", 1, 2)` round-trips through
      a clause; declared `point/2` built at arity 3 under the flag → `("point",
      1, 2, 3)` (advisory); the SAME source without the flag → today's errors
      (pin both `NameError`-path and over-arity paths); `-strict_atoms`
      orthogonality: a bare ATOM in the flagged module still needs declaration
      (the flag opens functor construction, not atom vocabulary); directive arg
      rejection.
- [ ] Full suite: name-diff == ledger (additive feature; expected empty delta).
      Commit.

### Task 7: cells in the writer / display surfaces

Post-flip every user-facing answer is a cell; `term_str` currently drops to
`repr(t)` → `('point', 1, 2)`. Unacceptable as the default REPL/error rendering.

- [ ] `terms.py term_str` (`:2363`): before the generic fallback (and before any
      `isinstance(t, tuple)` could shadow it — there is none today, it falls to
      `repr`), add: str-functor cell → `functor(arg1, arg2)` using `_locale_name`
      + the existing mangled-atom demangle treatment on the functor (a `-hide`
      atom as functor renders `m.name(...)` — reuse the `:2382-2390` str-branch
      logic, WITHOUT quoting); `TUPLE_TAG` cell → `(e1, e2)` with brackets through
      `_c(...)` like the list branch; `(TUPLE_TAG,)` → `()`. Recurse with
      `_bd + 1`.
- [ ] `term_pformat` (`:2474+`): mirror both branches (find its per-shape dispatch
      and add cells beside the Compound case).
- [ ] `clausal/reflection.py` (reified renderer + `op_node/3` world): grep its
      term-shape dispatch for `is_term_instance`/`Compound` cases and add the cell
      case beside them, same functor/args decomposition via the `_helpers` funnel
      (which is already cell-aware) rather than a third shape test if the code
      already funnels — verify which style the file uses before editing.
- [ ] Tests: `term_str(("point", 1, 2)) == "point(1, 2)"` and equals the class-era
      rendering byte-for-byte (parity with an old recorded string, styled OFF);
      nested cells; tuple-data cell renders as a plain tuple display; hidden-atom
      functor renders the human form; `term_pformat` smoke test; renderer
      round-trip test in the reflection suite.
- [ ] Sweep: grep tests for hardcoded `('point'` -style EXPECTED strings in
      display/diagnostic assertions that now change shape (ledger any inversions).
- [ ] Full suite: name-diff == ledger. Commit.

### Task 8: predicate_builtins pool split (parked P3-1 todo, scheduled with P3-2)

`todo/pythonic-ast-names-leak-into-strict-atom-namespace-2026-09-04.md`, fix
direction 1 (the architectural one): `import_hook.py` seeds `simple_ast.__all__`
class objects into the same process-wide `predicate_builtins` dict that serves as
the §1b/R2 global atom pool, so `Add`/`Call`/`Match`… resolve as declared atoms in
strict modules with zero declarations.

- [ ] `import_hook.py`: split into `runtime_builtins` (compilation-support names
      every generated module needs: `simple_ast.__all__` classes,
      `INJECTED_RUNTIME_BUILTINS`, `$`-helpers) and `predicate_builtins` (the
      global atom/functor pool only). Module-exec seeding
      (`module_dict.update(...)`) applies BOTH (generated code still needs the
      runtime names); the STRICTNESS check consults only the pool.
- [ ] `compiler_v2.py` `_process_bare_atom_refs`/`_process_declarations`: their
      `predicate_builtins` reads keep working against the pool-only dict; the
      "already resolved" path must now REJECT a name whose binding came from
      `runtime_builtins` (identity check against that dict's entry — the same
      shape discipline `_locally_declared_names` used in P3-1 Task 7).
- [ ] Tests: the todo's own repro (`-module(pool_leak_probe, [Chk(X)])` with
      `X == Add`) now raises the strict-atoms diagnostic; a module that DECLARES
      `Add` as an atom still compiles and unifies globally; both load orders
      (extend `tests/test_strict_atoms_default.py::TestDeclarednessIsPerModuleNotProcessWide`'s
      pattern); generated-code regression: an existing fixture module using
      f-strings/arith (which exercises `simple_ast` names in GENERATED code) still
      loads.
- [ ] Move the todo to `todo/done/` with a resolution note. Full suite: name-diff
      == ledger (expected: empty delta beyond the new tests). Commit.

### Task 9: whole-suite reconciliation + perf gate

- [ ] Final full-suite name-diff vs the Task 0 baseline == the ledger's accumulated
      expected-inversions EXACTLY, reproduced on two consecutive runs; every line
      cites its ruling (R5-R9/§1b/§4).
- [ ] Straggler sweep (grep, worktree-wide): `tagged_terms|TAGGED_TERMS` (0 hits
      outside this plan + historical docs), `cell_functor_for_name(.*scope`,
      `-tagged_terms` in fixtures/docs, `_charlist_to_str_or_none`,
      `own-module|own module` in terms_to_ast/head_match comments. Scryer-corpus
      reader + toklex suites untouched-green.
- [ ] Interleaved perf A/B (branch base vs head), `bench_struct_tabling` +
      `bench_fib`: hard gate >3% regression on any metric = FAIL; expectation is a
      WIN (Phase-2 walker-heavy B/A = 0.561) — record actual numbers in the
      ledger; if the win does NOT materialize, investigate before merge (the flip
      is the phase's economic justification), but a flat result blocks nothing.
- [ ] Whole-branch review (top-tier model, PROBE instructions + adversarial ledger
      spot-checks per process discipline), fix loop until clean.

### Task 10: close-out

- [ ] Spec (`tagged-tuple-term-representation.md`): STATUS note under §1/§1b —
      cells unconditional, R5-R9 recorded, slot-0 domain narrowed, OWA directive
      shipped, indexing landed; §3.1's "slot 0 becomes the index key" marked DONE;
      §6 hazard 2 (dict/set pairs) re-affirmed as Phase 4.
- [ ] `phase3-decomposition-and-p31-atom-pivot.md`: P3-2 outline section replaced
      by a pointer to this plan + DONE status; P3-3 outline untouched.
- [ ] Directive/user docs: `-tagged_terms` mentions removed; `-implicit_functors`
      + the cell representation documented where `-strict_atoms`/`-implicit_atoms`
      are.
- [ ] Memory updates: `tagged-tuple-term-design-parked` (P3-2 DONE, commits, P3-3
      next), new/updated status entries for the OWA flag and R8 semantics change.
- [ ] Hand-off doc for P3-3 (state relocation + qualified goals) with this
      branch's recon crown jewels: whatever Tasks 3/4 learned about lift/bucket
      structure, the `is_data_functor` single-gate location, cell-goal boundary
      notes (head_key/assertz/call-N explicitly deferred here).
- [ ] Merge per `superpowers:finishing-a-development-branch` after the EMPTY-or-
      fully-reconciled gate; `build_ext --inplace` in the clone root after merge.

## Explicitly OUT of scope (P3-3 / Phase 4 boundaries)

- Cell GOALS: `call/N` over cells, `assertz` of cell-headed clauses
  (`database.head_key` keeps raising for tuples), qualified `(":", m, G)` goals,
  `solve(module=)` — all P3-3 (R4 detail ratified there).
- Predicate-state relocation, class removal, specialization minting — P3-3.
- Dict/set pair tagging `(tuple, k, v)` — Phase 4; do NOT migrate them.
- Reader-surface migration (quoted atoms, double-quote chars) — user-owned parser
  phase (R3).
- `TermProxy` seam + `packages/` migration — Phase 5; NOTE the parked
  Python-seam design (`implementation_plans/python-seam-classes-as-functors.md`,
  classes-as-functors + dispatch-entry instance conversion) supersedes §5a as the
  intended seam answer — own plan, timing user-decided.

## Self-review notes (checked before presenting)

- Every handoff workstream maps to a task: dual-site unconditional emission (T2),
  head-dispatch reachability (T3), slot-0 indexing (T4), cross-module exchange
  (R5/T2), `_valid_functor_slot` narrowing (T5), OWA flag (T6), kwarg placement +
  backfill (T1+T2), data-functor class fate (R6/T2), flag deletion (T2), parity
  fixtures as anchors (T2), display (T7, found in recon: `term_str` falls to
  `repr`), pool-leak todo (T8), indexing todo (R8/T4).
- Type consistency: `is_data_functor` (instance side) defined once (T2);
  `functor_signature_for` defined T1, consumed T1/T2/T3;
  `_lift_clause_at_pos(clause, pos, globals_=None)` signature consistent T3;
  index key shape `(functor, arity)` consistent with existing Compound/class
  branches (T4).
- Known risk carried deliberately: T2's mid-branch window (cells unindexed until
  T4, heads unlifted until T3) is answer-preserving — the parity suite is the
  witness; if it reds mid-branch, the flip itself is wrong, not the sequencing.
