# String Implementation Audit — 2026-05-25

This directory holds the artifacts of the strings-as-lists audit.

**Status:** complete (closed 2026-05-26; revised 2026-06-13; F078 Phase 3 closure 2026-06-13; F046 C4 follow-up closed 2026-06-16). Tagged `string-audit-complete`.
**Totals:** 66 findings across 15 classes — 28 bug, 25 design-gap, 2 perf, 4 smell, 7 doc-only. 65 closed (59 in Phase 2 + 4 in 2026-06-13 follow-up C14 cluster + 1 in Phase 3 F078 closure + 1 in 2026-06-16 F046 C4 follow-up); 1 deferred (F068 architectural — see `findings.md` "Phase 3 sweep — conclusion").

## Phase 2 status — complete (with Phase 3 sweep)

- **Fix commits:** 14 core in Phase 2 (one per audit class plus the F046 deferral commit); 63 total in the Phase 2 range including planning, test scaffolding, and polish commits; +1 follow-up commit on 2026-06-13 closing the C14 args-of-list cluster (F088-F091) and renaming `get_item/3` → `list_item/3`; +1 Phase 3 commit (2026-06-13) closing F078 dead-branch deletion; +1 follow-up commit on 2026-06-16 (6c7acf6) closing F046 (C4 head-literal mismatch)
- **Findings closed:** 65 / 66
- **Findings deferred:** 1 (F068 architectural — see `findings.md` "Phase 3 sweep — conclusion")
- **Audit suite:** 80 PASSED, 1 XFAIL (F068), 0 XPASSED, 0 FAILED, 0 ERRORED
- **Pre-existing pytest suite:** 7840 passing, 1 xfailed (post-2026-06-16 F046 follow-up; was 7760 post-2026-06-13; baseline 7752) — zero regressions
- **Tagged:** `string-audit-complete`

The audit is complete. F046 (C4 head-pattern literal mismatch) closed 2026-06-16 via its follow-up spec (`../../specs/2026-06-13-f046-head-literal-mismatch-design.md`). F078 (C17 dead-branch smell) closed in Phase 3 sweep. Only F068 (C10 architectural) remains deferred.

### 2026-06-13 follow-up — C14 args-of-list cluster closed

User decision 2026-06-13: ISO-named inspection predicates
(`functor/3`, `arg/3`, `unpack/2` / `=..`) follow ISO Prolog cons-cell
semantics; Clausal-named predicates remain Pythonic. Strings-as-lists
Liskov symmetry applies, so str inputs decompose the same cons-cell
shape as the equivalent list inputs (modulo str-vs-list type on
head/tail). The 4 deferred findings in the args-of-list cluster
(F088 bug, F089 design-gap, F090 bug, F091 bug) closed in a single
follow-up commit. Same commit renamed `get_item/3` → `list_item/3`
(the old name was deemed too procedural) and added a code-level TODO
to rename `unpack/2` to a less procedural-sounding Clausal name
(candidates: `univ/2`, `decompose/2`, `as_list/2`, `to_list/2`,
`structure/2`; user to decide).

## Phase 1 status — complete

- **Test files:** 15 (`tests/audit_2026_05_25/test_class_C*.py`) — one per audit class with findings (C1, C2, C3, C4, C5, C8, C9, C10, C12, C13, C14, C15, C16, C17)
- **Tests:** 75 total (see breakdown below)
- **Pre-existing pytest suite:** verified unchanged after Phase 1 commits

### Per-class breakdown

| Class | File | Tests | Result on GIL build |
|-------|------|------:|---------------------|
| C1 | test_class_C01_type_preservation.py | 5 | 5 XFAIL |
| C2 | test_class_C02_nondet_first_only.py | 2 | 2 XFAIL |
| C3 | test_class_C03_segstring_blindspots.py | 8 | 8 XFAIL |
| C4 | test_class_C04_head_literal_mismatch.py | 1 | 1 XFAIL at Phase 1; F046 closed 2026-06-16 — file now has 7 tests, all PASSED (+6 coverage tests) |
| C5 | test_class_C05_hash_eq_asymmetries.py | 3 | 3 XFAIL |
| C8 | test_class_C08_partial_term_shortcircuits.py | 6 | 6 XFAIL |
| C9 | test_class_C09_polymorphic_mode_matrix.py | 19 | 19 XFAIL (F054 parametrized ×8) |
| C10 | test_class_C10_dcg_phrase.py | 9 | 9 XFAIL (F069 ×3, F070 ×4) |
| C12 | test_class_C12_char_representation.py | 6 | 6 XFAIL (F073 ×6 variants) |
| C13 | test_class_C13_type_checks.py | 5 | 5 XFAIL |
| C14 | test_class_C14_term_inspection.py | 7 | 7 XFAIL (all 7 now PASSED post-Phase-2 + 2026-06-13 follow-up) |
| C15 | test_class_C15_first_arg_indexing.py | 1 | 1 XFAIL |
| C16 | test_class_C16_ft_safety.py | 1 | 1 XPASSED (xfail strict=False — GIL build masks FT race) |
| C17 | test_class_C17_perf_memory.py | 2 | 1 PASSED (F009 regression test) + 1 XFAIL (F026) |
| **Total** | | **75** | **73 XFAIL + 1 XPASSED + 1 PASSED** |

### Phase 2 readiness

Every `bug` and `design-gap` finding in the ledger has at least one
adversarial test. Phase 2 fixes will flip xfails to passes class-by-class;
each fix commit must remove the corresponding xfail marker(s).

Lock-in tests in the pre-existing suite (F033, F042, F067, F080, F092,
F093) remain untouched per Phase 1 discipline; Phase 2 will update or
delete them when each fix lands.

- **Design spec:** `../../specs/2026-05-25-string-implementation-audit-design.md`
- **Phase 0 plan:** `../../plans/2026-05-25-string-audit-phase-0.md`
- **Ledger:** [findings.md](findings.md) — every issue found, grouped by
  class C1–C17, sorted by severity within class.
- **Probes:** [probes/](probes/) — self-contained Python scripts that
  confirm each finding's symptom. Re-runnable; not pytest tests.
- **Test coverage inventory:** [test_coverage.md](test_coverage.md) —
  which existing tests cover which surface; informs Phase 1.

## How to read the ledger

Each finding has a stable ID (F001…). Phase 1 test files and Phase 2 fix
commits reference these IDs. IDs are never re-numbered. Findings link to
related findings via wiki-style `[[Fnnn]]` syntax.

## How to re-run a probe

```bash
python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F042.py
```
