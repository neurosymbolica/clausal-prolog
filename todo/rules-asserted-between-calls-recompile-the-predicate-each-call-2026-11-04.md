# Rules asserted between calls still recompile the whole predicate at each call

Filed 2026-11-04, left over from the fact-load work (fact tables load in
linear time; an assertz of a fact into a clause table is appended in place,
`clausal/logic/compiler/clause_table.py`). Severity: medium, for programs
that build a rule base at run time and query it as they go.

## What / Repro

```prolog
:- dynamic(g/2).
fill(N) :- between(1, N, I), assertz((g(I, Y) :- Y is I + 1)), g(I, _), fail.
fill(_).
```

Each assertz invalidates g/2's dispatch and the next call recompiles every
clause: O(n^2) compiled clauses for n asserts. The same holds for any write
the table cannot take in place, for fact predicates too:

* `asserta/1` (the new clause shifts every index);
* `retract/1` (each retract rebuilds the table: O(n) per retract, so a
  loop retracting n facts with a call between them is O(n^2), though with
  a small constant, no code generation);
* an assertz after a table whose last clause is compiled (its answers were
  FINAL as the last clause's);
* a fact predicate of fewer than 16 clauses before its second recompile
  after a write: the first recompile still goes through the code generator.

## Options

* Append a rule to a table in place: compile it as a one-clause function,
  which needs the compile context of the table's compile (the trap fixed by
  57f3e28d: a lazy recompile must not reuse the first compile's context), so
  a fresh context per appended rule.
* asserta: a table that prepends (indices counting down from 0) would take
  it in place.
* retract: a tombstone per removed clause, with a running call still
  answering it (the logical update view), and a rebuild when tombstones
  pass a fraction of the table.
* The compiled path's per-arm constant (about 3 ms per clause arm at arity
  8: `mark_final_yields`, `fix_missing_locations`, the position pass and
  the body compile each walk the whole function) is what a rule-heavy
  predicate still pays at load.
