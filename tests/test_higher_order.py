"""Tests for V2-11 — higher-order list builtins and Pythonic aliases."""

from __future__ import annotations

import pytest

from clausal.logic.builtins import (
    _map_list__2, _map_list__3, _include__3, _exclude__3, _foldl__4,
)
from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import Call, LoadName, Compound


# ── Helpers ────────────────────────────────────────────────────────────────────


def run_simple(fn, *args):
    """Call a simple-mode builtin and return list of solutions."""
    trail = Trail()
    return list(fn(*args, trail, None))


def run_simple_var(fn, *args_before_result):
    """Call a simple-mode builtin with a trailing Var, return deref'd values."""
    trail = Trail()
    result = Var()
    results = []
    for _ in fn(*args_before_result, result, trail, None):
        results.append(deref(result))
    return results


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
        assert len(run_simple(_map_list__2, _goal_positive, [1, 2, 3])) == 1

    def test_one_fails(self):
        assert run_simple(_map_list__2, _goal_positive, [1, -2, 3]) == []

    def test_empty_list(self):
        assert len(run_simple(_map_list__2, _goal_positive, [])) == 1

    def test_non_list_fails(self):
        assert run_simple(_map_list__2, _goal_positive, 42) == []

    def test_non_callable_fails(self):
        assert run_simple(_map_list__2, 42, [1, 2, 3]) == []


# ── map_list/3 ────────────────────────────────────────────────────────────────


class TestMapList3:
    def test_double(self):
        results = run_simple_var(_map_list__3, _goal_double, [1, 2, 3])
        assert results == [[2, 4, 6]]

    def test_empty_list(self):
        results = run_simple_var(_map_list__3, _goal_double, [])
        assert results == [[]]

    def test_goal_fails_mid_list(self):
        results = run_simple_var(_map_list__3, _goal_always_fail, [1, 2, 3])
        assert results == []

    def test_non_list_fails(self):
        results = run_simple_var(_map_list__3, _goal_double, "abc")
        assert results == []


# ── include/3 ─────────────────────────────────────────────────────────────────


class TestInclude:
    def test_filter_positive(self):
        results = run_simple_var(_include__3, _goal_positive, [1, -2, 3, -4])
        assert results == [[1, 3]]

    def test_all_match(self):
        results = run_simple_var(_include__3, _goal_positive, [1, 2, 3])
        assert results == [[1, 2, 3]]

    def test_none_match(self):
        results = run_simple_var(_include__3, _goal_positive, [-1, -2, -3])
        assert results == [[]]

    def test_empty_input(self):
        results = run_simple_var(_include__3, _goal_positive, [])
        assert results == [[]]

    def test_even_filter(self):
        results = run_simple_var(_include__3, _goal_even, [1, 2, 3, 4])
        assert results == [[2, 4]]


# ── exclude/3 ─────────────────────────────────────────────────────────────────


class TestExclude:
    def test_filter_non_positive(self):
        results = run_simple_var(_exclude__3, _goal_positive, [1, -2, 3, -4])
        assert results == [[-2, -4]]

    def test_all_match(self):
        results = run_simple_var(_exclude__3, _goal_positive, [1, 2, 3])
        assert results == [[]]

    def test_none_match(self):
        results = run_simple_var(_exclude__3, _goal_positive, [-1, -2, -3])
        assert results == [[-1, -2, -3]]

    def test_empty_input(self):
        results = run_simple_var(_exclude__3, _goal_positive, [])
        assert results == [[]]


# ── foldl/4 ───────────────────────────────────────────────────────────────────


def _run_foldl(goal, lst, v0):
    """Helper: run foldl and capture deref'd result during yield."""
    trail = Trail()
    v = Var()
    results = []
    for _ in _foldl__4(goal, lst, v0, v, trail, None):
        results.append(deref(v))
    return results


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
