# A nested query a Python predicate starts on a fresh trail escapes the run-time cut check

**Status: OPEN, fails open** (final re-review 2, G-2, 2026-10-16). Introduced by the N-1 fix (45a94d6c), which keys the run-time check's records by trail object. Before that fix the cut raised here. Documented in docs/importing_prolog.md ("Not checked: a query a Python predicate starts on a new trail").

## Repro

```prolog
:- use_module(py/probehost).   % nest_fresh_a/1:  for _ in call("a", Y, module=M): unify(X, Y)
                               % (no trail= argument, so a new Trail())
:- table(a/1).
a(0).
a(X) :- nest_fresh_a(Y), !, X is Y + 1, X < 3.
% 81f63091: [0,1] silently.  11733492: permission_error(cut, incomplete_table, a/1).
% Scryer (direct call to a/1): [0,1,2].
% The same program with trail=trail (nest_shared_a) raises, correctly.
```

No engine builtin reachable from `.pl` lazily nests a query on a fresh trail:
- `clause_ops` passes the caller's trail;
- `_drive_dispatch_to_completion` uses a scratch trail but runs to completion.

So this needs a user-written Python predicate that drops the trail AND re-enters the enclosing table's evaluation.

## Fix (the reviewer's)

Tie records to the active QUERY, not to the trail object:
- Each `_drive_trampoline` resume pushes its query id on a thread-local stack, and pops it on suspend.
- A record keeps the ids that were active when it opened.
- A cut counts a record iff the cut's own query was active then.

In the interleaved case (N-1) the cut's query is suspended when the other query's table opens, so the record is ignored. In the nested case the cut's query is running the Python builtin, so the record counts. The cost falls on each resume, not on the cut's fast path.
