"""Tests for PySAT Boolean satisfiability integration.

Covers: variable mapping, activation-literal backtracking, CNF translation
(Tseitin), constraint blocks, labeling, cardinality, and nested search.
"""

from __future__ import annotations

import gc
import pytest

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.clpsat import (
    SATState, SATVarInfo, SAT_KEY,
    get_sat_state, _get_existing_sat_state, sat_var_for, _fresh_sat_var,
    sat_push, sat_add_clause, sat_check,
    sat_constraint_block, label_sat, sat_count,
    clausal_to_cnf, _is_simple_clause, _collect_disjuncts,
    sat_at_most, sat_at_least, sat_exactly,
    _sat_states,
)
from clausal.pythonic_ast.nodes import (
    BitAnd, BitOr, BitXor, Invert,
    And, Or, Not,
    ArithEq, ArithNeq,
)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: Core Infrastructure
# ═══════════════════════════════════════════════════════════════════════════

class TestVariableMapping:

    def test_var_mapping_bidirectional(self):
        # nv
        trail = Trail()
        x = Var()
        state = get_sat_state(trail, 'cadical195')
        sat_x = sat_var_for(x, trail)
        assert sat_x > 0
        assert state.var_map[id(x)] == sat_x
        assert state.rev_map[sat_x] is x

    def test_var_mapping_idempotent(self):
        # nv
        trail = Trail()
        x = Var()
        v1 = sat_var_for(x, trail)
        v2 = sat_var_for(x, trail)
        assert v1 == v2

    def test_multiple_vars_distinct(self):
        # nv
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        vx = sat_var_for(x, trail)
        vy = sat_var_for(y, trail)
        vz = sat_var_for(z, trail)
        assert len({vx, vy, vz}) == 3

    def test_ground_var_raises(self):
        # nv
        trail = Trail()
        x = Var()
        unify(x, 1, trail)
        with pytest.raises(TypeError, match="expected unbound"):
            sat_var_for(x, trail)

    def test_var_attribute_stored(self):
        # nv
        trail = Trail()
        x = Var()
        sat_x = sat_var_for(x, trail)
        info = get_sat_state(trail).var_map.get(id(x))
        assert info == sat_x


class TestSATState:

    def test_state_created_on_demand(self):
        # nv
        trail = Trail()
        state = get_sat_state(trail, 'cadical195')
        assert state.solver_name == 'cadical195'
        assert state._counter == 0

    def test_state_reused(self):
        # nv
        trail = Trail()
        s1 = get_sat_state(trail, 'cadical195')
        s2 = get_sat_state(trail, 'cadical195')
        assert s1 is s2

    def test_solver_mismatch_raises(self):
        # nv
        trail = Trail()
        get_sat_state(trail, 'cadical195')
        with pytest.raises(ValueError, match="mismatch"):
            get_sat_state(trail, 'glucose')

    def test_unknown_solver_raises(self):
        # nv
        trail = Trail()
        with pytest.raises(ValueError, match="Unknown SAT solver"):
            get_sat_state(trail, 'nonexistent_solver')

    def test_solver_cleanup_on_gc(self):
        # nv
        trail = Trail()
        get_sat_state(trail, 'cadical195')
        tid = id(trail)
        assert tid in _sat_states
        del trail
        gc.collect()
        assert tid not in _sat_states

    def test_solver_aliases(self):
        """Common aliases resolve correctly."""
        # nv
        trail1 = Trail()
        s1 = get_sat_state(trail1, 'cadical')
        assert s1.solver_name == 'cadical195'

        trail2 = Trail()
        s2 = get_sat_state(trail2, 'minisat')
        assert s2.solver_name == 'm22'


