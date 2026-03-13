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

from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.constraints import reify_eq, dif
from clausal.logic.clpfd import reify_fd, fd_eq, in_domain
from clausal.terms import Compound
from clausal.logic.predicate import PredicateMeta
from clausal.logic.database import Clause, Database
from clausal.logic.compiler import compile_predicate, compile_predicate_trampoline
from clausal.pythonic_ast.nodes import (
    IfExpr, Unify, DoesNotUnify, StructuralEq, StructuralNeq, Lt, LtE, Gt, GtE,
    And, Or, Not, Call, LoadName, In,
)


# ── reify_eq unit tests ──────────────────────────────────────────────────────


class TestReifyEq:
    """Test the three-valued reification decision procedure."""

    def test_identical_var(self):
        trail = Trail()
        x = Var()
        assert reify_eq(x, x, trail) is True

    def test_ground_equal_int(self):
        trail = Trail()
        assert reify_eq(1, 1, trail) is True

    def test_ground_equal_str(self):
        trail = Trail()
        assert reify_eq("hello", "hello", trail) is True

    def test_ground_incompatible_int(self):
        trail = Trail()
        assert reify_eq(1, 2, trail) is False

    def test_ground_incompatible_type(self):
        trail = Trail()
        assert reify_eq(1, "1", trail) is False

    def test_undetermined_var_int(self):
        trail = Trail()
        x = Var()
        assert reify_eq(x, 1, trail) is None

    def test_undetermined_int_var(self):
        trail = Trail()
        x = Var()
        assert reify_eq(1, x, trail) is None

    def test_undetermined_two_vars(self):
        trail = Trail()
        x = Var()
        y = Var()
        assert reify_eq(x, y, trail) is None

    def test_bound_var_ground_equal(self):
        trail = Trail()
        x = Var()
        unify(x, 42, trail)
        assert reify_eq(x, 42, trail) is True

    def test_bound_var_ground_inequal(self):
        trail = Trail()
        x = Var()
        unify(x, 42, trail)
        assert reify_eq(x, 99, trail) is False

    def test_compound_same(self):
        trail = Trail()
        a = Compound("f", (1, 2))
        b = Compound("f", (1, 2))
        assert reify_eq(a, b, trail) is True

    def test_compound_different(self):
        trail = Trail()
        a = Compound("f", (1, 2))
        b = Compound("f", (1, 3))
        assert reify_eq(a, b, trail) is False

    def test_compound_different_functor(self):
        trail = Trail()
        a = Compound("f", (1,))
        b = Compound("g", (1,))
        assert reify_eq(a, b, trail) is False

    def test_compound_with_var(self):
        trail = Trail()
        x = Var()
        a = Compound("f", (x, 2))
        b = Compound("f", (1, 2))
        assert reify_eq(a, b, trail) is None

    def test_predicate_meta_same(self):
        class point(metaclass=PredicateMeta):
            _fields = ("x", "y")

        trail = Trail()
        a = point(x=1, y=2)
        b = point(x=1, y=2)
        assert reify_eq(a, b, trail) is True

    def test_predicate_meta_different(self):
        class point(metaclass=PredicateMeta):
            _fields = ("x", "y")

        trail = Trail()
        a = point(x=1, y=2)
        b = point(x=1, y=3)
        assert reify_eq(a, b, trail) is False

    def test_list_same(self):
        trail = Trail()
        assert reify_eq([1, 2, 3], [1, 2, 3], trail) is True

    def test_list_different(self):
        trail = Trail()
        assert reify_eq([1, 2], [1, 3], trail) is False

    def test_list_with_var(self):
        trail = Trail()
        x = Var()
        assert reify_eq([1, x], [1, 2], trail) is None

    def test_no_side_effects(self):
        """reify_eq must not leave any bindings on the trail."""
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
        trail = Trail()
        assert reify_fd("eq", 3, 3, trail) is True

    def test_ground_eq_false(self):
        trail = Trail()
        assert reify_fd("eq", 3, 4, trail) is False

    def test_ground_lt_true(self):
        trail = Trail()
        assert reify_fd("lt", 2, 5, trail) is True

    def test_ground_lt_false(self):
        trail = Trail()
        assert reify_fd("lt", 5, 2, trail) is False

    def test_ground_ge_true(self):
        trail = Trail()
        assert reify_fd("ge", 5, 5, trail) is True

    def test_ground_ge_false(self):
        trail = Trail()
        assert reify_fd("ge", 4, 5, trail) is False

    def test_undetermined_with_var(self):
        trail = Trail()
        x = Var()
        assert reify_fd("eq", x, 3, trail) is None

    def test_undetermined_both_vars(self):
        trail = Trail()
        x = Var()
        y = Var()
        assert reify_fd("lt", x, y, trail) is None

    def test_ground_ne_true(self):
        trail = Trail()
        assert reify_fd("ne", 1, 2, trail) is True

    def test_ground_ne_false(self):
        trail = Trail()
        assert reify_fd("ne", 3, 3, trail) is False


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
        root = StepGenerator(fn, None, *args, trail)
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
        """If(1 is 1, result is 'yes', result is 'no') → 'yes'."""
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
        """If(1 is 2, result is 'yes', result is 'no') → 'no'."""
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
        """If(X is 1, result is 'eq', result is 'neq') with X unbound → both branches."""
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
        """If(1 is not 2, 'yes', 'no') → 'yes'."""
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
        """If(1 is not 1, 'yes', 'no') → 'no'."""
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
        """If(X is not 1, 'diff', 'same') with X unbound → both branches (swapped)."""
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

    def test_ground_lt_true(self):
        """If(2 < 5, 'yes', 'no') → 'yes'."""
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
        """If(5 < 2, 'yes', 'no') → 'no'."""
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
        """If(3 == 3, 'yes', 'no') → 'yes'."""
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=StructuralEq(left=3, right=3),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("yes",)]

    def test_ground_eq_false(self):
        """If(3 == 4, 'yes', 'no') → 'no'."""
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=StructuralEq(left=3, right=4),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple(clause)
        assert results == [("no",)]


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
        root = StepGenerator(fn, None, *args, trail)
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
        # We'll use In instead for simplicity: If(1 in [1,2,3], 'yes', 'no')
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=In(left=1, right=[1, 2, 3]),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple([clause])
        # In(1, [1,2,3]) succeeds (matches element 1), so then runs
        # But it also matches element 1 at position 0 only, then 2 and 3 don't match
        # Actually In is a for-loop that yields for each match.
        # 1 matches 1 → then runs once. 1 doesn't match 2,3.
        # So we get exactly one "yes"
        assert ("yes",) in results

    def test_failing_condition_simple(self):
        """If condition fails, run else branch."""
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=In(left=99, right=[1, 2, 3]),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_simple([clause])
        assert results == [("no",)]

    def test_succeeding_condition_trampoline(self):
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=In(left=1, right=[1, 2, 3]),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_trampoline([clause])
        assert ("yes",) in results

    def test_failing_condition_trampoline(self):
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=In(left=99, right=[1, 2, 3]),
                body=Unify(left=r, right="yes"),
                orelse=Unify(left=r, right="no"),
            )],
        )
        results = self._run_trampoline([clause])
        assert results == [("no",)]


