# Fable Partition Audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a self-contained "audit library" — output scaffolding plus 12 ready-to-paste Fable prompts — so the user can launch each audit of the `clausal` package as its own interactive Fable session.

**Architecture:** This plan builds *artifacts the user launches*, not code that runs here. Task 1 creates the on-disk output tree, ledger/README templates, a pytest smoke harness, and a path-checker script. Task 2 writes the shared prompt preamble (rubric, required reading, method, output contract) once. Tasks 3–7 assemble the 12 self-contained prompt files (each = preamble + a subsystem-specific block) plus a launch runbook. Every prompt file is validated by the path-checker so it names only real files.

**Tech Stack:** Markdown (prompts, ledgers, todos), Python + pytest (smoke harness + path checker), the existing `clausal` repo layout and `todo/` convention.

## Global Constraints

- Deliverable is **findings + adversarial tests + queued todos only** — no production-code fixes are applied by any audit.
- Design contradictions/ambiguities are **first-class**: resolved in-session with the user (after checking `DESIGN-DECISIONS.md`) or logged `open`.
- Each audit runs as its **own interactive Fable session** — prompts may ask the user; they are not headless subagents.
- Required reading (every prompt, before code): an external, executed-against-Clausal cheat-sheet (not in this repo), the subsystem's docstrings + `docs/`, subsystem prior-art, and current `DESIGN-DECISIONS.md`.
- Standing contracts: `==` is arithmetic eq (not structural); a string **is** a list of 1-char strings; cut-free (no `!`, `->`, `*->`); unification is `is`; bare atoms are strings; builtins are PascalCase full words.
- pytest is run **per-file** only — `pytest tests/` OOM-SIGKILLs on this box.
- This box is a **3.13 GIL build**; free-threading claims can only be *executed* on the `.cpython-314t` build, else logged `unconfirmed — needs 3.14t`.
- Finding IDs are namespaced per subsystem: `A<NN>-F<NNN>` (findings), `A<NN>-D<NNN>` (design questions).
- Output roots: `docs/superpowers/audits/2026-07-05-fable-partition/`, `tests/audit_2026_07_05/`, `todo/audit-2026-07-05/`.
- Spec: `docs/superpowers/specs/2026-07-05-fable-partition-audit-design.md` (authoritative; this plan implements it).

---

## Subsystem index (the 11 audits + session 12)

| ID | Slug | Files |
|----|------|-------|
| A01 | term-layer | `clausal/terms.py`, `clausal/pythonic_terms.py`, `clausal/logic/variables/_variables.c`, SegList/SegString/VarSeg |
| A02 | compiler-heads | `clausal/logic/compiler/{head_match,arg_index,terms_to_ast,terms_to_goalop,ir,list_dispatch}.py` |
| A03 | compiler-goals | `clausal/logic/compiler/{predicate,goal_shallow,goal_trampoline,control_constructs,ite_reified,tabled_naf,tro,destructive_reuse}.py`, `specialization.py`, `compiler/optimisations/{call_site,continuation_tco,destructive_reuse,tro}.py` |
| A04 | runtime-tabling | `clausal/logic/{solve,trampoline,continuation_search,coroutining,tabling}.py`, `_trampoline.c`, `_tabling_core.c`, `clausal/logic/runtime/*` (+`_list_unify.c`) |
| A05 | constraints-core | `clausal/logic/{constraints,reif,units_constraint}.py`, `_constraints_dif.c`, `clausal/logic/builtins/attributes.py` |
| A06 | clpfd | `clausal/logic/clpfd.py`, `_clpfd_core.c`, `_clpfd_propagate.c`, `_arithmetic_core.c` |
| A07 | clpb-sat | `clausal/logic/{clpb,clpsat}.py`, `_clpb_core.c`, `clausal/logic/builtins/sat_constraints.py` |
| A08 | clpqr-z3 | `clausal/logic/{clpq,clpr,clpz3,clportools,clportools_lp,clportools_graph,clportools_routing}.py`, `_clpr_core.c`, `clausal/logic/builtins/{z3_constraints,ortools_constraints}.py` |
| A09 | builtins | `clausal/logic/builtins/{lists,higher_order,arithmetic,io,inspection,type_checks,chars,dict_set,pairs,dcg,database_ops,keyword_ops,control,translations_builtin}.py`, `_chars_core.c`, `_lists_core.c` |
| A10 | rewriting-import | `clausal/templating/{term_rewriting,compiler,parser}.py`, `clausal/{import_hook,_lazy_hook,codegen}.py`, `clausal/logic/goal_expansion.py`, `clausal/pythonic_ast/*` |
| A11 | modules-interop | `clausal/modules/*` (incl. `py/*`), `clausal/regex.py`, `clausal/reflection.py`, `clausal/modules/reflection.py`, `clausal/tools/prolog_*`, `prolog_backends/` |
| A12 | seams | cross-subsystem interfaces + synthesis (runs last) |

---

## File Structure

Files this plan **creates**:

```
docs/superpowers/audits/2026-07-05-fable-partition/
  README.md                              # audit index + status board (Task 1)
  DESIGN-DECISIONS.md                    # cross-cutting decision log, seeded empty (Task 1)
  _templates/findings.md                 # ledger template (Task 1)
  _templates/design-questions.md         # design-questions template (Task 1)
  prompts/_shared-preamble.md            # common prompt body (Task 2)
  prompts/RUNBOOK.md                     # launch order + how-to (Task 3)
  prompts/01-term-layer.md … 12-seams.md # the 12 prompts (Tasks 4–7)
tests/audit_2026_07_05/
  __init__.py                            # (Task 1)
  conftest.py                            # per-file run guard + helpers (Task 1)
  test_00_smoke.py                       # library self-test (Task 1)
scripts/audit_2026_07_05/
  check_prompt_paths.py                  # asserts every path named in a prompt exists (Task 1)
todo/audit-2026-07-05/
  README.md                              # todo master index, seeded (Task 1)
```

Each prompt file is **self-contained** (preamble text is embedded at assembly time), so the user pastes one file per session. The plan stays DRY by defining the preamble once (Task 2) and referencing it during assembly.

---

### Task 1: Output scaffolding, templates, and validators

