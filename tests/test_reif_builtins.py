"""Tests for V2-8 Phase B: Reified builtins library.

Tests cover:
- eq/3 unit tests (reified equality as generator-based builtin)
- dif_t/3 unit tests (reified disequality as generator-based builtin)
- eq/3 and dif_t/3 as registered builtins (via get_builtin_dispatch)
- memberd_t/3 via .clausal stdlib import
"""

import os
import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.constraints import dif
from clausal.logic.reif import eq__3, dif_t__3


# ── eq/3 unit tests ──────────────────────────────────────────────────────────


class TestEq3:
    """Test reified equality: eq(X, Y, T)."""

    def _run(self, x, y, t, trail):
        """Run eq/3, return list of (x, y, t) after deref."""
        results = []
        for _ in eq__3(x, y, t, trail, None):
            results.append((deref(x), deref(y), deref(t)))
        return results

    def test_ground_equal(self):
        """eq(1, 1, T) → T = True."""
        trail = Trail()
        t = Var()
        results = self._run(1, 1, t, trail)
        assert len(results) == 1
        assert results[0][2] is True

    def test_ground_incompatible(self):
        """eq(1, 2, T) → T = False."""
        trail = Trail()
        t = Var()
        results = self._run(1, 2, t, trail)
        assert len(results) == 1
        assert results[0][2] is False

    def test_identical_var(self):
        """eq(X, X, T) with same var → T = True."""
        trail = Trail()
        x = Var()
        t = Var()
        results = self._run(x, x, t, trail)
        assert len(results) == 1
        assert results[0][2] is True

    def test_undetermined_explores_both(self):
        """eq(X, 1, T) with X unbound → two solutions."""
        trail = Trail()
        x = Var()
        t = Var()
        results = self._run(x, 1, t, trail)
        assert len(results) == 2
        # Branch 1: T=True, X=1
        assert results[0] == (1, 1, True)
        # Branch 2: T=False, dif(X, 1)
        assert results[1][2] is False
        # X should be unbound (dif constraint attached, not bound)
        assert is_var(results[1][0])

    def test_undetermined_two_vars(self):
        """eq(X, Y, T) with X,Y unbound → two solutions."""
        trail = Trail()
        x = Var()
        y = Var()
        t = Var()
        results = self._run(x, y, t, trail)
        assert len(results) == 2
        # Branch 1: T=True, X=Y (unified)
        assert results[0][2] is True
        # Branch 2: T=False, dif(X, Y)
        assert results[1][2] is False

    def test_ground_string_equal(self):
        """eq("hello", "hello", T) → T = True."""
        trail = Trail()
        t = Var()
        results = self._run("hello", "hello", t, trail)
        assert len(results) == 1
        assert results[0][2] is True

    def test_ground_string_different(self):
        """eq("hello", "world", T) → T = False."""
        trail = Trail()
        t = Var()
        results = self._run("hello", "world", t, trail)
        assert len(results) == 1
        assert results[0][2] is False

    def test_ground_type_mismatch(self):
        """eq(1, "1", T) → T = False."""
        trail = Trail()
        t = Var()
        results = self._run(1, "1", t, trail)
        assert len(results) == 1
        assert results[0][2] is False

    def test_t_already_bound_true_matches(self):
        """eq(1, 1, True) — T already True, condition true → succeeds."""
        trail = Trail()
        results = list(eq__3(1, 1, True, trail, None))
        assert len(results) == 1

    def test_t_already_bound_true_mismatch(self):
        """eq(1, 2, True) — T=True but 1≠2 → fails."""
        trail = Trail()
        results = list(eq__3(1, 2, True, trail, None))
        assert len(results) == 0

    def test_t_already_bound_false_matches(self):
        """eq(1, 2, False) — T already False, condition false → succeeds."""
        trail = Trail()
        results = list(eq__3(1, 2, False, trail, None))
        assert len(results) == 1

    def test_t_already_bound_false_mismatch(self):
        """eq(1, 1, False) — T=False but 1=1 → fails."""
        trail = Trail()
        results = list(eq__3(1, 1, False, trail, None))
        assert len(results) == 0

    def test_no_side_effects(self):
        """eq/3 should not leave bindings on the trail after exhaustion."""
        trail = Trail()
        x = Var()
        t = Var()
        mark = trail.mark()
        list(eq__3(x, 1, t, trail, None))
        # After exhaustion, all bindings should be undone
        assert is_var(deref(x))
        assert is_var(deref(t))

    def test_list_equal(self):
        """eq([1,2], [1,2], T) → T = True."""
        trail = Trail()
        t = Var()
        results = self._run([1, 2], [1, 2], t, trail)
        assert len(results) == 1
        assert results[0][2] is True

    def test_list_different(self):
        """eq([1,2], [1,3], T) → T = False."""
        trail = Trail()
        t = Var()
        results = self._run([1, 2], [1, 3], t, trail)
        assert len(results) == 1
        assert results[0][2] is False

    def test_list_with_var(self):
        """eq([X, 2], [1, 2], T) with X unbound → undetermined."""
        trail = Trail()
        x = Var()
        t = Var()
        results = self._run([x, 2], [1, 2], t, trail)
        assert len(results) == 2
        assert results[0][2] is True
        assert results[1][2] is False


