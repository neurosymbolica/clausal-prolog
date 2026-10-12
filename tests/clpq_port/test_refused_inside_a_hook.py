# tests/clpq_port/test_refused_inside_a_hook.py
"""Ruling R30: R27 is fail-closed.

A public entry point of the port that reads or writes the store raises
``error(permission_error(call, goal, Culprit), Name/Arity)`` while the
engine is dispatching attribute hooks (``trail.hooks_running`` above 0),
the shape the engine's ``solve``/``call`` raise there (a750f58c).  At a
goal, bare or under a driver, the same calls run.  clpfd's posts (``q_eq``
and the others, ``sync_fd_bounds``) are not refused: they queue (ruling
R28c, test_switch.py).  DEVIATIONS.md D3.
"""
from fractions import Fraction

import pytest

from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq import branch_and_bound as bb
from clausal.logic.clpq import holzbaur as h
from clausal.logic.clpq import normal_form as nf
from clausal.logic.clpq import residual_constraints as rc
from clausal.logic.clpq import variable_ordering as vo
from clausal.logic.exceptions import LogicException
from clausal.logic.pending import drain
from clausal.logic.variables import (
    Trail, Var, deref, is_var, put_attr, register_attr_hook, unify)
from clausal.pythonic_ast.nodes import Add, ArithEq, GtE, LtE

_PROBE_KEY = "clpq_test_refused_probe"


def _probe_hook(state, other, trail):
    return state(trail)


register_attr_hook(_PROBE_KEY, _probe_hook)


def _store():
    """{X + Q = 3, W >= Q + 1/2, W =< 20}: X, Q and W in one component."""
    t = Trail()
    x, q, w = Var(), Var(), Var()
    assert h.clpq_constraint_block(
        (ArithEq(left=Add(left=x, right=q), right=3),
         GtE(left=w, right=Add(left=q, right=Fraction(1, 2))),
         LtE(left=w, right=20)), t)
    return t, x, q, w


def _promote(trail):
    from clausal.logic.clpfd import FD_KEY, in_domain
    from clausal.logic.variables import get_attr
    variable = Var()
    assert in_domain(variable, 1, 5, trail)
    return h.promote_fd_to_q(variable, get_attr(variable, FD_KEY), trail)


#: (label, call(trail, w), Name, Arity).  Each call reads or writes the
#: store W is in.
_ENTRY_POINTS = [
    # the legacy API in front of the port (holzbaur.py)
    ("in_q", lambda t, w: h.in_q(w, 0, 30, t), "in_q", 3),
    ("sup", lambda t, w: h.sup(w, Var(), t), "sup", 2),
    ("inf", lambda t, w: h.inf(w, Var(), t), "inf", 2),
    ("maximize", lambda t, w: h.maximize(w, Var(), t), "maximize", 2),
    ("minimize", lambda t, w: h.minimize(w, Var(), t), "minimize", 2),
    ("bb_inf", lambda t, w: h.bb_inf([w], w, Var(), t), "bb_inf", 3),
    ("entailed", lambda t, w: h.entailed("=<", w, 30, t), "entailed", 1),
    ("dump_q", lambda t, w: h.dump_q([w], t), "dump_q", 2),
    ("residual_q", lambda t, w: h.residual_q([w], t, lambda v: "W"),
     "residual_q", 1),
    ("ordering", lambda t, w: h.ordering([w, Var()], t), "ordering", 1),
    ("clpq_constraint_block",
     lambda t, w: h.clpq_constraint_block((LtE(left=w, right=10),), t),
     "{}", 1),
    ("clpq_constraint_answers",
     lambda t, w: next(iter(h.clpq_constraint_answers(
         (LtE(left=w, right=10),), t)), None),
     "{}", 1),
    ("promote_fd_to_q", lambda t, w: _promote(t), "promote_fd_to_q", 1),
    # the port's own entry points (1.3.3's user predicates)
    ("nf.post_constraint",
     lambda t, w: nf.post_constraint(("=<", w, 10), t), "{}", 1),
    ("nf.post_constraint_with_choices",
     lambda t, w: nf.post_constraint_with_choices(("=<", w, 10), t),
     "{}", 1),
    ("nf.resume_constraint",
     lambda t, w: nf.resume_constraint(nf.ConstraintChoices([]), t),
     "resume_constraint", 1),
    ("nf.entailed", lambda t, w: nf.entailed(("=<", w, 30), t),
     "entailed", 1),
    ("bv.inf", lambda t, w: bv.inf(w, Var(), t), "inf", 2),
    ("bv.sup", lambda t, w: bv.sup(w, Var(), t), "sup", 2),
    ("bv.maximize", lambda t, w: bv.maximize(w, t), "maximize", 1),
    ("bv.minimize", lambda t, w: bv.minimize(w, t), "minimize", 1),
    ("bb.bb_inf", lambda t, w: bb.bb_inf([w], w, Var(), t), "bb_inf", 3),
    ("rc.dump", lambda t, w: rc.dump([w], ["W"], t), "dump", 3),
    ("rc.projecting_assert",
     lambda t, w: rc.projecting_assert(("clause", w), t),
     "projecting_assert", 1),
    ("vo.ordering", lambda t, w: vo.ordering([w, Var()], t), "ordering", 1),
]


