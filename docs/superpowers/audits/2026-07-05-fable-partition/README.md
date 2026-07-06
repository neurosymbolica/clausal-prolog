# Fable Partition Audit — 2026-07-05

Findings + adversarial tests + queued todos for the `clausal` package,
partitioned into 11 subsystems + a seams/synthesis session. See the design
spec: `docs/superpowers/specs/2026-07-05-fable-partition-audit-design.md`.

## Status board

| ID | Subsystem | Session status | Findings | Design Qs | Todos | Test file |
|----|-----------|----------------|----------|-----------|-------|-----------|
| A01 | term-layer | **done 2026-07-05** | 11 (F001–F011; F002 unconfirmed/capi-only) | 4 (D003 resolved-from-docs; D001/D002/D004 parked by user) | 10 fix + 2 investigate | test_01_term_layer.py (37 passed, 20 xfailed) |
| A02 | compiler-heads | **done 2026-07-05** | 5 (F001–F005; F005 doc-drift) | 2 (D001 resolved-from-docs; D002 parked) | 5 fix + 1 investigate | test_02_compiler_heads.py (51 passed, 20 xfailed) |
| A03 | compiler-goals | **done 2026-07-05** | 10 (F001–F010; F010 doc-drift) | 5 (D004/D005 resolved-from-docs; D001–D003 parked by user) | 10 fix + 1 investigate | test_03_compiler_goals.py (51 passed, 17 xfailed) |
| A04 | runtime-tabling | **done 2026-07-05** | 11 (F001–F011; F011 design) | 4 (D003 resolved-from-docs/cites A02-D002; D001/D002/D004 parked by user) | 8 fix + 3 investigate | test_04_runtime_tabling.py (24 passed, 20 xfailed) |
| A05 | constraints-core | **done 2026-07-05** | 6 (F001–F006; F006 doc-drift) | 3 (D003 resolved-from-docs; D001/D002 parked) | 5 fix + 1 investigate | test_05_constraints_core.py (57 passed, 17 xfailed) |
| A06 | clpfd | **done 2026-07-05** | 18 (F001–F018; F016 confirmed-by-inspection; F017 doc-drift; F018 design-parked) | 5 (D001–D005 parked; D005 blocked on A01-D001) | 17 fix + 1 investigate | test_06_clpfd.py (56 passed, 23 xfailed) |
| A07 | clpb-sat | **done 2026-07-05** | 11 (F001–F011; F010/F011 doc-drift) | 4 (D004 resolved-from-docs; D001–D003 parked) | 8 fix + 1 investigate | test_07_clpb_sat.py (35 passed, 12 xfailed) |
| A08 | clpqr-z3 | **done 2026-07-05** | 18 (F001–F018; F017 doc-drift; F018 design, unconfirmed-impact) | 5 (D001–D005 parked) | 11 fix + 5 investigate | test_08_clpqr_z3.py (26 passed, 29 xfailed) |
| A09 | builtins | **done 2026-07-05** | 32 (F001–F032; F022 design-parked; F023–F026 doc-drift; F027–F031 low) | 5 (D001–D005 parked; D001/D002 appended cross-cutting) | 23 fix + 4 investigate | test_09_builtins.py (28 passed, 45 xfailed) |
| A10 | rewriting-import | not started | – | – | – | test_10_rewriting_import.py |
| A11 | modules-interop | not started | – | – | – | test_11_modules_interop.py |
| A12 | seams | not started | – | – | – | test_12_seams.py |

Each session updates its own row on completion.
