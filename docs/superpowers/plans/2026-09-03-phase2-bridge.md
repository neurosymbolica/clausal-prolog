# Phase 2: the dual-representation bridge — tagged cells behind an experimental flag

Spec: implementation_plans/tagged-tuple-term-representation.md (§1 design, §3c optimisations,
§Phases "Phase 2"). User un-parked Phase 2 ("go"). This stage is an EXPERIMENT: its
deliverables are (a) parity evidence that tagged-cell modules behave identically to class-term
modules, and (b) the three-way measurement (class / cells / cells+interning) on the
walker-heavy macro. It is NOT a shippable user feature — the flag is documented experimental.
CLONE ONLY.

Keystone context: Phase 0's walker fast path measured B/A 0.6509 (~1.54×) on
bench_struct_tabling; §3c predicts interning/sharing stack on the same path.

## Global Constraints

- Work ONLY in /workspace/clausal-bug-fix/.claude/worktrees/phase2-bridge (branch feat/phase2-bridge); all commands from there with /workspace/clausal/venv/bin/python.
- NEVER `git add -A`; NEVER `git stash` (three violations already logged this session; a fourth fails the task). Explicit paths. Commit trailer (two lines):
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01G7xiWqatWtL6zNQDc7nspk
- Full-suite runs: exactly `/workspace/clausal/venv/bin/python -m pytest tests/ -q --tb=no --continue-on-collection-errors`; failure-set NAME-diff vs baseline_failures.txt (worktree root) must be empty per task. `tests/test_funnel_lint.py` stays green.
- DEFAULT-PATH INVARIANT: with the flag off, every module compiles byte-identically to today. All bridge behavior is strictly additive and opt-in. No changes to `PredicateMeta`, the five walkers' class-term arms, `_get_dispatch`, <harness-library>, or any C file in this stage (cells ride the EXISTING C tuple branches — that is the design's point; if a C change ever seems needed, STOP and report BLOCKED).
- BRIDGE-ENTRY RULINGS (ledgered): a cell's slot 0 may be an interned str, the `tuple` type object, or an unbound Var — nothing else constructs; the str~char-list cons-rule interaction is DEFERRED to Phase 3 — Task 1 ships a guard test documenting the boundary instead.
- Cells are plain tuples: `("foo", a1, ..., an)` compound, `(tuple, e1, ..., en)` tuple-data. They already unify/walk/key through the existing C tuple branches — do not add representation machinery the engine already has.
- Interning (Task 4) applies ONLY to fully-ground cells (recursive groundness; a Var anywhere disqualifies — Var.__hash__ stays untouched this stage).

## Task 1: cell primitives + funnel awareness + boundary guard tests

Files: new `clausal/logic/cells.py`; `clausal/logic/builtins/_helpers.py`; `tests/test_cells.py` (new).

