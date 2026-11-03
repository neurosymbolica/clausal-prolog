# tests/clpq_port/test_toplevel_projection.py
"""The `-g` printer's CLP(Q) residuals on the port: the SICStus toplevel's
protocol over 1.3.3's hooks (project.pl project_attributes/2, then itf3.pl
and geler.pl attribute_goal/2), not dump.pl's dump/3.

dump/3 calls ordering(Target) first, which reads the target list as the
chain V1 < V2 < ...; the toplevel imposes no such chain, so an ordering/1
the program states wins whatever order the query names its variables in
(todo/done/clpq-g-printer-should-project-through-itf3-project-attributes-
2026-10-23.md; DEVIATIONS.md D14, D15, D28).

The oracle (Scryer's library(clpq), its dump/3) is asked with the
variables in an order ordering/1 admits; the port's `-g` answers, with the
variables in every order, must have the same solution set (z3).
"""
import itertools

import pytest

from clausal.logic.clpq import holzbaur as h
from clausal.logic.variables import Trail, Var
from clausal.pythonic_ast.nodes import Add, Lt, Mult, Sub
from tests.clpq_oracle import (
    clausal_answers, oracle_answers, same_solution_sets)

_HEAD = ":- use_module(library(clpq)).\n"


def _names(mapping):
    return lambda v: mapping[v._id]


# ---------------------------------------------------------------- the API

def test_an_ordering_against_the_target_order_prints():
    # ordering(Y < X), {X + Y = 10}: Y is defined, in either target order.
    for swap in (False, True):
        t, x, y = Trail(), Var(), Var()
        assert h.ordering(Lt(left=y, right=x), t)
        assert h.q_eq(Add(left=x, right=y), 10, t)
        targets = [y, x] if swap else [x, y]
        name = _names({x._id: "X", y._id: "Y"})
        assert h.residual_q(targets, t, name) == ["{Y = 10 - X}"], swap


def test_the_toplevel_leaves_the_store_as_it_was():
    t, x, y = Trail(), Var(), Var()
    assert h.ordering(Lt(left=y, right=x), t)
    assert h.q_eq(Add(left=x, right=y), 10, t)
    name = _names({x._id: "X", y._id: "Y"})
    first = h.residual_q([x, y], t, name)
    assert h.residual_q([x, y], t, name) == first
    assert h.dump_q([y, x], t, name) == first      # dump/3 with Y < X


def test_a_variable_a_nonlinear_goal_reaches_is_kept():
    # {X*Y = Z, Z + X = 3}, shown X and Y: project.pl marks Z, which the
    # delayed goal reaches, a target (mark_target(NlReachable)), so Z's
    # equation stays.  dump/3 collects the goal first (nonlin_crux), so its
    # reachable set is empty and Z = 3 - X is projected away.
    t, x, y, z = Trail(), Var(), Var(), Var()
    assert h.q_eq(Mult(left=x, right=y), z, t)
    assert h.q_eq(Add(left=z, right=x), 3, t)
    name = _names({x._id: "X", y._id: "Y"})
    shown = h.residual_q([x, y], t, name)
    assert len(shown) == 2, shown
    assert any("_Q1" in s and "X" in s and "Y" not in s for s in shown), shown
    assert any("Y*X" in s and "_Q1" in s for s in shown), shown


def test_nonlinear_goals_without_a_linear_store_are_printed():
    t, x, y = Trail(), Var(), Var()
    assert h.q_eq(Mult(left=x, right=y), 1, t)
    name = _names({x._id: "X", y._id: "Y"})
    assert h.residual_q([x, y], t, name) == ["{-1 + Y*X = 0}"]


# ---------------------------------------------------------------- the -g printer

_PROGRAM = _HEAD + """
q_yx(X, Y) :- ordering(Y < X), {X + Y = 10}.
q_ineq(X, Y) :- {X >= Y, Y > 2}, ordering(X < Y).
q_three(X, Y, Z) :- ordering([Z, Y, X]), {X + 2*Y - Z = 4, X - Y >= 1}.
q_store(A, B, C, D, E) :- {2*A+B+C = 10, C-D = E, A < 10}.
q_mixed(X, Y, Z) :- ordering(Z < X), {X + Y + Z = 1, X - Z =< 5, Y >= 0}.
"""

