"""Tests for Z3 integration — Phase 1: core infrastructure.

Tests Z3State management, Var↔Z3 constant mapping, expression translation,
value conversion, and trail ↔ solver push/pop synchronization.

All tests are skipped if z3-solver is not installed.
"""

from __future__ import annotations

import pytest

z3 = pytest.importorskip("z3")

from fractions import Fraction

from clausal.logic.variables import Var, Trail, deref, is_var, unify, get_attr
from clausal.logic.clpz3 import (
    Z3State,
    Z3VarInfo,
    Z3_KEY,
    get_z3_state,
    z3_var_for,
    clausal_to_z3,
    z3_to_python,
    z3_push,
    z3_add,
)


# ══════════════════════════════════════════════════════════════════════════════
# Z3State lifecycle
# ══════════════════════════════════════════════════════════════════════════════

class TestZ3State:
    def test_create_state(self):
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        assert isinstance(state, Z3State)
        assert state.solver is not None

    def test_same_state_same_trail(self):
        # nv
        trail = Trail()
        s1 = get_z3_state(trail)
        s2 = get_z3_state(trail)
        assert s1 is s2

    def test_different_trails_different_states(self):
        # nv
        t1, t2 = Trail(), Trail()
        s1 = get_z3_state(t1)
        s2 = get_z3_state(t2)
        assert s1 is not s2

    def test_state_has_empty_maps(self):
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        assert state.var_map == {}
        assert state.rev_map == {}

    def test_counter_starts_at_zero(self):
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        assert state._counter == 0

    def test_empty_solver_is_sat(self):
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        assert state.solver.check() == z3.sat

    def test_gc_cleanup(self):
        """State is removed from the registry when the trail is GC'd."""
        # nv
        from clausal.logic.clpz3 import _z3_states
        trail = Trail()
        tid = id(trail)
        get_z3_state(trail)
        assert tid in _z3_states
        del trail
        import gc; gc.collect()
        assert tid not in _z3_states


# ══════════════════════════════════════════════════════════════════════════════
# Variable registration
# ══════════════════════════════════════════════════════════════════════════════