**Files:**
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/README.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/DESIGN-DECISIONS.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/_templates/findings.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/_templates/design-questions.md`
- Create: `tests/audit_2026_07_05/__init__.py`
- Create: `tests/audit_2026_07_05/conftest.py`
- Create: `tests/audit_2026_07_05/test_00_smoke.py`
- Create: `scripts/audit_2026_07_05/check_prompt_paths.py`
- Create: `todo/audit-2026-07-05/README.md`

**Interfaces:**
- Produces: the directory roots and templates every later task and every audit session writes into; `check_prompt_paths.py` (a CLI: `python scripts/audit_2026_07_05/check_prompt_paths.py <prompt.md>...`) that Tasks 4–7 use as their gate.

- [ ] **Step 1: Create the audit README status board**

Write `docs/superpowers/audits/2026-07-05-fable-partition/README.md`:

```markdown
# Fable Partition Audit — 2026-07-05

Findings + adversarial tests + queued todos for the `clausal` package,
partitioned into 11 subsystems + a seams/synthesis session. See the design
spec: `docs/superpowers/specs/2026-07-05-fable-partition-audit-design.md`.

## Status board

| ID | Subsystem | Session status | Findings | Design Qs | Todos | Test file |
|----|-----------|----------------|----------|-----------|-------|-----------|
| A01 | term-layer | not started | – | – | – | test_01_term_layer.py |
| A02 | compiler-heads | not started | – | – | – | test_02_compiler_heads.py |
| A03 | compiler-goals | not started | – | – | – | test_03_compiler_goals.py |
| A04 | runtime-tabling | not started | – | – | – | test_04_runtime_tabling.py |
| A05 | constraints-core | not started | – | – | – | test_05_constraints_core.py |
| A06 | clpfd | not started | – | – | – | test_06_clpfd.py |
| A07 | clpb-sat | not started | – | – | – | test_07_clpb_sat.py |
| A08 | clpqr-z3 | not started | – | – | – | test_08_clpqr_z3.py |
| A09 | builtins | not started | – | – | – | test_09_builtins.py |
| A10 | rewriting-import | not started | – | – | – | test_10_rewriting_import.py |
| A11 | modules-interop | not started | – | – | – | test_11_modules_interop.py |
| A12 | seams | not started | – | – | – | test_12_seams.py |

Each session updates its own row on completion.
```

- [ ] **Step 2: Seed the cross-cutting decision log**

Write `docs/superpowers/audits/2026-07-05-fable-partition/DESIGN-DECISIONS.md`:

```markdown
# Cross-cutting design decisions — 2026-07-05 audit

Append `resolved-by-user` and `open` design questions here as sessions
resolve them, so later sessions check here BEFORE asking the user again.

| ID | Status | Title | Decision + rationale | Raised by | Affects |
|----|--------|-------|----------------------|-----------|---------|
| _(none yet)_ | | | | | |
```

- [ ] **Step 3: Write the two ledger templates**

Write `docs/superpowers/audits/2026-07-05-fable-partition/_templates/findings.md`:

```markdown
# Findings — A<NN> <subsystem>

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A<NN>-F001 | | | | | | | |

## Coverage map

<function/predicate × dimension grid; "dry" is defined against this>
```

Write `docs/superpowers/audits/2026-07-05-fable-partition/_templates/design-questions.md`:

```markdown
# Design questions — A<NN> <subsystem>

Status: resolved-from-docs (cite) | resolved-by-user (record) | open.

| ID | Status | Title | Conflicting sources | Options considered | Decision + rationale | Follow-up |
|----|--------|-------|---------------------|--------------------|----------------------|-----------|
| A<NN>-D001 | | | | | | |
```

- [ ] **Step 4: Create the tests package + conftest + todo index**

Write `tests/audit_2026_07_05/__init__.py` (empty file).

Write `tests/audit_2026_07_05/conftest.py`:

```python
"""Shared fixtures for the 2026-07-05 Fable partition audit suite.

Run these tests PER FILE only — `pytest tests/` OOM-SIGKILLs on this box.
"""
import gc

import pytest


@pytest.fixture
def clear_query_cache():
    """Clear solve._query_cache — it keys by arg *types*, so back-to-back
    solves with differing non-Var args need a clear between them."""
    from clausal.logic import solve
    solve._query_cache.clear()
    yield
    solve._query_cache.clear()


@pytest.fixture
def refcount_stable():
    """Return a helper asserting no unbounded refcount/object growth across a
    stress loop. Usage:
        refcount_stable(lambda: do_work(), iterations=2000)
    """
    def _run(thunk, iterations=2000, tol=64):
        thunk()  # warm up caches
        gc.collect()
        before = len(gc.get_objects())
        for _ in range(iterations):
            thunk()
        gc.collect()
        after = len(gc.get_objects())
        assert after - before <= tol, (
            f"object growth {after - before} over {iterations} iters "
            f"exceeds tolerance {tol} — suspected leak"
        )
    return _run
```

Write `todo/audit-2026-07-05/README.md`:

```markdown
# Audit 2026-07-05 — queued todos

Fixes are QUEUED here, never applied by the audit sessions.

- `fix-<ID>-<slug>.md` — remediation understood; any implementer.
- `investigate-<ID>-<slug>.md` — needs deeper root-cause/design work; tagged for Opus.

Completed todos move to `todo/done/` (repo convention). Session 12 dedups and
maintains this index.

