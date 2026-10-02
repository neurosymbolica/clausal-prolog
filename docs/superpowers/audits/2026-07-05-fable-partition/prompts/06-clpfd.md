Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md`
  (from `_templates/findings.md`; IDs `A06-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A06-D001…`).
- `tests/audit_2026_07_05/test_06_clpfd.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A06-<slug>.md` (clear remediation)
  or `investigate-A06-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

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
