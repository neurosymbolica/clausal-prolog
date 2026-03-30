"""Tests for CLP(Q) — constraint logic programming over rationals."""

from fractions import Fraction as F

import pytest

from clausal.logic.variables import Var, Trail, deref, is_var, get_attr, unify
from clausal.logic.clpq import (
    Q_KEY, in_q, q_eq, q_ne, q_lt, q_le, q_gt, q_ge,
    maximize, minimize, _linearize, _get_tableau,
)
from clausal.terms import Add, Sub, Mult, Div, Negate


# ── Helpers ──────────────────────────────────────────────────────────────────

def fresh():
    return Trail(), Var()

def state(v):
    return get_attr(deref(v), Q_KEY)


# ── Phase 1: Dispatch ────────────────────────────────────────────────────────


class TestDispatch:
    def test_fraction_dispatches_to_q_eq(self):
        """fd_eq with Fraction argument dispatches to q_eq."""
        from clausal.logic.clpfd import fd_eq
        trail, x = fresh()
        assert fd_eq(x, F(1, 3), trail)
        assert deref(x) == F(1, 3)

    def test_fraction_dispatches_to_q_le(self):
        from clausal.logic.clpfd import fd_le
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert fd_le(x, F(5), trail)

    def test_int_does_not_dispatch_to_q(self):
        from clausal.logic.clpfd import fd_eq
        trail, x = fresh()
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5
        assert state(x) is None  # no Q attribute

    def test_float_does_not_dispatch_to_q(self):
        from clausal.logic.clpfd import fd_eq
        trail, x = fresh()
        assert fd_eq(x, 3.14, trail)


# ── Phase 2: Basic domain + bounds ───────────────────────────────────────────


class TestInQ:
    def test_basic(self):
        trail, x = fresh()
        assert in_q(x, 0, 10, trail)
        s = state(x)
        assert s is not None
        assert s.lo == F(0)
        assert s.hi == F(10)

    def test_narrows(self):
        trail, x = fresh()
        in_q(x, 0, 10, trail)
        in_q(x, 2, 8, trail)
        s = state(x)
        assert s.lo == F(2)
        assert s.hi == F(8)

    def test_infeasible(self):
        trail, x = fresh()
        in_q(x, 5, 10, trail)
        assert not in_q(x, 0, 3, trail)

    def test_point_binds(self):
        trail, x = fresh()
        in_q(x, 5, 5, trail)
        assert deref(x) == F(5)

    def test_list(self):
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        assert in_q([x, y, z], 0, 10, trail)
        for v in [x, y, z]:
            assert state(v) is not None

    def test_ground_check(self):
        trail = Trail()
        assert in_q(F(5), 0, 10, trail)
        assert not in_q(F(15), 0, 10, trail)

    def test_unbounded(self):
        trail, x = fresh()
        assert in_q(x, trail=trail)
        s = state(x)
        assert s.lo is None
        assert s.hi is None


# ── Phase 3: Ground rational constraints ─────────────────────────────────────


class TestGroundConstraints:
    def test_eq_ground_rationals(self):
        trail = Trail()
        assert q_eq(F(1, 3), F(1, 3), trail)

    def test_eq_ground_rationals_fail(self):
        trail = Trail()
        assert not q_eq(F(1, 3), F(1, 2), trail)

    def test_ne_ground(self):
        trail = Trail()
        assert q_ne(F(1, 3), F(1, 2), trail)
        assert not q_ne(F(1, 3), F(1, 3), trail)

    def test_lt_ground(self):
        trail = Trail()
        assert q_lt(F(1, 3), F(1, 2), trail)
        assert not q_lt(F(1, 2), F(1, 3), trail)
        assert not q_lt(F(1, 3), F(1, 3), trail)

    def test_le_ground(self):
        trail = Trail()
        assert q_le(F(1, 3), F(1, 3), trail)
        assert q_le(F(1, 3), F(1, 2), trail)
        assert not q_le(F(1, 2), F(1, 3), trail)

    def test_gt_ground(self):
        trail = Trail()
        assert q_gt(F(1, 2), F(1, 3), trail)
        assert not q_gt(F(1, 3), F(1, 2), trail)

    def test_ge_ground(self):
        trail = Trail()
        assert q_ge(F(1, 3), F(1, 3), trail)
        assert q_ge(F(1, 2), F(1, 3), trail)


# ── Phase 3: Variable binding ────────────────────────────────────────────────


