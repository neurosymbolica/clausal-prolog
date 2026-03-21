"""Tests for V2-11 — higher-order list builtins and Pythonic aliases."""

from __future__ import annotations

import pytest

from clausal.logic.builtins import (
    _map_list__2, _map_list__3, _include__3, _exclude__3, _foldl__4,
)
from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import Call, LoadName, Compound


# ── Helpers ────────────────────────────────────────────────────────────────────


def run_trampoline(fn, *args):
    """Call a native trampoline builtin and return number of solutions."""
    trail = Trail()
    sg = StepGenerator(fn, None, *args, trail)
    gen, value = sg.send(None)
    count = 0
    while True:
        if gen is None:
            if value is DONE:
                return count
            count += 1
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)


def run_trampoline_var(fn, *args_before_result):
    """Call a native trampoline builtin with trailing Var, return deref'd values."""
    trail = Trail()
    result = Var()
    sg = StepGenerator(fn, None, *args_before_result, result, trail)
    gen, value = sg.send(None)
    results = []
    while True:
        if gen is None:
            if value is DONE:
                return results
            results.append(deref(result))
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)


def fresh_module(name: str = "test") -> Module:
    return Module(name)


def solutions(goal, mod=None):
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return list(solve(goal, mod, t))


def sol_var(goal, var, *, mod=None):
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return [deref(var) for _ in solve(goal, mod, t)]


def _make_goal_call(name, args):
    return Call(func=LoadName(name=name), args=args, kwargs=[])


# ── Simple goal closures for testing ──────────────────────────────────────────


def _goal_positive(x, trail, k):
    val = deref(x)
    if isinstance(val, (int, float)) and val > 0:
        yield None


def _goal_even(x, trail, k):
    val = deref(x)
    if isinstance(val, int) and val % 2 == 0:
        yield None


def _goal_double(x, y, trail, k):
    val = deref(x)
    if isinstance(val, (int, float)):
        if unify(y, val * 2, trail):
            yield None


def _goal_add(elem, acc, result, trail, k):
    e = deref(elem)
    a = deref(acc)
    if isinstance(e, (int, float)) and isinstance(a, (int, float)):
        if unify(result, a + e, trail):
            yield None


def _goal_mul(elem, acc, result, trail, k):
    e = deref(elem)
    a = deref(acc)
    if isinstance(e, (int, float)) and isinstance(a, (int, float)):
        if unify(result, a * e, trail):
            yield None


def _goal_always_fail(*args):
    return; yield  # noqa: B901


# ── map_list/2 ────────────────────────────────────────────────────────────────


class TestMapList2:
    def test_all_succeed(self):
        assert run_trampoline(_map_list__2, _goal_positive, [1, 2, 3]) == 1

    def test_one_fails(self):
        assert run_trampoline(_map_list__2, _goal_positive, [1, -2, 3]) == 0

    def test_empty_list(self):
        assert run_trampoline(_map_list__2, _goal_positive, []) == 1

    def test_non_list_fails(self):
        assert run_trampoline(_map_list__2, _goal_positive, 42) == 0

    def test_non_callable_fails(self):
        assert run_trampoline(_map_list__2, 42, [1, 2, 3]) == 0


# ── map_list/3 ────────────────────────────────────────────────────────────────


class TestMapList3:
    def test_double(self):
        results = run_trampoline_var(_map_list__3, _goal_double, [1, 2, 3])
        assert results == [[2, 4, 6]]

    def test_empty_list(self):
        results = run_trampoline_var(_map_list__3, _goal_double, [])
        assert results == [[]]

    def test_goal_fails_mid_list(self):
        results = run_trampoline_var(_map_list__3, _goal_always_fail, [1, 2, 3])
        assert results == []

    def test_non_list_fails(self):
        results = run_trampoline_var(_map_list__3, _goal_double, "abc")
        assert results == []


# ── include/3 ─────────────────────────────────────────────────────────────────


class TestInclude:
    def test_filter_positive(self):
        results = run_trampoline_var(_include__3, _goal_positive, [1, -2, 3, -4])
        assert results == [[1, 3]]

    def test_all_match(self):
        results = run_trampoline_var(_include__3, _goal_positive, [1, 2, 3])
        assert results == [[1, 2, 3]]

    def test_none_match(self):
        results = run_trampoline_var(_include__3, _goal_positive, [-1, -2, -3])
        assert results == [[]]

    def test_empty_input(self):
        results = run_trampoline_var(_include__3, _goal_positive, [])
        assert results == [[]]

    def test_even_filter(self):
        results = run_trampoline_var(_include__3, _goal_even, [1, 2, 3, 4])
        assert results == [[2, 4]]


# ── exclude/3 ─────────────────────────────────────────────────────────────────


