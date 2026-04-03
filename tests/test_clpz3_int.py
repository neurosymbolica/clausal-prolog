"""Tests for Z3 integer constraints — Phase 2.

Covers: in_z3, all_different_z3, label_z3, z3_check,
        z3_eq/ne/lt/le/gt/ge, and the SEND+MORE=MONEY benchmark.

All tests are skipped if z3-solver is not installed.
"""

from __future__ import annotations

import pytest

z3 = pytest.importorskip("z3")

from fractions import Fraction

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.clpz3 import (
    in_z3, all_different_z3, label_z3, z3_check,
    z3_eq, z3_ne, z3_lt, z3_le, z3_gt, z3_ge,
    get_z3_state, z3_push,
)
from clausal.terms import Add, Mult, Sub


# ══════════════════════════════════════════════════════════════════════════════
# in_z3
# ══════════════════════════════════════════════════════════════════════════════

class TestInZ3:
    def test_single_var(self):
        trail = Trail()
        x = Var()
        assert in_z3(x, 1, 9, trail)

    def test_list_of_vars(self):
        trail = Trail()
        xs = [Var() for _ in range(5)]
        assert in_z3(xs, 0, 100, trail)

    def test_ground_in_range(self):
        trail = Trail()
        assert in_z3(5, 1, 9, trail)

    def test_ground_out_of_range(self):
        trail = Trail()
        assert not in_z3(15, 1, 9, trail)

    def test_ground_non_int_fails(self):
        trail = Trail()
        assert not in_z3(5.5, 1, 9, trail)

    def test_empty_domain(self):
        trail = Trail()
        x = Var()
        assert not in_z3(x, 5, 1, trail)

    def test_singleton_domain_binds(self):
        """Singleton domain [3,3] should bind var immediately."""
        trail = Trail()
        x = Var()
        assert in_z3(x, 3, 3, trail)
        assert deref(x) == 3

    def test_singleton_domain_backtracking(self):
        """Singleton binding is undone on trail.undo()."""
        trail = Trail()
        x = Var()
        mark = trail.mark()
        assert in_z3(x, 3, 3, trail)
        assert deref(x) == 3
        trail.undo(mark)
        assert is_var(deref(x))

    def test_narrowing_via_double_declaration(self):
        """Two in_z3 calls narrow the domain via both constraints."""
        trail = Trail()
        x = Var()
        assert in_z3(x, 1, 9, trail)
        assert in_z3(x, 3, 7, trail)
        state = get_z3_state(trail)
        z3_x = state.var_map[id(x)]
        # Value 2 should now be unsat
        state.solver.push()
        state.solver.add(z3_x == 2)
        assert state.solver.check() == z3.unsat
        state.solver.pop()
        # Value 5 should be sat
        state.solver.push()
        state.solver.add(z3_x == 5)
        assert state.solver.check() == z3.sat
        state.solver.pop()

    def test_mixed_list_ground_and_var(self):
        """List with mix of ground ints (checked) and vars (constrained)."""
        trail = Trail()
        x, y = Var(), Var()
        # 5 is in [1,9], so overall succeeds
        assert in_z3([x, 5, y], 1, 9, trail)

    def test_mixed_list_ground_out_of_range_fails(self):
        trail = Trail()
        x = Var()
        assert not in_z3([x, 15], 1, 9, trail)

    def test_non_integer_bounds_raise(self):
        trail = Trail()
        x = Var()
        with pytest.raises(TypeError, match="bounds must be integers"):
            in_z3(x, 1.5, 9, trail)

    def test_var_registered_as_intsort(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 9, trail)
        state = get_z3_state(trail)
        z3_x = state.var_map[id(x)]
        assert z3_x.sort() == z3.IntSort()

    def test_negative_domain(self):
        """Negative domain [-5, 5] works correctly."""
        trail = Trail()
        x = Var()
        assert in_z3(x, -5, 5, trail)
        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == list(range(-5, 6))

    def test_all_negative_domain(self):
        """All-negative domain [-3, -1]."""
        trail = Trail()
        x = Var()
        assert in_z3(x, -3, -1, trail)
        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == [-3, -2, -1]

    def test_crossing_zero_constraint(self):
        """x + y == 0 with domain [-2, 2]."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], -2, 2, trail)
        z3_eq(Add(left=x, right=y), 0, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            assert deref(x) + deref(y) == 0
            solutions.append((deref(x), deref(y)))
        assert len(solutions) == 5  # (-2,2),(-1,1),(0,0),(1,-1),(2,-2)

    def test_singleton_already_registered_tightens_z3(self):
        """Singleton narrowing on an already-Z3-registered var tightens Z3."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 9, trail)
        state = get_z3_state(trail)
        z3_x = state.var_map[id(x)]
        # Now narrow to singleton
        assert in_z3(x, 5, 5, trail)
        assert deref(x) == 5
        # Z3 should know x == 5 now
        state.solver.push()
        state.solver.add(z3_x != 5)
        assert state.solver.check() == z3.unsat
        state.solver.pop()


