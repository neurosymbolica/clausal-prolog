:- module(sw_setof, [s/1, b/1]).
p(1, a).
p(2, a).
p(3, b).
s(L) :- setof(X, Y^p(X, Y), L).
b(L) :- bagof(X, Y^p(X, Y), L).
