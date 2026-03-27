:- module(iso_type_checking, [test/1]).

is_bound_number(X) :-
    nonvar(X),
    number(X).

test("var: unbound var succeeds") :-
    var(X).

test("var: integer fails") :-
    \+ var(42).

test("var: atom fails") :-
    \+ var(hello).

test("var: bound var fails") :-
    X = 1,
    \+ var(X).

test("nonvar: integer succeeds") :-
    nonvar(42).

test("nonvar: atom succeeds") :-
    nonvar(hello).

test("nonvar: unbound var fails") :-
    \+ nonvar(X).

test("nonvar: bound var succeeds") :-
    X = 1,
    nonvar(X).

test("nonvar: list succeeds") :-
    nonvar([1, 2]).

test("atom: declared atom succeeds") :-
    atom(hello).

test("atom: declared atom Abc") :-
    atom(abc).

test("atom: string fails") :-
    \+ atom("hello").

test("atom: integer fails") :-
    \+ atom(1).

test("atom: unbound var fails") :-
    \+ atom(X).

test("str: plain string succeeds") :-
    atom("hello").

test("str: empty string succeeds") :-
    atom("").

test("str: declared atom fails") :-
    \+ atom(hello).

test("str: integer fails") :-
    \+ atom(1).

test("str: unbound var fails") :-
    \+ atom(X).

test("str: list fails") :-
    \+ atom([]).

test("integer: positive") :-
    integer(1).

test("integer: zero") :-
    integer(0).

test("integer: large") :-
    integer(100000000000000000000).

test("integer: string fails") :-
    \+ integer("1").

test("integer: var fails") :-
    \+ integer(X).

test("number: integer") :-
    number(42).

test("number: float") :-
    number(3.14).

test("number: string fails") :-
    \+ number("42").

test("number: var fails") :-
    \+ number(X).

test("callable: declared atom") :-
    callable(hello).

test("callable: string") :-
    callable("hello").

test("callable: int fails") :-
    \+ callable(42).

test("callable: var fails") :-
    \+ callable(X).

test("is_list: list") :-
    is_list([1, 2, 3]).

test("is_list: empty") :-
    is_list([]).

test("is_list: nested") :-
    is_list([[1], [2]]).

test("is_list: string fails") :-
    \+ is_list(hello).

test("is_list: int fails") :-
    \+ is_list(42).

test("is_list: var fails") :-
    \+ is_list(X).

test("ground: integer") :-
    ground(42).

test("ground: declared atom") :-
    ground(abc).

test("ground: ground list") :-
    ground([1, 2, 3]).

test("ground: empty list") :-
    ground([]).

test("ground: var fails") :-
    \+ ground(X).

test("is_bound_number: integer") :-
    is_bound_number(42).

test("is_bound_number: float") :-
    is_bound_number(3.14).

test("is_bound_number: string fails") :-
    \+ is_bound_number("42").

test("is_bound_number: unbound fails") :-
    \+ is_bound_number(X).
