"""Tests for V2-8: Reified If-Then-Else (pure monotonic branching).

Tests cover:
- reify_eq unit tests (three-valued decision procedure)
- reify_fd unit tests (CLP(FD) three-valued decision)
- Reified ITE with equality condition (simple + trampoline)
- Reified ITE with dif condition (simple + trampoline)
- Reified ITE with CLP(FD) conditions
- General ITE with predicate call condition
- ITE without else (→ conjunction)
- Nested ITE
- Integration: memberd via ITE, .clausal import
"""

import pytest

from clausal.logic.atoms import mint
from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.constraints import reify_eq, dif
from clausal.logic.clpfd import reify_fd, fd_eq, fd_lt, in_domain
from clausal.terms import Compound
from clausal.logic.predicate import PredicateMeta
from clausal.logic.database import Clause, Database
from clausal.logic.compiler import compile_predicate_shallow as compile_predicate, compile_predicate_trampoline
from clausal.pythonic_ast.nodes import (
    IfExpr, Unify, DoesNotUnify, ArithEq, ArithNeq, Lt, LtE, Gt, GtE,
    And, Or, Not, Call, LoadName, in_,
)


def _once(goal):
    """Helper: build a once(goal) Call node."""
    return Call(func=LoadName(name="once"), args=[goal], kwargs=[])


# ── reify_eq unit tests ──────────────────────────────────────────────────────


class TestReifyEq:
    """Test the three-valued reification decision procedure."""

    def test_identical_var(self):
        # nv
        trail = Trail()
        x = Var()
        assert reify_eq(x, x, trail) is True

    def test_ground_equal_int(self):
        # nv
        trail = Trail()
        assert reify_eq(1, 1, trail) is True

    def test_ground_equal_str(self):
        # nv
        trail = Trail()
        assert reify_eq("hello", "hello", trail) is True

    def test_ground_incompatible_int(self):
        # nv
        trail = Trail()
        assert reify_eq(1, 2, trail) is False

    def test_ground_incompatible_type(self):
        # nv
        trail = Trail()
        assert reify_eq(1, "1", trail) is False

    def test_undetermined_var_int(self):
        # nv
        trail = Trail()
        x = Var()
        assert reify_eq(x, 1, trail) is None

    def test_undetermined_int_var(self):
        # nv
        trail = Trail()
        x = Var()
        assert reify_eq(1, x, trail) is None

    def test_undetermined_two_vars(self):
        # nv
        trail = Trail()
        x = Var()
        y = Var()
        assert reify_eq(x, y, trail) is None

    def test_bound_var_ground_equal(self):
        # nv
        trail = Trail()
        x = Var()
        unify(x, 42, trail)
        assert reify_eq(x, 42, trail) is True

    def test_bound_var_ground_inequal(self):
        # nv
        trail = Trail()
        x = Var()
        unify(x, 42, trail)
        assert reify_eq(x, 99, trail) is False

    def test_compound_same(self):
        # nv
        trail = Trail()
        a = Compound("f", (1, 2))
        b = Compound("f", (1, 2))
        assert reify_eq(a, b, trail) is True

    def test_compound_different(self):
        # nv
        trail = Trail()
        a = Compound("f", (1, 2))
        b = Compound("f", (1, 3))
        assert reify_eq(a, b, trail) is False

    def test_compound_different_functor(self):
        # nv
        trail = Trail()
        a = Compound("f", (1,))
        b = Compound("g", (1,))
        assert reify_eq(a, b, trail) is False

    def test_compound_with_var(self):
        # nv
        trail = Trail()
        x = Var()
        a = Compound("f", (x, 2))
        b = Compound("f", (1, 2))
        assert reify_eq(a, b, trail) is None

    def test_predicate_meta_same(self):
        # nv
        class point(metaclass=PredicateMeta):
            _fields = ("x", "y")

        trail = Trail()
        a = point(x=1, y=2)
        b = point(x=1, y=2)
        assert reify_eq(a, b, trail) is True

    def test_predicate_meta_different(self):
        # nv
        class point(metaclass=PredicateMeta):
            _fields = ("x", "y")

        trail = Trail()
        a = point(x=1, y=2)
        b = point(x=1, y=3)
        assert reify_eq(a, b, trail) is False

    def test_list_same(self):
        # nv
        trail = Trail()
        assert reify_eq([1, 2, 3], [1, 2, 3], trail) is True

    def test_list_different(self):
        # nv
        trail = Trail()
        assert reify_eq([1, 2], [1, 3], trail) is False

    def test_list_with_var(self):
        # nv
        trail = Trail()
        x = Var()
        assert reify_eq([1, x], [1, 2], trail) is None

    def test_no_side_effects(self):
        """reify_eq must not leave any bindings on the trail."""
        # nv
        trail = Trail()
        x = Var()
        mark = trail.mark()
        reify_eq(x, 42, trail)
        assert is_var(deref(x)), "x should still be unbound"
        assert trail.mark() == mark, "trail should not have grown"


# ── reify_fd unit tests ──────────────────────────────────────────────────────