class TestVarBinding:
    def test_eq_var_to_rational(self):
        trail, x = fresh()
        assert q_eq(x, F(1, 3), trail)
        assert deref(x) == F(1, 3)

    def test_eq_var_to_int(self):
        trail, x = fresh()
        assert q_eq(x, F(5), trail)
        assert deref(x) == F(5)


# ── Phase 3: Linear equalities (Gaussian elimination) ───────────────────────


class TestLinearEqualities:
    def test_two_var_eq(self):
        """X + Y = 10, X = 3 → Y = 7."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        assert q_eq(Add(left=x, right=y), F(10), trail)
        assert q_eq(x, F(3), trail)
        assert deref(y) == F(7)

    def test_three_var_system(self):
        """X + Y + Z = 6, X - Y = 2, Y - Z = 1
        → Y = 5/3, X = 11/3, Z = 2/3"""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        in_q([x, y, z], -100, 100, trail)
        assert q_eq(Add(left=Add(left=x, right=y), right=z), F(6), trail)
        assert q_eq(Sub(left=x, right=y), F(2), trail)
        assert q_eq(Sub(left=y, right=z), F(1), trail)
        assert deref(x) == F(11, 3)
        assert deref(y) == F(5, 3)
        assert deref(z) == F(2, 3)

    def test_contradictory(self):
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert q_eq(x, F(3), trail)
        assert not q_eq(x, F(5), trail)

    def test_redundant(self):
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        assert q_eq(Add(left=x, right=y), F(10), trail)
        assert q_eq(Add(left=x, right=y), F(10), trail)  # redundant — should still pass

    def test_rational_coefficients(self):
        """(1/2)*X + (1/3)*Y = 1, Y = 0 → X = 2."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], -10, 10, trail)
        half_x = Mult(left=F(1, 2), right=x)
        third_y = Mult(left=F(1, 3), right=y)
        assert q_eq(Add(left=half_x, right=third_y), F(1), trail)
        assert q_eq(y, F(0), trail)
        assert deref(x) == F(2)

    def test_single_var_scaled(self):
        """2*X = 1 → X = 1/2."""
        trail = Trail()
        x = Var()
        in_q(x, -10, 10, trail)
        assert q_eq(Mult(left=F(2), right=x), F(1), trail)
        assert deref(x) == F(1, 2)

    def test_large_coefficients(self):
        """999999*X = 1 → X = 1/999999."""
        trail = Trail()
        x = Var()
        in_q(x, -10, 10, trail)
        assert q_eq(Mult(left=F(999999), right=x), F(1), trail)
        assert deref(x) == F(1, 999999)


# ── Phase 4: Linear inequalities (simplex) ──────────────────────────────────


class TestLinearInequalities:
    def test_simple_le(self):
        trail, x = fresh()
        in_q(x, 0, 10, trail)
        assert q_le(x, F(5), trail)

    def test_le_infeasible(self):
        trail, x = fresh()
        in_q(x, 0, 10, trail)
        assert q_ge(x, F(6), trail)
        assert not q_le(x, F(4), trail)

    def test_two_var_system(self):
        """X + Y <= 8, X <= 5, Y <= 6, X >= 0, Y >= 0 — should be feasible."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 100, trail)
        assert q_le(Add(left=x, right=y), F(8), trail)
        assert q_le(x, F(5), trail)
        assert q_le(y, F(6), trail)

    def test_redundant_constraint(self):
        """X <= 5, X <= 10 — second is redundant."""
        trail, x = fresh()
        in_q(x, 0, 100, trail)
        assert q_le(x, F(5), trail)
        assert q_le(x, F(10), trail)

    def test_zero_coefficients(self):
        """0*X + Y = 1 should simplify to Y = 1."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], -10, 10, trail)
        assert q_eq(Add(left=Mult(left=F(0), right=x), right=y), F(1), trail)
        assert deref(y) == F(1)


# ── Phase 5: Backtracking ───────────────────────────────────────────────────


class TestBacktracking:
    def test_undo_restores_unbound(self):
        trail, x = fresh()
        mark = trail.mark()
        assert q_eq(x, F(1, 3), trail)
        assert deref(x) == F(1, 3)
        trail.undo(mark)
        assert is_var(deref(x))

    def test_undo_restores_bounds(self):
        trail, x = fresh()
        in_q(x, 0, 10, trail)
        mark = trail.mark()
        assert q_le(x, F(5), trail)
        trail.undo(mark)
        s = state(x)
        assert s.hi == F(10)

    def test_undo_restores_tableau(self):
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        mark = trail.mark()
        q_eq(Add(left=x, right=y), F(10), trail)
        q_eq(x, F(3), trail)
        assert deref(y) == F(7)
        trail.undo(mark)
        assert is_var(deref(y))


