"""Tests for Z3 UserPropagateBase integration and table constraint — Phase 5.

Covers: ClausalPropagator (push/pop/fresh), z3_table, inner trampoline.

All tests are skipped if z3-solver is not installed.
"""

from __future__ import annotations

import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.clpz3 import (
    in_z3, label_z3, z3_check, z3_gt, z3_eq, get_z3_state,
    ClausalPropagator, z3_table,
)


# ══════════════════════════════════════════════════════════════════════════════
# ClausalPropagator — push / pop / fresh (trail synchronization)
# ══════════════════════════════════════════════════════════════════════════════

class TestClausalPropagator:
    def _make(self, trail):
        state = get_z3_state(trail)
        return ClausalPropagator(state.solver, trail, state.var_map, state.rev_map)

    def test_push_pop_trail_sync(self):
        """push() saves trail state; pop(1) restores it."""
        # nv
        trail = Trail()
        prop = self._make(trail)

        x = Var()
        prop.push()
        unify(x, 42, trail)
        assert deref(x) == 42

        prop.pop(1)
        assert is_var(deref(x))

    def test_nested_push_pop(self):
        """Two nested push/pop levels restore independently."""
        # nv
        trail = Trail()
        prop = self._make(trail)

        x, y = Var(), Var()
        prop.push()
        unify(x, 1, trail)
        prop.push()
        unify(y, 2, trail)

        assert deref(x) == 1
        assert deref(y) == 2

        prop.pop(1)
        assert deref(x) == 1    # still bound
        assert is_var(deref(y))  # undone

        prop.pop(1)
        assert is_var(deref(x))  # undone

    def test_pop_multiple(self):
        """pop(2) undoes two levels at once."""
        # nv
        trail = Trail()
        prop = self._make(trail)

        x, y = Var(), Var()
        prop.push()
        unify(x, 1, trail)
        prop.push()
        unify(y, 2, trail)

        prop.pop(2)
        assert is_var(deref(x))
        assert is_var(deref(y))

    def test_pop_zero(self):
        """pop(0) is a no-op."""
        # nv
        trail = Trail()
        prop = self._make(trail)
        x = Var()
        prop.push()
        unify(x, 5, trail)
        prop.pop(0)
        assert deref(x) == 5
        prop.pop(1)

    def test_push_does_not_bind(self):
        """push() itself does not bind any variables."""
        # nv
        trail = Trail()
        prop = self._make(trail)
        x = Var()
        prop.push()
        assert is_var(deref(x))
        prop.pop(1)

    def test_scope_marks_stack(self):
        """scope_marks is correct after push/pop."""
        # nv
        trail = Trail()
        prop = self._make(trail)
        assert len(prop.scope_marks) == 0
        prop.push()
        assert len(prop.scope_marks) == 1
        prop.push()
        assert len(prop.scope_marks) == 2
        prop.pop(1)
        assert len(prop.scope_marks) == 1
        prop.pop(1)
        assert len(prop.scope_marks) == 0

    def test_fresh_creates_new_trail(self):
        """fresh(None) creates a new propagator with a different trail."""
        # nv
        trail = Trail()
        prop = self._make(trail)
        fresh = prop.fresh(None)
        assert fresh.trail is not trail

    def test_fresh_shares_var_map(self):
        """fresh() propagator shares var_map/rev_map (read-only during solving)."""
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        prop = self._make(trail)
        fresh = prop.fresh(None)
        assert fresh.var_map is state.var_map
        assert fresh.rev_map is state.rev_map

    def test_fresh_inherits_goals(self):
        """fresh() propagator inherits on_fixed_goals."""
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        goal = object()  # dummy goal
        prop = ClausalPropagator(
            state.solver, trail, state.var_map, state.rev_map,
            on_fixed_goals=[goal],
        )
        fresh = prop.fresh(None)
        assert fresh.on_fixed_goals == [goal]

    def test_fresh_push_pop_independent(self):
        """fresh() propagator's push/pop operate on its own trail."""
        # nv
        trail = Trail()
        prop = self._make(trail)
        fresh = prop.fresh(None)

        x, y = Var(), Var()
        prop.push()
        unify(x, 1, trail)
        fresh.push()
        unify(y, 2, fresh.trail)

        prop.pop(1)
        assert is_var(deref(x))       # original trail undone
        assert deref(y) == 2          # fresh trail unaffected
        fresh.pop(1)
        assert is_var(deref(y))


# ══════════════════════════════════════════════════════════════════════════════
# z3_table — extensional constraint
# ══════════════════════════════════════════════════════════════════════════════

