# P2: signal-mode TRO on a non-last clause yields solutions in non-standard order

Split out of [[tro-signal-flag-clobbered-by-later-match-arms]] (the P1 clobber
there is now fixed; this ORDER issue is separate and remains open).

## Mechanism

Signal-mode TRO dispatch (`_make_*_dispatch_trampoline` in
`clausal/logic/compiler/arg_index.py`) drives a bucket to exhaustion — yielding
EVERY later match arm's solutions — and only THEN re-dispatches the tail call
signalled by an earlier (non-last) TRO clause. So for a predicate whose
recursive clause is NOT the last arm of its bucket, the later arms' solutions
arrive BEFORE the tail recursion's, i.e. reversed vs standard Prolog clause
order.

Example (`tests/fixtures/tro_nonlast_arm_clobber.clausal`, `Prc/3`):

    Prc("k", N, X) <- (N > 0, M is N - 1, Prc("k", M, X))   # non-last, TRO
    Prc("k", N, X) <- (X is N)                              # trailing, yields

`Prc("k", 2, X)` yields X in the order 2, 1, 0 — standard Prolog order for this
clause arrangement is 0, 1, 2. The COUNT is correct (3, post-P1-fix); only the
order differs. `once/1`, first-solution cut, and `findall/3` order are affected.

## Candidate fixes

1. When a bucket has a non-last TRO clause, re-dispatch the tail BEFORE running
   the later arms (emit the tail re-dispatch inline at the clause's position
   rather than after all arms). Fixes order; needs care to keep the later arms'
   choice points (they must still be explored after the tail exhausts).
2. Restrict signal-mode TRO to last-arm clauses (todo candidate 2 from the P1
   note). Gives standard order for free, but disables TRO for legitimately
   working non-last recursive clauses (e.g. the `secondary_dispatch_tro.clausal`
   fixture) and would break its `test_tro_is_active` pin — so it is a behavior
   trade, not a pure fix.

## Priority

Lower than P1 (soundness). Only bites order-sensitive callers over predicates
whose recursive clause is not the last arm of its bucket. Park until an
order-sensitive failure actually surfaces.
