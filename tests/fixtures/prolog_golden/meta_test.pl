squares(N, Squares) :-
    findall(Sq, in(X, N), Sq is X * X, Squares).

positives(Ns, Pos) :-
    findall(X, in(X, Ns), X > 0, Pos).

unique_members(Ns, Unique) :-
    setof(X, in(X, Ns), Unique).

all_positive(Ns) :-
    forall(in(X, Ns), X > 0).
