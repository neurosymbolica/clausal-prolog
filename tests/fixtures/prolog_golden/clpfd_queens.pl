safe_queens(N, Qs) :-
    in_domain(Qs, 1, N),
    all_different(Qs),
    label(Qs),
    check_diagonals(Qs).

check_diagonals([]).

check_diagonals([Q|Rest]) :-
    safe_from(Q, Rest, 1),
    check_diagonals(Rest).

safe_from(Q, [], D).

safe_from(Q, [H|T], D) :-
    Q \== H,
    Diff1 is Q - H,
    Diff2 is H - Q,
    Diff1 \== D,
    Diff2 \== D,
    D1 is D + 1,
    safe_from(Q, T, D1).
