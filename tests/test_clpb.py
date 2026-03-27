"""Tests for CLP(B) Boolean constraint solver.

Tests BDD operations, sat/taut/sat_count/labeling, attribute hook,
trail safety, and compiled integration via .clausal fixtures.
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var, put_attr, get_attr
from clausal.logic.clpb import (
    B_KEY, HASH_KEY,
    BDD_TRUE, BDD_FALSE, BDDNode, BoolState,
    BoolEq, BoolImpl,
    enumerate_var, make_node, apply, negate, restrict,
    _expr_to_bdd, _collect_bool_var_objects, _collect_bdd_var_ids,
    _propagate_forced,
    sat, taut, sat_count, bool_labeling,
)
from clausal.pythonic_ast.nodes import BitAnd, BitOr, BitXor, Invert


# ── Helpers ──────────────────────────────────────────────────────────────────

def fresh_trail() -> Trail:
    return Trail()


# ══════════════════════════════════════════════════════════════════════════════
# BDD Node
# ══════════════════════════════════════════════════════════════════════════════


class TestBDDNode:
    def test_construction(self):
        node = BDDNode(0, BDD_TRUE, BDD_FALSE)
        assert node.var_id == 0
        assert node.high is BDD_TRUE
        assert node.low is BDD_FALSE

    def test_identity_equality(self):
        n1 = BDDNode(0, BDD_TRUE, BDD_FALSE)
        n2 = BDDNode(0, BDD_TRUE, BDD_FALSE)
        assert n1 != n2  # identity-based
        assert n1 == n1

    def test_hashable(self):
        node = BDDNode(0, BDD_TRUE, BDD_FALSE)
        d = {node: "ok"}
        assert d[node] == "ok"

    def test_repr(self):
        node = BDDNode(0, BDD_TRUE, BDD_FALSE)
        assert "BDDNode" in repr(node)


# ══════════════════════════════════════════════════════════════════════════════
# make_node + unique table
# ══════════════════════════════════════════════════════════════════════════════


class TestMakeNode:
    def test_reduction_rule(self):
        """If high == low, make_node returns the child (no node created)."""
        trail = fresh_trail()
        var = Var()
        vid = enumerate_var(var)
        # high == low → skip node
        result = make_node(vid, BDD_TRUE, BDD_TRUE, var)
        assert result is BDD_TRUE

    def test_unique_table_sharing(self):
        """Same (high, low) for same var returns identical node."""
        trail = fresh_trail()
        var = Var()
        vid = enumerate_var(var)
        n1 = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        n2 = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        assert n1 is n2

    def test_different_children_different_node(self):
        trail = fresh_trail()
        var = Var()
        vid = enumerate_var(var)
        n1 = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        n2 = make_node(vid, BDD_FALSE, BDD_TRUE, var)
        assert n1 is not n2


# ══════════════════════════════════════════════════════════════════════════════
# apply operation
# ══════════════════════════════════════════════════════════════════════════════


class TestApply:
    def test_and_terminals(self):
        assert apply('and', BDD_TRUE, BDD_TRUE) is BDD_TRUE
        assert apply('and', BDD_TRUE, BDD_FALSE) is BDD_FALSE
        assert apply('and', BDD_FALSE, BDD_TRUE) is BDD_FALSE
        assert apply('and', BDD_FALSE, BDD_FALSE) is BDD_FALSE

    def test_or_terminals(self):
        assert apply('or', BDD_TRUE, BDD_TRUE) is BDD_TRUE
        assert apply('or', BDD_TRUE, BDD_FALSE) is BDD_TRUE
        assert apply('or', BDD_FALSE, BDD_TRUE) is BDD_TRUE
        assert apply('or', BDD_FALSE, BDD_FALSE) is BDD_FALSE

    def test_xor_terminals(self):
        assert apply('xor', BDD_TRUE, BDD_TRUE) is BDD_FALSE
        assert apply('xor', BDD_TRUE, BDD_FALSE) is BDD_TRUE
        assert apply('xor', BDD_FALSE, BDD_TRUE) is BDD_TRUE
        assert apply('xor', BDD_FALSE, BDD_FALSE) is BDD_FALSE

    def test_equiv_terminals(self):
        assert apply('equiv', BDD_TRUE, BDD_TRUE) is BDD_TRUE
        assert apply('equiv', BDD_TRUE, BDD_FALSE) is BDD_FALSE
        assert apply('equiv', BDD_FALSE, BDD_TRUE) is BDD_FALSE
        assert apply('equiv', BDD_FALSE, BDD_FALSE) is BDD_TRUE

    def test_impl_terminals(self):
        assert apply('impl', BDD_FALSE, BDD_FALSE) is BDD_TRUE
        assert apply('impl', BDD_FALSE, BDD_TRUE) is BDD_TRUE
        assert apply('impl', BDD_TRUE, BDD_FALSE) is BDD_FALSE
        assert apply('impl', BDD_TRUE, BDD_TRUE) is BDD_TRUE

    def test_and_with_variable(self):
        """X AND 1 = X, X AND 0 = 0."""
        var = Var()
        vid = enumerate_var(var)
        x_bdd = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        assert apply('and', x_bdd, BDD_TRUE) is x_bdd
        assert apply('and', x_bdd, BDD_FALSE) is BDD_FALSE

    def test_or_with_variable(self):
        """X OR 0 = X, X OR 1 = 1."""
        var = Var()
        vid = enumerate_var(var)
        x_bdd = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        assert apply('or', x_bdd, BDD_FALSE) is x_bdd
        assert apply('or', x_bdd, BDD_TRUE) is BDD_TRUE

    def test_xor_two_variables(self):
        """X XOR Y has 4 paths, 2 satisfying."""
        x = Var()
        y = Var()
        xid = enumerate_var(x)
        yid = enumerate_var(y)
        x_bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)
        y_bdd = make_node(yid, BDD_TRUE, BDD_FALSE, y)
        result = apply('xor', x_bdd, y_bdd)
        assert isinstance(result, BDDNode)

    def test_negate(self):
        assert negate(BDD_TRUE) is BDD_FALSE
        assert negate(BDD_FALSE) is BDD_TRUE

    def test_negate_variable(self):
        var = Var()
        vid = enumerate_var(var)
        x_bdd = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        neg = negate(x_bdd)
        assert isinstance(neg, BDDNode)
        assert neg.high is BDD_FALSE
        assert neg.low is BDD_TRUE


# ══════════════════════════════════════════════════════════════════════════════
# restrict
# ══════════════════════════════════════════════════════════════════════════════


class TestRestrict:
    def test_restrict_terminal(self):
        assert restrict(BDD_TRUE, 0, 1) is BDD_TRUE
        assert restrict(BDD_FALSE, 0, 0) is BDD_FALSE

    def test_restrict_identity(self):
        var = Var()
        vid = enumerate_var(var)
        x_bdd = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        assert restrict(x_bdd, vid, 1) is BDD_TRUE
        assert restrict(x_bdd, vid, 0) is BDD_FALSE

    def test_restrict_higher_var(self):
        """Restricting a variable not in the BDD returns BDD unchanged."""
        var = Var()
        vid = enumerate_var(var)
        x_bdd = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        # Restrict a higher (non-existent) var_id
        assert restrict(x_bdd, vid + 100, 1) is x_bdd


# ══════════════════════════════════════════════════════════════════════════════
# Expression → BDD
# ══════════════════════════════════════════════════════════════════════════════


class TestExprToBDD:
    def test_int_constants(self):
        assert _expr_to_bdd(1) is BDD_TRUE
        assert _expr_to_bdd(0) is BDD_FALSE

    def test_bool_constants(self):
        assert _expr_to_bdd(True) is BDD_TRUE
        assert _expr_to_bdd(False) is BDD_FALSE

    def test_invalid_int(self):
        with pytest.raises(ValueError, match="0 or 1"):
            _expr_to_bdd(42)

    def test_var(self):
        var = Var()
        bdd = _expr_to_bdd(var)
        assert isinstance(bdd, BDDNode)
        assert bdd.high is BDD_TRUE
        assert bdd.low is BDD_FALSE

    def test_bitand(self):
        x, y = Var(), Var()
        expr = BitAnd(left=x, right=y)
        bdd = _expr_to_bdd(expr)
        # x AND y: only true when both true
        assert bdd is not BDD_TRUE
        assert bdd is not BDD_FALSE

    def test_bitor(self):
        x, y = Var(), Var()
        expr = BitOr(left=x, right=y)
        bdd = _expr_to_bdd(expr)
        assert bdd is not BDD_FALSE

    def test_bitxor(self):
        x, y = Var(), Var()
        expr = BitXor(left=x, right=y)
        bdd = _expr_to_bdd(expr)
        assert bdd is not BDD_TRUE

    def test_invert(self):
        x = Var()
        expr = Invert(operand=x)
        bdd = _expr_to_bdd(expr)
        assert isinstance(bdd, BDDNode)
        assert bdd.high is BDD_FALSE
        assert bdd.low is BDD_TRUE

    def test_bool_eq(self):
        x, y = Var(), Var()
        expr = BoolEq(left=x, right=y)
        bdd = _expr_to_bdd(expr)
        assert isinstance(bdd, BDDNode)

    def test_bool_impl(self):
        x, y = Var(), Var()
        expr = BoolImpl(left=x, right=y)
        bdd = _expr_to_bdd(expr)
        assert isinstance(bdd, BDDNode)

    def test_nested_expression(self):
        """(X & Y) | ~Z"""
        x, y, z = Var(), Var(), Var()
        expr = BitOr(left=BitAnd(left=x, right=y), right=Invert(operand=z))
        bdd = _expr_to_bdd(expr)
        assert isinstance(bdd, BDDNode)

    def test_unsupported_type(self):
        with pytest.raises(TypeError, match="unsupported"):
            _expr_to_bdd("not a bool expr")


# ══════════════════════════════════════════════════════════════════════════════
# sat
# ══════════════════════════════════════════════════════════════════════════════


class TestSat:
    def test_ground_true(self):
        trail = fresh_trail()
        assert sat(1, trail) is True

    def test_ground_false(self):
        trail = fresh_trail()
        assert sat(0, trail) is False

    def test_single_var(self):
        """sat(X) means X must be true → X is forced to 1."""
        trail = fresh_trail()
        x = Var()
        assert sat(x, trail) is True
        assert deref(x) == 1

    def test_and_forces_both(self):
        """sat(X & Y) with no other info doesn't force them.
        But sat(X & Y) where X=1 → Y must be satisfiable."""
        trail = fresh_trail()
        x, y = Var(), Var()
        expr = BitAnd(left=x, right=y)
        assert sat(expr, trail) is True

    def test_contradiction_fails(self):
        """sat(X & ~X) should fail."""
        trail = fresh_trail()
        x = Var()
        expr = BitAnd(left=x, right=Invert(operand=x))
        assert sat(expr, trail) is False

    def test_tautology_succeeds(self):
        """sat(X | ~X) should succeed."""
        trail = fresh_trail()
        x = Var()
        expr = BitOr(left=x, right=Invert(operand=x))
        assert sat(expr, trail) is True

    def test_forced_value(self):
        """sat(X & 1) with sat(X) — X must be 1 since only X=1 satisfies X."""
        trail = fresh_trail()
        x = Var()
        # sat(X) doesn't force X by itself (both 0,1 satisfy "X is satisfiable")
        # But sat(X & X) is just sat(X) - X can still be 0 or 1
        # Let's do sat(X) then sat(~X) - together they should fail:
        # Actually sat(X) means X=1 is forced!
        # No: sat(expr) means "the BDD for expr is not FALSE" - it posts the constraint.
        # After sat(X), the BDD is just X (identity). X can be 0 or 1.
        # Wait — sat posts the constraint that the expression must be true.
        # So sat(X) means X=1 must hold! X is forced to 1.
        assert sat(x, trail) is True
        assert deref(x) == 1

    def test_sat_negation_forces_zero(self):
        """sat(~X) forces X=0."""
        trail = fresh_trail()
        x = Var()
        expr = Invert(operand=x)
        assert sat(expr, trail) is True
        assert deref(x) == 0

    def test_sat_and_two_vars(self):
        """sat(X & Y) forces both X=1 and Y=1."""
        trail = fresh_trail()
        x, y = Var(), Var()
        expr = BitAnd(left=x, right=y)
        assert sat(expr, trail) is True
        assert deref(x) == 1
        assert deref(y) == 1

    def test_sat_or_no_force(self):
        """sat(X | Y) doesn't force either variable."""
        trail = fresh_trail()
        x, y = Var(), Var()
        expr = BitOr(left=x, right=y)
        assert sat(expr, trail) is True
        # Neither is forced (could be 0,1 / 1,0 / 1,1)
        # Actually: let's check if they ARE forced. If restricting X=0 gives Y
        # (which is satisfiable), then X is not forced.
        # X is still var, Y is still var
        xd = deref(x)
        yd = deref(y)
        assert is_var(xd) or is_var(yd)  # at least one not forced

    def test_sequential_sat_conjunction(self):
        """sat(X | Y) then sat(~X) forces Y=1."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert sat(BitOr(left=x, right=y), trail) is True
        assert sat(Invert(operand=x), trail) is True
        # ~X forces X=0. Then X|Y with X=0 requires Y=1
        assert deref(x) == 0
        assert deref(y) == 1


# ══════════════════════════════════════════════════════════════════════════════
# taut
# ══════════════════════════════════════════════════════════════════════════════


class TestTaut:
    def test_tautology(self):
        """X | ~X is always true → T=1."""
        trail = fresh_trail()
        x = Var()
        t = Var()
        expr = BitOr(left=x, right=Invert(operand=x))
        assert taut(expr, t, trail) is True
        assert deref(t) == 1

    def test_contradiction(self):
        """X & ~X is always false → T=0."""
        trail = fresh_trail()
        x = Var()
        t = Var()
        expr = BitAnd(left=x, right=Invert(operand=x))
        assert taut(expr, t, trail) is True
        assert deref(t) == 0

    def test_indeterminate(self):
        """X alone is neither tautology nor contradiction → fail."""
        trail = fresh_trail()
        x = Var()
        t = Var()
        assert taut(x, t, trail) is False

    def test_ground_true(self):
        trail = fresh_trail()
        t = Var()
        assert taut(1, t, trail) is True
        assert deref(t) == 1

    def test_ground_false(self):
        trail = fresh_trail()
        t = Var()
        assert taut(0, t, trail) is True
        assert deref(t) == 0

    def test_xor_not_tautology(self):
        """X ^ Y is indeterminate."""
        trail = fresh_trail()
        x, y = Var(), Var()
        t = Var()
        assert taut(BitXor(left=x, right=y), t, trail) is False

    def test_equiv_tautology(self):
        """BoolEq(X, X) → always true → T=1."""
        trail = fresh_trail()
        x = Var()
        t = Var()
        expr = BoolEq(left=x, right=x)
        assert taut(expr, t, trail) is True
        assert deref(t) == 1


# ══════════════════════════════════════════════════════════════════════════════
# sat_count
# ══════════════════════════════════════════════════════════════════════════════


class TestSatCount:
    def test_xor_count(self):
        """X ^ Y has 2 satisfying assignments."""
        trail = fresh_trail()
        x, y = Var(), Var()
        n = Var()
        assert sat_count(BitXor(left=x, right=y), n, trail) is True
        assert deref(n) == 2

    def test_and_count(self):
        """X & Y has 1 satisfying assignment."""
        trail = fresh_trail()
        x, y = Var(), Var()
        n = Var()
        assert sat_count(BitAnd(left=x, right=y), n, trail) is True
        assert deref(n) == 1

    def test_or_count(self):
        """X | Y has 3 satisfying assignments."""
        trail = fresh_trail()
        x, y = Var(), Var()
        n = Var()
        assert sat_count(BitOr(left=x, right=y), n, trail) is True
        assert deref(n) == 3

    def test_tautology_count(self):
        """X | ~X has 2 satisfying assignments (X=0 and X=1)."""
        trail = fresh_trail()
        x = Var()
        n = Var()
        expr = BitOr(left=x, right=Invert(operand=x))
        assert sat_count(expr, n, trail) is True
        assert deref(n) == 2

    def test_contradiction_count(self):
        """X & ~X has 0 satisfying assignments."""
        trail = fresh_trail()
        x = Var()
        n = Var()
        expr = BitAnd(left=x, right=Invert(operand=x))
        assert sat_count(expr, n, trail) is True
        assert deref(n) == 0

    def test_single_var_true(self):
        """Constant 1 → 1 assignment."""
        trail = fresh_trail()
        n = Var()
        assert sat_count(1, n, trail) is True
        assert deref(n) == 1

    def test_three_vars_and(self):
        """X & Y & Z has 1 satisfying assignment."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        n = Var()
        expr = BitAnd(left=BitAnd(left=x, right=y), right=z)
        assert sat_count(expr, n, trail) is True
        assert deref(n) == 1


