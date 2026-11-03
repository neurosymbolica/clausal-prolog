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
- In one unification the port does each bound variable's work in the
  order of the bindings, X1, X2, ..., Xn, as Scryer (and, by the SICStus
  manual's description of verify_attributes/3, SICStus) does: the first
  hook makes a stand-in for every bound member (DEVIATIONS.md D3), and
  each variable's own hook does that variable's work on its stand-in
  (ruling 2026-11-03, "Follow 1.3.3").  Until then the first hook did all
  of the work in the member list's order, newest first (X1, then Xn, ...,
  X2), which made binding the chain in one unification cubic in 1.3.3's
  own work.
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
#: The port before the ruling of 2026-11-03: X1's hook, then the
#: stand-ins of X6, X5, X4, X3, X2.
MEMBER_LIST_ORDER = [("solve_for_variable", "X1"), ("solve", 4, "S5"),
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


def test_one_unification_does_the_bound_variables_in_binding_order():
    selections = _selections(_all_at_once)
    assert selections == SCRYER_ONE_UNIFICATION
    assert selections != MEMBER_LIST_ORDER


def test_one_unification_in_reverse_does_them_in_its_binding_order():
    # Binding order is the unification's, not the member list's: the list
    # bound last to first selects what 1.3.3 selects last to first.
    def bind(t, xs):
        assert unify(xs[::-1], list(range(N))[::-1], t)
        assert any(True for _ in drain(t))
    assert _selections(bind) == LAST_TO_FIRST


def _implied(values, order):
    """{X1 + X2 = 3, X2 >= 1, X1 >= 2} (X1 = 2 implies X2 = 1), then
    f(X1, X2) = f(*values), bound in *order*: the answer and X1, X2."""
    t = Trail()
    x1, x2 = Var(), Var()
    assert h.q_eq(_sum(x1, x2), 3, t)
    assert h.q_ge(x2, 1, t) and h.q_ge(x1, 2, t)
    pairs = list(zip((x1, x2), values))
    if order == "X2 first":
        pairs.reverse()
    left = ("f",) + tuple(v for v, _ in pairs)
    right = ("f",) + tuple(n for _, n in pairs)
    ok = unify(left, right, t) and any(True for _ in drain(t))
    return ok, deref(x1), deref(x2)


def _sum(a, b):
    from clausal.terms import Add
    return Add(left=a, right=b)


def test_a_binding_implied_by_an_earlier_one_is_checked_against_its_own():
    # X1 = 2 implies X2 = 1 inside X1's work (bv.pl export_binding/1), so
    # X2's stand-in is bound before X2's turn; X2's own binding must then
    # agree with it.  (Scryer fails these unifications even where the
    # values agree; SICStus's driver is documented to unify instead.)
    assert _implied((2, 1), "X1 first") == (True, 2, 1)
    assert _implied((2, 7), "X1 first")[0] is False
    assert _implied((2, 1), "X2 first") == (True, 2, 1)
    assert _implied((2, 7), "X2 first")[0] is False
    assert _implied((3, 0), "X1 first")[0] is False