class TestReifyFd:
    """Test three-valued CLP(FD) reification."""

    def test_ground_eq_true(self):
        # nv
        trail = Trail()
        assert reify_fd("eq", 3, 3, trail) is True

    def test_ground_eq_false(self):
        # nv
        trail = Trail()
        assert reify_fd("eq", 3, 4, trail) is False

    def test_ground_lt_true(self):
        # nv
        trail = Trail()
        assert reify_fd("lt", 2, 5, trail) is True

    def test_ground_lt_false(self):
        # nv
        trail = Trail()
        assert reify_fd("lt", 5, 2, trail) is False

    def test_ground_ge_true(self):
        # nv
        trail = Trail()
        assert reify_fd("ge", 5, 5, trail) is True

    def test_ground_ge_false(self):
        # nv
        trail = Trail()
        assert reify_fd("ge", 4, 5, trail) is False

    def test_undetermined_with_var(self):
        # nv
        trail = Trail()
        x = Var()
        assert reify_fd("eq", x, 3, trail) is None

    def test_undetermined_both_vars(self):
        # nv
        trail = Trail()
        x = Var()
        y = Var()
        assert reify_fd("lt", x, y, trail) is None

    def test_ground_ne_true(self):
        # nv
        trail = Trail()
        assert reify_fd("ne", 1, 2, trail) is True

    def test_ground_ne_false(self):
        # nv
        trail = Trail()
        assert reify_fd("ne", 3, 3, trail) is False

    def test_ground_le_true(self):
        # nv
        trail = Trail()
        assert reify_fd("le", 3, 3, trail) is True

    def test_ground_le_false(self):
        # nv
        trail = Trail()
        assert reify_fd("le", 4, 3, trail) is False

    def test_ground_gt_true(self):
        # nv
        trail = Trail()
        assert reify_fd("gt", 5, 3, trail) is True

    def test_ground_gt_false(self):
        # nv
        trail = Trail()
        assert reify_fd("gt", 3, 5, trail) is False

    # `test_ground_ge_true` / `test_ground_ge_false` are defined earlier in
    # the class (lines ~202/207). Re-defining them here would shadow them
    # at class-creation time without adding coverage.

    def test_undetermined_fd_var_with_domain(self):
        """FD var with domain is still undetermined (not ground)."""
        # nv
        trail = Trail()
        x = Var()
        in_domain(x, 1, 10, trail)
        assert reify_fd("lt", x, 5, trail) is None

    def test_undetermined_both_fd_vars(self):
        """Both sides are FD vars → undetermined."""
        # nv
        trail = Trail()
        x = Var()
        y = Var()
        in_domain(x, 1, 10, trail)
        in_domain(y, 1, 10, trail)
        assert reify_fd("eq", x, y, trail) is None

    def test_bound_fd_var_becomes_ground(self):
        """FD var bound to integer → ground, deterministic result."""
        # nv
        trail = Trail()
        x = Var()
        in_domain(x, 1, 10, trail)
        unify(x, 3, trail)
        assert reify_fd("lt", x, 5, trail) is True
        assert reify_fd("gt", x, 5, trail) is False

    def test_no_side_effects(self):
        """reify_fd must not leave bindings or domain changes on the trail."""
        # nv
        trail = Trail()
        x = Var()
        in_domain(x, 1, 10, trail)
        mark = trail.mark()
        reify_fd("lt", x, 5, trail)
        assert trail.mark() == mark, "trail should not have grown"
        assert is_var(deref(x)), "x should still be unbound"


# ── Compiled reified ITE tests ───────────────────────────────────────────────


def _make_db():
    """Create a fresh Database for testing."""
    return Database()


def _compile_ite_clause(test, then, else_, head_args=None, arity=1):
    """Build a single clause with an ITE body and compile it."""
    if head_args is None:
        head_args = tuple(Var() for _ in range(arity))

    body = IfExpr(test=test, body=then, orelse=else_)
    head = Compound("ite_test", head_args)
    return Clause(head=head, body=[body])