# ══════════════════════════════════════════════════════════════════════════════
# bool_labeling
# ══════════════════════════════════════════════════════════════════════════════


class TestBoolLabeling:
    def test_single_var(self):
        """Labeling a single unconstrained var gives 2 solutions."""
        trail = fresh_trail()
        x = Var()
        results = []
        for _ in bool_labeling([x], trail):
            results.append(deref(x))
        assert sorted(results) == [0, 1]

    def test_two_vars(self):
        """Labeling two unconstrained vars gives 4 solutions."""
        trail = fresh_trail()
        x, y = Var(), Var()
        results = []
        for _ in bool_labeling([x, y], trail):
            results.append((deref(x), deref(y)))
        assert len(results) == 4
        assert sorted(results) == [(0, 0), (0, 1), (1, 0), (1, 1)]

    def test_constrained_xor(self):
        """sat(X ^ Y) then labeling gives exactly 2 solutions."""
        trail = fresh_trail()
        x, y = Var(), Var()
        sat(BitXor(left=x, right=y), trail)
        results = []
        for _ in bool_labeling([x, y], trail):
            results.append((deref(x), deref(y)))
        assert len(results) == 2
        assert sorted(results) == [(0, 1), (1, 0)]

    def test_all_bound(self):
        """Labeling already-bound vars yields one solution."""
        trail = fresh_trail()
        x, y = Var(), Var()
        unify(x, 1, trail)
        unify(y, 0, trail)
        results = list(bool_labeling([x, y], trail))
        assert len(results) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Attribute hook
