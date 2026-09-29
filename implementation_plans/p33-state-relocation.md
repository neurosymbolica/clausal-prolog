# P3-3 — State Relocation + Qualified Goals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The per-module `Database` becomes the single authoritative home for predicate
state (clauses, dispatch, signature, lock, dynamics, provenance, tabling home) behind one
mutation gate and one invalidation point; cells become valid GOALS (`call/N`, dynamic
`assertz`, qualified `(":", module, Goal)`, `solve(module=)`); specialization stops
minting classes; reflection migrates to `(module, name, arity)`.

**Architecture:** Introduce a per-`(functor, arity)` `PredRow` record owned by
`Database`; invert the sync direction so `PredicateMeta` class attributes become
read-throughs onto the row (preserving the frozen zero-arg `_get_dispatch` duck type and
the `$disp_` bake-in as a row read); route all four known mutation channels through row
methods with per-write provenance; then teach the goal surface cells — `_term_to_goal`,
`head_key`, `call/N`, the query compiler, and the R4 qualified form — resolving modules
by name through the chain `_tabled_entry_for_goal` already uses. The dispatch seam gains
a per-row `backend` field and a chooser hook (stencil-seam ruling 2026-09-05): one
invalidation point, backend-pluggable, no adapter layer.

**Tech Stack:** Python; C only if measurement says so (user ruling 2026-09-05: allowed
where sensible); pytest; existing bench harnesses.

**Spec:** `implementation_plans/tagged-tuple-term-representation.md` §1/§1a/§1b (STATUS
blocks record what P3-1/P3-2 shipped); scope authority:
`implementation_plans/p33-state-relocation-handoff.md` (its recon crown-jewels section
is binding context for every task) + the P3-3 outline in
`implementation_plans/phase3-decomposition-and-p31-atom-pivot.md`. Anchors verified
2026-09-05 at clone main `e124754b`.

## PROPOSED RULINGS — need user sign-off before EXECUTION starts

(R1–R9 in force; R1-revised ratified 2026-09-05. Numbering continues.)

- **R10 (R4-detail — qualified-goal mechanism; REVISED per user 2026-09-05: single
  module registry).** In `(":", Module, Goal)` and `solve(goal, module=...)`:
  `Module` is an **atom (str) naming the module by its full dotted name, keying
  `sys.modules` directly** — `(":", "m1.m2", G)` is the idiomatic form. Resolution:
  `sys.modules[dotted]` → `__clausal_module__` attr → `Module` wrap. NO
  caller-module-dict step for the new forms (the user's ruling: two
  possibly-conflicting module dicts is the same disease as two clause stores;
  `sys.modules` is the one registry — `_clausal_test_*` modules live there too, so
  test loading is covered; a local alias that is not a real module name fails
  loudly, use the dotted name). The Python API additionally accepts a live `Module`
  or Python module object wherever it does today. An UNQUALIFIED cell goal resolves
  against the CALLING module's Database (replacing `_infer_module`'s class-walking,
  which cells made impossible). Resolution failure raises
  `existence_error(procedure, f/N)` naming the designator — never silent, never a
  NameError. Nested qualification `(":", m1, (":", m2, G))` is LEGAL and peels
  ISO-style (innermost wins — qualification stacking, as in SWI/SICStus; modules are
  flat, ISO 13211-2 being effectively unadopted; the hierarchy lives in the dotted
  name). `call/N` over a cell goal follows the same rules; a qualified cell is an
  ordinary cell with functor `":"` and arity 2. LEGACY NOTE: the pre-existing
  dotted-`Call` qualified path (`_tabled_entry_for_goal`'s caller-dict walk,
  solve.py:781-889, pinned by existing tests) keeps its behavior in P3-3; the new
  resolver is single-source from day one; convergence of the legacy path is a
  ledgered follow-up, not this phase's churn.
