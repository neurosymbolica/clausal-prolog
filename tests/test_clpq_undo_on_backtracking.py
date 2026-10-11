"""A CLP(Q) constraint posted after a choice point is undone on backtracking.

The store snapshot was skipped when the trail had not grown since the last
one, but a choice point can be taken at exactly that length: the
constraint after it then had nothing to undo it (second review,
2026-10-11).  Each answer below is Scryer's.
"""

import random

import pytest

from clausal.logic.clpq import q_eq, q_le, sup, inf, _tableaux, _last_snapshot
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref, unify
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
v(X) :- {X =< 3}, ( {X >= 1}, fail ; true ), X = 0.
r(Z) :- {2*_X + 2*Z =< 3}, ( {Z >= -2}, fail ; true ), Z = -3.
s(Z) :- {2*_X + 2*Z =< 3}, ( {Z >= -2}, fail ; true ), {Z = -3}.
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("undo") / "undo.clausal"
    p.write_text(_PL)
    return load_clausal_module(p)


@pytest.mark.parametrize("name, value", [("v", 0), ("r", -3), ("s", -3)])
def test_a_failed_branch_leaves_no_constraint(mod, name, value):
    x = Var()
    assert [deref(x) for _ in solve((name, x), mod)] == [value]


def _expr(coeffs, xs):
    e = None
    for c, x in zip(coeffs, xs):
        if c:
            t = Mult(left=c, right=x)
            e = t if e is None else Add(left=e, right=t)
    return e


def _post(t, xs, con):
    kind, a, b = con
    e = _expr(a, xs)
    return True if e is None else (q_eq if kind == "eq" else q_le)(e, b, t)


def _probe(t, xs, objs):
    out = []
    for o in objs:
        for op in (sup, inf):
            r = Var()
            out.append(deref(r) if op(_expr(o, xs), r, t) else None)
    return out


@pytest.mark.parametrize("seed", range(150))
def test_undo_restores_the_store(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 4)

    def con():
        return ("eq" if rng.random() < .2 else "le",
                [rng.randint(-3, 3) for _ in range(n)], rng.randint(-5, 8))

    box = [("le", [int(i == j) for i in range(n)], rng.randint(3, 9))
           for j in range(n)]
    box += [("le", [-int(i == j) for i in range(n)], rng.randint(3, 9))
            for j in range(n)]
    base = [con() for _ in range(rng.randint(1, 4))] + box
    extra = [con() for _ in range(rng.randint(1, 4))]
    objs = [[rng.randint(-3, 3) or 1] + [rng.randint(-3, 3) for _ in range(n - 1)]
            for _ in range(2)]

    t, xs = Trail(), [Var() for _ in range(n)]
    if not all(_post(t, xs, c) for c in base):
        return
    before = [deref(x) for x in xs]
    m = t.mark()
    for c in extra:
        if not _post(t, xs, c):
            break
    t.undo(m)
    assert [deref(x) for x in xs] == before
    got = _probe(t, xs, objs)

    _tableaux.clear()
    t2, xs2 = Trail(), [Var() for _ in range(n)]
    assert all(_post(t2, xs2, c) for c in base)
    assert got == _probe(t2, xs2, objs)


_DIF = """\
:- use_module(library(clpq)).
p(Z) :- {Z >= 0, Z =< 10}, {X =< 3}, dif(X-Z, 3-5), {X >= 3}, Z = 4.
"""


def test_a_trial_unify_inside_a_post_leaves_no_binding(tmp_path):
    # dif/2's hook marks the trail, tries a unification (which wakes the
    # CLP(Q) hook) and undoes it, all inside one CLP(Q) post: one snapshot
    # per post left Z fixed at 5 in the store (fourth review, 2026-10-11).
    p = tmp_path / "dif_trial.clausal"
    p.write_text(_DIF)
    z = Var()
    assert [deref(z) for _ in solve(("p", z), load_clausal_module(p))] == [4]


@pytest.mark.parametrize("both_ways", [False, True])
def test_unifying_with_an_unconstrained_variable_keeps_one_column(both_ways):
    # The unconstrained side took a copy of the other's attribute, tab_id
    # and all, but constraints on it were keyed by its own id: a fresh,
    # unlinked column.  So this infeasible store was accepted.
    t, y0, y1 = Trail(), Var(), Var()
    assert q_le(Mult(left=2, right=y1), -1, t)
    assert unify(y1, y0, t)
    if both_ways:
        assert unify(y0, y1, t)
    assert not q_le(Mult(left=-1, right=y0), 0, t)
