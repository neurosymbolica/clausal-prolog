Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

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
