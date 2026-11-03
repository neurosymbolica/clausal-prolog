# tests/clpq_port/test_chain_binding_order.py
"""Binding a solved chain X1 =< ... =< Xn to numbers: which variable
bv.pl's solve/5 and solve_x/6 select at each binding, against 1.3.3's
text as Scryer's copy runs it
(implementation_plans/clpq/2026-11-03-chain-binding-divergence.md).

The Scryer sequences below were recorded from an instrumented copy of
Scryer's src/lib/clpq.pl (format/2 prints in solve/5, solve_x/6, bs/3 and
bs_collect_bindings/5) at n = 6.  Slack Sk is the variable that X(k+1)'s row
holds and X(k)'s does not: the slack of the constraint Xk =< X(k+1).

- One variable at a time, first to last or last to first, the port selects
  exactly what 1.3.3 selects.
- In one unification the port differs from the second binding on: the hook
  of the first variable does every bound member's work
  (attribute_hooks._stand_in_for_bound_members, DEVIATIONS.md D3) in the
  order of the component's member list, which is newest first, so after
  X1 it does Xn, ..., X2.  Scryer (and, by the SICStus manual's
  description of verify_attributes/3, SICStus) does X1, X2, ..., Xn, the
  order of the bindings.  That order makes the port's one-unification
  binding cubic in 1.3.3's own work where Scryer's is quadratic.  This test
  pins the difference; a change of the order must update it.
"""
from clausal.logic.clpq import bounded_simplex
from clausal.logic.clpq import holzbaur as h
from clausal.logic.clpq.attributes import state_of
from clausal.logic.pending import drain
from clausal.logic.variables import Trail, Var, deref, unify

N = 6

FIRST_TO_LAST = [("solve_for_variable", "X1"), ("solve", 4, "S1"),
                 ("solve", 4, "S2"), ("solve", 4, "S3"), ("solve", 4, "S4"),
                 ("solve", 4, "S5")]
LAST_TO_FIRST = [("solve", 2, "X1"), ("solve", 4, "S5"), ("solve", 4, "S4"),
                 ("solve", 4, "S3"), ("solve", 4, "S2"), ("solve", 4, "S1")]
#: Scryer's copy, L = [0, ..., 5] in one unification: verify_attributes/3
#: runs for X1, X2, ... in turn, so the selections are FIRST_TO_LAST's.
SCRYER_ONE_UNIFICATION = FIRST_TO_LAST
#: The port today: X1's hook, then the stand-ins of X6, X5, X4, X3, X2.
PORT_ONE_UNIFICATION = [("solve_for_variable", "X1"), ("solve", 4, "S5"),
                        ("solve", 4, "S4"), ("solve", 4, "S3"),
                        ("solve", 4, "S2"), ("solve", 4, "S1")]


def _order(variable):
    return id(deref(state_of(deref(variable)).variable_order))


def _chain():
    """The chain, and a namer from variable_order to X1.., S1.. ."""
    t = Trail()
    xs = [Var() for _ in range(N)]
    for a, b in zip(xs, xs[1:]):
        assert h.q_le(a, b, t)
    names = {_order(x): f"X{i + 1}" for i, x in enumerate(xs)}
    previous = {_order(xs[0])}
    for k in range(1, N):
        row = [_order(v) for v, _ in state_of(deref(xs[k])).linear_form.terms]
        for order in row:
            if order not in previous and order not in names:
                names[order] = f"S{k}"
        previous = set(row)
    return t, xs, lambda v: names[_order(v)]


def _selections(bind):
    t, xs, name = _chain()
    events = []

    def trace(event, *arguments):
        if event == "solve":
            events.append(("solve", arguments[0], name(arguments[1])))
        elif event == "solve_for_variable":
            events.append(("solve_for_variable", name(arguments[0])))

    previous = bounded_simplex.TRACE
    bounded_simplex.TRACE = trace
    try:
        bind(t, xs)
    finally:
        bounded_simplex.TRACE = previous
    return events


def _one_at_a_time(indices):
    def bind(t, xs):
        for i in indices:
            assert unify(xs[i], i, t)
            assert any(True for _ in drain(t))
    return bind


def _all_at_once(t, xs):
    assert unify(xs, list(range(N)), t)
    assert any(True for _ in drain(t))


def test_first_to_last_selects_what_1_3_3_selects():
    assert _selections(_one_at_a_time(range(N))) == FIRST_TO_LAST


def test_last_to_first_selects_what_1_3_3_selects():
    assert _selections(_one_at_a_time(range(N - 1, -1, -1))) == LAST_TO_FIRST


def test_one_unification_does_the_bound_members_newest_first():
    selections = _selections(_all_at_once)
    assert selections == PORT_ONE_UNIFICATION
    assert selections != SCRYER_ONE_UNIFICATION