class TestExclude:
    def test_filter_non_positive(self):
        results = run_trampoline_var(_exclude__3, _goal_positive, [1, -2, 3, -4])
        assert results == [[-2, -4]]

    def test_all_match(self):
        results = run_trampoline_var(_exclude__3, _goal_positive, [1, 2, 3])
        assert results == [[]]

    def test_none_match(self):
        results = run_trampoline_var(_exclude__3, _goal_positive, [-1, -2, -3])
        assert results == [[-1, -2, -3]]

    def test_empty_input(self):
        results = run_trampoline_var(_exclude__3, _goal_positive, [])
        assert results == [[]]


# ── foldl/4 ───────────────────────────────────────────────────────────────────


def _run_foldl(goal, lst, v0):
    """Helper: run foldl via trampoline and capture deref'd result."""
    trail = Trail()
    v = Var()
    sg = StepGenerator(_foldl__4, None, goal, lst, v0, v, trail)
    gen, value = sg.send(None)
    results = []
    while True:
        if gen is None:
            if value is DONE:
                return results
            results.append(deref(v))
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)


class TestFoldl:
    def test_sum(self):
        assert _run_foldl(_goal_add, [1, 2, 3], 0) == [6]

    def test_product(self):
        assert _run_foldl(_goal_mul, [2, 3, 4], 1) == [24]

    def test_empty_list(self):
        assert _run_foldl(_goal_add, [], 0) == [0]

    def test_goal_fails_mid_fold(self):
        assert _run_foldl(_goal_always_fail, [1, 2, 3], 0) == []

    def test_non_list_fails(self):
        assert _run_foldl(_goal_add, 42, 0) == []


# ── Rename aliases (V2-11) ───────────────────────────────────────────────────


class TestAliases:
    def test_merge_sort(self):
        r = Var()
        goal = _make_goal_call("MergeSort", [[3, 1, 2], r])
        results = sol_var(goal, r)
        assert results == [[1, 2, 3]]

    def test_get_item(self):
        r = Var()
        goal = _make_goal_call("GetItem", [1, [10, 20, 30], r])
        results = sol_var(goal, r)
        assert results == [20]

    def test_member_check(self):
        goal = _make_goal_call("InCheck", [2, [1, 2, 3]])
        assert len(solutions(goal)) == 1

    def test_member_check_fail(self):
        goal = _make_goal_call("InCheck", [5, [1, 2, 3]])
        assert solutions(goal) == []

    def test_unpack(self):
        r = Var()
        goal = _make_goal_call("Unpack", [Compound("foo", (1, 2)), r])
        results = sol_var(goal, r)
        assert len(results) == 1
        assert results[0] == ["foo", 1, 2]


# ── Builtin predicates as arguments to meta-predicates ────────────────────────


class TestBuiltinAsArgument:
    """Test that builtin predicates can be passed as arguments to higher-order
    builtins like MapList, Filter, etc."""

    def test_builtin_to_maplist2(self):
        """IsNumber passed to MapList/2 — succeeds when all elements are numbers."""
        from clausal.logic.builtins import get_builtin_class
        is_number = get_builtin_class("IsNumber")
        assert run_trampoline(_map_list__2, is_number, [1, 2, 3.0]) == 1

    def test_builtin_to_maplist2_fail(self):
        """IsNumber passed to MapList/2 — fails when a non-number is present."""
        from clausal.logic.builtins import get_builtin_class
        is_number = get_builtin_class("IsNumber")
        assert run_trampoline(_map_list__2, is_number, [1, "a", 3]) == 0

    def test_builtin_to_maplist3(self):
        """Succ passed to MapList/3 — maps each element to its successor."""
        from clausal.logic.builtins import get_builtin_class
        succ = get_builtin_class("Succ")
        results = run_trampoline_var(_map_list__3, succ, [0, 1, 2])
        assert results == [[1, 2, 3]]

    def test_builtin_to_filter(self):
        """IsInt passed to Filter/3 — keeps only integers."""
        from clausal.logic.builtins import get_builtin_class
        is_int = get_builtin_class("IsInt")
        results = run_trampoline_var(_include__3, is_int, [1, 2.5, 3, "x"])
        assert results == [[1, 3]]

    def test_builtin_to_exclude(self):
        """IsInt passed to Exclude/3 — removes integers."""
        from clausal.logic.builtins import get_builtin_class
        is_int = get_builtin_class("IsInt")
        results = run_trampoline_var(_exclude__3, is_int, [1, 2.5, 3, "x"])
        assert results == [[2.5, "x"]]

    def test_builtin_clausal_fixture(self):
        """Builtins passed as arguments in compiled .clausal code."""
        from clausal.testing import load_clausal_module, collect_tests, run_test
        mod = load_clausal_module("tests/fixtures/builtin_as_arg.clausal")
        tests = collect_tests(mod)
        assert len(tests) >= 5
        for desc in tests:
            r = run_test(mod, desc)
            assert r.passed, f"Test {desc!r} failed: {r.error}"