class TestReifiedIteEquality:
    """Test reified ITE with equality (Unify) conditions."""

    def _run_simple(self, clause, arity=1):
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate("ite_test", arity, [clause], db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        for _ in fn(*args, trail, None):
            results.append(tuple(deref(a) for a in args))
        return results

    def _run_trampoline(self, clause, arity=1):
        from clausal.logic.trampoline import StepGenerator, DONE
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate_trampoline("ite_test", arity, [clause], db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        root = StepGenerator(fn, None, None, None, *args, trail)
        gen, value = root.send(None)
        while True:
            if gen is None:
                if value is DONE:
                    break
                results.append(tuple(deref(a) for a in args))
                gen, value = root.send(None)
            else:
                gen, value = gen.send(value)
        return results

    def test_ground_true_simple(self):
        """if_(1 is 1, result is 'yes', result is 'no') → 'yes'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Unify(left=1, right=1),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("yes",)]

    def test_ground_false_simple(self):
        """if_(1 is 2, result is 'yes', result is 'no') → 'no'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Unify(left=1, right=2),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("no",)]

    def test_undetermined_explores_both_simple(self):
        """if_(X is 1, result is 'eq', result is 'neq') with X unbound → both branches."""
        # nv
        x = Var()
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=Unify(left=x, right=1),
                body=Unify(left=r, right="eq"),
                orelse=Unify(left=r, right="neq"),
            )],
        )
        results = self._run_simple(clause, arity=2)
        # Should get both: X=1,R='eq' and X free with dif(X,1),R='neq'
        assert len(results) == 2
        assert results[0] == (1, "eq")
        assert results[1][1] == "neq"

    def test_ground_true_trampoline(self):
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Unify(left=1, right=1),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_trampoline(clause)
        assert results == [("yes",)]

    def test_ground_false_trampoline(self):
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Unify(left=1, right=2),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_trampoline(clause)
        assert results == [("no",)]

    def test_undetermined_explores_both_trampoline(self):
        # nv
        x = Var()
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=Unify(left=x, right=1),
                body=Unify(left=r, right="eq"),
                orelse=Unify(left=r, right="neq"),
            )],
        )
        results = self._run_trampoline(clause, arity=2)
        assert len(results) == 2
        assert results[0] == (1, "eq")
        assert results[1][1] == "neq"


class TestReifiedIteDif:
    """Test reified ITE with disequality (DoesNotUnify) conditions."""

    def _run_simple(self, clause, arity=1):
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate("ite_test", arity, [clause], db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        for _ in fn(*args, trail, None):
            results.append(tuple(deref(a) for a in args))
        return results

    def test_ground_dif_true(self):
        """if_(1 is not 2, 'yes', 'no') → 'yes'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=DoesNotUnify(left=1, right=2),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("yes",)]

    def test_ground_dif_false(self):
        """if_(1 is not 1, 'yes', 'no') → 'no'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=DoesNotUnify(left=1, right=1),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("no",)]

    def test_undetermined_dif(self):
        """if_(X is not 1, 'diff', 'same') with X unbound → both branches (swapped)."""
        # nv
        x = Var()
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=DoesNotUnify(left=x, right=1),
                body=Unify(left=r, right="diff"),
                orelse=Unify(left=r, right="same"),
            )],
        )
        results = self._run_simple(clause, arity=2)
        assert len(results) == 2
        # Swapped: dif-true→then(diff), dif-false(X=1)→else(same)
        # reify_eq returns None, swap=True means: True→else(same), False→then(diff)
        # undetermined: unify path→else(same), dif path→then(diff)
        # So we get: same (X=1), diff (dif(X,1))
        assert results[0] == (1, "same")
        assert results[1][1] == "diff"