def _inside_a_hook(call, driver):
    """Run *call* in a probe hook body (Z's, bound in one unification with
    X of the store), and return what it raised (None if nothing)."""
    t, x, q, w = _store()
    seen = {}

    def body(trail):
        seen["hooks_running"] = trail.hooks_running
        try:
            call(trail, w)
        except LogicException as exc:
            seen["raised"] = exc
        return True
    z = Var()
    put_attr(z, _PROBE_KEY, body, t)
    if driver:
        t.defer = True
    assert unify(("f", z, x), ("f", 1, 2), t)
    if driver:
        assert [None for _ in drain(t)][:1] == [None]
        t.defer = False
    assert seen["hooks_running"] >= 1
    return seen.get("raised")


@pytest.mark.parametrize("driver", [False, True])
@pytest.mark.parametrize(
    "label, call, name, arity", _ENTRY_POINTS,
    ids=[entry[0] for entry in _ENTRY_POINTS])
def test_an_entry_point_called_from_a_hook_is_refused(
        label, call, name, arity, driver):
    raised = _inside_a_hook(call, driver)
    assert raised is not None, f"{label} ran inside a hook"
    error, formal, context = raised.term
    assert error == "error"
    assert formal[:3] == ("permission_error", "call", "goal")
    culprit = formal[3]
    assert type(culprit) is tuple and culprit[0] == name
    assert len(culprit) == arity + 1
    assert context == ("/", name, arity)


@pytest.mark.parametrize("driver", [False, True])
@pytest.mark.parametrize(
    "label, call, name, arity", _ENTRY_POINTS,
    ids=[entry[0] for entry in _ENTRY_POINTS])
def test_an_entry_point_called_at_a_goal_runs(label, call, name, arity,
                                              driver):
    t, x, q, w = _store()
    t.defer = driver
    assert t.hooks_running == 0
    call(t, w)                          # raises nothing


def test_the_d3_repro_raises_instead_of_answering_wrong():
    # DEVIATIONS.md D3's R27 repro: a hook on another key dumps W and posts
    # {Q =< 1} in its body while X is bound with its hook still to come.
    # It gave `[W =< 20]` with Q left unbound (sup 1); now the dump is
    # refused, and the unification fails with the error.
    t, x, q, w = _store()
    out = {}

    def body(trail):
        out["dump"] = rc.dump([w], ["W"], trail)
        return nf.post_constraint(("=<", q, 1), trail)
    z = Var()
    put_attr(z, _PROBE_KEY, body, t)
    with pytest.raises(LogicException) as caught:
        unify(("f", z, x), ("f", 1, 2), t)
    assert "dump" not in out
    assert caught.value.term[1][:3] == ("permission_error", "call", "goal")
    assert caught.value.term[2] == ("/", "dump", 3)
    assert t.hooks_running == 0


def test_a_clpfd_post_from_a_hook_still_queues():
    # The adapter's q_* posts are not refused: R28c queues them.
    raised = _inside_a_hook(lambda t, w: h.q_le(w, 10, t), False)
    assert raised is None


def test_the_port_s_own_hook_is_not_refused():
    # The port's hook and its Later work run inside a unification: a
    # binding of a stored variable, and two stored variables unified,
    # bare and under a driver.
    for driver in (False, True):
        t, x, q, w = _store()
        t.defer = driver
        assert unify(x, 2, t)
        if driver:
            assert [None for _ in drain(t)][:1] == [None]
        assert deref(q) == 1
        t2 = Trail()
        a, b = Var(), Var()
        assert nf.post_constraint((">=", a, 1), t2)
        assert nf.post_constraint(("=<", b, 5), t2)
        t2.defer = driver
        assert unify(a, b, t2)
        if driver:
            assert [None for _ in drain(t2)][:1] == [None]
        low, high = Var(), Var()
        assert h.inf(a, low, t2) and h.sup(a, high, t2)
        assert (deref(low), deref(high)) == (1, 5)
