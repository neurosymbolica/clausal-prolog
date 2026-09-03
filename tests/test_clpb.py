"""Tests for CLP(B) Boolean constraint solver.

Tests BDD operations, sat/taut/sat_count/labeling, attribute hook,
trail safety, and compiled integration via .clausal fixtures.
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var, put_attr, get_attr
from clausal.logic.clpb import (
    B_KEY,
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
        # nv
        node = BDDNode(0, BDD_TRUE, BDD_FALSE)
        assert node.var_id == 0
        assert node.high is BDD_TRUE
        assert node.low is BDD_FALSE

    def test_identity_equality(self):
        # nv
        n1 = BDDNode(0, BDD_TRUE, BDD_FALSE)
        n2 = BDDNode(0, BDD_TRUE, BDD_FALSE)
        assert n1 != n2  # identity-based
        assert n1 == n1

    def test_hashable(self):
        # nv
        node = BDDNode(0, BDD_TRUE, BDD_FALSE)
        d = {node: "ok"}
        assert d[node] == "ok"

    def test_repr(self):
        # nv
        node = BDDNode(0, BDD_TRUE, BDD_FALSE)
        assert "BDDNode" in repr(node)


# ══════════════════════════════════════════════════════════════════════════════
# make_node + unique table
# ══════════════════════════════════════════════════════════════════════════════


class TestMakeNode:
    def test_reduction_rule(self):
        """If high == low, make_node returns the child (no node created)."""
        # nv
        trail = fresh_trail()
        var = Var()
        vid = enumerate_var(var)
        # high == low → skip node
        result = make_node(vid, BDD_TRUE, BDD_TRUE, var)
        assert result is BDD_TRUE

    def test_unique_table_sharing(self):
        """Same (high, low) for same var returns identical node."""
        # nv
        trail = fresh_trail()
        var = Var()
        vid = enumerate_var(var)
        n1 = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        n2 = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        assert n1 is n2

    def test_different_children_different_node(self):
        # nv
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
        # nv
        assert apply('and', BDD_TRUE, BDD_TRUE) is BDD_TRUE
        assert apply('and', BDD_TRUE, BDD_FALSE) is BDD_FALSE
        assert apply('and', BDD_FALSE, BDD_TRUE) is BDD_FALSE
        assert apply('and', BDD_FALSE, BDD_FALSE) is BDD_FALSE

    def test_or_terminals(self):
        # nv
        assert apply('or', BDD_TRUE, BDD_TRUE) is BDD_TRUE
        assert apply('or', BDD_TRUE, BDD_FALSE) is BDD_TRUE
        assert apply('or', BDD_FALSE, BDD_TRUE) is BDD_TRUE
        assert apply('or', BDD_FALSE, BDD_FALSE) is BDD_FALSE

    def test_xor_terminals(self):
        # nv
        assert apply('xor', BDD_TRUE, BDD_TRUE) is BDD_FALSE
        assert apply('xor', BDD_TRUE, BDD_FALSE) is BDD_TRUE
        assert apply('xor', BDD_FALSE, BDD_TRUE) is BDD_TRUE
        assert apply('xor', BDD_FALSE, BDD_FALSE) is BDD_FALSE

    def test_equiv_terminals(self):
        # nv
        assert apply('equiv', BDD_TRUE, BDD_TRUE) is BDD_TRUE
        assert apply('equiv', BDD_TRUE, BDD_FALSE) is BDD_FALSE
        assert apply('equiv', BDD_FALSE, BDD_TRUE) is BDD_FALSE
        assert apply('equiv', BDD_FALSE, BDD_FALSE) is BDD_TRUE

    def test_impl_terminals(self):
        # nv
        assert apply('impl', BDD_FALSE, BDD_FALSE) is BDD_TRUE
        assert apply('impl', BDD_FALSE, BDD_TRUE) is BDD_TRUE
        assert apply('impl', BDD_TRUE, BDD_FALSE) is BDD_FALSE
        assert apply('impl', BDD_TRUE, BDD_TRUE) is BDD_TRUE

    def test_and_with_variable(self):
        """X AND 1 = X, X AND 0 = 0."""
        # nv
        var = Var()
        vid = enumerate_var(var)
        x_bdd = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        assert apply('and', x_bdd, BDD_TRUE) is x_bdd
        assert apply('and', x_bdd, BDD_FALSE) is BDD_FALSE

    def test_or_with_variable(self):
        """X OR 0 = X, X OR 1 = 1."""
        # nv
        var = Var()
        vid = enumerate_var(var)
        x_bdd = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        assert apply('or', x_bdd, BDD_FALSE) is x_bdd
        assert apply('or', x_bdd, BDD_TRUE) is BDD_TRUE

    def test_xor_two_variables(self):
        """X XOR Y has 4 paths, 2 satisfying."""
        # nv
        x = Var()
        y = Var()
        xid = enumerate_var(x)
        yid = enumerate_var(y)
        x_bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)
        y_bdd = make_node(yid, BDD_TRUE, BDD_FALSE, y)
        result = apply('xor', x_bdd, y_bdd)
        assert isinstance(result, BDDNode)

    def test_negate(self):
        # nv
        assert negate(BDD_TRUE) is BDD_FALSE
        assert negate(BDD_FALSE) is BDD_TRUE

    def test_negate_variable(self):
        # nv
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
        # nv
        assert restrict(BDD_TRUE, 0, 1) is BDD_TRUE
        assert restrict(BDD_FALSE, 0, 0) is BDD_FALSE

    def test_restrict_identity(self):
        # nv
        var = Var()
        vid = enumerate_var(var)
        x_bdd = make_node(vid, BDD_TRUE, BDD_FALSE, var)
        assert restrict(x_bdd, vid, 1) is BDD_TRUE
        assert restrict(x_bdd, vid, 0) is BDD_FALSE

    def test_restrict_higher_var(self):
        """Restricting a variable not in the BDD returns BDD unchanged."""
        # nv
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
        # nv
        assert _expr_to_bdd(1) is BDD_TRUE
        assert _expr_to_bdd(0) is BDD_FALSE

    def test_bool_constants(self):
        # nv
        assert _expr_to_bdd(True) is BDD_TRUE
        assert _expr_to_bdd(False) is BDD_FALSE

    def test_invalid_int(self):
        # nv
        with pytest.raises(ValueError, match="0 or 1"):
            _expr_to_bdd(42)

    def test_var(self):
        # nv
        var = Var()
        bdd = _expr_to_bdd(var)
        assert isinstance(bdd, BDDNode)
        assert bdd.high is BDD_TRUE
        assert bdd.low is BDD_FALSE

    def test_bitand(self):
        # nv
        x, y = Var(), Var()
        expr = BitAnd(left=x, right=y)
        bdd = _expr_to_bdd(expr)
        # x AND y: only true when both true
        assert bdd is not BDD_TRUE
        assert bdd is not BDD_FALSE

    def test_bitor(self):
        # nv
        x, y = Var(), Var()
        expr = BitOr(left=x, right=y)
        bdd = _expr_to_bdd(expr)
        assert bdd is not BDD_FALSE

    def test_bitxor(self):
        # nv
        x, y = Var(), Var()
        expr = BitXor(left=x, right=y)
        bdd = _expr_to_bdd(expr)
        assert bdd is not BDD_TRUE

    def test_invert(self):
        # nv
        x = Var()
        expr = Invert(operand=x)
        bdd = _expr_to_bdd(expr)
        assert isinstance(bdd, BDDNode)
        assert bdd.high is BDD_FALSE
        assert bdd.low is BDD_TRUE

    def test_bool_eq(self):
        # nv
        x, y = Var(), Var()
        expr = BoolEq(left=x, right=y)
        bdd = _expr_to_bdd(expr)
        assert isinstance(bdd, BDDNode)

    def test_bool_impl(self):
        # nv
        x, y = Var(), Var()
        expr = BoolImpl(left=x, right=y)
        bdd = _expr_to_bdd(expr)
        assert isinstance(bdd, BDDNode)

    def test_nested_expression(self):
        """(X & Y) | ~Z"""
        # nv
        x, y, z = Var(), Var(), Var()
        expr = BitOr(left=BitAnd(left=x, right=y), right=Invert(operand=z))
        bdd = _expr_to_bdd(expr)
        assert isinstance(bdd, BDDNode)

    def test_unsupported_type(self):
        # nv
        with pytest.raises(TypeError, match="unsupported"):
            _expr_to_bdd("not a bool expr")

    def test_term_named_booleq_without_left_right_raises_type_error(self):
        """A term instance whose functor happens to be 'BoolEq' but which was
        NOT built by clpb's own make_predicate("BoolEq", ["left", "right"])
        -- and so has no .left/.right -- must fall through to the same
        unsupported-expression TypeError as any other unrecognized term, not
        raise an AttributeError. is_term_instance() admits any dataclass/
        PredicateMeta instance, so functor-name matching alone is not proof
        the .left/.right access is safe."""
        # nv
        from clausal.logic.predicate import make_predicate
        fake_bool_eq = make_predicate("BoolEq", ["x"])
        with pytest.raises(TypeError, match="unsupported"):
            _expr_to_bdd(fake_bool_eq(1))

    def test_term_named_boolimpl_without_left_right_raises_type_error(self):
        # nv
        from clausal.logic.predicate import make_predicate
        fake_bool_impl = make_predicate("BoolImpl", ["x"])
        with pytest.raises(TypeError, match="unsupported"):
            _expr_to_bdd(fake_bool_impl(1))


# ══════════════════════════════════════════════════════════════════════════════
# sat
# ══════════════════════════════════════════════════════════════════════════════


class TestSat:
    def test_ground_true(self):
        # nv
        trail = fresh_trail()
        assert sat(1, trail) is True

    def test_ground_false(self):
        # nv
        trail = fresh_trail()
        assert sat(0, trail) is False

    def test_single_var(self):
        """sat(X) means X must be true → X is forced to 1."""
        # nv
        trail = fresh_trail()
        x = Var()
        assert sat(x, trail) is True
        assert deref(x) == 1

    def test_and_forces_both(self):
        """sat(X & Y) with no other info doesn't force them.
        But sat(X & Y) where X=1 → Y must be satisfiable."""
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        expr = BitAnd(left=x, right=y)
        assert sat(expr, trail) is True

    def test_contradiction_fails(self):
        """sat(X & ~X) should fail."""
        # nv
        trail = fresh_trail()
        x = Var()
        expr = BitAnd(left=x, right=Invert(operand=x))
        assert sat(expr, trail) is False

    def test_tautology_succeeds(self):
        """sat(X | ~X) should succeed."""
        # nv
        trail = fresh_trail()
        x = Var()
        expr = BitOr(left=x, right=Invert(operand=x))
        assert sat(expr, trail) is True

    def test_forced_value(self):
        """sat(X & 1) with sat(X) — X must be 1 since only X=1 satisfies X."""
        # nv
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
        # nv
        trail = fresh_trail()
        x = Var()
        expr = Invert(operand=x)
        assert sat(expr, trail) is True
        assert deref(x) == 0

    def test_sat_and_two_vars(self):
        """sat(X & Y) forces both X=1 and Y=1."""
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        expr = BitAnd(left=x, right=y)
        assert sat(expr, trail) is True
        assert deref(x) == 1
        assert deref(y) == 1

    def test_sat_or_no_force(self):
        """sat(X | Y) doesn't force either variable."""
        # nv
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
        # nv
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
        # nv
        trail = fresh_trail()
        x = Var()
        t = Var()
        expr = BitOr(left=x, right=Invert(operand=x))
        assert taut(expr, t, trail) is True
        assert deref(t) == 1

    def test_contradiction(self):
        """X & ~X is always false → T=0."""
        # nv
        trail = fresh_trail()
        x = Var()
        t = Var()
        expr = BitAnd(left=x, right=Invert(operand=x))
        assert taut(expr, t, trail) is True
        assert deref(t) == 0

    def test_indeterminate(self):
        """X alone is neither tautology nor contradiction → fail."""
        # nv
        trail = fresh_trail()
        x = Var()
        t = Var()
        assert taut(x, t, trail) is False

    def test_ground_true(self):
        # nv
        trail = fresh_trail()
        t = Var()
        assert taut(1, t, trail) is True
        assert deref(t) == 1

    def test_ground_false(self):
        # nv
        trail = fresh_trail()
        t = Var()
        assert taut(0, t, trail) is True
        assert deref(t) == 0

    def test_xor_not_tautology(self):
        """X ^ Y is indeterminate."""
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        t = Var()
        assert taut(BitXor(left=x, right=y), t, trail) is False

    def test_equiv_tautology(self):
        """BoolEq(X, X) → always true → T=1."""
        # nv
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
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        n = Var()
        assert sat_count(BitXor(left=x, right=y), n, trail) is True
        assert deref(n) == 2

    def test_and_count(self):
        """X & Y has 1 satisfying assignment."""
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        n = Var()
        assert sat_count(BitAnd(left=x, right=y), n, trail) is True
        assert deref(n) == 1

    def test_or_count(self):
        """X | Y has 3 satisfying assignments."""
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        n = Var()
        assert sat_count(BitOr(left=x, right=y), n, trail) is True
        assert deref(n) == 3

    def test_tautology_count(self):
        """X | ~X has 2 satisfying assignments (X=0 and X=1)."""
        # nv
        trail = fresh_trail()
        x = Var()
        n = Var()
        expr = BitOr(left=x, right=Invert(operand=x))
        assert sat_count(expr, n, trail) is True
        assert deref(n) == 2

    def test_contradiction_count(self):
        """X & ~X has 0 satisfying assignments."""
        # nv
        trail = fresh_trail()
        x = Var()
        n = Var()
        expr = BitAnd(left=x, right=Invert(operand=x))
        assert sat_count(expr, n, trail) is True
        assert deref(n) == 0

    def test_single_var_true(self):
        """Constant 1 → 1 assignment."""
        # nv
        trail = fresh_trail()
        n = Var()
        assert sat_count(1, n, trail) is True
        assert deref(n) == 1

    def test_three_vars_and(self):
        """X & Y & Z has 1 satisfying assignment."""
        # nv
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
        # nv
        trail = fresh_trail()
        x = Var()
        results = []
        for _ in bool_labeling([x], trail):
            results.append(deref(x))
        assert sorted(results) == [0, 1]

    def test_two_vars(self):
        """Labeling two unconstrained vars gives 4 solutions."""
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        results = []
        for _ in bool_labeling([x, y], trail):
            results.append((deref(x), deref(y)))
        assert len(results) == 4
        assert sorted(results) == [(0, 0), (0, 1), (1, 0), (1, 1)]

    def test_constrained_xor(self):
        """sat(X ^ Y) then labeling gives exactly 2 solutions."""
        # nv
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
        # nv
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
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        # sat(X | Y) then bind X=0 → Y must become 1
        sat(BitOr(left=x, right=y), trail)
        assert unify(x, 0, trail)
        assert deref(y) == 1

    def test_bind_to_invalid_int(self):
        """Binding a CLP(B) var to 2 should fail."""
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
        x, y = Var(), Var()
        eq = BoolEq(left=x, right=y)
        assert eq.left is x
        assert eq.right is y

    def test_bool_impl_construction(self):
        # nv
        x, y = Var(), Var()
        impl = BoolImpl(left=x, right=y)
        assert impl.left is x
        assert impl.right is y

    def test_bool_eq_in_sat(self):
        """sat(BoolEq(X, Y)) — X ↔ Y must hold."""
        # nv
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
        # nv
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
        # nv
        s, c = self._half_adder(0, 0)
        assert (s, c) == (0, 0)

    def test_0_1(self):
        # nv
        s, c = self._half_adder(0, 1)
        assert (s, c) == (1, 0)

    def test_1_0(self):
        # nv
        s, c = self._half_adder(1, 0)
        assert (s, c) == (1, 0)

    def test_1_1(self):
        # nv
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
        # nv
        assert self._full_adder(0, 0, 0) == (0, 0)

    def test_1_1_0(self):
        # nv
        assert self._full_adder(1, 1, 0) == (0, 1)

    def test_1_1_1(self):
        # nv
        assert self._full_adder(1, 1, 1) == (1, 1)

    def test_0_1_1(self):
        # nv
        assert self._full_adder(0, 1, 1) == (0, 1)

    def test_1_0_0(self):
        # nv
        assert self._full_adder(1, 0, 0) == (1, 0)


