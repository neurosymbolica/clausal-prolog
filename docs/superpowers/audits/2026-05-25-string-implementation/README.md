# String Implementation Audit — 2026-05-25

This directory holds the artifacts of the strings-as-lists audit.

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
