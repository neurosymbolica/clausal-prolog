% Later heads with a list pattern deeper than one cell: against a partial
% list [a|Z] they bind Z, waking a goal frozen on it before the guard fails
% -- as ISO runs them, after the tail call's answers
% (tests/test_tro_clause_order.py).
:- module(tro_clause_order_lists_pl, [run_q/2]).
:- use_module(library(freeze)).
:- dynamic(ev/1).
q(X, N) :- N > 0, M is N - 1, q(X, M).
q([_], N) :- N =< 0.
q2(X, N) :- N > 0, M is N - 1, q2(X, M).
q2([_, _], N) :- N =< 0.
q3(X, N) :- N > 0, M is N - 1, q3(X, M).
q3([_, _|_], N) :- N =< 0.
log(E) :- assertz(ev(E)).
run_q(Which, L) :-
    retractall(ev(_)),
    \+ (freeze(Z, log(woke)), L0 = [a|Z], go(Which, L0), log(answer), fail),
    findall(E, ev(E), L).
go(q, X) :- q(X, 2).
go(q2, X) :- q2(X, 2).
go(q3, X) :- q3(X, 2).
