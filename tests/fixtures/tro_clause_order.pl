% Last-call optimisation in a predicate that is not indexed: a tail call
% restarts the predicate in place only where no later clause can answer
% first (tests/test_tro_clause_order.py).
:- module(tro_clause_order_pl, [p/2, cnt/1, len/3, down/1, up/2]).
% A later clause answers at every step: the tail is an ordinary call.
p(N, X) :- N > 0, M is N - 1, p(M, X).
p(N, N).
% The later clause's first argument keys it out while N > 0.
cnt(N) :- N > 0, M is N - 1, cnt(M).
cnt(0).
% The later head cannot unify with [_|_].
len([_|T], N0, N) :- N1 is N0 + 1, len(T, N1, N).
len([], N, N).
% The later clause's first goal fails where N > 0 held.
down(N) :- N > 0, M is N - 1, down(M).
down(N) :- N =< 0.
% The later head needs I and N identical, which I < N rules out.
up(I, N) :- I < N, I1 is I + 1, up(I1, N).
up(N, N).
