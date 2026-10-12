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
