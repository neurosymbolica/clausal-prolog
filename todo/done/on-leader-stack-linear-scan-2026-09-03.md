# _on_leader_stack O(depth) linear scan is ~32% of bench_tabling and makes it O(n^2)

**Status: RESOLVED 2026-11-03 (commit 34680fa9).** No longer true: since D68 `_complete_scc` filters on `status == "evaluating" and scc_deps` before asking `_on_leader_stack`, and the other callers are guarded by `status == "evaluating"`, so `bench_tabling` makes zero `_on_leader_stack` calls at n=2000 and n=8000 (counted by wrapping the function). On a cycle-heavy workload (tabled right-recursive path over a 100-node ring) it is 29,210 calls, 0.22 s of 8.2 s (~3%), so an O(1) membership structure was not added. The workload is still superlinear (fit exponent 1.45 over n=1000..8000, rising to 1.70), but the cost is now `_complete_scc`'s scan of the whole table store per completion: see todo/done/complete-scc-scans-whole-table-store-per-completion-2026-11-03.md (since fixed).

Profile evidence 2026-09-03 (phase2-prereq Task 3): _on_leader_stack (clausal/logic/tabling.py:130)
is a linear scan of the leader stack per tabled dispatch — ~32% cumulative at bench_tabling(2000),
the dominant cost and the source of the workload's quadratic growth. Identical on both sides of
the Phase 0 A/B (cannot have biased it). Fix direction: set/flag membership instead of a scan.
Perf-only; high value; independent of the term-representation program.
