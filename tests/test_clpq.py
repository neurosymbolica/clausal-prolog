"""Tests for CLP(Q) — constraint logic programming over rationals."""

from fractions import Fraction as F

import pytest

from clausal.logic.variables import Var, Trail, deref, is_var, get_attr, unify
from clausal.logic.clpq import (
    Q_KEY, in_q, q_eq, q_ne, q_lt, q_le, q_gt, q_ge,
    maximize, minimize, sup, inf, entailed, dump_q, bb_inf,
    _linearize, _get_tableau, _tableaux, _last_snapshot,
)
from clausal.terms import Add, Sub, Mult, Div, Negate


@pytest.fixture(autouse=True)
def _clean_tableaux():
    """Clear global tableau state between tests to prevent leaks."""
    _tableaux.clear()
    _last_snapshot.clear()
    yield
    _tableaux.clear()
    _last_snapshot.clear()


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
        # B1: variables should be bound to optimal values
        assert deref(x) == F(7)
        assert deref(y) == F(2)

    def test_minimize_lp_binds_vars(self):
        """After minimize, X and Y should be bound to optimal point."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 100, trail)
        assert q_le(Add(left=Mult(left=F(2), right=x), right=y), F(16), trail)
        assert q_le(Add(left=x, right=Mult(left=F(2), right=y)), F(11), trail)
        assert q_le(Add(left=x, right=Mult(left=F(3), right=y)), F(15), trail)
        obj = Add(left=Mult(left=F(30), right=x), right=Mult(left=F(50), right=y))
        result = Var()
        assert minimize(obj, result, trail)
        # Minimum of 30X+50Y at (0,0) = 0 with all constraints satisfied at origin
        assert deref(result) == F(0)
        assert deref(x) == F(0)
        assert deref(y) == F(0)

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


# ── sup/inf ──────────────────────────────────────────────────────────────────


class TestSupInf:
    def test_sup_simple(self):
        """sup(X) with X <= 10 → 10."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_le(x, F(10), trail)
        result = Var()
        assert sup(x, result, trail)
        assert deref(result) == F(10)

    def test_inf_simple(self):
        """inf(X) with X >= 3 → 3."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_ge(x, F(3), trail)
        result = Var()
        assert inf(x, result, trail)
        assert deref(result) == F(3)

    def test_sup_does_not_bind_vars(self):
        """sup should compute the bound WITHOUT binding X."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_le(x, F(10), trail)
        result = Var()
        assert sup(x, result, trail)
        assert deref(result) == F(10)
        assert is_var(deref(x))  # x must remain unbound

    def test_inf_does_not_bind_vars(self):
        """inf should compute the bound WITHOUT binding X."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_ge(x, F(3), trail)
        result = Var()
        assert inf(x, result, trail)
        assert is_var(deref(x))  # x must remain unbound

    def test_sup_lp(self):
        """sup(30X + 50Y) with LP constraints → 310 (without binding X, Y)."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 1000, trail)
        q_le(Add(left=Mult(left=F(2), right=x), right=y), F(16), trail)
        q_le(Add(left=x, right=Mult(left=F(2), right=y)), F(11), trail)
        q_le(Add(left=x, right=Mult(left=F(3), right=y)), F(15), trail)
        obj = Add(left=Mult(left=F(30), right=x), right=Mult(left=F(50), right=y))
        result = Var()
        assert sup(obj, result, trail)
        assert deref(result) == F(310)
        # Variables must NOT be bound
        assert is_var(deref(x))
        assert is_var(deref(y))


# ── entailed ─────────────────────────────────────────────────────────────────


