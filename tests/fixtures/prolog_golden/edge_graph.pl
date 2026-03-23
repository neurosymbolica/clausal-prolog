edge(1, 2).

edge(2, 3).

edge(1, 3).

reach(X, Y) :-
    edge(X, Y).

reach(X, Y) :-
    edge(X, Z),
    reach(Z, Y).
