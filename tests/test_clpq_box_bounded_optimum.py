"""sup/inf/maximize/minimize reach the optimum when variables are box-bounded.

The simplex parked a variable at its upper bound and dropped its objective
coefficient, and never let a variable at its upper bound fall again.  So
``X in [0, 2], Y in [0, 3], X + 2*Y =< 6`` maximised ``X + 3*Y`` at (2, 2) = 8
instead of (0, 3) = 9 (reported 2026-10-11).  The sweep checks random small
LPs against every vertex, worked out by brute force.
"""

import itertools
import random
from fractions import Fraction as F

import pytest

from clausal.logic.clpq import (
    in_q, q_le, sup, inf, maximize, minimize, _tableaux, _last_snapshot,
)
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref
from clausal.terms import Add, Mult
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
    obj = [rng.randint(-3, 3) for _ in range(n)]
    if not any(obj):
        obj[0] = 1
    return n, boxes, extra, obj


def _post(n, boxes, extra):
    t = Trail()
    xs = [Var() for _ in range(n)]
    for x, (lo, hi) in zip(xs, boxes):
        if not in_q(x, lo, hi, t):
            return None
    for a, b in extra:
        if not q_le(_expr(a, xs), b, t):
            return None
    return t, xs


@pytest.mark.parametrize("seed", range(300))
def test_random_box_bounded_lp_matches_the_vertices(seed):
    n, boxes, extra, obj = _random_lp(random.Random(seed))
    cons = list(extra)
    for i, (lo, hi) in enumerate(boxes):
        unit = [0] * n
        unit[i] = 1
        cons.append((unit, hi))
        cons.append(([-u for u in unit], -lo))
    expected = _vertex_range(n, cons, obj)
    posted = _post(n, boxes, extra)
    if expected is None:
        assert posted is None
        return
    lo_v, hi_v = expected
    for op, want in [(sup, hi_v), (inf, lo_v), (maximize, hi_v), (minimize, lo_v)]:
        t, xs = _post(n, boxes, extra)
        r = Var()
        assert op(_expr(obj, xs), r, t), op.__name__
        assert deref(r) == want, (op.__name__, n, boxes, extra, obj)
        if op in (maximize, minimize):
            point = [F(deref(x)) for x in xs]
            assert all(sum(F(ai) * xi for ai, xi in zip(a, point)) <= b
                       for a, b in cons)