class TestEntailed:
    def test_entailed_le_true(self):
        """X <= 4 entails X <= 5."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_le(x, F(4), trail)
        assert entailed('=<', x, F(5), trail)

    def test_entailed_le_false(self):
        """X <= 4 does NOT entail X <= 3."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_le(x, F(4), trail)
        assert not entailed('=<', x, F(3), trail)

    def test_entailed_ge_true(self):
        """X >= 5 entails X >= 3."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_ge(x, F(5), trail)
        assert entailed('>=', x, F(3), trail)

    def test_entailed_eq_true(self):
        """X == 5 entails X = 5."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_eq(x, F(5), trail)
        assert entailed('=', x, F(5), trail)

    def test_entailed_eq_false(self):
        """X in [0, 10] does NOT entail X = 5."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert not entailed('=', x, F(5), trail)

    def test_entailed_ne_true(self):
        """X <= 4 entails X != 5 (since X can never reach 5)."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_le(x, F(4), trail)
        assert entailed('\\=', x, F(5), trail)

    def test_entailed_ne_false(self):
        """X in [0, 10] does NOT entail X != 5 (X could be 5)."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert not entailed('\\=', x, F(5), trail)

    def test_entailed_does_not_modify_store(self):
        """entailed must not change the constraint store."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        entailed('=<', x, F(5), trail)
        # x should still be unconstrained beyond [0, 10]
        assert is_var(deref(x))

    def test_entailed_does_not_add_q_attr(self):
        """entailed on a bare variable must not add Q attributes."""
        trail = Trail()
        x = Var()
        entailed('=<', x, F(5), trail)
        assert get_attr(x, Q_KEY) is None


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


