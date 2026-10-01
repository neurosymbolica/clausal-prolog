"""Native ``.pl``: a cut BUILT AT RUN TIME and handed to a meta-call is
refused (``existence_error(procedure, !/0)``), never run as ``true``.

The load-time refusal (test_l3_s1_refusals.py) sees a cut WRITTEN in a body,
including inside ``call/1`` or ``findall/3``; it cannot see one bound to a
variable first.  ``G = (p(X), !), call(G)`` loaded and gave both ``p``
answers (Scryer: the first).  A cut that is the WHOLE goal of the call
(``G = !, call(G)``) is ISO-local and stays ``true``."""
from __future__ import annotations

import pytest

SRC = """\
p(1).
p(2).
:- dynamic(h/0).
c1(R) :- catch((G = (p(_), !), call(G), R = ran), error(E, _), R = E).
c2(R) :- catch((G = (!, p(_)), call(G), R = ran), error(E, _), R = E).
c3(R) :- catch((G = (p(_) ; !), call(G), R = ran), error(E, _), R = E).
c4(R) :- catch((G = (p(_), !), \\+ G, R = ran), error(E, _), R = E).
c5(R) :- catch((G = (p(X), !), findall(X, G, L), R = L), error(E, _), R = E).
c6(R) :- catch((G = (p(_), !), forall(G, true), R = ran), error(E, _), R = E).
c7(R) :- catch((G = (p(_), !), once(G), R = ran), error(E, _), R = E).
c8(R) :- catch((C = h, B = !, assertz(B), R = C), error(E, _), R = E).
w1(R) :- G = !, call(G), R = ran.
w2(R) :- G = !, findall(x, G, R).
"""

REFUSED = ("existence_error", "procedure", ("/", "!", 0))


@pytest.mark.parametrize("name", ["c1", "c2", "c3", "c4", "c5", "c6", "c7"])
def test_a_runtime_built_cut_is_refused_in_every_meta_call(native, ans, name):
    mod = native.load("l3_cut_meta", SRC)
    assert ans(mod, name) == [REFUSED]


def test_a_cut_that_is_the_whole_goal_is_unchanged(native, ans):
    """ISO 7.8.3: the cut is local to the call and cuts nothing."""
    mod = native.load("l3_cut_meta_whole", SRC)
    assert ans(mod, "w1") == ["ran"]
    assert ans(mod, "w2") == [["x"]]


def test_asserting_a_runtime_built_cut_is_a_permission_error(native, ans):
    mod = native.load("l3_cut_meta_assert", SRC)
    assert ans(mod, "c8") == [("permission_error", "modify",
                               "static_procedure", ("/", "!", 0))]
