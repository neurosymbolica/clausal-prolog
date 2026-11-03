# A tabled SCC re-leads each dormant member from scratch: right recursion round an n-cycle is O(n^3)

Found 2026-11-03 while measuring the leader-stack and SCC-completion fixes
(todo/done/complete-scc-scans-whole-table-store-per-completion-2026-11-03.md).
Performance only; answers are right.

## Repro

```
-table(rpath/2)

edge(0, 1),
edge(1, 2),
...
edge(n-1, 0),

rpath(X, Y) <- edge(X, Y)
rpath(X, Y) <- (
    edge(X, Z),
    rpath(Z, Y)
)
```

Query `rpath(0, Y)`: n answers, and n variant tables `rpath(i, _)`, all one SCC.

| n | time (no profiler) | leader pushes | add_answer calls | new answers |
|---|---|---|---|---|
| 50 | | 3,484 | 124,753 | 2,500 |
| 100 | 2.3 s | 14,459 | 998,878 | 10,000 |
| 200 | 17.5-19 s | 58,909 | 7,995,253 | 40,000 |

Measured on 98a0427d, on a loaded machine.  Leader pushes grow as ~1.5 n^2 and
`add_answer` calls as n^3, while the tables only ever hold n^2 answers: almost
every derivation is a duplicate.  Under cProfile at n=100 the time is in
`tabled_dispatch` (2.0 M calls, 7.6 s cumulative of 8.8 s) and `add_answer`
(1.0 M calls, 2.0 s); `_on_leader_stack` is ~3% and `_complete_scc` is
negligible.

## Cause

A dormant SCC member is re-led (A04-F001) on every pass of each enclosing
leader's fixpoint, and each re-lead re-runs its clauses against its whole
answer set: naive iteration, no delta.  About n re-leads per member, each
re-deriving its O(n) answers, over n members.

## Options

This is the completion algorithm, not a local slip: a fix is a design change
(XSB-style SCC scheduling on a completion stack, so members are evaluated
together under the leader rather than re-led per pass, or semi-naive
re-evaluation that feeds a re-led member only the answers new since its last
lead).  Either has to keep D68 (complete before the first answer), the
answer order and the WFS delay bookkeeping.  Needs a plan before any code.