class TestDumpQ:
    """Fourier-Motzkin projection of constraint store."""

    def test_simple_bounds(self):
        """in_q(X, 0, 10) projects to {-X =< 0} and {X =< 10}."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        result = dump_q([x], trail)
        assert any('=< 0' in c for c in result)   # lower bound
        assert any('=< 10' in c for c in result)   # upper bound

    def test_inequality_projection(self):
        """Slacks are eliminated, original constraints recovered."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 100, trail)
        q_le(Add(left=Mult(left=F(2), right=x), right=y), F(16), trail)
        q_le(Add(left=x, right=Mult(left=F(2), right=y)), F(11), trail)
        result = dump_q([x, y], trail)
        # Should contain the two original constraints (plus bounds)
        assert len(result) >= 4  # 2 inequalities + at least 2 bounds
        # Check that no internal variable names appear
        for c in result:
            assert '_-' not in c, f"Internal variable leaked: {c}"

    def test_equality_projection(self):
        """Equality: X + Y = 10 projects correctly."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 100, trail)
        q_eq(Add(left=x, right=y), F(10), trail)
        result = dump_q([x, y], trail)
        # Should contain an equality constraint
        assert any('= 10' in c for c in result)

    def test_no_internal_vars(self):
        """Projection must eliminate all slack/internal variables."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 1000, trail)
        q_le(Add(left=Mult(left=F(2), right=x), right=y), F(16), trail)
        q_le(Add(left=x, right=Mult(left=F(2), right=y)), F(11), trail)
        q_le(Add(left=x, right=Mult(left=F(3), right=y)), F(15), trail)
        result = dump_q([x, y], trail)
        for c in result:
            # No negative IDs (slack vars) should appear
            assert '_-' not in c, f"Internal variable leaked: {c}"

    def test_empty_store(self):
        """No constraints → empty projection."""
        trail = Trail()
        x = Var()
        in_q(x, trail=trail)
        result = dump_q([x], trail)
        # Unbounded variable — no constraints to project
        assert result == []

    def test_ground_var(self):
        """X = 5 projects to {X = 5} (or equivalent bounds)."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        q_eq(x, F(5), trail)
        # x is now ground — dump_q with unbound vars only
        y = Var()
        in_q(y, 0, 10, trail)
        result = dump_q([y], trail)
        assert any('=< 10' in c for c in result)


class TestBBInf:
    """Branch-and-bound mixed-integer optimization."""

    def test_simple_integer(self):
        """min(X) with X >= 3/2, X integer → 2."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        q_ge(x, F(3, 2), trail)
        result = Var()
        assert bb_inf([x], x, result, trail)
        assert deref(result) == F(2)

    def test_integer_lp(self):
        """SICStus example: min(X) subject to X >= Y + Z, Y > 1, Z > 1,
        all integer → X = 4 (Y=2, Z=2)."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        in_q([x, y, z], 0, 100, trail)
        q_ge(x, Add(left=y, right=z), trail)
        q_ge(y, F(2), trail)  # Y > 1 with integer Y means Y >= 2
        q_ge(z, F(2), trail)  # Z > 1 with integer Z means Z >= 2
        result = Var()
        assert bb_inf([x, y, z], x, result, trail)
        assert deref(result) == F(4)

    def test_no_integer_constraint(self):
        """If IntVars is empty, bb_inf == inf (LP relaxation)."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        q_ge(x, F(3, 2), trail)
        result = Var()
        assert bb_inf([], x, result, trail)
        assert deref(result) == F(3, 2)  # no integrality → rational optimum

    def test_infeasible(self):
        """X >= 5/2, X <= 7/2, integer and X != 3 → infeasible.
        LP has solutions (2.5 to 3.5), but only integer in that range is 3,
        and we exclude 3 via bounds."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_ge(x, F(5, 2), trail)   # X >= 2.5
        q_le(x, F(7, 2), trail)   # X <= 3.5
        # Only integer in [2.5, 3.5] is 3
        # Make it infeasible by splitting: X <= 2 or X >= 4
        # Actually, bb_inf should find X=3. Let's test a truly infeasible case:
        # X >= 3.1, X <= 3.9 — no integer in range
        trail2 = Trail()
        y = Var()
        in_q(y, 0, 100, trail2)
        q_ge(y, F(31, 10), trail2)  # Y >= 3.1
        q_le(y, F(39, 10), trail2)  # Y <= 3.9
        result = Var()
        assert not bb_inf([y], y, result, trail2)

    def test_already_integer(self):
        """If LP optimum is already integer, no branching needed."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        q_ge(x, F(3), trail)
        result = Var()
        assert bb_inf([x], x, result, trail)
        assert deref(result) == F(3)

    def test_mixed_integer(self):
        """Only some variables must be integer."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        q_le(Add(left=x, right=y), F(5), trail)
        # Minimize x + y with x integer, y rational
        result = Var()
        assert bb_inf([x], Add(left=x, right=y), result, trail)
        # LP minimum is 0 (x=0, y=0), which is already integer for x
        assert deref(result) == F(0)

    def test_two_integer_vars(self):
        """Multi-level branching: both X and Y must be integer.
        min(X + Y) with X + Y >= 5/2, X,Y in [0,10] integer.
        LP relaxation gives X+Y = 5/2 (fractional).
        Integer optimum: X=0, Y=3 (or X=3, Y=0, etc.) → min = 3."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        q_ge(Add(left=x, right=y), F(5, 2), trail)
        result = Var()
        assert bb_inf([x, y], Add(left=x, right=y), result, trail)
        assert deref(result) == F(3)

    def test_binds_variables(self):
        """bb_inf should bind integer variables to their optimal values."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        q_ge(x, F(3, 2), trail)
        result = Var()
        assert bb_inf([x], x, result, trail)
        assert deref(result) == F(2)
        assert deref(x) == F(2)  # x must be bound, not just result

    def test_binds_multiple_vars(self):
        """bb_inf binds all constrained vars to optimal integer point."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        in_q([x, y, z], 0, 100, trail)
        q_ge(x, Add(left=y, right=z), trail)
        q_ge(y, F(2), trail)
        q_ge(z, F(2), trail)
        result = Var()
        assert bb_inf([x, y, z], x, result, trail)
        assert deref(result) == F(4)
        # Variables should be bound to integers
        assert deref(x) == F(4)
        assert deref(y) == F(2)
        assert deref(z) == F(2)


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


# ── Phase A: correctness fix tests ───────────────────────────────────────────


