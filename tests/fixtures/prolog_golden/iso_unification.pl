:- module(iso_unification, [test/1]).

:- use_module(library(clpz), [(#=)/2]).

same_value(X, Y) :-
    X = Y,
    X == Y.

test('atom unifies with itself') :-
    _x = a,
    _x == a.

test('var unifies with atom') :-
    _x = a,
    _x == a.

test('var unifies with integer') :-
    _x = 42,
    #=(_x, 42).

test('var unifies with list') :-
    _x = [1, 2, 3],
    _x == [1, 2, 3].

test('different atoms fail') :-
    \+ (_x = a, _x = b, _x == b).

test('list unification') :-
    _x = [a],
    _x == [a].

test('empty lists unify') :-
    _x = [],
    _x == [].

test('different atoms: is not succeeds') :-
    _x = a,
    dif(_x, b).

test('same atom: is not fails') :-
    _x = a,
    \+ dif(_x, a).

test('same atom ==') :-
    a == a.

test('different atoms == fails') :-
    a \== b.

test('same integer ==') :-
    #=(42, 42).

test('bound var == value') :-
    _x = hello,
    _x == hello.

test('different atoms !=') :-
    a \== b.

test('same atom != fails') :-
    \+ a \== a.

test('same_value: integers') :-
    same_value(42, 42).

test('same_value: strings') :-
    same_value(hello, hello).

test('same_value: lists') :-
    same_value([1, 2], [1, 2]).

test('integer unifies with itself') :-
    X = 1,
    #=(X, 1).

test('float unifies with itself') :-
    X = 1.0,
    #=(X, 1.0).

test('var unifies with var (aliasing)') :-
    X = Y,
    X == Y.

test('different integers fail to unify') :-
    \+ (X = 1, X = 2).

test('int vs float (clausal quirk): 1 is 1.0') :-
    X = 1,
    X = 1.0.

test('list unify with var') :-
    X = [1, 2, 3],
    X == [1, 2, 3].

test('arithmetic term is structural: 1+2 != 3 in unify') :-
    \+ (X = 1 + 2, X = 3).

test('var/atom is not: succeeds with constraint') :-
    dif(_X_UNUSED, a).

test('different numbers: 1 is not 2') :-
    dif(1, 2).

test('int == float (Python quirk)') :-
    #=(1, 1.0).

test('two fresh vars: X == Y (CLP(FD) posts)') :-
    #=(_X_UNUSED, _Y_UNUSED).

test('same var: X == X') :-
    #=(X, X).

test('var != atom raises catchable type_error') :-
    catch((_X_UNUSED \== a, false), _, true).

test('two fresh vars: X != Y') :-
    _X_UNUSED \== _Y_UNUSED.

test('structural_eq: a == a') :-
    structural_eq(a, a).

test('structural_eq: a != b fails') :-
    \+ structural_eq(a, b).

test('structural_eq: 42 == 42') :-
    structural_eq(42, 42).

test('structural_eq: same var') :-
    X = Y,
    structural_eq(X, Y).

test('structural_eq: distinct unbound vars fail') :-
    \+ structural_eq(_X_UNUSED, _Y_UNUSED).

test('structural_eq: unbound var vs atom fails') :-
    \+ structural_eq(_X_UNUSED, a).

test('structural_eq: nested lists') :-
    structural_eq([1, [2, 3]], [1, [2, 3]]).

test('structural_eq: distinct lists fail') :-
    \+ structural_eq([1, 2], [1, 3]).

test('structural_neq: same var fails') :-
    X = Y,
    \+ \+ structural_eq(X, Y).