# ══════════════════════════════════════════════════════════════════════════════


class TestBoolHook:
    def test_bind_constrained_var(self):
        """Binding a CLP(B) var to 0 or 1 propagates."""
        trail = fresh_trail()
        x, y = Var(), Var()
        # sat(X | Y) then bind X=0 → Y must become 1
        sat(BitOr(left=x, right=y), trail)
        assert unify(x, 0, trail)
        assert deref(y) == 1

    def test_bind_to_invalid_int(self):
        """Binding a CLP(B) var to 2 should fail."""
        trail = fresh_trail()
        x = Var()
        sat(x, trail)
        # x was forced to 1 already by sat(x), so let's use a different setup
        x2 = Var()
        expr = BitOr(left=x2, right=Invert(operand=x2))  # tautology on x2
        # Post as sat won't force x2 since it's a tautology
        # Actually, sat(x2 | ~x2) is BDD_TRUE, so returns True immediately
        # with no attr stored. Let's manually create state.
        trail2 = Trail()
        x3 = Var()
        vid = enumerate_var(x3)
        bdd = make_node(vid, BDD_TRUE, BDD_FALSE, x3)
        state = BoolState(sat_expr=x3, bdd=bdd, root_var=x3)
        put_attr(x3, B_KEY, state, trail2)
        # Now bind x3 to 2 — should fail via hook
        assert not unify(x3, 2, trail2)

    def test_var_var_merge(self):
        """Unifying two CLP(B) vars with compatible BDDs succeeds."""
        trail = fresh_trail()
        x, y = Var(), Var()
        # Both have identity BDDs (both must be true)
        xid = enumerate_var(x)
        x_bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)
        state_x = BoolState(sat_expr=x, bdd=x_bdd, root_var=x)
        put_attr(x, B_KEY, state_x, trail)

        yid = enumerate_var(y)
        y_bdd = make_node(yid, BDD_TRUE, BDD_FALSE, y)
        state_y = BoolState(sat_expr=y, bdd=y_bdd, root_var=y)
        put_attr(y, B_KEY, state_y, trail)

        # Unify x and y — merges compatible BDDs
        assert unify(x, y, trail)

    def test_var_var_merge_incompatible(self):
        """Unifying CLP(B) vars with contradictory BDDs fails."""
        trail = fresh_trail()
        x, y = Var(), Var()
        # x must be true, y must be false — merging should fail
        xid = enumerate_var(x)
        x_bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)
        state_x = BoolState(sat_expr=x, bdd=x_bdd, root_var=x)
        put_attr(x, B_KEY, state_x, trail)

        yid = enumerate_var(y)
        y_bdd = make_node(yid, BDD_TRUE, BDD_FALSE, y)
        neg_y_bdd = negate(y_bdd)
        state_y = BoolState(sat_expr=Invert(operand=y), bdd=neg_y_bdd, root_var=y)
        put_attr(y, B_KEY, state_y, trail)

        # Unify x and y — x=1 AND y=0 with x=y → contradiction
        assert not unify(x, y, trail)


