"""clpz's reflection predicates and global constraints under Scryer's
names: fd_dom/2, fd_size/2, fd_inf/2, fd_sup/2, tuples_in/2,
global_cardinality/2, zcompare/3, all_distinct/1.  Each was an
existence_error although the solver implements it.  Every answer below is
Scryer's clpz for the same goal (2026-09-30)."""
from __future__ import annotations

SRC = """\
:- use_module(library(clpz)).
c1(R) :- findall(L, (L = [A,B,C], L ins 1..3, all_distinct(L), A #> C, label(L)), R).
c5(R) :- findall(L, (L = [A,B], tuples_in([L], [[1,2],[2,3],[3,1]]), A #> 1, label(L)), R).
c6(R) :- findall(L, (L = [A,B,C], L ins 1..2, global_cardinality(L, [1-2, 2-1]), label(L)), R).
c22(R) :- findall(S, (X in 1..9, X #\\= 5, fd_size(X, S)), R).
c23(R) :- findall(D, (X in 1..9, X #\\= 5, fd_dom(X, D)), R).
c24(R) :- findall(I-S, (X in 1..3, fd_inf(X, I), fd_sup(X, S)), R).
c25(R) :- findall(D-S, (fd_dom(X, D), fd_size(X, S)), R).
c26(R) :- findall(I-S, (X #> 3, fd_inf(X, I), fd_sup(X, S)), R).
c27(R) :- findall(D, fd_dom(3, D), R).
c31(R) :- findall(X, (X in 1..4, zcompare(O, X, 2), O = (<), label([X])), R).
c32(R) :- findall(O, zcompare(O, 1, 2), R).
"""


def test_clpz_globals(native, ans):
    mod = native.load("l3_clpz_globals", SRC)
    p = lambda a, b: ("-", a, b)  # noqa: E731
    r = lambda a, b: ("..", a, b)  # noqa: E731
    assert ans(mod, "c1") == [[[2, 3, 1], [3, 1, 2], [3, 2, 1]]]
    assert ans(mod, "c5") == [[[2, 3], [3, 1]]]
    assert ans(mod, "c6") == [[[1, 1, 2], [1, 2, 1], [2, 1, 1]]]
    assert ans(mod, "c22") == [[8]]
    assert ans(mod, "c23") == [[("\\/", r(1, 4), r(6, 9))]]
    assert ans(mod, "c24") == [[p(1, 3)]]
    assert ans(mod, "c25") == [[p(r("inf", "sup"), "sup")]]
    assert ans(mod, "c26") == [[p(4, "sup")]]
    assert ans(mod, "c27") == [[r(3, 3)]]
    assert ans(mod, "c31") == [[1]]
    assert ans(mod, "c32") == [["<"]]