| Todo | Kind | Severity | Finding | Owning subsystem | Status |
|------|------|----------|---------|------------------|--------|
| _(none yet)_ | | | | | |
```

- [ ] **Step 5: Write the prompt path-checker**

Write `scripts/audit_2026_07_05/check_prompt_paths.py`:

```python
"""Validate that every *source* repo path named in an audit prompt exists.

Extracts backtick-quoted tokens that look like FULL repo paths (start with a
known top-level dir AND end in a code extension or '/') and asserts each exists
relative to the repo root. This catches stale source-under-audit paths before a
session is launched.

Deliberately skips:
- the audit's own OUTPUT roots (findings.md, per-subsystem test files, todos) —
  those are created by the audit sessions, so they legitimately don't exist yet;
- prompt-template tokens still containing `{{...}}`;
- glob/brace/placeholder shorthand (`*`, `{`, `<`), bare fragments (`terms.py`,
  `optimisations/`), and absolute external refs.

Usage: python scripts/audit_2026_07_05/check_prompt_paths.py <prompt.md>...
Exit 0 if all paths resolve, 1 otherwise (prints the misses).
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CODE_EXT = (".py", ".c", ".h", ".md", ".clausal")
ROOTS = ("clausal/", "tests/", "docs/", "todo/", "scripts/",
         "packages/", "prolog_backends/", "benchmarks/")
# audit-output roots: created by the sessions, not required to exist now
SKIP_PREFIXES = (
    "tests/audit_2026_07_05/",
    "docs/superpowers/audits/2026-07-05-fable-partition/",
    "todo/audit-2026-07-05/",
)
BACKTICK = re.compile(r"`([^`]+)`")


def candidate_paths(text):
    for tok in BACKTICK.findall(text):
        tok = "".join(tok.split())  # collapse markdown line-wraps inside `...`
        base = re.sub(r":\d+(-\d+)?$", "", tok)  # strip :line refs
        if not base.startswith(ROOTS):
            continue
        if not (base.endswith("/") or base.endswith(CODE_EXT)):
            continue
        if any(c in base for c in "*{<"):  # globs, braces, <placeholders>
            continue
        if base.startswith(SKIP_PREFIXES):
            continue
        yield base


def main(argv):
    misses = []
    for prompt in argv:
        text = Path(prompt).read_text()
        for p in candidate_paths(text):
            if not (REPO / p).exists():
                misses.append((prompt, p))
    if misses:
        print("MISSING PATHS:")
        for prompt, p in misses:
            print(f"  {prompt}: {p}")
        return 1
    print(f"OK: all repo paths in {len(argv)} prompt(s) resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 6: Write the library smoke test**

Write `tests/audit_2026_07_05/test_00_smoke.py`:

```python
"""Smoke test for the audit library itself: scaffolding exists and imports clean."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "docs/superpowers/audits/2026-07-05-fable-partition"


def test_scaffolding_exists():
    for rel in [
        "README.md",
        "DESIGN-DECISIONS.md",
        "_templates/findings.md",
        "_templates/design-questions.md",
    ]:
        assert (AUDIT / rel).exists(), f"missing {rel}"


def test_todo_index_exists():
    assert (REPO / "todo/audit-2026-07-05/README.md").exists()


def test_conftest_fixtures_import():
    # importing the audit package must not error
    import tests.audit_2026_07_05  # noqa: F401


def test_path_checker_runs_clean_on_readme():
    # the audit README names real test files; the checker must pass it
    import subprocess
    script = REPO / "scripts/audit_2026_07_05/check_prompt_paths.py"
    # README references test_NN files that don't exist yet, so check the
    # checker on the spec instead (spec names only existing files/dirs).
    spec = REPO / "docs/superpowers/specs/2026-07-05-fable-partition-audit-design.md"
    r = subprocess.run(["python", str(script), str(spec)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 7: Run the smoke test**

Run: `python -m pytest tests/audit_2026_07_05/test_00_smoke.py -v`
Expected: `test_scaffolding_exists`, `test_todo_index_exists`, `test_conftest_fixtures_import` PASS. `test_path_checker_runs_clean_on_readme` PASS (the spec names only existing paths). If the spec references a not-yet-existing path, fix the checker's skip rules or the spec, not the test expectation.

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/audits/2026-07-05-fable-partition tests/audit_2026_07_05 scripts/audit_2026_07_05 todo/audit-2026-07-05
git commit -m "test(audit): scaffold 2026-07-05 Fable partition audit library"
```

---

### Task 2: Shared prompt preamble

**Files:**
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/_shared-preamble.md`

**Interfaces:**
- Consumes: the scaffolding + templates from Task 1.
- Produces: the common prompt body reused verbatim at the top of all 12 prompt files (Tasks 4–7). Defines the `{{SUBSYSTEM}}` handoff contract those tasks fill in.

- [ ] **Step 1: Write the shared preamble**

Write `docs/superpowers/audits/2026-07-05-fable-partition/prompts/_shared-preamble.md`:

````markdown
You are running an **interactive audit session** of one subsystem of **Clausal**
(a logic-programming language embedded in Python, at `/workspace/clausal`). You
are running as the **Fable** model in your own session — you may and should ask
the user questions when a design-level issue needs a human decision. You do
**not** fix production code; you produce findings, adversarial tests, and queued
todos.

## Read first, before any code (in order)

1. An external, executed-against-Clausal cheat-sheet (not in this repo) — the
   ground-truth of *intended* semantics. Treat verified sections as
   authoritative; sections marked *(unverified)* are weaker evidence.
2. This subsystem's docstrings and its `docs/` topic pages.
3. This subsystem's **prior art** (do not re-report known issues — cite and move
   on): `todo/cross_cutting_issues.md`, `todo/audit-tests-input-output-mode-coverage.md`,
   `tests/audit_2026_05_25/`, `DUPLICATE_TESTS.md`, and any matching
   `implementation_plans/*/todo/*audit*`.
4. `docs/superpowers/audits/2026-07-05-fable-partition/DESIGN-DECISIONS.md` — an
   earlier session may have already answered a design question you hit.

## Standing contracts (violations are findings)

- `==` is **arithmetic** equality (Prolog `=:=`), not structural.
- A string **is** a list of single-character strings (Liskov substitution).
- **Cut-free by design:** no `!/0`, `(->)/2`, `(*->)/2` — replaced by disjoint
  guarded clauses, first-arg indexing, reified `If(C,T,E)`, `dif/2`, `once/1`.
- Unification is `is`; `==` posts a CLP(ℤ) constraint (multi-mode); `:=` is eager
  Python eval; `!=` is arithmetic disequality; `X is not Y` → `dif/2`.
- Bare atoms are **strings**; facts end in a trailing comma; rules use `<-` with
  parenthesized multi-goal bodies; DCG uses `>>`.
- Builtins are PascalCase / full words, no abbreviations (`list_item/3` is 0-based;
  no `nth1`).
- Clausal is logic programming *in Python* — not a Prolog clone; features Python
  already provides are intentionally omitted.

## Method

1. **Coverage map first.** Before probing, list this subsystem's public
   functions/predicates × the dimensions to exercise: input vs **output** mode,
   ground vs partial vs unbound args, empty/singleton/cyclic inputs,
   backtracking + trail restoration, error paths. Write it into the "Coverage
   map" section of your findings ledger. (A numeric-head-literal bug survived
   8085 tests because every test used input mode only — the output/var-query
   direction is mandatory.)