# ── Phase 6: Optimization ───────────────────────────────────────────────────


class TestOptimization:
    def test_maximize_simple(self):
        """maximize X subject to X <= 10, X >= 0 → 10."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_le(x, F(10), trail)
        result = Var()
        assert maximize(x, result, trail)
        assert deref(result) == F(10)

    def test_minimize_simple(self):
        """minimize X subject to X >= 3, X <= 100 → 3."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_ge(x, F(3), trail)
        result = Var()
        assert minimize(x, result, trail)
        assert deref(result) == F(3)

    def test_maximize_lp(self):
        """Classic LP from SICStus docs:
        maximize 30X + 50Y subject to
            2X + Y <= 16, X + 2Y <= 11, X + 3Y <= 15
        → optimal value 310 at X=7, Y=2"""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 1000, trail)
        assert q_le(Add(left=Mult(left=F(2), right=x), right=y), F(16), trail)
        assert q_le(Add(left=x, right=Mult(left=F(2), right=y)), F(11), trail)
        assert q_le(Add(left=x, right=Mult(left=F(3), right=y)), F(15), trail)
        obj = Add(left=Mult(left=F(30), right=x), right=Mult(left=F(50), right=y))
        result = Var()
        assert maximize(obj, result, trail)
        assert deref(result) == F(310)

    def test_minimize_lp(self):
        """Scheduling example from docs:
        minimize 5X + 3Y subject to
            X + Y >= 10, 2X + Y <= 30, X + 3Y <= 40, X,Y >= 0"""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 100, trail)
        assert q_ge(Add(left=x, right=y), F(10), trail)
        assert q_le(Add(left=Mult(left=F(2), right=x), right=y), F(30), trail)
        assert q_le(Add(left=x, right=Mult(left=F(3), right=y)), F(40), trail)
        cost = Var()
        obj = Add(left=Mult(left=F(5), right=x), right=Mult(left=F(3), right=y))
        assert minimize(obj, cost, trail)
        # At optimum: minimize 5X+3Y with X+Y>=10 → cheapest is max Y
        # Y limited by X+3Y<=40 and 2X+Y<=30
        # At X=0: Y>=10, 3Y<=40→Y<=40/3≈13.3, Y<=30. So Y=10, cost=30
        assert deref(cost) == F(30)


# ── Phase 7: Linearization ──────────────────────────────────────────────────


class TestLinearize:
    def test_constant(self):
        trail = Trail()
        assert _linearize(F(5), trail) == ({}, F(5))

    def test_int(self):
        trail = Trail()
        assert _linearize(3, trail) == ({}, F(3))

    def test_var(self):
        trail = Trail()
        x = Var()
        coeffs, const = _linearize(x, trail)
        assert coeffs == {x._id: F(1)}
        assert const == F(0)

    def test_add(self):
        trail = Trail()
        x, y = Var(), Var()
        coeffs, const = _linearize(Add(left=x, right=y), trail)
        assert coeffs == {x._id: F(1), y._id: F(1)}
        assert const == F(0)

    def test_scalar_mult(self):
        trail = Trail()
        x = Var()
        coeffs, const = _linearize(Mult(left=F(3), right=x), trail)
        assert coeffs == {x._id: F(3)}

    def test_nonlinear_rejected(self):
        trail = Trail()
        x, y = Var(), Var()
        assert _linearize(Mult(left=x, right=y), trail) is None

    def test_negate(self):
        trail = Trail()
        x = Var()
        coeffs, const = _linearize(Negate(operand=x), trail)
        assert coeffs == {x._id: F(-1)}


# ── Coefficient growth ───────────────────────────────────────────────────────


class TestCoefficientGrowth:
    def test_newton_sqrt2(self):
        """Newton's method for sqrt(2), 5 iterations → exact large fraction."""
        s = F(1)
        for _ in range(5):
            s = s / 2 + 1 / s
        assert s == F(886731088897, 627013566048)

    def test_large_coefficient_constraint(self):
        trail = Trail()
        x = Var()
        big = F(886731088897, 627013566048)
        in_q(x, 0, big * 2, trail)
        assert q_eq(x, big, trail)
        assert deref(x) == big
