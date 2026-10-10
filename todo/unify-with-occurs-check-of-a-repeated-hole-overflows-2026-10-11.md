# unify_with_occurs_check of a pattern with a repeated hole overflows

Found by the security review of the split pending goal (2026-10-10);
reproduces on 1b717269, before that change.

```seam
rep(R) <- (P is [*A, *A], findall(1, unify_with_occurs_check(P, [[A], A]), R))
```

raises `RecursionError: unify: term nesting too deep` from
`_apply_seglist_split` (clausal/terms.py). The expected answer is `R = []`:
every split binds `A` to a term containing `A`. A split binds holes with
plain `unify`; for the second occurrence of a repeated hole it unifies a
cyclic binding with more of itself and recurses. The occurs-checked
builtins check acyclicity only after a split is bound, so they never get
the chance. Fix direction: give the split's apply an occurs-checked mode
(or check `occurs_check(var, value)` before each hole's bind) when called
from `unify_with_occurs_check/2`.
