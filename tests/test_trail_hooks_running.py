"""``trail.hooks_running``: how deep the trail is in attribute-hook dispatch.

A constraint library must tell apart two places that both see
``trail.defer`` true:

* inside an attribute hook (the unification that bound the variable is
  still firing its hooks): it must QUEUE what it would post -- a hook body
  never runs another library's entry point in place;
* at a goal (a body goal, a woken goal run at a goal boundary): it may post
  in place.

``hooks_running`` counts the attribute-hook dispatches in progress on the
trail: 0 at a goal, under a driver or bare; 1 inside a hook; one more per
unification nested inside a hook that fires hooks of its own.  It is
restored on every exit, a raising hook included.
"""
from __future__ import annotations

import pathlib

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import (
    Trail, Var, put_attr, register_attr_hook, unify,
)
from clausal.testing import load_clausal_module

_A = "probe_hooks_running_a"
_B = "probe_hooks_running_b"
_R = "probe_hooks_running_raise"

_SEAM = "bind(X) <- (X is 1)\n"


@pytest.fixture(autouse=True)
def _unregister():
    yield
    for key in (_A, _B, _R):
        register_attr_hook(key, None)


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("hooks_running") / "m.seam"
    p.write_text(_SEAM)
    return load_clausal_module(p)


def _recording_hook(log, tag, queue_goal=True):
    """A hook logging the count it sees, then queueing a goal that logs the
    count the goal sees when the engine runs it at a goal boundary."""
    def hook(_attr, _bound_to, trail):
        log.append((tag, trail.hooks_running))
        if queue_goal:
            def goal():
                log.append((tag + " goal", trail.hooks_running))
                yield None
            trail.push_pending(goal)
        return True
    return hook


def test_a_fresh_trail_is_at_a_goal():
    assert Trail().hooks_running == 0


def test_bare_inside_a_hook_and_at_the_woken_goal():
    log = []
    register_attr_hook(_A, _recording_hook(log, "hook"))
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    assert unify(x, 1, t)
    assert log == [("hook", 1), ("hook goal", 0)]
    assert t.hooks_running == 0


def test_under_a_driver_inside_a_hook_and_at_the_woken_goal(mod):
    log = []
    register_attr_hook(_A, _recording_hook(log, "hook"))
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    answers = 0
    for tr in solve(("bind", x), mod, trail=t):
        assert tr.hooks_running == 0
        answers += 1
    assert answers == 1
    assert log == [("hook", 1), ("hook goal", 0)]
    assert t.hooks_running == 0


def test_defer_alone_cannot_tell_a_hook_from_a_goal(mod):
    # Why the counter exists: under a driver defer is set in both places.
    seen = []
    def hook(_attr, _bound_to, trail):
        seen.append(("hook", trail.defer, trail.hooks_running))
        def goal():
            seen.append(("goal", trail.defer, trail.hooks_running))
            yield None
        trail.push_pending(goal)
        return True
    register_attr_hook(_A, hook)
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    assert len(list(solve(("bind", x), mod, trail=t))) == 1
    assert seen == [("hook", True, 1), ("goal", True, 0)]


def _nesting_hooks(log):
    """Hook A unifies a second attributed variable, whose hook B fires
    nested inside A's dispatch."""
    def hook_a(_attr, _bound_to, trail):
        log.append(("a before", trail.hooks_running))
        y = Var()
        put_attr(y, _B, 1, trail)
        ok = unify(y, 2, trail)
        log.append(("a after", trail.hooks_running))
        return ok
    def hook_b(_attr, _bound_to, trail):
        log.append(("b", trail.hooks_running))
        return True
    register_attr_hook(_A, hook_a)
    register_attr_hook(_B, hook_b)


def test_a_unify_nested_in_a_hook_counts_up_bare():
    log = []
    _nesting_hooks(log)
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    assert unify(x, 1, t)
    assert log == [("a before", 1), ("b", 2), ("a after", 1)]
    assert t.hooks_running == 0


def test_a_unify_nested_in_a_hook_counts_up_under_a_driver(mod):
    log = []
    _nesting_hooks(log)
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    assert len(list(solve(("bind", x), mod, trail=t))) == 1
    assert log == [("a before", 1), ("b", 2), ("a after", 1)]
    assert t.hooks_running == 0


class _Boom(Exception):
    pass


def _raising_hook(_attr, _bound_to, trail):
    raise _Boom(trail.hooks_running)


def test_restored_after_a_raising_hook_bare():
    register_attr_hook(_R, _raising_hook)
    t, x = Trail(), Var()
    put_attr(x, _R, 1, t)
    with pytest.raises(_Boom) as info:
        unify(x, 1, t)
    assert info.value.args == (1,)
    assert t.hooks_running == 0
    # and the next dispatch starts from zero again
    log = []
    register_attr_hook(_A, _recording_hook(log, "hook", queue_goal=False))
    y = Var()
    put_attr(y, _A, 1, t)
    assert unify(y, 1, t)
    assert log == [("hook", 1)]


