"""Infrastructure tests for CLP(Q) and CLP(R) constraint block evaluators.

Problem-solving tests are in tests/fixtures/clpq_module.clausal and
tests/fixtures/clpr_module.clausal. These Python tests cover error paths
and internal mechanics.
"""

from __future__ import annotations
import pytest
from fractions import Fraction

from clausal.logic.variables import Var, Trail, deref
from clausal.pythonic_ast.nodes import ArithEq, LtE, CompareChain


class TestClpqErrorPaths:
    def test_unsupported_node_raises(self):
        # nv
        from clausal.logic.clpq import clpq_constraint_block
        trail = Trail()
        with pytest.raises(TypeError, match="unsupported node"):
            clpq_constraint_block(("not_a_constraint",), trail)

    def test_disequality_conflict(self):
        """ArithNeq + ArithEq on same value fails."""
        # nv
        from clausal.logic.clpq import clpq_constraint_block
        from clausal.pythonic_ast.nodes import ArithNeq
        trail = Trail()
        x = Var()
        assert not clpq_constraint_block((
            ArithNeq(left=x, right=5),
            ArithEq(left=x, right=5),
        ), trail)


class TestClprErrorPaths:
    def test_unsupported_node_raises(self):
        # nv
        from clausal.logic.clpr import clpr_constraint_block
        trail = Trail()
        with pytest.raises(TypeError, match="unsupported node"):
            clpr_constraint_block(("not_a_constraint",), trail)

    def test_infeasible_returns_false(self):
        # nv
        from clausal.logic.clpr import clpr_constraint_block
        from clausal.pythonic_ast.nodes import GtE
        trail = Trail()
        x = Var()
        assert not clpr_constraint_block((
            GtE(left=x, right=10.0),
            LtE(left=x, right=5.0),
        ), trail)


class TestClpqEntailed:
    def test_entailed_by_bounds(self):
        # nv
        from clausal.logic.clpq import clpq_constraint_block, entailed
        trail = Trail()
        x = Var()
        assert clpq_constraint_block((
            CompareChain(comparisons=[LtE(left=5, right=x), LtE(left=x, right=10)]),
        ), trail)
        assert entailed(">=", x, 5, trail)
        assert not entailed("<", x, 5, trail)
