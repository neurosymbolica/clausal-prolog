"""solve/1 of the 0-arity control atoms answers as call/1 does.

todo/done/solve-of-a-true-cell-goal-raises-predicate-not-found-2026-09-06.md:
``solve("true", m)`` raised PredicateNotFoundError (true/0 has no row -- the
compiler lowers it) while ``call(true)`` succeeded once.  ISO 7.8.1/7.8.2:
``true`` succeeds once, ``fail`` (and ``false``) fail.
"""
import pytest

from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.predicate_diagnostics import PredicateNotFoundError


@pytest.fixture
def mod():
    return Module("solve_ctl_atoms")


@pytest.mark.parametrize("goal,n", [("true", 1), ("fail", 0), ("false", 0)])
def test_bare_control_atom(mod, goal, n):
    assert len(list(solve(goal, mod))) == n


@pytest.mark.parametrize("goal,n", [("true", 1), ("fail", 0), ("false", 0)])
def test_qualified_control_atom(mod, goal, n):
    assert len(list(solve((":", mod, goal), mod))) == n


@pytest.mark.parametrize("goal,n", [("true", 1), ("fail", 0)])
def test_same_answer_as_call_1(mod, goal, n):
    assert len(list(solve(("call", goal), mod))) == n


def test_an_unknown_atom_still_raises(mod):
    with pytest.raises(PredicateNotFoundError):
        list(solve("nosuch_zero_arity", mod))