class TestReifiedIteFd:
    """Test reified ITE with CLP(FD) conditions."""

    def _run_simple(self, clause, arity=1):
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate("ite_test", arity, [clause], db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        for _ in fn(*args, trail, None):
            results.append(tuple(deref(a) for a in args))
        return results

    def _run_trampoline(self, clause, arity=1):
        from clausal.logic.trampoline import StepGenerator, DONE
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate_trampoline("ite_test", arity, [clause], db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        root = StepGenerator(fn, None, None, None, *args, trail)
        gen, value = root.send(None)
        while True:
            if gen is None:
                if value is DONE:
                    break
                results.append(tuple(deref(a) for a in args))
                gen, value = root.send(None)
            else:
                gen, value = gen.send(value)
        return results

    # ── Ground tests: all operators ──

    def test_ground_lt_true(self):
        """if_(2 < 5, 'yes', 'no') → 'yes'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Lt(left=2, right=5),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("yes",)]

    def test_ground_lt_false(self):
        """if_(5 < 2, 'yes', 'no') → 'no'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Lt(left=5, right=2),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("no",)]

    def test_ground_eq_true(self):
        """if_(3 == 3, 'yes', 'no') → 'yes'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=ArithEq(left=3, right=3),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("yes",)]

    def test_ground_eq_false(self):
        """if_(3 == 4, 'yes', 'no') → 'no'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=ArithEq(left=3, right=4),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("no",)]

    def test_ground_ne_true(self):
        """if_(3 != 4, 'yes', 'no') → 'yes'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=ArithNeq(left=3, right=4),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("yes",)]

    def test_ground_ne_false(self):
        """if_(3 != 3, 'yes', 'no') → 'no'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=ArithNeq(left=3, right=3),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("no",)]

    def test_ground_le_true(self):
        """if_(3 <= 3, 'yes', 'no') → 'yes'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=LtE(left=3, right=3),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("yes",)]

    def test_ground_le_false(self):
        """if_(4 <= 3, 'yes', 'no') → 'no'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=LtE(left=4, right=3),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("no",)]

    def test_ground_gt_true(self):
        """if_(5 > 3, 'yes', 'no') → 'yes'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Gt(left=5, right=3),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("yes",)]

    def test_ground_gt_false(self):
        """if_(3 > 5, 'yes', 'no') → 'no'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Gt(left=3, right=5),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("no",)]

    def test_ground_ge_true(self):
        """if_(5 >= 5, 'yes', 'no') → 'yes'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=GtE(left=5, right=5),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("yes",)]

    def test_ground_ge_false(self):
        """if_(4 >= 5, 'yes', 'no') → 'no'."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=GtE(left=4, right=5),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("no",)]

    # ── Trampoline mode: ground FD tests ──

    def test_ground_lt_true_trampoline(self):
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Lt(left=2, right=5),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_trampoline(clause)
        assert results == [("yes",)]

    def test_ground_lt_false_trampoline(self):
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Lt(left=5, right=2),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_trampoline(clause)
        assert results == [("no",)]

    def test_ground_ge_true_trampoline(self):
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=GtE(left=5, right=5),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_trampoline(clause)
        assert results == [("yes",)]

    def test_ground_ne_true_trampoline(self):
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=ArithNeq(left=1, right=2),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_trampoline(clause)
        assert results == [("yes",)]

    # ── Undetermined: FD var tests (both branches explored) ──

    def test_undetermined_lt_explores_both(self):
        """if_(X < 5, 'lo', 'hi') with X as FD var [1..10] → both branches."""
        # nv
        x = Var()
        r = Var()
        trail = Trail()
        in_domain(x, 1, 10, trail)
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=Lt(left=x, right=5),
                body=Unify(left=r, right="lo"),
                orelse=Unify(left=r, right="hi"),
            )],
        )
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate("ite_test", 2, [clause], db)
        results = []
        for _ in fn(x, r, trail, None):
            results.append((deref(x), deref(r)))
        # Undetermined: reify_fd returns None, both branches should be explored
        # fd_lt path: X < 5 constrained → 'lo'
        # fd_ge path: X >= 5 constrained → 'hi'
        labels = [r for _, r in results]
        assert "lo" in labels
        assert "hi" in labels

    def test_undetermined_eq_explores_both(self):
        """if_(X == 3, 'hit', 'miss') with FD var X [1..5] → both branches."""
        # nv
        x = Var()
        r = Var()
        trail = Trail()
        in_domain(x, 1, 5, trail)
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=ArithEq(left=x, right=3),
                body=Unify(left=r, right="hit"),
                orelse=Unify(left=r, right="miss"),
            )],
        )
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate("ite_test", 2, [clause], db)
        results = []
        for _ in fn(x, r, trail, None):
            results.append((deref(x), deref(r)))
        labels = [r for _, r in results]
        assert "hit" in labels
        assert "miss" in labels

    def test_undetermined_ge_explores_both_trampoline(self):
        """if_(X >= 5, 'hi', 'lo') with FD var X [1..10] in trampoline mode."""
        # nv
        from clausal.logic.trampoline import StepGenerator, DONE
        x = Var()
        r = Var()
        trail = Trail()
        in_domain(x, 1, 10, trail)
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=GtE(left=x, right=5),
                body=Unify(left=r, right="hi"),
                orelse=Unify(left=r, right="lo"),
            )],
        )
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate_trampoline("ite_test", 2, [clause], db)
        results = []
        root = StepGenerator(fn, None, None, None, x, r, trail)
        gen, value = root.send(None)
        while True:
            if gen is None:
                if value is DONE:
                    break
                results.append((deref(x), deref(r)))
                gen, value = root.send(None)
            else:
                gen, value = gen.send(value)
        labels = [r for _, r in results]
        assert "hi" in labels
        assert "lo" in labels

    # ── FD reification + labeling integration ──

    def test_fd_ite_then_label(self):
        """if_(X < 5, R is 'lo', R is 'hi') then label X — correct domain restriction."""
        # nv
        from clausal.logic.clpfd import label as fd_label
        x = Var()
        r = Var()
        trail = Trail()
        in_domain(x, 1, 8, trail)
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=Lt(left=x, right=5),
                body=Unify(left=r, right="lo"),
                orelse=Unify(left=r, right="hi"),
            )],
        )
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate("ite_test", 2, [clause], db)
        lo_vals = []
        hi_vals = []
        for _ in fn(x, r, trail, None):
            dx, dr = deref(x), deref(r)
            if dr == "lo":
                # X should be constrained to < 5 (i.e., 1..4)
                # label to enumerate concrete values
                m = trail.mark()
                for _ in fd_label([x], trail):
                    lo_vals.append(deref(x))
                trail.undo(m)
            elif dr == "hi":
                m = trail.mark()
                for _ in fd_label([x], trail):
                    hi_vals.append(deref(x))
                trail.undo(m)
        # lo branch: X constrained < 5, domain [1..4]
        if lo_vals:
            assert all(v < 5 for v in lo_vals), f"lo branch values should be < 5: {lo_vals}"
        # hi branch: X constrained >= 5, domain [5..8]
        if hi_vals:
            assert all(v >= 5 for v in hi_vals), f"hi branch values should be >= 5: {hi_vals}"
        # At least one branch should have produced values
        assert lo_vals or hi_vals

    # ── Nested FD ITE ──

    def test_nested_fd_ite(self):
        """if_(X < 10, if_(X > 5, 'mid', 'lo'), 'hi') — nested FD conditions."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Lt(left=3, right=10),
                body=IfExpr(
                    test=Gt(left=3, right=5),
                    body=Unify(left=r, right="mid"),
                    orelse=Unify(left=r, right="lo"),
                ),
                orelse=Unify(left=r, right="hi"),
            )],
        )
        results = self._run_simple(clause)
        # 3 < 10 → true, 3 > 5 → false → "lo"
        assert results == [("lo",)]


class TestGeneralIte:
    """Test general ITE with non-reifiable conditions (predicate calls)."""

    def _run_simple(self, clauses, arity=1):
        db = _make_db()
        functor = "ite_test"
        for c in clauses:
            db.assertz(c)
        fn = compile_predicate(functor, arity, clauses, db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        for _ in fn(*args, trail, None):
            results.append(tuple(deref(a) for a in args))
        return results

    def _run_trampoline(self, clauses, arity=1):
        from clausal.logic.trampoline import StepGenerator, DONE
        db = _make_db()
        functor = "ite_test"
        for c in clauses:
            db.assertz(c)
        fn = compile_predicate_trampoline(functor, arity, clauses, db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        root = StepGenerator(fn, None, None, None, *args, trail)
        gen, value = root.send(None)
        while True:
            if gen is None:
                if value is DONE:
                    break
                results.append(tuple(deref(a) for a in args))
                gen, value = root.send(None)
            else:
                gen, value = gen.send(value)
        return results

    def test_succeeding_condition_simple(self):
        """If condition succeeds, run then branch."""
        # member/2: member(X, [X|_]). member(X, [_|T]) :- member(X, T).
        # We'll use in_ instead for simplicity: if_(1 in [1,2,3], 'yes', 'no')
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=in_(left=1, right=[1, 2, 3]),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple([clause])
        # in_(1, [1,2,3]) succeeds (matches element 1), so then runs
        # But it also matches element 1 at position 0 only, then 2 and 3 don't match
        # Actually in_ is a for-loop that yields for each match.
        # 1 matches 1 → then runs once. 1 doesn't match 2,3.
        # So we get exactly one "yes"
        assert ("yes",) in results

    def test_failing_condition_simple(self):
        """If condition fails, run else branch."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=in_(left=99, right=[1, 2, 3]),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple([clause])
        assert results == [("no",)]

    def test_succeeding_condition_trampoline(self):
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=in_(left=1, right=[1, 2, 3]),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_trampoline([clause])
        assert ("yes",) in results

    def test_failing_condition_trampoline(self):
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=in_(left=99, right=[1, 2, 3]),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_trampoline([clause])
        assert results == [("no",)]


