# An opt-in streaming mode per tabled predicate, for tables that never complete

Filed 2026-10-16, from the D68 review (Q3), by the engine lane.

## What

Since operator ruling D68 (2026-10-16) a tabled call completes its table
before its first answer.  A tabled predicate with infinitely many answers
therefore never answers at all: the call runs, its table grows until memory
runs out, and `once(nat(X))` hangs.

```prolog
:- table(nat/1).
nat(0).
nat(N) :- nat(M), N is M + 1.
?- once(nat(X)).      % before D68: X = 0; since D68: hangs
```

Q3 is accepted and documented (operator ruling D74, 2026-10-19 (Mike: "all as recommended"); docs/tabling.md):
bound the generator, or do not table it.  This todo stays open for the
optional streaming mode.

## Candidate

A per-predicate opt-in, e.g. `:- table(nat/1, [stream])` (XSB's
`batched` scheduling is the analogue), under which the leader hands answers
over as it derives them, as before D68.  The cost is D68's two fixes for
that predicate: a second call of the same table in the continuation reads
a partial table (todo/done/tabled-findall-over-two-calls-loses-pairs-
2026-10-16.md), and a cut over its first answer raises
`permission_error(cut, incomplete_table, F/N)`.  The machinery exists: the
leader already streams SCC members and constrained answers
(`tabling.make_tabled_wrapper_trampoline`, `streamed`).
