"""Tests for the clpq.* and clpr.* module API — constraint blocks with ()."""

from __future__ import annotations
import pytest
from fractions import Fraction

from clausal.logic.variables import Var, Trail, deref, is_var
from clausal.pythonic_ast.nodes import (
    ArithEq, ArithNeq, Lt, LtE, Gt, GtE,
    Add, Sub, Mult, CompareChain,
)


# ══════════════════════════════════════════════════════════════════════════════
# CLP(Q) constraint blocks
# ══════════════════════════════════════════════════════════════════════════════

class TestClpqConstraintBlock:
    def test_simple_equality(self):
        from clausal.logic.clpq import clpq_constraint_block
        trail = Trail()
        x = Var()
        assert clpq_constraint_block((
            ArithEq(left=x, right=Fraction(1, 3)),
        ), trail)
        assert deref(x) == Fraction(1, 3)

    def test_chained_comparison(self):
        """1 <= X <= 5 with X == 3."""
        from clausal.logic.clpq import clpq_constraint_block, q_eq
        trail = Trail()
        x = Var()
        assert clpq_constraint_block((
            CompareChain(comparisons=[LtE(left=1, right=x), LtE(left=x, right=5)]),
            ArithEq(left=x, right=3),
        ), trail)
        assert deref(x) == Fraction(3)

    def test_inequality(self):
        from clausal.logic.clpq import clpq_constraint_block
        trail = Trail()
        x = Var()
        assert clpq_constraint_block((
            GtE(left=x, right=0),
            LtE(left=x, right=Fraction(1, 2)),
            ArithEq(left=x, right=Fraction(1, 4)),
        ), trail)
        assert deref(x) == Fraction(1, 4)

    def test_arithmetic_expression(self):
        """2*X + Y == 1, X == 1/4 => Y == 1/2."""
        from clausal.logic.clpq import clpq_constraint_block
        trail = Trail()
        x, y = Var(), Var()
        assert clpq_constraint_block((
            ArithEq(left=Add(left=Mult(left=2, right=x), right=y), right=1),
            ArithEq(left=x, right=Fraction(1, 4)),
        ), trail)
        assert deref(y) == Fraction(1, 2)

    def test_unsatisfiable_returns_false(self):
        from clausal.logic.clpq import clpq_constraint_block
        trail = Trail()
        x = Var()
        result = clpq_constraint_block((
            GtE(left=x, right=10),
            LtE(left=x, right=5),
        ), trail)
        assert not result

    def test_compare_chain_bounds(self):
        """0 <= X <= 1 with maximize."""
        from clausal.logic.clpq import clpq_constraint_block, maximize
        trail = Trail()
        x = Var()
        assert clpq_constraint_block((
            CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=1)]),
        ), trail)
        r = Var()
        assert maximize(x, r, trail)
        assert deref(r) == Fraction(1)

    def test_disequality(self):
        from clausal.logic.clpq import clpq_constraint_block
        trail = Trail()
        x = Var()
        assert clpq_constraint_block((
            ArithNeq(left=x, right=5),
            ArithEq(left=x, right=5),
        ), trail) is False


# ══════════════════════════════════════════════════════════════════════════════
# CLP(R) constraint blocks
# ══════════════════════════════════════════════════════════════════════════════

class TestClprConstraintBlock:
    def test_simple_equality(self):
        from clausal.logic.clpr import clpr_constraint_block
        trail = Trail()
        x = Var()
        assert clpr_constraint_block((
            ArithEq(left=x, right=3),
        ), trail)

    def test_chained_comparison(self):
        from clausal.logic.clpr import clpr_constraint_block
        trail = Trail()
        x = Var()
        assert clpr_constraint_block((
            CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=10)]),
        ), trail)

    def test_inequality(self):
        from clausal.logic.clpr import clpr_constraint_block
        trail = Trail()
        x = Var()
        assert clpr_constraint_block((
            GtE(left=x, right=0),
            LtE(left=x, right=1),
        ), trail)

    def test_unsatisfiable_returns_false(self):
        from clausal.logic.clpr import clpr_constraint_block
        trail = Trail()
        x = Var()
        result = clpr_constraint_block((
            GtE(left=x, right=10),
            LtE(left=x, right=5),
        ), trail)
        assert not result

    def test_arithmetic_expression(self):
        from clausal.logic.clpr import clpr_constraint_block
        trail = Trail()
        x = Var()
        assert clpr_constraint_block((
            CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=10)]),
            ArithEq(left=Mult(left=x, right=2), right=6),
        ), trail)

    def test_label(self):
        from clausal.logic.clpr import clpr_constraint_block, label_real
        trail = Trail()
        x = Var()
        # Use equality so labeling converges immediately
        assert clpr_constraint_block((
            ArithEq(left=x, right=3.0),
        ), trail)
        count = sum(1 for _ in label_real([x], trail))
        assert count >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Unsupported node type
# ══════════════════════════════════════════════════════════════════════════════

class TestClpqEntailed:
    def test_entailed_by_bounds(self):
        """clpq.entailed succeeds when constraint is implied."""
        from clausal.logic.clpq import clpq_constraint_block, entailed
        trail = Trail()
        x = Var()
        assert clpq_constraint_block((
            CompareChain(comparisons=[LtE(left=5, right=x), LtE(left=x, right=10)]),
        ), trail)
        # x >= 5 is entailed
        assert entailed(">=", x, 5, trail)
        # x < 5 is NOT entailed
        assert not entailed("<", x, 5, trail)


class TestUnsupportedNodes:
    def test_clpq_unsupported_raises(self):
        from clausal.logic.clpq import clpq_constraint_block
        trail = Trail()
        with pytest.raises(TypeError, match="unsupported node"):
            clpq_constraint_block(("not_a_constraint",), trail)

    def test_clpr_unsupported_raises(self):
        from clausal.logic.clpr import clpr_constraint_block
        trail = Trail()
        with pytest.raises(TypeError, match="unsupported node"):
            clpr_constraint_block(("not_a_constraint",), trail)
