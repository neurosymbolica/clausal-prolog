# A tabled SCC re-leads each dormant member from scratch: right recursion round an n-cycle is O(n^3)

**Status: PARTLY FIXED 2026-11-03 (commit 844fc5fd).** Idle re-leads skip their fixpoint loop (option 3 below), with every table's answers, their order and WFS truth unchanged; that is a 4-6x constant factor on the ring, not the asymptotic fix: the ring is still ~n^3.  What is left needs a ruling: option 1 (semi-naive feeding, a compiler analysis of tabled call sites) or option 2 (XSB-style SCC scheduling, which changes answer order).  Pinned in tests/test_tabling_idle_relead.py.

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

## Design (operator ruling 2026-11-03, R12)

The ruling: improve completion so a re-led member does not re-derive answers
it already has; answers, answer order and WFS truth values unchanged; if that
cannot be guaranteed, stop and report with options.

### Where the work goes

On the ring every member is re-led about 1.5 n times, and a re-lead does two
things: it replays the member's rows to the caller (O(n)), and it re-runs the
member's clauses to a fixpoint of their own, which re-leads the next member,
and so on round the ring.  Leader pushes are ~1.5 n^2 and nearly every
`add_answer` is a duplicate.  The order of every table is the order in which
this schedule happens to find answers (`rpath(0, Y)` gives Y = 1, 3, 5, ...,
2, 4, ...), and that order is observable: `findall/3` over a complete table
returns it, and every inner table keeps its own.

### The options

1. **Semi-naive feeding** (a re-led member, or the caller of one, sees only
   the rows new since it last ran).  Sound only when the rest of the clause
   after the tabled call is a pure function of the call's row and of the
   prefix bindings that reach it: an old row joined with a NEW row of
   another incomplete table later in the body, or with a new binding made
   by the prefix that the call's variant key does not carry, is a new answer
   that the delta would drop.  The engine re-derives by re-running compiled
   generator code; it cannot see a continuation's environment or prove it
   pure, so this would need a compiler analysis of each tabled call site (the
   goals after the call, which variables they read) plus a per-site,
   per-environment watermark.  Large, and the risk is lost answers.
2. **XSB-style SCC scheduling** (members evaluated together under the leader,
   each member's dispatch run once per round against the current tables,
   instead of being re-led per enclosing pass).  O(n^2) on the ring, but it
   finds answers in a different order, so the order of every table in the
   SCC changes (for `rpath(0, Y)` it would be the SLG order 1, 2, ..., n-1,
   0).  Ruled out by "answer order unchanged"; it needs a ruling of its own.
3. **Idle re-leads** (implemented).  A re-lead whose clauses can read
   nothing that changed since a pass of theirs that found nothing new skips
   its fixpoint loop: the re-run would be a replay of that pass, finding the
   same answers in the same order, all already tabled, and changing no
   condition.  It still replays its rows to the caller (the caller's pass has
   not seen them), and it does not re-lead the members beneath it, which is
   where the saving is.  Every table gains the same rows in the same order
   as before, so order and truth values are unchanged by construction.  It
   removes the redundant re-leads, not the cubic shape: a re-lead that is
   not idle still replays and re-derives O(n) rows.

### Idle re-leads, precisely

A pass of a leader is QUIET when it found no new answer, incurred no delay,
and no table anywhere changed while it ran.  Its end records a stamp
(`_quiet_stamp`): the table epoch, the clause-write counter, and the lead
token of the leader below on the leader stack.  A re-lead of a dormant SCC
member compares the stamp after it has replayed its rows (the caller's
continuation runs during the replay and may change tables) and skips its
loop when the stamp still matches:

* the table epoch (`tabling._epoch`) takes a fresh value whenever any table
  gains a row, revives a failed one, changes a row's conditions (a new
  disjunct, `_resolve_conditions`), completes, or is dropped (A04-F007
  repair, `end_drive_episode`, `clausal.aio` reaping);
