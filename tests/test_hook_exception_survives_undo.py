"""An attribute hook's exception reaches Python intact.

When a hook raised after a trailed change, ``unify`` undid the trail on its
error path, and ``trail_undo_to`` cleared the error indicator (after deleting
a fresh attribute, after a failed undo callback): Python then saw
``SystemError: <built-in function unify> returned NULL without setting an
exception`` instead of the hook's own exception.  The undo now keeps the
exception it was called with.
"""
from __future__ import annotations

import pytest

from clausal.logic.exceptions import LogicException, type_error
from clausal.logic.variables import (
    Trail, Var, deref, get_attr, is_var, put_attr, register_attr_hook, unify,
    unify_with_occurs_check,
)

_KEYS = ("probe_raise", "probe_first", "probe_second", "probe_cb",
         "probe_cb_ok", "probe_logic")


@pytest.fixture(autouse=True)
def _unregister():
    yield
    for k in _KEYS:
        register_attr_hook(k, None)


def _trailing_raiser(exc, made):
    def hook(value, other, trail):
        z = Var()
        made.append(z)
        put_attr(z, "k", 1, trail)
        raise exc
    return hook


@pytest.mark.parametrize("unify_fn", [unify, unify_with_occurs_check])
def test_hook_exception_after_trailed_change(unify_fn):
    made = []
    register_attr_hook("probe_raise", _trailing_raiser(ValueError("boom"), made))
    t = Trail()
    x = Var()
    put_attr(x, "probe_raise", 1, t)
    with pytest.raises(ValueError, match="boom"):
        unify_fn(x, 1, t)
    # the trail is fully undone: x unbound, z's attribute gone
    assert is_var(deref(x))
    assert get_attr(x, "probe_raise") == 1
    (z,) = made
    assert get_attr(z, "k") is None


def test_raising_undo_callback_keeps_the_hook_exception():
    undone = []

    def bad_undo():
        undone.append(True)
        raise RuntimeError("undo failed")

    def hook(value, other, trail):
        trail.record(bad_undo)
        raise ValueError("boom")

    register_attr_hook("probe_cb", hook)
    t = Trail()
    x = Var()
    put_attr(x, "probe_cb", 1, t)
    with pytest.raises(ValueError, match="boom"):
        unify(x, 1, t)
    assert undone == [True]
    assert is_var(deref(x))


def test_succeeding_undo_callback_runs_and_keeps_the_hook_exception():
    undone = []

    def hook(value, other, trail):
        trail.record(lambda: undone.append(True))
        raise ValueError("boom")

    register_attr_hook("probe_cb_ok", hook)
    t = Trail()
    x = Var()
    put_attr(x, "probe_cb_ok", 1, t)
    with pytest.raises(ValueError, match="boom"):
        unify(x, 1, t)
    assert undone == [True]
    assert is_var(deref(x))


def test_second_hook_raises_after_first_trailed_a_change():
    made = []

    def first(value, other, trail):
        z = Var()
        made.append(z)
        put_attr(z, "k", 1, trail)
        return True

    register_attr_hook("probe_first", first)
    register_attr_hook("probe_second", _trailing_raiser(ValueError("second"), made))
    t = Trail()
    x, y = Var(), Var()
    put_attr(x, "probe_first", 1, t)
    put_attr(y, "probe_second", 1, t)
    with pytest.raises(ValueError, match="second"):
        unify((x, y), (1, 2), t)
    assert is_var(deref(x)) and is_var(deref(y))
    assert len(made) == 2
    assert all(get_attr(z, "k") is None for z in made)


def test_logic_exception_from_a_hook_arrives_intact():
    term = type_error("integer", "a", "probe/1")
    made = []
    register_attr_hook("probe_logic", _trailing_raiser(LogicException(term), made))
    t = Trail()
    x = Var()
    put_attr(x, "probe_logic", 1, t)
    with pytest.raises(LogicException) as info:
        unify(x, 1, t)
    assert info.value.term == term
    assert is_var(deref(x))
