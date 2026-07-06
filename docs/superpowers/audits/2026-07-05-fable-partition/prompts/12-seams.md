Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

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
