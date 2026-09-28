:- use_module(library(clpz), [(#=)/2]).

safe_queens(N, QUEENS) :-
    in_domain(QUEENS, 1, N),
    all_different(QUEENS),
    label(QUEENS),
    check_diagonals(QUEENS).

check_diagonals([]).

check_diagonals([QUEEN|REST]) :-
    safe_from(QUEEN, REST, 1),
    check_diagonals(REST).

safe_from(_QUEEN_UNUSED, [], _DISTANCE_UNUSED).

safe_from(QUEEN, [HEAD|TAIL], DISTANCE) :-
    dif(QUEEN, HEAD),
    #=(DIFFERENCE1, QUEEN - HEAD),
    #=(DIFFERENCE2, HEAD - QUEEN),
    dif(DIFFERENCE1, DISTANCE),
    dif(DIFFERENCE2, DISTANCE),
    #=(NEXT_DISTANCE, DISTANCE + 1),
    safe_from(QUEEN, TAIL, NEXT_DISTANCE).

test('queens 1') :-
    length(QUEENS, 1),
    safe_queens(1, QUEENS),
    length(QUEENS, 1).

test('queens 4 valid') :-
    length(QUEENS, 4),
    safe_queens(4, QUEENS),
    length(QUEENS, 4).
