% A TRO restart must not run a later clause ahead of the tail call's
% answers: binding a frozen argument there woke its goal early, and a goal
% that throws lost the answers (tests/test_tro_clause_order.py).
:- module(tro_clause_order_wake_pl, [run_w/1, run_w2/1, run_w3/1, first_w2/1, cnt/1]).
:- use_module(library(freeze)).
:- dynamic(ev/1).
% The later head binds X to 0 before its guard fails.
w(N, X) :- N > 0, M is N - 1, w(M, X).
w(N, 0) :- N =< 0.
w2(N, X) :- N > 0, M is N - 1, w2(M, X).
w2(N, X) :- N =:= 0, X = done.
w2(N, 0) :- N < 0.
% The later clause binds Y in its body, before its guard.
w3(N, X) :- N > 0, M is N - 1, w3(M, X).
w3(N, X) :- N =:= 0, X = done.
w3(N, Y) :- Y = 0, N < 0.
log(E) :- assertz(ev(E)).
check(X) :- X \== 0.
check(0) :- throw(oops).
run_w(L) :- retractall(ev(_)), \+ (freeze(X, log(woke)), w(2, X), log(answer), fail), findall(E, ev(E), L).
run_w2(L) :- retractall(ev(_)), \+ (freeze(X, log(woke)), w2(1, X), log(answer), fail), findall(E, ev(E), L).
run_w3(L) :- retractall(ev(_)), \+ (freeze(X, log(woke)), w3(1, X), log(answer), fail), findall(E, ev(E), L).
first_w2(X) :- freeze(X, check(X)), w2(1, X).
% Later clauses keyed by atoms, called with an integer: still restarts.
cnt(N) :- N > 0, M is N - 1, cnt(M).
cnt(x).
cnt(y).
