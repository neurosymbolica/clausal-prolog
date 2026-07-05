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
   `python -m pytest tests/audit_2026_07_05/test_03_compiler_goals.py -v` — never `pytest tests/`
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

- `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md`
  (from `_templates/findings.md`; IDs `A03-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A03-D001…`).
- `tests/audit_2026_07_05/test_03_compiler_goals.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A03-<slug>.md` (clear remediation)
  or `investigate-A03-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

## Rules

- Do not edit production code, the cheat-sheet, or another subsystem's files.
- Stay within your subsystem's file list (next section). Anything you find at a
  boundary with another subsystem: log it and note it for the seams session (A12).

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