# ══════════════════════════════════════════════════════════════════════════════
# Trail safety
# ══════════════════════════════════════════════════════════════════════════════


class TestTrailSafety:
    def test_backtrack_restores_state(self):
        """After backtracking, CLP(B) state is restored."""
        trail = fresh_trail()
        x = Var()
        mark = trail.mark()

        # Post constraint
        expr = BitOr(left=x, right=Invert(operand=x))  # tautology
        sat(expr, trail)

        # Check state exists (may or may not, since tautology returns True immediately)
        # Let's use a non-trivial constraint
        trail.undo(mark)

        # After undo, variable should be clean
        trail2 = fresh_trail()
        y, z = Var(), Var()
        mark2 = trail2.mark()
        sat(BitAnd(left=y, right=z), trail2)
        # Both forced to 1
        assert deref(y) == 1
        assert deref(z) == 1

        trail2.undo(mark2)
        # After undo, y and z should be unbound again
        assert is_var(deref(y))
        assert is_var(deref(z))

    def test_labeling_backtracks_cleanly(self):
        """Labeling undoes assignments between solutions."""
        trail = fresh_trail()
        x, y = Var(), Var()
        results = []
        for _ in bool_labeling([x, y], trail):
            results.append((deref(x), deref(y)))
        assert len(results) == 4
        # After generator exhausted, vars should be unbound
        assert is_var(deref(x))
        assert is_var(deref(y))


