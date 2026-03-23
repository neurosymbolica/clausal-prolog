fib(0, 0).

fib(1, 1).

fib(N, Result) :-
    N > 1,
    N1 is N - 1,
    N2 is N - 2,
    fib(N1, A),
    fib(N2, B),
    Result is A + B.
