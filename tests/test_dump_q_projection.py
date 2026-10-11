"""dump_q/2 projects the CLP(Q) store onto the variables it is given.

Fixed 2026-10-11: projecting ``X + Y = 3`` onto ``X`` answered ``X = 3``
(the equality that eliminated ``Y`` was kept with ``Y`` struck out), and a
strict bound or a disequality was not shown at all.
"""

from clausal.logic.clpq import dump_q, q_eq, q_lt, q_gt, q_ne, q_le
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
