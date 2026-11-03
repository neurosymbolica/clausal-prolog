# _complete_scc scans the whole table store on every completion, making bench_tabling O(n^2)

Found 2026-11-03 while re-checking
todo/done/on-leader-stack-linear-scan-2026-09-03.md. Performance only.

## What

`_complete_scc` (clausal/logic/tabling.py) runs once per completed leader and
starts with

```python
members = [e for e in table_store.values()
           if e.status == "evaluating" and e.scc_deps
           and not _on_leader_stack(e) and _mine(e)]
```

That walks every entry of the store. In `bench_tabling` (tabled fib, one new
table per N) the store holds up to n entries and n leaders complete, so the
walk is O(n^2) in total although `members` is empty every time.

Measured on main 4e352fe4 (`benchmarks/workloads.py::bench_tabling(n, 1)`,
best of 3):

| n | time | exponent vs previous |
|---|---|---|
| 1000 | 0.141 s | |
| 2000 | 0.328 s | 1.21 |
| 4000 | 0.892 s | 1.44 |
| 8000 | 2.893 s | 1.70 |

Under cProfile at n=8000, `_complete_scc` is 2.14 s tottime of 4.91 s (44%),
over 8001 calls; at n=2000 it is 0.12 s of 0.81 s (15%).

## Fix direction

Keep, per table store, the set of dormant SCC members (entries that are
`evaluating` with non-empty `scc_deps` and no longer on the leader stack), and
iterate that instead of `table_store.values()`. It must stay in sync with every
status change (completion, the A04-F007 repair that drops entries, re-leads of
dormant members, clausal.aio reaping). The order in which `members` is built
does not affect the result (the blocked-set fixpoint is order-independent), but
check that before relying on it.
