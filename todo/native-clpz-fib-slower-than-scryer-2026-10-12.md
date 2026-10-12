# Native `which_fib_is_55` takes 3.7 s; Scryer takes 1.0 s (2026-10-12)

The family example in `README.md` and `docs/clausal_prolog.md` (the `fib/2` over clpz) has
`test(which_fib_is_55) :- N in 0..20, fib(N, 55), N == 10.`. Measured standalone, it takes 3.7 s under
the native front end and 1.0 s in Scryer. Under `-j 6` it timed out at the parity harness's old 5 s
limit (`clausal/tools/pl_parity.py` now allows 30 s and records a timeout as an observation, never as
a difference).

Next: profile where the time goes (clpz propagation, the recursive `fib/2` search, or the native
lowering of `#=`/`#>=` goals), compare with the seam twin, and decide whether it is in the CLP(Z) core
or the front end.