# ══════════════════════════════════════════════════════════════════════════════
# BoolEq / BoolImpl term constructors
# ══════════════════════════════════════════════════════════════════════════════


class TestTermConstructors:
    def test_bool_eq_construction(self):
        x, y = Var(), Var()
        eq = BoolEq(left=x, right=y)
        assert eq.left is x
        assert eq.right is y

    def test_bool_impl_construction(self):
        x, y = Var(), Var()
        impl = BoolImpl(left=x, right=y)
        assert impl.left is x
        assert impl.right is y

    def test_bool_eq_in_sat(self):
        """sat(BoolEq(X, Y)) — X ↔ Y must hold."""
        trail = fresh_trail()
        x, y = Var(), Var()
        sat(BoolEq(left=x, right=y), trail)
        # Both free, but equiv constrained
        results = []
        for _ in bool_labeling([x, y], trail):
            results.append((deref(x), deref(y)))
        # Only (0,0) and (1,1)
        assert sorted(results) == [(0, 0), (1, 1)]

    def test_bool_impl_in_sat(self):
        """sat(BoolImpl(X, Y)) — X → Y must hold."""
        trail = fresh_trail()
        x, y = Var(), Var()
        sat(BoolImpl(left=x, right=y), trail)
        results = []
        for _ in bool_labeling([x, y], trail):
            results.append((deref(x), deref(y)))
        # X→Y: (0,0), (0,1), (1,1) — not (1,0)
        assert sorted(results) == [(0, 0), (0, 1), (1, 1)]


