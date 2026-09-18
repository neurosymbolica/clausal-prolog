# PredicateMeta retirement, P2: terms in argument position are tuples — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every structural term in argument position is the functor-first tuple `('f', a, b)` the engine already unifies in C; no `PredicateMeta` INSTANCE is constructed or read anywhere in `clausal/` or `packages/`, and declared data functors live in one registry on the Database.

**Architecture:** Three moves, in order. (1) A declaration registry on the `Database` (`declare_functor(name, fields, kind)`, kind `data` | `predicate`) replaces the module-level functor-signature map, so "what fields does `f/2` have" and "is `f/2` a predicate here" are answered without a class. (2) The reader, compiler and seam stop constructing instances: a term is `make_cell(f, *args)`; positional field names come from the registry. (3) The instance READERS (81 `is_term_instance` + 82 `term_field_names` sites, 7 C functions, 7 package files) lose their instance arm, file by file, each file gated on its neighbours. Classes for PREDICATES stay until P4; classes for DATA functors stop being minted here.

**Tech Stack:** Python 3.13, the C extension `clausal/logic/variables/_variables.c` (rebuild with `setup.py build_ext --inplace` in a worktree, never on a tree a live process has imported), pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-retire-predicatemeta-design.md` (§3 replacement table, §4 module-level binding, §6 phases, §7 verification) and its §4 answer `implementation_plans/2026-09-14-retire-predicatemeta-section4-answer.md`. Rulings taken 2026-09-18 with the operator (this plan's premises):

* **R-P2-1** One declaration registry on the Database with a `data`/`predicate` kind. A fielded declaration starts as `data`; clauses, `-dynamic`, or a `-discontiguous`/`-table`/`-shallow` directive naming it make it `predicate`. `row()` answers only for predicates (the P4-prerequisite landing fb0106f3 already mints those rows); `signature_for` answers for both. The module-level `FUNCTOR_SIGNATURES_KEY` map is retired.
* **R-P2-2** `m.pred(X)` from Python is retired WITH the class (P4), not replaced by a proxy: the calling forms are `call("pred", X, module=m)` and `solve(("pred", X), module=m)`. P2 does not touch it; P2 must not add a new dependency on it.
* **R-P2-3** `-implicit_atoms` is deprecated this landing (warning), removed the next.
* **R-P2-4 (sequencing, option 2)** P2 runs BEFORE L3's rules/directives phases; L3 stays at facts and its harness (`tests/iso_l3/`) is one of P2's controls. L3's later phases are written against the tuple AST once.

## Global Constraints

* No `('x',)` 1-tuple is ever built: it is RESERVED (`cells.refuse_reserved_1tuple`). An atom is the `str`; a string is `('$chars', s)`.
* `_get_dispatch` is a frozen duck-typed protocol with out-of-tree implementors; it is NOT touched by P2.
* A predicate's CLASS still exists after P2 (P4 deletes it). P2 removes INSTANCES and DATA-functor classes only.
* Every site change is one of three rewrites (below, "The three rewrites"); anything else is reported, not improvised.
* Gate per task: the file's neighbour tests green; gate per landing: clean-base engine A/B NEW 0 / GONE 0 on DETACHED worktrees with the same extension set + positive controls, twin-parity, exporter goldens (`tests/test_clausal_to_prolog*`), `tests/iso`, `tests/rewrite`, `tests/iso_l3`; then the corpus ANSWER-SET axis (harness-batch-lane, 28 sealed scorers) before promotion. Report class count and the construct/unify benchmark (spec §7) before and after; they are exit criteria.
* `git add` explicit paths only; `git branch --show-current` before every commit; build in a same-sha worktree and copy-then-move extensions under live importers.

---

## The representation, stated once

| term | today | after P2 |
| --- | --- | --- |
| `point(1, 2)` (data functor declared `-private([point(X, Y)])`) | instance `point(arg_0=1, arg_1=2)` of a `PredicateMeta` class | the cell `('point', 1, 2)` |
| its field names | `type(t)._fields` | `db.signature_for('point', 2)` → `('x', 'y')` (registry) |
| "is `point/2` a predicate here?" | `isinstance(module_dict['point'], PredicateMeta)` | `db.declared_kind('point', 2) == 'predicate'` / `db.row(...)` |
| a clause head `p(X, Y)` at compile time | instance-shaped `head_key` via `type(head).__name__` | `compound_cell_shape(head)` → `('p', 2)` (already exists) |
| a predicate reached from Python | `m.p` (class) | unchanged in P2 (class stays until P4) |
| `functor/3`, `arg/3`, `=..`, `copy_term`, `is_ground`, indexing | instance arm + cell arm | cell arm only |

The existing helpers are the whole vocabulary: `cells.make_cell`, `is_cell`, `cell_functor`, `cell_args`, `cell_arity`, `compound_cell_shape`, `_cell_shape`. Do not add a second spelling.

## The three rewrites (every site is one of these)

1. **Constructor** — `SomeClass(arg_0=a, arg_1=b)` / `cls(*args)` → `make_cell(name, a, b)`.
2. **Decomposer** — `is_term_instance(t)` + `term_field_names(t)` + `getattr(t, f)` → `compound_cell_shape(t)` + `cell_args(t)`; field NAMES, when a site needs them (keyword calls, `P.key` sugar, diagnostics), → `db.signature_for(f, n)`; if no `db` is in scope the site is listed, not patched.
3. **Type test** — `is_term_instance(t)` asked as "is this a compound?" → `is_cell(t)` (or `compound_cell_shape(t)[0]`); asked as "is this a predicate?" → the Database (`row`/`declared_kind`). The P0 census labelled every site with which question it asks; re-read the site, do not trust the label blindly.

---

### Task 1: the census, refreshed and sized

**Files:**
- Create: `tools/predmeta_census/P2_SITES.tsv` (columns: file, line, qualname, kind ∈ {constructor, decomposer, typetest-compound, typetest-predicate, c-arm, package}, disposition, note)
- Create: `tools/predmeta_census/p2_census.py` (the walker: every `is_term_instance(`, `term_field_names(`, `make_predicate(`, `_make_functor_class_ast(`, `._fields`, `PredicateMeta_type` in `clausal/`, `packages/` excluding `build/`)

- [ ] **Step 1: write the walker** — regex + AST over the paths above; prints POPULATION SIZE then rows; asserts the population is non-empty.
- [ ] **Step 2: run it, commit the TSV with `disposition` blank** — expected rows ≈ 81 + 82 + 35 + 7 C + 7 package files; the numbers measured 2026-09-18 are the positive control.
- [ ] **Step 3: label `kind` by reading each site's enclosing function** (the P0 rule: a mislabelled site is a silent behaviour change). Commit.

Exit: every site has a kind; the count per kind is in the commit message.

### Task 2: the declaration registry (R-P2-1)

**Files:**
- Modify: `clausal/logic/database.py` (beside `register_signature` ~964, `signature_for` ~984, `row` ~578)
- Modify: `clausal/logic/compiler_v2.py::_process_directives` (~1022, the fb0106f3 shape)
- Modify: `clausal/templating/term_rewriting.py::_make_functor_signatures_update_ast` (~4456) — stop emitting the map; the items already carry `(name, fields)`
- Modify: `clausal/testing.py:897`, `clausal/logic/constants.py:255-262` (the two `FUNCTOR_SIGNATURES_KEY` readers → `db.signature_for`)
- Test: `tests/predmeta_p2/test_declaration_registry.py`

**Interfaces:**
- Produces: `Database.declare_functor(name: str, fields: tuple[str, ...], kind: str = "data") -> None`; `Database.declared_kind(name, arity) -> str | None`; `Database.signature_for(name, arity)` now answers for declared data functors too; `Database.promote_to_predicate(name, arity)` called by `mark_dynamic`, the three `mark_*` (for declared targets), and the first clause install.

- [ ] **Step 1: failing tests** — `-private([point(X, Y)])` alone: `declared_kind == "data"`, `row is None`, `signature_for == ("x", "y")`; add `-discontiguous(point/2)`: kind `predicate`, row exists; a clause: kind `predicate`; an undeclared name: `None`. Plus the existing `test_predrow::test_predicate_functor_names_says_data_and_the_database_agrees` and `tests/predmeta_p1/*` must stay green.
- [ ] **Step 2: implement** — one dict `_declared: dict[(name, arity), (fields, kind)]`; `_process_directives` writes declarations from `ModuleDeclItem`/`PrivateDeclItem` fielded entries first, then promotes on directives (replacing the fb0106f3 `db.row(..., create=True)` with `promote_to_predicate`, which mints the row).
- [ ] **Step 3: retire the module-level map** — `_make_functor_signatures_update_ast` emits nothing; the two readers go through the module's `db`. Run `tests/test_constants*.py`, `tests/test_testing*.py`, `tests/fixtures/docs`.
- [ ] **Step 4: commit** with explicit paths.

Exit: `grep -rn FUNCTOR_SIGNATURES_KEY clausal` is empty except `cells.py`'s definition (delete it too if nothing else reads it).

### Task 3: constructors emit cells

**Files:**
- Modify: `clausal/logic/compiler/terms_to_ast.py::term_to_ast_expr` (~615; the `is_term_instance`/class-call arm at ~99-101)
- Modify: `clausal/templating/term_rewriting.py::_make_functor_class_ast` (~4240): for a DATA functor emit nothing (no class); for a predicate keep the class (P4)
- Modify: `clausal/logic/python_terms.py::to_term` (~561) if it still builds instances for registered classes; `from_term` twin
- Modify: `clausal/logic/compiler/head_match.py` instance-head arm (~4 sites) → cells (the cell path exists from P3-3)
- Test: `tests/predmeta_p2/test_constructors_emit_cells.py`

- [ ] **Step 1: failing tests** — a `.clausal` module with `-private([point(X, Y)])` and `mk(P) <- (P is point(1, 2))`: `deref(P) == ('point', 1, 2)`; a head pattern `f(point(A, B)) <- ...` matches a cell; `to_term` of a Python tuple `('point', 1, 2)` is that cell; `functor(P, N, A)` answers `point/2`.
- [ ] **Step 2: implement, run the compiler neighbours** (`tests/test_compiler.py`, `tests/test_cell_goals.py`, `tests/test_atoms_as_str_stage2.py`, `tests/test_head_*.py`, `tests/fixtures/docs`).
- [ ] **Step 3: commit.**

Exit: no `PredicateMeta` INSTANCE is created for a data functor anywhere (positive control: a census hook counting `PredicateMeta.__call__` on a data class during the suite reads 0).

### Task 4: the decomposer sweep, by file

Order (readers by count, measured 2026-09-18): `builtins/_helpers.py` 14, `compiler/globals_env.py` 13, `database.py` 10, `compiler/list_dispatch.py` 9, `solve.py` 8, `compiler/arg_index.py` 8, `testing.py` 6, `specialization.py` 6, `compiler/tro.py` 6, `builtins/io.py` 6, `builtins/type_checks.py` 5, `builtins/inspection.py` 5, `repl.py` 4, `modules/reflection.py` 4, `predicate.py` 4, `coroutining.py` 4, `constraints.py` 4, `compiler/head_match.py` 4, `compiler/_vars.py` 4, `builtins/dcg.py` 4, `terms.py` 3, `compiler/terms_to_ast.py` 3, then the tail.

- [ ] For each file: apply rewrite 2 or 3 per the census kind; run that file's neighbour tests (the census row names them); commit per file with the census rows it closes in the message; update `disposition` in the TSV.
- [ ] Sites whose field NAMES are needed and no `db` is in scope: list them under `disposition = needs-db` and STOP the sweep on that file — the fix is plumbing `db`, not a global.
- [ ] `specialization.py`: the six reads are the MI class's clauses/fields; take `(db, functor, arity)` and read `db.clauses_for`/`signature_for` (R-P2 read 2026-09-18: annotations only, no identity dependence).

Exit: `is_term_instance(` / `term_field_names(` call sites in `clausal/` = 0 outside `predicate.py`'s definitions; the definitions stay until P4 with a deprecation docstring.

### Task 5: the C arms

**Files:** `clausal/logic/variables/_variables.c`: `c_is_term_instance`, `c_term_field_names`, `py_term_field_names`, `c_is_ground`, `c_copy_term`, `c_collect_vars`, `py_is_atom`, `py_register_predicate_meta` (17 `PredicateMeta_type` arms).

- [ ] **Step 1: twin-parity pins first** (`tests/test_python_fallbacks.py` shape): for a cell, `_is_ground`, `copy_term`, `collect_vars` agree between C and Python and never take an instance arm.
- [ ] **Step 2: delete the instance arms** (the cell arms already walk `PyTuple`); keep `py_register_predicate_meta` (predicates' classes still register until P4).
- [ ] **Step 3: rebuild in the worktree, twin-parity + `tests/test_c_*`, commit.**

### Task 6: the reflection vocabulary

`clausal/reflection.py:101-109` mints nine vocabulary classes (`Clause`, `Goal`, `Atom`, `Variable`, `Escape`, `FormatString`, `IfThenElse`, `ModuleDirective`, `PythonCode`) with `make_predicate`. These are the reified terms the rewriter (`clausal/rewrite`) matches from `.clausal` rules.

- [ ] Replace with cells: `Goal(name, args, kwargs)` → `('Goal', name, args, kwargs)`; the renderer (`_ClauseRenderer`) and reifier switch from attribute reads to `cell_args`; keyword constructors stay as thin functions so `Goal(name=..., args=...)` in tests keeps reading.
- [ ] Gate on `tests/test_reflection*.py`, `tests/rewrite`, `tests/fmt`.

Exit: `make_predicate(` callers in `clausal/` = the three in `specialization.py` (predicate classes, P4) only.

### Task 7: packages (7 source files, `build/` copies are regenerated)

- `packages/clausal-provenance/clausal/modules/provenance/engine.py` (instance reads at 66-112 → rewrites 2/3; the `_get_dispatch` registration goals are untouched),
- `packages/clausal-scipy/clausal/modules/py/scipy_stats.py` + its three tests (term-instance results → cells),
- the remaining two files per the census.

- [ ] Each package's own test suite green; commit per package.

### Task 8: R-P2-3, deprecate `-implicit_atoms`

- [ ] `_handle_implicit_atoms_directive` (~8047) warns once per file: "deprecated 2026-09-18; declare the names in -private/-module, or -hide them; removed in the next landing". The four engine test sources that use it are migrated to declarations; `docs/directives.md` and the 11 other docs mentioning it get the one-line note. Pin: the warning fires; a declared-only module does not.

### Task 9: gates, handoff, announcement

- [ ] Clean-base A/B: base = canonical main at P2's branch point (own build, 13 extensions), candidate = detached tip, positive controls (`deref(P) == ('point', 1, 2)`; census hook 0; `is_term_instance` grep 0). NEW 0 / GONE 0, skips identical.
- [ ] `tests/iso_l3`, `tests/iso`, `tests/rewrite`, exporter goldens, twin-parity: green.
- [ ] Spec §7 exit numbers in the handoff: class count before/after (`gc.get_objects()` filtered by `PredicateMeta` after loading the docs fixtures), construct/unify microbench before/after.
- [ ] corpus ANSWER-SET axis: ask harness-batch-lane to run the 28 sealed scorers on the frozen tip; landing waits for that, as the flip's did.
- [ ] Handoff `implementation_plans/SESSION-HANDOFF-<date>-engine-lane-p2.md`; announcement beside the atoms ones: what a downstream reader of a term must know (a data term is a tuple; field names come from `signature_for`; `m.pred` unchanged until P4).

## Not in P2 (so nobody folds it in)

* Goal position (P3): a goal is still lowered from `nodes.Call`; `call/N` and `solve/1` already take cells.
* Deleting the class, `make_predicate`, `py_register_predicate_meta`, `m.pred(X)` (P4, R-P2-2).
* L3 rules/directives (after P2, against the tuple AST, R-P2-4).
* `Compound` (144 constructions / 58 files): the design measured the tuple dominates it; retire it in P3 with goal position, not here.