# ══════════════════════════════════════════════════════════════════════════════
# Integration: pigeon-hole (unsatisfiable)
# ══════════════════════════════════════════════════════════════════════════════


class TestPigeonHole:
    def test_3_pigeons_2_holes(self):
        """3 pigeons, 2 holes — no valid assignment exists."""
        # nv
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
        # nv
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
        # nv
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
        # nv
        from clausal.logic.solve import call
        s_, c_ = Var(), Var()
        results = []
        for _ in call("HalfAdder", 0, 0, s_, c_, module=self.logic_mod):
            results.append((deref(s_), deref(c_)))
        assert len(results) >= 1
        assert results[0] == (0, 0)

    def test_half_adder_1_1(self):
        # nv
        from clausal.logic.solve import call
        s_, c_ = Var(), Var()
        results = []
        for _ in call("HalfAdder", 1, 1, s_, c_, module=self.logic_mod):
            results.append((deref(s_), deref(c_)))
        assert len(results) >= 1
        assert results[0] == (0, 1)

    def test_full_adder_1_1_1(self):
        # nv
        from clausal.logic.solve import call
        s_, cout_ = Var(), Var()
        results = []
        for _ in call("FullAdder", 1, 1, 1, s_, cout_, module=self.logic_mod):
            results.append((deref(s_), deref(cout_)))
        assert len(results) >= 1
        assert results[0] == (1, 1)

    def test_pigeon_hole_unsat(self):
        # nv
        from clausal.logic.solve import call
        results = list(call("PigeonHole", module=self.logic_mod))
        assert len(results) == 0


