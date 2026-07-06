Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/07-clpb-sat/findings.md`
  (from `_templates/findings.md`; IDs `A07-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/07-clpb-sat/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A07-D001…`).
- `tests/audit_2026_07_05/test_07_clpb_sat.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A07-<slug>.md` (clear remediation)
  or `investigate-A07-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

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
