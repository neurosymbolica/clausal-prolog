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
-private([oops, caught])
-table(tab_two/1)
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
c_eq(Y) <- catch((freeze(X, throw(oops)), X == 3), _, Y is caught)
c_is(Y) <- catch((freeze(X, throw(oops)), X is 3), _, Y is caught)
c_squeeze(Y) <- catch((freeze(X, throw(oops)), X <= 3, X >= 3), _, Y is caught)
c_reified(Y) <- catch((freeze(X, throw(oops)), if_(X == 3, true, true)), _, Y is caught)
c_in_or(Y) <- (catch((freeze(X, throw(oops)), X == 3), _, Y is caught) or Y is 2)
c_or_inside(Y) <- catch(((freeze(X, throw(oops)), X == 3) or Y is 2), _, Y is caught)
c_two(Y) <- catch((freeze(X, member(Y, [1, 2])), X == 3), _, Y is caught)
c_fail(Y) <- (catch((freeze(X, fail), X == 3), _, true), Y is 1)
c_findall(Y) <- catch(findall(X, (freeze(X, throw(oops)), X == 3), _), _, Y is caught)
c_once(Y) <- catch(once((freeze(X, throw(oops)), X == 3)), _, Y is caught)
c_neg(Y) <- catch(not (freeze(X, throw(oops)), X == 3), _, Y is caught)
c_forall(Y) <- catch(forall((freeze(X, throw(oops)), X == 3), true), _, Y is caught)
c_cleanup(Y) <- catch(call_cleanup((freeze(X, throw(oops)), X == 3), true), _, Y is caught)
c_setup(Y) <- catch(setup_call_cleanup(true, (freeze(X, throw(oops)), X == 3), true), _, Y is caught)
forall_fail(Y) <- (forall((freeze(X, fail), X == 3), fail), Y is 1)
once_two(Y) <- (once((freeze(X, member(Y, [1, 2])), X == 3)), nonvar(Y))
cleanup_two(Y) <- (call_cleanup((freeze(X, member(Y, [1, 2])), X == 3), true), nonvar(Y))
setup_two(Y) <- (setup_call_cleanup(true, (freeze(X, member(Y, [1, 2])), X == 3), true), nonvar(Y))
tab_two(Y) <- (freeze(X, member(Y, [1, 2])), X == 3)
tab_seen(Y) <- (tab_two(Y), nonvar(Y))
"""

_PREDS = ["fd_eq", "fd_squeeze", "fd_strict", "fd_arith", "fd_sees", "fd_two",
          "fd_order", "dif_sees", "dif_count", "fail_count", "fail_collect",
          "fail_negated", "two_collect", "reified",
          "c_eq", "c_is", "c_squeeze", "c_reified", "c_in_or", "c_or_inside",
          "c_two", "c_fail", "c_findall", "c_once", "c_neg", "c_forall",
          "c_cleanup", "c_setup", "forall_fail", "once_two", "cleanup_two",
          "setup_two", "tab_seen"]   # tab_two is tabled: trampoline only


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


# ── A construct that scopes its goal sees the goals the goal woke ──────────
#
# The goals a comparison wakes belong to the goal that made the comparison:
# inside catch/3 they run inside the catch (Scryer catches the ball), and
# the same holds for every other construct that runs its goal in a scope of
# its own.  The trampoline catch/3 compiles its goal with the clause's
# solution step as the continuation, and that step's own boundary runs the
# queue OUTSIDE the ``try``: the ball escaped.  (``X is 3`` was caught, since
# a unification drains in place.)


@pytest.mark.parametrize("goal", [
    "c_eq", "c_is", "c_squeeze", "c_reified", "c_or_inside",
    "c_findall", "c_once", "c_neg", "c_forall", "c_cleanup", "c_setup",
])
def test_catch_catches_a_ball_thrown_by_a_woken_goal(mod, goal):
    assert _answers(mod, goal) == ["caught"]


def test_catch_in_a_disjunction_catches_then_tries_the_other_branch(mod):
    assert _answers(mod, "c_in_or") == ["caught", 2]


def test_catch_keeps_every_answer_of_a_woken_goal(mod):
    assert _answers(mod, "c_two") == [1, 2]


def test_a_woken_goal_that_fails_fails_the_catch_goal(mod):
    assert _answers(mod, "c_fail") == []


@pytest.mark.parametrize("goal, expected", [
    ("forall_fail", [1]),
    ("once_two", [1]),
    ("cleanup_two", [1, 2]),
    ("setup_two", [1, 2]),
    ("tab_seen", [1, 2]),
])
def test_a_scoped_goal_runs_what_it_woke_inside_the_scope(mod, goal, expected):
    assert _answers(mod, goal) == expected