class TestA1MaximizeSnapshot:
    """Issue #10: maximize/minimize must snapshot before mutating tableau."""

    def test_maximize_backtrack_restores_tableau(self):
        """After backtracking past a maximize, the tableau is restored."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_le(x, F(10), trail)

        mark = trail.mark()
        result = Var()
        assert maximize(x, result, trail)
        assert deref(result) == F(10)

        trail.undo(mark)
        # Tableau should be restored — x is still constrained but not optimized
        assert is_var(deref(x))
        # Should be able to post new constraints
        assert q_le(x, F(5), trail)

    def test_minimize_backtrack_restores_tableau(self):
        trail = Trail()
        x = Var()
        in_q(x, 0, 100, trail)
        q_ge(x, F(3), trail)

        mark = trail.mark()
        result = Var()
        assert minimize(x, result, trail)
        assert deref(result) == F(3)

        trail.undo(mark)
        assert is_var(deref(x))
        assert q_ge(x, F(7), trail)  # can tighten further


class TestA2PivotBound:
    """Issue #13: pivot must respect the target bound (lower or upper)."""

    def test_upper_bound_inequality(self):
        """System where feasibility requires variables near upper bounds."""
        trail = Trail()
        x, y = Var(), Var()
        in_q(x, 0, 10, trail)
        in_q(y, 0, 10, trail)
        # X + Y >= 15 with X,Y in [0,10] is feasible (e.g., x=10, y=5)
        assert q_ge(Add(left=x, right=y), F(15), trail)
        # Verify the system is feasible via optimization
        result = Var()
        assert maximize(Add(left=x, right=y), result, trail)
        assert deref(result) == F(20)  # max x+y with x,y in [0,10] and x+y>=15

    def test_infeasible_upper_bound(self):
        """X + Y >= 25 with X,Y in [0,10] → infeasible."""
        trail = Trail()
        x, y = Var(), Var()
        in_q(x, 0, 10, trail)
        in_q(y, 0, 10, trail)
        assert not q_ge(Add(left=x, right=y), F(25), trail)


class TestA3DualSimplex:
    """Issue #3: dual simplex must handle complex inequality systems correctly."""

    def test_three_constraint_feasibility(self):
        """System that requires multiple dual simplex pivots."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 100, trail)
        assert q_le(Add(left=x, right=y), F(10), trail)
        assert q_ge(x, F(3), trail)
        assert q_ge(y, F(4), trail)
        # Feasible: e.g., x=3, y=7 or x=6, y=4

    def test_tight_system(self):
        """Constraints that leave only one feasible point via equality."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 100, trail)
        # Use explicit equality instead of two opposing inequalities
        assert q_eq(Add(left=x, right=y), F(10), trail)
        assert q_eq(x, F(4), trail)
        assert deref(y) == F(6)

    def test_contradictory_inequalities(self):
        """X + Y <= 5, X >= 3, Y >= 3 → infeasible (3+3=6 > 5)."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 100, trail)
        assert q_le(Add(left=x, right=y), F(5), trail)
        assert q_ge(x, F(3), trail)
        assert not q_ge(y, F(3), trail)

    def test_degenerate_vertex(self):
        """Multiple constraints active at the same point (degeneracy)."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        assert q_le(x, F(5), trail)
        assert q_le(y, F(5), trail)
        assert q_le(Add(left=x, right=y), F(10), trail)  # redundant at (5,5)
        # All three constraints are tight at x=5, y=5
        result = Var()
        assert maximize(Add(left=x, right=y), result, trail)
        assert deref(result) == F(10)


class TestA4Disequality:
    """Issue #1: q_ne must store and check disequalities properly."""

    def test_ne_prevents_binding_to_excluded_value(self):
        """X != 5, then X == 5 must fail."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert q_ne(x, F(5), trail)
        assert not q_eq(x, F(5), trail)

    def test_ne_allows_other_values(self):
        """X != 5, X == 3 succeeds."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert q_ne(x, F(5), trail)
        assert q_eq(x, F(3), trail)
        assert deref(x) == F(3)

    def test_strict_lt_rejects_equal(self):
        """X < 5 means X <= 5 AND X != 5. If X is later forced to 5, it fails."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert q_lt(x, F(5), trail)
        assert not q_eq(x, F(5), trail)

    def test_strict_lt_allows_less(self):
        """X < 5, X == 4 succeeds."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        assert q_lt(x, F(5), trail)
        assert q_eq(x, F(4), trail)

    def test_ne_two_vars(self):
        """X != Y, then X and Y forced equal must fail."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        assert q_ne(x, y, trail)
        assert q_eq(x, F(5), trail)
        assert not q_eq(y, F(5), trail)

    def test_ne_two_vars_different_ok(self):
        """X != Y, X = 5, Y = 3 succeeds."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        assert q_ne(x, y, trail)
        assert q_eq(x, F(5), trail)
        assert q_eq(y, F(3), trail)

    def test_ne_ground_equal_fails(self):
        """Posting q_ne(5, 5) fails immediately."""
        trail = Trail()
        assert not q_ne(F(5), F(5), trail)

    def test_ne_ground_different_succeeds(self):
        """Posting q_ne(5, 3) succeeds immediately."""
        trail = Trail()
        assert q_ne(F(5), F(3), trail)

    def test_ne_backtrack_restores(self):
        """Disequality is undone on backtrack."""
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        mark = trail.mark()
        assert q_ne(x, F(5), trail)
        trail.undo(mark)
        # After undo, X != 5 is gone — X == 5 should succeed
        assert q_eq(x, F(5), trail)
        assert deref(x) == F(5)


