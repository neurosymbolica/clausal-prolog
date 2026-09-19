:- use_module(library(clpz), [(#=)/2]).

fib(0, 0).

fib(1, 1).

fib(N, RESULT) :-
    N > 1,
    #=(N1, N - 1),
    #=(N2, N - 2),
    fib(N1, FIRST),
    fib(N2, SECOND),
    #=(RESULT, FIRST + SECOND).

test('fib 0') :-
    fib(0, 0).

test('fib 1') :-
    fib(1, 1).

test('fib 5') :-
    fib(5, RESULT),
    #=(RESULT, 5).

test('fib 10') :-
    fib(10, RESULT),
    #=(RESULT, 55).