2. **Deep (loop-until-dry).** Probe against the map, repeating passes until the
   map is covered AND a pass surfaces nothing new. Stop after 2 consecutive dry
   passes or when your session budget runs low.
3. **Run to confirm.** Reproduce every correctness finding with an executed
   pytest before logging it confirmed. Run **per file**:
   `python -m pytest tests/audit_2026_07_05/{{TEST_FILE}} -v` — never `pytest tests/`
   (it OOM-SIGKILLs). Unreproducible → log `unconfirmed`.
4. **C findings** (if this subsystem owns `.c`): use the `refcount_stable`
   fixture in `tests/audit_2026_07_05/conftest.py` (object-count deltas over a
   stress loop) for leaks; exercise failure paths for borrowed-ref/Trail bugs;
   cross-reference `todo/cross_cutting_issues.md`. Free-threading claims can only
   be *executed* on the `.cpython-314t` build — this box is a 3.13 GIL build, so
   log FT findings `unconfirmed — needs 3.14t` unless that build is available.
5. **Differential oracle** where one exists (see your subsystem block) — generate
   inputs, diff outputs; a divergence is a finding.
6. **Design issues.** On a design contradiction/ambiguity: (a) check
   `DESIGN-DECISIONS.md`; (b) if unresolved, state the conflict + 2–3 options
   with a recommendation and **ask the user**; (c) record the decision in your
   `design-questions.md` and append cross-cutting ones to `DESIGN-DECISIONS.md`.
   A design issue never blocks the correctness pass — log and continue.
