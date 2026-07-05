# Fable Partition Audit — 2026-07-05

Findings + adversarial tests + queued todos for the `clausal` package,
partitioned into 11 subsystems + a seams/synthesis session. See the design
spec: `docs/superpowers/specs/2026-07-05-fable-partition-audit-design.md`.

## Status board

| ID | Subsystem | Session status | Findings | Design Qs | Todos | Test file |
|----|-----------|----------------|----------|-----------|-------|-----------|
| A01 | term-layer | **done 2026-07-05** | 11 (F001–F011; F002 unconfirmed/capi-only) | 4 (D003 resolved-from-docs; D001/D002/D004 parked by user) | 10 fix + 2 investigate | test_01_term_layer.py (37 passed, 20 xfailed) |
| A02 | compiler-heads | not started | – | – | – | test_02_compiler_heads.py |
| A03 | compiler-goals | not started | – | – | – | test_03_compiler_goals.py |
| A04 | runtime-tabling | not started | – | – | – | test_04_runtime_tabling.py |
| A05 | constraints-core | not started | – | – | – | test_05_constraints_core.py |
| A06 | clpfd | not started | – | – | – | test_06_clpfd.py |
| A07 | clpb-sat | not started | – | – | – | test_07_clpb_sat.py |
| A08 | clpqr-z3 | not started | – | – | – | test_08_clpqr_z3.py |
| A09 | builtins | not started | – | – | – | test_09_builtins.py |
| A10 | rewriting-import | not started | – | – | – | test_10_rewriting_import.py |
| A11 | modules-interop | not started | – | – | – | test_11_modules_interop.py |
| A12 | seams | not started | – | – | – | test_12_seams.py |

Each session updates its own row on completion.
