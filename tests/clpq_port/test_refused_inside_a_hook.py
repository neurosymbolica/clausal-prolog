# tests/clpq_port/test_refused_inside_a_hook.py
"""Ruling R30: R27 is fail-closed.

A public entry point of the port that reads or writes the store raises
``error(permission_error(call, goal, Culprit), Name/Arity)`` while the
engine is dispatching attribute hooks (``trail.hooks_running`` above 0,
or ``hook_dispatch_depth()`` above 0 for a fresh trail built inside a
hook, DEVIATIONS.md D26), the shape the engine's ``solve``/``call`` raise there (a750f58c).  At a
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
    Trail, Var, deref, hook_dispatch_depth, is_var, put_attr,
    register_attr_hook, unify)
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
    ("in_q/3", lambda t, w: h.in_q(w, 0, 30, t), "in_q", 3),
    ("in_q/1", lambda t, w: h.in_q(w, trail=t), "in_q", 1),
    ("in_q/3 one bound", lambda t, w: h.in_q(w, 0, None, t), "in_q", 3),
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
    ("bv.inf/4", lambda t, w: bv.inf(w, Var(), t, [w], [Var()]), "inf", 4),
    ("bv.sup/4", lambda t, w: bv.sup(w, Var(), t, [w], [Var()]), "sup", 4),
    ("bv.maximize", lambda t, w: bv.maximize(w, t), "maximize", 1),
    ("bv.minimize", lambda t, w: bv.minimize(w, t), "minimize", 1),
    ("bb.bb_inf", lambda t, w: bb.bb_inf([w], w, Var(), t), "bb_inf", 3),
    ("bb.bb_inf/5",
     lambda t, w: bb.bb_inf([w], w, Var(), t, Var(), Fraction(1, 1000)),
     "bb_inf", 5),
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
    assert not _holds_none(culprit), culprit
    # The indicator is the term's; the prose does not repeat it.
    assert not raised.message.startswith(f"{name}/"), raised.message


def _holds_none(term):
    stack = [term]
    while stack:
        item = deref(stack.pop())
        if item is None:
            return True
        if type(item) in (tuple, list):
            stack.extend(item)
    return False


def test_an_omitted_argument_is_a_variable_in_the_culprit():
    # in_q(X, 0) with no upper bound: in_q/3, the missing Hi a variable.
    raised = _inside_a_hook(lambda t, w: h.in_q(w, 0, None, t), False)
    culprit = raised.term[1][3]
    assert culprit[0] == "in_q" and culprit[2] == 0 and is_var(culprit[3])


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


def test_a_fresh_trail_inside_a_hook_is_refused_too():
    # Ruling R31's limit is closed: the check reads hook_dispatch_depth()
    # as well as the counter of the trail it is given.  D3's repro through
    # a fresh Trail inside a hook: the fresh trail reads 0, the thread's
    # dispatch depth reads 1, and dump/3 refuses instead of answering
    # `[W =< 20]` with Q left unbound.
    t, x, q, w = _store()
    out = {}

    def body(trail):
        other = Trail()
        out["hooks_running"] = other.hooks_running
        out["depth"] = hook_dispatch_depth()
        out["dump"] = rc.dump([w], ["W"], other)
        return nf.post_constraint(("=<", q, 1), other)
    z = Var()
    put_attr(z, _PROBE_KEY, body, t)
    with pytest.raises(LogicException) as caught:
        unify(("f", z, x), ("f", 1, 2), t)
    assert out == {"hooks_running": 0, "depth": 1}
    assert caught.value.term[1][:3] == ("permission_error", "call", "goal")
    assert caught.value.term[2] == ("/", "dump", 3)
    assert t.hooks_running == 0 and hook_dispatch_depth() == 0


def _inside_a_hook_on_a_fresh_trail(call):
    """Run *call* in a probe hook body with a fresh Trail, not the hook's:
    return what it raised (None if nothing)."""
    t, x, q, w = _store()
    seen = {}

    def body(trail):
        other = Trail()
        seen["hooks_running"] = other.hooks_running
        try:
            call(other, w)
        except LogicException as exc:
            seen["raised"] = exc
        return True
    z = Var()
    put_attr(z, _PROBE_KEY, body, t)
    assert unify(("f", z, x), ("f", 1, 2), t)
    assert seen["hooks_running"] == 0
    return seen.get("raised")


@pytest.mark.parametrize(
    "label, call, name, arity", _ENTRY_POINTS,
    ids=[entry[0] for entry in _ENTRY_POINTS])
def test_an_entry_point_called_from_a_hook_on_a_fresh_trail_is_refused(
        label, call, name, arity):
    raised = _inside_a_hook_on_a_fresh_trail(call)
    assert raised is not None, f"{label} ran inside a hook on a fresh trail"
    assert raised.term[1][:3] == ("permission_error", "call", "goal")
    assert raised.term[2] == ("/", name, arity)


_LIBRARY_POSTS = [
    ("q_le", lambda t, w: h.q_le(w, 10, t), ("{}", "LtE")),
    ("q_eq", lambda t, w: h.q_eq(w, 10, t), ("{}", "ArithEq")),
    ("q_ne", lambda t, w: h.q_ne(w, 10, t), ("{}", "ArithNeq")),
    ("q_lt", lambda t, w: h.q_lt(w, 10, t), ("{}", "Lt")),
    ("q_gt", lambda t, w: h.q_gt(w, 1, t), ("{}", "Gt")),
    ("q_ge", lambda t, w: h.q_ge(w, 1, t), ("{}", "GtE")),
    ("sync_fd_bounds", lambda t, w: h.sync_fd_bounds(w, 2, 5, t), None),
]


def _w_bounds(t, w):
    low, high = Var(), Var()
    return (deref(low) if h.inf(w, low, t) else None,
            deref(high) if h.sup(w, high, t) else None)


@pytest.mark.parametrize(
    "label, post, culprit", _LIBRARY_POSTS,
    ids=[entry[0] for entry in _LIBRARY_POSTS])
def test_a_clpfd_post_from_a_hook_on_a_fresh_trail_is_refused(
        label, post, culprit):
    # D26: a post from clpfd on a fresh trail inside another trail's
    # dispatch cannot be queued: that trail's goal boundary may come while
    # the outer dispatch is still running (a driver on the fresh trail,
    # or a drain of it in the hook body), where the queued post would
    # read R27's unhooked bindings or be refused by {}/1 -- an error from
    # a post the caller never saw.  It is refused where it is made, with
    # the {}/1 culprit, and the store is unchanged.
    t, x, q, w = _store()
    seen = {}

    def body(trail):
        other = Trail()
        try:
            post(other, w)
        except LogicException as exc:
            seen["raised"] = exc
        seen["pending"] = other.pending
        return True
    z = Var()
    put_attr(z, _PROBE_KEY, body, t)
    assert unify(("f", z, x), ("f", 1, 2), t)
    raised = seen.get("raised")
    assert raised is not None, f"{label} was not refused"
    assert seen["pending"] is None
    assert raised.term[1][:3] == ("permission_error", "call", "goal")
    assert raised.term[2] == ("/", "{}", 1)
    assert "hook's own trail" in raised.message, raised.message
    if culprit is not None:
        assert raised.term[1][3][0] == "{}"
        assert type(raised.term[1][3][1]).__name__ == culprit[1]
    t2, x2, q2, w2 = _store()
    assert unify(x2, 2, t2)
    assert _w_bounds(t, w) == _w_bounds(t2, w2)


def test_a_fresh_trail_drained_inside_the_hook_raises_no_queued_post():
    # The review's reproducer: a hook that posts on a fresh trail and
    # drains it there.  Queued, the post ran at the drain, inside the
    # dispatch, and {}/1 refused it: a permission_error out of drain/1 for
    # a goal the hook never called.  Now the post itself is refused.
    t = Trail()
    w, x = Var(), Var()
    assert h.q_ge(w, 0, t) and h.q_le(x, 5, t)
    seen = {}

    def body(trail):
        other = Trail()
        try:
            h.q_le(w, 10, other)
            seen["post"] = "ran"
        except LogicException as exc:
            seen["post"] = exc.term[2]
        seen["drain"] = [None for _ in drain(other)][:1]
        return True
    z = Var()
    put_attr(z, _PROBE_KEY, body, t)
    assert unify(("f", z, x), ("f", 1, 2), t)
    assert seen == {"post": ("/", "{}", 1), "drain": [None]}
    assert _w_bounds(t, w) == (0, None)


def test_a_clpfd_post_inside_a_nested_dispatch_on_a_fresh_trail_is_refused():
    # Inside A's dispatch, a unification on a fresh trail B dispatches B's
    # hooks: B's counter is 1, the depth 2.  B's queue is drained when B's
    # dispatch ends, still inside A's, so the post is refused there too.
    t, x, q, w = _store()
    seen = {}

    def inner(trail):
        seen["counts"] = (trail.hooks_running, hook_dispatch_depth())
        try:
            h.q_le(w, 10, trail)
            seen["post"] = "queued"
        except LogicException as exc:
            seen["post"] = exc.term[2]
        return True

    def body(trail):
        other = Trail()
        y = Var()
        put_attr(y, _PROBE_KEY, inner, other)
        assert unify(y, 1, other)
        return True
    z = Var()
    put_attr(z, _PROBE_KEY, body, t)
    assert unify(("f", z, x), ("f", 1, 2), t)
    assert seen == {"counts": (1, 2), "post": ("/", "{}", 1)}


def test_a_clpfd_post_inside_the_trail_s_own_dispatch_is_still_queued():
    # The dispatch on the post's own trail, nested or not, still queues:
    # every level of the depth is that trail's, so its queue runs after
    # the outermost hook, at a goal.
    t, x, q, w = _store()
    seen = {}

    def inner(trail):
        seen["counts"] = (trail.hooks_running, hook_dispatch_depth())
        before = trail.pending
        assert h.q_le(w, 10, trail)
        seen["queued"] = trail.pending is not before
        return True

    def body(trail):
        y = Var()
        put_attr(y, _PROBE_KEY, inner, trail)
        assert unify(y, 1, trail)
        return True
    z = Var()
    put_attr(z, _PROBE_KEY, body, t)
    assert unify(("f", z, x), ("f", 1, 2), t)
    assert seen == {"counts": (2, 2), "queued": True}
    assert _w_bounds(t, w)[1] == 10
