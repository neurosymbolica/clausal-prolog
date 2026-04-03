"""Tests for Z3 Boolean constraints — Phase 3.

Covers: clausal_bool_to_z3, sat_z3, taut_z3, sat_count_z3,
        label_z3_bool, at_most_z3, at_least_z3, exactly_z3.

All tests are skipped if z3-solver is not installed.
"""

from __future__ import annotations

import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.clpz3 import (
    clausal_bool_to_z3, sat_z3, taut_z3, sat_count_z3, label_z3_bool,
    at_most_z3, at_least_z3, exactly_z3,
    get_z3_state, z3_check,
)
from clausal.pythonic_ast.nodes import BitAnd, BitOr, BitXor, Invert
from clausal.logic.clpb import BoolEq, BoolImpl


# ══════════════════════════════════════════════════════════════════════════════
# clausal_bool_to_z3 — expression translation
# ══════════════════════════════════════════════════════════════════════════════

class TestClausalboolToZ3:
    def test_bool_true(self):
        trail = Trail()
        r = clausal_bool_to_z3(True, trail)
        assert z3.is_true(r)

    def test_bool_false(self):
        trail = Trail()
        r = clausal_bool_to_z3(False, trail)
        assert z3.is_false(r)

    def test_int_one_is_true(self):
        """int 1 → BoolVal(True), not IntVal(1)."""
        trail = Trail()
        r = clausal_bool_to_z3(1, trail)
        assert z3.is_true(r)

    def test_int_zero_is_false(self):
        """int 0 → BoolVal(False), not IntVal(0)."""
        trail = Trail()
        r = clausal_bool_to_z3(0, trail)
        assert z3.is_false(r)

    def test_var_gets_boolsort(self):
        trail = Trail()
        x = Var()
        r = clausal_bool_to_z3(x, trail)
        assert r.sort() == z3.BoolSort()

    def test_bitand(self):
        trail = Trail()
        x, y = Var(), Var()
        r = clausal_bool_to_z3(BitAnd(left=x, right=y), trail)
        assert z3.is_bool(r)

    def test_bitor(self):
        trail = Trail()
        x, y = Var(), Var()
        r = clausal_bool_to_z3(BitOr(left=x, right=y), trail)
        assert z3.is_bool(r)

    def test_bitxor(self):
        trail = Trail()
        x, y = Var(), Var()
        r = clausal_bool_to_z3(BitXor(left=x, right=y), trail)
        assert z3.is_bool(r)

    def test_invert(self):
        trail = Trail()
        x = Var()
        r = clausal_bool_to_z3(Invert(operand=x), trail)
        assert z3.is_bool(r)

    def test_booleq(self):
        trail = Trail()
        x, y = Var(), Var()
        r = clausal_bool_to_z3(BoolEq(x, y), trail)
        assert z3.is_bool(r)

    def test_boolimpl(self):
        trail = Trail()
        x, y = Var(), Var()
        r = clausal_bool_to_z3(BoolImpl(x, y), trail)
        assert z3.is_bool(r)

    def test_nested(self):
        trail = Trail()
        x, y, z_var = Var(), Var(), Var()
        # BoolEq(X, X & Y)
        expr = BoolEq(x, BitAnd(left=x, right=y))
        r = clausal_bool_to_z3(expr, trail)
        assert z3.is_bool(r)

    def test_bound_var_uses_value(self):
        """A var bound to 1 is translated as BoolVal(True)."""
        trail = Trail()
        x = Var()
        unify(x, 1, trail)
        r = clausal_bool_to_z3(x, trail)
        assert z3.is_true(r)

    def test_unknown_type_raises(self):
        trail = Trail()
        with pytest.raises(TypeError):
            clausal_bool_to_z3("not_a_bool_expr", trail)


# ══════════════════════════════════════════════════════════════════════════════
# sat_z3
# ══════════════════════════════════════════════════════════════════════════════