class TestIteControlFlow:
    """Test ITE control flow: nesting, binding preservation."""

    def _run_simple(self, clause, arity=1):
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate("ite_test", arity, [clause], db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        for _ in fn(*args, trail, None):
            results.append(tuple(deref(a) for a in args))
        return results

    def test_nested_ite(self):
        """if_(c1, if_(c2, a, b), c) with ground conditions."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Unify(left=1, right=1),
                body=IfExpr(
                    test=Unify(left=2, right=2),
                    body=Unify(left=r, right="both_true"),
                    orelse=Unify(left=r, right="first_only"),
                ),
                orelse=Unify(left=r, right="none"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("both_true",)]

    def test_nested_ite_inner_false(self):
        """if_(true, if_(false, a, b), c)."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Unify(left=1, right=1),
                body=IfExpr(
                    test=Unify(left=1, right=2),
                    body=Unify(left=r, right="both_true"),
                    orelse=Unify(left=r, right="first_only"),
                ),
                orelse=Unify(left=r, right="none"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("first_only",)]

    def test_ite_preserves_bindings(self):
        """Undetermined ITE: then path binds X, else path leaves X free with dif."""
        # nv
        x = Var()
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=Unify(left=x, right=42),
                body=Unify(left=r, right="bound"),
                orelse=Unify(left=r, right="free"),
            )],
        )
        results = self._run_simple(clause, arity=2)
        # First result: x=42, r='bound'
        assert results[0] == (42, "bound")
        # Second result: x still has dif(x,42), r='free'
        assert results[1][1] == "free"

    def test_ite_with_conjunction_body(self):
        """ITE where then is a conjunction: if_(cond, a and b, c)."""
        # nv
        x = Var()
        y = Var()
        clause = Clause(
            head=Compound("ite_test", (x, y)),
            body=[IfExpr(
                test=Unify(left=1, right=1),
                body=And(
                    left=Unify(left=x, right="a"),
                    right=Unify(left=y, right="b"),
                ),
                orelse=Unify(left=x, right="fail"),
            )],
        )
        results = self._run_simple(clause, arity=2)
        assert results == [("a", "b")]


# ── Multi-solution general ITE ────────────────────────────────────────────────