class TestBasicClauses:

    def test_unit_clause_sat(self):
        # nv
        trail = Trail()
        x = Var()
        v = sat_var_for(x, trail)
        sat_add_clause([v], trail)
        assert sat_check(trail)

    def test_contradictory_clauses_unsat(self):
        # nv
        trail = Trail()
        x = Var()
        v = sat_var_for(x, trail)
        sat_add_clause([v], trail)
        sat_add_clause([-v], trail)
        assert not sat_check(trail)

    def test_binary_clause(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        vx, vy = sat_var_for(x, trail), sat_var_for(y, trail)
        sat_add_clause([vx, vy], trail)  # x | y
        assert sat_check(trail)


class TestActivationLiterals:

    def test_backtracking_retracts_clauses(self):
        """Clauses added inside a scope become dormant after backtrack."""
        # nv
        trail = Trail()
        x = Var()
        v = sat_var_for(x, trail)

        mark = trail.mark()
        sat_push(trail)
        sat_add_clause([v], trail)    # x (guarded)
        sat_add_clause([-v], trail)   # ~x (guarded)
        assert not sat_check(trail)   # UNSAT

        trail.undo(mark)              # backtrack — activation lit removed
        assert sat_check(trail)       # SAT again

    def test_nested_backtracking(self):
        """Inner scope retracted independently of outer."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        vx = sat_var_for(x, trail)
        vy = sat_var_for(y, trail)

        mark_outer = trail.mark()
        sat_push(trail)
        sat_add_clause([vx], trail)  # x (outer scope)

        mark_inner = trail.mark()
        sat_push(trail)
        sat_add_clause([-vx], trail)  # ~x (inner scope) — contradicts
        assert not sat_check(trail)

        trail.undo(mark_inner)  # retract inner
        assert sat_check(trail)  # outer x still active

        trail.undo(mark_outer)  # retract outer
        assert sat_check(trail)  # everything dormant

    def test_three_levels_of_nesting(self):
        # nv
        trail = Trail()
        x = Var()
        v = sat_var_for(x, trail)

        mark1 = trail.mark()
        sat_push(trail)
        sat_add_clause([v, v], trail)  # tautology in scope 1

        mark2 = trail.mark()
        sat_push(trail)
        sat_add_clause([v], trail)  # x in scope 2

        mark3 = trail.mark()
        sat_push(trail)
        sat_add_clause([-v], trail)  # ~x in scope 3 — contradicts scope 2
        assert not sat_check(trail)

        trail.undo(mark3)
        assert sat_check(trail)  # scope 2: x still forced

        trail.undo(mark2)
        assert sat_check(trail)  # only scope 1

        trail.undo(mark1)
        assert sat_check(trail)  # empty


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: CNF Translation & Labeling
# ═══════════════════════════════════════════════════════════════════════════

class TestSimpleClauseDetection:

    def test_var_is_simple(self):
        # nv
        assert _is_simple_clause(Var())

    def test_or_of_vars_is_simple(self):
        # nv
        x, y = Var(), Var()
        assert _is_simple_clause(BitOr(left=x, right=y))

    def test_negated_var_is_simple(self):
        # nv
        x = Var()
        assert _is_simple_clause(Invert(operand=x))

    def test_or_with_negation_is_simple(self):
        # nv
        x, y = Var(), Var()
        assert _is_simple_clause(BitOr(left=x, right=Invert(operand=y)))

    def test_and_is_not_simple(self):
        # nv
        x, y = Var(), Var()
        assert not _is_simple_clause(BitAnd(left=x, right=y))

    def test_nested_or_is_simple(self):
        # nv
        x, y, z = Var(), Var(), Var()
        assert _is_simple_clause(BitOr(left=BitOr(left=x, right=y), right=z))

    def test_not_is_literal(self):
        """Not(X) (from 'not X' in .clausal) is a literal like Invert(X)."""
        # nv
        x = Var()
        assert _is_simple_clause(Not(operand=x))

    def test_or_node_is_simple(self):
        """Or(X, Y) (from 'X or Y' in .clausal) is a simple clause like BitOr."""
        # nv
        x, y = Var(), Var()
        assert _is_simple_clause(Or(left=x, right=y))

    def test_or_with_not_is_simple(self):
        """Or(Not(X), Y) is a simple clause."""
        # nv
        x, y = Var(), Var()
        assert _is_simple_clause(Or(left=Not(operand=x), right=y))


class TestTseitinTransformation:

    def test_and(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        root, aux = clausal_to_cnf(BitAnd(left=x, right=y), trail)
        assert len(aux) == 3  # t <-> (a & b)

    def test_or(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        root, aux = clausal_to_cnf(BitOr(left=x, right=y), trail)
        assert len(aux) == 3  # t <-> (a | b)

    def test_xor(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        root, aux = clausal_to_cnf(BitXor(left=x, right=y), trail)
        assert len(aux) == 4

    def test_eq(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        root, aux = clausal_to_cnf(ArithEq(left=x, right=y), trail)
        assert len(aux) == 4  # XNOR

    def test_neq(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        root, aux = clausal_to_cnf(ArithNeq(left=x, right=y), trail)
        assert len(aux) == 4  # XOR

    def test_not(self):
        # nv
        trail = Trail()
        x = Var()
        root, aux = clausal_to_cnf(Invert(operand=x), trail)
        assert len(aux) == 0  # just negation, no aux
        vx = sat_var_for(x, trail)
        assert root == -vx


# TestConstraintBlock: problem-solving tests moved to pysat_boolean.seam

class TestLabelingInfrastructure:
    """Infrastructure tests for labeling — generator protocol, binding semantics."""

    def test_bindings_undone_after_labeling(self):
        # nv
        trail = Trail()
        x = Var()
        vx = sat_var_for(x, trail)
        sat_push(trail)
        sat_add_clause([vx, -vx], trail)
        for _ in label_sat([x], trail):
            assert not is_var(deref(x))  # bound during iteration
        assert is_var(deref(x))  # unbound after

    def test_ground_vars_skipped(self):
        """Ground values in the label list are accepted."""
        # nv
        trail = Trail()
        x = Var()
        sat_constraint_block((x,), 'cadical195', trail)  # x must be 1
        sols = []
        for _ in label_sat([x, 1], trail):
            sols.append(deref(x))
        assert sols == [1]

    def test_nested_search(self):
        """Inner labeling does not corrupt outer state."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block((
            BitOr(left=x, right=y),
        ), 'cadical195', trail)

        outer = []
        for _ in label_sat([x], trail):
            xv = deref(x)
            inner_count = sum(1 for _ in label_sat([y], trail))
            outer.append((xv, inner_count))
        # x=1: y can be 0 or 1 (2 solutions)
        # x=0: y must be 1 (1 solution)
        assert sorted(outer) == [(0, 1), (1, 2)]


