:- module(sw_arith, [mx/1, mn/1, ab/1]).
mx(X) :- X is max(3, 5).
mn(X) :- X is min(3, 5).
ab(X) :- X is abs(-4).
