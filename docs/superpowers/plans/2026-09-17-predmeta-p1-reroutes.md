# PredicateMeta P1 Reroutes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the 14 actionable category-A sites off the class-routing path: membership and state reads go to the Database row, index plans get a row home, and the four arity-blind index-hint lookups become arity-exact.

**Architecture:** Three row-local fields on `PredRow` with read-through properties on `PredicateMeta` (the `_signature` shape) give index plans a row home with zero behaviour change. Then each site's `isinstance(module_dict.get(f), PredicateMeta)` becomes `db.row(f, arity) is not None` and its state reads become row fields. The four index-hint sites get `db` threaded in explicitly and read `db.row(fname, arity)`.

**Tech Stack:** Python 3.13, pytest, the engine's `Database`/`PredRow`, `PredicateMeta` metaclass properties.

**Spec:** `docs/superpowers/specs/2026-09-17-predmeta-p1-reroutes-design.md` (this plan argues from it; read it first) over `docs/superpowers/specs/2026-09-14-retire-predicatemeta-design.md` §6 P1 and `tools/predmeta_census/FINDINGS.md` + `P1_SITES.tsv`.

## Global Constraints

- Worktree `/workspace/clausal-bug-fix/.claude/worktrees/iso-l3`, branch `feat/iso-l3-lowering-2026-09-14`. Run every command from there. `git branch --show-current` before every commit; stage explicit paths; never `git add -A`, never bare `git stash`.
- Python `/workspace/clausal/venv/bin/python`, run FROM the worktree; probes print `clausal.__file__` and assert the worktree prefix.
- THE RULE, verbatim from the census: `isinstance(module_dict.get(functor), PredicateMeta)` → `db.row(functor, arity) is not None`. NEVER `db.is_defined` (stricter, un-declares dynamic-but-empty predicates).
- The `db` is the one in scope at the site; with only a module dict in scope it is `module_dict["$module"].db`. NEVER a predicate's `_row.db` (a different Database for an imported name).
- A site that still needs the class after the membership test keeps it for that use and REPORTS it (spec §3). Never add a row→class accessor.
- `dynamic_arities` is a per-NAME set on the CLASS's own row (spec §2, "the wart"): the two `-dynamic` sites must reach that same row or keep the class for the write and say so.
- Do not touch any P4/Q/X4/NO row of `P1_SITES.tsv`; do not edit `clausal/terms.py`, `python_terms.py`, or `py/datetime.py`.
- No mention of any other repository's name anywhere. Commit trailer on every commit, both lines verbatim:

      Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
      Claude-Session: https://claude.ai/code/session_01G3Bi6ruQWgu7WHKrYWPTT9

---

## File map

| file | change |
|---|---|
| `clausal/logic/database.py` (`PredRow`) | + `index_plans`, `index_plans_joint`, `index_plans_hierarchical` fields |
| `clausal/logic/predicate.py` (`PredicateMeta`) | + three read-through properties with setters |
| `clausal/logic/compiler/goal_trampoline.py`, `clausal/logic/compiler/optimisations/call_site.py` | the 4 R! sites: `db` threaded, `db.row(fname, arity)` read |
| `clausal/logic/compiler/predicate.py` | only the call sites of the passes above, to pass `db` |
| `clausal/logic/compiler_v2.py` (276, 285, 851→892, 882→923, 234, 796→837, 1008→1049 — census line → worktree line) | 4 R, 2 S, 1 R-enum |
| `clausal/logic/builtins/database_ops.py` (275), `clausal/logic/compiler/globals_env.py` (165), `clausal/testing.py` (862) | 3 R |
| `tests/predmeta_p1/test_index_plans_row_home.py` (create) | Task 1 |
| `tests/predmeta_p1/test_arity_exact_index_hints.py` (create) | Task 2 |
| `tests/predmeta_p1/test_p1_sites_rerouted.py` (create) | Task 3 |

---

### Task 0: Baseline and the blind-spot list

**Files:** read only; outputs to `/home/node/.claude/jobs/af5b4bbe/tmp/p1-baseline.raw` and `p1-red-in-touched.txt`.