1. `clausal/logic/cells.py`: `TUPLE_TAG = tuple`; `make_cell(functor, *args)` (validates slot-0 ruling: str → intern via sys.intern, `tuple` type, or Var; else TypeError); `make_tuple_cell(*elems)`; `is_cell(x)` (tuple, len>=1, slot0 is str | tuple-type | Var); `cell_functor(c)`, `cell_args(c)` (slice), `cell_arity(c)`. Pure Python, no C.
2. Funnel awareness (additive branches ONLY; class-term paths byte-identical): `_functor_name`/`_arity`/`_nth_arg`/`_args_list`/`_is_compound`/`functor_arity` in `_helpers.py` recognize cells with str functors (a `(tuple, ...)` cell is NOT compound — it is tuple data; slot0-Var cells: `_functor_name` returns the Var, `_is_compound` True, `functor_arity` None). IMPORTANT: these branches must come AFTER the existing tuple-as-charlist/data handling cannot be broken — study `_args_list`'s existing list/str cons behavior first and place the cell branch so a plain user tuple like `(1, 2)` keeps today's behavior exactly (`is_cell` is False for it — slot0 is an int — that is the disambiguator during the bridge; document that a user tuple whose slot 0 happens to be a str IS ambiguous during the bridge and resolves as a cell ONLY inside flagged contexts — the funnel branches must therefore be gated on `is_cell` alone but every changed accessor gets a regression test with today's plain-tuple inputs).
3. Guard tests: (a) cons-rule boundary — a str-functor cell unified against a same-shape cell works; a str functor NEVER meets a char-list comparison through cell unification paths in this stage's corpus (document the Phase 3 deferral in the test docstring); (b) slot-0 ruling enforcement (make_cell rejects int/class/None functors); (c) unification via existing C branch: `unify(("f", X), ("f", 1))` binds X; `("f", 1)` vs `("g", 1)` fails; `(tuple, 1)` vs `("f",)` fails; slot0-Var higher-order bind `unify((F, 1), ("f", 1))` binds F="f".
TDD; focused + full suite, empty name-diff.

## Task 2: compiler — the `-tagged_terms` module flag (emission + head dispatch)

Files: `clausal/templating/term_rewriting.py` (directive parsing — study how `-strict_atoms`/`-implicit_atoms` flags are parsed and threaded), `clausal/logic/compiler/terms_to_ast.py`, `clausal/logic/compiler/head_match.py`, `clausal/logic/compiler/predicate.py` (only if threading the flag requires it), tests in `tests/test_tagged_terms.py` (new).

1. Directive: `-tagged_terms` recognized per-module, threaded to the compile context the way existing module flags are. Flag OFF → zero behavioral change (assert via a golden test: compile a fixture with and without the branch's code on a non-flagged module — emitted AST identical; simplest: unparse comparison on term_to_ast_expr outputs).
2. Data emission (flagged modules): saturated construction of a declared functor emits the CELL literal `("name", <args>)` (ast.Tuple with a Constant functor string) instead of `Cls._clausal_new(...)`. Partial/keyword construction: keep class emission even in flagged modules (cells have no Var-backfill; document). Atoms remain class atoms (Phase 3 does the atom pivot) — a 0-arity reference stays a class value.
3. Head dispatch (flagged modules): clause heads whose args are declared-functor compounds emit sequence-literal patterns — `case ("point", x, y)` — instead of MatchClass; non-cell-shaped head args unchanged. The `(tuple, ...)` tag in patterns uses the dotted `builtins.tuple` value pattern (NEVER bare `tuple` — capture pattern; NEVER `__builtins__` — dict in imported modules; the design doc §4 records both traps).
4. Mixed-boundary rule for this stage: a flagged module's predicates may be CALLED from anywhere (goal args are flattened — representation-neutral); but compound DATA crossing between flagged and unflagged modules is out of scope — the parity corpus (Task 3) uses self-contained fixtures. Document the limitation in the directive's docstring.
5. Tests: a small fixture pair (same source ± flag) → identical query answers via a representation normalizer (cell → (functor, args...) vs class term → (name, field values...) canonical tuples); dispatch tests (multi-clause flagged predicate discriminating on cell functors and arities); the golden flag-off test.
Focused + full suite, empty name-diff. THIS IS THE DESIGN-HEAVY TASK — if the flag threading or head_match integration requires restructuring beyond additive branches, report BLOCKED with the specifics rather than improvising.

## Task 3: parity corpus

Files: `tests/test_tagged_terms_parity.py` (new), corpus fixtures under `tests/fixtures/` (new `*_tagged.clausal` variants of 3-5 representative existing fixtures INCLUDING struct_tabling).

- Pick 3-5 fixtures spanning: recursion + compound answers (struct_tabling shape), multi-clause dispatch with compound heads, list/tuple data mixing, atoms as values. For each: a `-tagged_terms` variant (same logic, flag added; adjust only what the flag requires) + a parity test running an identical query set against both and comparing normalized answer sets.
- Also parity of FAILURE behavior: one query per fixture that must fail — fails on both.
- Run the corpus in both this worktree and (spot, one fixture) confirm timing same order of magnitude — no 10x cliffs (a cliff is reportable, not a failure).
Focused + full suite, empty name-diff.

## Task 4: selective ground-cell interning at the tabling freeze boundary + THE MEASUREMENT

Files: `clausal/logic/cells.py` (intern table + `intern_cell`), a MINIMAL hook where tabled answers are frozen — `clausal/logic/tabling.py` `_freeze_args_py` region — gated so it applies ONLY to cells (class terms and everything else untouched; find the least-invasive Python hook point; NO C changes — if the C freeze path bypasses the Python hook for cells, measure what is reachable and report the coverage honestly), `benchmarks/workloads.py` (`bench_struct_tabling_tagged(n, reps, intern=False)`), fixture `tests/fixtures/struct_tabling_tagged.seam` (from Task 3), tests.

1. `intern_cell(c)`: recursive — intern ground sub-cells bottom-up via a module-level dict (str functors already interned); non-ground (contains Var anywhere) returned unchanged. Hashability: ground cells are tuples of scalars/cells → hashable; guard with try/except TypeError → return unchanged.
2. Hook: at the freeze boundary, if the frozen value is a cell → `intern_cell`. Prove via test: two structurally-equal ground cell answers in a table are THE SAME object after interning.
3. THE MEASUREMENT (report-only): interleaved, same protocol as Stage A, all in THIS worktree (no cross-build): (A) `bench_struct_tabling` (class terms), (B) `bench_struct_tabling_tagged` intern=False, (C) intern=True. 5 rounds each, fresh subprocesses, n as Task 3's fixture supports (~1500 target). One profile per variant. Report medians/spreads/ratios B/A and C/B and C/A, walker/freeze share per variant, and an honest read: does the cell representation beat class+`_clausal_new`? Does interning add on top? Numbers straight, whatever they are — a null or negative result is decision-relevant and reportable.
Focused + full suite, empty name-diff. Commit code+fixture+bench; measurement report-only.
