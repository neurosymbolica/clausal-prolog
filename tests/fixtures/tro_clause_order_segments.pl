% A restart guarded by a runtime key test (N =\= 0 refutes seg(0, ...), not
% seg(-1, ...)) beside a later clause long enough to be cut into body
% segments (tests/test_tro_clause_order.py).
:- module(tro_clause_order_segments, [seg/3]).
seg(N, A, R) :- N =\= 0, N1 is N - 1, A1 is A + 1, seg(N1, A1, R).
seg(0, R, R).
seg(-1, A, R) :-
    X0 is A + 0,
    X1 is X0 + 1,
    X2 is X1 + 1,
    X3 is X2 + 1,
    X4 is X3 + 1,
    X5 is X4 + 1,
    X6 is X5 + 1,
    X7 is X6 + 1,
    X8 is X7 + 1,
    X9 is X8 + 1,
    X10 is X9 + 1,
    X11 is X10 + 1,
    X12 is X11 + 1,
    X13 is X12 + 1,
    X14 is X13 + 1,
    X15 is X14 + 1,
    X16 is X15 + 1,
    X17 is X16 + 1,
    X18 is X17 + 1,
    X19 is X18 + 1,
    X20 is X19 + 1,
    X21 is X20 + 1,
    X22 is X21 + 1,
    X23 is X22 + 1,
    X24 is X23 + 1,
    X25 is X24 + 1,
    X26 is X25 + 1,
    X27 is X26 + 1,
    X28 is X27 + 1,
    X29 is X28 + 1,
    R = X29.