# ══════════════════════════════════════════════════════════════════════════════
# Integration: half adder truth table
# ══════════════════════════════════════════════════════════════════════════════


class TestHalfAdder:
    def _half_adder(self, x_val, y_val):
        """Compute half adder via CLP(B)."""
        trail = fresh_trail()
        x, y, s, c = Var(), Var(), Var(), Var()
        # sum_ ↔ (X XOR Y)
        assert sat(BoolEq(left=s, right=BitXor(left=x, right=y)), trail)
        # Carry ↔ (X AND Y)
        assert sat(BoolEq(left=c, right=BitAnd(left=x, right=y)), trail)
        # Bind inputs
        assert unify(x, x_val, trail)
        assert unify(y, y_val, trail)
        return deref(s), deref(c)

    def test_0_0(self):
        s, c = self._half_adder(0, 0)
        assert (s, c) == (0, 0)

    def test_0_1(self):
        s, c = self._half_adder(0, 1)
        assert (s, c) == (1, 0)

    def test_1_0(self):
        s, c = self._half_adder(1, 0)
        assert (s, c) == (1, 0)

    def test_1_1(self):
        s, c = self._half_adder(1, 1)
        assert (s, c) == (0, 1)


# ══════════════════════════════════════════════════════════════════════════════
# Integration: full adder
# ══════════════════════════════════════════════════════════════════════════════