class TestB4SnapshotDedup:
    """Issue #4: redundant tableau snapshots should be avoided."""

    def test_multi_constraint_single_snapshot(self):
        """A multi-step operation (q_eq triggering implied bindings) should
        still be undoable as a single unit, proving snapshots work correctly
        even when deduplicated."""
        trail = Trail()
        x, y = Var(), Var()
        in_q([x, y], 0, 10, trail)
        q_eq(Add(left=x, right=y), F(10), trail)
        mark = trail.mark()
        # This q_eq triggers Gaussian elimination + check_implied_bindings
        # + potentially _q_hook — all should share one snapshot
        q_eq(x, F(3), trail)
        assert deref(y) == F(7)
        trail.undo(mark)
        # After undo, both x and y should be restored
        assert is_var(deref(x))
        assert is_var(deref(y))


class TestA5FloatTypeError:
    """Issue #9: unifying a Q-var with float must raise TypeError."""

    def test_unify_q_var_with_float_raises(self):
        trail = Trail()
        x = Var()
        in_q(x, 0, 10, trail)
        with pytest.raises(TypeError, match="Cannot unify CLP\\(Q\\)"):
            unify(x, 3.14, trail)

    def test_float_literal_does_not_reach_q(self):
        """fd_eq(X, 3.14) should dispatch to CLP(R), not CLP(Q)."""
        from clausal.logic.clpfd import fd_eq
        from clausal.logic.clpr import REAL_KEY
        trail = Trail()
        x = Var()
        # No in_q — float should go to CLP(R), not CLP(Q)
        assert fd_eq(x, 3.14, trail)
        # x should have a real attribute, not a Q attribute
        assert get_attr(deref(x) if not is_var(deref(x)) else x, REAL_KEY) is not None or \
               isinstance(deref(x), float) or not is_var(deref(x))
        assert get_attr(x, Q_KEY) is None  # must NOT have Q attribute


# ── End-to-end Clausal integration tests ─────────────────────────────────────
# These compile and run .clausal files through the full pipeline (parser →
# compiler → runtime dispatch), verifying every doc example end-to-end.


class TestClausalIntegration:
    """Run the doc examples as compiled Clausal predicates."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        from clausal.testing import load_clausal_module
        self.mod = load_clausal_module("tests/fixtures/clpq_examples.clausal")

    def _run(self, name, arity):
        """Run a predicate and return the first solution's deref'd args."""
        from clausal.logic.solve import call
        args = [Var() for _ in range(arity)]
        for _trail in call(name, *args, module=self.mod):
            return tuple(deref(a) for a in args)
        return None  # no solution

    def test_two_var(self):
        result = self._run("TwoVar", 2)
        assert result is not None
        x, y = result
        assert x == F(3)
        assert y == F(7)

    def test_three_var(self):
        result = self._run("ThreeVar", 3)
        assert result is not None
        x, y, z = result
        assert x == F(11, 3)
        assert y == F(5, 3)
        assert z == F(2, 3)

    def test_rational_coeffs(self):
        result = self._run("RationalCoeffs", 2)
        assert result is not None
        x, y = result
        assert x == F(2)
        assert y == F(0)

    def test_feasible(self):
        result = self._run("Feasible", 2)
        assert result is not None  # just needs to succeed

    def test_infeasible(self):
        result = self._run("Infeasible", 1)
        assert result is None  # must fail

    def test_lp_maximize(self):
        result = self._run("LP", 3)
        assert result is not None
        x, y, obj = result
        assert obj == F(310)

    def test_scheduling_minimize(self):
        result = self._run("Scheduling", 3)
        assert result is not None
        x, y, cost = result
        assert cost == F(30)