class TestIteControlFlow:
    """Test ITE control flow: no-else, nesting, binding preservation."""

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

    def test_ite_without_else(self):
        """If without else → conjunction (if cond fails, whole goal fails)."""
        r = Var()
        # If(1 is 1, r is 'ok', None) → 'ok'
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Unify(left=1, right=1),
                body=Unify(left=r, right="ok"),
                orelse=None,
            )],
        )
        results = self._run_simple(clause)
        assert results == [("ok",)]

    def test_ite_without_else_fails(self):
        """If(failing_cond, then, None) → no solutions."""
        r = Var()
        clause = Clause(
            head=Compound("ite_test", (r,)),
            body=[IfExpr(
                test=Unify(left=1, right=2),
                body=Unify(left=r, right="ok"),
                orelse=None,
            )],
        )
        results = self._run_simple(clause)
        assert results == []

    def test_nested_ite(self):
        """If(c1, If(c2, a, b), c) with ground conditions."""
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
        """If(true, If(false, a, b), c)."""
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
        """ITE where then is a conjunction: If(cond, a and b, c)."""
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


# ── Import integration test ──────────────────────────────────────────────────


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
        mod = self._load_fixture("reified_max.clausal")
        from clausal.logic.solve import query

        logic_mod = mod.__dict__["$module"]

        l = Var()
        goal = Call(func=LoadName(name="classify"), args=[5, l], kwargs=[])
        results = list(query(goal, {"l": l}, logic_mod))
        labels = [r["l"] for r in results]
        assert "positive" in labels

        l2 = Var()
        goal2 = Call(func=LoadName(name="classify"), args=[-3, l2], kwargs=[])
        results2 = list(query(goal2, {"l": l2}, logic_mod))
        labels2 = [r["l"] for r in results2]
        assert "negative" in labels2