# ══════════════════════════════════════════════════════════════════════════════
# NAND operation
# ══════════════════════════════════════════════════════════════════════════════


class TestNand:
    def test_nand_true_true(self):
        """NAND(1, 1) = 0."""
        # nv
        result = apply('nand', BDD_TRUE, BDD_TRUE)
        assert result is BDD_FALSE

    def test_nand_true_false(self):
        """NAND(1, 0) = 1."""
        # nv
        result = apply('nand', BDD_TRUE, BDD_FALSE)
        assert result is BDD_TRUE

    def test_nand_false_true(self):
        """NAND(0, 1) = 1."""
        # nv
        result = apply('nand', BDD_FALSE, BDD_TRUE)
        assert result is BDD_TRUE

    def test_nand_false_false(self):
        """NAND(0, 0) = 1."""
        # nv
        result = apply('nand', BDD_FALSE, BDD_FALSE)
        assert result is BDD_TRUE

    def test_nand_with_variables(self):
        """NAND(X, Y) is equivalent to ~(X & Y)."""
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        xid, yid = enumerate_var(x), enumerate_var(y)
        x_bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)
        y_bdd = make_node(yid, BDD_TRUE, BDD_FALSE, y)

        nand_bdd = apply('nand', x_bdd, y_bdd)
        and_neg_bdd = negate(apply('and', x_bdd, y_bdd))

        # Equivalence: nand ↔ ~and should be tautology
        equiv = apply('equiv', nand_bdd, and_neg_bdd)
        assert equiv is BDD_TRUE

    def test_nand_self(self):
        """NAND(X, X) = ~X."""
        # nv
        trail = fresh_trail()
        x = Var()
        xid = enumerate_var(x)
        x_bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)

        nand_self = apply('nand', x_bdd, x_bdd)
        not_x = negate(x_bdd)

        equiv = apply('equiv', nand_self, not_x)
        assert equiv is BDD_TRUE


