"""``hook_dispatch_depth()``: attribute-hook dispatch in progress, on any trail.

``trail.hooks_running`` counts the dispatches on ONE trail.  A hook body
that builds a fresh ``Trail()`` and calls a library on it sees 0 there, so
the library takes itself to be at a goal and posts in place -- the "never
run a library entry point inside a hook" rule is bypassed.

``hook_dispatch_depth()`` counts the dispatches in progress in the calling
THREAD, whatever their trail: 0 at a goal, one more per dispatch nested
inside a hook, across trails.  It is restored on every exit of a dispatch
(success, a failing hook, a raising hook).  Another thread has its own.
"""
from __future__ import annotations

import threading

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import (
    Trail, Var, hook_dispatch_depth, put_attr, register_attr_hook, unify,
)
from clausal.testing import load_clausal_module

_A = "probe_dispatch_depth_a"
_B = "probe_dispatch_depth_b"
_R = "probe_dispatch_depth_raise"
_F = "probe_dispatch_depth_fail"


@pytest.fixture(autouse=True)
def _unregister():
    yield
    for key in (_A, _B, _R, _F):
        register_attr_hook(key, None)


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("dispatch_depth") / "m.seam"
    p.write_text("bind(X) <- (X is 1)\n")
    return load_clausal_module(p)


class _Boom(Exception):
    pass


def _bind(key, value=1, trail=None):
    t = trail if trail is not None else Trail()
    x = Var()
    put_attr(x, key, 1, t)
    return unify(x, value, t), t


def test_zero_at_a_goal():
    assert hook_dispatch_depth() == 0


def test_one_inside_a_hook_and_zero_at_the_woken_goal():
    log = []
    def hook(_attr, _bound_to, trail):
        log.append(("hook", hook_dispatch_depth(), trail.hooks_running))
        def goal():
            log.append(("goal", hook_dispatch_depth(), trail.hooks_running))
            yield None
        trail.push_pending(goal)
        return True
    register_attr_hook(_A, hook)
    ok, t = _bind(_A)
    assert ok
    assert log == [("hook", 1, 1), ("goal", 0, 0)]
    assert hook_dispatch_depth() == 0


def test_a_fresh_trail_inside_a_hook_still_counts():
    # The bypass: on the fresh trail hooks_running is 0, the global depth is not.
    log = []
    def hook_a(_attr, _bound_to, trail):
        fresh = Trail()
        log.append(("a", hook_dispatch_depth(), trail.hooks_running,
                    fresh.hooks_running))
        y = Var()
        put_attr(y, _B, 1, fresh)
        ok = unify(y, 2, fresh)
        log.append(("a after", hook_dispatch_depth(), trail.hooks_running))
        return ok
    def hook_b(_attr, _bound_to, trail):
        log.append(("b", hook_dispatch_depth(), trail.hooks_running))
        return True
    register_attr_hook(_A, hook_a)
    register_attr_hook(_B, hook_b)
    ok, _t = _bind(_A)
    assert ok
    assert log == [("a", 1, 1, 0), ("b", 2, 1), ("a after", 1, 1)]
    assert hook_dispatch_depth() == 0


def test_nested_on_the_same_trail_counts_up():
    log = []
    def hook_a(_attr, _bound_to, trail):
        y = Var()
        put_attr(y, _B, 1, trail)
        ok = unify(y, 2, trail)
        log.append(("a after", hook_dispatch_depth()))
        return ok
    def hook_b(_attr, _bound_to, trail):
        log.append(("b", hook_dispatch_depth(), trail.hooks_running))
        return True
    register_attr_hook(_A, hook_a)
    register_attr_hook(_B, hook_b)
    ok, _t = _bind(_A)
    assert ok
    assert log == [("b", 2, 2), ("a after", 1)]
    assert hook_dispatch_depth() == 0


def test_restored_after_a_raising_hook():
    def hook(_attr, _bound_to, _trail):
        raise _Boom(hook_dispatch_depth())
    register_attr_hook(_R, hook)
    with pytest.raises(_Boom) as info:
        _bind(_R)
    assert info.value.args == (1,)
    assert hook_dispatch_depth() == 0


def test_restored_after_a_failing_hook():
    seen = []
    def hook(_attr, _bound_to, _trail):
        seen.append(hook_dispatch_depth())
        return False
    register_attr_hook(_F, hook)
    ok, _t = _bind(_F)
    assert not ok
    assert seen == [1]
    assert hook_dispatch_depth() == 0


def test_restored_after_a_nested_dispatch_on_a_fresh_trail_raises():
    log = []
    def hook_a(_attr, _bound_to, _trail):
        try:
            _bind(_R)
        except _Boom as exc:
            log.append(("caught at", exc.args[0]))
        log.append(("a after", hook_dispatch_depth()))
        return True
    def hook_r(_attr, _bound_to, _trail):
        raise _Boom(hook_dispatch_depth())
    register_attr_hook(_A, hook_a)
    register_attr_hook(_R, hook_r)
    ok, _t = _bind(_A)
    assert ok
    assert log == [("caught at", 2), ("a after", 1)]
    assert hook_dispatch_depth() == 0


def test_restored_under_a_driver(mod):
    def hook(_attr, _bound_to, _trail):
        raise _Boom(hook_dispatch_depth())
    register_attr_hook(_R, hook)
    t, x = Trail(), Var()
    put_attr(x, _R, 1, t)
    with pytest.raises(Exception):
        list(solve(("bind", x), mod, trail=t))
    assert hook_dispatch_depth() == 0


def test_a_fresh_trail_driver_inside_a_hook_is_still_allowed(mod):
    # The permission docs/coroutining.md gives is kept: solve() refuses only
    # on the trail whose hooks are running.  The driver sees the depth.
    log = []
    def hook(_attr, _bound_to, _trail):
        y = Var()
        for _tr in solve(("bind", y), mod, trail=Trail()):
            log.append(("driven", hook_dispatch_depth()))
            break
        return True
    register_attr_hook(_A, hook)
    ok, _t = _bind(_A)
    assert ok
    assert log == [("driven", 1)]
    assert hook_dispatch_depth() == 0


def test_another_thread_sees_zero():
    seen = []
    def hook(_attr, _bound_to, _trail):
        here = hook_dispatch_depth()
        out = []
        th = threading.Thread(target=lambda: out.append(hook_dispatch_depth()))
        th.start()
        th.join()
        seen.append((here, out[0]))
        return True
    register_attr_hook(_A, hook)
    ok, _t = _bind(_A)
    assert ok
    assert seen == [(1, 0)]


def test_a_thread_inside_its_own_hook_does_not_move_this_threads_depth():
    inside = threading.Event()
    release = threading.Event()
    seen = []
    def hook(_attr, _bound_to, _trail):
        seen.append(("other", hook_dispatch_depth()))
        inside.set()
        release.wait(10)
        return True
    register_attr_hook(_A, hook)
    th = threading.Thread(target=lambda: _bind(_A))
    th.start()
    assert inside.wait(10)
    seen.append(("main", hook_dispatch_depth()))
    release.set()
    th.join()
    assert seen == [("other", 1), ("main", 0)]
