:- module(iso_arithmetic, [test/1]).

double(X, Y) :-
    Y is X * 2.

square(X, Y) :-
    Y is X * X.

triangle_number(N, T) :-
    T is N * (N + 1) // 2.

test("addition: 1+2=3") :-
    X is 1 + 2,
    X == 3.

test("subtraction: 5-3=2") :-
    X is 5 - 3,
    X == 2.

test("multiplication: 3*4=12") :-
    X is 3 * 4,
    X == 12.

test("integer division: 7//2=3") :-
    X is 7 // 2,
    X == 3.

test("modulo: 7%2=1") :-
    X is 7 mod 2,
    X == 1.

test("power: 2**3=8") :-
    X is 2 ** 3,
    X == 8.

test("negation: -3") :-
    X is -3,
    X == -3.

test("nested: (2+3)*4=20") :-
    X is (2 + 3) * 4,
    X == 20.

test("float addition: 1.5+2.5=4.0") :-
    X is 1.5 + 2.5,
    X == 4.0.

test("double negation: --5=5") :-
    X is 5,
    X == 5.

test("subtraction negative: 3-5=-2") :-
    X is 3 - 5,
    X == -2.

test("negative floor div: -7//2=-4") :-
    X is -7 // 2,
    X == -4.

test("negative mod: -7%2=1") :-
    X is -7 mod 2,
    X == 1.

test("1 < 2") :-
    1 < 2.

test("not 2 < 1") :-
    \+ 2 < 1.

test("not 1 < 1") :-
    \+ 1 < 1.

test("1 <= 2") :-
    1 =< 2.

test("1 <= 1") :-
    1 =< 1.

test("2 > 1") :-
    2 > 1.

test("not 1 > 2") :-
    \+ 1 > 2.

test("2 >= 1") :-
    2 >= 1.

test("1 >= 1") :-
    1 >= 1.

test("1.5 < 2.5") :-
    1.5 < 2.5.

test("expression: 1+2 < 2+3") :-
    1 + 2 < 2 + 3.

test("expression: 1+2 <= 3") :-
    1 + 2 =< 3.

test("succ forward: succ(3,4)") :-
    succ(3, 4).

test("succ backward: succ(X,4)=3") :-
    succ(X, 4),
    X == 3.

test("succ zero: succ(0,1)") :-
    succ(0, 1).

test("plus forward: 2+3=5") :-
    plus(2, 3, 5).

test("plus backward x: X+3=5") :-
    plus(X, 3, 5),
    X == 2.

test("plus backward y: 2+Y=5") :-
    plus(2, Y, 5),
    Y == 3.

test("between check: 3 in 1..5") :-
    between(1, 5, 3).

test("between out of range") :-
    \+ between(1, 5, 6).

test("double 3 is 6") :-
    double(3, Y),
    Y == 6.

test("double 0 is 0") :-
    double(0, Y),
    Y == 0.

test("square 4 is 16") :-
    square(4, Y),
    Y == 16.

test("square 1 is 1") :-
    square(1, Y),
    Y == 1.

test("triangle 5 is 15") :-
    triangle_number(5, T),
    T == 15.

test("triangle 1 is 1") :-
    triangle_number(1, T),
    T == 1.

test("triangle 10 is 55") :-
    triangle_number(10, T),
    T == 55.