class TestGeneralIteMultiSolution:
    """Test general ITE with conditions that yield multiple solutions."""

    def _run_simple(self, clause, arity=1):
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate("ite_test", arity, [clause], db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        for _ in fn(*args, trail, None):
            results.append(tuple(deref(a) for a in args))
        return results

    def _run_trampoline(self, clause, arity=1):
        from clausal.logic.trampoline import StepGenerator, DONE
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate_trampoline("ite_test", arity, [clause], db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        root = StepGenerator(fn, None, None, None, *args, trail)
        gen, value = root.send(None)
        while True:
            if gen is None:
                if value is DONE:
                    break
                results.append(tuple(deref(a) for a in args))
                gen, value = root.send(None)
            else:
                gen, value = gen.send(value)
        return results

    def test_multi_solution_runs_then_for_each(self):
        """if_(X in [1,2,3], R is X, R is 'none') → then runs 3 times."""
        # nv
        x = Var()
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=in_(left=x, right=[1, 2, 3]),
                body=Unify(left=r, right=x),
                orelse=Unify(left=r, right="none"),
            )],
        )
        results = self._run_simple(clause, arity=2)
        # Condition matches 3 times (X=1, X=2, X=3), then branch runs for each
        then_results = [(a, b) for a, b in results if b != "none"]
        assert len(then_results) == 3
        vals = {a for a, _ in then_results}
        assert vals == {1, 2, 3}

    def test_multi_solution_then_for_each_trampoline(self):
        """Same multi-solution test in trampoline mode."""
        # nv
        x = Var()
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=in_(left=x, right=[1, 2, 3]),
                body=Unify(left=r, right=x),
                orelse=Unify(left=r, right="none"),
            )],
        )
        results = self._run_trampoline(clause, arity=2)
        then_results = [(a, b) for a, b in results if b != "none"]
        assert len(then_results) == 3

    def test_general_ite_preserves_condition_bindings(self):
        """General ITE: bindings from condition survive into then branch."""
        # nv
        x = Var()
        r = Var()
        # if_(X in [10, 20], R is X, R is 0) — then branch sees X bound by condition
        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=in_(left=x, right=[10, 20]),
                body=Unify(left=r, right=x),
                orelse=Unify(left=r, right=0),
            )],
        )
        results = self._run_simple(clause, arity=2)
        then_results = [(a, b) for a, b in results if b != 0]
        # Each then result should have R == X (bound by condition)
        for a, b in then_results:
            assert a == b, f"then branch should see X={a} bound by condition, got R={b}"


# ── ITE + dif/2 interaction ──────────────────────────────────────────────────


class TestIteDifInteraction:
    """Test ITE interacting with pre-existing dif constraints."""

    def _run_simple(self, clause, arity, args, trail):
        db = _make_db()
        db.assertz(clause)
        fn = compile_predicate("ite_test", arity, [clause], db)
        results = []
        for _ in fn(*args, trail, None):
            results.append(tuple(deref(a) for a in args))
        return results

    def test_undetermined_ite_with_preexisting_dif(self):
        """dif(X, 1) before if_(X is 1, then, else) → only else branch."""
        # nv
        x = Var()
        r = Var()
        trail = Trail()
        # Constrain X != 1 before the ITE
        assert dif(x, 1, trail)

        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=Unify(left=x, right=1),
                body=Unify(left=r, right="eq"),
                orelse=Unify(left=r, right="neq"),
            )],
        )
        results = self._run_simple(clause, 2, [x, r], trail)
        # X already has dif(X, 1), so reify_eq returns None (undetermined),
        # but the unify(X, 1) path in the undetermined branch fails because
        # dif constraint blocks it. Only else branch produces a result.
        labels = [b for _, b in results]
        assert "neq" in labels
        assert "eq" not in labels

    def test_undetermined_ite_with_dif_still_explores_both_when_compatible(self):
        """dif(X, 2) before if_(X is 1, then, else) → both branches (dif doesn't block)."""
        # nv
        x = Var()
        r = Var()
        trail = Trail()
        assert dif(x, 2, trail)

        clause = Clause(
            head=Compound("ite_test", (x, r)),
            body=[IfExpr(
                test=Unify(left=x, right=1),
                body=Unify(left=r, right="eq"),
                orelse=Unify(left=r, right="neq"),
            )],
        )
        results = self._run_simple(clause, 2, [x, r], trail)
        # dif(X, 2) doesn't block X=1, so both branches explored
        labels = [b for _, b in results]
        assert "eq" in labels
        assert "neq" in labels


# ── Tabled predicate as ITE condition ────────────────────────────────────────


