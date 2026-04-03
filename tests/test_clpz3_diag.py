"""Tests for Z3 diagnostics — Phase 8.

Covers: named constraints, unsat cores, model inspection, entailment,
        simplification, assertions dump, solver config, statistics.
"""

from __future__ import annotations
import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var
from clausal.logic.clpz3 import (
    in_z3, z3_eq, z3_le, z3_ge, z3_check, label_z3,
    z3_named, z3_unsat_core, z3_minimal_unsat_core,
    z3_is_sat, z3_disentailed, z3_model, z3_simplify,
    z3_assertions, z3_stats, z3_set_option, z3_set_logic,
    entailed_z3, get_z3_state,
)
from clausal.pythonic_ast.nodes import ArithEq, Lt, LtE, Gt, GtE, Add


# ══════════════════════════════════════════════════════════════════════════════
# Named Constraints & Unsat Core
# ══════════════════════════════════════════════════════════════════════════════

class TestNamedConstraints:
    def test_named_post_succeeds(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert z3_named(Gt(left=x, right=5), "x_big", trail)

    def test_named_and_unsat_core(self):
        """x > 5 AND x < 3 is unsat — core includes both."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), "x_big", trail)
        z3_named(Lt(left=x, right=3), "x_small", trail)
        core = Var()
        assert z3_unsat_core(core, trail)
        names = deref(core)
        assert "x_big" in names
        assert "x_small" in names

    def test_satisfiable_no_core(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), "x_big", trail)
        core = Var()
        assert not z3_unsat_core(core, trail)

    def test_named_backtrack(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)

        mark = trail.mark()
        z3_named(Gt(left=x, right=5), "x_big", trail)
        trail.undo(mark)

        state = get_z3_state(trail)
        named = getattr(state, '_named_constraints', {})
        assert "x_big" not in named

    def test_three_constraints_two_conflict(self):
        """Three named constraints, only two conflict."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), "a", trail)
        z3_named(Lt(left=x, right=3), "b", trail)
        z3_named(GtE(left=x, right=1), "c", trail)  # always true (domain)
        core = Var()
        assert z3_unsat_core(core, trail)
        names = deref(core)
        assert "a" in names
        assert "b" in names

    def test_no_named_unsat(self):
        """Unsat with no named constraints returns empty core."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        z3_eq(x, 10, trail)  # contradicts domain
        core = Var()
        assert z3_unsat_core(core, trail)
        assert deref(core) == []


class TestMinimalUnsatCore:
    def test_minimal_core_strips_redundant(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), "a", trail)
        z3_named(Lt(left=x, right=3), "b", trail)
        z3_named(GtE(left=x, right=1), "c", trail)  # redundant
        core = Var()
        assert z3_minimal_unsat_core(core, trail)
        names = deref(core)
        assert "a" in names
        assert "b" in names
        # "c" should NOT be in minimal core
        assert "c" not in names

    def test_satisfiable_returns_false(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), "a", trail)
        core = Var()
        assert not z3_minimal_unsat_core(core, trail)


# ══════════════════════════════════════════════════════════════════════════════
# Satisfiability Check
# ══════════════════════════════════════════════════════════════════════════════

class TestIsSat:
    def test_sat(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        r = Var()
        assert z3_is_sat(r, trail)
        assert deref(r) == "sat"

    def test_unsat(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        z3_eq(x, 10, trail)
        r = Var()
        assert z3_is_sat(r, trail)
        assert deref(r) == "unsat"


# ══════════════════════════════════════════════════════════════════════════════
# Entailment & Disentailment
# ══════════════════════════════════════════════════════════════════════════════

class TestEntailment:
    def test_entailed_by_bounds(self):
        trail = Trail()
        x = Var()
        in_z3(x, 5, 10, trail)
        assert entailed_z3(GtE(left=x, right=5), trail)
        assert entailed_z3(LtE(left=x, right=10), trail)

    def test_not_entailed(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert not entailed_z3(GtE(left=x, right=5), trail)

    def test_entailed_after_equality(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_eq(x, y, trail)
        z3_eq(x, 5, trail)
        assert entailed_z3(ArithEq(left=y, right=5), trail)


class TestDisentailed:
    def test_disentailed(self):
        trail = Trail()
        x = Var()
        in_z3(x, 5, 10, trail)
        assert z3_disentailed(Lt(left=x, right=5), trail)

    def test_not_disentailed(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert not z3_disentailed(Lt(left=x, right=5), trail)


# ══════════════════════════════════════════════════════════════════════════════
# Model Inspection
# ══════════════════════════════════════════════════════════════════════════════

class TestModel:
    def test_model_without_binding(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 3, trail)
        vals = Var()
        assert z3_model([x], vals, trail)
        assert is_var(deref(x))  # x still unbound
        model_data = deref(vals)
        assert len(model_data) == 1
        assert model_data[0][1] in [1, 2, 3]

    def test_model_constrained(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_eq(x, 7, trail)
        vals = Var()
        assert z3_model([x], vals, trail)
        assert deref(vals)[0][1] == 7

    def test_model_unsat_fails(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        z3_eq(x, 10, trail)
        vals = Var()
        assert not z3_model([x], vals, trail)

    def test_model_multiple_vars(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_eq(x, 3, trail)
        z3_eq(y, 7, trail)
        vals = Var()
        assert z3_model([x, y], vals, trail)
        model_data = deref(vals)
        assert len(model_data) == 2
        values = {pair[1] for pair in model_data}
        assert values == {3, 7}


# ══════════════════════════════════════════════════════════════════════════════
# Simplification
# ══════════════════════════════════════════════════════════════════════════════

class TestSimplify:
    def test_simplify_constant(self):
        trail = Trail()
        r = Var()
        assert z3_simplify(Add(left=2, right=3), r, trail)
        assert deref(r) == 5

    def test_simplify_tautology(self):
        trail = Trail()
        r = Var()
        assert z3_simplify(ArithEq(left=5, right=5), r, trail)
        # z3_to_python may return True or 1 (bool is subclass of int)
        assert deref(r) in (True, 1)

    def test_simplify_with_variable(self):
        """Simplify expression containing a variable returns string form."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        r = Var()
        assert z3_simplify(Add(left=x, right=0), r, trail)
        result = deref(r)
        # Z3 simplifies x + 0 → x; result is either the int (if var resolved)
        # or a string representation
        assert result is not None


# ══════════════════════════════════════════════════════════════════════════════
# Assertions Dump
# ══════════════════════════════════════════════════════════════════════════════

class TestAssertions:
    def test_dump_assertions(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        a = Var()
        assert z3_assertions(a, trail)
        a_list = deref(a)
        assert len(a_list) >= 2  # at least x >= 1 and x <= 10
        assert all(isinstance(s, str) for s in a_list)

    def test_empty_assertions(self):
        trail = Trail()
        _ = get_z3_state(trail)  # init state
        a = Var()
        assert z3_assertions(a, trail)
        assert deref(a) == []


# ══════════════════════════════════════════════════════════════════════════════
# Solver Statistics
# ══════════════════════════════════════════════════════════════════════════════

class TestStats:
    def test_stats_returns_pairs(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        s = Var()
        assert z3_stats(s, trail)
        stats = deref(s)
        assert isinstance(stats, list)
        # Stats should contain at least some entries after check()
        # Each entry is [key, value]
        for pair in stats:
            assert len(pair) == 2
            assert isinstance(pair[0], str)


# ══════════════════════════════════════════════════════════════════════════════
# Solver Configuration
# ══════════════════════════════════════════════════════════════════════════════

class TestSolverConfig:
    def test_set_timeout(self):
        trail = Trail()
        assert z3_set_option("timeout", 5000, trail)

    def test_set_logic_qf_lia(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert z3_set_logic("QF_LIA", trail)
        assert z3_check(trail)

    def test_set_logic_preserves_constraints(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_eq(x, 5, trail)
        z3_set_logic("QF_LIA", trail)
        sols = []
        for _ in label_z3([x], trail):
            sols.append(deref(x))
        assert sols == [5]

    def test_set_logic_detects_unsat(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        z3_eq(x, 10, trail)
        z3_set_logic("QF_LIA", trail)
        assert not z3_check(trail)


# ══════════════════════════════════════════════════════════════════════════════
# Integration: Debug workflow
# ══════════════════════════════════════════════════════════════════════════════

class TestDebugWorkflow:
    def test_find_conflict_with_unsat_core(self):
        """Full workflow: post named constraints, find conflict."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 10, trail)
        z3_named(Gt(left=x, right=8), "x_high", trail)
        z3_named(Lt(left=y, right=3), "y_low", trail)
        z3_named(ArithEq(left=x, right=y), "x_eq_y", trail)

        # x > 8 AND y < 3 AND x == y is unsat
        core = Var()
        assert z3_unsat_core(core, trail)
        names = deref(core)
        # All three participate in the conflict
        assert len(names) >= 2

    def test_model_then_entailment(self):
        """Inspect model, then verify entailment."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_eq(x, 5, trail)

        # Model shows x = 5
        vals = Var()
        assert z3_model([x], vals, trail)
        assert deref(vals)[0][1] == 5

        # x == 5 is entailed
        assert entailed_z3(ArithEq(left=x, right=5), trail)

        # x > 5 is disentailed
        assert z3_disentailed(Gt(left=x, right=5), trail)
