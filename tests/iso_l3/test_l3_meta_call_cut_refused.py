"""Native ``.pl``: a cut BUILT AT RUN TIME and handed to a meta-call RUNS,
local to that call (ISO 7.8.3), never as ``true``.

Before D59 (Task 5) a ``.pl`` caller refused it with
``existence_error(procedure, !/0)``; ``G = (p(X), !), call(G)`` once loaded
and gave both ``p`` answers (Scryer: the first).  A ``.clausal`` or seam
caller keeps that refusal (tests/test_meta_call_cut_refused.py and
test_l3_cut_meta.py).  A cut that is the WHOLE goal of the call
(``G = !, call(G)``) is ISO-local and stays ``true``.  Every answer below is
Scryer's (2026-10-14), except c6: Scryer has no forall/2 without
library(lists)'s import, and ISO 8.15.1 makes it succeed."""
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

@pytest.mark.parametrize("name,want", [
    ("c1", ["ran"]), ("c2", ["ran", "ran"]), ("c3", ["ran", "ran", "ran"]),
    ("c4", []), ("c5", [[1]]), ("c6", ["ran"]), ("c7", ["ran"]),
])
def test_a_runtime_built_cut_runs_local_to_every_meta_call(native, ans, name,
                                                           want):
    mod = native.load("l3_cut_meta", SRC)
    assert ans(mod, name) == want


def test_a_cut_that_is_the_whole_goal_is_unchanged(native, ans):
    """ISO 7.8.3: the cut is local to the call and cuts nothing."""
    mod = native.load("l3_cut_meta_whole", SRC)
    assert ans(mod, "w1") == ["ran"]
    assert ans(mod, "w2") == [["x"]]


def test_asserting_a_runtime_built_cut_is_a_permission_error(native, ans):
    mod = native.load("l3_cut_meta_assert", SRC)
    assert ans(mod, "c8") == [("permission_error", "modify",
                               "static_procedure", ("/", "!", 0))]
