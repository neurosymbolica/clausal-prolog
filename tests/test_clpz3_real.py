"""Tests for Z3 real/rational constraints — Phase 4.

Covers: in_z3_real, z3_real_eq/ne/lt/le/gt/ge, label_z3_real,
        maximize_z3, minimize_z3, entailed_z3, sup_z3, inf_z3.

All tests are skipped if z3-solver is not installed.
"""

from __future__ import annotations

import pytest
from fractions import Fraction

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.clpz3 import (
    in_z3_real, z3_real_eq, z3_real_ne, z3_real_lt, z3_real_le,
    z3_real_gt, z3_real_ge, label_z3_real,
    maximize_z3, minimize_z3, entailed_z3, sup_z3, inf_z3,
    get_z3_state, z3_check,
)
from clausal.pythonic_ast.nodes import Add, Sub, Mult, LtE, Lt, GtE, Gt, ArithEq


# ══════════════════════════════════════════════════════════════════════════════
# in_z3_real — variable declaration and bounds
# ══════════════════════════════════════════════════════════════════════════════

class TestInZ3Real:
    def test_unbounded_var(self):
        # nv
        trail = Trail()
        x = Var()
        assert in_z3_real(x, None, None, trail)
        state = get_z3_state(trail)
        assert state.var_map[id(x)].sort() == z3.RealSort()

    def test_bounded_var(self):
        # nv
        trail = Trail()
        x = Var()
        assert in_z3_real(x, 0, 10, trail)
        assert z3_check(trail)

    def test_fraction_bounds(self):
        # nv
        trail = Trail()
        x = Var()
        assert in_z3_real(x, Fraction(1, 3), Fraction(2, 3), trail)
        assert z3_check(trail)

    def test_float_bounds(self):
        # nv
        trail = Trail()
        x = Var()
        assert in_z3_real(x, 0.0, 1.5, trail)
        assert z3_check(trail)

    def test_negative_bounds(self):
        # nv
        trail = Trail()
        x = Var()
        assert in_z3_real(x, -100, 100, trail)
        assert z3_check(trail)

    def test_tight_bounds_feasible(self):
        """lo == hi — one feasible point."""
        # nv
        trail = Trail()
        x = Var()
        assert in_z3_real(x, 5, 5, trail)
        assert z3_check(trail)
        r = Var()
        assert maximize_z3(x, r, trail)
        assert deref(r) == Fraction(5)

    def test_tight_bounds_infeasible(self):
        """lo > hi — infeasible."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 10, 5, trail)
        assert not z3_check(trail)

    def test_ground_in_range(self):
        # nv
        trail = Trail()
        assert in_z3_real(5, 0, 10, trail)
        assert in_z3_real(5.0, 0, 10, trail)
        assert in_z3_real(Fraction(1, 2), 0, 1, trail)

    def test_ground_out_of_range(self):
        # nv
        trail = Trail()
        assert not in_z3_real(15, 0, 10, trail)
        assert not in_z3_real(-1, 0, 10, trail)

    def test_list_of_vars(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        assert in_z3_real([x, y], 0, 10, trail)
        state = get_z3_state(trail)
        assert state.var_map[id(x)].sort() == z3.RealSort()
        assert state.var_map[id(y)].sort() == z3.RealSort()

    def test_backtracking_retracts_bounds(self):
        """Bounds posted via in_z3_real are undone on trail.undo."""
        # nv
        trail = Trail()
        x = Var()
        mark = trail.mark()
        in_z3_real(x, 0, 5, trail)
        # With bounds, x > 10 is unsat
        state = get_z3_state(trail)
        z3_x = state.var_map[id(x)]
        state.solver.push()
        state.solver.add(z3_x > z3.RealVal(10))
        assert state.solver.check() == z3.unsat
        state.solver.pop()
        # Undo bounds
        trail.undo(mark)
        # Now x > 10 should be sat (no bounds remain)
        state.solver.push()
        state.solver.add(z3_x > z3.RealVal(10))
        assert state.solver.check() == z3.sat
        state.solver.pop()


# ══════════════════════════════════════════════════════════════════════════════
# Arithmetic constraints
# ══════════════════════════════════════════════════════════════════════════════

class TestRealArithConstraints:
    def test_eq(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        z3_real_eq(x, 3, trail)
        solutions = []
        for _ in label_z3_real([x], trail):
            solutions.append(deref(x))
        assert len(solutions) == 1
        assert solutions[0] == Fraction(3)

    def test_ne(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        z3_real_ne(x, 5, trail)
        # Should be satisfiable — many reals != 5 in [0,10]
        assert z3_check(trail)

    def test_lt(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        z3_real_lt(x, 3, trail)
        solutions = []
        for _ in label_z3_real([x], trail):
            solutions.append(deref(x))
        assert len(solutions) == 1
        assert solutions[0] < 3

    def test_le(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        z3_real_le(x, 5, trail)
        solutions = []
        for _ in label_z3_real([x], trail):
            solutions.append(deref(x))
        assert len(solutions) == 1
        assert solutions[0] <= 5

    def test_gt(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        z3_real_gt(x, 7, trail)
        solutions = []
        for _ in label_z3_real([x], trail):
            solutions.append(deref(x))
        assert len(solutions) == 1
        assert solutions[0] > 7

    def test_ge(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        z3_real_ge(x, 8, trail)
        solutions = []
        for _ in label_z3_real([x], trail):
            solutions.append(deref(x))
        assert len(solutions) == 1
        assert solutions[0] >= 8

    def test_two_var_eq(self):
        """x + y == 10, x == 3 → y == 7."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_real([x, y], 0, 10, trail)
        z3_real_eq(Add(left=x, right=y), 10, trail)
        z3_real_eq(x, 3, trail)
        solutions = []
        for _ in label_z3_real([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert len(solutions) == 1
        assert solutions[0] == (Fraction(3), Fraction(7))

    def test_unsatisfiable(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 5, trail)
        z3_real_eq(x, 10, trail)
        assert not z3_check(trail)

    def test_backtracking_retracts_constraint(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        mark = trail.mark()
        z3_real_eq(x, 3, trail)
        solutions = []
        for _ in label_z3_real([x], trail):
            solutions.append(deref(x))
        assert len(solutions) == 1
        assert solutions[0] == Fraction(3)
        trail.undo(mark)
        # Constraint retracted — x can be anything in [0,10]
        r = Var()
        assert maximize_z3(x, r, trail)
        assert deref(r) == Fraction(10)


# ══════════════════════════════════════════════════════════════════════════════
# label_z3_real
# ══════════════════════════════════════════════════════════════════════════════

class TestLabelZ3Real:
    def test_single_var_yields_one(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        solutions = []
        for _ in label_z3_real([x], trail):
            solutions.append(deref(x))
        assert len(solutions) == 1
        val = solutions[0]
        assert isinstance(val, (int, float, Fraction))
        assert 0 <= float(val) <= 10

    def test_infeasible_yields_none(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 5, trail)
        z3_real_eq(x, 10, trail)
        assert len(list(label_z3_real([x], trail))) == 0

    def test_all_ground_yields_one(self):
        # nv
        trail = Trail()
        assert len(list(label_z3_real([1, 2, Fraction(1, 2)], trail))) == 1

    def test_vars_unbound_after(self):
        """Bindings from label_z3_real are undone after the generator resumes."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        for _ in label_z3_real([x], trail):
            pass
        assert is_var(deref(x))

    def test_unregistered_var_raises(self):
        # nv
        trail = Trail()
        x = Var()
        with pytest.raises(ValueError, match="not registered"):
            list(label_z3_real([x], trail))


# ══════════════════════════════════════════════════════════════════════════════
# maximize_z3 / minimize_z3
# ══════════════════════════════════════════════════════════════════════════════

class TestOptimize:
    def test_maximize_bounded(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        r = Var()
        assert maximize_z3(x, r, trail)
        assert deref(r) == Fraction(10)

    def test_minimize_bounded(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        r = Var()
        assert minimize_z3(x, r, trail)
        assert deref(r) == Fraction(0)

    def test_maximize_lp(self):
        """Classic LP: maximize 30x + 50y subject to linear constraints."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_real([x, y], 0, 1000, trail)
        # 2x + y <= 16
        z3_real_le(Add(left=Mult(left=2, right=x), right=y), 16, trail)
        # x + 2y <= 11
        z3_real_le(Add(left=x, right=Mult(left=2, right=y)), 11, trail)
        # x + 3y <= 15
        z3_real_le(Add(left=x, right=Mult(left=3, right=y)), 15, trail)

        obj = Var()
        assert maximize_z3(Add(left=Mult(left=30, right=x), right=Mult(left=50, right=y)), obj, trail)
        result = deref(obj)
        # Optimal: x=7, y=2, obj=310
        assert result == Fraction(310) or result == 310

    def test_minimize_lp(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_real([x, y], 0, 100, trail)
        z3_real_ge(Add(left=x, right=y), 10, trail)
        obj = Var()
        assert minimize_z3(Add(left=x, right=y), obj, trail)
        assert deref(obj) == Fraction(10)

    def test_infeasible_maximize_fails(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 5, trail)
        z3_real_eq(x, 10, trail)  # contradicts bounds
        obj = Var()
        assert not maximize_z3(x, obj, trail)

    def test_infeasible_minimize_fails(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 5, trail)
        z3_real_eq(x, 10, trail)
        obj = Var()
        assert not minimize_z3(x, obj, trail)

    def test_maximize_does_not_commit(self):
        """maximize_z3 does not modify the main solver state."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        state = get_z3_state(trail)
        before = state.solver.num_scopes()
        r = Var()
        maximize_z3(x, r, trail)
        assert state.solver.num_scopes() == before

    def test_result_unifies(self):
        """If result_var is already bound to the optimal value, succeeds."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 5, 5, trail)
        r = Var()
        unify(r, Fraction(5), trail)
        assert maximize_z3(x, r, trail)

    def test_result_wrong_value_fails(self):
        """If result_var is bound to a wrong value, unify fails."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        r = Var()
        unify(r, Fraction(5), trail)
        assert not maximize_z3(x, r, trail)


# ══════════════════════════════════════════════════════════════════════════════
# entailed_z3
# ══════════════════════════════════════════════════════════════════════════════

class TestEntailed:
    def test_entailed_upper_bound(self):
        """x in [0,5] → x <= 10 is entailed."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 5, trail)
        assert entailed_z3(LtE(left=x, right=10), trail)

    def test_entailed_exact(self):
        """x == 3 → x <= 5 is entailed."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 3, 3, trail)
        assert entailed_z3(LtE(left=x, right=5), trail)

    def test_not_entailed_indeterminate(self):
        """x in [0,10] → x < 5 is not entailed (x could be 8)."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        assert not entailed_z3(Lt(left=x, right=5), trail)

    def test_entailed_equality(self):
        """x == 3, y == 3 → x == y is entailed."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        z3_real_eq(x, 3, trail)
        z3_real_eq(y, 3, trail)
        assert entailed_z3(ArithEq(left=x, right=y), trail)

    def test_not_entailed_unconstrained(self):
        """No constraints → x < 5 is not entailed."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, None, None, trail)
        assert not entailed_z3(Lt(left=x, right=5), trail)

    def test_entailed_does_not_modify_solver(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 5, trail)
        state = get_z3_state(trail)
        before = state.solver.num_scopes()
        entailed_z3(LtE(left=x, right=10), trail)
        assert state.solver.num_scopes() == before


# ══════════════════════════════════════════════════════════════════════════════
# sup_z3 / inf_z3 (aliases)
# ══════════════════════════════════════════════════════════════════════════════

class TestSupInf:
    def test_sup(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        r = Var()
        assert sup_z3(x, r, trail)
        assert deref(r) == Fraction(10)

    def test_inf(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        r = Var()
        assert inf_z3(x, r, trail)
        assert deref(r) == Fraction(0)

    def test_sup_with_constraints(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        z3_real_le(x, 7, trail)
        r = Var()
        assert sup_z3(x, r, trail)
        assert deref(r) == Fraction(7)


# ══════════════════════════════════════════════════════════════════════════════
# Nonlinear arithmetic
# ══════════════════════════════════════════════════════════════════════════════

class TestNonlinear:
    def test_quadratic_eq(self):
        """x² == 4 in [0,10] → x == 2."""
        # nv
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        z3_real_eq(Mult(left=x, right=x), 4, trail)
        solutions = []
        for _ in label_z3_real([x], trail):
            solutions.append(deref(x))
        assert len(solutions) == 1
        xf = float(solutions[0]) if isinstance(solutions[0], Fraction) else solutions[0]
        assert abs(xf - 2.0) < 1e-6

    def test_circle_constraint(self):
        """x² + y² <= 25 in [-10,10]² — finds a point inside the circle."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3_real([x, y], -10, 10, trail)
        z3_real_le(Add(left=Mult(left=x, right=x), right=Mult(left=y, right=y)), 25, trail)
        solutions = []
        for _ in label_z3_real([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert len(solutions) == 1
        xv, yv = solutions[0]
        xf = float(xv) if isinstance(xv, Fraction) else xv
        yf = float(yv) if isinstance(yv, Fraction) else yv
        assert xf**2 + yf**2 <= 25.001


# ══════════════════════════════════════════════════════════════════════════════
# Cross-validation: compare Z3 results with CLP(Q)
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossValidation:
    def test_lp_matches_clpq(self):
        """LP: maximize 30x + 50y subject to 2x+y<=16, x+2y<=11, x+3y<=15.
        Both CLP(Q) and Z3 should give obj = 310.
        """
        # nv
        from clausal.logic.clpq import in_q, q_le, maximize as clpq_maximize

        # CLP(Q) version
        trail_q = Trail()
        xq, yq = Var(), Var()
        in_q([xq, yq], 0, 1000, trail_q)
        q_le(Add(left=Mult(left=2, right=xq), right=yq), 16, trail_q)
        q_le(Add(left=xq, right=Mult(left=2, right=yq)), 11, trail_q)
        obj_q = Var()
        clpq_maximize(Add(left=Mult(left=30, right=xq), right=Mult(left=50, right=yq)), obj_q, trail_q)
        clpq_result = float(deref(obj_q))

        # Z3 version
        trail_z = Trail()
        xz, yz = Var(), Var()
        in_z3_real([xz, yz], 0, 1000, trail_z)
        z3_real_le(Add(left=Mult(left=2, right=xz), right=yz), 16, trail_z)
        z3_real_le(Add(left=xz, right=Mult(left=2, right=yz)), 11, trail_z)
        obj_z = Var()
        assert maximize_z3(Add(left=Mult(left=30, right=xz), right=Mult(left=50, right=yz)), obj_z, trail_z)
        z3_result = float(deref(obj_z))

        assert clpq_result == pytest.approx(z3_result)

    def test_minimize_matches_clpq(self):
        """Minimize x subject to x >= 3 in [0,100]: both give 3."""
        # nv
        from clausal.logic.clpq import in_q, q_le, minimize as clpq_minimize

        trail_q = Trail()
        xq = Var()
        in_q(xq, 0, 100, trail_q)
        q_le(3, xq, trail_q)  # x >= 3 as 3 <= x
        obj_q = Var()
        clpq_minimize(xq, obj_q, trail_q)
        clpq_result = float(deref(obj_q))

        trail_z = Trail()
        xz = Var()
        in_z3_real(xz, 0, 100, trail_z)
        z3_real_ge(xz, 3, trail_z)
        obj_z = Var()
        assert minimize_z3(xz, obj_z, trail_z)
        z3_result = float(deref(obj_z))

        assert clpq_result == pytest.approx(z3_result)
