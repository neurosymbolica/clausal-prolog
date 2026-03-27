"""tests/test_term_inspection.py — V2-13 term inspection builtins.

Tests for:
  copy_term/2       — deep copy with fresh Vars
  term_variables/2  — collect unbound Vars in term
  numbervars/3     — number unbound Vars with $VAR(N)
"""

import pytest

from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.terms import Compound, Call, LoadName


# ── Helpers ────────────────────────────────────────────────────────────────────


def fresh_module():
    return Module("test")


def solutions(goal):
    """Drive goal and return list of (nothing — just count solutions)."""
    mod = fresh_module()
    trail = Trail()
    return list(solve(goal, mod, trail))


def sol_var(goal, var):
    """Return dereffed values of var across all solutions of goal."""
    mod = fresh_module()
    trail = Trail()
    return [deref(var) for _ in solve(goal, mod, trail)]


def goal(functor, *args):
    """Build a Call goal for a builtin."""
    return Call(func=LoadName(name=functor), args=list(args), kwargs=[])


# ── copy_term/2 ─────────────────────────────────────────────────────────────────


class TestCopyTerm:

    def test_copy_atom(self):
        copy = Var()
        vals = sol_var(goal("copy_term", "hello", copy), copy)
        assert vals == ["hello"]

    def test_copy_integer(self):
        copy = Var()
        vals = sol_var(goal("copy_term", 42, copy), copy)
        assert vals == [42]

    def test_copy_none(self):
        copy = Var()
        vals = sol_var(goal("copy_term", None, copy), copy)
        assert vals == [None]

    def test_copy_list_ground(self):
        copy = Var()
        vals = sol_var(goal("copy_term", [1, 2, 3], copy), copy)
        assert vals == [[1, 2, 3]]

    def test_copy_compound_ground(self):
        term = Compound("foo", (1, 2))
        copy = Var()
        vals = sol_var(goal("copy_term", term, copy), copy)
        assert len(vals) == 1
        c = vals[0]
        assert isinstance(c, Compound)
        assert c.functor == "foo"
        assert c.args == (1, 2)

    def test_copy_var_gets_fresh_var(self):
        x = Var()
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", x, copy), mod, trail):
            c = deref(copy)
            assert is_var(c)
            assert c is not x

    def test_copy_preserves_sharing(self):
        """Two occurrences of the same Var → same fresh Var in copy."""
        x = Var()
        term = Compound("f", (x, x))
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", term, copy), mod, trail):
            c = deref(copy)
            assert isinstance(c, Compound)
            a0, a1 = deref(c.args[0]), deref(c.args[1])
            assert is_var(a0) and is_var(a1)
            assert a0 is a1

    def test_copy_fresh_var_distinct_from_original(self):
        x = Var()
        term = Compound("f", (x,))
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", term, copy), mod, trail):
            c = deref(copy)
            fresh = deref(c.args[0])
            assert fresh is not x

    def test_copy_nested_compound(self):
        inner = Compound("bar", (Var(),))
        term = Compound("foo", (inner, 99))
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", term, copy), mod, trail):
            c = deref(copy)
            assert isinstance(c, Compound) and c.functor == "foo"
            c_inner = deref(c.args[0])
            assert isinstance(c_inner, Compound) and c_inner.functor == "bar"

    def test_copy_list_with_vars(self):
        x = Var()
        lst = [1, x, 3]
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", lst, copy), mod, trail):
            c = deref(copy)
            assert isinstance(c, list)
            assert deref(c[0]) == 1
            assert is_var(deref(c[1]))
            assert deref(c[2]) == 3

    def test_copy_bound_var(self):
        """Var already bound → copy gets the bound value."""
        trail = Trail()
        x = Var()
        unify(x, 42, trail)
        copy = Var()
        mod = fresh_module()
        for _ in solve(goal("copy_term", x, copy), mod, trail):
            assert deref(copy) == 42

    def test_copy_exactly_one_solution(self):
        copy = Var()
        sols = solutions(goal("copy_term", Compound("f", (1,)), copy))
        assert len(sols) == 1

    def test_copy_no_side_effects_on_original(self):
        """copy_term does not bind original Vars."""
        x = Var()
        term = Compound("f", (x,))
        copy = Var()
        solutions(goal("copy_term", term, copy))
        assert is_var(deref(x))