- [ ] **Step 1:** confirm tree: `git branch --show-current` → `feat/iso-l3-lowering-2026-09-14`; `git status --short | wc -l` → 0; record `git rev-parse --short HEAD`.
- [ ] **Step 2:** `rm -f /home/node/.claude/jobs/af5b4bbe/tmp/p1-baseline.raw; nohup /home/node/.claude/jobs/af5b4bbe/tmp/gate_iso_l3.sh /home/node/.claude/jobs/af5b4bbe/tmp/p1-baseline.raw >/dev/null 2>&1 &` then wait for `^EXIT=` (about 3 minutes). Print `TREE-SHA`/`IMPORTED`/`PLUGIN-OK`/`RUN-EXIT`, the FAILED count (non-zero, low hundreds) and the summary line.
- [ ] **Step 3:** enumerate already-red tests in the touched test files, with the positive control if the count is 0:

```bash
sed 's/\x1b\[[0-9;]*[mK]//g' /home/node/.claude/jobs/af5b4bbe/tmp/p1-baseline.raw \
 | grep -E '^(FAILED|ERROR) (tests/predmeta_p1/|tests/test_first_arg_index|tests/test_optimisations_call_site|tests/test_bucket_refs_ir_parallel|tests/test_deep_indexing|tests/test_database|tests/test_dynamic|tests/test_assert|tests/test_import|tests/test_testing|tests/test_specializ)' \
 | tee /home/node/.claude/jobs/af5b4bbe/tmp/p1-red-in-touched.txt; echo "red-in-touched: $(wc -l < /home/node/.claude/jobs/af5b4bbe/tmp/p1-red-in-touched.txt)"
sed 's/\x1b\[[0-9;]*[mK]//g' /home/node/.claude/jobs/af5b4bbe/tmp/p1-baseline.raw | grep -c '^FAILED tests/'   # positive control
```
Run each listed red test alone and write its one-line reason after its name.

