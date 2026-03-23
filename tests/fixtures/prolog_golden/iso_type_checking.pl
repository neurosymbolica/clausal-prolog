:- module(iso_type_checking, [test/1]).

is_bound_number(X) :-
    is_bound(X),
    is_number(X).

test("var: unbound var succeeds") :-
    is_var(X).

test("var: integer fails") :-
    \+ is_var(42).

test("var: atom fails") :-
    \+ is_var(hello).

test("var: bound var fails") :-
    X = 1,
    \+ is_var(X).

test("nonvar: integer succeeds") :-
    is_bound(42).

test("nonvar: atom succeeds") :-
    is_bound(hello).

test("nonvar: unbound var fails") :-
    \+ is_bound(X).

test("nonvar: bound var succeeds") :-
    X = 1,
    is_bound(X).

test("nonvar: list succeeds") :-
    is_bound([1, 2]).

test("atom: string succeeds") :-
    is_str(hello).

test("atom: empty string succeeds") :-
    is_str("").

test("atom: integer fails") :-
    \+ is_str(1).

test("atom: unbound var fails") :-
    \+ is_str(X).

test("atom: list fails") :-
    \+ is_str([]).

test("integer: positive") :-
    is_int(1).

test("integer: zero") :-
    is_int(0).

test("integer: large") :-
    is_int(100000000000000000000).

test("integer: string fails") :-
    \+ is_int("1").

test("integer: var fails") :-
    \+ is_int(X).

test("number: integer") :-
    is_number(42).

test("number: float") :-
    is_number(3.14).

test("number: string fails") :-
    \+ is_number("42").

test("number: var fails") :-
    \+ is_number(X).

test("string: str succeeds") :-
    is_str(hello).

test("string: empty str") :-
    is_str("").

test("string: int fails") :-
    \+ is_str(42).

test("string: var fails") :-
    \+ is_str(X).

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
    is_ground(42).

test("ground: string") :-
    is_ground(abc).

test("ground: ground list") :-
    is_ground([1, 2, 3]).

test("ground: empty list") :-
    is_ground([]).

test("ground: var fails") :-
    \+ is_ground(X).

test("is_bound_number: integer") :-
    is_bound_number(42).

test("is_bound_number: float") :-
    is_bound_number(3.14).

test("is_bound_number: string fails") :-
    \+ is_bound_number("42").

test("is_bound_number: unbound fails") :-
    \+ is_bound_number(X).
