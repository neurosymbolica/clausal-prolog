"""A goal woken by a unification keeps every answer.

``freeze/2`` and ``when/2`` used to run a woken goal inside the unification,
to its first answer only (a committed choice): ``f(Y) :- freeze(X,
member(Y, [1,2,3])), X = go.`` answered ``Y = 1`` alone.  Under a driver a
woken goal is now queued on the trail and run at the next goal boundary,
with every answer, as Scryer runs woken goals (clausal/logic/pending.py).
"""
from __future__ import annotations

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref, put_attr, unify
from clausal.testing import load_clausal_module

_PL = """\
f(Y) :- freeze(X, member(Y, [1, 2, 3])), X = go.
later(Y) :- freeze(X, member(Y, [1, 2, 3])), X = go, Y > 1.
via_call(Y) :- freeze(X, member(Y, [1, 2])), call(=, X, go).
via_head(Y) :- freeze(X, member(Y, [a, b])), p(X).
p(go).
collected(Ys) :- findall(Y, (freeze(X, member(Y, [1, 2, 3])), X = go), Ys).
nested(Y) :- freeze(X, (freeze(Z, member(Y, [1, 2])), Z = go)), X = go.
w_ground(Y) :- when(ground(X), member(Y, [1, 2, 3])), X = f(go).
w_bound(Y) :- X = go, when(nonvar(X), member(Y, [1, 2])).
w_now(Y) :- when(ground(go), member(Y, [1, 2])).
w_now_fails(Y) :- when(ground(go), fail), Y = 1.
not_unif_true(Y) :- freeze(X, fail), Y = 1, X \\= go.
not_unif_false(Y) :- freeze(X, member(Y, [1, 2, 3])), X \\= go.
chk(Y) :- freeze(X, member(Y, [1, 2, 3])), memberchk(X, [go]).
chk_skips(Y) :- freeze(X, X == b), memberchk(X, [a, b, c]), Y = X.
not_chk(Y) :- freeze(X, fail), Y = 1, \\+ memberchk(X, [go]).
"""

_SEAM = """\
after_unify(Y) <- (freeze(X, Y is 1), X is 7, var(Y))
sees_binding(Y) <- (freeze(X, Y is 1), X is 7, Y == 1)
r(7, Y) <- var(Y)
head_wakes(Y) <- (freeze(X, Y is 1), r(X, Y))
s(7, Y) <- (Y > 1)
head_backtracks(Y) <- (freeze(X, member(Y, [1, 2, 3])), s(X, Y))
"""


@pytest.fixture(scope="module")
def pl(tmp_path_factory):
    p = tmp_path_factory.mktemp("woken") / "woken.clausal"
    p.write_text(_PL)
    return load_clausal_module(p)


@pytest.fixture(scope="module")
def seam(tmp_path_factory):
    p = tmp_path_factory.mktemp("woken_seam") / "woken.seam"
    p.write_text(_SEAM)
    return load_clausal_module(p)


def _answers(mod, goal):
    y = Var()
    return [y.value for _ in solve((goal, y), mod)]


@pytest.mark.parametrize("goal, expected", [
    ("f", [1, 2, 3]),
    ("later", [2, 3]),
    ("via_call", [1, 2]),
    ("via_head", ["a", "b"]),
    ("collected", [[1, 2, 3]]),
    ("nested", [1, 2]),
])
def test_a_frozen_goal_keeps_every_answer(pl, goal, expected):
    assert _answers(pl, goal) == expected


@pytest.mark.parametrize("goal, expected", [
    ("w_ground", [1, 2, 3]),
    ("w_bound", [1, 2]),
    ("w_now", [1, 2]),
    ("w_now_fails", []),            # used to be ignored: answered [1]
])
def test_a_when_goal_keeps_every_answer(pl, goal, expected):
    assert _answers(pl, goal) == expected


@pytest.mark.parametrize("goal, expected", [
    ("not_unif_true", [1]),         # \+ X = go: the woken goal fails inside it
    ("not_unif_false", []),
    ("chk", [1]),                   # memberchk is once(member): first answer
    ("chk_skips", ["b"]),           # an element whose woken goal fails is passed over
    ("not_chk", [1]),
])
def test_woken_goals_run_inside_a_test(pl, goal, expected):
    assert _answers(pl, goal) == expected


@pytest.mark.parametrize("goal, expected", [
    ("after_unify", []),            # the next goal sees the woken goal's binding
    ("sees_binding", [1]),
    ("head_wakes", []),             # a head unification wakes before the body
    ("head_backtracks", [2, 3]),
])
def test_woken_goals_run_before_the_next_goal(seam, goal, expected):
    assert _answers(seam, goal) == expected


# ── the trail's queue ────────────────────────────────────────────────────────

def _goal():
    yield None


def test_the_queue_is_trailed():
    t = Trail()
    assert t.pending is None
    m0 = t.mark()
    t.push_pending(_goal)
    t.push_pending(_goal)
    assert t.pending == (_goal, _goal)
    m1 = t.mark()
    assert t.take_pending() == (_goal, _goal) and t.pending is None
    t.undo(m1)
    assert t.pending == (_goal, _goal)    # backtracking past a take restores it
    t.undo(m0)
    assert t.pending is None              # and past a push removes it


def test_a_queued_goal_blocks_the_tail_call_commit():
    t = Trail()
    mark, floor = t.mark(), t.var_floor()
    t.push_pending(_goal)
    assert t.commit_fresh(mark, floor) is False


def test_without_a_driver_a_hook_runs_its_goal_in_place():
    """A bare unify from Python (no driver owns the trail) keeps the old
    behaviour: the frozen goal runs inside the unification."""
    from clausal.logic.coroutining import _freeze_var
    t, x, y = Trail(), Var(), Var()
    assert t.defer is False

    def goal():
        m = t.mark()
        if unify(y, 1, t):
            yield None
        t.undo(m)
    _freeze_var(x, goal, t)
    assert unify(x, "go", t)
    assert deref(y) == 1 and t.pending is None


def test_under_a_driver_a_hook_queues_its_goal():
    from clausal.logic.coroutining import _freeze_var
    t, x = Trail(), Var()
    t.defer = True
    _freeze_var(x, _goal, t)
    assert unify(x, "go", t)
    assert t.pending == (_goal,)


def test_many_goals_woken_at_once(tmp_path):
    """Review M1: the drain nested a frame per queued goal, so about a
    thousand goals woken by one unification raised RecursionError."""
    n = 3000
    src = (f"many(R) :- length(Xs, {n}), maplist(fz, Xs), "
           f"length(Ys, {n}), maplist(=(go), Ys), Xs = Ys, R = ok.\n"
           "fz(X) :- freeze(X, true).\n")
    p = tmp_path / "many.clausal"
    p.write_text(src)
    m = load_clausal_module(p)
    assert _answers(m, "many") == ["ok"]
