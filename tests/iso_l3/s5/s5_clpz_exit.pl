% Slice 5 exit rulebase: library(clpz) under Scryer's names.  Each case/2
% row is the findall/3 of one query; tests/iso_l3/test_l3_s5_exit.py runs
% this file natively and through Scryer and compares every row.
:- use_module(library(clpz)).
:- use_module(library(lists)).

% formal/2: the formal of a caught error, as Name-FirstArgument (or the
% atom itself), so the comparison does not depend on error contexts.
formal(E, E) :- atom(E).
formal(E, F-K) :- compound(E), E =.. [F, K|_].

err(G, F) :- catch((G, F = none), error(E, _), formal(E, F)).

% label/1 called directly (not through call/N): Scryer's label/1
label_err(F) :- catch((label([_]), F = none), error(E, _), formal(E, F)).
label_err(F) :- catch((Z #> 3, label([Z]), F = none), error(E, _), formal(E, F)).
label_err(F) :- catch((label(foo), F = none), error(E, _), formal(E, F)).

% ins/2 on a list, then label/1 (leftmost, up)
case(c01_ins_label, L) :- findall([X,Y], ([X,Y] ins 0..1, label([X,Y])), L).
% a domain with \/
case(c02_union_domain, L) :- findall(X, (X in 1..3 \/ 5..7 \/ 9, label([X])), L).
% a linear system over #=
case(c03_linear, L) :-
    findall([X,Y], ([X,Y] ins 0..10, X + Y #= 10, X - Y #= 4, label([X,Y])), L).
% label/1's answer order is leftmost-first
case(c04_label_order, L) :-
    findall([X,Y], (X in 1..3, Y in 1..2, label([X,Y])), L).
% labeling: down
case(c05_down, L) :- findall(X, (X in 1..4, labeling([down], [X])), L).
% labeling: ff (smallest domain first, step)
case(c06_ff, L) :-
    findall([X,Y], (X in 1..3, Y in 1..2, labeling([ff], [X,Y])), L).
% reified #<==> with a comparison
case(c07_reify_iff, L) :-
    findall([X,B], (X in 0..5, B #<==> (X #> 3), label([X])), L).
% #\/ as a goal
case(c08_or, L) :- findall(X, (X in 0..5, (X #= 1) #\/ (X #= 4), label([X])), L).
% #==> as a goal
case(c09_implies, L) :-
    findall([X,Y], ([X,Y] ins 0..3, (X #> 2) #==> (Y #= 0), label([X,Y])), L).
% #\ (negation) as a goal
case(c10_not, L) :- findall(X, (X in 0..3, #\ (X #= 2), label([X])), L).
% a reified conjunction
case(c11_reify_and, L) :-
    findall([X,B], (X in 0..6, B #<==> ((X #> 1) #/\ (X #< 4)), label([X])), L).
% #\ (xor) as a goal, labeled by bisection
case(c12_xor_bisect, L) :-
    findall([X,Y], ([X,Y] ins 0..2, (X #= 1) #\ (Y #= 1), labeling([bisect], [X,Y])), L).
% a reified domain membership, and #<== with the B bound first
case(c13_reify_in, L) :-
    findall([X,B], (X in 0..6, B #<==> (X in 2..4 \/ 6), label([X,B])), L).
case(c14_rimplies, L) :-
    findall([X,Y], ([X,Y] ins 0..2, (X #= 2) #<== (Y #= 1), labeling([max, down], [X,Y])), L).
% sum and ordering constraints over a list, labeling with min + enum
case(c15_sum, L) :-
    findall(Vs, (Vs = [A,B,C], Vs ins 0..2, A + B + C #= 3, A #< B, labeling([min, enum], Vs)), L).
% membership of an integer
case(c16_int_in, L) :- findall(X, (member(X, [0,3,5,8]), X in 1..5), L).
% errors: formal terms as Scryer's clpz raises them
case(c17_errors, L) :-
    findall(F, (member(G, [X #= a, X #= _ * foo, _ in a..3, _ in 1..sup_x,
                           a in 1..3, foo ins 0..1, [_|_] ins 0..1,
                           labeling([bogus], [1]), labeling([up, down], [1]),
                           labeling([ff, ff], [1]), labeling([upto_ground], [1]),
                           labeling(foo, [1]), labeling([bogus], [_]),
                           labeling([], [_]), (Z #> 3, labeling([], [Z])),
                           _ #<==> 2]),
                err(G, F)), L).
case(c18_label_errors, L) :- findall(F, label_err(F), L).
% bisection over a domain below zero (Scryer's split point truncates)
case(c19_bisect_negative, L) :-
    findall([X,Y], (X in -5..0, Y in 0..2, labeling([ff, bisect], [X,Y])), L).
