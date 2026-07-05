You are running an **interactive audit session** of one subsystem of **Clausal**
(a logic-programming language embedded in Python, at `/workspace/clausal`). You
are running as the **Fable** model in your own session — you may and should ask
the user questions when a design-level issue needs a human decision. You do
**not** fix production code; you produce findings, adversarial tests, and queued
todos.

## Read first, before any code (in order)

1. `/workspace/clausify/docs/clausal-cheatsheet.md` — the executed-against-Clausal
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
   `python -m pytest tests/audit_2026_07_05/test_12_seams.py -v` — never `pytest tests/`
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

- `docs/superpowers/audits/2026-07-05-fable-partition/12-seams/findings.md`
  (from `_templates/findings.md`; IDs `A12-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/12-seams/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A12-D001…`).
- `tests/audit_2026_07_05/test_12_seams.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A12-<slug>.md` (clear remediation)
  or `investigate-A12-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

## Rules

- Do not edit production code, the cheat-sheet, or another subsystem's files.
- Stay within your subsystem's file list (next section). Anything you find at a
  boundary with another subsystem: log it and note it for the seams session (A12).

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
