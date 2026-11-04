# Seam: a goal woken by a head unification is dropped if that clause then fails

**Status: OPEN.** Found 2026-11-04 in code review of the TRO answer-order work. Behaviour is the
same with TRO on and off, and at f434f384, so it predates that work.

In a `.seam` predicate, a frozen goal woken while a clause HEAD unifies waits for the next answer.
If that clause's body then fails (its guard is false), the queued goal is discarded and never
runs. In `.pl` and `.clausal` it runs, as in Scryer:

```prolog
q(X, N) :- N > 0, M is N-1, q(X, M).
q([_], N) :- N =< 0.
?- freeze(Z, (write(wz(Z)), nl)), q([a|Z], 2).
```

| Surface | Wake log |
|---|---|
| `.pl`, `.clausal`, Scryer | woke, answer, woke, woke |
| `.seam` (the same program) | woke, answer |

This contradicts `docs/coroutining.md` (Implementation note), which says the queue runs "at the
start of a clause body whose head unified". Either the seam must drain the queue at the start of
the body, as the other surfaces do, or the docs must say the seam doesn't. Pinned as current
behaviour by the comment at `tests/test_tro_clause_order.py:155` ("dropped").
