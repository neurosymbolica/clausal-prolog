squares(Numbers, Squares) :-
    findall(Square, in(X, Numbers), Square is X * X, Squares).

positives(Numbers, Positives) :-
    findall(X, in(X, Numbers), X > 0, Positives).

unique_members(Numbers, Unique) :-
    setof(X, in(X, Numbers), Unique).

all_positive(Numbers) :-
    forall(in(X, Numbers), X > 0).

test("squares") :-
    squares([1, 2, 3], Squares),
    Squares == [1, 4, 9].

test("positives") :-
    positives([-1, 2, -3, 4], Positives),
    Positives == [2, 4].

test("unique members") :-
    unique_members([1, 2, 1, 3, 2], Unique),
    Unique == [1, 2, 3].

test("all positive") :-
    all_positive([1, 2, 3]).
