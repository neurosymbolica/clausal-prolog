% A predicate dispatched on a list argument answers in clause order: a
% clause with a variable there, written before the [] and [_|_] clauses,
% answers first (tests/test_list_dispatch_clause_order.py).
:- module(list_dispatch_order_pl, [lo/2, gz/4]).
lo(_, X) :- X = any.
lo([], X) :- X = nil.
lo([_|_], X) :- X = cons.
lo(_, X) :- X = last.
gz(_, N, X, seven(N)) :- X == 7.
gz([], N, X, R) :- N > 0, M is N - 1, gz([], M, X, R).
gz([], N, _, zero(N)) :- N =< 0.
gz([_|T], N, X, R) :- gz(T, N, X, R).
