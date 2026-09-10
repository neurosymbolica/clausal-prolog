squares(NUMBERS, SQUARES) :-
    findall(SQUARE, (member(X, NUMBERS), SQUARE =:= X * X), SQUARES).

positives(NUMBERS, POSITIVES) :-
    findall(X, (member(X, NUMBERS), X > 0), POSITIVES).

unique_members(NUMBERS, UNIQUE) :-
    setof(X, member(X, NUMBERS), UNIQUE).

all_positive(NUMBERS) :-
    forall(member(X, NUMBERS), X > 0).

test(squares) :-
    squares([1, 2, 3], SQUARES),
    SQUARES == [1, 4, 9].

test(positives) :-
    positives([-1, 2, -3, 4], POSITIVES),
    POSITIVES == [2, 4].

test('unique members') :-
    unique_members([1, 2, 1, 3, 2], UNIQUE),
    UNIQUE == [1, 2, 3].

test('all positive') :-
    all_positive([1, 2, 3]).

test('all positive fails: [1,-2,3]') :-
    \+ all_positive([1, -2, 3]).

test('findall basic: member of [1,2,3]') :-
    findall(X, member(X, [1, 2, 3]), L),
    L == [1, 2, 3].

test('findall with filter: X > 1') :-
    findall(X, (member(X, [1, 2, 3]), X > 1), L),
    L == [2, 3].

test('findall empty: no solutions yields []') :-
    findall(_X_UNUSED, false, L),
    L == [].

test('findall cartesian product') :-
    findall([X, Y], (member(X, [a, b]), member(Y, [1, 2])), L),
    L == [[a, 1], [a, 2], [b, 1], [b, 2]].

test('findall no side effects on outer vars') :-
    findall(X, member(X, [10, 20]), L),
    L == [10, 20].

test('findall nested: outer + inner') :-
    findall([Y, INNER], (member(Y, [10, 20]), findall(X, member(X, [1, 2]), INNER)), L),
    L == [[10, [1, 2]], [20, [1, 2]]].

test('bagof basic') :-
    bagof(X, member(X, [1, 2]), L),
    L == [1, 2].

test('bagof fails on empty') :-
    \+ bagof(_X_UNUSED, false, _).

test('setof deduplicates') :-
    setof(X, member(X, [1, 1, 2, 2, 3]), L),
    L == [1, 2, 3].

test('setof fails on empty') :-
    \+ setof(_X_UNUSED, false, _).

test('forall positive elements') :-
    forall(member(X, [2, 4, 6]), X > 0).

test('forall fails with negative') :-
    \+ forall(member(X, [2, -1, 6]), X > 0).

test('forall vacuously true when cond fails') :-
    forall(false, _X_UNUSED > 0).