class TestSatZ3:
    def test_simple_var(self):
        """sat_z3(X) forces X true."""
        trail = Trail()
        x = Var()
        assert sat_z3(x, trail)
        # Label: only x=1 satisfies
        solutions = []
        for _ in label_z3_bool([x], trail):
            solutions.append(deref(x))
        assert solutions == [1]

    def test_and(self):
        trail = Trail()
        x, y = Var(), Var()
        sat_z3(BitAnd(left=x, right=y), trail)
        solutions = []
        for _ in label_z3_bool([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert solutions == [(1, 1)]

    def test_contradiction_lazy(self):
        """sat_z3(X & ~X) is lazy — returns True but solver is unsat."""
        trail = Trail()
        x = Var()
        assert sat_z3(BitAnd(left=x, right=Invert(operand=x)), trail)
        assert not z3_check(trail)

    def test_ground_true(self):
        trail = Trail()
        assert sat_z3(1, trail)
        assert z3_check(trail)

    def test_ground_false_makes_unsat(self):
        trail = Trail()
        sat_z3(0, trail)
        assert not z3_check(trail)

    def test_booleq(self):
        """BoolEq(X, Y): solutions are (0,0) and (1,1)."""
        trail = Trail()
        x, y = Var(), Var()
        sat_z3(BoolEq(x, y), trail)
        solutions = []
        for _ in label_z3_bool([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert sorted(solutions) == [(0, 0), (1, 1)]

    def test_boolimpl(self):
        """BoolImpl(X, Y): not (1, 0)."""
        trail = Trail()
        x, y = Var(), Var()
        sat_z3(BoolImpl(x, y), trail)
        solutions = []
        for _ in label_z3_bool([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert (1, 0) not in solutions
        assert len(solutions) == 3


# ══════════════════════════════════════════════════════════════════════════════
# taut_z3
# ══════════════════════════════════════════════════════════════════════════════

class TestTautZ3:
    def test_tautology(self):
        trail = Trail()
        x = Var()
        t = Var()
        assert taut_z3(BitOr(left=x, right=Invert(operand=x)), t, trail)
        assert deref(t) == 1

    def test_contradiction(self):
        trail = Trail()
        x = Var()
        t = Var()
        assert taut_z3(BitAnd(left=x, right=Invert(operand=x)), t, trail)
        assert deref(t) == 0

    def test_indeterminate_fails(self):
        trail = Trail()
        x = Var()
        t = Var()
        assert not taut_z3(x, t, trail)
        assert is_var(deref(t))

    def test_forced_true_by_constraint(self):
        """After sat_z3(X), taut_z3(X, T) → T = 1."""
        trail = Trail()
        x = Var()
        t = Var()
        sat_z3(x, trail)
        assert taut_z3(x, t, trail)
        assert deref(t) == 1

    def test_forced_false_by_constraint(self):
        """After sat_z3(~X), taut_z3(X, T) → T = 0."""
        trail = Trail()
        x = Var()
        t = Var()
        sat_z3(Invert(operand=x), trail)
        assert taut_z3(x, t, trail)
        assert deref(t) == 0

    def test_does_not_modify_solver(self):
        """taut_z3 uses push/pop — constraint store unchanged after call."""
        trail = Trail()
        x = Var()
        t = Var()
        state = get_z3_state(trail)
        before = state.solver.num_scopes()
        taut_z3(x, t, trail)
        assert state.solver.num_scopes() == before

    def test_t_already_bound_wrong(self):
        """T already bound to wrong value → fails."""
        trail = Trail()
        x = Var()
        t = Var()
        unify(t, 0, trail)
        # X | ~X is a tautology → would set T=1, but T=0 → unify fails
        assert not taut_z3(BitOr(left=x, right=Invert(operand=x)), t, trail)


# ══════════════════════════════════════════════════════════════════════════════
# sat_count_z3
# ══════════════════════════════════════════════════════════════════════════════

class TestSatCountZ3:
    def test_or_two_vars(self):
        """X | Y: 3 of 4 assignments satisfy."""
        trail = Trail()
        x, y = Var(), Var()
        n = Var()
        assert sat_count_z3(BitOr(left=x, right=y), n, trail)
        assert deref(n) == 3

    def test_and_two_vars(self):
        """X & Y: 1 of 4."""
        trail = Trail()
        x, y = Var(), Var()
        n = Var()
        assert sat_count_z3(BitAnd(left=x, right=y), n, trail)
        assert deref(n) == 1

    def test_tautology_count(self):
        """X | ~X: 2 of 2 (both assignments satisfy)."""
        trail = Trail()
        x = Var()
        n = Var()
        assert sat_count_z3(BitOr(left=x, right=Invert(operand=x)), n, trail)
        assert deref(n) == 2

    def test_contradiction_count(self):
        """X & ~X: 0."""
        trail = Trail()
        x = Var()
        n = Var()
        assert sat_count_z3(BitAnd(left=x, right=Invert(operand=x)), n, trail)
        assert deref(n) == 0

    def test_does_not_modify_solver(self):
        """sat_count_z3 uses push/pop — constraint store unchanged after call."""
        trail = Trail()
        x, y = Var(), Var()
        n = Var()
        state = get_z3_state(trail)
        before = state.solver.num_scopes()
        sat_count_z3(BitOr(left=x, right=y), n, trail)
        assert state.solver.num_scopes() == before

    def test_n_already_bound_correct(self):
        """N bound to correct count → succeeds."""
        trail = Trail()
        x = Var()
        n = Var()
        unify(n, 1, trail)
        assert sat_count_z3(x, n, trail)

    def test_n_already_bound_wrong(self):
        """N bound to wrong count → fails."""
        trail = Trail()
        x = Var()
        n = Var()
        unify(n, 0, trail)
        assert not sat_count_z3(x, n, trail)

    def test_counts_within_existing_constraint_context(self):
        """Prior sat_z3 constraints restrict which assignments are counted.

        X forced true → X | Y is always true → both Y=0 and Y=1 satisfy.
        So the count for X | Y, within the context where X is forced, is 2
        (not the unconstrained 3).
        """
        trail = Trail()
        x, y = Var(), Var()
        n = Var()
        sat_z3(x, trail)   # force x = true in the solver
        assert sat_count_z3(BitOr(left=x, right=y), n, trail)
        assert deref(n) == 2


# ══════════════════════════════════════════════════════════════════════════════
# label_z3_bool
# ══════════════════════════════════════════════════════════════════════════════

class TestLabelZ3Bool:
    def test_single_var_all_assignments(self):
        trail = Trail()
        x = Var()
        solutions = []
        for _ in label_z3_bool([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == [0, 1]

    def test_two_vars_all_assignments(self):
        trail = Trail()
        x, y = Var(), Var()
        solutions = []
        for _ in label_z3_bool([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert len(solutions) == 4
        assert sorted(solutions) == [(0, 0), (0, 1), (1, 0), (1, 1)]

    def test_with_sat_constraint(self):
        """sat_z3(X & Y) → only (1,1)."""
        trail = Trail()
        x, y = Var(), Var()
        sat_z3(BitAnd(left=x, right=y), trail)
        solutions = []
        for _ in label_z3_bool([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert solutions == [(1, 1)]

    def test_empty_list(self):
        trail = Trail()
        assert len(list(label_z3_bool([], trail))) == 1

    def test_all_ground(self):
        trail = Trail()
        assert len(list(label_z3_bool([1, 0, 1], trail))) == 1

    def test_vars_unbound_after_exhaustion(self):
        trail = Trail()
        x = Var()
        for _ in label_z3_bool([x], trail):
            pass
        assert is_var(deref(x))

    def test_invalid_ground_value_raises(self):
        trail = Trail()
        with pytest.raises(TypeError):
            list(label_z3_bool([2], trail))

    def test_unregistered_var_gets_boolsort(self):
        """Vars not yet in var_map are auto-registered as BoolSort."""
        trail = Trail()
        x = Var()
        solutions = []
        for _ in label_z3_bool([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == [0, 1]
        state = get_z3_state(trail)
        assert state.var_map[id(x)].sort() == z3.BoolSort()


# ══════════════════════════════════════════════════════════════════════════════
# Cardinality constraints
# ══════════════════════════════════════════════════════════════════════════════

class TestCardinalityConstraints:
    def test_at_most_one(self):
        trail = Trail()
        xs = [Var() for _ in range(3)]
        at_most_z3(xs, 1, trail)
        solutions = []
        for _ in label_z3_bool(xs, trail):
            solutions.append(tuple(deref(x) for x in xs))
        assert len(solutions) == 4  # (0,0,0) + 3 singletons
        assert all(sum(s) <= 1 for s in solutions)

    def test_at_most_zero(self):
        """at_most_z3(Xs, 0) → all false."""
        trail = Trail()
        xs = [Var() for _ in range(3)]
        at_most_z3(xs, 0, trail)
        solutions = []
        for _ in label_z3_bool(xs, trail):
            solutions.append(tuple(deref(x) for x in xs))
        assert solutions == [(0, 0, 0)]

    def test_at_least_two(self):
        trail = Trail()
        xs = [Var() for _ in range(3)]
        at_least_z3(xs, 2, trail)
        solutions = []
        for _ in label_z3_bool(xs, trail):
            solutions.append(tuple(deref(x) for x in xs))
        assert len(solutions) == 4  # 3 pairs + all-three
        assert all(sum(s) >= 2 for s in solutions)

    def test_exactly_one(self):
        trail = Trail()
        xs = [Var() for _ in range(3)]
        exactly_z3(xs, 1, trail)
        solutions = []
        for _ in label_z3_bool(xs, trail):
            solutions.append(tuple(deref(x) for x in xs))
        assert len(solutions) == 3
        assert all(sum(s) == 1 for s in solutions)

    def test_exactly_two(self):
        trail = Trail()
        xs = [Var() for _ in range(3)]
        exactly_z3(xs, 2, trail)
        solutions = []
        for _ in label_z3_bool(xs, trail):
            solutions.append(tuple(deref(x) for x in xs))
        assert len(solutions) == 3
        assert all(sum(s) == 2 for s in solutions)

    def test_at_most_with_ground(self):
        """at_most_z3([1, X, Y], 1) — 1 already uses the budget."""
        trail = Trail()
        x, y = Var(), Var()
        at_most_z3([1, x, y], 1, trail)
        solutions = []
        for _ in label_z3_bool([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert (1, 0) not in solutions
        assert (0, 1) not in solutions
        assert (1, 1) not in solutions
        assert (0, 0) in solutions


# ══════════════════════════════════════════════════════════════════════════════
# Backtracking
# ══════════════════════════════════════════════════════════════════════════════

class TestBoolBacktracking:
    def test_sat_z3_undone_on_undo(self):
        """sat_z3 constraints within a z3_push scope are retracted on undo."""
        from clausal.logic.clpz3 import z3_push
        trail = Trail()
        x = Var()
        mark = trail.mark()
        z3_push(trail)
        sat_z3(x, trail)          # force x = true in this scope
        assert z3_check(trail)
        sat_z3(Invert(operand=x), trail)  # now x = true AND x = false → unsat
        assert not z3_check(trail)
        trail.undo(mark)
        assert z3_check(trail)    # contradiction scope gone

    def test_label_bool_blocking_retracted(self):
        """Blocking clauses from label_z3_bool are retracted on trail.undo."""
        trail = Trail()
        x = Var()
        state = get_z3_state(trail)
        mark = trail.mark()
        solutions = []
        for _ in label_z3_bool([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == [0, 1]
        trail.undo(mark)
        # Blocking clauses gone — both values satisfiable again
        z3_x = state.var_map[id(x)]
        for val in [z3.BoolVal(True), z3.BoolVal(False)]:
            state.solver.push()
            state.solver.add(z3_x == val)
            assert state.solver.check() == z3.sat
            state.solver.pop()
