:- module(iso_unification, [test/1]).

same_value(X, Y) :-
    X = Y,
    X == Y.

test("atom unifies with itself") :-
    X = a,
    X == a.

test("var unifies with atom") :-
    X = a,
    X == a.

test("var unifies with integer") :-
    X = 42,
    X == 42.

test("var unifies with list") :-
    X = [1, 2, 3],
    X == [1, 2, 3].

test("different atoms fail") :-
    \+ (X = a, X = b, X == b).

test("list unification") :-
    X = [a],
    X == [a].

test("empty lists unify") :-
    X = [],
    X == [].

test("different atoms: is not succeeds") :-
    X = a,
    dif(X, b).

test("same atom: is not fails") :-
    X = a,
    \+ dif(X, a).

test("same atom ==") :-
    a == a.

test("different atoms == fails") :-
    a \== b.

test("same integer ==") :-
    42 == 42.

test("bound var == value") :-
    X = hello,
    X == hello.

test("different atoms !=") :-
    a \== b.

test("same atom != fails") :-
    \+ a \== a.

test("same_value: integers") :-
    same_value(42, 42).

test("same_value: strings") :-
    same_value(hello, hello).

test("same_value: lists") :-
    same_value([1, 2], [1, 2]).