- [ ] **Step 4:** run `/workspace/clausal/venv/bin/python tools/predmeta_census/check_p1.py` and record its three counts (it must pass on the untouched tree; it is the census's own consistency check and Task 3 re-runs it).

---

### Task 1: Index plans get a row home

**Files:** Modify `clausal/logic/database.py` (`PredRow` dataclass fields, after `dynamic_arities`), `clausal/logic/predicate.py` (`PredicateMeta`, next to the `_signature` property, ~line 1008). Create `tests/predmeta_p1/test_index_plans_row_home.py`.

**Interfaces:** Produces `PredRow.index_plans: dict`, `.index_plans_joint: dict`, `.index_plans_hierarchical: dict` (row-local, default `{}`), and `PredicateMeta._index_plans` / `_index_plans_joint` / `_index_plans_hierarchical` as properties reading/writing `(cls._row or cls._detached_row())`. Task 2 reads the row fields.

- [ ] **Step 1: failing tests**

```python
"""Index plans live on the Database ROW, not the class (P1, spec 2026-09-17 §2.1).

Until now `_index_plans` & co. were CLASS-ONLY state (census: "the class holds
state that the spec says it does not"). A row home is what lets a call site
find a predicate's plans by (functor, arity) without the class.
"""
from clausal import Var
from clausal.import_hook import _load_module
from clausal.logic.predicate import PredicateMeta


def _load(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"; p.write_text(src)
    return _load_module(name, str(p)).__dict__["$module"]


SRC = "".join(f"colour({i}, c{i})\n" for i in range(40))   # enough clauses to be indexed


def test_the_class_attribute_reads_through_to_the_row(tmp_path):
    mod = _load(tmp_path, "ip_a", SRC)
    cls = mod.module_dict["colour"]
    row = mod.db.row("colour", 2)
    assert row is not None
    assert cls._index_plans is row.index_plans
    assert cls._index_plans_joint is row.index_plans_joint
    assert cls._index_plans_hierarchical is row.index_plans_hierarchical


def test_the_compiler_wrote_plans_onto_the_row(tmp_path):
    # the writer in compiler/predicate.py is untouched; its assignment now lands on the row
    mod = _load(tmp_path, "ip_b", SRC)
    row = mod.db.row("colour", 2)
    assert isinstance(row.index_plans, dict) and row.index_plans, "first-arg index expected"


def test_assignment_on_the_class_lands_on_the_row(tmp_path):
    mod = _load(tmp_path, "ip_c", SRC)
    cls = mod.module_dict["colour"]
    cls._index_plans = {"marker": {}}
    assert mod.db.row("colour", 2).index_plans == {"marker": {}}


def test_a_detached_class_still_has_plans_through_its_private_row():
    class Loose(metaclass=PredicateMeta):
        pass
    assert Loose._index_plans == {}
    Loose._index_plans = {0: {}}
    assert Loose._index_plans == {0: {}}


def test_a_fresh_row_has_empty_plans(tmp_path):
    mod = _load(tmp_path, "ip_d", "-dynamic(empty/1)\n")
    row = mod.db.row("empty", 1)
    assert row is not None and row.index_plans == {} and row.index_plans_joint == {} \
        and row.index_plans_hierarchical == {}
```
If `class Loose(metaclass=PredicateMeta): pass` is not how a detached class is minted in this tree, find the spelling in `tests/` (grep `metaclass=PredicateMeta`) and use it; if the `-dynamic` module fails to load without a body, use `"-dynamic(empty/1)\nseed(1)\n"`.

- [ ] **Step 2:** run → expect `AttributeError: 'PredRow' object has no attribute 'index_plans'` (or `_index_plans`).
- [ ] **Step 3: implement.** In `PredRow`, after `dynamic_arities`:

```python
    # Index plans (arg_index): the call-site bucket functions the compiler
    # exposes per argument position. Row-LOCAL (P1, 2026-09-17): they were
    # class-only state, the one thing an index-hint pass could not find by
    # (functor, arity). ``repr=False``: they hold closures.
    index_plans: dict = dataclasses.field(default_factory=dict, repr=False, compare=False)
    index_plans_joint: dict = dataclasses.field(default_factory=dict, repr=False, compare=False)
    index_plans_hierarchical: dict = dataclasses.field(default_factory=dict, repr=False, compare=False)
```
In `PredicateMeta`, beside `_signature`, three property pairs of exactly this shape:
```python
    @property
    def _index_plans(cls) -> dict:
        return (cls._row or cls._detached_row()).index_plans

    @_index_plans.setter
    def _index_plans(cls, value: dict) -> None:
        (cls._row or cls._detached_row()).index_plans = value
```
(and `_index_plans_joint`, `_index_plans_hierarchical`). If `PredicateMeta` declares `__slots__` or a class-body default named `_index_plans`, remove that default — the property must be the only definition.
- [ ] **Step 4:** run the new file + `tests/test_first_arg_index.py tests/test_optimisations_call_site.py tests/test_bucket_refs_ir_parallel.py tests/test_deep_indexing.py tests/predmeta_p1/` → all pass (modulo Task 0's red list, same reasons).
- [ ] **Step 5:** commit: "predicate rows: index plans get a row home; the class attributes read through".

---

### Task 2: The four arity-exact index-hint sites (R!)

**Files:** Modify `clausal/logic/compiler/goal_trampoline.py` (`_inject_bucket_refs_trampoline` ~line 149 and `analyse_ir_bucket_refs` ~line 265), `clausal/logic/compiler/optimisations/call_site.py` (`analyse` ~line 85, `apply` ~line 206), and their callers in `clausal/logic/compiler/predicate.py` (and any other caller: `git grep -n 'analyse_ir_bucket_refs\|_inject_bucket_refs_trampoline\|call_site.analyse\|call_site.apply\|\bapply(ir' -- clausal tests`). Create `tests/predmeta_p1/test_arity_exact_index_hints.py`.

**Interfaces:** Consumes `PredRow.locked`, `.index_plans`, `.index_plans_joint` (Task 1). Produces: each of the four functions takes a `db` (a `Database`, keyword `db=`), and resolves the callee as `row = db.row(fname, arity)` — `None` or `not row.locked` → skip, else plans from `row`. No `base_globals.get(fname)` for the callee remains in those four places.

- [ ] **Step 1:** read the four sites and every caller; note how `db` reaches `compile_predicate_trampoline` (it is a parameter) and thread it to the passes as `db=`. If a caller genuinely has no `Database` (grep the tests that build `base_globals` by hand), pass `db=None` and let the pass skip hints — and say so in the report, naming the caller.
- [ ] **Step 2: failing test**

```python
"""Index hints are ARITY-EXACT (P1, spec 2026-09-17 §2.3 — the R! sites).

Before: the two hint passes looked the callee up BY NAME in base_globals and
read the class's plans whatever the call's arity. After: `db.row(fname, arity)`.
"""
from clausal import Var
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import deref


def _load(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"; p.write_text(src)
    return _load_module(name, str(p)).__dict__["$module"]


TWO_ARITIES = (
    "".join(f"colour({i}, c{i})\n" for i in range(40))      # colour/2: indexed
    + "colour(0)\n"                                          # colour/1: one clause, unindexed
    + "pick2(X, Y) <- colour(X, Y)\n"
    + "pick1(X) <- colour(X)\n"
)


def test_each_arity_has_its_own_row_and_plans(tmp_path):
    mod = _load(tmp_path, "ax_a", TWO_ARITIES)
    r2, r1 = mod.db.row("colour", 2), mod.db.row("colour", 1)
    assert r2 is not None and r1 is not None and r2 is not r1
    assert r2.index_plans and not r1.index_plans


def test_a_call_at_the_unindexed_arity_still_answers(tmp_path):
    # the arity-1 call must not borrow arity-2's plans (it could not have used
    # them correctly: position 0's buckets are keyed on colour/2's first arg)
    mod = _load(tmp_path, "ax_b", TWO_ARITIES)
    x = Var()
    assert [deref(x) for _ in call("pick1", x, module=mod)] == [0]
    y = Var()
    assert sorted(deref(y) for _ in call("pick2", 3, y, module=mod)) == ["c3"]


def test_the_ordinary_load_path_STILL_produces_hints(tmp_path):
    # positive control for Task 2's db threading: if `db` were silently None
    # everywhere, every pass would skip and this would be empty
    mod = _load(tmp_path, "ax_c", TWO_ARITIES)
    from clausal.logic.compiler.optimisations import call_site
    # find the compiled IR-level evidence the pass leaves behind: adapt to
    # what `tests/test_optimisations_call_site.py` asserts (a CallSitePlan with
    # non-empty hints for pick2's body) — read that file and reuse its accessor.
    assert mod.db.row("colour", 2).index_plans
```
The third test's body is deliberately incomplete: read `tests/test_optimisations_call_site.py` for how a plan's hints are observed and assert non-empty hints for `pick2`; the row-plans assertion is the fallback minimum.

- [ ] **Step 3:** run → the arity tests may already pass (two rows exist); the point of the file is to PIN them, so confirm each assertion is exercised by adding a temporary `assert False` and seeing it fire, then remove it. The positive control must fail if you hard-code `db=None` (try it once, then restore).
- [ ] **Step 4: implement.** Each of the four sites becomes, in shape:

```python
            row = db.row(fname, arity) if db is not None else None
            if row is None or not row.locked:
                continue
            plans = row.index_plans          # was pred_obj._index_plans
```
and every later `pred_obj.` in the function reads `row.` (`_index_plans` → `index_plans`, `_index_plans_joint` → `index_plans_joint`). The `hasattr(pred_obj, "_index_plans")` guard is gone (a row always has the field). Remove `PredicateMeta` from the import list of a file that no longer references it.
- [ ] **Step 5:** run the new file + the four arg-index test files + `tests/predmeta_p1/` → all pass.
- [ ] **Step 6:** commit: "index hints: the callee is db.row(fname, arity), arity-exact, with db threaded to the passes".

---

### Task 3: The ten remaining sites (7 R, 2 S, 1 R-enum)

**Files:** Modify `clausal/logic/compiler_v2.py`, `clausal/logic/builtins/database_ops.py`, `clausal/logic/compiler/globals_env.py`, `clausal/testing.py`. Create `tests/predmeta_p1/test_p1_sites_rerouted.py`.

**Interfaces:** Consumes Task 1's row fields. Produces: none of the ten sites tests `PredicateMeta` for MEMBERSHIP any more; `tools/predmeta_census/check_p1.py` is UPDATED so its check 2 ("every row still points at a line containing PredicateMeta") accepts a rerouted row — add a disposition marker `R-done`/`S-done`/`R-enum-done` for the rows this task closes and teach `check_p1.py` that a `-done` row must NOT contain `isinstance(..., PredicateMeta)` at its snippet (the check flips direction for those rows).

The sites, by worktree line (census line in brackets), with the reroute each gets. Read the ENCLOSING FUNCTION of every one before editing it.

| site | disposition | reroute |
|---|---|---|
| `compiler/globals_env.py:165` `signature_for` | R | `row = self._db.row(functor, arity)` … `return row.signature if row else None` — `_GlobalsEnv` must know its `db`: if it only holds `_globals`, take `db` at construction (find its one constructor call) or read `self._globals["$module"].db` |
| `compiler_v2.py:234` [234] | S | `pred_cls` is passed on to `_load_gate` as a class: keep the LOOKUP, drop only the redundant `isinstance` (a non-class value in the module dict under a predicate name cannot occur post-FLIP; if it can, say why and leave it) |
| `compiler_v2.py:837` [796] `_redefinition_error` | S | `pred_cls` is already resolved by the caller; drop the `isinstance` half of the test, keep `origin is None` |
| `compiler_v2.py:276` [276] `-dynamic` stamp | R | THE WART (spec §2): the set lives on the class's own row. Reach it as `db.row(functor, a)` where `a` is the class's arity ONLY if that arity can be named without the class; otherwise keep the class for the write and reroute nothing here but REPORT it. Do not move the set. |
| `compiler_v2.py:285` [285] | R | `len(pred_cls._fields) == arity` → `db.row(functor, arity) is not None`; `_belongs_elsewhere(pred_cls, db)` still needs the class → keep the lookup for that call and REPORT |
| `compiler_v2.py:892` [851] | R | `term_field_names_of_class(cls)` + length check → `db.row(functor, arity) is not None` (that IS the arity-checked membership); if the field NAMES are used later, keep the class for that and report |
| `compiler_v2.py:923` [882] | R | same shape as 892: `is_pred = db.row(functor, arity) is not None` |
| `compiler_v2.py:1049` [1008] | R-enum | `sorted({f for (f, _a) in (*module_db._rows, *module_db._adopted)})` where `module_db = module_dict["$module"].db` (or the `db` in scope) |
| `builtins/database_ops.py:275` [275] | R | `named` is compared BY IDENTITY to `type(head)` to catch a redirected write. Reroute to rows: `named_row = db.row(functor, arity)`, `own_row = type(head)._row` (the class's row; `type(head)` is the head's OWN class and stays), compare `named_row is not own_row`. `db` = `module_dict["$module"].db`. Keep every other condition. |
| `testing.py:862` [862] | R | `declared = namespace.get(functor)` + `len(declared._fields) != arity` → `namespace["$module"].db.row(functor, arity) is None` → continue; keep the `else` branch's atom handling |

- [ ] **Step 1: failing tests** — one per site that has observable behaviour, driven through a loaded module. Minimum set:

```python
"""The P1 category-A sites route to the Database row (spec 2026-09-17 §2.2)."""
import pytest
from clausal import Var
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import deref


def _load(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"; p.write_text(src)
    return _load_module(name, str(p)).__dict__["$module"]


def test_signature_for_answers_from_the_row(tmp_path):
    from clausal.logic.compiler.globals_env import _GlobalsEnv   # adapt the name to the class at globals_env.py:~160
    mod = _load(tmp_path, "p1_a", "p(1, 2)\n")
    env = _GlobalsEnv(mod.module_dict)                             # adapt to its constructor
    assert env.signature_for("p", 2) == mod.db.row("p", 2).signature
    assert env.signature_for("p", 3) is None
    assert env.signature_for("nope", 2) is None


def test_a_dynamic_declaration_at_a_second_arity_keeps_the_size_two_set(tmp_path):
    # the wart: dynamic_arities is a per-NAME set on the class's own row
    mod = _load(tmp_path, "p1_b", "-dynamic(d/1)\n-dynamic(d/2)\nd(1)\n")
    cls = mod.module_dict["d"]
    assert cls._dynamic_arities == {1, 2}


def test_an_imported_predicate_passes_the_rerouted_membership_tests(tmp_path):
    (tmp_path / "exp_p1.clausal").write_text("-module(exp_p1, [p(X)])\np(1)\np(2)\n")
    _load_module("exp_p1", str(tmp_path / "exp_p1.clausal"))
    mod = _load(tmp_path, "imp_p1", "-import_from(exp_p1, [p])\nq(X) <- p(X)\n")
    x = Var()
    assert sorted(deref(x) for _ in call("q", x, module=mod)) == [1, 2]


def test_the_specialize_diagnostic_lists_rows_not_classes(tmp_path):
    with pytest.raises(RuntimeError) as exc:
        _load(tmp_path, "p1_c", "-specialize(nosuch_mi, [])\np(1)\n")    # adapt to the directive's real spelling at compiler_v2.py:~1040
    assert "p" in str(exc.value)


def test_assert_from_a_module_that_only_saw_the_term_does_not_redirect(tmp_path):
    # database_ops.py:275 — keep whatever tests/ already pins for this
    # (grep tests/ for 'redirect' near assertz); if a test exists, this one
    # only re-asserts it still passes; if none exists, write the two-module
    # case the docstring describes and assert the write lands on the OWN
    # module's predicate.
    pass  # replace with the real test before committing; a `pass` test is a defect
```
Adapt names to the tree (each `# adapt` comment). Every test must assert something; delete the last one only if an existing test already covers that site and name it in the report.

- [ ] **Step 2:** run → the signature/imported/dynamic tests may pass before the reroute (they pin equivalence); the `check_p1.py` update below must FAIL until the sites are rerouted — that is the RED.
- [ ] **Step 3:** implement the ten reroutes per the table; update `P1_SITES.tsv` dispositions to `R-done`/`S-done`/`R-enum-done` for the rows closed (keep `R` on any row you had to leave — and say why in the report); update `check_p1.py`: add the three `-done` values to `DISPOSITIONS`, and in check 2 require that a `-done` row's snippet line no longer contains `isinstance(` … `PredicateMeta)` while a non-done row still does. Run `check_p1.py` — it prints the size of each check; all three must be non-zero and pass. Run `check_p1.py --controls` once and confirm each check can go red.
- [ ] **Step 4:** run `tests/predmeta_p1/ tests/test_first_arg_index.py tests/test_optimisations_call_site.py tests/test_bucket_refs_ir_parallel.py tests/test_deep_indexing.py` plus every test file whose name contains `dynamic`, `assert`, `import`, `specializ`, `testing` under `tests/` → all pass modulo Task 0's red list.
- [ ] **Step 5:** commit in two: (a) the reroutes + tests: "P1: ten category-A sites route to the Database row"; (b) the census table + checker: "predmeta census: mark the rerouted rows done; the checker now guards the reroute".

---

### Task 4: Gate, review, handoff

- [ ] **Step 1:** full gate into `p1-candidate.raw`, `failure_diff.py p1-baseline.raw p1-candidate.raw` → NEW must be 0 (the F026 wall-clock test flips either way; anything else NEW is a regression). Re-run every test in `p1-red-in-touched.txt` alone and confirm the same reason.
- [ ] **Step 2:** `tests/test_funnel_lint.py` alone (nothing inserted in `terms.py`, but the allowlist has tripped on unrelated insertions before).
- [ ] **Step 3:** handoff note in `implementation_plans/SESSION-HANDOFF-2026-09-16-engine-lane-END.md` under the LANDED block: the range, NEW 0, which rows are `-done`, which R rows were LEFT and why (the class still needed after the test), and the line: "the harness lane asked for the 82-row answer diff because index hints are now arity-exact".
- [ ] **Step 4 (controller):** message the harness lane with the sha and the question; message harness-date-migration only if `py/datetime.py` or the seam moved (it did not).

## Self-review against the spec

§2.1 row home → Task 1; §2.2 membership + state reads → Task 3; §2.3 R! arity-exact + db threaded + positive control → Task 2; §2.4 R-enum → Task 3; §2 wart → Task 3 rows 276/285 + the size-two test; §3 report-don't-hide → Task 3 report contract + `-done` markers; §4 gate + harness question → Task 4; §5 out of scope → the table touches no P4/Q/X4/NO row.
