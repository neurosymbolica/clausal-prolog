# length/2 of a pattern with a hole that is not its tail has no answer

Found 2026-10-11 by the security review of the split pending goal;
reproduces on 1b717269 (before it) and on a6e2dae0.

```seam
l0(A, B) <- (P is [*A, *B], length(P, 0))      % no answer; want A = [], B = []
l2(A, B) <- (P is [*A, *B], length(P, 2))      % no answer; want 3 splits of 2 fresh vars
l1(A, B) <- (P is [*A, 1, *B], length(P, 1))   % no answer; want A = [], B = []
```

A partial list whose only hole is its tail (`[a|T]`) works. Expected,
as `length(P, N)` with `P = [X1, ..., Xn]` then `P = [*A, *B]`: every
split of N fresh variables, in append/3 order. Likely fix: for a Seg* with
a non-tail hole and a bound N, unify P with a list of N fresh variables
(the split pending goal then gives the splits).
