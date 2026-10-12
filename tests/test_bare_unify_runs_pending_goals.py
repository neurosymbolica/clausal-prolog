"""A bare unify runs the goals it woke after every hook, to a first answer.

Outside a driver (``trail.defer`` false) ``freeze/2`` used to run a woken
goal inside its hook, to its first answer, while other variables bound by
the same unification had not had their own hooks run yet -- the ordering
behind wrong answers in a CLP solver.  Hooks now always queue; a bare unify
makes all its bindings, fires every hook, then runs the queue to its first
answer (clausal/logic/pending.py), as Scryer runs woken goals after the
unification.  Under a driver nothing changes.
"""
from __future__ import annotations

import pytest

from clausal.logic.coroutining import _freeze_var
from clausal.logic.solve import solve
from clausal.logic.variables import (
    Trail, Var, deref, get_attr, is_var, put_attr, register_attr_hook, unify,
    unify_iter, unify_with_occurs_check,
)
from clausal.testing import load_clausal_module

_ORDER = "probe_order"


@pytest.fixture(autouse=True)
def _unregister():
    yield
    register_attr_hook(_ORDER, None)


def _goal(fn):
    """A zero-arg generator factory running fn() once; fails on False."""
    def goal():
        if fn() is not False:
            yield None
    return goal


@pytest.mark.parametrize("unify_fn", [unify, unify_with_occurs_check])
def test_a_woken_goal_sees_every_hook_of_the_unification(unify_fn):
    log = []
    register_attr_hook(_ORDER, lambda v, o, t: log.append("probe") or True)
    t, z, w = Trail(), Var(), Var()
    _freeze_var(z, _goal(lambda: log.append("goal")), t)
    put_attr(w, _ORDER, 1, t)
    # z is bound first, so its freeze hook fires before w's probe hook
    assert unify_fn((z, w), (1, 2), t)
    assert log == ["probe", "goal"]
    assert t.pending is None and t.defer is False


def test_a_woken_goal_sees_every_hook_through_unify_iter():
    log = []
    register_attr_hook(_ORDER, lambda v, o, t: log.append("probe") or True)
    t, z, w = Trail(), Var(), Var()
    _freeze_var(z, _goal(lambda: log.append("goal")), t)
    put_attr(w, _ORDER, 1, t)
    assert len(list(unify_iter((z, w), (1, 2), t))) == 1
    assert log == ["probe", "goal"]


def test_a_failing_woken_goal_fails_the_unify_and_binds_nothing():
    t, z, w = Trail(), Var(), Var()
    _freeze_var(z, _goal(lambda: False), t)
    mark = t.mark()
    assert unify((z, w), (1, 2), t) is False
    assert is_var(deref(z)) and is_var(deref(w))
    assert t.mark() == mark and t.pending is None and t.defer is False
    assert get_attr(z, "freeze")      # still frozen


def test_a_raising_woken_goal_propagates_and_binds_nothing():
    def boom():
        raise ValueError("woken")
    t, z = Trail(), Var()
    _freeze_var(z, _goal(boom), t)
    mark = t.mark()
    with pytest.raises(ValueError, match="woken"):
        unify(z, 1, t)
    assert is_var(deref(z)) and t.mark() == mark
    assert t.pending is None and t.defer is False


def test_a_bare_unify_keeps_the_first_answer_only():
    t, z, y = Trail(), Var(), Var()

    def goal():
        for v in (1, 2, 3):
            m = t.mark()
            if unify(y, v, t):
                yield None
            t.undo(m)
    _freeze_var(z, goal, t)
    assert unify(z, "go", t)
    assert deref(y) == 1 and t.pending is None


def test_under_a_driver_every_answer_is_kept(tmp_path):
    p = tmp_path / "every.clausal"
    p.write_text("f(Y) :- freeze(X, member(Y, [1, 2, 3])), X = go.\n")
    mod = load_clausal_module(p)
    y = Var()
    assert [y.value for _ in solve(("f", y), mod)] == [1, 2, 3]


def test_under_a_driver_a_bare_unify_queues_and_does_not_drain():
    t, z = Trail(), Var()
    ran = []
    g = _goal(lambda: ran.append(1))
    _freeze_var(z, g, t)
    t.defer = True
    assert unify(z, 1, t)
    assert ran == [] and t.pending == (g,)


# ── re-entrancy ──────────────────────────────────────────────────────────────


def test_a_woken_goal_that_unifies_again_is_drained_once():
    """The goal of z binds v (frozen too).  The nested unify runs inside
    the outer drain, so it only queues; the outer drain runs v's goal after
    z's, once each."""
    log = []
    t, z, v = Trail(), Var(), Var()

    def zg():
        log.append(("z", t.defer))
        if unify(v, 2, t):
            log.append("z bound v")
            yield None
    _freeze_var(z, zg, t)
    _freeze_var(v, _goal(lambda: log.append("v")), t)
    assert unify(z, 1, t)
    assert log == [("z", True), "z bound v", "v"]
    assert t.pending is None and t.defer is False


def test_a_hook_that_unifies_does_not_drain_before_the_other_hooks():
    """A hook binding a frozen variable (as a CLP propagator does) wakes its
    goal; the goal still runs after every hook of the outer unification."""
    log = []
    t, z, w, u = Trail(), Var(), Var(), Var()

    def binder(value, other, trail):
        log.append("binder")
        return unify(u, 5, trail)
    register_attr_hook(_ORDER, binder)
    _freeze_var(u, _goal(lambda: log.append("u goal")), t)
    _freeze_var(w, _goal(lambda: log.append("w goal")), t)
    put_attr(z, _ORDER, 1, t)
    # w is bound first: its goal is queued before the binder hook runs
    assert unify((w, z), (2, 1), t)
    assert log == ["binder", "w goal", "u goal"]
    assert deref(u) == 5


def test_a_chain_of_woken_goals_is_bounded():
    """Each goal binds the next frozen variable: one drain runs the chain."""
    n = 200
    t = Trail()
    vs = [Var() for _ in range(n + 1)]
    for i in range(n):
        a, b = vs[i], vs[i + 1]

        def g(a=a, b=b):
            if unify(b, deref(a), t):
                yield None
        _freeze_var(a, g, t)
    assert unify(vs[0], "go", t)
    assert deref(vs[n]) == "go" and t.pending is None


def test_a_raising_hook_restores_defer():
    def hook(value, other, trail):
        raise ValueError("hook")
    register_attr_hook(_ORDER, hook)
    t, z = Trail(), Var()
    put_attr(z, _ORDER, 1, t)
    with pytest.raises(ValueError):
        unify(z, 1, t)
    assert t.defer is False


# ── when/2 outside a driver ──────────────────────────────────────────────────


def test_when_queues_a_goal_whose_condition_holds():
    from clausal.logic.coroutining import _run_now
    t = Trail()
    g = _goal(lambda: None)
    assert _run_now(g, t) is True
    assert t.pending == (g,)
