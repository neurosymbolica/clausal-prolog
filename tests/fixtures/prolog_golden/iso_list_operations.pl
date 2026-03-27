:- module(iso_list_operations, [test/1]).

palindrome(Xs) :-
    reverse(Xs, Xs).

sorted_asc([]).

sorted_asc([_]).

sorted_asc([A, B|Rest]) :-
    A =< B,
    sorted_asc([B|Rest]).

is_permutation(Xs, Ys) :-
    length(Xs, N),
    length(Ys, N),
    sort(Xs, S),
    sort(Ys, S).

test("in: found") :-
    member(b, [a, b, c]).

test("in: not found") :-
    \+ member(d, [a, b, c]).

test("in: empty list fails") :-
    \+ member(x, []).

test("in: integer") :-
    member(2, [1, 2, 3]).

test("not in: absent") :-
    \+ member(d, [a, b, c]).

test("not in: present fails") :-
    \+ \+ member(b, [a, b, c]).

test("not in: empty list") :-
    \+ member(x, []).

test("member: found") :-
    in(b, [a, b, c]).

test("member: not found") :-
    \+ in(d, [a, b, c]).

test("member: empty fails") :-
    \+ in(x, []).

test("memberchk: found") :-
    memberchk(b, [a, b, c]).

test("memberchk: not found") :-
    \+ memberchk(d, [a, b, c]).

test("append two lists") :-
    append([1, 2], [3, 4], [1, 2, 3, 4]).

test("append empty left") :-
    append([], [1, 2], [1, 2]).

test("append empty right") :-
    append([1, 2], [], [1, 2]).

test("append both empty") :-
    append([], [], []).

test("append binds result") :-
    append([1], [2], R),
    R == [1, 2].

test("length of 3") :-
    length([a, b, c], 3).

test("length empty") :-
    length([], 0).

test("length one") :-
    length([42], 1).

test("length binds") :-
    length([1, 2, 3], N),
    N == 3.

test("last element") :-
    last([1, 2, 3], 3).

test("last singleton") :-
    last([42], 42).

test("last empty fails") :-
    \+ last([], _).

test("reverse list") :-
    reverse([1, 2, 3], [3, 2, 1]).

test("reverse empty") :-
    reverse([], []).

test("reverse singleton") :-
    reverse([42], [42]).

test("reverse involution") :-
    reverse([1, 2, 3], R),
    reverse(R, Rr),
    Rr == [1, 2, 3].

test("nth0 first") :-
    nth0(0, [a, b, c], a).

test("nth0 last") :-
    nth0(2, [a, b, c], c).

test("nth1 first") :-
    nth0(0, [a, b, c], a).

test("nth1 last") :-
    nth0(2, [a, b, c], c).

test("nth0 out of range") :-
    \+ nth0(5, [a, b], _).

test("nth1 zero fails") :-
    \+ nth0(-1, [a, b], _).

test("sort removes dups") :-
    sort([3, 1, 2, 1], [1, 2, 3]).

test("sort already sorted") :-
    sort([1, 2, 3], [1, 2, 3]).

test("sort empty") :-
    sort([], []).

test("msort preserves dups") :-
    msort([3, 1, 2, 1], [1, 1, 2, 3]).

test("sort strings") :-
    sort([c, a, b], [a, b, c]).

test("flatten nested") :-
    flatten([1, [2, [3]], 4], [1, 2, 3, 4]).

test("flatten already flat") :-
    flatten([1, 2, 3], [1, 2, 3]).

test("flatten empty") :-
    flatten([], []).

test("select element") :-
    select(2, [1, 2, 3], [1, 3]).

test("select first") :-
    select(1, [1, 2, 3], [2, 3]).

test("select not found") :-
    \+ select(9, [1, 2, 3], _).

test("subtract") :-
    subtract([1, 2, 3, 4], [2, 4], [1, 3]).

test("intersection") :-
    intersection([1, 2, 3], [2, 3, 4], [2, 3]).

test("union") :-
    union([1, 2], [2, 3], [1, 2, 3]).

test("list_to_set") :-
    list_to_set([1, 2, 1, 3, 2], [1, 2, 3]).

test("sum_list") :-
    sum_list([1, 2, 3, 4], 10).

test("sum_list empty") :-
    sum_list([], 0).

test("max_list") :-
    max_list([3, 1, 4, 1, 5], 5).

test("min_list") :-
    min_list([3, 1, 4, 1, 5], 1).

test("max_list singleton") :-
    max_list([42], 42).

test("palindrome: empty") :-
    palindrome([]).

test("palindrome: single") :-
    palindrome([1]).

test("palindrome: aba") :-
    palindrome([1, 2, 1]).

test("palindrome: abba") :-
    palindrome([1, 2, 2, 1]).

test("not palindrome: ab") :-
    \+ palindrome([1, 2]).

test("sorted_asc: empty") :-
    sorted_asc([]).

test("sorted_asc: single") :-
    sorted_asc([1]).

test("sorted_asc: ascending") :-
    sorted_asc([1, 2, 3]).

test("sorted_asc: not descending") :-
    \+ sorted_asc([3, 2, 1]).

test("sorted_asc: equal elements") :-
    sorted_asc([2, 2, 2]).

test("is_permutation: same list") :-
    is_permutation([1, 2, 3], [1, 2, 3]).

test("is_permutation: reordered") :-
    is_permutation([3, 1, 2], [1, 2, 3]).

test("not permutation: different lengths") :-
    \+ is_permutation([1, 2], [1, 2, 3]).

test("is_permutation: empty") :-
    is_permutation([], []).
