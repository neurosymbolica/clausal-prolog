"""Tests for clausal.logic.clportools_lp — LP/MIP infrastructure unit tests.

Problem-solving tests (feasibility, optimization, diet problem, MIP) live in
tests/fixtures/ortools_lp.seam and tests/fixtures/ortools_mip.seam.

These Python tests cover infrastructure that can't be tested from .clausal:
  - Internal var_map data structures
  - Solver mismatch error handling
  - Backend availability checks
  - Constraint scope retraction via mark/undo
"""

import pytest

from clausal.logic.variables import Var, Trail, deref

from clausal.pythonic_ast.nodes import GtE, LtE

from clausal.logic.clportools_lp import (
    get_lp_state,
    lp_var,
    lp_constraint_block,
    lp_check,
)


class TestLPInfrastructure:

    def test_var_registration(self):
        # nv
        trail = Trail()
        x = Var()
        lp_var(x, 0.0, 100.0, trail, 'glop')
        state = get_lp_state(trail, 'glop')
        assert id(x) in state.var_map

    def test_solver_mismatch(self):
        # nv
        trail = Trail()
        get_lp_state(trail, 'glop')
        with pytest.raises(ValueError, match="mismatch"):
            get_lp_state(trail, 'scip')

    def test_scip_available(self):
        # nv
        trail = Trail()
        state = get_lp_state(trail, 'scip')
        assert state.solver_name == 'scip'

    def test_backtracking_retracts_constraints(self):
        """Constraint scope retraction via trail mark/undo."""
        # nv
        trail = Trail()
        x = Var()
        lp_var(x, 0.0, 100.0, trail, 'glop')
        mark = trail.mark()
        lp_constraint_block((
            GtE(left=x, right=50),
            LtE(left=x, right=30),
        ), 'glop', trail)
        assert not lp_check(trail)
        trail.undo(mark)
        assert lp_check(trail)