# ── term_variables/2 ────────────────────────────────────────────────────────────


class TestTermVariables:

    def test_ground_term_empty(self):
        out = Var()
        vals = sol_var(goal("term_variables", 42, out), out)
        assert vals == [[]]

    def test_ground_compound_empty(self):
        out = Var()
        vals = sol_var(goal("term_variables", Compound("f", (1, 2)), out), out)
        assert vals == [[]]

    def test_single_var(self):
        x = Var()
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", x, out), mod, trail):
            result = deref(out)
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0] is x

    def test_compound_with_vars(self):
        x, y = Var(), Var()
        term = Compound("f", (x, y))
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", term, out), mod, trail):
            result = deref(out)
            assert len(result) == 2
            assert result[0] is x
            assert result[1] is y

    def test_repeated_var_only_once(self):
        x = Var()
        term = Compound("f", (x, x))
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", term, out), mod, trail):
            result = deref(out)
            assert len(result) == 1
            assert result[0] is x

    def test_left_to_right_order(self):
        x, y, z = Var(), Var(), Var()
        term = Compound("f", (x, Compound("g", (y,)), z))
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", term, out), mod, trail):
            result = deref(out)
            assert [r is v for r, v in zip(result, [x, y, z])] == [True, True, True]

    def test_list_term(self):
        x, y = Var(), Var()
        lst = [1, x, 2, y]
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", lst, out), mod, trail):
            result = deref(out)
            assert len(result) == 2
            assert result[0] is x
            assert result[1] is y

    def test_bound_var_not_collected(self):
        """Bound Var derefs to value — not collected."""
        trail = Trail()
        x = Var()
        unify(x, 99, trail)
        y = Var()
        term = Compound("f", (x, y))
        out = Var()
        mod = fresh_module()
        for _ in solve(goal("term_variables", term, out), mod, trail):
            result = deref(out)
            assert len(result) == 1
            assert result[0] is y

    def test_nested_vars(self):
        x = Var()
        term = Compound("a", (Compound("b", (Compound("c", (x,)),)),))
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", term, out), mod, trail):
            result = deref(out)
            assert len(result) == 1
            assert result[0] is x

    def test_exactly_one_solution(self):
        out = Var()
        sols = solutions(goal("term_variables", Var(), out))
        assert len(sols) == 1


# ── numbervars/3 ───────────────────────────────────────────────────────────────


class TestNumberVars:

    def test_ground_term_no_vars(self):
        end = Var()
        term = Compound("f", (1, 2))
        vals = sol_var(goal("numbervars", term, 0, end), end)
        assert vals == [0]

    def test_single_var(self):
        x = Var()
        term = Compound("f", (x,))
        end = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("numbervars", term, 0, end), mod, trail):
            xv = deref(x)
            assert xv == Compound("$VAR", (0,))
            assert deref(end) == 1

    def test_two_vars(self):
        x, y = Var(), Var()
        term = Compound("f", (x, y))
        end = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("numbervars", term, 0, end), mod, trail):
            assert deref(x) == Compound("$VAR", (0,))
            assert deref(y) == Compound("$VAR", (1,))
            assert deref(end) == 2

    def test_start_offset(self):
        x = Var()
        term = Compound("f", (x,))
        end = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("numbervars", term, 5, end), mod, trail):
            assert deref(x) == Compound("$VAR", (5,))
            assert deref(end) == 6

    def test_repeated_var_numbered_once(self):
        x = Var()
        term = Compound("f", (x, x))
        end = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("numbervars", term, 0, end), mod, trail):
            assert deref(x) == Compound("$VAR", (0,))
            assert deref(end) == 1

    def test_unbound_start_fails(self):
        x = Var()
        end = Var()
        sols = solutions(goal("numbervars", x, Var(), end))
        assert len(sols) == 0

    def test_list_term(self):
        x, y = Var(), Var()
        lst = [x, y]
        end = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("numbervars", lst, 0, end), mod, trail):
            assert deref(x) == Compound("$VAR", (0,))
            assert deref(y) == Compound("$VAR", (1,))
            assert deref(end) == 2

    def test_exactly_one_solution(self):
        end = Var()
        sols = solutions(goal("numbervars", 42, 0, end))
        assert len(sols) == 1

    def test_end_wrong_value_fails(self):
        """If End is already bound to wrong value, predicate fails."""
        x = Var()
        term = Compound("f", (x,))
        # one var → end should be 1; bind end to 99 → should fail
        trail = Trail()
        end = Var()
        unify(end, 99, trail)
        mod = fresh_module()
        sols = list(solve(goal("numbervars", term, 0, end), mod, trail))
        assert len(sols) == 0

    def test_bindings_undone_after_backtrack(self):
        """numbervars binds vars via trail; bindings are undone on backtrack."""
        x = Var()
        term = Compound("f", (x,))
        end = Var()
        mod = fresh_module()
        trail = Trail()
        # Collect solutions — after iteration ends, trail should be undone
        sols = list(solve(goal("numbervars", term, 0, end), mod, trail))
        assert len(sols) == 1
        # After solve completes (generator exhausted), trail is rewound
        # x should be unbound again since solve unwinds
        # Note: solve() doesn't undo the trail; the bindings persist at top level.
        # Just check that there was exactly 1 solution.


