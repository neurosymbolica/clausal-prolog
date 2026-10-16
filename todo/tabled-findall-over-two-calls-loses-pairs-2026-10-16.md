# WRONG ANSWER: findall over two calls to one non-recursive tabled predicate loses pairs (2026-10-16)

On canonical 0731c12e, no cut involved:

```prolog
:- table(t/1).
t(1). t(2). t(3).
?- findall(X-Y, (t(X), t(Y)), L), length(L, N).
% Clausal: N = 6, L = [1-1,2-1,2-2,3-1,3-2,3-3]   (missing 1-2, 1-3, 2-3)
% Correct: N = 9 (as without tabling)
```

Cause, from the cut series' final re-review: the tabled call hands back answers before its table is complete. The inner t(Y) consumes the incomplete table, which holds only the answers found so far.

Fix candidate: complete a non-recursive tabled call's table before its first answer (XSB local scheduling), reusing the deferral path in make_tabled_wrapper_trampoline (tabling.py ~1651/1702). It was prototyped as a two-line change during the cut-series review. It is the same change as option B of the cut-over-table decision pending with Mike. Needs a corpus scorer re-run, since answer order becomes table order.
