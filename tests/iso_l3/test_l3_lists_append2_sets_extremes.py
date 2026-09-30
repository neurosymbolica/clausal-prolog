"""append/2, list_max/2 and list_min/2 (Scryer's library(lists) exports
that were existence errors), and subtract/3, intersection/3,
union/3 comparing elements by ==/2 (Python's == made 1 and 1.0 one
element).  Answers measured against Scryer 2026-09-30; Scryer has no
subtract/intersection/union, so those rows pin term identity."""
from __future__ import annotations

SRC = """\
:- use_module(library(lists)).
p1(R) :- findall(X, append([[1],[2,3]], X), R).
p2(R) :- findall(Xs, append([Xs,[a]], [b,a]), R).
p3(R) :- findall(A-B, append([A,B], [1,2]), R).
p4(R) :- findall(A-B-C, append([A,B,C], [1]), R).
p5(R) :- findall(x, append(foo, _), R).
p6(R) :- findall(X, append([[1],X,[3]], [1,2,3]), R).
p7(R) :- findall(x, append([[1],[2]], [1,2,3]), R).
p8(R) :- findall(T, append([[1|T]], [1,2]), R).
p9(R) :- findall(X, append([], X), R).
p10(R) :- findall(T, (length(T, 2), append([[1]|T], [1])), R).
p11(R) :- findall(X, (length(L, 3), append([[1],L], X)), R).
s1(R) :- findall(D, subtract([1,2,1.0], [1.0], D), R).
s2(R) :- findall(D, subtract([f(1),f(1.0)], [f(1)], D), R).
s3(R) :- findall(D, intersection([1,1.0,2], [1], D), R).
s4(R) :- findall(D, union([1], [1.0], D), R).
s5(R) :- findall(D, union([a,b], [b,a,c,c], D), R).
s6(R) :- findall(D, subtract([1,x,2.0], [2.0,x], D), R).
s7(R) :- findall(X-Y-D, subtract([X,Y], [X], D), R).
m1(R) :- findall(M, list_max([1,3,2], M), R).
m2(R) :- findall(M-N, (list_max([2,2.0], M), list_min([2.0,2], N)), R).
m3(R) :- findall(M, list_max([1+1], M), R).
m4(R) :- findall(M, list_max([1,1+1], M), R).
m5(R) :- findall(x, list_max([], _), R).
m6(R) :- findall(x, list_max(foo, _), R).
m7(R) :- findall(M, list_min([1,2.0,0.5], M), R).
e1(E) :- catch(list_max([1,a], _), error(E, _), true).
e2(E) :- catch(list_max([1,_], _), error(E, _), true).
e3(E) :- catch(findall(L-M, list_max(L, M), _), error(E, _), true).
e4(E) :- catch(findall(T, list_max([1|T], _), _), error(E, _), true).
"""


def test_append_2(native, ans):
    mod = native.load("l3_lists_append2", SRC)
    assert ans(mod, "p1") == [[[1, 2, 3]]]
    assert ans(mod, "p2") == [[["b"]]]
    assert ans(mod, "p3") == [[("-", [], [1, 2]), ("-", [1], [2]),
                               ("-", [1, 2], [])]]
    assert ans(mod, "p4") == [[("-", ("-", [], []), [1]),
                               ("-", ("-", [], [1]), []),
                               ("-", ("-", [1], []), [])]]
    assert ans(mod, "p5") == [[]]
    assert ans(mod, "p6") == [[[2]]]
    assert ans(mod, "p7") == [[]]
    assert ans(mod, "p8") == [[[2]]]
    assert ans(mod, "p9") == [[[]]]
    assert ans(mod, "p10") == [[[[], []]]]
    ((x,),) = ans(mod, "p11")
    assert len(x) == 4 and x[0] == 1


def test_set_predicates_compare_by_identity(native, ans):
    mod = native.load("l3_lists_sets_identity", SRC)
    assert ans(mod, "s1") == [[[1, 2]]]
    assert ans(mod, "s2") == [[[("f", 1.0)]]]
    assert ans(mod, "s3") == [[[1]]]
    assert ans(mod, "s4") == [[[1, 1.0]]]
    assert ans(mod, "s5") == [[["a", "b", "c"]]]
    assert ans(mod, "s6") == [[[1]]]
    (((_m, (_m2, x, y), d),),) = ans(mod, "s7")   # variables by identity
    assert len(d) == 1 and d[0] is y and x is not y


def test_list_max_list_min(native, ans):
    mod = native.load("l3_lists_extremes", SRC)
    assert ans(mod, "m1") == [[3]]
    (row,) = ans(mod, "m2")
    assert [(m, n) for (_o, m, n) in row] == [(2.0, 2.0)]
    assert type(row[0][1]) is float and type(row[0][2]) is float
    assert ans(mod, "m3") == [[("+", 1, 1)]]     # the first is not evaluated
    assert ans(mod, "m4") == [[2]]
    assert ans(mod, "m5") == [[]]
    assert ans(mod, "m6") == [[]]
    assert ans(mod, "m7") == [[0.5]]
    assert ans(mod, "e1") == [("type_error", "evaluable", ("/", "a", 0))]
    assert ans(mod, "e2") == ["instantiation_error"]
    assert ans(mod, "e3") == ["instantiation_error"]
    assert ans(mod, "e4") == ["instantiation_error"]