class TestTabledIteCondition:
    """Test ITE where the condition is a call to a tabled predicate."""

    def _load_fixture(self, filename):
        import os
        from clausal.import_hook import _load_module
        path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
        name = f"_test_fixture_{filename.replace('.', '_')}"
        return _load_module(name, path)

    def test_tabled_condition_succeeds(self):
        """check_path(3, R) with tabled path(1,3) reachable → 'reachable'."""
        # nv
        mod = self._load_fixture("tabled_ite.clausal")
        from clausal.logic.solve import query

        logic_mod = mod.__dict__["$module"]
        r = Var()
        goal = Call(func=LoadName(name="CheckPath"), args=[3, r], kwargs=[])
        results = list(query(goal, {"r": r}, logic_mod))
        labels = [res["r"] for res in results]
        assert mint("reachable") in labels

    def test_tabled_condition_fails(self):
        """check_path(99, R) with tabled path(1,99) unreachable → 'unreachable'."""
        # nv
        mod = self._load_fixture("tabled_ite.clausal")
        from clausal.logic.solve import query

        logic_mod = mod.__dict__["$module"]
        r = Var()
        goal = Call(func=LoadName(name="CheckPath"), args=[99, r], kwargs=[])
        results = list(query(goal, {"r": r}, logic_mod))
        labels = [res["r"] for res in results]
        assert mint("unreachable") in labels
        assert mint("reachable") not in labels


# ── Import integration tests ─────────────────────────────────────────────────


class TestIteImportIntegration:
    """Test ITE via .clausal file import."""

    def _load_fixture(self, filename):
        import os
        from clausal.import_hook import _load_module
        path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
        name = f"_test_fixture_{filename.replace('.', '_')}"
        return _load_module(name, path)

    def test_classify_ground(self):
        """Import classify predicate and query with ground values."""
        # nv
        mod = self._load_fixture("reified_max.clausal")
        from clausal.logic.solve import query

        logic_mod = mod.__dict__["$module"]

        l = Var()
        goal = Call(func=LoadName(name="Classify"), args=[5, l], kwargs=[])
        results = list(query(goal, {"l": l}, logic_mod))
        labels = [r["l"] for r in results]
        assert mint("positive") in labels

        l2 = Var()
        goal2 = Call(func=LoadName(name="Classify"), args=[-3, l2], kwargs=[])
        results2 = list(query(goal2, {"l": l2}, logic_mod))
        labels2 = [r["l"] for r in results2]
        assert mint("negative") in labels2

    def test_memberd_ground_deterministic(self):
        """memberd(1, [1,2,3]) — ground query is deterministic (one solution, no duplicates).

        This is the key example from Neumerkel & Kral §6: reified membership
        eliminates leftover choicepoints for ground queries.
        """
        # nv
        mod = self._load_fixture("reified_memberd.clausal")
        from clausal.logic.solve import query

        logic_mod = mod.__dict__["$module"]

        goal = Call(func=LoadName(name="Memberd"), args=[1, [1, 2, 3]], kwargs=[])
        results = list(query(goal, {}, logic_mod))
        # Ground element present → exactly one solution (deterministic)
        assert len(results) == 1

    def test_memberd_ground_absent(self):
        """memberd(99, [1,2,3]) — ground element not in list → no solutions."""
        # nv
        mod = self._load_fixture("reified_memberd.clausal")
        from clausal.logic.solve import query

        logic_mod = mod.__dict__["$module"]

        goal = Call(func=LoadName(name="Memberd"), args=[99, [1, 2, 3]], kwargs=[])
        results = list(query(goal, {}, logic_mod))
        assert len(results) == 0

    def test_memberd_unbound_enumerates(self):
        """memberd(X, [a, b, c]) — unbound X enumerates all elements."""
        # nv
        mod = self._load_fixture("reified_memberd.clausal")
        from clausal.logic.solve import query

        logic_mod = mod.__dict__["$module"]

        x = Var()
        goal = Call(func=LoadName(name="Memberd"), args=[x, ["a", "b", "c"]], kwargs=[])
        results = list(query(goal, {"x": x}, logic_mod))
        vals = {r["x"] for r in results}
        assert vals == {"a", "b", "c"}

    def test_memberd_no_duplicates(self):
        """memberd(X, [1,1,2]) — repeated elements: each unique value once.

        Unlike standard member/2 which yields 1 twice, memberd with dif
        constraints should yield 1 once and 2 once.
        """
        # nv
        mod = self._load_fixture("reified_memberd.clausal")
        from clausal.logic.solve import query

        logic_mod = mod.__dict__["$module"]

        x = Var()
        goal = Call(func=LoadName(name="Memberd"), args=[x, [1, 1, 2]], kwargs=[])
        results = list(query(goal, {"x": x}, logic_mod))
        vals = [r["x"] for r in results]
        # Should not yield duplicate 1s
        assert vals.count(1) == 1
        assert 2 in vals


# ── once() tests ─────────────────────────────────────────────────────────────