* the clause-write counter (`database._mutations`) takes one on every
  `Database.mutate` transaction (all assert/retract/abolish channels), on
  `abolish_table` and on clearing a store;
* the parent lead token: while that frame lives, every entry beneath it
  stays on the stack, so every table the member's clauses reach is consumed
  (on the stack) or re-led (off it) exactly as in the quiet pass, and the
  SCC edges (`scc_deps`) the re-run would record are the ones already
  recorded.  Without it, a table the quiet pass re-led could now be an
  ancestor on the stack, which a re-run would consume, recording an edge
  that keeps the members between from completing early.

Never skipped (these paths run as before): a member with a CLP(Q) residue
row; a call with an attributed variable in its arguments; any judging leader
or detached segment on the stack (`seam.judged_answers`); a `clausal.aio`
drive.  The bookkeeping a re-run would do and the skip does not: suspended
consumers the replay's caller parked on the entry are closed, as the pass end
would; `incomplete_reads` is bumped by the replay itself, so the enclosing
leader's no-confirming-pass test sees the same thing; cut-check records the
re-run would open are opened and closed inside it.  What the stamp cannot see
is state outside the engine: a clause body whose answers depend on a Python
escape's mutable state or on I/O is assumed to derive the same answers when
re-run over the same tables -- the assumption the no-confirming-pass rule
already makes (D74 Q4, provisional).

`CLAUSAL_TABLING_SEMINAIVE=0` turns the skip off.

### Verification and measurements (2026-11-03)

Differential, `CLAUSAL_TABLING_SEMINAIVE=1` against `=0`:

* pytest with JUnit XML over the 67 test files that table (every file under
  `tests/` naming `-table(`, `:- table`, `tabling`, `query_wfs`, `tabled` or
  `judged_answers`: test_tabling*, test_wfs, test_aio, test_slg_termination,
  tests/iso_l3 tabled files, audit_2026_07_05 tabling/seams, ...) plus the
  new test file: 3976 passed, 2 skipped, 11 xfailed in both modes; no test
  differs.
* An answer dump (each query's answers in order, then every table's key,
  status, rows in order and conditions; WFS truth through `query_wfs` after
  each query and on a fresh store): 4,400 generated programs (400 random
  graphs of 1-9 nodes, every fifth containing a ring, x 11 formulations:
  right, left and double recursion, mutual recursion two ways, same
  generation, `win/1`, reachability under negation, `win` inside
  reachability, `findall/3` over a tabled predicate) and the 26 tabled
  fixtures under tests/fixtures (two do not load standalone, in either mode):
  identical output; 32,697 idle re-leads were
  taken with the switch on.  (`query_wfs` itself never skips: it drives
  through a judging leader.)

Ring (`rpath(0, Y)`, `call/N`, same machine, same load):

| n | leader pushes off -> on | add_answer calls off -> on | time off -> on |
|---|---|---|---|
| 100 | 14,459 -> 5,243 | 998,878 -> 206,497 | 3.15 -> 0.71 s |
| 200 | 58,909 -> 20,493 | 7,995,253 -> 1,492,997 | 24.6 -> 5.0 s |
| 400 | 237,809 -> 80,993 | 63,980,503 -> 11,305,997 | 209 -> 37.4 s |

Time exponents: off 2.96 (100-200), 3.09 (200-400); on 2.82, 2.90.
`add_answer` exponents on: 2.85, 2.92.  Still cubic.

`bench_tabling(n, 1)` (tabled fib, no SCC), best of 3, two runs each: n=1000
0.115/0.116 s off, 0.117/0.114 s on; 2000 0.200/0.201, 0.201/0.202; 4000
0.387/0.382, 0.396/0.401; 8000 0.844/0.856, 0.864/0.866.  Exponent ~1.0 both;
the stamp bookkeeping costs ~2% at the top end.