- **R11 (cell-headed `assertz`/`asserta`/`retract` — restoring the ISO dynamic-code
  idiom under the shipped representation).** Framing, per the user's question
  2026-09-05: this neither exposes an internal form nor removes one — post-P3-2 the
  cell IS the public term representation, and every dynamically CONSTRUCTED term
  (`=..`, `functor/3`+`arg/3`, `copy_term` output, data-functor construction, Python
  tuples) is a cell. P3-2 deliberately made `assertz` REFUSE cell heads
  (`_reject_cell_head`, correct `permission_error` diagnostic) because clause-head
  machinery wasn't cell-aware — which breaks the classic ISO idiom "build a term
  with `=..`, assert it". R11 closes exactly that: a cell whose functor names a
  predicate **declared dynamic** in the target module asserts fine (equivalent to
  the written form); static → the existing
  `permission_error(modify, static_procedure, f/N)`; undeclared functor →
  `existence_error(procedure, f/N)`. Literally-written `assertz(edge(1, 2))` in a
  module where `edge` is a dynamic predicate is UNCHANGED (predicate references
  compile as class/goal forms today and already work). No implicit dynamic
  auto-creation (current policy; revisit only under future ISO `unknown`-flag work).

## Global Constraints

- CLONE ONLY (`/workspace/clausal-bug-fix`); worktree per SDD
  (`git worktree add .claude/worktrees/p33-state-reloc -b feat/p33-state-reloc` from
  clone HEAD, NOT origin); `build_ext --inplace` in the worktree before the baseline;
  `/workspace/clausal/venv/bin/python` FROM the worktree;
  `--continue-on-collection-errors`; verify each run executed before trusting a diff.
  KNOWN worktree artifact: `tests/fmt/test_corpus.py` self-skips under `.claude/` paths
  (2 corpus tests fail, ~1570 fewer collected) — the baseline captured in-worktree
  carries this; final comparisons vs clone-root numbers must account for it (P3-2/R1
  precedent).
- NEVER `git add -A`; NEVER `git stash` (shared stack; standing ban with prior
  violation logged); FOREGROUND ONLY for all suite runs in every dispatch; explicit
  staging; commit trailers (Co-Authored-By + Claude-Session) on every commit.
- `_get_dispatch` DUCK TYPE FROZEN (~22 out-of-tree implementors): the zero-/one-arg
  call signature and semantics must not change; only OUR `PredicateMeta._get_dispatch`
  IMPLEMENTATION may change (to read the row). Any task drifting into changing the
  protocol: STOP.
- `<harness-library>` is frozen — off limits. Dict/set pairs stay plain 2-tuples
  (Phase 4). The functor-signature registry
  (`__clausal_functor_signatures__`, read via `functor_signature_for`) stays the single
  source of truth for DATA-functor shape — nothing in this plan may fork it.
- Dispatch-plan 4-tuples `(pos, idx_dict, default_fn, deep_gate)` must survive every
  restructuring of closure building (handoff crown-jewel 3); dropping the 4th element
  is a correctness or perf regression.
- Any NEW name seeded into every module namespace (a `$row_`-style key, a Database
  singleton) is DISTRUSTED by strict-atoms by default (`STRICTNESS_EXEMPT_RUNTIME_NAMES`,
  import_hook.py:333) — add exemptions deliberately with a justification line, and
  expect the loud test failure, not silent breakage.
- Full-suite gates compare failure-NAME sets vs the Task 0 baseline; this phase is
  mostly representation-internal — inversions are expected ONLY where R10/R11 rule new
  semantics (cell-goal surfaces) and where class-state pins become row pins; every
  inversion ledgered with a ruling citation, per-task gate = diff == ledger.
- Perf gate: interleaved A/B (branch base vs head) on `bench_struct_tabling` +
  `bench_fib`; >3% regression on any metric fails. Dispatch is THE hot path this phase
  touches — Task 2 and Task 4 carry their own spot A/B in addition to Task 9's formal
  gate. Bench processes assert `'p33-state-reloc' in clausal.__file__` first (70x-wrong
  precedent).
- C changes allowed where they make sense (user ruling 2026-09-05) — measured need, own
  scoped task, line-level review, never casually.
- Reviews PROBE, never trust; inversion ledgers spot-checked adversarially; the
  `callable_` alias-mismatch incident is the cautionary tale — probes must assert
  registration/identity before comparing behaviors.

## File Structure