# ══════════════════════════════════════════════════════════════════════════════
# Direct _collect_bdd_var_ids tests
# ══════════════════════════════════════════════════════════════════════════════


class TestCollectBddVarIds:
    def test_terminal_true(self):
        """No var IDs in a terminal node."""
        # nv
        result = set()
        _collect_bdd_var_ids(BDD_TRUE, result)
        assert result == set()

    def test_terminal_false(self):
        # nv
        result = set()
        _collect_bdd_var_ids(BDD_FALSE, result)
        assert result == set()

    def test_single_variable(self):
        """Identity BDD for one variable has one var_id."""
        # nv
        trail = fresh_trail()
        x = Var()
        xid = enumerate_var(x)
        bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)
        result = set()
        _collect_bdd_var_ids(bdd, result)
        assert result == {xid}

    def test_two_variables(self):
        """apply('and', X, Y) contains both var_ids."""
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        xid, yid = enumerate_var(x), enumerate_var(y)
        x_bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)
        y_bdd = make_node(yid, BDD_TRUE, BDD_FALSE, y)
        and_bdd = apply('and', x_bdd, y_bdd)
        result = set()
        _collect_bdd_var_ids(and_bdd, result)
        assert xid in result
        assert yid in result

    def test_complex_bdd(self):
        """(X & Y) | (Z ^ W) has four var_ids."""
        # nv
        trail = fresh_trail()
        vs = [Var() for _ in range(4)]
        ids = [enumerate_var(v) for v in vs]
        bdds = [make_node(vid, BDD_TRUE, BDD_FALSE, v) for vid, v in zip(ids, vs)]
        and_bdd = apply('and', bdds[0], bdds[1])
        xor_bdd = apply('xor', bdds[2], bdds[3])
        or_bdd = apply('or', and_bdd, xor_bdd)
        result = set()
        _collect_bdd_var_ids(or_bdd, result)
        assert result == set(ids)

    def test_adds_to_existing_set(self):
        """_collect_bdd_var_ids adds to (not replaces) the result set."""
        # nv
        trail = fresh_trail()
        x = Var()
        xid = enumerate_var(x)
        bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)
        result = {999}
        _collect_bdd_var_ids(bdd, result)
        assert 999 in result
        assert xid in result


