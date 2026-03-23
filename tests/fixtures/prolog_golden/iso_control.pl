:- module(iso_control, [test/1]).

choose(X, _, X).

choose(_, Y, Y).

safe_max(X, Y, X) :-
    X >= Y.

safe_max(X, Y, Y) :-
    Y > X.

test("conjunction binds two vars") :-
    X = 1,
    Y = 2,
    X == 1,
    Y == 2.

test("conjunction fails if first fails") :-
    \+ (a = b, X = 1).

test("conjunction fails if second fails") :-
    \+ (X = 1, a = b).

test("triple conjunction") :-
    X = 1,
    Y = 2,
    Z = 3,
    R is X + Y + Z,
    R == 6.

test("disjunction first succeeds") :-
    X = 1 ; X = 2.

test("disjunction first fails, second succeeds") :-
    a = b ; X = 1.

test("disjunction both fail") :-
    \+ (a = b ; c = d).

test("not: failed unification succeeds") :-
    \+ 1 = 2.

test("not: successful unification fails") :-
    \+ \+ 1 = 1.

test("not: member absent") :-
    \+ in(d, [a, b, c]).

test("not: member present fails") :-
    \+ \+ in(b, [a, b, c]).

test("double negation: not not (1=1)") :-
    \+ \+ 1 = 1.

test("and + or: (X=1 and Y=a) or (X=2 and Y=b)") :-
    X = 1, Y = a ; X = 2, Y = b.

test("not + member: d not in list") :-
    \+ in(d, [a, b, c]).

test("conjunction + negation") :-
    X = 5,
    \+ X = 3,
    X == 5.

test("choose picks first") :-
    choose(1, 2, 1).

test("choose picks second") :-
    choose(1, 2, 2).

test("choose with atoms") :-
    choose(a, b, a).

test("safe_max: first is larger") :-
    safe_max(5, 3, M),
    M == 5.

test("safe_max: second is larger") :-
    safe_max(2, 7, M),
    M == 7.

test("safe_max: equal") :-
    safe_max(4, 4, M),
    M == 4.
