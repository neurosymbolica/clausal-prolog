# _on_leader_stack O(depth) linear scan is ~32% of bench_tabling and makes it O(n^2)

Profile evidence 2026-09-03 (phase2-prereq Task 3): _on_leader_stack (clausal/logic/tabling.py:130)
is a linear scan of the leader stack per tabled dispatch — ~32% cumulative at bench_tabling(2000),
the dominant cost and the source of the workload's quadratic growth. Identical on both sides of
the Phase 0 A/B (cannot have biased it). Fix direction: set/flag membership instead of a scan.
Perf-only; high value; independent of the term-representation program.