class TestFullAdder:
    def _full_adder(self, x_val, y_val, cin_val):
        trail = fresh_trail()
        x, y, cin, s, cout = Var(), Var(), Var(), Var(), Var()
        s1, c1, c2 = Var(), Var(), Var()
        # S1 ↔ (X XOR Y)
        assert sat(BoolEq(left=s1, right=BitXor(left=x, right=y)), trail)
        # C1 ↔ (X AND Y)
        assert sat(BoolEq(left=c1, right=BitAnd(left=x, right=y)), trail)
        # sum_ ↔ (S1 XOR Cin)
        assert sat(BoolEq(left=s, right=BitXor(left=s1, right=cin)), trail)
        # C2 ↔ (S1 AND Cin)
        assert sat(BoolEq(left=c2, right=BitAnd(left=s1, right=cin)), trail)
        # Cout ↔ (C1 OR C2)
        assert sat(BoolEq(left=cout, right=BitOr(left=c1, right=c2)), trail)
        # Bind inputs
        assert unify(x, x_val, trail)
        assert unify(y, y_val, trail)
        assert unify(cin, cin_val, trail)
        return deref(s), deref(cout)

    def test_0_0_0(self):
        assert self._full_adder(0, 0, 0) == (0, 0)

    def test_1_1_0(self):
        assert self._full_adder(1, 1, 0) == (0, 1)

    def test_1_1_1(self):
        assert self._full_adder(1, 1, 1) == (1, 1)

    def test_0_1_1(self):
        assert self._full_adder(0, 1, 1) == (0, 1)

    def test_1_0_0(self):
        assert self._full_adder(1, 0, 0) == (1, 0)


