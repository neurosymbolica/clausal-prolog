Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/05-constraints-core/findings.md`
  (from `_templates/findings.md`; IDs `A05-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/05-constraints-core/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A05-D001…`).
- `tests/audit_2026_07_05/test_05_constraints_core.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A05-<slug>.md` (clear remediation)
  or `investigate-A05-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

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
