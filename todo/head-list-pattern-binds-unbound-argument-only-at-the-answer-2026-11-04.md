# A head list pattern binds an unbound argument only at the answer, so goals frozen on it wake at the wrong times

Found 2026-11-04 in review of the TRO answer-order work (the same with
`CLAUSAL_DISABLE_OPT=tro`, so not caused by it).  Severity: side-effect
order and count differ from ISO when a goal is frozen on an argument that a
clause head's list pattern (`[]`, `[H|T]`, `[a|T]`) meets unbound.

## What / Repro

The compiled head meets an unbound argument with
`$head_list_unify_input`, which returns None and defers the binding to
`$head_list_unify_output`, run at each answer.  A goal frozen on the
argument therefore wakes once per answer (not once per head unification),
not at all for a clause that fails after its head, and a frozen tail sees
`[_]` where ISO binds `[_|_]`.

```prolog
:- use_module(library(freeze)).
w([], N, X) :- N > 0, M is N-1, w([], M, X).
w(_, N, X) :- N =< 0, X = done.
w(L, 0, X) :- L = [], X = late.
pl2(X, N) :- N > 0, M is N-1, pl2(X, M).
pl2([_|_], N) :- N =< 0.
pl3(X, N) :- N > 0, M is N-1, pl3(X, M).
pl3([], N) :- N =< 0.
```

- `freeze(L, (write(wl(L)), nl)), w(L, 2, X)`: Clausal prints `wl([])`
  before each of the two answers; Scryer once, before the first.
- `freeze(L, ...), pl2(L, 2)` and `pl3(L, 2)`: Clausal wakes once (at the
  answer); Scryer three times (at each level's head unification, two of
  them followed by a failing guard).

## Notes

The TRO restart already refuses to restart while such a binding is
deferred (`_lrN is not None`, tests/test_tro_deferred_list.py).  A fix
would bind (or construct) at head-unification time when the argument is
unbound, keeping the deferred output only where it is needed for the
input/output split of list heads.
