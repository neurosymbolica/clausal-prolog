"""dump_q/2 projects the CLP(Q) store onto the variables it is given.

Fixed 2026-10-11: projecting ``X + Y = 3`` onto ``X`` answered ``X = 3``
(the equality that eliminated ``Y`` was kept with ``Y`` struck out), and a
strict bound or a disequality was not shown at all.
"""

from fractions import Fraction

import pytest

from clausal.logic.clpq import dump_q, inf, q_eq, q_ge, q_lt, q_gt, q_ne, q_le, sup
from clausal.logic.variables import deref
from clausal.logic.variables import Trail, Var
from clausal.terms import Add, Mult


def _names(*vs):
    return {id(v): n for v, n in zip(vs, "XYZ")}


def _dump(vs, t, **kw):
    names = _names(*vs)
    return dump_q(list(vs), t, lambda v: names[id(v)], **kw)


def test_an_eliminated_variable_takes_its_equality_with_it():
    t, x, y = Trail(), Var(), Var()
    assert q_eq(Add(left=x, right=y), 3, t)
    assert _dump([x], t) == []
    assert _dump([x, y], t) == ["{X + Y = 3}"]


def test_a_dependent_system_is_one_equality():
    t, x, y = Trail(), Var(), Var()
    assert q_eq(Add(left=x, right=y), 3, t)
    assert q_eq(Add(left=Mult(left=2, right=x), right=Mult(left=2, right=y)), 6, t)
    assert _dump([x, y], t) == ["{X + Y = 3}"]


def test_strict_bounds():
    t, x = Trail(), Var()
    assert q_gt(x, 1, t) and q_lt(x, 3, t)
    assert _dump([x], t) == ["{-X < -1}", "{X < 3}"]
    assert _dump([x], t, toplevel=True) == ["{X > 1}", "{X < 3}"]


def test_a_disequality():
    t, x = Trail(), Var()
    assert q_ne(x, 2, t)
    assert _dump([x], t) == ["{X =\\= 2}"]


def test_a_disequality_over_an_eliminated_variable_is_not_shown():
    t, x, y = Trail(), Var(), Var()
    assert q_ne(Add(left=x, right=y), 2, t)
    assert q_le(x, 5, t)
    assert _dump([x], t) == ["{X =< 5}"]


# Pruned projection (security review, 2026-10-11): every answer printed by
# `clausal -g` projects the store, and unpruned Fourier-Motzkin grew
# exponentially (22 constraints over 11 variables ran for minutes).

def _random_system(seed, n_vars, n_cons):
    import random
    rng = random.Random(seed)
    t = Trail()
    vs = [Var() for _ in range(n_vars)]
    for _ in range(n_cons):
        picked = rng.sample(vs, 3)
        e = None
        for v in picked:
            term = Mult(left=rng.choice([-3, -2, -1, 1, 2, 3]), right=v)
            e = term if e is None else Add(left=e, right=term)
        assert q_le(e, rng.randint(1, 9), t)
    return t, vs


def _bounds(lines):
    lo = hi = None
    for s in lines:
        body = s[1:-1]
        lhs, rel, rhs = body.rsplit(" ", 2)
        assert lhs in ("X", "-X") or "*X" in lhs, s       # only X survives
        k = Fraction(rhs)
        c = Fraction(1) if lhs == "X" else Fraction(-1) if lhs == "-X" \
            else Fraction(lhs.split("*")[0])
        bound = k / c
        if (rel == "=<") == (c > 0):
            hi = bound if hi is None else min(hi, bound)
        else:
            lo = bound if lo is None else max(lo, bound)
    return lo, hi


@pytest.mark.parametrize("seed", range(40))
def test_a_pruned_projection_gives_the_tight_bounds(seed):
    # Pruning drops only redundant constraints: what is left bounds X
    # exactly as inf/2 and sup/2 do.
    t, vs = _random_system(seed, 7, 22)
    x = vs[0]
    lines = _dump([x], t)
    if any("_Q" in s for s in lines):
        pytest.skip("too large to project: shown unprojected")
    s, i = Var(), Var()
    hi = deref(s) if sup(x, s, t) else None
    lo = deref(i) if inf(x, i, t) else None
    assert _bounds(lines) == (lo, hi)


def test_a_projection_too_large_to_finish_is_shown_unprojected():
    t, vs = _random_system(0, 7, 22)
    lines = _dump([vs[0]], t)
    assert any("_Q" in s for s in lines)
    assert any("X" in s.replace("_Q", "") for s in lines)


def test_constraints_not_linked_to_the_targets_are_left_out():
    t, x, y, z = Trail(), Var(), Var(), Var()
    assert q_le(x, 5, t) and q_le(Add(left=y, right=z), 3, t)
    assert _dump([x], t) == ["{X =< 5}"]


# A basic row is an equation, not just bounds on its expression: a user
# variable can be basic, and with free variables entering the basis it
# often is (second review, 2026-10-11).
def test_a_basic_user_variable_keeps_its_constraints():
    t, x, y = Trail(), Var(), Var()
    assert q_ge(Add(left=x, right=y), 2, t)
    assert _dump([x, y], t, toplevel=True) == ["{X + Y >= 2}"]


def test_a_bound_reaches_the_answer_through_an_eliminated_variable():
    t, x, y = Trail(), Var(), Var()
    assert q_ge(y, 2, t)
    assert q_le(Add(left=Mult(left=3, right=x), right=y), 1, t)
    assert _dump([x], t) == ["{X =< -1/3}"]
