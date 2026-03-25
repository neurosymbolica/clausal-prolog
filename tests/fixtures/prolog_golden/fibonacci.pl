fib(0, 0).

fib(1, 1).

fib(N, Result) :-
    N > 1,
    N1 is N - 1,
    N2 is N - 2,
    fib(N1, First),
    fib(N2, Second),
    Result is First + Second.

test("fib 0") :-
    fib(0, 0).

test("fib 1") :-
    fib(1, 1).

test("fib 5") :-
    fib(5, Result),
    Result == 5.

test("fib 10") :-
    fib(10, Result),
    Result == 55.
