"""Tests for V2-5: dif/2 via attributed variables.

Tests the disequality constraint (``is not`` / ``dif/2``) which uses the
AttVar infrastructure to lazily check that two terms remain different.
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var, put_attr, get_attr
from clausal.logic.constraints import dif, _collect_free_vars, DIF_KEY
from clausal.logic.compiler import compile_predicate_trampoline as compile_predicate
from clausal.logic.database import Clause, Database, Module
from clausal.logic.solve import solve, once, query
from clausal.logic.trampoline import StepGenerator, DONE
from clausal.terms import (
    Compound, And,
    Unify as Is, DoesNotUnify as IsNot, Evaluate,
    Call, LoadName,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def fresh_trail() -> Trail:
    return Trail()


def solutions_simple(fn, *args_trail_extract):
    """Call a simple-mode dispatch fn and collect results."""
    *args, trail, extract = args_trail_extract
    results = []
    for _ in fn(*args, trail, []):
        results.append(extract())
    return results


def _drive_trampoline(dispatch_fn, trail):
    """Drive a trampoline dispatch fn, yielding after each solution."""
    sg = StepGenerator(dispatch_fn, None, None, None, trail)
    gen, value = sg.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return
            yield trail
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)


def solutions_trampoline(dispatch_fn, trail, extract):
    """Drive trampoline and collect extracted values at each solution."""
    results = []
    for _ in _drive_trampoline(dispatch_fn, trail):
        results.append(extract())
    return results


# ── Unit: _collect_free_vars ──────────────────────────────────────────────────


class TestCollectFreeVars:

    def test_scalar(self):
        # nv
        assert _collect_free_vars(42) == []

    def test_string(self):
        # nv
        assert _collect_free_vars("hello") == []

    def test_single_var(self):
        # nv
        x = Var()
        result = _collect_free_vars(x)
        assert len(result) == 1
        assert result[0] is x

    def test_bound_var_not_collected(self):
        # nv
        x = Var()
        t = fresh_trail()
        unify(x, 42, t)
        assert _collect_free_vars(x) == []

    def test_tuple_with_vars(self):
        # nv
        x, y = Var(), Var()
        result = _collect_free_vars((x, 1, y))
        assert len(result) == 2
        ids = {id(v) for v in result}
        assert id(x) in ids and id(y) in ids

    def test_list_with_vars(self):
        # nv
        x = Var()
        result = _collect_free_vars([1, x, 3])
        assert len(result) == 1
        assert result[0] is x

    def test_compound_with_vars(self):
        # nv
        x, y = Var(), Var()
        c = Compound("f", (x, 42, y))
        result = _collect_free_vars(c)
        assert len(result) == 2

    def test_nested_structures(self):
        # nv
        x = Var()
        c = Compound("f", ([1, (x, 2)],))
        result = _collect_free_vars(c)
        assert len(result) == 1
        assert result[0] is x

    def test_dedup_same_var(self):
        # nv
        x = Var()
        result = _collect_free_vars((x, x, x))
        assert len(result) == 1


# ── Unit: dif directly ───────────────────────────────────────────────────────


class TestDifDirect:

    def test_ground_equal_fails(self):
        # nv
        t = fresh_trail()
        assert dif(1, 1, t) is False

    def test_ground_different_succeeds(self):
        # nv
        t = fresh_trail()
        assert dif(1, 2, t) is True

    def test_ground_string_different(self):
        # nv
        t = fresh_trail()
        assert dif("a", "b", t) is True

    def test_ground_string_equal_fails(self):
        # nv
        t = fresh_trail()
        assert dif("a", "a", t) is False

    def test_same_var_fails(self):
        """dif(X, X) where X is the same var → False (always identical)."""
        # nv
        t = fresh_trail()
        x = Var()
        assert dif(x, x, t) is False

    def test_one_var_posts_constraint(self):
        """dif(X, 1) with unbound X → True (constraint posted)."""
        # nv
        t = fresh_trail()
        x = Var()
        assert dif(x, 1, t) is True
        attrs = get_attr(x, DIF_KEY)
        assert attrs is not None
        assert len(attrs) == 1

    def test_both_vars_posts_constraint(self):
        """dif(X, Y) with both unbound → True (constraint on both)."""
        # nv
        t = fresh_trail()
        x, y = Var(), Var()
        assert dif(x, y, t) is True
        assert get_attr(x, DIF_KEY) is not None
        assert get_attr(y, DIF_KEY) is not None

    def test_compound_structurally_different(self):
        # nv
        t = fresh_trail()
        assert dif(Compound("f", (1,)), Compound("g", (1,)), t) is True

    def test_compound_structurally_equal_fails(self):
        # nv
        t = fresh_trail()
        assert dif(Compound("f", (1,)), Compound("f", (1,)), t) is False


# ── Occurs check ─────────────────────────────────────────────────────────────


class TestDifOccursCheck:

    def test_var_vs_compound_containing_it(self):
        """dif(X, f(X)) → True — X can never equal f(X)."""
        # nv
        t = fresh_trail()
        x = Var()
        assert dif(x, Compound("f", (x,)), t) is True


# ── Constraint propagation ───────────────────────────────────────────────────


class TestDifPropagation:

    def test_dif_then_same_value_fails(self):
        """dif(X, Y), X=1, Y=1 → unification of Y=1 should fail."""
        # nv
        t = fresh_trail()
        x, y = Var(), Var()
        assert dif(x, y, t) is True
        assert unify(x, 1, t) is True  # X=1, constraint re-checked
        assert unify(y, 1, t) is False  # Y=1 violates dif

    def test_dif_then_different_values_succeeds(self):
        """dif(X, Y), X=1, Y=2 → succeeds."""
        # nv
        t = fresh_trail()
        x, y = Var(), Var()
        assert dif(x, y, t) is True
        assert unify(x, 1, t) is True
        assert unify(y, 2, t) is True

    def test_dif_var_ground_then_bind_same(self):
        """dif(X, 1), X=1 → fails."""
        # nv
        t = fresh_trail()
        x = Var()
        assert dif(x, 1, t) is True
        assert unify(x, 1, t) is False

    def test_dif_var_ground_then_bind_different(self):
        """dif(X, 1), X=2 → succeeds."""
        # nv
        t = fresh_trail()
        x = Var()
        assert dif(x, 1, t) is True
        assert unify(x, 2, t) is True

    def test_multiple_constraints_on_same_var(self):
        """dif(X, 1), dif(X, 2) — X=1 fails, X=2 fails, X=3 succeeds."""
        # nv
        t = fresh_trail()
        x = Var()
        assert dif(x, 1, t) is True
        assert dif(x, 2, t) is True

        # X=1 should fail
        mark = t.mark()
        assert unify(x, 1, t) is False
        t.undo(mark)

        # X=2 should fail
        mark = t.mark()
        assert unify(x, 2, t) is False
        t.undo(mark)

        # X=3 should succeed
        assert unify(x, 3, t) is True

    def test_compound_args_constraint(self):
        """dif(f(X), f(Y)) — constraint on X,Y; violation when X=Y."""
        # nv
        t = fresh_trail()
        x, y = Var(), Var()
        assert dif(Compound("f", (x,)), Compound("f", (y,)), t) is True
        assert unify(x, 1, t) is True
        assert unify(y, 1, t) is False  # f(1) = f(1) violates dif

    def test_compound_args_different_ok(self):
        """dif(f(X), f(Y)), X=1, Y=2 → succeeds."""
        # nv
        t = fresh_trail()
        x, y = Var(), Var()
        assert dif(Compound("f", (x,)), Compound("f", (y,)), t) is True
        assert unify(x, 1, t) is True
        assert unify(y, 2, t) is True

    def test_transitive_via_shared_var(self):
        """dif(X, Y), X=Z, Y=Z → fails (X and Y become equal through Z)."""
        # nv
        t = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert dif(x, y, t) is True
        assert unify(x, z, t) is True
        assert unify(y, z, t) is False


# ── Backtracking ─────────────────────────────────────────────────────────────


class TestDifBacktracking:

    def test_constraint_undone_on_trail_undo(self):
        """Constraint attachment is trailed — undo removes constraint."""
        # nv
        t = fresh_trail()
        x = Var()
        mark = t.mark()
        assert dif(x, 1, t) is True
        assert get_attr(x, DIF_KEY) is not None
        t.undo(mark)
        # After undo, the constraint should be gone
        assert get_attr(x, DIF_KEY) is None

    def test_binding_failure_doesnt_corrupt_trail(self):
        """After dif(X, 1), unify(X, 1) fails — X is still free."""
        # nv
        t = fresh_trail()
        x = Var()
        dif(x, 1, t)
        mark = t.mark()
        assert unify(x, 1, t) is False
        t.undo(mark)
        assert is_var(deref(x))


# ── Integration via compiler ─────────────────────────────────────────────────


class TestDifCompiled:

    def test_is_not_dif_semantics_via_solve(self):
        """X_ is not Y_, X_ is 1, Y_ is 2 → succeeds via solve API."""
        # nv
        mod = Module("test_dif_mod")
        x, y = Var(), Var()
        goal = And(
            left=IsNot(left=x, right=y),
            right=And(
                left=Is(left=x, right=1),
                right=Is(left=y, right=2),
            ),
        )
        result = once(goal, mod)
        assert result is not None
        assert deref(x) == 1
        assert deref(y) == 2

    def test_is_not_dif_violation_via_solve(self):
        """X_ is not Y_, X_ is 1, Y_ is 1 → fails via solve API."""
        # nv
        mod = Module("test_dif_mod2")
        x, y = Var(), Var()
        goal = And(
            left=IsNot(left=x, right=y),
            right=And(
                left=Is(left=x, right=1),
                right=Is(left=y, right=1),
            ),
        )
        result = once(goal, mod)
        assert result is None

    def test_is_not_ground_different(self):
        """1 is not 2 → succeeds (immediate)."""
        # nv
        mod = Module("test_dif_ground")
        result = once(IsNot(left=1, right=2), mod)
        assert result is not None

    def test_is_not_ground_same(self):
        """1 is not 1 → fails (immediate)."""
        # nv
        mod = Module("test_dif_ground2")
        result = once(IsNot(left=1, right=1), mod)
        assert result is None

    def test_is_not_same_var(self):
        """X_ is not X_ → fails (always identical)."""
        # nv
        mod = Module("test_dif_same")
        x = Var()
        result = once(IsNot(left=x, right=x), mod)
        assert result is None

    def test_not_unify_still_works_as_immediate(self):
        """not (X_ is Y_) → immediate check: fails for two free vars."""
        # nv
        from clausal.terms import Not
        mod = Module("test_naf_unify")
        x, y = Var(), Var()
        goal = Not(operand=Is(left=x, right=y))
        result = once(goal, mod)
        # NAF of unification: two free vars CAN unify → not succeeds = fails
        assert result is None

    def test_is_not_with_multiple_constraints(self):
        """dif(X, 1), dif(X, 2), X is 3 → succeeds."""
        # nv
        mod = Module("test_dif_multi")
        x = Var()
        goal = And(
            left=IsNot(left=x, right=1),
            right=And(
                left=IsNot(left=x, right=2),
                right=Is(left=x, right=3),
            ),
        )
        result = once(goal, mod)
        assert result is not None
        assert deref(x) == 3

    def test_is_not_with_multiple_constraints_violation(self):
        """dif(X, 1), dif(X, 2), X is 1 → fails."""
        # nv
        mod = Module("test_dif_multi2")
        x = Var()
        goal = And(
            left=IsNot(left=x, right=1),
            right=And(
                left=IsNot(left=x, right=2),
                right=Is(left=x, right=1),
            ),
        )
        result = once(goal, mod)
        assert result is None


# ── Builtin dif/2 ───────────────────────────────────────────────────────────


class TestDifBuiltin:

    def test_dif_builtin_succeeds_different(self):
        """dif(1, 2) as builtin call → succeeds."""
        # nv
        mod = Module("test_dif_builtin")
        goal = Call(func=LoadName(name="dif"), args=[1, 2], kwargs=[])
        result = once(goal, mod)
        assert result is not None

    def test_dif_builtin_fails_equal(self):
        """dif(1, 1) as builtin call → fails."""
        # nv
        mod = Module("test_dif_builtin2")
        goal = Call(func=LoadName(name="dif"), args=[1, 1], kwargs=[])
        result = once(goal, mod)
        assert result is None

    def test_dif_builtin_with_vars(self):
        """dif(X, Y), X=1, Y=2 → succeeds."""
        # nv
        mod = Module("test_dif_builtin3")
        x, y = Var(), Var()
        goal = And(
            left=Call(func=LoadName(name="dif"), args=[x, y], kwargs=[]),
            right=And(
                left=Is(left=x, right=1),
                right=Is(left=y, right=2),
            ),
        )
        result = once(goal, mod)
        assert result is not None

    def test_dif_builtin_violation(self):
        """dif(X, Y), X=1, Y=1 → fails."""
        # nv
        mod = Module("test_dif_builtin4")
        x, y = Var(), Var()
        goal = And(
            left=Call(func=LoadName(name="dif"), args=[x, y], kwargs=[]),
            right=And(
                left=Is(left=x, right=1),
                right=Is(left=y, right=1),
            ),
        )
        result = once(goal, mod)
        assert result is None


# ── Import hook integration ──────────────────────────────────────────────────


class TestDifImportHook:

    def test_clausal_file_with_dif(self, tmp_path):
        """A .clausal file using 'is not' with proper dif semantics."""
        # nv
        src = tmp_path / "dif_test.clausal"
        src.write_text(
            "different(X_, Y_, R_) <- (\n"
            "    X_ is not Y_\n"
            "    and R_ is True\n"
            ")\n"
        )
        from clausal.testing import load_clausal_module
        mod = load_clausal_module(src)
        logic_mod = mod.__dict__["$module"]

        # Test: different(1, 2, R) → R = True
        x = Var()
        goal = Call(func=LoadName(name="different"), args=[1, 2, x], kwargs=[])
        result = once(goal, logic_mod)
        assert result is not None
        assert deref(x) is True

        # Test: different(1, 1, R) → fails
        x2 = Var()
        goal2 = Call(func=LoadName(name="different"), args=[1, 1, x2], kwargs=[])
        result2 = once(goal2, logic_mod)
        assert result2 is None
