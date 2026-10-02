Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md`
  (from `_templates/findings.md`; IDs `A04-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A04-D001…`).
- `tests/audit_2026_07_05/test_04_runtime_tabling.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A04-<slug>.md` (clear remediation)
  or `investigate-A04-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

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
`clausal/logic/runtime/_trampoline.c`, `clausal/logic/_tabling_core.c`, `clausal/logic/runtime/_list_unify.c` against
`todo/cross_cutting_issues.md`. FT: log `unconfirmed — needs 3.14t` unless run there.

**Oracle:** `docs/tabling.md` for intended tabling semantics; internal differential
(tabled vs untabled predicate must agree on solution sets for terminating programs).

**Seam notes for A12:** executes A03's emitted code; composes with dif (A05) and CLP (A06–A08).
