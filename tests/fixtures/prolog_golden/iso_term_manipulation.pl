:- module(iso_term_manipulation, [test/1]).

:- use_module(library(clpz), [(#=)/2]).

test('construct atom: functor(T, a, 0)') :-
    functor(_t, a, 0),
    _t == a.

test('decompose atom: functor(\'hello\', Name, Arity)') :-
    functor(hello, _n, _a),
    _n == hello,
    #=(_a, 0).

test('decompose empty atom') :-
    functor('', _n, _a),
    _n = '',
    #=(_a, 0).

test('decompose empty list') :-
    functor([], _n2, _a2),
    _n2 = [],
    #=(_a2, 0).

test('construct atom from list: T =.. [\'a\']') :-
    unpack(_t, [a]),
    _t == a.

test('decompose atom: \'a\' =.. X') :-
    unpack(a, _x),
    _x == [a].

test('decompose string: \'hello\' =.. X') :-
    unpack(hello, _x),
    _x == [hello].

test('decompose int: functor(1, N, A)') :-
    functor(1, _n_UNUSED, _a),
    #=(_a, 0).

test('decompose float: functor(1.0, N, A)') :-
    functor(1.0, _n_UNUSED, _a),
    #=(_a, 0).

test('unpack int: 1 =.. X gives [1]') :-
    unpack(1, _x),
    _x == [1].