class TestVarRegistration:
    def test_register_int_var(self):
        # nv
        trail = Trail()
        x = Var()
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        assert z3_x.sort() == z3.IntSort()

    def test_register_bool_var(self):
        # nv
        trail = Trail()
        b = Var()
        z3_b = z3_var_for(b, z3.BoolSort(), trail)
        assert z3_b.sort() == z3.BoolSort()

    def test_register_real_var(self):
        # nv
        trail = Trail()
        r = Var()
        z3_r = z3_var_for(r, z3.RealSort(), trail)
        assert z3_r.sort() == z3.RealSort()

    def test_same_var_returns_same_constant(self):
        # nv
        trail = Trail()
        x = Var()
        z3_x1 = z3_var_for(x, z3.IntSort(), trail)
        z3_x2 = z3_var_for(x, z3.IntSort(), trail)
        assert z3_x1 is z3_x2

    def test_different_vars_different_constants(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        z3_y = z3_var_for(y, z3.IntSort(), trail)
        assert z3_x is not z3_y
        assert z3_x.get_id() != z3_y.get_id()

    def test_var_map_populated(self):
        # nv
        trail = Trail()
        x = Var()
        state = get_z3_state(trail)
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        assert state.var_map[id(x)] is z3_x

    def test_rev_map_populated(self):
        # nv
        trail = Trail()
        x = Var()
        state = get_z3_state(trail)
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        assert state.rev_map[z3_x.get_id()] is x

    def test_attvar_attribute_stored(self):
        # nv
        trail = Trail()
        x = Var()
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        info = get_attr(x, Z3_KEY)
        assert info is not None
        assert isinstance(info, Z3VarInfo)
        assert info.z3_const is z3_x
        assert info.sort == z3.IntSort()

    def test_ground_var_raises(self):
        # nv
        trail = Trail()
        x = Var()
        unify(x, 42, trail)
        with pytest.raises(TypeError, match="expected unbound Var"):
            z3_var_for(x, z3.IntSort(), trail)

    def test_sort_mismatch_raises(self):
        # nv
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        with pytest.raises(TypeError, match="sort mismatch"):
            z3_var_for(x, z3.BoolSort(), trail)

    def test_unique_names(self):
        """Each Z3 constant gets a unique name."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        z3_y = z3_var_for(y, z3.IntSort(), trail)
        assert str(z3_x) != str(z3_y)

    def test_counter_increments(self):
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        x, y, z = Var(), Var(), Var()
        z3_var_for(x, z3.IntSort(), trail)
        z3_var_for(y, z3.IntSort(), trail)
        z3_var_for(z, z3.IntSort(), trail)
        assert state._counter == 3


# ══════════════════════════════════════════════════════════════════════════════
# Expression translation
# ══════════════════════════════════════════════════════════════════════════════

class TestExpressionTranslation:
    # ── Ground literals ──────────────────────────────────────────────────────

    def test_int_literal(self):
        # nv
        trail = Trail()
        result = clausal_to_z3(42, trail)
        assert z3.is_int_value(result)
        assert result.as_long() == 42

    def test_zero(self):
        # nv
        trail = Trail()
        result = clausal_to_z3(0, trail)
        assert z3.is_int_value(result)
        assert result.as_long() == 0

    def test_negative_int(self):
        # nv
        trail = Trail()
        result = clausal_to_z3(-7, trail)
        assert z3.is_int_value(result)
        assert result.as_long() == -7

    def test_large_int(self):
        # nv
        trail = Trail()
        big = 10 ** 100
        result = clausal_to_z3(big, trail)
        assert z3.is_int_value(result)
        assert result.as_long() == big

    def test_bool_true(self):
        # nv
        trail = Trail()
        result = clausal_to_z3(True, trail)
        assert z3.is_true(result)

    def test_bool_false(self):
        # nv
        trail = Trail()
        result = clausal_to_z3(False, trail)
        assert z3.is_false(result)

    def test_bool_before_int(self):
        """True/False must translate to Bool, not Int (bool is subclass of int)."""
        # nv
        trail = Trail()
        assert clausal_to_z3(True, trail).sort() == z3.BoolSort()
        assert clausal_to_z3(False, trail).sort() == z3.BoolSort()

    def test_float_literal(self):
        # nv
        trail = Trail()
        result = clausal_to_z3(1.5, trail)
        assert result.sort() == z3.RealSort()

    def test_fraction_literal(self):
        # nv
        trail = Trail()
        result = clausal_to_z3(Fraction(3, 7), trail)
        assert result.sort() == z3.RealSort()

    # ── Variables ────────────────────────────────────────────────────────────

    def test_registered_var_lookup(self):
        # nv
        trail = Trail()
        x = Var()
        z3_x = z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(x, trail)
        assert result is z3_x

    def test_unregistered_var_with_default_sort(self):
        # nv
        trail = Trail()
        x = Var()
        result = clausal_to_z3(x, trail, default_sort=z3.IntSort())
        assert result.sort() == z3.IntSort()
        # Should now be registered
        state = get_z3_state(trail)
        assert id(x) in state.var_map

    def test_unregistered_var_no_sort_raises(self):
        # nv
        trail = Trail()
        x = Var()
        with pytest.raises(ValueError, match="Unregistered"):
            clausal_to_z3(x, trail)

    def test_bound_var_translates_value(self):
        """A bound Var translates its dereferenced value."""
        # nv
        trail = Trail()
        x = Var()
        unify(x, 10, trail)
        result = clausal_to_z3(x, trail)
        assert z3.is_int_value(result)
        assert result.as_long() == 10

    # ── Arithmetic operators ─────────────────────────────────────────────────

    def test_addition(self):
        # nv
        from clausal.pythonic_ast.nodes import Add
        trail = Trail()
        x, y = Var(), Var()
        z3_var_for(x, z3.IntSort(), trail)
        z3_var_for(y, z3.IntSort(), trail)
        result = clausal_to_z3(Add(left=x, right=y), trail)
        assert result.sort() == z3.IntSort()
        assert result.num_args() == 2

    def test_subtraction(self):
        # nv
        from clausal.pythonic_ast.nodes import Sub
        trail = Trail()
        x, y = Var(), Var()
        z3_var_for(x, z3.IntSort(), trail)
        z3_var_for(y, z3.IntSort(), trail)
        result = clausal_to_z3(Sub(left=x, right=y), trail)
        assert result.sort() == z3.IntSort()

    def test_multiplication(self):
        # nv
        from clausal.pythonic_ast.nodes import Mult
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(Mult(left=2, right=x), trail)
        assert result.sort() == z3.IntSort()

    def test_negate(self):
        # nv
        from clausal.pythonic_ast.nodes import Negate
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(Negate(operand=x), trail)
        assert result.sort() == z3.IntSort()

    def test_nested_arithmetic(self):
        """2 * x + 3 translates correctly."""
        # nv
        from clausal.pythonic_ast.nodes import Add, Mult
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        expr = Add(left=Mult(left=2, right=x), right=3)
        result = clausal_to_z3(expr, trail)
        assert result.sort() == z3.IntSort()

    # ── Comparison operators ─────────────────────────────────────────────────

    def test_arith_eq_gives_bool(self):
        # nv
        from clausal.pythonic_ast.nodes import ArithEq
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(ArithEq(left=x, right=5), trail)
        assert result.sort() == z3.BoolSort()

    def test_arith_neq(self):
        # nv
        from clausal.pythonic_ast.nodes import ArithNeq
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(ArithNeq(left=x, right=5), trail)
        assert result.sort() == z3.BoolSort()

    def test_lt(self):
        # nv
        from clausal.pythonic_ast.nodes import Lt
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(Lt(left=x, right=10), trail)
        assert result.sort() == z3.BoolSort()

    def test_lte(self):
        # nv
        from clausal.pythonic_ast.nodes import LtE
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(LtE(left=x, right=10), trail)
        assert result.sort() == z3.BoolSort()

    def test_gt(self):
        # nv
        from clausal.pythonic_ast.nodes import Gt
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(Gt(left=x, right=0), trail)
        assert result.sort() == z3.BoolSort()

    def test_gte(self):
        # nv
        from clausal.pythonic_ast.nodes import GtE
        trail = Trail()
        x = Var()
        z3_var_for(x, z3.IntSort(), trail)
        result = clausal_to_z3(GtE(left=x, right=0), trail)
        assert result.sort() == z3.BoolSort()

    # ── Boolean operators ────────────────────────────────────────────────────

    def test_and(self):
        # nv
        from clausal.pythonic_ast.nodes import And
        trail = Trail()
        p, q = Var(), Var()
        z3_var_for(p, z3.BoolSort(), trail)
        z3_var_for(q, z3.BoolSort(), trail)
        result = clausal_to_z3(And(left=p, right=q), trail)
        assert result.sort() == z3.BoolSort()

    def test_or(self):
        # nv
        from clausal.pythonic_ast.nodes import Or
        trail = Trail()
        p, q = Var(), Var()
        z3_var_for(p, z3.BoolSort(), trail)
        z3_var_for(q, z3.BoolSort(), trail)
        result = clausal_to_z3(Or(left=p, right=q), trail)
        assert result.sort() == z3.BoolSort()

    def test_not(self):
        # nv
        from clausal.pythonic_ast.nodes import Not
        trail = Trail()
        p = Var()
        z3_var_for(p, z3.BoolSort(), trail)
        result = clausal_to_z3(Not(operand=p), trail)
        assert result.sort() == z3.BoolSort()

    def test_bitand(self):
        # nv
        from clausal.pythonic_ast.nodes import BitAnd
        trail = Trail()
        p, q = Var(), Var()
        z3_var_for(p, z3.BoolSort(), trail)
        z3_var_for(q, z3.BoolSort(), trail)
        result = clausal_to_z3(BitAnd(left=p, right=q), trail)
        assert result.sort() == z3.BoolSort()

    def test_bitor(self):
        # nv
        from clausal.pythonic_ast.nodes import BitOr
        trail = Trail()
        p, q = Var(), Var()
        z3_var_for(p, z3.BoolSort(), trail)
        z3_var_for(q, z3.BoolSort(), trail)
        result = clausal_to_z3(BitOr(left=p, right=q), trail)
        assert result.sort() == z3.BoolSort()

    def test_bitxor(self):
        # nv
        from clausal.pythonic_ast.nodes import BitXor
        trail = Trail()
        p, q = Var(), Var()
        z3_var_for(p, z3.BoolSort(), trail)
        z3_var_for(q, z3.BoolSort(), trail)
        result = clausal_to_z3(BitXor(left=p, right=q), trail)
        assert result.sort() == z3.BoolSort()

    def test_invert(self):
        # nv
        from clausal.pythonic_ast.nodes import Invert
        trail = Trail()
        p = Var()
        z3_var_for(p, z3.BoolSort(), trail)
        result = clausal_to_z3(Invert(operand=p), trail)
        assert result.sort() == z3.BoolSort()

    def test_unknown_type_raises(self):
        # nv
        trail = Trail()

        class _Bogus:
            pass

        with pytest.raises(TypeError, match="Cannot translate"):
            clausal_to_z3(_Bogus(), trail)


# ══════════════════════════════════════════════════════════════════════════════
# Value conversion (Z3 → Python)
# ══════════════════════════════════════════════════════════════════════════════

class TestZ3ToPython:
    def test_int_value(self):
        # nv
        assert z3_to_python(z3.IntVal(42)) == 42
        assert isinstance(z3_to_python(z3.IntVal(42)), int)

    def test_int_zero(self):
        # nv
        assert z3_to_python(z3.IntVal(0)) == 0

    def test_int_negative(self):
        # nv
        assert z3_to_python(z3.IntVal(-7)) == -7

    def test_large_int(self):
        # nv
        big = 10 ** 100
        assert z3_to_python(z3.IntVal(big)) == big

    def test_bool_true(self):
        # nv
        assert z3_to_python(z3.BoolVal(True)) == 1

    def test_bool_false(self):
        # nv
        assert z3_to_python(z3.BoolVal(False)) == 0

    def test_bool_result_is_int(self):
        """Clausal uses 0/1 for booleans, not Python True/False."""
        # nv
        result = z3_to_python(z3.BoolVal(True))
        assert result == 1
        assert type(result) is int

    def test_rational_exact(self):
        # nv
        result = z3_to_python(z3.RealVal("3/7"))
        assert result == Fraction(3, 7)
        assert isinstance(result, Fraction)

    def test_rational_whole(self):
        # nv
        result = z3_to_python(z3.RealVal("5"))
        # May come back as Fraction(5, 1) or int depending on Z3
        assert result == 5

    def test_rational_half(self):
        # nv
        result = z3_to_python(z3.RealVal("1/2"))
        assert result == Fraction(1, 2)

    def test_model_int_value(self):
        """Value extracted from a real model."""
        # nv
        s = z3.Solver()
        x = z3.Int("x")
        s.add(x == 99)
        assert s.check() == z3.sat
        val = z3_to_python(s.model().eval(x, model_completion=True))
        assert val == 99


# ══════════════════════════════════════════════════════════════════════════════
# Trail ↔ Solver synchronization
# ══════════════════════════════════════════════════════════════════════════════

class TestTrailSync:
    def test_z3_push_increments_scopes(self):
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        assert state.solver.num_scopes() == 0

        mark = trail.mark()
        z3_push(trail)
        assert state.solver.num_scopes() == 1

        trail.undo(mark)
        assert state.solver.num_scopes() == 0

    def test_z3_push_pop_retracts_constraint(self):
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        x = z3.Int("x")
        state.solver.add(x > 0)

        mark = trail.mark()
        z3_push(trail)
        state.solver.add(x < 0)  # contradicts x > 0

        assert state.solver.check() == z3.unsat

        trail.undo(mark)
        assert state.solver.num_scopes() == 0
        assert state.solver.check() == z3.sat  # x < 0 retracted

    def test_nested_push_pop(self):
        # nv
        trail = Trail()
        state = get_z3_state(trail)

        mark1 = trail.mark()
        z3_push(trail)
        state.solver.add(z3.Int("x") > 0)

        mark2 = trail.mark()
        z3_push(trail)
        state.solver.add(z3.Int("x") > 10)

        assert state.solver.num_scopes() == 2

        trail.undo(mark2)
        assert state.solver.num_scopes() == 1

        trail.undo(mark1)
        assert state.solver.num_scopes() == 0

    def test_push_interleaved_with_clausal_bindings(self):
        """Trail undo undoes both Z3 scope and Clausal variable bindings."""
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        x = Var()

        mark = trail.mark()
        z3_push(trail)
        state.solver.add(z3.Int("z") > 0)
        unify(x, 42, trail)

        assert deref(x) == 42
        assert state.solver.num_scopes() == 1

        trail.undo(mark)

        assert is_var(deref(x))           # Clausal binding undone
        assert state.solver.num_scopes() == 0  # Z3 scope popped

    def test_z3_add_lazy(self):
        """z3_add does not check consistency — always returns True."""
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        x = z3.Int("x")
        result = z3_add(x > 100, trail)
        assert result is True
        # Contradictory: add x < 0 without checking
        result2 = z3_add(x < 0, trail)
        assert result2 is True
        # Only checked when we explicitly call check()
        assert state.solver.check() == z3.unsat

    def test_multiple_trail_pops(self):
        """Pop correctly handles multiple levels in one trail.undo()."""
        # nv
        trail = Trail()
        state = get_z3_state(trail)

        mark = trail.mark()
        z3_push(trail)
        z3_push(trail)
        z3_push(trail)
        assert state.solver.num_scopes() == 3

        trail.undo(mark)
        assert state.solver.num_scopes() == 0

    def test_push_then_constraint_then_backtrack_and_re_add(self):
        """After backtrack, new constraints can be added in clean scope."""
        # nv
        trail = Trail()
        state = get_z3_state(trail)
        x = z3.Int("x")
        state.solver.add(x >= 0)

        mark = trail.mark()
        z3_push(trail)
        state.solver.add(x > 100)
        assert state.solver.check() == z3.sat

        trail.undo(mark)

        # Now add a different constraint
        z3_push(trail)
        state.solver.add(x == 5)
        assert state.solver.check() == z3.sat
        m = state.solver.model()
        assert z3_to_python(m.eval(x, model_completion=True)) == 5


# ══════════════════════════════════════════════════════════════════════════════
# Import guard
# ══════════════════════════════════════════════════════════════════════════════

class TestImportGuard:
    def test_z3_state_requires_z3(self, monkeypatch):
        """If z3 is not available, Z3State raises ImportError."""
        # nv
        import clausal.logic.clpz3 as m
        monkeypatch.setattr(m, "_HAS_Z3", False)
        with pytest.raises(ImportError, match="pip install z3-solver"):
            m.Z3State()
