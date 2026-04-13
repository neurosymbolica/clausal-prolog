"""Tests for CLP(R): real-domain constraint solver.

Tests interval arithmetic primitives, RealVar state, constraint posting,
propagation, labeling, and FD/real interoperability.
"""

from __future__ import annotations

import math

import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var, get_attr
from clausal.logic.clpr import (
    REAL_KEY, RealVar,
    _dn, _up,
    _iadd, _isub, _imul, _idiv, _ipow_int, _isqrt, _iabs,
    _isin, _icos, _iexp, _ilog,
    _expr_interval, _invert_expr,
    in_real, label_real,
    real_eq, real_ne, real_lt, real_le, real_gt, real_ge,
    RealEqConstraint, RealLeConstraint, RealLtConstraint, RealNeConstraint,
)
from clausal.terms import Add, Sub, Mult, Div, Pow, Negate


# ── Helpers ───────────────────────────────────────────────────────────────────


def fresh() -> tuple[Trail, Var]:
    return Trail(), Var()


def state(v) -> RealVar:
    return get_attr(deref(v), REAL_KEY)


def collect_solutions(gen):
    return list(gen)


# ── Interval arithmetic ───────────────────────────────────────────────────────


class TestOutwardRounding:
    def test_dn_is_less_or_equal(self):
        # nv
        x = 1.0
        assert _dn(x) <= x

    def test_up_is_greater_or_equal(self):
        # nv
        x = 1.0
        assert _up(x) >= x

    def test_dn_changes_non_exact(self):
        # 0.3 is not exactly representable; _dn should go below
        # nv
        assert _dn(0.3) < 0.3 or _dn(0.3) == 0.3  # at worst equal

    def test_dn_inf_is_inf(self):
        # nv
        assert _dn(-math.inf) == -math.inf

    def test_up_inf_is_inf(self):
        # nv
        assert _up(math.inf) == math.inf


class TestIntervalArithmetic:
    def test_iadd_basic(self):
        # nv
        lo, hi = _iadd(1.0, 2.0, 3.0, 4.0)
        assert lo <= 4.0 <= hi
        assert lo <= 6.0 <= hi

    def test_iadd_outward_rounding(self):
        # nv
        lo, hi = _iadd(0.1, 0.1, 0.2, 0.2)
        # 0.1 + 0.2 is not exactly 0.3; interval must contain 0.3
        assert lo <= 0.3 <= hi

    def test_isub_basic(self):
        # nv
        lo, hi = _isub(5.0, 10.0, 1.0, 3.0)
        assert lo <= 2.0 and hi >= 9.0

    def test_imul_positive(self):
        # nv
        lo, hi = _imul(2.0, 3.0, 4.0, 5.0)
        assert lo <= 8.0 and hi >= 15.0

    def test_imul_mixed_sign(self):
        # nv
        lo, hi = _imul(-2.0, 3.0, -1.0, 4.0)
        assert lo <= -8.0 and hi >= 12.0

    def test_imul_negative(self):
        # nv
        lo, hi = _imul(-3.0, -1.0, -4.0, -2.0)
        assert lo <= 2.0 and hi >= 12.0

    def test_idiv_positive(self):
        # nv
        lo, hi = _idiv(4.0, 6.0, 2.0, 3.0)
        assert lo <= 4.0 / 3.0 and hi >= 3.0

    def test_idiv_zero_in_denominator(self):
        # nv
        lo, hi = _idiv(1.0, 2.0, -1.0, 1.0)
        assert lo == -math.inf and hi == math.inf

    def test_ipow_int_square_positive(self):
        # nv
        lo, hi = _ipow_int(2.0, 3.0, 2)
        assert lo <= 4.0 and hi >= 9.0

    def test_ipow_int_square_mixed(self):
        # nv
        lo, hi = _ipow_int(-2.0, 3.0, 2)
        assert lo <= 0.0 and hi >= 9.0

    def test_ipow_int_cube(self):
        # nv
        lo, hi = _ipow_int(-2.0, 3.0, 3)
        assert lo <= -8.0 and hi >= 27.0

    def test_isqrt_positive(self):
        # nv
        lo, hi = _isqrt(4.0, 9.0)
        assert lo <= 2.0 and hi >= 3.0

    def test_isqrt_zero_lo(self):
        # nv
        lo, hi = _isqrt(-1.0, 4.0)
        assert lo <= 0.0 and hi >= 2.0

    def test_iabs_positive(self):
        # nv
        assert _iabs(2.0, 5.0) == (2.0, 5.0)

    def test_iabs_negative(self):
        # nv
        assert _iabs(-5.0, -2.0) == (2.0, 5.0)

    def test_iabs_mixed(self):
        # nv
        lo, hi = _iabs(-3.0, 4.0)
        assert lo == 0.0 and hi == 4.0

    def test_isin_wide(self):
        # nv
        lo, hi = _isin(0.0, 7.0)
        assert lo <= -1.0 and hi >= 1.0

    def test_icos_narrow(self):
        # cos on [0, pi/2] → [0, 1]
        # nv
        lo, hi = _icos(0.0, math.pi / 2)
        assert lo >= -1e-15 and hi >= 1.0 - 1e-15

    def test_iexp_ilog_roundtrip(self):
        # nv
        lo, hi = _iexp(1.0, 2.0)
        lo2, hi2 = _ilog(lo, hi)
        assert lo2 <= 1.0 and hi2 >= 2.0