# ══════════════════════════════════════════════════════════════════════════════
# Direct _propagate_forced tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPropagateForced:
    def test_terminal_true(self):
        """Terminal BDD_TRUE — nothing to propagate."""
        # nv
        trail = fresh_trail()
        assert _propagate_forced(BDD_TRUE, trail) is True

    def test_terminal_false(self):
        """Terminal BDD_FALSE — nothing to propagate (returns True, it's not
        _propagate_forced's job to detect BDD_FALSE, only forced vars)."""
        # nv
        trail = fresh_trail()
        assert _propagate_forced(BDD_FALSE, trail) is True

    def test_single_var_forced_high(self):
        """Identity BDD (if X then 1 else 0): restrict X=0 gives FALSE → X must be 1."""
        # nv
        trail = fresh_trail()
        x = Var()
        xid = enumerate_var(x)
        bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)
        assert _propagate_forced(bdd, trail) is True
        assert deref(x) == 1

    def test_single_var_forced_low(self):
        """Negated BDD (if X then 0 else 1): restrict X=1 gives FALSE → X must be 0."""
        # nv
        trail = fresh_trail()
        x = Var()
        xid = enumerate_var(x)
        bdd = make_node(xid, BDD_FALSE, BDD_TRUE, x)
        assert _propagate_forced(bdd, trail) is True
        assert deref(x) == 0

    def test_contradiction_detected(self):
        """BDD where both cofactors are FALSE → contradiction."""
        # nv
        trail = fresh_trail()
        x = Var()
        xid = enumerate_var(x)
        # Manually construct: if X then FALSE else FALSE
        # This shouldn't normally be created (reduction rule), but test the check
        bdd = BDDNode(xid, BDD_FALSE, BDD_FALSE)
        assert _propagate_forced(bdd, trail) is False


