# Engine lane handoff — 2026-09-20 (b), P2 Task 4 sweep: 142 → 46 NEW

Branch `feat/predmeta-p2-head-cells-2026-09-19` in **/workspace/clausal**.
Still nothing of this branch on main. Main was `bd774c46` at both ends of
this session's gate.

Continues `SESSION-HANDOFF-2026-09-20-engine-lane-task4.md` (commit 7699f5bb).
Everything that handoff says about METHOD, ROOMS and the `-rfE` trap still
holds and is not repeated here.

## THE NUMBER — gated against MAIN, both arms in a faithful room

    142 -> 46 NEW failures vs main.  96 fixed, and ZERO NEW introduced.

    base (main bd774c46)  147 failed / 16709 passed / 50 skipped
    cand (b08b275c)       192 failed / 16672 passed / 50 skipped
    NEW 46   GONE 1   extracted counts == the summary lines, both arms

**The GONE is noise and was checked, not assumed.**
`test_class_C17_perf_memory.py::test_F026_multi_star_splits_bounded_for_moderate_input`
fails in the BASE full run and passes on the branch — but it passes 3/3 in
isolation in BOTH rooms, so it is a load-sensitive perf test, not something
this branch fixed. No base test regressed.

**The set of NEW failures is a strict SUBSET of the 142 this session started
with** — that is the check worth making, not the count: nothing I touched
introduced a failure that was not already there.

Six batches, `e0bb5eaf` `91d791ba` `cc2b09ba` `71a231a7` `ad05bc62` `b08b275c`.
Rooms reused from the previous session: `…/823f67d2…/scratchpad/{kwwt,mainnow}`,
both faithful (12 `.so`, venv symlink, clean). **C is identical main↔branch**,
so no rebuild-and-swap was needed anywhere in this session.

## WHAT THE SIX BATCHES DID

1. **`phrase/2,3` resolve a cell nonterminal** (22 tests). The operator ruled:
   follow the call/N precedent. Made db-receiving exactly as
   `_make_call_goal_factory` is — straight into `_DB_BUILTINS`, `_db_optional`.
2. **The module a test HELPER cannot carry** (18). `solve` refuses to guess;
   these reached it through `_solutions`/`_values`/`_answers`/`once`, one frame
   past what batch 3's AST sweep matches.
3. **A cell is DRIVEN, never iterated** (7 + 12 more in batch 6). The silent one.
4. **Class-layer test pins migrate to cells** (29). All pins, no defects.
5. **`time_goal` + the benchmarks** (8). See the two findings below.
6. **The rest of the iterated cells** (12).

## THREE FINDINGS THAT OUTLIVE THIS BRANCH

**The benchmarks were measuring nothing.** All four workloads in
`benchmarks/workloads.py` drove a predicate with `for _ in <mod>.<pred>(...)`,
so since the constructor flip they iterated the cell's SLOTS: `bench_nqueens`
returned **3** — the arity — not 92. Any perf comparison run on this branch
before `ad05bc62` measured the cost of building one tuple. Now 92 / 610 / sorts
/ 50.

**A bug that is already on MAIN, not a P2 consequence.** Every db-dependent
builtin used in ARGUMENT position raises `'BuiltinPredicate' object is not
callable` — `time_goal(listing(append))` does it on `bd774c46` today. A name in
a compiled template stands for two things, the DISPATCH and the term
CONSTRUCTOR; the stateless path binds the `_BUILTIN_CLASSES` entry, which is
callable and does both, while a db-dependent builtin binds the adapter, which
is the only thing carrying the database. `BuiltinPredicate.__call__` now
constructs through the same class the stateless path would have bound.
**Moving any builtin into `_DB_BUILTINS` used to break it in argument
position** — that is what made this surface, and it is worth knowing before
Task 5/6 move more of them.

**The dormant sites are real and this sweep found three.** `tests/fmt/
test_arrows.py` (iterated a cell, but only formatting was asserted) and
`tests/test_global_atoms_default.py:376`
(`assert list(consumer.priv_imp_use(Var())) != []` — a cell is a non-empty
list, so the assertion could not fail whatever the predicate did). Driving
them properly is what proves they were passing for the wrong reason.

## THE SWEEP TOOLS (in this session's scratchpad, worth re-deriving)

* `sweep_iter3.py` — iterated cells. **Sweeping on the SHAPE alone is useless**:
  764 hits, drowned in `.items()`/`.values()`/`.splitlines()`. Discriminate by
  DATA FLOW — the names bound to a `.clausal`-backed module. Track BOTH
  bindings: an assignment from a loader AND `import <clausal module> as <name>`
  (the benchmarks are the second kind, and a fixed list of loader names missed
  `_load_fixture` — match the loader SHAPE instead).
  **Two false positives it cannot tell apart on shape, both correct as they
  are:** `mod.solve(goal)` is `Module.solve`, a real method; `clpfd.label(...)`,
  `O.label_or(...)` and `http_mod._post_3(...)` are Python generators in Python
  modules. Only a `.clausal`-backed receiver makes an iterated call a cell.
* `thread_module.py` — threads `module=<receiver>` into a goal-driving helper,
  deriving the receiver at the CALL SITE and REPORTING when it is not derivable.
  It never guesses; a helper that guessed would be the inference `solve` just
  stopped doing.

## INSTRUMENTS THAT FAILED OPEN IN THIS SESSION — four, all mine

Add to the running count. Every one of them read as SUCCESS.

1. `tail -12` on a pytest summary — I read a truncated FAILED list as "these
   tests are fixed" and reported progress that had not happened. **Compare
   SETS, and print the size of the set.**
2. `grep -c` for an import, with an alternation whose second branch matched ANY
   import from the module — said three files already imported `solve` when none
   did. **Replaced with an AST check that asks for the bound NAME.**
3. zsh glob: `grep -rn --include=*.py` unquoted — zsh expands it, grep never
   sees the flag, and the structural count read **0** instead of 79/76.
4. A renamed test left a stale id in the driver list; pytest exited **4**
   (usage error) having run nothing, and the extraction read "0 remaining".
   **Gate on pytest's own exit code, never on the extraction alone.**

## WHAT IS LEFT — 46, and the structural exit

Remaining clusters (regenerate, do not trust these numbers):
`test_tagged_terms` 7, `test_term_rewriting` 4,
`fixtures/docs/keyword_preds_examples.clausal` 4,
`test_low_level_db_mutation_sync` 3, `test_functor_construction_declared_term` 3,
`test_functor_arity_conflict` 3, then a long tail of 1s and 2s.
Shapes seen in their tracebacks: `TypeError: tuple() takes no keyword
arguments` (a `type(x)(**kwargs)` reconstruction), `must be called with a
dataclass type or instance` (`dataclasses.fields` on a cell), and
`'tuple' object has no attribute '<field>'` (the ordinary decomposer).

**The structural exit is NOT the failure count** (unchanged from the previous
handoff, and still the thing to finish): `is_term_instance(` **79** +
`term_field_names(` **76** in `clausal/` outside `predicate.py`. Both fell by
exactly one this session — the `phrase` pair. A dormant site passes today and
breaks the first time something reaches it; this session found three that were
doing exactly that.

Then Task 5 (17 C `PredicateMeta_type` arms) and Task 6 (17 `instances=True`),
which are what block step C of the head flip. **Read the `BuiltinPredicate`
finding above before Task 5/6.**
