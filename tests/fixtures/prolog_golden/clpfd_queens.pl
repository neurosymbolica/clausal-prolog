safe_queens(N, Queens) :-
    in_domain(Queens, 1, N),
    all_different(Queens),
    label(Queens),
    check_diagonals(Queens).

check_diagonals([]).

check_diagonals([Queen|Rest]) :-
    safe_from(Queen, Rest, 1),
    check_diagonals(Rest).

safe_from(_Queen_unused, [], _Distance_unused).

safe_from(Queen, [Head|Tail], Distance) :-
    Queen \== Head,
    Difference1 =:= Queen - Head,
    Difference2 =:= Head - Queen,
    Difference1 \== Distance,
    Difference2 \== Distance,
    Next_distance =:= Distance + 1,
    safe_from(Queen, Tail, Next_distance).

test('queens 1') :-
    length(Queens, 1),
    safe_queens(1, Queens),
    length(Queens, 1).

test('queens 4 valid') :-
    length(Queens, 4),
    safe_queens(4, Queens),
    length(Queens, 4).