7. **Escalate, don't grind.** When a thread needs deeper root-cause/design work
   than this session should spend, write an `investigate-*` todo (tagged for
   Opus) and move on.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/{{DIR}}/findings.md`
  (from `_templates/findings.md`; IDs `{{ID}}-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/{{DIR}}/design-questions.md`
  (from `_templates/design-questions.md`; IDs `{{ID}}-D001…`).
- `tests/audit_2026_07_05/{{TEST_FILE}}` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-{{ID}}-<slug>.md` (clear remediation)
  or `investigate-{{ID}}-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

## Rules

- Do not edit production code, the cheat-sheet, or another subsystem's files.
- Stay within your subsystem's file list (next section). Anything you find at a
  boundary with another subsystem: log it and note it for the seams session (A12).
````

- [ ] **Step 2: Sanity-check the preamble names real paths**

Run: `python scripts/audit_2026_07_05/check_prompt_paths.py docs/superpowers/audits/2026-07-05-fable-partition/prompts/_shared-preamble.md`
Expected: `OK: all repo paths in 1 prompt(s) resolve`. (The `{{TEST_FILE}}` placeholders contain `{{` so they are not matched as paths; `todo/`, `tests/audit_2026_07_05/conftest.py`, `_templates/*` all exist from Task 1.)

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/audits/2026-07-05-fable-partition/prompts/_shared-preamble.md
git commit -m "docs(audit): shared Fable prompt preamble"
```

---

### Task 3: Launch runbook

**Files:**
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/RUNBOOK.md`

**Interfaces:**
- Consumes: the subsystem index and preamble.
- Produces: the operator instructions the user follows to launch the 12 sessions.

- [ ] **Step 1: Write the runbook**

Write `docs/superpowers/audits/2026-07-05-fable-partition/prompts/RUNBOOK.md`:

```markdown
# Launch runbook — 2026-07-05 Fable partition audit

## How to launch one audit
1. Open a **new Claude Code session** in `/workspace/clausal`.
2. Set the session model to **Fable** (`/model` → Fable).
3. Paste the entire contents of the subsystem's prompt file
   (`prompts/NN-slug.md`). Each file is self-contained.
4. Answer design questions when the session asks; they are recorded for you.

## Order (later sessions inherit earlier design decisions)
- **Wave 1 — core engine:** 01 → 02 → 03 → 04
- **Wave 2 — constraints:** 05 → 06 → 07 → 08
- **Wave 3 — surface:** 09 → 10 → 11
- **Last — seams & synthesis:** 12 (only after 01–11 finish)

Sessions write to disjoint paths, so several can run at once — run as many as
you can attend to (each may block on a question). Landing wave-1 decisions in
`DESIGN-DECISIONS.md` first reduces duplicate questions later.

## After all sessions
- Session 12 has deduped findings/todos, culled false positives, and rolled
  design decisions into `DESIGN-DECISIONS.md` + `todo/audit-2026-07-05/README.md`.
- Triage `todo/audit-2026-07-05/`: `fix-*` (any implementer) vs `investigate-*`
  (Opus). Fixes are a separate, later effort — this round applied none.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/audits/2026-07-05-fable-partition/prompts/RUNBOOK.md
git commit -m "docs(audit): launch runbook for partition audit"
```

---

### Task 4: Core-engine prompts (A01–A04)

**Files:**
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/01-term-layer.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/02-compiler-heads.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/03-compiler-goals.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/04-runtime-tabling.md`

**Interfaces:**
- Consumes: `_shared-preamble.md` (Task 2).
- Produces: 4 self-contained prompts. **Assembly rule for every prompt file (Tasks 4–7):** the file is the full text of `_shared-preamble.md` with `{{DIR}}`, `{{ID}}`, `{{TEST_FILE}}` substituted, followed by a `---` and the subsystem block below. Substitutions per file are given in each block's heading.

- [ ] **Step 1: Assemble `01-term-layer.md`**

Copy `_shared-preamble.md`, replace `{{DIR}}`→`01-term-layer`, `{{ID}}`→`A01`, `{{TEST_FILE}}`→`test_01_term_layer.py`, `{{SUBSYSTEM}}`→`term layer & C unification`. Append:

```markdown
---
## Subsystem A01 — Term layer & C unification

**Files (stay within):** `clausal/terms.py`, `clausal/pythonic_terms.py`,
`clausal/logic/variables/_variables.c`, `clausal/logic/variables/__init__.py`.

**Hotspots:**
- `SegList` / `SegString` / `VarSeg` / `ConcreteSeg` dunders: `__walk__`,
  `__unify__`, `__eq__`/`__hash__` (asymmetries), `__occurs_check__`,
  `__contains__`, `__add__`/`__radd__`. The strings-as-lists Liskov rule:
  promote a walked all-1-char-str list to `str`; keep list shape otherwise.
- The C `do_unify` `str ↔ list` branches and the `__unify__` protocol-hook
  ordering in `_variables.c`.
- Var deref, trail record/undo, occurs-check on cyclic terms.

**C toolkit:** use `refcount_stable` on unify/backtrack loops; check `_variables.c`
against `todo/cross_cutting_issues.md` (Trail_Check before cast; `PyObject_IsInstance`
-1 handling). FT: `_ft_compat.h` — log `unconfirmed — needs 3.14t` unless run there.

**Oracle:** none external; the cheat-sheet's strings-as-lists section + the prior
string audit (`tests/audit_2026_05_25/`) are the reference — extend, don't repeat.

**Seam notes for A12:** how `terms.py` dunders are invoked by the C unifier, and
by the compiler's head matcher (A02).
```

- [ ] **Step 2: Assemble `02-compiler-heads.md`**

Copy preamble, replace `{{DIR}}`→`02-compiler-heads`, `{{ID}}`→`A02`, `{{TEST_FILE}}`→`test_02_compiler_heads.py`, `{{SUBSYSTEM}}`→`compiler: heads & indexing`. Append:

```markdown
---
## Subsystem A02 — Compiler: heads & indexing

**Files (stay within):** `clausal/logic/compiler/head_match.py`,
`clausal/logic/compiler/arg_index.py`, `clausal/logic/compiler/terms_to_ast.py`,
`clausal/logic/compiler/terms_to_goalop.py`, `clausal/logic/compiler/ir.py`,
`clausal/logic/compiler/list_dispatch.py`.

**Hotspots:**
- `head_to_match_pattern`, multi-star guard AST, str/SegList normalization gates.
- First-argument indexing: numeric/bool/None head literals in **output mode**
  (the 8085-test blind spot — `todo/audit-tests-input-output-mode-coverage.md`).
- Groundness-keyed dispatch selection; index correctness for partial terms.
- `terms_to_ast` / `terms_to_goalop` lowering fidelity vs `terms.py` shapes.

**Oracle:** none external; use `clausal/tools/visualize.py` (`predicate_to_source`)
to inspect generated code and diff intended vs emitted match arms.

**Seam notes for A12:** the IR/goalop contract consumed by A03; head patterns
depending on `terms.py` dunders (A01).
```

- [ ] **Step 3: Assemble `03-compiler-goals.md`**

Copy preamble, replace `{{DIR}}`→`03-compiler-goals`, `{{ID}}`→`A03`, `{{TEST_FILE}}`→`test_03_compiler_goals.py`, `{{SUBSYSTEM}}`→`compiler: goals, control & specialization`. Append:

```markdown
---
## Subsystem A03 — Compiler: goals, control & specialization

**Files (stay within):** `clausal/logic/compiler/predicate.py`,
`clausal/logic/compiler/goal_shallow.py`, `clausal/logic/compiler/goal_trampoline.py`,
`clausal/logic/compiler/control_constructs.py`, `clausal/logic/compiler/ite_reified.py`,
`clausal/logic/compiler/tabled_naf.py`, `clausal/logic/compiler/tro.py`,
`clausal/logic/compiler/destructive_reuse.py`, `clausal/logic/specialization.py`,
`clausal/logic/compiler/optimisations/call_site.py`,
`clausal/logic/compiler/optimisations/continuation_tco.py`,
`clausal/logic/compiler/optimisations/destructive_reuse.py`,
`clausal/logic/compiler/optimisations/tro.py`.

**Hotspots:**
- Shallow vs trampoline body lowering equivalence; `_head_has_deferred_pattern`
  driving whether continuation-TCO is safe for string-pattern clauses.
- Reified vs general if-then-else (`ite_reified.py`); `once/1` committed choice.
- Cut-free guarantee: confirm no cut/`->` leaks through any construct.
- Specialization / callsite: a specialized clause must be observationally
  identical to the generic one across all modes (differential: run same goal
  with specialization on vs off).
- Destructive reuse / TRO: aliasing safety under backtracking.

**Oracle:** internal differential — same predicate compiled shallow vs trampoline,
and specialized vs generic, must give identical solution sets.

**Seam notes for A12:** consumes A02's IR; emits code A04 executes.
```

- [ ] **Step 4: Assemble `04-runtime-tabling.md`**

Copy preamble, replace `{{DIR}}`→`04-runtime-tabling`, `{{ID}}`→`A04`, `{{TEST_FILE}}`→`test_04_runtime_tabling.py`, `{{SUBSYSTEM}}`→`runtime, search & tabling`. Append:

```markdown
---
## Subsystem A04 — Runtime, search & tabling

**Files (stay within):** `clausal/logic/solve.py`, `clausal/logic/trampoline.py`,
`clausal/logic/continuation_search.py`, `clausal/logic/coroutining.py`,
`clausal/logic/tabling.py`, `clausal/logic/runtime/list_unify.py`,
`clausal/logic/runtime/body_star_unify.py`, `clausal/logic/runtime/tramp_call.py`,
`clausal/logic/runtime/_seg_helpers.py`.

**Hotspots:**
- `solve` / `call` / `query` / `once` mode matrix; `_query_cache` value vs type
  keying (use the `clear_query_cache` fixture between differing solves).
- Trampoline suspension/resume; deep recursion without Python stack overflow.
- SLG tabling: `TableEntry`, `SuspendedConsumer`, cyclic paths (see
  `tests/fixtures/tabled_path.seam`), answer completeness, WFS delayed negation.
- Trail restoration correctness across suspension and backtracking.

**C toolkit:** `refcount_stable` over solve/backtrack and table-fill loops; audit
`_trampoline.c`, `_tabling_core.c`, `runtime/_list_unify.c` against
`todo/cross_cutting_issues.md`. FT: log `unconfirmed — needs 3.14t` unless run there.

**Oracle:** `docs/tabling.md` for intended tabling semantics; internal differential
(tabled vs untabled predicate must agree on solution sets for terminating programs).

**Seam notes for A12:** executes A03's emitted code; composes with dif (A05) and CLP (A06–A08).
```

- [ ] **Step 5: Validate the four prompts name only real paths**

Run: `python scripts/audit_2026_07_05/check_prompt_paths.py docs/superpowers/audits/2026-07-05-fable-partition/prompts/0{1,2,3,4}-*.md`
Expected: `OK: all repo paths in 4 prompt(s) resolve`. If any path misses, fix the prompt (a file may have moved) — do not weaken the checker.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/audits/2026-07-05-fable-partition/prompts/0{1,2,3,4}-*.md
git commit -m "docs(audit): core-engine Fable prompts (A01-A04)"
```

---

### Task 5: Constraint prompts (A05–A08)

**Files:**
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/05-constraints-core.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/06-clpfd.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/07-clpb-sat.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/08-clpqr-z3.md`

**Interfaces:**
- Consumes: `_shared-preamble.md`. Same assembly rule as Task 4.

- [ ] **Step 1: Assemble `05-constraints-core.md`**

Copy preamble, replace `{{DIR}}`→`05-constraints-core`, `{{ID}}`→`A05`, `{{TEST_FILE}}`→`test_05_constraints_core.py`, `{{SUBSYSTEM}}`→`constraints core`. Append:

```markdown
---
## Subsystem A05 — Constraints core (dif, attributed vars, reif)

**Files (stay within):** `clausal/logic/constraints.py`, `clausal/logic/reif.py`,
`clausal/logic/units_constraint.py`, `clausal/logic/builtins/attributes.py`.

**Hotspots:**
- `dif/2`: free-var collection, occurs check, propagation on binding, survival
  across backtracking; `X is not Y` sugar equivalence.
- Attributed-variable hooks: ordering, re-entrancy, interaction with plain unify.
- Reification correctness (`reif.py`): truth-var semantics in all modes.

**C toolkit:** `refcount_stable` over dif post/propagate/backtrack loops; audit
`_constraints_dif.c` against `todo/cross_cutting_issues.md` (Trail_Check).

**Oracle:** `docs/constraints.md` for intended dif semantics; the existing dif
tests are the behavioral baseline — extend into unhappy paths.

**Seam notes for A12:** attribute hooks fire from the A01/A04 unifier; dif composes
with CLP(FD) (A06) and tabling (A04).
```

- [ ] **Step 2: Assemble `06-clpfd.md`**

Copy preamble, replace `{{DIR}}`→`06-clpfd`, `{{ID}}`→`A06`, `{{TEST_FILE}}`→`test_06_clpfd.py`, `{{SUBSYSTEM}}`→`CLP(FD)`. Append:

```markdown
---
## Subsystem A06 — CLP(FD)

**Files (stay within):** `clausal/logic/clpfd.py`,
`clausal/logic/_clpfd_core.c`, `clausal/logic/_clpfd_propagate.c`,
`clausal/logic/_arithmetic_core.c`.

**Hotspots:**
- Domain ops, `fd_eq/ne/lt/le/gt/ge`, `all_different`, labeling completeness
  and determinism; operator remapping.
- Propagation fixpoint correctness (no missed prunings, no over-pruning);
  bounds vs domain consistency claims must match behavior.
- Labeling must enumerate exactly the solution set (no dups, no misses).

**C toolkit:** `refcount_stable` over post/propagate/label loops; audit
`_clpfd_core.c`, `_clpfd_propagate.c`, `_arithmetic_core.c` against
`todo/cross_cutting_issues.md`.

**Oracle:** classic instances with known solution counts — N-queens
(`tests/fixtures/clpfd_queens.seam`) and SEND+MORE=MONEY
(`tests/fixtures/clpfd_sendmore.seam`) have unique known answers; a wrong
count is a finding.

**Seam notes for A12:** FD vars flow through the A01/A04 unifier and interact with
dif (A05) and labeling under backtracking.
```

- [ ] **Step 3: Assemble `07-clpb-sat.md`**

Copy preamble, replace `{{DIR}}`→`07-clpb-sat`, `{{ID}}`→`A07`, `{{TEST_FILE}}`→`test_07_clpb_sat.py`, `{{SUBSYSTEM}}`→`CLP(B) & SAT`. Append:

```markdown
---
## Subsystem A07 — CLP(B) & SAT

**Files (stay within):** `clausal/logic/clpb.py`, `clausal/logic/clpsat.py`,
`clausal/logic/_clpb_core.c`, `clausal/logic/builtins/sat_constraints.py`.

**Hotspots:**
- BDD correctness: reduced/ordered invariants, unique tables, apply/negate/
  restrict, `sat`/`taut`/`sat_count`/`bool_labeling`.
- `&` `|` `^` `~` operator semantics; variable ordering effects.
- `sat_count` must equal brute-force truth-table count for small formulas.

**C toolkit:** `refcount_stable` over BDD build/apply loops; audit `_clpb_core.c`
against `todo/cross_cutting_issues.md`.

**Oracle:** brute-force truth-table enumeration in Python for ≤ ~12 vars — diff
`sat`/`sat_count`/`taut` against it. `docs/clpb.md` for intended semantics.

**Seam notes for A12:** BDD attr hook propagation via the A01/A05 attribute machinery.
```

- [ ] **Step 4: Assemble `08-clpqr-z3.md`**

Copy preamble, replace `{{DIR}}`→`08-clpqr-z3`, `{{ID}}`→`A08`, `{{TEST_FILE}}`→`test_08_clpqr_z3.py`, `{{SUBSYSTEM}}`→`CLP(Q/R), Z3 & ortools`. Append:

```markdown
---
## Subsystem A08 — CLP(Q/R), Z3 & ortools

**Files (stay within):** `clausal/logic/clpq.py`, `clausal/logic/clpr.py`,
`clausal/logic/clpz3.py`, `clausal/logic/clportools.py`,
`clausal/logic/clportools_lp.py`, `clausal/logic/clportools_graph.py`,
`clausal/logic/clportools_routing.py`, `clausal/logic/_clpr_core.c`,
`clausal/logic/builtins/z3_constraints.py`,
`clausal/logic/builtins/ortools_constraints.py`.

**Known-incorrect warning:** the original CLP(Q) implementation is **known to be
incorrect** — SICStus/Scryer is the canonical reference. Expect real bugs;
prioritize differential testing over reading.

**Hotspots:**
- Rational arithmetic exactness (`clpq.py`); simplex/projection correctness;
  entailment and satisfiability of linear systems.
- `clpr.py` float behavior and its C core.
- Z3/ortools adapters: constraint translation fidelity, result extraction.

**Oracle (strong here):**
- CLP(Z3) → the `z3` package directly: build the same constraints, compare
  sat/model.
- CLP(Q) → SICStus/Scryer via `prolog_backends/{gprolog,scryer}`. **No Prolog
  binary is on PATH** — check availability first; if it can't be built/run, log
  the divergence class you *would* test as an `investigate-*` todo (Opus),
  don't skip silently.
- Cross-check `docs/clpq.md`, `docs/clpr.md` intended vs actual.

**C toolkit:** `refcount_stable` over post/solve loops; audit `_clpr_core.c`.

**Seam notes for A12:** solver vars share the A01/A04 unifier and attribute hooks (A05).
```

- [ ] **Step 5: Validate**

Run: `python scripts/audit_2026_07_05/check_prompt_paths.py docs/superpowers/audits/2026-07-05-fable-partition/prompts/0{5,6,7,8}-*.md`
Expected: `OK: all repo paths in 4 prompt(s) resolve`.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/audits/2026-07-05-fable-partition/prompts/0{5,6,7,8}-*.md
git commit -m "docs(audit): constraint-solver Fable prompts (A05-A08)"
```

---

### Task 6: Surface prompts (A09–A11)

**Files:**
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/09-builtins.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/10-rewriting-import.md`
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/11-modules-interop.md`

**Interfaces:**
- Consumes: `_shared-preamble.md`. Same assembly rule as Task 4.

- [ ] **Step 1: Assemble `09-builtins.md`**

Copy preamble, replace `{{DIR}}`→`09-builtins`, `{{ID}}`→`A09`, `{{TEST_FILE}}`→`test_09_builtins.py`, `{{SUBSYSTEM}}`→`builtins & stdlib predicates`. Append:

```markdown
---
## Subsystem A09 — Builtins & stdlib predicates

**Files (stay within):** `clausal/logic/builtins/lists.py`,
`clausal/logic/builtins/higher_order.py`, `clausal/logic/builtins/arithmetic.py`,
`clausal/logic/builtins/io.py`, `clausal/logic/builtins/inspection.py`,
`clausal/logic/builtins/type_checks.py`, `clausal/logic/builtins/chars.py`,
`clausal/logic/builtins/dict_set.py`, `clausal/logic/builtins/pairs.py`,
`clausal/logic/builtins/dcg.py`, `clausal/logic/builtins/database_ops.py`,
`clausal/logic/builtins/keyword_ops.py`, `clausal/logic/builtins/control.py`,
`clausal/logic/builtins/translations_builtin.py`,
`clausal/logic/builtins/_chars_core.c`, `clausal/logic/runtime/_list_unify.c`.

(Solver-specific builtin adapters — z3/ortools/sat — belong to A07/A08, not here.)

**Hotspots:**
- List builtins under the strings-as-lists rule: every `isinstance(_, str)` site,
  `append`/`length`/`member`/`reverse`/`nth`(`list_item`)/`msort`/`last` in
  **both** input and output modes; result-type promotion.
- Higher-order (`MapList`/`Filter`/`Exclude`/`FoldLeft`) with partial/unbound args.
- `type_checks`, `inspection` (`CopyTerm`/`TermVariables`/`NumberVars`),
  `dict_set`, `pairs`, `control` (once/timeouts), `database_ops` (assertz/retract
  clause sync).
- `chars` C core (`_chars_core.c`).

**C toolkit:** `refcount_stable` over char/list-builtin loops; audit
`_chars_core.c`, `runtime/_list_unify.c` against `todo/cross_cutting_issues.md`.

**Oracle:** Python's own list/string semantics for the pure list ops; DCG example
`clausal/examples/dcg_state.seam`.

**Seam notes for A12:** builtins lean on A01 term shapes and A04 unify helpers.
```

- [ ] **Step 2: Assemble `10-rewriting-import.md`**

Copy preamble, replace `{{DIR}}`→`10-rewriting-import`, `{{ID}}`→`A10`, `{{TEST_FILE}}`→`test_10_rewriting_import.py`, `{{SUBSYSTEM}}`→`term rewriting, templating & import`. Append:

```markdown
---
## Subsystem A10 — Term rewriting, templating & import

**Files (stay within):** `clausal/templating/term_rewriting.py`,
`clausal/templating/compiler.py`, `clausal/templating/parser.py`,
`clausal/import_hook.py`, `clausal/_lazy_hook.py`, `clausal/codegen.py`,
`clausal/logic/goal_expansion.py`, `clausal/pythonic_ast/node_class.py`,
`clausal/pythonic_ast/nodes.py`, `clausal/pythonic_ast/transform.py`,
`clausal/pythonic_ast/conversion_from_python_ast.py`.

**Hotspots (largest file in the codebase — `term_rewriting.py`, ~3600 lines —
coverage-map discipline matters most here):**
- `TermTransformer` / `EmbedTransformer` / `_make_functor_class_ast`: every
  Python-AST node kind → term mapping (operator nodes, list/dict/tuple, unary
  escapes `++()`, f-strings).
- Import hook: transitive py-backed module import, source-vs-installed path
  resolution (`todo/fix-audit-2026-06-24.md` documents a known band-aid — cite,
  don't re-report; probe for *sibling* cases).
- Goal expansion (`goal_expansion.py`): ALLCAPS/trailing_ auto-binding, arrow-
  pattern sugar, recursion into multi-goal bodies.

**Oracle:** `clausal/tools/dump_transformed.py` / `show_generated.py` to compare
intended vs produced AST; round-trip `.clausal` example files through the hook.

**Seam notes for A12:** produces the Predicate/term AST the compiler (A02/A03)
consumes; import hook feeds the runtime (A04).
```

- [ ] **Step 3: Assemble `11-modules-interop.md`**

Copy preamble, replace `{{DIR}}`→`11-modules-interop`, `{{ID}}`→`A11`, `{{TEST_FILE}}`→`test_11_modules_interop.py`, `{{SUBSYSTEM}}`→`modules, interop & Prolog tools`. Append:

```markdown
---
## Subsystem A11 — Modules, interop & Prolog tools

**Files (stay within):** `clausal/modules/graphs.py`, `clausal/modules/imperial.py`,
`clausal/modules/units.py`, `clausal/modules/reflection.py`,
`clausal/modules/prolog.py`, `clausal/modules/py/` (all wrappers),
`clausal/regex.py`, `clausal/reflection.py`, `clausal/tools/prolog_ast.py`,
`clausal/tools/prolog_parser.py`, `clausal/tools/prolog_tokenizer.py`,
`clausal/tools/prolog_operators.py`, `clausal/tools/prolog_dialect.py`,
`clausal/tools/prolog_to_clausal.py`, `clausal/tools/clausal_to_prolog.py`.

**Hotspots:**
- `modules/py/*` wrappers (`csv`, `json`, `datetime`, `hash`, `hmac`, `http`,
  `os`, `process`, `random`, `re`, `sqlite`, `tcp`, `url`, `uuid`, `files`,
  `logging`, `pbkdf2`): faithful pass-through of Python stdlib semantics and
  error propagation; snake_case API fidelity (recent datetime rename).
- `regex.py` / `reflection.py`: multi-arity dispatch, auto-binding, reify_source
  static-eval correctness.
- Prolog tools: tokenizer/parser/operator-table round-trip
  (`prolog_to_clausal` → `clausal_to_prolog`) fidelity across ISO/SWI/Scryer.

**Oracle (strong here):** each `modules/py/*` wrapper's oracle is the **Python
stdlib module it wraps** — call both, diff results and error behavior.
Prolog round-trip is its own differential (parse→emit→parse must be stable).

**Seam notes for A12:** modules load via the A10 import hook; reflection reads
the A01 term layer.
```

- [ ] **Step 4: Validate**

Run: `python scripts/audit_2026_07_05/check_prompt_paths.py docs/superpowers/audits/2026-07-05-fable-partition/prompts/{09,10,11}-*.md`
Expected: `OK: all repo paths in 3 prompt(s) resolve`.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/audits/2026-07-05-fable-partition/prompts/{09,10,11}-*.md
git commit -m "docs(audit): surface-layer Fable prompts (A09-A11)"
```

---

### Task 7: Seams & synthesis prompt (A12)

**Files:**
- Create: `docs/superpowers/audits/2026-07-05-fable-partition/prompts/12-seams.md`

**Interfaces:**
- Consumes: `_shared-preamble.md`; runs after A01–A11 exist.

- [ ] **Step 1: Assemble `12-seams.md`**

Copy preamble, replace `{{DIR}}`→`12-seams`, `{{ID}}`→`A12`, `{{TEST_FILE}}`→`test_12_seams.py`, `{{SUBSYSTEM}}`→`seams & synthesis`. Append:

```markdown
---
## Subsystem A12 — Seams & synthesis (run LAST, after A01–A11)

You have two jobs no single partition audit can do.

### 1. Seams (cross-subsystem interfaces)
Probe the boundaries the partition split apart, plus every boundary ambiguity
the other sessions handed off (search their `findings.md` for "seam"):
- compiler-emits (A03) ↔ runtime-consumes (A04)
- `terms.py` dunders (A01) ↔ C unifier (A01) ↔ head matcher (A02)
- tabling (A04) ↔ dif (A05) ↔ CLP (A06–A08) composition
- import hook / rewriting (A10) ↔ compiler (A02/A03) ↔ runtime (A04)
Write seam findings to `docs/superpowers/audits/2026-07-05-fable-partition/12-seams/findings.md`
and boundary-crossing tests to `tests/audit_2026_07_05/test_12_seams.py`. You may
read (not edit) any subsystem file for seam work.

### 2. Synthesis
- **Dedup** findings AND todos across all 11 ledgers; collapse a cross-cutting
  fix filed by several subsystems into one todo.
- **Cull false positives:** re-run each confirmed finding's repro; downgrade what
  no longer reproduces (note it).
- **Roll up** design questions into `DESIGN-DECISIONS.md` with a single triage-
  ready ordering.
- **Master index:** (re)write `todo/audit-2026-07-05/README.md` — fix vs
  investigate, severity, owning subsystem.
- **Memory:** capture confirmed standing design decisions into project memory
  (`/home/node/.claude/projects/-workspace-clausal/memory/`) per the memory
  convention (one fact per file + a one-line pointer in `MEMORY.md`).
- Update the A12 row (and any corrected rows) in the audit `README.md`.

**Oracle:** the other 11 ledgers + `DESIGN-DECISIONS.md` are your inputs.
```

- [ ] **Step 2: Validate**

Run: `python scripts/audit_2026_07_05/check_prompt_paths.py docs/superpowers/audits/2026-07-05-fable-partition/prompts/12-seams.md`
Expected: `OK: all repo paths in 1 prompt(s) resolve`.

- [ ] **Step 3: Full-library validation + smoke**

Validate the 12 numbered prompts (the `??-*.md` glob matches `01-…`…`12-…`, and excludes `_shared-preamble.md` and `RUNBOOK.md`, whose illustrative `prompts/NN-slug.md` tokens are not real paths):

Run: `python scripts/audit_2026_07_05/check_prompt_paths.py docs/superpowers/audits/2026-07-05-fable-partition/prompts/??-*.md`
Expected: `OK: all repo paths in 12 prompt(s) resolve`.
Run: `python -m pytest tests/audit_2026_07_05/test_00_smoke.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/audits/2026-07-05-fable-partition/prompts/12-seams.md
git commit -m "docs(audit): seams & synthesis Fable prompt (A12)"
```

---

## Done criteria

- `docs/superpowers/audits/2026-07-05-fable-partition/` has README status board, DESIGN-DECISIONS.md, `_templates/`, and `prompts/` with `_shared-preamble.md`, `RUNBOOK.md`, and 12 self-contained prompts.
- `tests/audit_2026_07_05/` has `__init__.py`, `conftest.py` (with `clear_query_cache` + `refcount_stable`), and `test_00_smoke.py` (green per-file).
- `scripts/audit_2026_07_05/check_prompt_paths.py` passes on all 12 prompts.
- `todo/audit-2026-07-05/README.md` seeded.
- The user can open a Fable session and paste any `prompts/NN-slug.md` to run that audit; RUNBOOK gives the order.
