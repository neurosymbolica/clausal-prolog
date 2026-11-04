% A restart beside a later clause whose head has a pattern where the
% restarting head has one too (tests/test_tro_clause_order.py): where the
% restarting head's term is ground, the later head binds nothing of the
% call, so the restart needs no run-time check there.
:- module(tro_clause_order_patterns, [ls/2, gc/2, walk/3, gl/4, run_b/1]).
:- use_module(library(freeze)).
:- dynamic(ev/1).
ls([], N) :- N > 0, M is N - 1, ls([], M).
ls([], N) :- N =< 0.
gc(f(1), N) :- N > 0, M is N - 1, gc(f(1), M).
gc(f(1), N) :- N =< 0.
% A evaluated by is/2: ground at the restart; R checked at run time.
walk(s(A), N, R) :- N > 0, M is N - 1, A1 is A + 1, walk(s(A1), M, R).
walk(s(A), N, A) :- N =< 0.
gl(_, N, X, seven(N)) :- X == 7.
gl([], N, X, R) :- N > 0, M is N - 1, gl([], M, X, R).
gl([], N, X, zero(N)) :- N =< 0.
gl([_|T], N, X, R) :- gl(T, N, X, R).
% A constant inside the later head binds into the call's argument: Y
% frozen inside f(Y) wakes at each level, after the answer (Scryer).
b(N, X) :- N > 0, M is N - 1, b(M, X).
b(N, f(0)) :- N =< 0.
log(E) :- assertz(ev(E)).
run_b(L) :- retractall(ev(_)), findall(_, (freeze(Y, log(woke)), b(2, f(Y)), log(answer)), _), findall(E, ev(E), L).
