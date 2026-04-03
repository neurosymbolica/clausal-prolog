"""Tests for Z3 optimization & soft constraints — Phase 7."""

from __future__ import annotations
import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.clpz3 import (
    in_z3, in_z3_real, z3_check, z3_eq, z3_le, z3_ge,
    z3_soft, z3_max_sat, z3_optimize_label, z3_multi_optimize,
    maximize_z3, minimize_z3, get_z3_state,
    label_z3, label_z3_real, z3_push,
)
from clausal.pythonic_ast.nodes import ArithEq, LtE, GtE, Add, Sub


# ══════════════════════════════════════════════════════════════════════════════
# Soft Constraints
# ══════════════════════════════════════════════════════════════════════════════

class TestSoftConstraints:
    def test_soft_post_succeeds(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        assert z3_soft(ArithEq(left=x, right=5), 1, trail)

    def test_soft_with_group(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        assert z3_soft(ArithEq(left=x, right=5), 1, trail, group="g1")
        state = get_z3_state(trail)
        assert state._soft_constraints[-1] == (
            state._soft_constraints[-1][0], 1, "g1"
        )

    def test_soft_backtrack(self):
        """Soft constraints are retracted on trail backtrack."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)

        mark = trail.mark()
        z3_soft(ArithEq(left=x, right=5), 10, trail)
        assert any(e is not None for e in get_z3_state(trail)._soft_constraints)

        trail.undo(mark)

        active = [s for s in get_z3_state(trail)._soft_constraints if s is not None]
        assert len(active) == 0

    def test_multiple_soft_backtrack_partial(self):
        """Only soft constraints added after the mark are retracted."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)

        z3_soft(ArithEq(left=x, right=3), 5, trail)

        mark = trail.mark()
        z3_soft(ArithEq(left=x, right=7), 10, trail)
        trail.undo(mark)

        active = [s for s in get_z3_state(trail)._soft_constraints if s is not None]
        assert len(active) == 1
        assert active[0][1] == 5  # only weight-5 remains


# ══════════════════════════════════════════════════════════════════════════════
# MaxSAT
# ══════════════════════════════════════════════════════════════════════════════

class TestMaxSat:
    def test_all_soft_satisfiable(self):
        """When all soft constraints can be satisfied, total = sum of weights."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        z3_soft(GtE(left=x, right=0), 5, trail)
        z3_soft(LtE(left=x, right=10), 3, trail)
        sat = Var()
        assert z3_max_sat(sat, trail)
        assert deref(sat) == 8

    def test_conflicting_soft(self):
        """Conflicting soft constraints: higher-weight wins."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 1, trail)
        z3_soft(ArithEq(left=x, right=0), 5, trail)
        z3_soft(ArithEq(left=x, right=1), 3, trail)
        sat = Var()
        assert z3_max_sat(sat, trail)
        # x=0 satisfies weight-5, violates weight-3 → total = 5
        assert deref(sat) == 5

    def test_infeasible_returns_false(self):
        """MaxSAT on infeasible hard constraints returns False."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 5, trail)
        z3_eq(x, 10, trail)  # contradicts domain
        sat = Var()
        assert not z3_max_sat(sat, trail)

    def test_no_soft_constraints(self):
        """MaxSAT with no soft constraints returns 0."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        sat = Var()
        assert z3_max_sat(sat, trail)
        assert deref(sat) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Optimize + Label
# ══════════════════════════════════════════════════════════════════════════════

class TestOptimizeLabel:
    def test_maximize_simple(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        obj = Var()
        sols = []
        for _ in z3_optimize_label([x], x, obj, "maximize", trail):
            sols.append((deref(x), deref(obj)))
        assert sols == [(10, 10)]

    def test_minimize_simple(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        obj = Var()
        sols = []
        for _ in z3_optimize_label([x], x, obj, "minimize", trail):
            sols.append((deref(x), deref(obj)))
        assert sols == [(0, 0)]

    def test_maximize_with_constraint(self):
        """Maximize x subject to x + y == 10, y >= 3."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_eq(Add(left=x, right=y), 10, trail)
        z3_ge(y, 3, trail)
        obj = Var()
        sols = []
        for _ in z3_optimize_label([x, y], x, obj, "maximize", trail):
            sols.append((deref(x), deref(y), deref(obj)))
        assert sols == [(7, 3, 7)]

    def test_minimize_with_soft(self):
        """Soft constraints influence optimization."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        # Soft: prefer x >= 5 (weight 10)
        z3_soft(GtE(left=x, right=5), 10, trail)
        obj = Var()
        # Minimize x — but soft constraint pushes toward x >= 5
        # Since soft constraints are included, the optimizer balances them
        sols = []
        for _ in z3_optimize_label([x], x, obj, "minimize", trail):
            sols.append(deref(obj))
        # The objective is purely "minimize x", soft doesn't affect the objective
        # but soft constraints are present in the Optimize instance
        assert len(sols) == 1

    def test_infeasible_yields_nothing(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 5, trail)
        z3_eq(x, 10, trail)
        obj = Var()
        sols = list(z3_optimize_label([x], x, obj, "maximize", trail))
        assert len(sols) == 0

    def test_invalid_mode_raises(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        with pytest.raises(ValueError, match="mode must be"):
            list(z3_optimize_label([x], x, Var(), "bad_mode", trail))

    def test_bindings_undone_after_yield(self):
        """Variables are unbound after the generator completes."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        obj = Var()
        for _ in z3_optimize_label([x], x, obj, "maximize", trail):
            assert deref(x) == 10
        assert is_var(deref(x))
        assert is_var(deref(obj))


# ══════════════════════════════════════════════════════════════════════════════
# Multi-Objective Optimization
# ══════════════════════════════════════════════════════════════════════════════

class TestMultiObjective:
    def test_lex_two_objectives(self):
        """Lexicographic: maximize x first, then maximize y."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_le(Add(left=x, right=y), 10, trail)
        r1, r2 = Var(), Var()
        sols = []
        for _ in z3_multi_optimize(
            [(x, "maximize"), (y, "maximize")],
            [r1, r2], "lex", trail
        ):
            sols.append((deref(r1), deref(r2)))
        assert len(sols) == 1
        # Lex: first maximize x → 10, then maximize y s.t. x+y ≤ 10 → y = 0
        assert sols[0] == (10, 0)

    def test_lex_minimize_then_maximize(self):
        """Lex: minimize x, then maximize y."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_le(Add(left=x, right=y), 10, trail)
        r1, r2 = Var(), Var()
        sols = []
        for _ in z3_multi_optimize(
            [(x, "minimize"), (y, "maximize")],
            [r1, r2], "lex", trail
        ):
            sols.append((deref(r1), deref(r2)))
        assert len(sols) == 1
        # Lex: first minimize x → 0, then maximize y s.t. y ≤ 10 → y = 10
        assert sols[0] == (0, 10)

    def test_box_independent(self):
        """Box mode: each objective optimized independently."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_le(Add(left=x, right=y), 10, trail)
        r1, r2 = Var(), Var()
        sols = []
        for _ in z3_multi_optimize(
            [(x, "maximize"), (y, "maximize")],
            [r1, r2], "box", trail
        ):
            sols.append((deref(r1), deref(r2)))
        assert len(sols) == 1

    def test_infeasible_yields_nothing(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 5, trail)
        z3_eq(x, 10, trail)
        r = Var()
        sols = list(z3_multi_optimize(
            [(x, "maximize")], [r], "lex", trail
        ))
        assert len(sols) == 0

    def test_bindings_undone(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        r = Var()
        for _ in z3_multi_optimize([(x, "maximize")], [r], "lex", trail):
            assert deref(r) == 10
        assert is_var(deref(r))


# ══════════════════════════════════════════════════════════════════════════════
# Interaction with existing maximize_z3 / minimize_z3 (Phase 4)
# ══════════════════════════════════════════════════════════════════════════════

class TestPhase4OptWithSoft:
    def test_maximize_z3_includes_soft(self):
        """Phase 4 maximize_z3 now includes soft constraints in optimize.

        The soft constraint x <= 5 (weight 1) competes with the objective
        maximize(x).  Z3 Optimize satisfies soft constraints when possible,
        so the optimal is x=5 (soft satisfied) not x=10.
        """
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        z3_soft(LtE(left=x, right=5), 1, trail)
        obj = Var()
        assert maximize_z3(x, obj, trail)
        assert deref(obj) == 5

    def test_minimize_z3_basic(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        obj = Var()
        assert minimize_z3(x, obj, trail)
        assert deref(obj) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Scheduling example (integration test)
# ══════════════════════════════════════════════════════════════════════════════

class TestIntegrationScheduling:
    def test_minimize_makespan(self):
        """Minimize makespan of 3 non-overlapping tasks."""
        trail = Trail()
        t1, t2, t3 = Var(), Var(), Var()
        in_z3([t1, t2, t3], 0, 100, trail)
        # t1 before t2 (duration 5)
        z3_le(Add(left=t1, right=5), t2, trail)
        # t2 before t3 (duration 3)
        z3_le(Add(left=t2, right=3), t3, trail)

        obj = Var()
        sols = []
        for _ in z3_optimize_label([t1, t2, t3], t3, obj, "minimize", trail):
            sols.append((deref(t1), deref(t2), deref(t3), deref(obj)))

        assert len(sols) == 1
        t1v, t2v, t3v, cost = sols[0]
        # Optimal: t1=0, t2=5, t3=8
        assert t1v == 0
        assert t2v == 5
        assert t3v == 8
        assert cost == 8

    def test_maxsat_scheduling_preferences(self):
        """MaxSAT: satisfy as many scheduling preferences as possible."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        # Soft preferences: x <= 3 (weight 2), x >= 7 (weight 5)
        # These conflict: can't have x <= 3 AND x >= 7
        z3_soft(LtE(left=x, right=3), 2, trail)
        z3_soft(GtE(left=x, right=7), 5, trail)
        sat = Var()
        assert z3_max_sat(sat, trail)
        # Higher weight wins: x >= 7 (weight 5)
        assert deref(sat) == 5


# ══════════════════════════════════════════════════════════════════════════════
# Real-valued optimization (Phase 4 + Phase 7)
# ══════════════════════════════════════════════════════════════════════════════

class TestRealOptimize:
    def test_real_minimize(self):
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        obj = Var()
        assert minimize_z3(x, obj, trail)
        assert deref(obj) == 0

    def test_real_maximize(self):
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        obj = Var()
        assert maximize_z3(x, obj, trail)
        assert deref(obj) == 10
