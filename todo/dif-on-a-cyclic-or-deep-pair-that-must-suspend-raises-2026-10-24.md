# `dif/2` that must SUSPEND on a cyclic or very deep pair raises `resource_error(stack)`

Filed 2026-10-24 by the review of `fix/cyclic-terms-2026-10-24`
(d8d1693f).  Scryer suspends the constraint; this engine raises
`error(resource_error(stack), _)`.  Before that branch it raised a raw
Python `RecursionError`, so the branch is already better; the answer is
still not Scryer's.

## Repro

```prolog
nest(0, T, T).
nest(N, T, f(R)) :- N > 0, N1 is N-1, nest(N1, T, R).

r1 :- X = f(X, V), Y = f(Y, a), dif(X, Y).                      % Scryer: suspends (V \= a)
r2 :- nest(100000, V, T1), nest(100000, a, T2), dif(T1, T2).     % Scryer: suspends
```

Both raise `error(resource_error(stack), _)` under `catch/3`.  A pair that
DECIDES -- two cyclic terms that are one rational tree (`dif` fails), or
two that differ in a ground position (`dif` succeeds with nothing to
suspend on) -- is answered as Scryer answers it (the `u20` row of
`tests/iso/test_cyclic_terms_scryer.py`).

## Cause

`dif/2` first runs its trial unify (`c_structural_unify_oc`, which since
2026-10-24 unwinds past its depth threshold to the engine's rational-tree
unify and so terminates), and when that unify SUCCEEDS with bindings it
collects the pair's free variables to attach the constraint to:
`collect_walk` in `clausal/logic/_constraints_dif.c:81`, a recursive
descent capped at `MAX_DEPTH` (50000) with no cycle memo.  On a cyclic
pair it re-enters the cycle until the cap; on a 100k-deep pair it reaches
the cap.  The Python twin (`constraints._collect_free_vars`) recurses the
same way.

## Fix sketch

The treatment `term_variables/2` got the same day: past a depth threshold
answer a "deep" code that unwinds to the depth-0 entry, which then runs an
iterative walk with a visited set over compound addresses (see
`occurs_check_iterative` in `variables/_variables.c`, or
`rational_walk.collect_vars_iterative`).  The variables collected are the
same; only the walk changes.  Pin `r1`/`r2` above as rows of
`tests/iso/test_cyclic_terms_scryer.py` (`dif` needs
`:- use_module(library(dif))` on the Scryer side, already in the prelude).
