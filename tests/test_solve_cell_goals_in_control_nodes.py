"""solve() of a control NODE (And/Or/Not) with CELL goals inside.

todo/done/a-cell-goal-nested-in-a-control-node-is-not-lowered-2026-09-06.md:
``solve(And(("p", X), ("q", X)), m)`` raised ``NotImplementedError:
terms_to_goalop: goal shape not yet supported (tuple)`` -- only a TOP-LEVEL
cell was lowered.  Such a query now runs as call/1 of the body term.
"""
import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from clausal.terms import And, Not, Or


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("scgcn")
    p = d / "scgcn.clausal"
    p.write_text("p(1),\np(2),\nq(2),\nq(3),\n")
    return _load_module("scgcn_mod", str(p))


def _xs(mod, goal, x):
    return [_deref_walk(x) for _ in solve(goal, mod)]


def test_and_of_cells(mod):
    x = Var()
    assert _xs(mod, And(left=("p", x), right=("q", x)), x) == [2]


def test_or_of_cells(mod):
    x = Var()
    assert _xs(mod, Or(left=("p", x), right=("q", x)), x) == [1, 2, 2, 3]


def test_not_of_a_cell(mod):
    assert len(list(solve(Not(operand=("p", 5)), mod))) == 1
    assert list(solve(Not(operand=("p", 1)), mod)) == []


def test_a_control_cell_inside_a_node(mod):
    x = Var()
    g = And(left=("p", x), right=(",", ("q", x), ("p", 2)))
    assert _xs(mod, g, x) == [2]


def test_an_unknown_cell_inside_a_node_is_the_iso_error(mod):
    x = Var()
    with pytest.raises(LogicException) as info:
        list(solve(And(left=("p", x), right=("nosuch", 1)), mod))
    assert info.value.term[1][0] == "existence_error"