# TestCardinality: problem-solving tests moved to pysat_boolean.seam

# ═══════════════════════════════════════════════════════════════════════════
# Cardinality Edge Cases (infrastructure)
# ═══════════════════════════════════════════════════════════════════════════

# TestCardinality problem-solving removed (in pysat_boolean.seam)

# TestCardinality and TestIntegration problem-solving tests moved to
# pysat_boolean.seam. Infrastructure tests kept below.

class TestBacktrackingStress:

    def test_deep_backtracking_stress(self):
        """Many push/undo cycles don't break the solver."""
        # nv
        trail = Trail()
        x = Var()
        v = sat_var_for(x, trail)

        for _ in range(50):
            mark = trail.mark()
            sat_push(trail)
            sat_add_clause([v], trail)
            sat_add_clause([-v], trail)
            assert not sat_check(trail)
            trail.undo(mark)
            assert sat_check(trail)

    def test_cardinality_backtracks(self):
        """Cardinality constraints retracted on backtrack."""
        # nv
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        for v in [x, y, z]:
            sat_var_for(v, trail)

        mark = trail.mark()
        sat_exactly([x, y, z], 0, trail)
        count1 = sum(1 for _ in label_sat([x, y, z], trail))
        assert count1 == 1

        trail.undo(mark)
        count2 = sum(1 for _ in label_sat([x, y, z], trail))
        assert count2 == 8


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestLabelingRepeated:
    """label_sat / sat_count called multiple times without backtracking."""

    def test_sat_count_twice(self):
        """sat_count called twice gives same result (activation lit cleaned up)."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block((
            BitOr(left=x, right=y),
        ), 'cadical195', trail)
        assert sat_count([x, y], trail) == 3
        assert sat_count([x, y], trail) == 3  # must be the same

    def test_label_sat_twice(self):
        """label_sat called twice without backtracking enumerates fully both times."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block((BitXor(left=x, right=y),), 'cadical195', trail)

        sols1 = []
        for _ in label_sat([x, y], trail):
            sols1.append((deref(x), deref(y)))

        sols2 = []
        for _ in label_sat([x, y], trail):
            sols2.append((deref(x), deref(y)))

        assert sorted(sols1) == sorted(sols2) == [(0, 1), (1, 0)]

    def test_label_early_exit(self):
        """Breaking after first solution: binding persists, future labels work."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block((
            BitOr(left=x, right=y),
        ), 'cadical195', trail)

        # Take only first solution
        gen = label_sat([x, y], trail)
        next(gen)
        xv, yv = deref(x), deref(y)
        assert isinstance(xv, int) and isinstance(yv, int)
        gen.close()  # explicitly close the generator

        # After closing, vars are still bound (Prolog cut semantics)
        # But we can start a fresh label_sat (activation lit cleaned up)
        mark = trail.mark()
        trail.undo(mark)  # unbind manually if needed for next test

    def test_label_early_exit_then_relabel(self):
        """After breaking + undoing, full enumeration still works."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block((BitXor(left=x, right=y),), 'cadical195', trail)

        mark = trail.mark()
        gen = label_sat([x, y], trail)
        next(gen)  # get first solution
        gen.close()
        trail.undo(mark)

        # Full enumeration should still work
        sols = []
        for _ in label_sat([x, y], trail):
            sols.append((deref(x), deref(y)))
        assert sorted(sols) == [(0, 1), (1, 0)]