# ══════════════════════════════════════════════════════════════════════════════
# Large variable count and sat_count edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestLargeVarCount:
    def test_20_variable_or_chain(self):
        """OR of 20 variables: 2^20 - 1 satisfying assignments."""
        # nv
        trail = fresh_trail()
        vs = [Var() for _ in range(20)]
        expr = vs[0]
        for v in vs[1:]:
            expr = BitOr(left=expr, right=v)
        n = Var()
        assert sat_count(expr, n, trail) is True
        assert deref(n) == 2**20 - 1

    def test_10_variable_xor_chain(self):
        """XOR of 10 variables: 2^9 = 512 satisfying assignments."""
        # nv
        trail = fresh_trail()
        vs = [Var() for _ in range(10)]
        expr = vs[0]
        for v in vs[1:]:
            expr = BitXor(left=expr, right=v)
        n = Var()
        assert sat_count(expr, n, trail) is True
        assert deref(n) == 2**9

    def test_sat_count_constant_true(self):
        """sat_count(1) with no variables = 1."""
        # nv
        trail = fresh_trail()
        n = Var()
        assert sat_count(1, n, trail) is True
        assert deref(n) == 1

    def test_sat_count_constant_false(self):
        """sat_count(0) = 0."""
        # nv
        trail = fresh_trail()
        n = Var()
        assert sat_count(0, n, trail) is True
        assert deref(n) == 0

    def test_sat_count_single_var_identity(self):
        """sat_count(X) = 1 (only X=1 satisfies)."""
        # nv
        trail = fresh_trail()
        x = Var()
        n = Var()
        assert sat_count(x, n, trail) is True
        assert deref(n) == 1

    def test_deep_and_chain(self):
        """AND of 15 variables: exactly 1 satisfying assignment."""
        # nv
        trail = fresh_trail()
        vs = [Var() for _ in range(15)]
        expr = vs[0]
        for v in vs[1:]:
            expr = BitAnd(left=expr, right=v)
        n = Var()
        assert sat_count(expr, n, trail) is True
        assert deref(n) == 1

    def test_labeling_with_many_vars(self):
        """Labeling 5 vars constrained by XOR: should get 2^4 = 16 solutions."""
        # nv
        trail = fresh_trail()
        vs = [Var() for _ in range(5)]
        expr = vs[0]
        for v in vs[1:]:
            expr = BitXor(left=expr, right=v)
        sat(expr, trail)
        results = list(bool_labeling(vs, trail))
        assert len(results) == 16