class TestOnce:
    """Test once(goal) — commit to first solution."""

    def _run_simple(self, clauses, arity=1):
        db = _make_db()
        for c in clauses:
            db.assertz(c)
        fn = compile_predicate("once_test", arity, clauses, db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        for _ in fn(*args, trail, None):
            results.append(tuple(deref(a) for a in args))
        return results

    def _run_trampoline(self, clauses, arity=1):
        from clausal.logic.trampoline import StepGenerator, DONE
        db = _make_db()
        for c in clauses:
            db.assertz(c)
        fn = compile_predicate_trampoline("once_test", arity, clauses, db)
        trail = Trail()
        results = []
        args = [Var() for _ in range(arity)]
        root = StepGenerator(fn, None, None, None, *args, trail)
        gen, value = root.send(None)
        while True:
            if gen is None:
                if value is DONE:
                    break
                results.append(tuple(deref(a) for a in args))
                gen, value = root.send(None)
            else:
                gen, value = gen.send(value)
        return results

    def test_once_takes_first_solution_simple(self):
        """once(X in [1,2,3]) should produce only X=1."""
        # nv
        x = Var()
        clause = Clause(
            head=Compound("once_test", (x,)),
            body=[_once(in_(left=x, right=[1, 2, 3]))],
        )
        results = self._run_simple([clause])
        assert results == [(1,)]

    def test_once_takes_first_solution_trampoline(self):
        """once(X in [1,2,3]) should produce only X=1."""
        # nv
        x = Var()
        clause = Clause(
            head=Compound("once_test", (x,)),
            body=[_once(in_(left=x, right=[1, 2, 3]))],
        )
        results = self._run_trampoline([clause])
        assert results == [(1,)]

    def test_once_failing_goal_simple(self):
        """once(99 in [1,2,3]) — failing goal produces no results."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("once_test", (r,)),
            body=[
                _once(in_(left=99, right=[1, 2, 3])),
                Unify(left=r, right="reached"),
            ],
        )
        results = self._run_simple([clause])
        assert results == []

    def test_once_failing_goal_trampoline(self):
        """once(99 in [1,2,3]) — failing goal produces no results."""
        # nv
        r = Var()
        clause = Clause(
            head=Compound("once_test", (r,)),
            body=[
                _once(in_(left=99, right=[1, 2, 3])),
                Unify(left=r, right="reached"),
            ],
        )
        results = self._run_trampoline([clause])
        assert results == []

    def test_once_with_continuation_simple(self):
        """once(X in [1,2]) and Y in [a,b] — once limits first goal,
        continuation still backtracks normally."""
        # nv
        x, y = Var(), Var()
        clause = Clause(
            head=Compound("once_test", (x, y)),
            body=[
                _once(in_(left=x, right=[1, 2])),
                in_(left=y, right=["a", "b"]),
            ],
        )
        results = self._run_simple([clause], arity=2)
        # X=1 only (once), but Y backtracks: (1,"a"), (1,"b")
        assert results == [(1, "a"), (1, "b")]

    def test_once_with_continuation_trampoline(self):
        # nv
        x, y = Var(), Var()
        clause = Clause(
            head=Compound("once_test", (x, y)),
            body=[
                _once(in_(left=x, right=[1, 2])),
                in_(left=y, right=["a", "b"]),
            ],
        )
        results = self._run_trampoline([clause], arity=2)
        assert results == [(1, "a"), (1, "b")]

    def test_once_preserves_bindings_simple(self):
        """Bindings from the once'd goal are visible in continuation."""
        # nv
        x, r = Var(), Var()
        clause = Clause(
            head=Compound("once_test", (r,)),
            body=[
                _once(Unify(left=x, right=42)),
                Unify(left=r, right=x),
            ],
        )
        results = self._run_simple([clause])
        assert results == [(42,)]

    def test_once_preserves_bindings_trampoline(self):
        # nv
        x, r = Var(), Var()
        clause = Clause(
            head=Compound("once_test", (r,)),
            body=[
                _once(Unify(left=x, right=42)),
                Unify(left=r, right=x),
            ],
        )
        results = self._run_trampoline([clause])
        assert results == [(42,)]

    def test_once_in_if_condition_simple(self):
        """if_(once(X in [1,2,3]), then, else) — once inside if_ condition."""
        # nv
        r = Var()
        x = Var()
        clause = Clause(
            head=Compound("once_test", (r,)),
            body=[IfExpr(
                test=_once(in_(left=x, right=[1, 2, 3])),
                body=Unify(left=r, right="found"),
                orelse=Unify(left=r, right="not_found"),
            )],
        )
        results = self._run_simple([clause])
        assert ("found",) in results

    def test_once_in_if_condition_trampoline(self):
        # nv
        r = Var()
        x = Var()
        clause = Clause(
            head=Compound("once_test", (r,)),
            body=[IfExpr(
                test=_once(in_(left=x, right=[1, 2, 3])),
                body=Unify(left=r, right="found"),
                orelse=Unify(left=r, right="not_found"),
            )],
        )
        results = self._run_trampoline([clause])
        assert ("found",) in results


class TestOnceClausal:
    """Test once() via .clausal file import."""

    def test_once_clausal_import(self):
        """once() works when used in a .clausal file."""
        # nv
        import importlib
        import os
        from clausal.import_hook import _load_module

        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "once_member.clausal"
        )
        if not os.path.exists(fixture):
            pytest.skip("once_member.clausal fixture not created yet")
        mod = _load_module("once_member", fixture)
        from clausal.logic.solve import query

        logic_mod = mod.__dict__["$module"]
        x = Var()
        goal = Call(func=LoadName(name="FirstMember"), args=[x, [10, 20, 30]], kwargs=[])
        results = list(query(goal, {"x": x}, logic_mod))
        assert len(results) == 1
        assert results[0]["x"] == 10