```
clausal/logic/database.py                PredRow; authoritative store; mutation gate;
                                         single invalidation point; provenance per-write;
                                         mirror blocks deleted; _pred_cls_for deleted
clausal/logic/predicate.py               PredicateMeta state attrs → read-through
                                         properties onto the row; _assertz/_asserta/
                                         _retract delegate; _get_dispatch reads row;
                                         make_predicate registers a row
clausal/logic/compiler_v2.py             steps 3c/4/5 become row transactions;
                                         _predicate_functor_names consults the db;
                                         listing surface → (module, name, arity)
clausal/logic/compiler/predicate.py      compile install writes the row; dispatch-closure
                                         building keeps 4-tuple plans; $cells injection
                                         consolidated into INJECTED_RUNTIME_BUILTINS
clausal/logic/compiler/globals_env.py    $disp_ bake-in captures from the row (locked
                                         rows only — the staleness-safety invariant)
clausal/logic/solve.py                   _term_to_goal cell branch; _infer_module retired
                                         for cells; _goal_cache_key/_templatize learn
                                         cells + (":") form; solve(module=) resolution
clausal/logic/tabling.py + solve.py      _tabled_entry_for_goal learns cell + (":") goals
clausal/logic/builtins/higher_order.py   call/N accepts cells (resolves via calling db)
clausal/logic/builtins/database_ops.py   _reject_cell_head → R11 permission logic;
                                         cell-head assertz/asserta/retract for dynamics
clausal/logic/database.py head_key       cell branch: ("f", a, b) → ("f", 2)
clausal/logic/specialization.py          make_predicate/make_atom call sites (:277,
                                         :1313, :1671 + the 4th grep hit) → row
                                         registration; make_atom → plain str
clausal/reflection.py, clausal/modules/  (module, name, arity) lookups
  reflection.py, clausal/logic/builtins/inspection.py
tests/ (new + inversions)                row semantics, gate provenance, cell goals,
                                         qualified goals, spec-minting, reflection
```

**Interfaces produced (single source of truth; later tasks consume verbatim):**
- `Database.row(functor: str, arity: int, create: bool = False) -> PredRow | None`
  (Task 1). `PredRow` fields: `clauses: list[Clause]`, `dispatch_fn: Callable | None`,
  `lazy_recompile: Callable | None`, `backend: str` (default `"python"`),
  `signature: tuple[str, ...] | None`, `locked: bool`, `dynamic: bool`,
  `source: tuple[str, str] | None`, `writes: list[WriteStamp]` (provenance).
- `PredRow.invalidate()` — THE one invalidation point (Task 1; consumed everywhere).
- `Database.mutate(functor, arity, author: str) -> _RowTxn` context manager — THE one
  mutation gate (Task 3): checks lock/permission once, stamps provenance per-write.
- `resolve_module(designator, calling_module) -> Module` in solve.py (Task 6) — the R10
  chain, shared by solve/call/tabling.
- `BACKEND_CHOOSER` hook: `Database.set_backend_chooser(fn: Callable[[PredRow], str])`
  (Task 4) — default returns `"python"`; the stencil seam.

---

### Task 0: worktree + baseline + anchor re-verification

- [ ] Worktree from clone HEAD (`e124754b` or later); EnterWorktree; build_ext; fresh
      full-suite baseline (failure-NAME set → workspace; expect the worktree-artifact
      count ≈144 incl. the 2 corpus-path names; two runs if anomalous).
- [ ] Anchor sweep (HOLDS/MOVED/MISSING, file:line, to workspace):
      `PredicateMeta` state block predicate.py:637-658; mutators :740-771;
      `_get_dispatch` :800-811; database.py `_pred_cls_for` :72, mirror blocks
      :93-160, `register_signature` :166, `set_dispatch/get_dispatch` :191-230,
      `add_clause` :345-366, `head_key` (grep — post-P3-2 near :517-541 with the cell
      TypeError); solve.py `_term_to_goal` :170, `_goal_cache_key` :254,
      `_templatize_query_goal` :277, `_infer_module` :473, `solve` :598, tabled entry
      :742/:781; globals_env `_disp_key` :436, `_maybe_cache_dispatch` :553-569;
      goal_shallow :83, goal_trampoline :469; specialization make_predicate :277/:1313/
      :1671 (+ enumerate the 4th `make_predicate|make_atom` hit); higher_order
      call_goal :22-47; database_ops `_reject_cell_head`; import_hook
      `STRICTNESS_EXEMPT_RUNTIME_NAMES` :333. MISSING anchor = BLOCKED, report.