# ── dif_t/3 unit tests ───────────────────────────────────────────────────────


class TestDifT3:
    """Test reified disequality: dif_t(X, Y, T)."""

    def _run(self, x, y, t, trail):
        results = []
        for _ in dif_t__3(x, y, t, trail, None):
            results.append((deref(x), deref(y), deref(t)))
        return results

    def test_ground_different(self):
        """dif_t(1, 2, T) → T = True (they are definitely different)."""
        trail = Trail()
        t = Var()
        results = self._run(1, 2, t, trail)
        assert len(results) == 1
        assert results[0][2] is True

    def test_ground_equal(self):
        """dif_t(1, 1, T) → T = False (they are equal, dif fails)."""
        trail = Trail()
        t = Var()
        results = self._run(1, 1, t, trail)
        assert len(results) == 1
        assert results[0][2] is False

    def test_identical_var(self):
        """dif_t(X, X, T) with same var → T = False."""
        trail = Trail()
        x = Var()
        t = Var()
        results = self._run(x, x, t, trail)
        assert len(results) == 1
        assert results[0][2] is False

    def test_undetermined_explores_both(self):
        """dif_t(X, 1, T) with X unbound → two solutions."""
        trail = Trail()
        x = Var()
        t = Var()
        results = self._run(x, 1, t, trail)
        assert len(results) == 2
        # Branch 1: T=True, dif(X, 1)
        assert results[0][2] is True
        assert is_var(results[0][0])
        # Branch 2: T=False, X=1
        assert results[1] == (1, 1, False)

    def test_t_already_bound_true_matches(self):
        """dif_t(1, 2, True) → succeeds (they're different)."""
        trail = Trail()
        results = list(dif_t__3(1, 2, True, trail, None))
        assert len(results) == 1

    def test_t_already_bound_true_mismatch(self):
        """dif_t(1, 1, True) → fails (they're equal, dif_t returns False)."""
        trail = Trail()
        results = list(dif_t__3(1, 1, True, trail, None))
        assert len(results) == 0

    def test_no_side_effects(self):
        """dif_t/3 should not leave bindings after exhaustion."""
        trail = Trail()
        x = Var()
        t = Var()
        list(dif_t__3(x, 1, t, trail, None))
        assert is_var(deref(x))
        assert is_var(deref(t))

    def test_inverse_of_eq(self):
        """eq and dif_t should produce opposite truth values for same args."""
        trail = Trail()
        # Ground case: collect truth values during iteration
        t1 = Var()
        eq_truths = []
        for _ in eq__3(1, 2, t1, trail, None):
            eq_truths.append(deref(t1))
        t2 = Var()
        dif_truths = []
        for _ in dif_t__3(1, 2, t2, trail, None):
            dif_truths.append(deref(t2))
        assert eq_truths == [False]   # eq(1,2) → False
        assert dif_truths == [True]   # dif_t(1,2) → True


# ── Builtin registration tests ──────────────────────────────────────────────


class TestReifBuiltinRegistration:
    """Test that eq/3 and dif_t/3 are properly registered as builtins."""

    def test_eq_registered(self):
        from clausal.logic.builtins import _BUILTINS
        assert ("eq", 3) in _BUILTINS

    def test_dif_t_registered(self):
        from clausal.logic.builtins import _BUILTINS
        assert ("dif_t", 3) in _BUILTINS

    def test_eq_via_get_builtin_dispatch(self):
        """eq/3 should be findable via get_builtin_dispatch."""
        from clausal.logic.builtins import get_builtin_dispatch
        from clausal.logic.database import Database
        db = Database()
        dispatch = get_builtin_dispatch("eq", 3, db)
        assert dispatch is not None

    def test_dif_t_via_get_builtin_dispatch(self):
        """dif_t/3 should be findable via get_builtin_dispatch."""
        from clausal.logic.builtins import get_builtin_dispatch
        from clausal.logic.database import Database
        db = Database()
        dispatch = get_builtin_dispatch("dif_t", 3, db)
        assert dispatch is not None


# ── eq/3 and dif_t/3 via compiled code ───────────────────────────────────────