class TestTableConstraint:
    def test_basic_table(self):
        """Variables must match one of the given tuples."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 5, trail)
        z3_table([x, y], [[1, 2], [2, 3], [3, 4]], trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert sorted(solutions) == [(1, 2), (2, 3), (3, 4)]

    def test_empty_table_fails(self):
        """Empty table → no solutions."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 5, trail)
        z3_table([x, y], [], trail)
        assert list(label_z3([x, y], trail)) == []

    def test_table_with_other_constraints(self):
        """Table + additional constraint narrows solutions."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 5, trail)
        z3_table([x, y], [[1, 2], [2, 3], [3, 4]], trail)
        z3_gt(x, 1, trail)  # x > 1
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert sorted(solutions) == [(2, 3), (3, 4)]

    def test_single_row_table(self):
        """Single-row table forces unique solution."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 10, trail)
        z3_table([x, y], [[7, 3]], trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert solutions == [(7, 3)]

    def test_table_single_var(self):
        """Single-variable table works."""
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        z3_table([x], [[2], [5], [8]], trail)
        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == [2, 5, 8]

    def test_table_no_match_in_domain(self):
        """Table tuples outside the declared domain → no solutions."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 3, trail)
        z3_table([x, y], [[5, 6], [7, 8]], trail)
        assert list(label_z3([x, y], trail)) == []

    def test_table_with_ground_var(self):
        """Ground variable in position constrains which tuples match."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 10, trail)
        z3_eq(x, 2, trail)  # x == 2
        z3_table([x, y], [[1, 2], [2, 3], [3, 4]], trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert solutions == [(2, 3)]

    def test_table_backtracking(self):
        """Table constraint is retracted when the trail scope is undone."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 5, trail)
        mark = trail.mark()
        z3_table([x, y], [[1, 2]], trail)
        solutions_restricted = []
        for _ in label_z3([x, y], trail):
            solutions_restricted.append((deref(x), deref(y)))
        assert solutions_restricted == [(1, 2)]

        trail.undo(mark)  # retract z3_table constraint

        # Now any pair in [1,5]² is allowed — check there are many solutions
        solutions_free = []
        for _ in label_z3([x, y], trail):
            solutions_free.append((deref(x), deref(y)))
        assert len(solutions_free) == 25  # 5×5 grid

    def test_table_length_mismatch_raises(self):
        """Tuple length mismatch raises ValueError."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 5, trail)
        with pytest.raises(ValueError, match="tuple length"):
            z3_table([x, y], [[1, 2, 3]], trail)


# ══════════════════════════════════════════════════════════════════════════════
# Inner trampoline (running Clausal goals from propagator context)
# ══════════════════════════════════════════════════════════════════════════════

class TestInnerTrampoline:
    def test_step_generator_in_propagator_context(self):
        """A StepGenerator runs correctly even when created in a propagator context."""
        # nv
        from clausal.logic.trampoline import StepGenerator, trampoline

        trail = Trail()
        state = get_z3_state(trail)
        _ = ClausalPropagator(state.solver, trail, state.var_map, state.rev_map)

        result = Var()

        def my_goal(this_sg, parent, var, value, inner_trail):
            if unify(result, value + 1, inner_trail):
                yield (parent, None)

        sg = StepGenerator(my_goal, None, None, None, Var(), 5, trail)
        trampoline(sg)
        assert deref(result) == 6

    def test_inner_trampoline_bindings_undone_by_pop(self):
        """Bindings made by an inner trampoline are undone by propagator.pop()."""
        # nv
        from clausal.logic.trampoline import StepGenerator, trampoline

        trail = Trail()
        state = get_z3_state(trail)
        prop = ClausalPropagator(state.solver, trail, state.var_map, state.rev_map)

        result = Var()
        prop.push()

        def my_goal(this_sg, parent, inner_trail):
            unify(result, 42, inner_trail)
            yield (parent, None)

        sg = StepGenerator(my_goal, None, None, None, trail)
        trampoline(sg)
        assert deref(result) == 42

        prop.pop(1)
        assert is_var(deref(result))  # undone by pop

    def test_inner_trampoline_multiple_bindings(self):
        """Multiple bindings across two push levels, popped independently."""
        # nv
        from clausal.logic.trampoline import StepGenerator, trampoline

        trail = Trail()
        state = get_z3_state(trail)
        prop = ClausalPropagator(state.solver, trail, state.var_map, state.rev_map)

        a, b = Var(), Var()
        prop.push()

        def bind_a(this_sg, parent, inner_trail):
            unify(a, 10, inner_trail)
            yield (parent, None)

        trampoline(StepGenerator(bind_a, None, None, None, trail))
        assert deref(a) == 10

        prop.push()

        def bind_b(this_sg, parent, inner_trail):
            unify(b, 20, inner_trail)
            yield (parent, None)

        trampoline(StepGenerator(bind_b, None, None, None, trail))
        assert deref(b) == 20

        prop.pop(1)
        assert deref(a) == 10    # a still bound
        assert is_var(deref(b))  # b undone

        prop.pop(1)
        assert is_var(deref(a))  # a undone too