- [ ] Start the inversion ledger (P3-2 format).

### Task 1: PredRow + authoritative store (additive; no behavior change)

**Files:** Modify `clausal/logic/database.py`; Test `tests/test_predrow.py` (new).

- [ ] TDD: `PredRow` dataclass with the Interfaces fields; `Database.row(f, a,
      create=)`; rows BACK the existing dicts (`self._clauses[key]` becomes a view of
      `row.clauses` — same list object; `self._dispatch[key]`/`_lazy_recompile`/
      `_signatures` re-pointed to row fields via thin dict-compat shims or direct
      migration of the internal reads — implementer picks the smaller diff, but the
      OLD public methods keep byte-identical behavior this task).
- [ ] `PredRow.invalidate()`: clears `dispatch_fn` (leaves `lazy_recompile`), and is
      the ONLY place allowed to do so going forward (enforced by convention this task,
      by the gate in Task 3).
- [ ] `WriteStamp = namedtuple("WriteStamp", "author kind detail")`; `row.writes`
      append-only, capped (keep last 32 — diagnostics, not history).
- [ ] Tests: row identity (`db.row("f",2) is db.row("f",2)`), create semantics, view
      coherence (mutating via legacy `db.assertz` shows in `row.clauses` and vice
      versa), invalidate clears dispatch only.
- [ ] Gate: covering set + full suite EMPTY vs baseline. Commit.

### Task 2: THE INVERSION — class becomes read-through; mirrors die

**Files:** Modify `clausal/logic/predicate.py`, `clausal/logic/database.py`,
`clausal/logic/compiler_v2.py`, `clausal/logic/compiler/predicate.py`;
Test `tests/test_predrow.py`, inversions per ledger.

- [ ] `make_predicate(name, fields)` gains an optional `db`/owner argument; when a
      class is bound into a module (compiler_v2 minting, `-dynamic` stamping, R6b
      `name/arity` exports), it is LINKED to its row: `cls._row = db.row(name, arity,
      create=True)`. A class minted with no db (bare `make_predicate` in Python, the
      out-of-tree pattern) gets a private detached `PredRow` so the duck type never
      breaks — document this as the compatibility mode.
- [ ] `PredicateMeta` state attrs become properties reading the row: `_clauses` →
      `cls._row.clauses` (SAME list object — append-sites keep working), `_dispatch_fn`
      get/set → row field (setter allowed this task, gated in Task 3), `_signature`,
      `_locked`, `_dynamic_arities` (derives from `row.dynamic` + the existing set
      semantics — verify its three consumers accept the derivation), `_clauses_source`
      → `row.source`. `_get_dispatch` body: read `row.dispatch_fn`, lazy-recompile via
      `row.lazy_recompile`, arity check unchanged — signature untouched.
- [ ] database.py: DELETE the three mirror blocks (assertz :102-105, asserta :121-124,
      retract :146-151) and `_pred_cls_for` (:72-86) — the arity-blind lookup dies
      (identity todo instance 3 becomes unrepresentable: there is no second store to
      miss). `db.assertz` now: append to `row.clauses` (the same list the class
      reads), `row.invalidate()`, table-abolish as today.
- [ ] compiler_v2 steps 4/5 + `compile_predicate_*`'s install: write through the row
      (`row.clauses[:] = ...`, `row.dispatch_fn = fn` via the class property or row
      directly — ONE spelling, grep-enforced). `_predicate_functor_names` consults
      `db.row(...)`-backed truth where it consulted class state — add the sync test the
      handoff demands (a divergence flips goal/data emission silently: pin one case
      each way).