class TestReifCompiledIntegration:
    """Test eq/3 and dif_t/3 called from compiled predicate code."""

    def _load_fixture(self, filename):
        from clausal.import_hook import _load_module
        path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
        name = f"_test_fixture_{filename.replace('.', '_')}"
        return _load_module(name, path)

    def test_eq_from_clausal_file(self):
        """eq/3 called from a .clausal predicate."""
        mod = self._load_fixture("reif_eq_test.clausal")
        from clausal.logic.solve import query
        from clausal.pythonic_ast.nodes import Call, LoadName

        logic_mod = mod.__dict__["$module"]
        t = Var()
        goal = Call(func=LoadName(name="check_eq"), args=[1, 1, t], kwargs=[])
        results = list(query(goal, {"t": t}, logic_mod))
        assert len(results) == 1
        assert results[0]["t"] is True

    def test_eq_ground_false_from_clausal(self):
        mod = self._load_fixture("reif_eq_test.clausal")
        from clausal.logic.solve import query
        from clausal.pythonic_ast.nodes import Call, LoadName

        logic_mod = mod.__dict__["$module"]
        t = Var()
        goal = Call(func=LoadName(name="check_eq"), args=[1, 2, t], kwargs=[])
        results = list(query(goal, {"t": t}, logic_mod))
        assert len(results) == 1
        assert results[0]["t"] is False

    def test_eq_undetermined_from_clausal(self):
        mod = self._load_fixture("reif_eq_test.clausal")
        from clausal.logic.solve import query
        from clausal.pythonic_ast.nodes import Call, LoadName

        logic_mod = mod.__dict__["$module"]
        x = Var()
        t = Var()
        goal = Call(func=LoadName(name="check_eq"), args=[x, 1, t], kwargs=[])
        results = list(query(goal, {"x": x, "t": t}, logic_mod))
        assert len(results) == 2
        truths = {r["t"] for r in results}
        assert truths == {True, False}


# ── memberd_t/3 stdlib tests ─────────────────────────────────────────────────


class TestMemberdT:
    """Test memberd_t/3 from clausal/stdlib/reif.clausal."""

    def _load_stdlib_reif(self):
        from clausal.import_hook import _load_module
        path = os.path.join(
            os.path.dirname(__file__), os.pardir,
            "clausal", "stdlib", "reif.clausal",
        )
        path = os.path.normpath(path)
        return _load_module("_test_stdlib_reif", path)

    def test_ground_member_true(self):
        """memberd_t(1, [1,2,3], T) → T = True."""
        mod = self._load_stdlib_reif()
        from clausal.logic.solve import query
        from clausal.pythonic_ast.nodes import Call, LoadName

        logic_mod = mod.__dict__["$module"]
        t = Var()
        goal = Call(func=LoadName(name="memberd_t"), args=[1, [1, 2, 3], t], kwargs=[])
        results = list(query(goal, {"t": t}, logic_mod))
        truths = [r["t"] for r in results]
        assert True in truths

    def test_ground_member_false(self):
        """memberd_t(99, [1,2,3], T) → T = False."""
        mod = self._load_stdlib_reif()
        from clausal.logic.solve import query
        from clausal.pythonic_ast.nodes import Call, LoadName

        logic_mod = mod.__dict__["$module"]
        t = Var()
        goal = Call(func=LoadName(name="memberd_t"), args=[99, [1, 2, 3], t], kwargs=[])
        results = list(query(goal, {"t": t}, logic_mod))
        truths = [r["t"] for r in results]
        assert False in truths

    def test_empty_list(self):
        """memberd_t(1, [], T) → T = False."""
        mod = self._load_stdlib_reif()
        from clausal.logic.solve import query
        from clausal.pythonic_ast.nodes import Call, LoadName

        logic_mod = mod.__dict__["$module"]
        t = Var()
        goal = Call(func=LoadName(name="memberd_t"), args=[1, [], t], kwargs=[])
        results = list(query(goal, {"t": t}, logic_mod))
        truths = [r["t"] for r in results]
        assert truths == [False]

    def test_unbound_element_explores_branches(self):
        """memberd_t(X, [1,2], T) with X unbound → explores possibilities."""
        mod = self._load_stdlib_reif()
        from clausal.logic.solve import query
        from clausal.pythonic_ast.nodes import Call, LoadName

        logic_mod = mod.__dict__["$module"]
        x = Var()
        t = Var()
        goal = Call(func=LoadName(name="memberd_t"), args=[x, [1, 2], t], kwargs=[])
        results = list(query(goal, {"x": x, "t": t}, logic_mod))
        # Should have solutions with T=True for X=1 and X=2
        true_results = [r for r in results if r["t"] is True]
        assert len(true_results) >= 2
        true_xs = {r["x"] for r in true_results}
        assert true_xs == {1, 2}