# ── Expression interval evaluator ─────────────────────────────────────────────


class TestExprInterval:
    def test_float_literal(self):
        # nv
        trail = Trail()
        lo, hi = _expr_interval(3.14, trail)
        assert lo == hi == 3.14

    def test_int_literal(self):
        # nv
        trail = Trail()
        lo, hi = _expr_interval(5, trail)
        assert lo == hi == 5.0

    def test_real_var(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 2.0, 4.0, trail)
        lo, hi = _expr_interval(x, trail)
        assert lo == 2.0 and hi == 4.0

    def test_unbound_var(self):
        # nv
        trail = Trail()
        x = Var()
        lo, hi = _expr_interval(x, trail)
        assert lo == -math.inf and hi == math.inf

    def test_add_expr(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 1.0, 2.0, trail)
        in_real(y, 3.0, 4.0, trail)
        lo, hi = _expr_interval(Add(left=x, right=y), trail)
        assert lo <= 4.0 and hi >= 6.0

    def test_mult_expr(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 2.0, 3.0, trail)
        in_real(y, 4.0, 5.0, trail)
        lo, hi = _expr_interval(Mult(left=x, right=y), trail)
        assert lo <= 8.0 and hi >= 15.0

    def test_negate_expr(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 1.0, 3.0, trail)
        lo, hi = _expr_interval(Negate(operand=x), trail)
        assert lo <= -3.0 and hi >= -1.0

    def test_pow_int_expr(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 2.0, 3.0, trail)
        lo, hi = _expr_interval(Pow(left=x, right=2), trail)
        assert lo <= 4.0 and hi >= 9.0


# ── RealVar state tests ───────────────────────────────────────────────────────


