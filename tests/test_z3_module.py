"""Infrastructure tests for the z3.* module API.

Problem-solving tests are in tests/fixtures/z3_*.seam.
These Python tests cover internal mechanics not reachable from .clausal:
variable registration, sort checking, error paths, backtracking internals.
"""

from __future__ import annotations
import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var
from clausal.logic.clpz3 import (
    z3_constraint_block, label_z3_polymorphic,
    get_z3_state, z3_check,
    clausal_to_z3,
)
from clausal.pythonic_ast.nodes import (
    ArithEq, LtE, CompareChain,
)


class TestCompareChainEdge:
    def test_single_comparison_chain(self):
        """Single-element CompareChain still produces a valid z3 expr."""
        # nv
        trail = Trail()
        x = Var()
        chain = CompareChain(comparisons=[LtE(left=x, right=5)])
        z3_expr = clausal_to_z3(chain, trail, default_sort=z3.IntSort())
        assert z3_expr is not None


class TestAutoRegistration:
    def test_integer_sort_registered(self):
        """Vars in constraint block are auto-registered with IntSort."""
        # nv
        trail = Trail()
        x = Var()
        z3_constraint_block((
            LtE(left=x, right=10),
        ), z3.IntSort(), trail)
        state = get_z3_state(trail)
        assert id(x) in state.var_map
        assert state.var_map[id(x)].sort() == z3.IntSort()

    def test_real_sort_registered(self):
        """Vars in constraint block are auto-registered with RealSort."""
        # nv
        trail = Trail()
        x = Var()
        z3_constraint_block((
            LtE(left=x, right=10),
        ), z3.RealSort(), trail)
        state = get_z3_state(trail)
        assert state.var_map[id(x)].sort() == z3.RealSort()


class TestLabelEdgeCases:
    def test_ground_vars_ignored(self):
        """Ground values in the label list are skipped."""
        # nv
        trail = Trail()
        x = Var()
        z3_constraint_block(
            (ArithEq(left=x, right=5),),
            z3.IntSort(), trail
        )
        sols = []
        for _ in label_z3_polymorphic([x, 42], trail):
            sols.append(deref(x))
        assert sols == [5]

    def test_unregistered_raises(self):
        # nv
        trail = Trail()
        x = Var()
        with pytest.raises(ValueError, match="not registered"):
            list(label_z3_polymorphic([x], trail))

    def test_bindings_undone_after_label(self):
        # nv
        trail = Trail()
        x = Var()
        z3_constraint_block(
            (CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=2)]),),
            z3.IntSort(), trail
        )
        for _ in label_z3_polymorphic([x], trail):
            pass
        assert is_var(deref(x))


class TestBacktracking:
    def test_constraint_block_retracted_on_undo(self):
        """Constraint block constraints are retracted on trail undo."""
        # nv
        trail = Trail()
        x = Var()
        z3_constraint_block(
            (CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=10)]),),
            z3.IntSort(), trail
        )
        mark = trail.mark()
        z3_constraint_block((ArithEq(left=x, right=5),), z3.IntSort(), trail)
        sols = []
        for _ in label_z3_polymorphic([x], trail):
            sols.append(deref(x))
        assert sols == [5]

        trail.undo(mark)
        count = sum(1 for _ in label_z3_polymorphic([x], trail))
        assert count == 11