def test_restored_after_a_raising_hook_under_a_driver(mod):
    register_attr_hook(_R, _raising_hook)
    t, x = Trail(), Var()
    put_attr(x, _R, 1, t)
    with pytest.raises(Exception):
        list(solve(("bind", x), mod, trail=t))
    assert t.hooks_running == 0


def test_restored_after_a_nested_hook_raises_and_is_caught():
    log = []
    def hook_a(_attr, _bound_to, trail):
        y = Var()
        put_attr(y, _R, 1, trail)
        try:
            unify(y, 2, trail)
        except _Boom as exc:
            log.append(("caught at", exc.args[0]))
        log.append(("a after", trail.hooks_running))
        return True
    register_attr_hook(_A, hook_a)
    register_attr_hook(_R, _raising_hook)
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    assert unify(x, 1, t)
    assert log == [("caught at", 2), ("a after", 1)]
    assert t.hooks_running == 0


def test_a_failing_hook_restores_it():
    register_attr_hook(_A, lambda a, b, t: False)
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    assert not unify(x, 1, t)
    assert t.hooks_running == 0


def test_read_only():
    t = Trail()
    with pytest.raises(AttributeError):
        t.hooks_running = 1
    assert t.hooks_running == 0


# ── No driver on the trail inside a hook ─────────────────────────────────────
#
# A hook that drove a goal on its own trail ran that driver INSIDE the outer
# dispatch (hooks_running > 0 throughout), and the driver's first goal
# boundary ran the goals the OUTER unification had queued so far; leaving the
# driver undid that take, so they ran a second time at the outer boundary.
# A hook body queues; it never runs goals in place: solve/call on a trail
# whose hooks are running are refused with an ISO permission error.

from clausal.logic.exceptions import LogicException  # noqa: E402
from clausal.logic.solve import call  # noqa: E402


def _nested_driver_hook(log, drive):
    def hook(_attr, _bound_to, trail):
        def queued():
            log.append(("queued goal ran", trail.hooks_running))
            yield None
        trail.push_pending(queued)
        try:
            for _ in drive(trail):
                log.append(("nested answer", trail.hooks_running))
        except LogicException as exc:
            log.append(("refused", exc.term))
        return True
    return hook


def _assert_refusal(term, goal, context):
    """The whole error term: error(permission_error(call, goal, Goal), PI),
    the goal compared element by element (a Var by identity)."""
    assert type(term) is tuple and len(term) == 3, term
    assert term[0] == "error"
    assert term[2] == context, term
    formal = term[1]
    assert formal[:3] == ("permission_error", "call", "goal"), formal
    culprit = formal[3]
    assert len(culprit) == len(goal) and all(
        a is b or a == b for a, b in zip(culprit, goal)), (culprit, goal)
    assert len(formal) == 4


def test_solve_on_the_trail_inside_a_hook_is_refused_and_nothing_runs_twice(mod):
    log = []
    goal = ("bind", Var())
    register_attr_hook(_A, _nested_driver_hook(
        log, lambda tr: solve(goal, mod, trail=tr)))
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    assert unify(x, 1, t)
    assert [e[0] for e in log] == ["refused", "queued goal ran"]
    _assert_refusal(log[0][1], goal, ("/", "solve", 2))
    assert log[1] == ("queued goal ran", 0)
    assert t.hooks_running == 0


def test_solve_on_the_trail_inside_a_hook_is_refused_under_a_driver(mod):
    log = []
    goal = ("bind", Var())
    register_attr_hook(_A, _nested_driver_hook(
        log, lambda tr: solve(goal, mod, trail=tr)))
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    assert len(list(solve(("bind", x), mod, trail=t))) == 1
    assert [e[0] for e in log] == ["refused", "queued goal ran"]
    _assert_refusal(log[0][1], goal, ("/", "solve", 2))
    assert log[1] == ("queued goal ran", 0)
    assert t.hooks_running == 0


def test_call_on_the_trail_inside_a_hook_is_refused(mod):
    log = []
    v = Var()
    register_attr_hook(_A, _nested_driver_hook(
        log, lambda tr: call("bind", v, module=mod, trail=tr)))
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    assert unify(x, 1, t)
    assert [e[0] for e in log] == ["refused", "queued goal ran"]
    # The goal call/N would have run, and call/N's indicator: the functor
    # is call's first argument, so call("bind", V) is call/2.
    _assert_refusal(log[0][1], ("bind", v), ("/", "call", 2))


def test_a_driver_on_a_fresh_trail_inside_a_hook_is_allowed(mod):
    log = []
    register_attr_hook(_A, _nested_driver_hook(
        log, lambda _tr: solve(("bind", Var()), mod, trail=Trail())))
    t, x = Trail(), Var()
    put_attr(x, _A, 1, t)
    assert unify(x, 1, t)
    assert log == [("nested answer", 1), ("queued goal ran", 0)]
