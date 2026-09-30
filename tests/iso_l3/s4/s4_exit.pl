% Slice 4's exit rulebase (plan native-iso-reader-step2 §4 Slice 4): one
% case(Name, L) row per construct, L the findall/3 of its answers in order.
% Loaded by the native front end AND run through Scryer (the oracle test);
% s4_exit_twin.seam holds the same rows as a seam author writes them.
% Every transition construct below is PLANTED: the lint must count exactly
% these sites (test_l3_s4_exit.PLANTED).
:- use_module(library(lists)).
:- use_module(library(iso_ext)).
:- use_module(library(dif)).
:- use_module(library(reif)).

p(1, a). p(2, a). p(3, b).

add(X, A0, A) :- A is A0 + X.
add2(X, Y, A0, A) :- A is A0 + X * Y.
add3(X, Y, Z, A0, A) :- A is A0 + X + Y + Z.
sum3(A, B, C) :- C is A + B.
sum4(A, B, C, D) :- D is A + B + C.
sum5(A, B, C, D, E) :- E is A + B + C + D.
sum6(A, B, C, D, E, F) :- F is A + B + C + D + E.
two(1). two(2).

% D40: a user-defined true/N and false/N (N >= 1).
true(X) :- X = 1.
false(X, Y) :- Y is X + 1.

bad_t(_).
bad2_t(foo).

case(c01_setof_caret, L) :- findall(S, setof(X, Y^p(X, Y), S), L).
case(c02_bagof_groups, L) :- findall(Y-S, bagof(X, p(X, Y), S), L).
case(c03_findall4, L) :- findall(R, findall(X, member(X, [1, 2]), R, [3]), L).
case(c04_forall, L) :-
    findall(R, (member(R, [yes, no]), forall(member(X, [1, 2]), X > 0), R == yes), L).
case(c05_forall_fails, L) :- findall(ok, forall(member(X, [1, 2]), once(X > 1)), L).
case(c06_once, L) :- findall(X, once(member(X, [a, b])), L).
case(c07_catch_throw, L) :- findall(E, catch(throw(my(err)), E, true), L).
case(c08_maplist2, L) :- findall(X-Y, maplist(two, [X, Y]), L).
case(c09_maplist3, L) :- findall(R, maplist(add(1), [1, 2], R), L).
case(c10_maplist4to7, L) :-
    findall(R3-R4-R5-R6,
            ( maplist(sum3, [1, 2], [10, 20], R3),
              maplist(sum4, [1], [2], [3], R4),
              maplist(sum5, [1], [2], [3], [4], R5),
              maplist(sum6, [1], [2], [3], [4], [5], R6) ), L).
case(c11_foldl4to6, L) :-
    findall(S4-S5-S6,
            ( foldl(add, [1, 2, 3], 0, S4),
              foldl(add2, [1, 2], [3, 4], 0, S5),
              foldl(add3, [1], [2], [3], 0, S6) ), L).
case(c12_dif, L) :- findall(X, (dif(X, a), member(X, [a, b, c])), L).
case(c13_naf, L) :- findall(X, (member(X, [1, 2, 3]), \+ X = 2), L).
case(c14_if_eq, L) :- findall(X-R, (if_(X = a, R = y, R = n), member(X, [a, b])), L).
case(c15_if_dif, L) :- findall(X-R, (if_(dif(X, a), R = y, R = n), member(X, [a, b])), L).
case(c16_if_and, L) :-
    findall(X-Y-R, (if_((X = a, Y = b), R = y, R = n),
                    member(X, [a, c]), member(Y, [b, d])), L).
case(c17_if_or, L) :-
    findall(X-Y-R, (if_((X = a ; Y = b), R = y, R = n),
                    member(X, [a, c]), member(Y, [b, d])), L).
case(c18_if_closure, L) :-
    findall(E-R, (member(E, [a, c]), if_(memberd_t(E, [a, b]), R = y, R = n)), L).
case(c19_memberd_t_true, L) :- findall(ok, memberd_t(b, [a, b], true), L).
case(c20_memberd_t_enum, L) :-
    findall(X-T, (memberd_t(X, [a, b], T), member(X, [a, b, c])), L).
case(c21_tfilter, L) :-
    findall(X-Y-Es, (tfilter(=(a), [X, Y], Es), member(X, [a, b]), member(Y, [a, b])), L).
case(c22_tfilter_dif, L) :- findall(Fs, tfilter(dif(a), [a, b, a, c], Fs), L).
case(c23_tpartition, L) :- findall(Ts-Fs, tpartition(=(a), [a, b, a, c], Ts, Fs), L).
case(c24_tmember, L) :- findall(ok, tmember(=(b), [a, b]), L).
case(c25_tmember_t, L) :- findall(T, (member(E, [b, z]), tmember_t(=(E), [a, b], T)), L).
case(c26_cond_t, L) :- findall(X-T, (cond_t(X = a, true, T), member(X, [a, b])), L).
case(c27_eq3_dif3_order, L) :- findall(T1-T2, (=(_, a, T1), dif(_, a, T2)), L).
case(c28_if_errors, L) :-
    findall(F, ( member(G, [bad_t, bad2_t]),
                 catch(if_(G, true, true), error(F, _), true) ), L).
case(c29_truth_data, L) :- findall(X, (X = true ; X = false), L).
case(c30_user_true_n, L) :- findall(A-B-C, (true(A), call(true, B), false(1, C)), L).
case(c31_memberchk, L) :- findall(X, memberchk(X, [a, b]), L).
case(c32_findall_backdoor, L) :- findall(X, (member(X, [1, 2]), findall(_, X > 1, [])), L).
case(c33_naf_as_data, L) :- findall(R, (G = (\+ fail), call(G), R = ok), L).