# ══════════════════════════════════════════════════════════════════════════════
# Integration: pigeon-hole (unsatisfiable)
# ══════════════════════════════════════════════════════════════════════════════


class TestPigeonHole:
    def test_3_pigeons_2_holes(self):
        """3 pigeons, 2 holes — no valid assignment exists."""
        trail = fresh_trail()
        # P_ij = pigeon i in hole j
        p = [[Var() for _ in range(2)] for _ in range(3)]

        # Each pigeon in at least one hole
        for i in range(3):
            assert sat(BitOr(left=p[i][0], right=p[i][1]), trail)

        # Each hole has at most one pigeon
        for j in range(2):
            for i1 in range(3):
                for i2 in range(i1 + 1, 3):
                    result = sat(Invert(operand=BitAnd(left=p[i1][j], right=p[i2][j])), trail)
                    if not result:
                        return  # already detected unsat — test passes

        # If we get here, try labeling — should produce no solutions
        all_vars = [p[i][j] for i in range(3) for j in range(2)]
        solutions = list(bool_labeling(all_vars, trail))
        assert len(solutions) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Integration: circuit equivalence via taut
# ══════════════════════════════════════════════════════════════════════════════


class TestCircuitEquivalence:
    def test_demorgan(self):
        """taut(~(X & Y) ↔ (~X | ~Y)) should be tautology."""
        trail = fresh_trail()
        x, y = Var(), Var()
        t = Var()
        lhs = Invert(operand=BitAnd(left=x, right=y))
        rhs = BitOr(left=Invert(operand=x), right=Invert(operand=y))
        equiv_expr = BoolEq(left=lhs, right=rhs)
        assert taut(equiv_expr, t, trail) is True
        assert deref(t) == 1

    def test_non_equivalence(self):
        """taut(X ↔ Y) is not a tautology."""
        trail = fresh_trail()
        x, y = Var(), Var()
        t = Var()
        assert taut(BoolEq(left=x, right=y), t, trail) is False


# ══════════════════════════════════════════════════════════════════════════════
# Integration: .clausal fixture
# ══════════════════════════════════════════════════════════════════════════════


class TestClpbFixture:
    @pytest.fixture(autouse=True)
    def load_fixture(self):
        import os
        from clausal.import_hook import _load_module
        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "clpb_circuit.clausal"
        )
        self.mod = _load_module("clpb_circuit", fixture_path)
        self.logic_mod = self.mod.__dict__["$module"]

    def test_half_adder_0_0(self):
        from clausal.logic.solve import call
        s_, c_ = Var(), Var()
        results = []
        for _ in call("HalfAdder", 0, 0, s_, c_, module=self.logic_mod):
            results.append((deref(s_), deref(c_)))
        assert len(results) >= 1
        assert results[0] == (0, 0)

    def test_half_adder_1_1(self):
        from clausal.logic.solve import call
        s_, c_ = Var(), Var()
        results = []
        for _ in call("HalfAdder", 1, 1, s_, c_, module=self.logic_mod):
            results.append((deref(s_), deref(c_)))
        assert len(results) >= 1
        assert results[0] == (0, 1)

    def test_full_adder_1_1_1(self):
        from clausal.logic.solve import call
        s_, cout_ = Var(), Var()
        results = []
        for _ in call("FullAdder", 1, 1, 1, s_, cout_, module=self.logic_mod):
            results.append((deref(s_), deref(cout_)))
        assert len(results) >= 1
        assert results[0] == (1, 1)

    def test_pigeon_hole_unsat(self):
        from clausal.logic.solve import call
        results = list(call("PigeonHole", module=self.logic_mod))
        assert len(results) == 0
