"""An inline goal op that binds is a goal boundary: woken goals run after it.

Scryer runs the goals a binding wakes before the next call.  The engine did
so after every unification and at every call's answer, but not after the
goal ops the compiler lowers inline with no call boundary: a CLP(FD)
comparison (``X == 3``, ``X <= 3``, and the posts of a reified ``if_/3``
test) can bind a variable -- directly, or as the implied value of a domain
squeezed to one -- and the goals that binding woke stayed queued past the
goals that followed, which then saw the variable unbound:

    freeze(X, Y is 1), X == 3, var(Y)       % succeeded; Scryer: false

Inside ``count_all/2``, ``findall/3`` or a negation, whose inner goal ends
in no call, the queued goals never ran at all: a woken goal that fails was
counted, and one with two answers was collected once, unbound.

Every case runs under ``solve`` (a driver) in both compilation strategies.
"""
from __future__ import annotations

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_SEAM = """\
fd_eq(Y) <- (freeze(X, Y is 1), X == 3, var(Y))
fd_squeeze(Y) <- (freeze(X, Y is 1), X <= 3, X >= 3, var(Y))
fd_strict(Y) <- (freeze(X, Y is 1), X > 2, X < 4, var(Y))
fd_arith(Y) <- (freeze(X, Y is 1), X + 1 == 4, var(Y))
fd_sees(Y) <- (freeze(X, Y is 1), X == 3, nonvar(Y))
fd_two(Y) <- (freeze(X, member(Y, [1, 2])), X == 3, nonvar(Y))
fd_order(P) <- (freeze(X, member(Y, [1, 2])), X == 3, member(Z, [10, 20]), P is (Y, Z))
dif_sees(Y) <- (freeze(X, Y is 2), X == 3, Y is not 3, nonvar(Y))
dif_count(N) <- count_all((X is not 4, freeze(X, fail), X <= 3, X >= 3), N)
fail_count(N) <- count_all((freeze(X, fail), X == 3), N)
fail_collect(L) <- findall(Y, ((Y is 1, freeze(X, fail), X == 3) or Y is 2), L)
fail_negated(Y) <- (not (freeze(X, fail), X == 3), Y is 1)
two_collect(L) <- findall(Y, (freeze(X, member(Y, [1, 2])), X == 3), L)
reified(Y) <- (freeze(X, Y is 1), if_(X == 3, nonvar(Y), fail))
"""

_PREDS = ["fd_eq", "fd_squeeze", "fd_strict", "fd_arith", "fd_sees", "fd_two",
          "fd_order", "dif_sees", "dif_count", "fail_count", "fail_collect",
          "fail_negated", "two_collect", "reified"]


@pytest.fixture(scope="module", params=["trampoline", "shallow"])
def mod(request, tmp_path_factory):
    src = _SEAM
    if request.param == "shallow":
        src = "-shallow([" + ", ".join(f"{p}/1" for p in _PREDS) + "])\n" + src
    p = tmp_path_factory.mktemp("inline_drain_" + request.param) / "m.seam"
    p.write_text(src)
    return load_clausal_module(p)


def _answers(mod, goal):
    y = Var()
    return [_plain(y) for _ in solve((goal, y), mod)]


def _plain(t):
    t = deref(t)
    if isinstance(t, list):
        return [_plain(e) for e in t]
    if isinstance(t, tuple):
        return tuple(_plain(e) for e in t)
    return t


@pytest.mark.parametrize("goal", ["fd_eq", "fd_squeeze", "fd_strict", "fd_arith"])
def test_a_comparison_that_binds_runs_the_woken_goal_before_the_next_goal(mod, goal):
    # Scryer: false -- the woken ``Y is 1`` has run by the time var(Y) runs.
    assert _answers(mod, goal) == []


def test_the_next_goal_sees_the_woken_goals_binding(mod):
    assert _answers(mod, "fd_sees") == [1]


def test_a_woken_goal_with_two_answers_gives_both(mod):
    assert _answers(mod, "fd_two") == [1, 2]


def test_the_woken_goal_runs_before_the_next_call_so_its_answers_lead(mod):
    # Run before member(Z, ...), as Scryer runs it: Y varies slowest.
    assert _answers(mod, "fd_order") == [(1, 10), (1, 20), (2, 10), (2, 20)]


def test_dif_after_the_comparison_sees_the_woken_binding(mod):
    assert _answers(mod, "dif_sees") == [2]


def test_dif_and_a_failing_woken_goal_inside_count_all(mod):
    assert _answers(mod, "dif_count") == [0]


def test_a_woken_goal_that_fails_fails_the_comparison_inside_count_all(mod):
    assert _answers(mod, "fail_count") == [0]


def test_a_woken_goal_that_fails_fails_the_comparisons_clause(mod):
    # The first disjunct ends in the comparison: its woken ``fail`` must fail
    # that disjunct, not be dropped when findall takes the answer.
    assert _answers(mod, "fail_collect") == [[2]]


def test_a_woken_goal_that_fails_is_seen_by_a_negation(mod):
    assert _answers(mod, "fail_negated") == [1]


def test_findall_collects_every_answer_of_the_woken_goal(mod):
    assert _answers(mod, "two_collect") == [[1, 2]]


def test_a_reified_comparison_that_posts_runs_the_woken_goal(mod):
    # if_/3 on an undetermined X posts X == 3 for the then-branch.
    assert _answers(mod, "reified") == [1]