#: (goal, the shown variables in an order ordering/1 admits).
_QUERIES = [
    ("q_yx(X, Y)", ["Y", "X"]),
    ("q_ineq(X, Y)", ["X", "Y"]),
    ("q_three(X, Y, Z)", ["Z", "Y", "X"]),
    ("q_store(A, B, C, D, E)", ["A", "B", "C", "D", "E"]),
    ("q_mixed(X, Y, Z)", ["Z", "X", "Y"]),
]


@pytest.mark.parametrize("goal, admitted", _QUERIES,
                         ids=[g.split("(")[0] for g, _ in _QUERIES])
def test_every_variable_order_prints_the_oracle_s_solution_set(goal, admitted):
    # The oracle's dump/3 takes the shown variables in an order ordering/1
    # admits.  The `-g` printer shows the variables in the order the goal
    # first names them, so `_ = f(...)` names them in each order first.
    want = oracle_answers(_PROGRAM, goal, admitted)
    failures = []
    for order in itertools.permutations(admitted):
        order = list(order)
        named = "_ = f(" + ", ".join(order) + ")"
        got = clausal_answers(_PROGRAM, f"{named}, {goal}", order, "holzbaur")
        ok, why = same_solution_sets(got, want)
        if not ok:
            failures.append(f"{order}: {why}")
    assert not failures, "\n".join(failures)


def test_the_g_printer_on_an_ordering_against_the_query_order():
    [answer] = clausal_answers(_PROGRAM, "q_yx(X, Y)", ["X", "Y"], "holzbaur")
    assert answer.bindings == {}
    assert answer.residual == ["Y = 10 - X"], answer


def test_a_failing_projection_raises_a_system_error(monkeypatch):
    from clausal.logic.clpq import residual_constraints
    from clausal.logic.exceptions import LogicException
    t, x, y = Trail(), Var(), Var()
    assert h.q_eq(Add(left=x, right=y), 10, t)
    monkeypatch.setattr(residual_constraints, "project_attributes",
                        lambda *arguments: False)
    with pytest.raises(LogicException) as raised:
        h.residual_q([x, y], t, str)
    assert "clpq_projection_failed" in str(raised.value.term)


def test_dump_still_imposes_the_target_order():
    # dump/3 keeps ordering(Target): the chain X < Y against Y < X.
    from clausal.logic.exceptions import LogicException
    t, x, y = Trail(), Var(), Var()
    assert h.ordering(Lt(left=y, right=x), t)
    assert h.q_eq(Add(left=x, right=y), 10, t)
    with pytest.raises(LogicException) as raised:
        h.dump_q([x, y], t, str)
    assert "unsatisfiable_ordering" in str(raised.value.term)


def test_the_manual_s_store_prints_as_its_top_level_answer():
    # {2*A+B+C = 10, C-D = E, A < 10}: the manual's top-level answer is
    # C=10-2*A-B, E=10-2*A-B-D, A<10 (dump/3 over [A,B,C,D,E] defines A).
    t = Trail()
    a, b, c, d, e = (Var() for _ in range(5))
    assert h.q_eq(Add(left=Add(left=Mult(left=2, right=a), right=b), right=c),
                  10, t)
    assert h.q_eq(Sub(left=c, right=d), e, t)
    assert h.q_lt(a, 10, t)
    name = _names({a._id: "A", b._id: "B", c._id: "C", d._id: "D", e._id: "E"})
    assert sorted(h.residual_q([a, b, c, d, e], t, name)) == sorted(
        ["{C = 10 - 2*A - B}", "{E = 10 - 2*A - B - D}", "{A < 10}"])


_GLOBAL = _HEAD + """
q_sin(X) :- {X >= 10}, {sin(_Z) > 3}.
q_bound(X) :- {X >= 10}, {_Z >= 3}.
"""


def test_a_nonlinear_goal_no_query_variable_reaches_shows():
    # The manual (dump/3): "From the top level's report we have a chance to
    # deduce this fact": q(X) answers {X>=10.0} and clpr:{3.0-sin(_B)<0.0}.
    # The `-g` printer passes the query's other attributed variables as
    # AttrVars, so project_nonlinear/3 collects the goal on _Z.
    [answer] = clausal_answers(_GLOBAL, "q_sin(X)", ["X"], "holzbaur")
    assert answer.bindings == {}
    assert answer.residual == ["X >= 10", "3 - sin(_Q1) < 0"], answer


def test_a_linear_constraint_no_query_variable_reaches_is_projected_away():
    [answer] = clausal_answers(_GLOBAL, "q_bound(X)", ["X"], "holzbaur")
    assert answer.residual == ["X >= 10"], answer
