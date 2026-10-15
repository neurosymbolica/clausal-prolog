# setup_call_cleanup/3 runs Cleanup after the caller's continuation, not at the cut or at a deterministic exit

**Status: OPEN, not fixed in the `.pl` cut series** (final review I-2, 2026-10-16). Documented in docs/importing_prolog.md; pinned as `xfail(strict=True)` in `tests/iso_l3/test_l3_cut.py` (`test_a_pruned_setup_call_cleanup_runs_cleanup_at_the_cut`).

## What happens

`_compile_setup_call_cleanup` runs the Goal's sub-generator in a `for` loop whose body is the caller's continuation, and Cleanup sits in that loop's `finally`. So Cleanup runs only once the continuation is finished with the Goal. A cut is compiled as "run the rest of the clause and the caller's continuation, then leave", so `!` and `->` do not make it earlier.

```prolog
:- dynamic(cl/0).
chk(R) :- cl, R = early.
chk(R) :- \+ cl, R = late.
u :- setup_call_cleanup(true, member(_, [1,2]), assertz(cl)), !.
t21(R) :- retractall(cl), u, chk(R).                    % Clausal late, Scryer early
v :- ( setup_call_cleanup(true, member(_,[1,2]), assertz(cl)) -> true ; true ).
t22(R) :- retractall(cl), v, chk(R).                    % Clausal late, Scryer early
t24(R) :- retractall(cl), \+ \+ u, chk(R).              % Clausal late, Scryer early
t26(R) :- retractall(cl), setup_call_cleanup(true, true, assertz(cl)), chk(R).
                                                        % Clausal late, Scryer early
```

`once/1` over a setup_call_cleanup behaves the same, and so does a deterministic Goal (t26), on the base before the series, so this is not a regression. But `!`/`->` around a resource-holding call (open, read, close) is a common `.pl` idiom, and the stream stays open while the rest of the clause runs.

## To do

A real pruning mechanism: Cleanup must run when the Goal exits deterministically, and when a cut or commit prunes its choice points (Ulrich Neumerkel's setup_call_cleanup draft; Scryer). Exiting deterministically needs the Goal's sub-generator to report "no more choice points". Pruning needs the cut exit to close the generators it prunes, in order.
