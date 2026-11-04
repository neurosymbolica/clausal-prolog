# A TRO restart from a clause that is not the last reverses the answer order

Found 2026-11-04 while fixing last-call optimisation inside index buckets.
Severity: wrong answer ORDER (the set of answers is right) for a predicate
that is not indexed and whose tail-recursive clause has a later clause.

## What / Repro

```prolog
:- module(nl, [p/2]).
p(N, X) :- N > 0, M is N - 1, p(M, X).
p(N, N).
```

`findall(X, p(3, X), L)` gives `L = [3, 2, 1, 0]`; ISO clause order (and
`CLAUSAL_DISABLE_OPT=tro`) gives `[0, 1, 2, 3]`.  `once/1` and the first
answer are therefore wrong too.  The same in `.clausal` and `.seam` source.

The whole-predicate function restarts in place ("loop" mode): the
recursive clause sets `_tro`, the match arms AFTER it still run and answer,
and only then does the `while True` loop restart with the tail call's
arguments.  The later clause's answer for this activation comes before
every answer of the tail call.  A restart is in clause order only when no
later clause can answer: the last clause, or a clause that cuts before its
tail (the cut exit raises `TroCutRestart`, skipping the later arms).

Index buckets, defaults and fallbacks (the "signal" mode) have the same
mechanism.  They now restart only from such clauses
(`_signal_safe_tro_indices` in `clausal/logic/compiler/predicate.py`);
`tests/test_tro_nonlast_arm_clobber.py::test_nonlast_tro_arm_answers_in_clause_order`
pins the bucket order.

## Fix

Apply the same rule to loop mode: restart only from the function's last
clause or a clause that cuts before its tail.  It changes the generated
code of every unindexed predicate with a non-last recursive clause (that
clause makes the ordinary call, as an ISO WAM does while the clause still
has an alternative) and the answer order of those predicates, so it wants
a before/after generated-code comparison and a CHANGELOG entry of its own.