class TestConstraintBlockEdgeCases:

    def test_empty_constraint_block(self):
        """Empty constraint tuple is trivially SAT."""
        # nv
        trail = Trail()
        assert sat_constraint_block((), 'cadical195', trail)
        assert sat_check(trail)

    def test_single_element_tuple(self):
        """Single-element tuple: not a tuple in Python unless trailing comma."""
        # nv
        trail = Trail()
        x = Var()
        # (x,) is a 1-tuple
        sat_constraint_block((x,), 'cadical195', trail)
        sols = []
        for _ in label_sat([x], trail):
            sols.append(deref(x))
        assert sols == [1]  # bare var forces True

    def test_bare_variable_forces_true(self):
        """A bare Var in a constraint block is a unit clause (must be 1)."""
        # nv
        trail = Trail()
        x = Var()
        sat_constraint_block((x,), 'cadical195', trail)
        assert sat_check(trail)
        for _ in label_sat([x], trail):
            assert deref(x) == 1

    def test_negated_variable_forces_false(self):
        """~X in a constraint block forces X=0."""
        # nv
        trail = Trail()
        x = Var()
        sat_constraint_block((Invert(operand=x),), 'cadical195', trail)
        for _ in label_sat([x], trail):
            assert deref(x) == 0

    def test_deeply_nested_expression(self):
        """(A & B) | (C ^ D) — nested AND/OR/XOR via Tseitin."""
        # nv
        trail = Trail()
        a, b, c, d = Var(), Var(), Var(), Var()
        expr = BitOr(
            left=BitAnd(left=a, right=b),
            right=BitXor(left=c, right=d),
        )
        sat_constraint_block((expr,), 'cadical195', trail)
        sols = []
        for _ in label_sat([a, b, c, d], trail):
            av, bv, cv, dv = deref(a), deref(b), deref(c), deref(d)
            # Verify: (a & b) | (c ^ d) must be True
            assert (av and bv) or (cv ^ dv)
            sols.append((av, bv, cv, dv))
        # 16 total assignments, minus those where (a&b)=0 and (c^d)=0
        # (c^d)=0 when c==d: (0,0) and (1,1) — 2 cases
        # (a&b)=0: 3 cases (00,01,10)
        # Excluded: 3 * 2 = 6
        assert len(sols) == 10

    def test_constraint_block_with_list(self):
        """Constraint block accepts a list as well as a tuple."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block([
            BitOr(left=x, right=y),
            BitOr(left=Invert(operand=x), right=Invert(operand=y)),
        ], 'cadical195', trail)
        # x|y AND ~x|~y  →  XOR
        sols = []
        for _ in label_sat([x, y], trail):
            sols.append((deref(x), deref(y)))
        assert sorted(sols) == [(0, 1), (1, 0)]

    def test_or_not_nodes_fast_path(self):
        """Or/Not nodes (from 'or'/'not' keywords) use the fast path."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        # Or(Not(X), Y) is equivalent to ~X | Y → (X implies Y)
        sat_constraint_block((
            Or(left=Not(operand=x), right=y),
            x,  # force X=1, so Y must be 1
        ), 'cadical195', trail)
        sols = []
        for _ in label_sat([x, y], trail):
            sols.append((deref(x), deref(y)))
        assert sols == [(1, 1)]

    def test_top_level_and_flattened(self):
        """X & Y in constraint block is flattened to two unit clauses."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block((
            BitAnd(left=x, right=y),
        ), 'cadical195', trail)
        sols = []
        for _ in label_sat([x, y], trail):
            sols.append((deref(x), deref(y)))
        assert sols == [(1, 1)]

    def test_nested_and_flattened(self):
        """(A & B) & C is flattened to three unit clauses."""
        # nv
        trail = Trail()
        a, b, c = Var(), Var(), Var()
        sat_constraint_block((
            BitAnd(left=BitAnd(left=a, right=b), right=c),
        ), 'cadical195', trail)
        sols = []
        for _ in label_sat([a, b, c], trail):
            sols.append((deref(a), deref(b), deref(c)))
        assert sols == [(1, 1, 1)]

    def test_and_of_clauses_flattened(self):
        """(X | Y) & (~X | Y) is flattened to two simple clauses."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        expr = BitAnd(
            left=BitOr(left=x, right=y),
            right=BitOr(left=Invert(operand=x), right=y),
        )
        sat_constraint_block((expr,), 'cadical195', trail)
        # Equivalent to: X|Y AND ~X|Y → Y must be True
        sols = []
        for _ in label_sat([x, y], trail):
            sols.append((deref(x), deref(y)))
        assert all(s[1] == 1 for s in sols)
        assert len(sols) == 2

    def test_and_node_flattened(self):
        """And(X, Y) (from 'X and Y' in .clausal) is also flattened."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block((And(left=x, right=y),), 'cadical195', trail)
        sols = []
        for _ in label_sat([x, y], trail):
            sols.append((deref(x), deref(y)))
        assert sols == [(1, 1)]


class TestCardinalityEdgeCases:

    def test_empty_list_at_most(self):
        """at_most([], k) is trivially true for any k >= 0."""
        # nv
        trail = Trail()
        get_sat_state(trail)  # ensure state
        assert sat_at_most([], 0, trail)
        assert sat_at_most([], 5, trail)

    def test_empty_list_at_least_zero(self):
        """at_least([], 0) is trivially true."""
        # nv
        trail = Trail()
        get_sat_state(trail)
        assert sat_at_least([], 0, trail)

    def test_empty_list_at_least_one(self):
        """at_least([], 1) fails — no vars to satisfy."""
        # nv
        trail = Trail()
        get_sat_state(trail)
        assert not sat_at_least([], 1, trail)

    def test_empty_list_exactly_zero(self):
        """exactly([], 0) succeeds."""
        # nv
        trail = Trail()
        get_sat_state(trail)
        assert sat_exactly([], 0, trail)

    def test_empty_list_exactly_one(self):
        """exactly([], 1) fails."""
        # nv
        trail = Trail()
        get_sat_state(trail)
        assert not sat_exactly([], 1, trail)

    def test_all_ground_true_at_most(self):
        """at_most([1, 1, 1], 2) fails — 3 ground Trues exceed bound."""
        # nv
        trail = Trail()
        get_sat_state(trail)
        assert not sat_at_most([1, 1, 1], 2, trail)

    def test_all_ground_false_at_least(self):
        """at_least([0, 0, 0], 1) fails — no Trues."""
        # nv
        trail = Trail()
        get_sat_state(trail)
        assert not sat_at_least([0, 0, 0], 1, trail)

    def test_mixed_ground_and_vars(self):
        """at_most([1, X, Y], 2): X and Y can have at most 1 True."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        for v in [x, y]:
            sat_var_for(v, trail)
        sat_at_most([1, x, y], 2, trail)
        sols = []
        for _ in label_sat([x, y], trail):
            sols.append((deref(x), deref(y)))
        # at_most 1 of {x,y} can be true (since ground 1 consumes one slot)
        assert sorted(sols) == [(0, 0), (0, 1), (1, 0)]

    def test_at_most_exceeds_var_count(self):
        """at_most([X, Y], 5) is trivially true (bound exceeds var count)."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        for v in [x, y]:
            sat_var_for(v, trail)
        sat_at_most([x, y], 5, trail)
        count = sum(1 for _ in label_sat([x, y], trail))
        assert count == 4  # all 4 combinations


class TestErrorPaths:

    def test_label_unregistered_var(self):
        """label_sat with unregistered variable raises."""
        # nv
        trail = Trail()
        x = Var()
        get_sat_state(trail)
        with pytest.raises(ValueError, match="not registered"):
            list(label_sat([x], trail))

    def test_label_bad_ground_value(self):
        """label_sat with ground value other than 0/1 raises."""
        # nv
        trail = Trail()
        x = Var()
        sat_var_for(x, trail)
        with pytest.raises(TypeError, match="expected 0/1"):
            list(label_sat([x, 42], trail))

    def test_tseitin_unsupported_node(self):
        """Tseitin transform on unsupported node raises TypeError."""
        # nv
        from clausal.pythonic_ast.nodes import Add
        trail = Trail()
        x, y = Var(), Var()
        with pytest.raises(TypeError, match="Cannot translate"):
            clausal_to_cnf(Add(left=x, right=y), trail)

    def test_expr_to_literal_bad_int(self):
        """_expr_to_literal with int other than 0/1 raises."""
        # nv
        from clausal.logic.clpsat import _expr_to_literal
        trail = Trail()
        get_sat_state(trail)
        with pytest.raises(TypeError, match="Cannot translate"):
            _expr_to_literal(42, trail)
