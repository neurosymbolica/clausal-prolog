:- module(iso_term_manipulation, [test/1]).

test("construct atom: functor(T, a, 0)") :-
    functor(T, a, 0),
    T == a.

test("decompose atom: functor('Hello', Name, Arity)") :-
    functor(hello, N, A),
    N == hello,
    A == 0.

test("decompose empty string") :-
    functor("", N, A),
    N == "",
    A == 0.

test("construct atom from list: T =.. ['a']") :-
    unpack(T, [a]),
    T == a.

test("decompose atom: 'a' =.. X") :-
    unpack(a, X),
    X == [a].

test("decompose string: 'Hello' =.. X") :-
    unpack(hello, X),
    X == [hello].
