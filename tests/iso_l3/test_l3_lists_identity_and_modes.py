"""list_to_set/2 removes duplicates by term identity (==/2), and
permutation/2 runs with its first argument unbound -- Scryer's answers
(2026-09-30).  list_to_set([a,b,a,1,1.0], S) dropped 1.0 (Python's == made
1 and 1.0 one element); permutation(X, [1,2]) had no answers."""
from __future__ import annotations

SRC = """\
:- use_module(library(lists)).
l1(R) :- findall(X, list_to_set([a,b,a,1,1.0], X), R).
l2(R) :- findall(X, list_to_set([f(A),f(B),f(A)], X), R).
p1(R) :- findall(X, permutation(X, [1,2]), R).
p2(R) :- findall(X, permutation([1,2,3], X), R).
p3(R) :- findall(x, permutation([1,2], [2,1]), R).
"""


def test_list_to_set_by_identity(native, ans):
    from clausal.logic.variables import is_var
    mod = native.load("l3_lists_identity", SRC)
    assert ans(mod, "l1") == [[["a", "b", 1, 1.0]]]
    (((first, second),),) = ans(mod, "l2")
    assert is_var(first[1]) and is_var(second[1]) and first[1] is not second[1]


def test_permutation_with_the_first_argument_unbound(native, ans):
    mod = native.load("l3_lists_perm", SRC)
    assert ans(mod, "p1") == [[[1, 2], [2, 1]]]
    assert ans(mod, "p2") == [[[1, 2, 3], [1, 3, 2], [2, 1, 3], [2, 3, 1],
                               [3, 1, 2], [3, 2, 1]]]
    assert ans(mod, "p3") == [["x"]]
