"""The CLP(Q) simplex: optima on box-bounded LPs, free variables, and
bounds on a variable an equality eliminates.

The simplex parked a variable at its upper bound and dropped its objective
coefficient, and never let a variable at its upper bound fall again.  So
``X in [0, 2], Y in [0, 3], X + 2*Y =< 6`` maximised ``X + 3*Y`` at (2, 2) = 8
instead of (0, 3) = 9 (reported 2026-10-11).  The sweep checks random small
LPs, some with an equality, against every vertex, worked out by brute force.
The review of that fix found two older faults in the same solver, pinned at
the end.
"""

import itertools
import random
from fractions import Fraction as F

import pytest

from clausal.logic.clpq import (
    in_q, q_eq, q_ge, q_le, q_lt, sup, inf, maximize, minimize, _tableaux, _last_snapshot,
)
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.terms import Add, Mult, Sub
from clausal.testing import load_clausal_module


@pytest.fixture(autouse=True)
def _clean_tableaux():
    _tableaux.clear()
    _last_snapshot.clear()
    yield
    _tableaux.clear()
    _last_snapshot.clear()


_PL = """\
:- use_module(library(clpq)).
region(X, Y) :- {X >= 0, X =< 2, Y >= 0, Y =< 3, X + 2*Y =< 6}.
by_sup(S) :- region(X, Y), sup(X + 3*Y, S).
by_maximize(S) :- region(X, Y), maximize(X + 3*Y, S).
by_inf(S) :- region(X, Y), inf(-X - 3*Y, S).
by_minimize(S) :- region(X, Y), minimize(-X - 3*Y, S).
at_max(X, Y) :- region(X, Y), maximize(X + 3*Y, _).
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("box") / "box.clausal"
    p.write_text(_PL)
    return load_clausal_module(p)


@pytest.mark.parametrize("name, value", [
    ("by_sup", 9), ("by_maximize", 9), ("by_inf", -9), ("by_minimize", -9),
])
def test_the_reported_region(mod, name, value):
    s = Var()
    assert [deref(s) for _ in solve((name, s), mod)] == [value]


def test_maximize_binds_the_optimal_vertex(mod):
    x, y = Var(), Var()
    assert [(deref(x), deref(y)) for _ in solve(("at_max", x, y), mod)] == [(0, 3)]


def _expr(coeffs, xs):
    e = None
    for c, x in zip(coeffs, xs):
        if c:
            t = Mult(left=c, right=x)
            e = t if e is None else Add(left=e, right=t)
    return e


def _solve_square(rows):
    """Gaussian elimination over F; the unique solution or None."""
    n = len(rows)
    m = [list(map(F, a)) + [F(b)] for a, b in rows]
    for col in range(n):
        piv = next((r for r in range(col, n) if m[r][col] != 0), None)
        if piv is None:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col and m[r][col] != 0:
                f = m[r][col] / m[col][col]
                m[r] = [a - f * b for a, b in zip(m[r], m[col])]
    return [m[i][n] / m[i][i] for i in range(n)]


def _vertex_range(n, cons, obj):
    """(min, max) of obj over {x : a.x <= b for (a, b) in cons}, or None."""
    vals = []
    for rows in itertools.combinations(cons, n):
        x = _solve_square(rows)
        if x is None:
            continue
        if all(sum(F(ai) * xi for ai, xi in zip(a, x)) <= b for a, b in cons):
            vals.append(sum(F(c) * xi for c, xi in zip(obj, x)))
    return (min(vals), max(vals)) if vals else None


def _random_lp(rng):
    n = rng.choice([2, 3])
    boxes = []
    for _ in range(n):
        lo = rng.randint(-2, 1)
        boxes.append((lo, lo + rng.randint(0, 4)))
    extra = []
    for _ in range(rng.randint(1, 3)):
        a = [rng.randint(-3, 3) for _ in range(n)]
        if any(a):
            extra.append((a, rng.randint(-2, 8)))
    eqs = []
    if rng.random() < .4:
        a = [rng.randint(-2, 2) for _ in range(n)]
        if any(a):
            eqs.append((a, rng.randint(-3, 3)))
    obj = [rng.randint(-3, 3) for _ in range(n)]
    if not any(obj):
        obj[0] = 1
    return n, boxes, extra, eqs, obj


def _post(n, boxes, extra, eqs):
    t = Trail()
    xs = [Var() for _ in range(n)]
    for x, (lo, hi) in zip(xs, boxes):
        if not in_q(x, lo, hi, t):
            return None
    for a, b in eqs:
        if not q_eq(_expr(a, xs), b, t):
            return None
    for a, b in extra:
        if not q_le(_expr(a, xs), b, t):
            return None
    return t, xs


@pytest.mark.parametrize("seed", range(300))
def test_random_box_bounded_lp_matches_the_vertices(seed):
    n, boxes, extra, eqs, obj = _random_lp(random.Random(seed))
    cons = list(extra)
    for a, b in eqs:
        cons.append((a, b))
        cons.append(([-u for u in a], -b))
    for i, (lo, hi) in enumerate(boxes):
        unit = [0] * n
        unit[i] = 1
        cons.append((unit, hi))
        cons.append(([-u for u in unit], -lo))
    expected = _vertex_range(n, cons, obj)
    posted = _post(n, boxes, extra, eqs)
    if expected is None:
        assert posted is None
        return
    lo_v, hi_v = expected
    for op, want in [(sup, hi_v), (inf, lo_v), (maximize, hi_v), (minimize, lo_v)]:
        t, xs = _post(n, boxes, extra, eqs)
        r = Var()
        assert op(_expr(obj, xs), r, t), op.__name__
        assert deref(r) == want, (op.__name__, n, boxes, extra, obj)
        if op in (maximize, minimize):
            point = [F(deref(x)) for x in xs]
            assert all(sum(F(ai) * xi for ai, xi in zip(a, point)) <= b
                       for a, b in cons)


def test_a_store_over_free_variables_is_feasible():
    # Restoring feasibility only let a variable sitting at a bound enter,
    # so a free one never could: {X + Y >= 2} failed.
    for rel, k in [(q_ge, 2), (q_le, -2)]:
        t, x, y = Trail(), Var(), Var()
        assert rel(Add(left=x, right=y), k, t)
    t, x, y = Trail(), Var(), Var()
    assert q_le(Sub(left=x, right=y), -2, t)


def test_an_eliminated_variable_keeps_its_bounds():
    # X = Y + 1 made X parametric and forgot 1 =< X =< 5, so Y = -10 passed.
    t, x, y = Trail(), Var(), Var()
    assert q_le(1, x, t) and q_le(x, 5, t)
    assert q_eq(x, Add(left=y, right=1), t)
    r = Var()
    assert inf(y, r, t) and deref(r) == 0
    assert not q_eq(y, -10, t)


@pytest.mark.parametrize("order", [
    "bind_last", "bind_first",
    pytest.param("bound_last", marks=pytest.mark.xfail(
        strict=True, reason="todo/clpq-strict-bounds-closed-by-inequalities")),
])
def test_a_strict_inequality_the_store_closes_fails(order):
    # X < Y with Y =< 3 and X = 3 leaves Y only in [3, 3] through a row,
    # not its own bounds, and the disequality was checked only once every
    # variable was fixed: X = 3 succeeded with Y = 3 (third review).
    t, x, y = Trail(), Var(), Var()
    steps = {
        "bind_last": [lambda: q_lt(x, y, t), lambda: q_le(y, 3, t),
                      lambda: unify(x, 3, t)],
        "bind_first": [lambda: unify(x, 3, t), lambda: q_lt(x, y, t),
                       lambda: q_le(y, 3, t)],
        "bound_last": [lambda: q_lt(x, y, t), lambda: q_ge(x, 3, t),
                       lambda: q_le(y, 3, t)],
    }[order]
    assert not all(step() for step in steps)


def test_an_equality_that_closes_a_strict_bound_fails():
    t, x, y = Trail(), Var(), Var()
    assert q_lt(Add(left=x, right=y), -1, t)
    assert not q_eq(Add(left=x, right=y), -1, t)


_CLOSED = """\
:- use_module(library(clpq)).
unify_vars :- {X < Y}, X = Y.
bind_elsewhere :- {A < B, B - A =< D}, D = 0.
post_elsewhere :- {A < B, B - A =< D}, {D = 0}.
"""


@pytest.mark.parametrize("name", ["unify_vars", "bind_elsewhere", "post_elsewhere"])
def test_a_binding_or_equality_that_closes_a_strict_bound_fails(tmp_path, name):
    # Every binding and equality checks every disequality, not only those
    # naming the variable bound (fifth review, 2026-10-11).
    p = tmp_path / "closed.clausal"
    p.write_text(_CLOSED)
    assert list(solve(name, load_clausal_module(p))) == []
