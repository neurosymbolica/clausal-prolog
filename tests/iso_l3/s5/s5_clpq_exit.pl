% Slice 5 exit rulebase: library(clpq)'s {}/1.  Each case/2 row is the
% findall/3 of one query (see test_l3_s5_exit.py).
:- use_module(library(clpq)).

case(q01_system, L) :- findall([X,Y], {X + Y = 10, X - Y = 4}, L).
case(q02_rational, L) :- findall(X, {2*X = 3}, L).
case(q03_bounds, L) :- findall(X, {X >= 2, X =< 2}, L).
case(q04_exact_decimal, L) :- findall(X, {X = 15505/100}, L).
case(q05_infeasible, L) :- findall(X, {X > 1, X < 1}, L).
case(q06_negation, L) :- findall(X, {X = -(1/3) + 1, X =:= 2/3}, L).