- [ ] `$disp_` bake-in unchanged this task (it reads `obj._dispatch_fn`, now a
      property — verify the capture still fires for locked rows; Task 4 moves it).
- [ ] Expected inversions: any test pinning `cls._clauses is not db._clauses[key]`
      (dual-store pins), `_pred_cls_for` behavior pins, `_clauses_source`
      load-attribution pins (provenance improves in Task 3 — only shape pins invert
      here). Each ledgered.
- [ ] Spot A/B: `bench_struct_tabling` interleaved vs branch base — property reads on
      the dispatch path must be ≤3%; if property overhead shows, cache the row object
      in closures/`__slots__` locals (measure, don't guess; C help is available by
      ruling if Python can't make it flat).
- [ ] Full suite: diff == ledger. Commit (2-3 commits fine: properties / mirror
      deletion / compiler install).

### Task 3: the mutation gate + per-write provenance (closes both parked todos)

**Files:** Modify `clausal/logic/database.py`, `clausal/logic/predicate.py`,
`clausal/logic/compiler_v2.py`, `clausal/logic/import_hook.py` (deferred-load writes);
Test `tests/test_mutation_gate.py` (new); Delete-to-done: the two todos.

- [ ] `Database.mutate(functor, arity, author)` context manager returning the row in a
      transaction: entry checks — locked rows refuse non-compiler authors with the
      existing `permission_error` text; the aliased-import clobber scenario (todo
      table row 2: dispatch replaced while clauses guarded) becomes impossible because
      `dispatch_fn` writes outside a txn RAISE (`RuntimeError` naming the channel) —
      the property setter from Task 2 now requires an open txn.
- [ ] All four channels route through it: compiler_v2 step-4 clause write + step-5
      dispatch install (author = canonical source path, per todo instance 1 —
      source-path keyed, NOT module name); import_hook's two deferred paths;
      `PredicateMeta._assertz/_asserta/_retract` (author = "runtime-assert:<module>");
      `db.assertz/asserta/retract`. `assertz` provenance now per-write (`row.writes`
      stamped) — the todo's "attributed to the loading module" defect gets a test.
- [ ] The step-3c guard (`_clauses[:]` clobber refusal) reimplements ON the gate:
      one policy — "may this author write this row" — consulted by every channel;
      delete the channel-local guards it replaces. The alias scenarios from the
      identity todo (dotted import name, `_clausal_test_*` dual-name, alias(f, G))
      become gate test cases — all three pinned.
- [ ] Acceptance (from the todo, verbatim): each of the four channels attempted from a
      non-owner load → refused with the same diagnostic; owner writes stamped;
      `assertz` records its own author.
- [ ] Full suite: diff == ledger (expected: the clobber-refusal diagnostics may
      reword — ledger them). Commit.

### Task 4: bake-in from rows + the backend seam (stencil-seam ruling lands here)

**Files:** Modify `clausal/logic/compiler/globals_env.py`,
`clausal/logic/compiler/predicate.py`, `clausal/logic/database.py`;
Test `tests/test_backend_seam.py` (new).

- [ ] `_maybe_cache_dispatch` (globals_env:553-569): reads `row = db.row(name, arity)`;
      captures `row.dispatch_fn` iff `row.locked` and non-None (same arity guard,
      same rationale comment — cite it). The staleness invariant gets its own test:
      only locked rows are ever baked, and `row.invalidate()` on an UNLOCKED row can
      never orphan a baked reference (assert no `$disp_` key exists for any unlocked
      row after a representative compile).
- [ ] `row.backend: str` + `Database.set_backend_chooser(fn)`; the compile-install
      path (compiler/predicate.py) consults the chooser before installing:
      `backend = chooser(row)`; `"python"` (default) installs exactly as today; any
      other value looks up a registered installer (`Database.register_backend(name,
      installer)`) — none registered in-tree; a one-page docstring on `set_backend_
      chooser` states the stencil-v2 contract (one invalidation point =
      `row.invalidate()`; per-predicate choice = this hook; cite
      `implementation_plans/stencil-v2-scoping-memo.md`).
- [ ] Consolidate `$cells` injection (crown-jewel 2's suggestion): move the two
      duplicated pool entries (compiler/predicate.py:837-839, :1657-1659) into
      `INJECTED_RUNTIME_BUILTINS` — and add the required
      `STRICTNESS_EXEMPT_RUNTIME_NAMES` entry ONLY if the strict-atoms probe test
      demands it (`$`-prefixed names are unspellable as atoms; verify, don't assume —
      the loud failure is the design).
- [ ] Fold-in (handoff): wire the `is_term_instance` half of the deep-gate
      (todo/first-arg-index-partially-ground-instance-keys-into-bucket) — the key
      branch gains the same `deep_gate` condition the cell branch got in P3-2 fix
      round 2, now that closure building is being touched; move todo → done with the
      repro as the test. Preserve 4-tuple plans throughout (regression: the P3-2
      driven-bucket tests must stay green untouched).
- [ ] Cheap-pass check (handoff): `todo/owa-unknown-functor-head-args-never-indexed` —
      assess while in the closure code; fix if ≤ ~20 lines, else leave the todo with a
      dated note.
- [ ] Spot A/B on `bench_struct_tabling` (bake-in path touched). Full suite: diff ==
      ledger. Commit.

### Task 5: cells as goals — the core surfaces (R11)

**Files:** Modify `clausal/logic/solve.py`, `clausal/logic/database.py` (`head_key`),
`clausal/logic/builtins/database_ops.py`, `clausal/logic/builtins/higher_order.py`;
Test `tests/test_cell_goals.py` (new).

- [ ] `head_key` cell branch (before the TypeError): `type(head) is tuple and head and
      type(head[0]) is str` → `(head[0], len(head) - 1)` (the consolidated shape
      discipline — reuse `cells._cell_shape`, do not re-spell). A `TUPLE_TAG` or
      Var-slot-0 tuple keeps the existing TypeError (data, not a predicate head).
- [ ] `_term_to_goal` cell branch: `("f", a, b)` → `AstCall(LoadName("f"), [a, b])`;
      the qualified form `(":", M, G)` recurses on `G` after `resolve_module` (Task 6
      provides it — this task lands the branch behind a stub raising
      `existence_error` for the qualified form, ledgered, so Task 5 and 6 are
      independently gateable).
- [ ] R11 in `database_ops`: `_reject_cell_head` becomes `_check_cell_head_permission`:
      dynamic target (row.dynamic for that arity) → proceed (normalize the cell to the
      Call-node clause shape the existing path builds — reuse
      `_normalize_fact_clause`'s machinery); static → existing permission_error
      verbatim; unknown → `existence_error(procedure, f/N)`. `retract` with a cell
      pattern follows the same gate.
- [ ] `call/N` cells (higher_order): in `_call_goal_n` and the `call/N` family, before
      the callable/`_get_dispatch` guard: a compound CELL goal resolves
      `db.get_dispatch(cell[0], len(cell)-1 + extra_n)` against the CALLING module's
      db (threaded how the builtins already receive db — verify via `_registry`; if
      db is not in scope there, route through the goal-lowering seam instead and
      document which). A bare-str atom goal of arity 0+extras resolves the same way.
      Silent-fail for non-cell non-callables is UNCHANGED (the translator session's
      pinned §4.2 contract — their 15 pins must stay green at the final canonical
      sync; note in ledger).
- [ ] `_goal_cache_key`/`_templatize_query_goal`: cells key structurally (they are
      already hashable tuples — verify the existing `_structural_key` walk handles
      slot-0 correctly and Vars in slots; add the cell case if it falls to
      `_Uncacheable`).
- [ ] Control-construct functors in cell-goal position (`","`, `";"`, `"->"`,
      `"\\+"` — ISO's conjunction-as-term is `','(A, B)` = `(",", A, B)` under
      cells): DEFERRED this phase with a clear diagnostic
      (`type_error(callable_control_construct_unsupported, ...)` or similar naming
      the functor and pointing at the adaptor's compile-time forms), pinned by a
      test, ledgered for the ISO-surface phase. The adaptor surface never produces
      them (conjunctions compile to `And` nodes); only runtime-built terms can
      reach this today.
- [ ] Tests (all driven, assert answers): solve with a cell goal (ground + var-carrying);
      call/1..3 over cells incl. extra args; assertz cell into dynamic → queryable via
      both cell and Call-node goals; static/unknown error classes pinned verbatim;
      cache-key: two structurally equal cell goals share compiled code (instrument
      `_query_cache` size).
- [ ] Full suite: diff == ledger. Commit.

### Task 6: R10 — qualified goals + module resolution

**Files:** Modify `clausal/logic/solve.py` (resolve_module, solve(module=), the Task-5
stub), tabling entry (`_tabled_entry_for_goal`), `clausal/logic/builtins/higher_order.py`
(qualified cells in call/N); Test `tests/test_qualified_goals.py` (new).

- [ ] `resolve_module(designator, calling_module)` implementing the REVISED R10 chain:
      `sys.modules[dotted]` → `__clausal_module__` → `Module` wrap; str/Module/
      py-module accepted; anything else or a miss → `existence_error` with the
      designator repr'd. Do NOT re-point `_tabled_entry_for_goal`'s legacy
      caller-dict walk (R10's legacy note — it stays pinned as-is); instead ADD the
      new resolver as the path for cell/`(":")` goals, and file the convergence
      follow-up as a ledgered todo at close-out.
- [ ] `solve(goal, module=...)`: accepts str designator per R10 (today it takes
      Module/py-module — keep both); unqualified cell goal + no module= → calling
      module (the module solve() is already invoked with; where solve is called
      module-less from Python with a cell goal → existence_error naming the gap, NOT
      `_infer_module` guessing — `_infer_module` keeps serving legacy class-instance
      goals only, with a docstring note that cells never reach it).
- [ ] `(":", M, G)`: in `_term_to_goal` (replace Task 5's stub) and in
      `_tabled_entry_for_goal` (a qualified CELL goal reaches the entry lookup —
      resolve M, consult the EXPORTING module's db, same as the dotted-Call path);
      nesting `(":", m1, (":", m2, G))` → innermost wins (ISO `m1:m2:G` semantics);
      M non-str/unresolvable → existence_error with the designator repr'd.
- [ ] call/N over `(":", M, G)`: resolve then dispatch in the exporting db.
- [ ] Tests: qualified cell goal cross-module (exporter's clauses answer, importer's
      same-spelling predicate does NOT — the module-locality pin); solve(module="name")
      with str; unresolvable module → existence_error; nested qualification; tabled
      predicate via qualified cell goal (table lands in exporter's homes — assert via
      table introspection); parity: qualified cell answers == the equivalent dotted
      Call-node answers on the same fixtures.
- [ ] Full suite: diff == ledger. Commit.

### Task 7: specialization stops minting

**Files:** Modify `clausal/logic/specialization.py` (:277, :1313, :1671 + the 4th
site from Task 0's sweep); Test existing specialization suites + additions.

- [ ] Each `make_predicate(new_name, fields)` site: register a row in the DEFINING
      module's db (`db.row(new_name, arity, create=True)` + signature) and install
      compiled dispatch through the Task-3 gate (author = "specialization"); the
      returned handle for downstream code is the row-linked class ONLY where a caller
      genuinely needs the class API — grep each site's consumers; where they only
      need name+dispatch, pass those. `make_atom` callers → the interned str (atoms
      are strs; if the 4th site is make_atom, this is a one-liner).
- [ ] Generated-goal references inside specialized clause bodies resolve via the same
      db rows (verify the compile of unfolded clauses reaches `$disp_`/row dispatch —
      an existing specialization fixture must show the specialized predicate calling
      another specialized one).
- [ ] Expected inversions: pins on specialized-class attributes (`__module__`,
      class-identity assertions) → row/name pins; ledger each.
- [ ] Full suite: diff == ledger. Commit.

### Task 8: reflection/listing/inspection migrate to (module, name, arity)

**Files:** Modify `clausal/reflection.py`, `clausal/modules/reflection.py`,
`clausal/logic/builtins/inspection.py`, `clausal/logic/compiler_v2.py` (listing);
Test their suites + `tests/test_listing.py`.

- [ ] Grep each file for class-keyed predicate lookups (`module_dict.get(functor)`,
      `isinstance(x, PredicateMeta)` used as "is a predicate", `._clauses` direct
      reads) → replace with `db.row(name, arity)` reads through a small shared helper
      (`predicate_rows(module) -> Iterable[(name, arity, PredRow)]` in database.py).
      `listing/1` output must be byte-identical for unchanged fixtures (pin one golden
      before touching).
- [ ] Handoff fold-in: extend the inspection-builtin probes with
      registration-asserting checks (todo/registration-asserting-probes...) for the
      seven names while their surfaces are open; todo → done.
- [ ] Full suite: diff == ledger. Commit.

### Task 9: reconciliation + perf gate

- [ ] Final name-diff vs Task 0 baseline == accumulated ledger EXACTLY, two consecutive
      runs; every line cites R10/R11/a task ruling.
- [ ] Straggler sweep: `_pred_cls_for` (0), `_dispatch_fn = ` outside
      database.py/predicate.py txn paths (0 live), `_clauses_source` writers (row only),
      `_infer_module` cell reachability (comment-pinned), `make_predicate(` in
      specialization (0), mirror-comment residue in database.py (0).
- [ ] Interleaved perf A/B both benches + the Task 2/4 spot benches re-run at head;
      >3% fails. Toklex/scryer-reader suites untouched-green.
- [ ] Whole-branch final review (top-tier model; probe instructions; point it at the
      ledger's deferred/parked lines for triage).

### Task 10: close-out

- [ ] Spec STATUS note under §1b (P3-3 shipped: Database authoritative, gate,
      backend seam, cell goals, R10/R11 recorded); decomposition doc P3-3 section →
      DONE pointer; both closed todos → todo/done with resolution notes; memory
      updates (tagged-tuple program status; parked-follow-ups list).
- [ ] Phase 4 handoff doc (dict/set pair tagging + atom/string audit) with this
      branch's crown jewels: PredRow/gate/backend-seam interfaces verbatim, the
      cell-goal surfaces map, R10 resolution chain location, what stencil-v2 consumes.
- [ ] Canonical-sync note: the next sync repeats the Option-B coordination protocol
      (translator session hold; barrier scan; their 788-test battery + 15 pins as
      acceptance bars).
- [ ] Merge per finishing-a-development-branch after the gate; build_ext in clone root
      post-merge.

## Explicitly OUT of scope

- Class REMOVAL for predicates (classes remain as read-through shells; deletion is
  Phase 5 seam work), `packages/` migration, provenance-package repair (parked todo).
- Dict/set pair tagging (Phase 4); reader-surface migration (user-owned, R3).
- Stencil-v2 itself (its plan consumes Task 4's seam; separate plan, user-timed).
- The Kleene/WFS tabling internals beyond re-homing table keys on rows (tabling
  algorithm untouched).

## Self-review notes

- Handoff coverage: authoritative store (T1-2), read-through + `$disp_` equivalent
  direct-read (T2, T4), single mutation gate + both todos (T3), backend-pluggable seam
  + one invalidation point + per-predicate hook (T4), cell goals + `call/N` + R11
  boundary closure of P3-2's three refusal points (T5), R4/R10 qualified form +
  `solve(module=)` + tabled dotted-walk verification (T6), specialization minting stop
  incl. `make_atom` (T7), reflection `(module, name, arity)` (T8), deep-gate 4-tuple
  preservation (T2/T4 + global constraint), `_predicate_functor_names` sync test (T2),
  STRICTNESS_EXEMPT expectation (global + T4), `$cells` consolidation (T4), folded
  todos (T4 ×2 fold-ins, T8 probes).
- Type consistency: `PredRow`/`Database.row`/`mutate`/`invalidate`/
  `set_backend_chooser`/`resolve_module` defined once in Interfaces, consumed by name
  in T2-T8.
- Known risk carried deliberately: T2's property-read overhead on the dispatch hot
  path — spot A/B in-task with the C lever available by ruling; and the
  detached-row compatibility mode for out-of-tree `make_predicate` callers (pinned by
  a duck-type test in T2).
