# TRO does not count the seam's arithmetic `==` as binding a tail argument

Found 2026-11-04 while fixing last-call optimisation inside index buckets.
Severity: missed optimisation only (answers are right): memory grows with
the length of the loop.

## What / Repro

```
-module(cseam, [c(S, K, A, N)])
c('stop', _, N, N),
c('go', 0, A, N) <- c('stop', 0, A, N)
c('go', K, A, N) <- (K > 0, K1 == K - 1, A1 == A + 1, c('go', K1, A1, N))
c('other', _, N, N),
```

`c('go', 100000, 0, N)` peaks at about 400 MB traced.  In the seam `==`
lowers to a CLP(FD) equation (`$fd_eq`, IR `FDCompare`), and
`_collect_bound_vars_ir` (`clausal/logic/compiler/tro.py`) does not count
its target as bound, so `_tro_args_safe_ir` refuses the clause.  Writing
the same steps as `K1 is ++(K - 1)` makes it eligible and the loop runs in
constant space (`tests/fixtures/bucket_tro.seam`).

## Fix

Treat the variable side of an `FDCompare` equation like an unbound
head variable: a tail position it reaches gets the runtime `$is_var` check
(the `allow_head_vars` path), so an equation that left it unbound takes the
ordinary call.