# ══════════════════════════════════════════════════════════════════════════════
# all_different_z3
# ══════════════════════════════════════════════════════════════════════════════

class TestAllDifferentZ3:
    def test_basic(self):
        trail = Trail()
        xs = [Var() for _ in range(3)]
        in_z3(xs, 1, 3, trail)
        assert all_different_z3(xs, trail)

    def test_with_ground_int(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 3, trail)
        assert all_different_z3([x, 1, y], trail)

    def test_duplicate_grounds_lazy_fail(self):
        """Distinct(1, 1) doesn't fail eagerly — detected at check time."""
        trail = Trail()
        assert all_different_z3([1, 1], trail)
        assert not z3_check(trail)

    def test_empty_list(self):
        trail = Trail()
        assert all_different_z3([], trail)

    def test_single_element(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 9, trail)
        assert all_different_z3([x], trail)

    def test_non_int_non_var_raises(self):
        trail = Trail()
        with pytest.raises(TypeError, match="expected int or Var"):
            all_different_z3(["not_valid"], trail)


# ══════════════════════════════════════════════════════════════════════════════
# label_z3
# ══════════════════════════════════════════════════════════════════════════════

class TestLabelZ3:
    def test_single_var_all_solutions(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 3, trail)
        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == [1, 2, 3]

    def test_two_vars_all_different(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 2, trail)
        all_different_z3([x, y], trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert sorted(solutions) == [(1, 2), (2, 1)]

    def test_no_solution(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 1, trail)
        all_different_z3([x, y], trail)
        assert list(label_z3([x, y], trail)) == []

    def test_vars_unbound_after_exhaustion(self):
        """After generator exhausts, Clausal vars are unbound."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 3, trail)
        for _ in label_z3([x], trail):
            pass
        assert is_var(deref(x))

    def test_early_termination(self):
        """Breaking out of label_z3 loop works; var stays bound at break."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 100, trail)
        mark = trail.mark()
        for _ in label_z3([x], trail):
            val = deref(x)
            assert isinstance(val, int)
            assert 1 <= val <= 100
            break
        # After break, var is still bound (we haven't called trail.undo)
        assert isinstance(deref(x), int)
        # Undo restores unbound state
        trail.undo(mark)
        assert is_var(deref(x))

    def test_all_ground_single_solution(self):
        trail = Trail()
        solutions = list(label_z3([1, 2, 3], trail))
        assert len(solutions) == 1

    def test_unregistered_var_raises(self):
        trail = Trail()
        x = Var()
        # x not declared with in_z3
        with pytest.raises(ValueError, match="not registered with Z3"):
            list(label_z3([x], trail))

    def test_non_int_non_var_raises(self):
        trail = Trail()
        with pytest.raises(TypeError, match="expected int or Var"):
            list(label_z3(["bad"], trail))

    def test_solutions_differ(self):
        """Each yielded solution is a distinct assignment."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert len(solutions) == len(set(solutions)) == 5


# ══════════════════════════════════════════════════════════════════════════════
# z3_check
# ══════════════════════════════════════════════════════════════════════════════

class TestZ3Check:
    def test_empty_constraints_sat(self):
        trail = Trail()
        assert z3_check(trail)

    def test_consistent_constraints_sat(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 9, trail)
        assert z3_check(trail)

    def test_inconsistent_constraints_unsat(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 3, trail)
        z3_lt(x, 1, trail)   # x < 1 contradicts x >= 1
        assert not z3_check(trail)


# ══════════════════════════════════════════════════════════════════════════════
# Arithmetic constraints
# ══════════════════════════════════════════════════════════════════════════════

class TestArithmeticConstraints:
    def test_eq_yields_equal_pairs(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 5, trail)
        z3_eq(x, y, trail)
        for _ in label_z3([x, y], trail):
            assert deref(x) == deref(y)
            break

    def test_ne_yields_unequal_pairs(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 2, trail)
        z3_ne(x, y, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert sorted(solutions) == [(1, 2), (2, 1)]

    def test_lt(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 3, trail)
        z3_lt(x, y, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert all(a < b for a, b in solutions)
        assert len(solutions) == 3  # (1,2),(1,3),(2,3)

    def test_le(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 2, trail)
        z3_le(x, y, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert all(a <= b for a, b in solutions)

    def test_gt(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 3, trail)
        z3_gt(x, y, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert all(a > b for a, b in solutions)

    def test_ge(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 2, trail)
        z3_ge(x, y, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert all(a >= b for a, b in solutions)

    def test_eq_with_ground(self):
        """z3_eq(x, 5) constrains x == 5."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 9, trail)
        z3_eq(x, 5, trail)
        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert solutions == [5]

    def test_linear_expression_add(self):
        """X + Y == 10 with domain [0, 10] → 11 solutions."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_eq(Add(left=x, right=y), 10, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            assert deref(x) + deref(y) == 10
            solutions.append((deref(x), deref(y)))
        assert len(solutions) == 11

    def test_linear_expression_sub(self):
        """X - Y == 0 with domain [1, 3] → X == Y."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 3, trail)
        z3_eq(Sub(left=x, right=y), 0, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            assert deref(x) == deref(y)
            solutions.append((deref(x), deref(y)))
        assert len(solutions) == 3

    def test_linear_expression_mult(self):
        """2 * X == 6 with domain [1, 5] → X == 3."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        z3_eq(Mult(left=2, right=x), 6, trail)
        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert solutions == [3]


# ══════════════════════════════════════════════════════════════════════════════
# Backtracking integration
# ══════════════════════════════════════════════════════════════════════════════

class TestBacktracking:
    def test_trail_undo_retracts_z3_scope(self):
        """After trail.undo(), Z3 constraints added in that scope are gone."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        state = get_z3_state(trail)
        z3_x = state.var_map[id(x)]

        mark = trail.mark()
        z3_push(trail)
        z3_lt(x, 5, trail)  # x < 5 in this scope

        # Before undo: x >= 8 is unsat
        state.solver.push()
        state.solver.add(z3_x == 8)
        assert state.solver.check() == z3.unsat
        state.solver.pop()

        trail.undo(mark)

        # After undo: x >= 8 is sat again
        state.solver.push()
        state.solver.add(z3_x == 8)
        assert state.solver.check() == z3.sat
        state.solver.pop()

    def test_label_blocking_clauses_retracted_on_undo(self):
        """Blocking clauses from label_z3 are cleaned up after backtracking."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 3, trail)
        state = get_z3_state(trail)

        mark = trail.mark()

        # Exhaust all solutions — 3 blocking clauses accumulate
        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == [1, 2, 3]

        # Backtrack past the labeling call
        trail.undo(mark)

        # Blocking clauses should be gone — all 3 values are satisfiable again
        z3_x = state.var_map[id(x)]
        for v in [1, 2, 3]:
            state.solver.push()
            state.solver.add(z3_x == v)
            assert state.solver.check() == z3.sat, f"Expected {v} to be sat after undo"
            state.solver.pop()

    def test_interleaved_clausal_and_z3(self):
        """Clausal bindings and Z3 constraints interleave correctly."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 5, trail)

        # Bind y = 3 on the trail
        mark = trail.mark()
        assert unify(y, 3, trail)

        # Post x < y (which is x < 3)
        z3_push(trail)
        z3_lt(x, 3, trail)

        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == [1, 2]

        trail.undo(mark)
        assert is_var(deref(y))


# ══════════════════════════════════════════════════════════════════════════════
# SEND + MORE = MONEY
# ══════════════════════════════════════════════════════════════════════════════

class TestSendMoreMoney:
    def test_unique_solution(self):
        trail = Trail()
        S, E, N, D, M, O, R, Y = (Var() for _ in range(8))
        in_z3([S, E, N, D, M, O, R, Y], 0, 9, trail)
        all_different_z3([S, E, N, D, M, O, R, Y], trail)
        z3_ne(S, 0, trail)
        z3_ne(M, 0, trail)

        # SEND + MORE = MONEY
        send  = Add(left=Add(left=Add(left=Mult(left=S, right=1000),
                                      right=Mult(left=E, right=100)),
                             right=Mult(left=N, right=10)),
                    right=D)
        more  = Add(left=Add(left=Add(left=Mult(left=M, right=1000),
                                      right=Mult(left=O, right=100)),
                             right=Mult(left=R, right=10)),
                    right=E)
        money = Add(left=Add(left=Add(left=Add(left=Mult(left=M, right=10000),
                                               right=Mult(left=O, right=1000)),
                                      right=Mult(left=N, right=100)),
                             right=Mult(left=E, right=10)),
                    right=Y)
        z3_eq(Add(left=send, right=more), money, trail)

        solutions = []
        for _ in label_z3([S, E, N, D, M, O, R, Y], trail):
            solutions.append(tuple(deref(v) for v in [S, E, N, D, M, O, R, Y]))

        assert len(solutions) == 1
        assert solutions[0] == (9, 5, 6, 7, 1, 0, 8, 2)
