# String Implementation Audit — Phase 1 Implementation Plan

**Status:** STUB — to be expanded from the Phase 0 ledger.

**Goal:** Convert each Phase 0 `bug` and `design-gap` finding into an adversarial pytest test marked `xfail(strict=True, reason="ledger F<N>")`.

**Architecture:** One test file per class with findings: `tests/audit_2026_05_25/test_class_C<N>_<topic>.py`. Tests grouped by finding ID inside each file. `xfail(strict=True)` so a fix that accidentally passes a test will be caught.

**Special handling:** per `docs/superpowers/audits/2026-05-25-string-implementation/test_coverage.md`, six findings (F033, F042, F067, F080, F092, F093) have existing pytest cases that codify the audit's "should be different" behaviour as the intended contract. Phase 1 must either:
- Mark those existing tests as `xfail(strict=True, reason="ledger F<N>")` until fixes land, or
- Write new tests asserting the corrected contract and document the conflict (rename or remove the lock-in tests in Phase 2 when fixes land).

**Tasks:** To be written by invoking superpowers:writing-plans with this stub + the completed ledger + the test_coverage.md as input. Expected output: ~15-17 tasks, one per class with findings (plus a setup task for `tests/audit_2026_05_25/conftest.py`).

**Inputs for plan-writing:**
- Spec: `docs/superpowers/specs/2026-05-25-string-implementation-audit-design.md`
- Ledger: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Coverage: `docs/superpowers/audits/2026-05-25-string-implementation/test_coverage.md`
- Phase 0 plan: `docs/superpowers/plans/2026-05-25-string-audit-phase-0.md`
