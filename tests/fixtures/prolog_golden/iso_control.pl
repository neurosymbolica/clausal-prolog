:- module(iso_control, [test/1]).

parent(a, b).

parent(b, c).

parent(c, d).

parent(a, e).

ancestor(A, D) :-
    parent(A, D).

ancestor(A, D) :-
    parent(A, Z),
    ancestor(Z, D).

color(red).

color(green).

color(blue).

choose(X, _, X).

choose(_, Y, Y).

safe_max(X, Y, X) :-
    X >= Y.

safe_max(X, Y, Y) :-
    Y > X.

test('conjunction binds two vars') :-
    _x = 1,
    _y = 2,
    _x == 1,
    _y == 2.

test('conjunction fails if first fails') :-
    \+ (a = b, _x_UNUSED = 1).

test('conjunction fails if second fails') :-
    \+ (_x_UNUSED = 1, a = b).

test('triple conjunction') :-
    _x = 1,
    _y = 2,
    _z = 3,
    _x + _y + _z =:= 6.

test('disjunction first succeeds') :-
    _x = 1 ; _x = 2.

test('disjunction first fails, second succeeds') :-
    a = b ; _x_UNUSED = 1.

test('disjunction both fail') :-
    \+ (a = b ; c = d).

test('not: failed unification succeeds') :-
    \+ 1 = 2.

test('not: successful unification fails') :-
    \+ \+ 1 = 1.

test('not: member absent') :-
    \+ member(d, [a, b, c]).

test('not: member present fails') :-
    \+ \+ member(b, [a, b, c]).

test('double negation: not not (1=1)') :-
    \+ \+ 1 = 1.

test('and + or: (X=1 and Y=a) or (X=2 and Y=b)') :-
    _x = 1, _y = a ; _x = 2, _y = b.

test('not + member: d not in list') :-
    \+ member(d, [a, b, c]).

test('conjunction + negation') :-
    _x = 5,
    \+ _x = 3,
    _x == 5.

test('choose picks first') :-
    choose(1, 2, 1).

test('choose picks second') :-
    choose(1, 2, 2).

test('choose with atoms') :-
    choose(a, b, a).

test('safe_max: first is larger') :-
    safe_max(5, 3, _m),
    _m == 5.

test('safe_max: second is larger') :-
    safe_max(2, 7, _m),
    _m == 7.

test('safe_max: equal') :-
    safe_max(4, 4, _m),
    _m == 4.

test('true succeeds (1 == 1)') :-
    1 == 1.

test('fail fails: not False') :-
    \+ false.

test('conjunction backtracks: 2x2 = 4 solutions') :-
    findall([X, Y], (member(X, [1, 2]), member(Y, [a, b])), L),
    length(L, 4),
    member([1, a], L),
    member([2, b], L).

test('disjunction yields 2 solutions') :-
    findall(X, (X = 1 ; X = 2), L),
    L == [1, 2].

test('disjunction with conjunction: 2 solutions') :-
    findall([X, Y], (X = 1, Y = a ; X = 2, Y = b), L),
    L == [[1, a], [2, b]].

test('naf does not bind: not(X is a) fails') :-
    \+ \+ _x_UNUSED = a.

test('color enumerates three') :-
    findall(X, color(X), L),
    L == [red, green, blue].

test('ancestor: direct parent') :-
    ancestor(a, b).

test('ancestor: transitive') :-
    ancestor(a, d).

test('ancestor of a yields all descendants') :-
    findall(D, ancestor(a, D), L),
    sort(L, S),
    S == [b, c, d, e].