# ══════════════════════════════════════════════════════════════════════════════
# Direct restrict tests
# ══════════════════════════════════════════════════════════════════════════════


class TestRestrictDirect:
    def test_restrict_deeper_bdd(self):
        """Restrict on a multi-level BDD correctly simplifies."""
        # nv
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        xid, yid, zid = enumerate_var(x), enumerate_var(y), enumerate_var(z)
        x_bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)
        y_bdd = make_node(yid, BDD_TRUE, BDD_FALSE, y)
        z_bdd = make_node(zid, BDD_TRUE, BDD_FALSE, z)

        # (X & Y) | Z
        and_bdd = apply('and', x_bdd, y_bdd)
        or_bdd = apply('or', and_bdd, z_bdd)

        # Restrict Z=1 → should be TRUE (Z=1 makes X&Y | Z always true)
        r = restrict(or_bdd, zid, 1)
        assert r is BDD_TRUE

        # Restrict Z=0 → should be X & Y
        r = restrict(or_bdd, zid, 0)
        # Verify: restrict further X=1,Y=1 → TRUE; X=1,Y=0 → FALSE
        assert restrict(r, xid, 1) is not BDD_FALSE or restrict(r, yid, 1) is not BDD_FALSE
        r_11 = restrict(restrict(r, xid, 1), yid, 1)
        r_10 = restrict(restrict(r, xid, 1), yid, 0)
        assert r_11 is BDD_TRUE
        assert r_10 is BDD_FALSE

    def test_restrict_preserves_other_vars(self):
        """Restricting var not in BDD leaves BDD unchanged."""
        # nv
        trail = fresh_trail()
        x = Var()
        xid = enumerate_var(x)
        unused = Var()
        unused_id = enumerate_var(unused)
        bdd = make_node(xid, BDD_TRUE, BDD_FALSE, x)

        r = restrict(bdd, unused_id, 1)
        # Should be identical (var not present, higher ID)
        # The result depends on whether unused_id > xid
        if unused_id > xid:
            assert r is bdd
        else:
            # If unused_id < xid, restrict returns bdd unchanged
            assert r is bdd