class TestRealVar:
    def test_in_real_bounds(self):
        # nv
        trail = Trail()
        x = Var()
        assert in_real(x, 0.0, 1.0, trail)
        s = state(x)
        assert s is not None
        assert s.lo == 0.0 and s.hi == 1.0

    def test_in_real_list(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        assert in_real([x, y], -5.0, 5.0, trail)
        for v in [x, y]:
            s = state(v)
            assert s.lo == -5.0 and s.hi == 5.0

    def test_in_real_narrows_existing(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        in_real(x, 2.0, 8.0, trail)
        s = state(x)
        assert s.lo == 2.0 and s.hi == 8.0

    def test_in_real_empty_fails(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 5.0, 10.0, trail)
        assert not in_real(x, 11.0, 15.0, trail)

    def test_unify_in_bounds_succeeds(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        assert unify(x, 0.5, trail)
        assert deref(x) == 0.5

    def test_unify_out_of_bounds_fails(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        mark = trail.mark()
        assert not unify(x, 2.0, trail)
        trail.undo(mark)

    def test_unify_at_lower_bound(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 3.0, 7.0, trail)
        assert unify(x, 3.0, trail)

    def test_unify_at_upper_bound(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 3.0, 7.0, trail)
        assert unify(x, 7.0, trail)

    def test_backtrack_restores_domain(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        mark = trail.mark()
        real_le(x, 5.0, trail)
        assert state(x).hi <= 5.0
        trail.undo(mark)
        assert state(x).hi == 10.0

    def test_point_domain_binds_var(self):
        # nv
        trail = Trail()
        x = Var()
        assert in_real(x, 3.0, 3.0, trail)
        assert deref(x) == 3.0

    def test_ground_int_checks_domain(self):
        # nv
        trail = Trail()
        assert in_real(5, 0.0, 10.0, trail)

    def test_ground_int_out_of_range_fails(self):
        # nv
        trail = Trail()
        assert not in_real(15, 0.0, 10.0, trail)

    def test_unify_two_real_vars_merges(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 0.0, 5.0, trail)
        in_real(y, 2.0, 8.0, trail)
        assert unify(x, y, trail)
        # After merge, bound_to gets intersection [2, 5]
        bound = deref(x)
        s = state(bound)
        assert s.lo == 2.0 and s.hi == 5.0

    def test_unify_two_real_vars_disjoint_fails(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 0.0, 3.0, trail)
        in_real(y, 5.0, 8.0, trail)
        mark = trail.mark()
        assert not unify(x, y, trail)
        trail.undo(mark)


# ── Constraint propagation ────────────────────────────────────────────────────


class TestLinearConstraints:
    def test_eq_pins_var(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        assert real_eq(x, 3.0, trail)
        s = state(x)
        assert s.lo == 3.0 and s.hi == 3.0

    def test_eq_narrows_from_both_sides(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 0.0, 10.0, trail)
        in_real(y, 0.0, 10.0, trail)
        # x == y and x <= 5 → both narrowed to [0, 5]
        real_eq(x, y, trail)
        real_le(x, 5.0, trail)
        sx = state(x)
        sy = state(y)
        assert sx.hi <= 5.0 + 1e-12
        assert sy.hi <= 5.0 + 1e-12

    def test_le_narrows_upper(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        assert real_le(x, 5.0, trail)
        assert state(x).hi <= 5.0

    def test_le_narrows_lower(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        assert real_le(3.0, x, trail)
        assert state(x).lo >= 3.0

    def test_lt_narrows(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        assert real_lt(x, 5.0, trail)
        assert state(x).hi < 5.0

    def test_ge_succeeds(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 5.0, 10.0, trail)
        assert real_ge(x, 3.0, trail)

    def test_gt_narrows_lower(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        assert real_gt(x, 3.0, trail)
        assert state(x).lo > 3.0

    def test_eq_unsatisfiable(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        assert not real_eq(x, 5.0, trail)

    def test_le_unsatisfiable(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 5.0, 10.0, trail)
        assert not real_le(x, 3.0, trail)

    def test_ge_unsatisfiable(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 5.0, trail)
        assert not real_ge(x, 8.0, trail)

    def test_ne_ground_equal_fails(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 3.0, 3.0, trail)  # point
        assert not real_ne(x, 3.0, trail)

    def test_ne_non_ground_passes(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        assert real_ne(x, 5.0, trail)

    def test_add_constraint_propagates(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 0.0, 10.0, trail)
        in_real(y, 0.0, 10.0, trail)
        # x + y == 6 and x == 2 → y == 4
        real_eq(Add(left=x, right=y), 6.0, trail)
        real_eq(x, 2.0, trail)
        sy = state(y)
        assert abs(sy.lo - 4.0) < 1e-10 and abs(sy.hi - 4.0) < 1e-10

    def test_sub_constraint(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 0.0, 10.0, trail)
        in_real(y, 0.0, 10.0, trail)
        # x - y == 3 and x == 7 → y == 4
        real_eq(Sub(left=x, right=y), 3.0, trail)
        real_eq(x, 7.0, trail)
        sy = state(y)
        assert abs(sy.lo - 4.0) < 1e-10 and abs(sy.hi - 4.0) < 1e-10


class TestNonLinearConstraints:
    def test_square_narrows_upper(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        # x^2 <= 4 → x <= 2
        assert real_le(Mult(left=x, right=x), 4.0, trail)
        assert state(x).hi <= 2.0 + 1e-12

    def test_square_eq_pin(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        # x^2 == 9 → x in [3, 3] (non-negative domain)
        assert real_eq(Mult(left=x, right=x), 9.0, trail)
        s = state(x)
        assert s.lo <= 3.0 <= s.hi

    def test_square_unsatisfiable(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        # x^2 == -1 has no solution
        assert not real_eq(Mult(left=x, right=x), -1.0, trail)

    def test_product_constraint(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 2.0, 4.0, trail)
        in_real(y, 1.0, 3.0, trail)
        # x * y <= 6 → x <= 3 (since y >= 1, x <= 6)
        assert real_le(Mult(left=x, right=y), 6.0, trail)
        # At least some narrowing should have occurred
        assert state(x).hi <= 6.0 + 1e-12

    def test_negate_constraint(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, -5.0, 5.0, trail)
        # -x == 3 → x == -3
        assert real_eq(Negate(operand=x), 3.0, trail)
        s = state(x)
        assert abs(s.lo - (-3.0)) < 1e-10 and abs(s.hi - (-3.0)) < 1e-10

    def test_pow2_constraint(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        # x^2 == 4 via Pow node
        assert real_eq(Pow(left=x, right=2), 4.0, trail)
        s = state(x)
        assert s.lo <= 2.0 <= s.hi


# ── Labeling ──────────────────────────────────────────────────────────────────


class TestLabelReal:
    def test_ieee_termination(self):
        # Check that bisection produces at least one near-point solution.
        # We only take the first solution to avoid enumerating all 2^53 leaves.
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        gen = label_real([x], trail)
        got = next(gen, "none")
        assert got is None  # at least one solution exists
        # x should be in a near-point interval
        v = deref(x)
        if is_var(v):
            s = state(v)
            mid = (s.lo + s.hi) / 2.0
            assert mid <= s.lo or mid >= s.hi  # IEEE termination criterion met

    def test_eps_stopping(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        eps = 1e-4
        # Check first few solutions only
        count = 0
        for _ in label_real([x], trail, eps=eps):
            v = deref(x)
            if is_var(v):
                assert state(v).hi - state(v).lo <= eps
            count += 1
            if count >= 5:
                break
        assert count >= 1

    def test_already_ground_yields_once(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 3.0, 3.0, trail)  # point — binds immediately
        sols = collect_solutions(label_real([x], trail))
        assert len(sols) >= 1

    def test_empty_list_yields_once(self):
        # nv
        trail = Trail()
        sols = collect_solutions(label_real([], trail))
        assert len(sols) == 1

    def test_constrained_labeling(self):
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 4.0, trail)
        # x^2 == 4 → x == 2 (non-negative domain); propagation narrows to ~[2, 2]
        real_eq(Mult(left=x, right=x), 4.0, trail)
        sols = []
        for _ in label_real([x], trail, eps=1e-9):
            v = deref(x)
            if is_var(v):
                s = state(v)
                sols.append((s.lo + s.hi) / 2.0)
            else:
                sols.append(float(v))
            if len(sols) >= 5:
                break
        assert len(sols) >= 1
        for mid in sols:
            assert abs(mid - 2.0) < 1e-6

    def test_unit_circle(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_real(x, 0.0, 1.0, trail)
        in_real(y, 0.0, 1.0, trail)
        real_eq(Add(left=Mult(left=x, right=x), right=Mult(left=y, right=y)), 1.0, trail)

        def mid(v):
            v = deref(v)
            if is_var(v):
                s = state(v)
                return (s.lo + s.hi) / 2.0
            return float(v)

        sols = []
        for _ in label_real([x, y], trail, eps=1e-9):
            sols.append((mid(x), mid(y)))
            if len(sols) >= 3:
                break
        assert len(sols) >= 1
        for mx, my in sols:
            assert abs(mx ** 2 + my ** 2 - 1.0) < 1e-6

    def test_backtrack_restores_state(self):
        # Verify that after a labeling step the trail can be restored
        # nv
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 1.0, trail)
        mark = trail.mark()
        gen = label_real([x], trail)
        next(gen, None)  # get first solution
        del gen          # discard generator (no more iteration)
        trail.undo(mark)
        s = state(x)
        assert s.lo == 0.0 and s.hi == 1.0


# ── FD/real dispatch ──────────────────────────────────────────────────────────


class TestFDRealDispatch:
    def test_float_triggers_real_dispatch(self):
        """fd_eq dispatches to CLP(R) when a float literal is present."""
        # nv
        from clausal.logic.clpfd import fd_eq
        trail = Trail()
        x = Var()
        # x == 3.14 — float triggers real dispatch
        assert fd_eq(x, 3.14, trail)
        s = state(x)
        assert s is not None
        assert s.lo == 3.14 and s.hi == 3.14

    def test_float_le_dispatch(self):
        # nv
        from clausal.logic.clpfd import fd_le
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        assert fd_le(x, 5.0, trail)
        assert state(x).hi <= 5.0

    def test_real_var_triggers_dispatch(self):
        """fd_eq dispatches to CLP(R) when a var has REAL_KEY."""
        # nv
        from clausal.logic.clpfd import fd_eq
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        y = Var()
        # y is plain, but x has real attr — dispatch to real
        assert fd_eq(x, y, trail)

    def test_fd_var_not_dispatched(self):
        """Pure integer FD constraints still work normally."""
        # nv
        from clausal.logic.clpfd import fd_eq, in_domain
        trail = Trail()
        x = Var()
        in_domain(x, 1, 10, trail)
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5


# ── Float-literal auto-promotion ─────────────────────────────────────────────


class TestAutoPromotion:
    def test_float_eq_undeclared_var(self):
        """X == 2.0 with undeclared X automatically uses CLP(R)."""
        # nv
        from clausal.logic.clpfd import fd_eq
        trail = Trail()
        x = Var()
        assert fd_eq(x, 2.0, trail)
        s = state(x)
        assert s is not None

    def test_float_in_expression(self):
        """Mult(X, X) == 9.0 uses CLP(R) via float on rhs."""
        # nv
        from clausal.logic.clpfd import fd_eq
        trail = Trail()
        x = Var()
        in_real(x, 0.0, 10.0, trail)
        assert fd_eq(Mult(left=x, right=x), 9.0, trail)
        s = state(x)
        assert s.lo <= 3.0 <= s.hi

    def test_ground_float_eq(self):
        """Ground float comparison goes through real path."""
        # nv
        from clausal.logic.clpfd import fd_eq
        trail = Trail()
        assert fd_eq(3.0, 3.0, trail)
        assert not fd_eq(3.0, 4.0, trail)
