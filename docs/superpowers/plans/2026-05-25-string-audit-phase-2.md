# String Implementation Audit — Phase 2 Implementation Plan

**Status:** STUB — to be expanded from the Phase 0 ledger + Phase 1 test suite.

**Goal:** Land one fix commit per audit class, flipping the corresponding
`tests/audit_2026_05_25/test_class_C<N>_*.py` xfails to passes. Each commit
also removes/updates the lock-in tests in `tests/test_*.py` that codified
the old buggy contract.

**Architecture:** Class-by-class fixes in the Phase 0-recommended order
(see Phase 0 conclusion in
`docs/superpowers/audits/2026-05-25-string-implementation/findings.md`).
Each fix commit:
1. Implements the fix in the relevant `clausal/` source file(s).
2. Removes the xfail markers from `tests/audit_2026_05_25/test_class_C<N>_*.py`
   for the findings closed by the fix.
3. Updates or deletes the lock-in tests in the pre-existing suite as needed.
4. Runs the full pytest suite — zero regressions allowed.
5. Updates the ledger entry status: `open` → `fixed in <sha>`.

**Recommended ordering** (from Phase 0 conclusion):
1. C17 (perf/smell) — F026 only (F009 already a regression test, F078 deferred)
2. C7 (doc-only) — paragraph extension in `docs/strings_as_lists.md`
3. C12 (chr() range guard) — narrow fix in `chars.py`
4. C16 (FT critical section) — `_variables.c` PyList_GET_ITEM → PyList_GetItemRef
5. C5 (Seg* hash/eq) — terms.py SegList/SegString dunders
6. C2 (non-det protocol) — terms.py __unify__ entry point
7. C8 (Seg* sequence protocol) — terms.py SegList/SegString __len__/__iter__/__contains__/__getitem__
8. C15 (runtime_arg_key canonicalisation — must precede C4)
9. C13 (register Seg* + add string/atomic/1) — type_checks.py + `_register_term_types`
10. C14 (copy_term/term_variables Seg* registration) — inspection.py + `_register_term_types`
11. C3 (SegString blind-spot sweep — closes ~16 findings in one change)
12. C9 (_as_items extension + output-shape fixes) — lists.py + higher_order.py
13. C1 (type-source plumbing — design choice required) — multiple files
14. C10 (DCG depends on C3+C1)
15. C4 (F046 + F095 sub-plan — highest blast radius; touches compiler)

**Lock-in test handling:** When fixing C1/C10/C13/C14, the Phase 2 commit
must also update or delete the corresponding tests in:
- `tests/test_seglist_creation.py` (F033, F042)
- `tests/test_dcg.py` (F067)
- `tests/test_string_list_builtins.py` (F080)
- `tests/test_term_inspection.py` (F092, F093)

Phase 1 left these untouched; Phase 2 owns the contract change.

**Phase 1 deliverables ready:**
- 14 test files in `tests/audit_2026_05_25/` covering every bug + design-gap finding
- 75 test functions total (73 XFAIL, 1 XPASSED for F011, 1 PASSED for F009)
- Pre-existing pytest suite confirmed unchanged

**Phase 2 commit cadence:** one commit per class. Each commit:
- Implements the source-code fix in `clausal/`.
- Removes `@pytest.mark.xfail(strict=True, ...)` markers from
  `tests/audit_2026_05_25/test_class_C<N>_*.py` for closed findings.
- Updates lock-in tests if applicable.
- Runs `pytest tests/` and confirms zero regressions.
- Updates ledger entry status `open` → `fixed in <sha>` and adds the
  commit SHA to the entry's Notes.

**Tasks:** To be written by invoking superpowers:writing-plans with this
stub + the completed ledger + the Phase 1 test suite as input. Expected
output: ~16 tasks (one per class fix in the order above + a final sweep
task per the spec's Phase 3).

**Inputs for plan-writing:**
- Spec: `docs/superpowers/specs/2026-05-25-string-implementation-audit-design.md`
- Ledger: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Coverage: `docs/superpowers/audits/2026-05-25-string-implementation/test_coverage.md`
- Phase 1 plan + tests: `docs/superpowers/plans/2026-05-25-string-audit-phase-1.md` + `tests/audit_2026_05_25/`