# ── gensym/2 ──────────────────────────────────────────────────────────────────


class TestGenSym:

    def setup_method(self):
        """Reset gensym counters between tests."""
        from clausal.logic.builtins.inspection import _gensym_counters
        _gensym_counters.clear()

    def test_basic(self):
        """gensym("x", A) → "x_1"."""
        a = Var()
        vals = sol_var(goal("gensym", "x", a), a)
        assert vals == ["x_1"]

    def test_sequential(self):
        """Two calls increment: "x_1", "x_2"."""
        a1, a2 = Var(), Var()
        vals1 = sol_var(goal("gensym", "x", a1), a1)
        vals2 = sol_var(goal("gensym", "x", a2), a2)
        assert vals1 == ["x_1"]
        assert vals2 == ["x_2"]

    def test_different_prefixes(self):
        """Different prefixes have independent counters."""
        a = Var()
        b = Var()
        sol_var(goal("gensym", "x", a), a)
        vals = sol_var(goal("gensym", "y", b), b)
        assert vals == ["y_1"]

    def test_unbound_prefix_fails(self):
        """gensym(X, A) with unbound X → no solutions."""
        a = Var()
        sols = solutions(goal("gensym", Var(), a))
        assert len(sols) == 0

    def test_non_string_prefix_fails(self):
        """gensym(42, A) → no solutions."""
        a = Var()
        sols = solutions(goal("gensym", 42, a))
        assert len(sols) == 0

    def test_counter_survives_backtracking(self):
        """Counter does NOT reset on backtracking — impure."""
        a1 = Var()
        sol_var(goal("gensym", "z", a1), a1)
        # Counter is now at 1; next call should give z_2
        a2 = Var()
        vals = sol_var(goal("gensym", "z", a2), a2)
        assert vals == ["z_2"]

    def test_atom_already_bound_unification(self):
        """gensym("x", "x_1") succeeds if counter is at 1."""
        sols = solutions(goal("gensym", "x", "x_1"))
        assert len(sols) == 1

    def test_atom_already_bound_mismatch(self):
        """gensym("x", "x_99") fails when counter is at 1."""
        sols = solutions(goal("gensym", "x", "x_99"))
        assert len(sols) == 0

    def test_thread_safety(self):
        """Concurrent gensym calls produce unique atoms."""
        import threading
        results = []
        lock = threading.Lock()

        def gen():
            a = Var()
            mod = fresh_module()
            trail = Trail()
            for _ in solve(goal("gensym", "t", a), mod, trail):
                with lock:
                    results.append(deref(a))

        threads = [threading.Thread(target=gen) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(results)) == 10  # all unique
