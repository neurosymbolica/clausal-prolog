"""Tests for V2-10 meta-predicates: find_all, bag_of, set_of, for_all, call/N."""

from __future__ import annotations

import os
import sys

import pytest

from clausal.logic.compiler import compile_predicate, compile_predicate_trampoline
from clausal.logic.database import Clause, Database, Module
from clausal.logic.solve import call, solve, query, once, _deref_walk
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import (
    And, Or, Not,
    Unify as Is, Evaluate,
    Lt, LtE, Gt, GtE,
    In, NotIn,
    Call, LoadName,
    Compound,
)

import clausal.import_hook
from clausal.import_hook import _load_module


# ── Helpers ────────────────────────────────────────────────────────────────────


def fresh_module(name: str = "test") -> Module:
    return Module(name)


def solutions_of(goal, mod=None) -> list[Trail]:
    if mod is None:
        mod = fresh_module()
    return list(solve(goal, mod))


def bindings(goal, var: Var, mod=None) -> list:
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return [_deref_walk(var) for _ in solve(goal, mod, t)]


# ── find_all/3 ────────────────────────────────────────────────────────────────


class TestFindAll:
    def test_find_all_basic(self):
        """find_all(X, member(X, [1,2,3]), Bag) → [1,2,3]"""
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="FindAll"), args=[
            x,
            Call(func=LoadName(name="In"), args=[x, [1, 2, 3]], kwargs=[]),
            bag,
        ], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[1, 2, 3]]

    def test_find_all_with_filter(self):
        """find_all(X, (member(X, [1,2,3]) and X > 1), Bag) → [2, 3]"""
        x = Var()
        bag = Var()
        inner = And(
            left=Call(func=LoadName(name="In"), args=[x, [1, 2, 3]], kwargs=[]),
            right=Gt(left=x, right=1),
        )
        goal = Call(func=LoadName(name="FindAll"), args=[x, inner, bag], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[2, 3]]

    def test_find_all_fail_empty_list(self):
        """find_all(X, fail, Bag) → [] (succeeds with empty list)"""
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="FindAll"), args=[x, False, bag], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[]]

    def test_find_all_template_expression(self):
        """find_all([X,Y], cross product) → cartesian product"""
        x = Var()
        y = Var()
        bag = Var()
        inner = And(
            left=Call(func=LoadName(name="In"), args=[x, ["a", "b"]], kwargs=[]),
            right=Call(func=LoadName(name="In"), args=[y, [1, 2]], kwargs=[]),
        )
        goal = Call(func=LoadName(name="FindAll"), args=[[x, y], inner, bag], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[["a", 1], ["a", 2], ["b", 1], ["b", 2]]]

    def test_find_all_no_side_effects(self):
        """find_all should undo bindings from inner goal."""
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="FindAll"), args=[
            x,
            Call(func=LoadName(name="In"), args=[x, [10, 20]], kwargs=[]),
            bag,
        ], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[10, 20]]

    def test_find_all_nested(self):
        """Nested find_all: outer collects inner results."""
        x = Var()
        y = Var()
        inner_bag = Var()
        outer_bag = Var()
        inner_fa = Call(func=LoadName(name="FindAll"), args=[
            x,
            Call(func=LoadName(name="In"), args=[x, [1, 2]], kwargs=[]),
            inner_bag,
        ], kwargs=[])
        # Outer: for each Y in [10,20], find_all X in [1,2], collect inner_bag
        outer_goal = Call(func=LoadName(name="FindAll"), args=[
            [y, inner_bag],
            And(
                left=Call(func=LoadName(name="In"), args=[y, [10, 20]], kwargs=[]),
                right=inner_fa,
            ),
            outer_bag,
        ], kwargs=[])
        results = bindings(outer_goal, outer_bag)
        assert results == [[[10, [1, 2]], [20, [1, 2]]]]


# ── bag_of/3 ──────────────────────────────────────────────────────────────────


class TestBagOf:
    def test_bag_of_basic(self):
        """bag_of(X, member(X, [1,2]), Bag) → [1, 2]"""
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="BagOf"), args=[
            x,
            Call(func=LoadName(name="In"), args=[x, [1, 2]], kwargs=[]),
            bag,
        ], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[1, 2]]

    def test_bag_of_fails_on_empty(self):
        """bag_of(X, fail, _) → fails (no solutions)"""
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="BagOf"), args=[x, False, bag], kwargs=[])
        results = solutions_of(goal)
        assert results == []


# ── set_of/3 ──────────────────────────────────────────────────────────────────


class TestSetOf:
    def test_set_of_dedup(self):
        """set_of(X, member(X, [1,1,2,2,3]), Bag) → [1,2,3]"""
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="SetOf"), args=[
            x,
            Call(func=LoadName(name="In"), args=[x, [1, 1, 2, 2, 3]], kwargs=[]),
            bag,
        ], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[1, 2, 3]]

    def test_set_of_fails_on_empty(self):
        """set_of with no solutions fails."""
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="SetOf"), args=[x, False, bag], kwargs=[])
        results = solutions_of(goal)
        assert results == []

    def test_set_of_preserves_order(self):
        """set_of preserves first occurrence order."""
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="SetOf"), args=[
            x,
            Call(func=LoadName(name="In"), args=[x, [3, 1, 2, 1, 3]], kwargs=[]),
            bag,
        ], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[3, 1, 2]]


# ── for_all/2 ────────────────────────────────────────────────────────────────


class TestForAll:
    def test_for_all_succeeds(self):
        """for_all(member(X, [2,4,6]), X > 0) → succeeds"""
        x = Var()
        cond = Call(func=LoadName(name="In"), args=[x, [2, 4, 6]], kwargs=[])
        action = Gt(left=x, right=0)
        goal = Call(func=LoadName(name="ForAll"), args=[cond, action], kwargs=[])
        results = solutions_of(goal)
        assert len(results) == 1

    def test_for_all_fails(self):
        """for_all(member(X, [2,-1,6]), X > 0) → fails"""
        x = Var()
        cond = Call(func=LoadName(name="In"), args=[x, [2, -1, 6]], kwargs=[])
        action = Gt(left=x, right=0)
        goal = Call(func=LoadName(name="ForAll"), args=[cond, action], kwargs=[])
        results = solutions_of(goal)
        assert results == []

    def test_for_all_vacuously_true(self):
        """for_all(fail, _) → succeeds (vacuously true)."""
        x = Var()
        goal = Call(func=LoadName(name="ForAll"), args=[
            False,
            Gt(left=x, right=0),
        ], kwargs=[])
        results = solutions_of(goal)
        assert len(results) == 1


# ── call/N ───────────────────────────────────────────────────────────────────


class TestCallN:
    def test_call_1(self):
        """call(Goal) where Goal is a lambda-like callable."""
        mod = fresh_module()
        x = Var()
        results = [deref(x) for _ in call("Call", x, module=mod)]
        # call/1 with unbound goal — not callable, should produce no solutions
        assert results == []

    def test_call_goal_4(self):
        """call_goal with 3 extra args."""
        mod = fresh_module()
        # We need a callable that takes 3 extra args + trail + k
        called_with = []
        def my_goal(a1, a2, a3, trail, k):
            called_with.append((a1, a2, a3))
            yield None
            return; yield
        results = list(call("CallGoal", my_goal, 10, 20, 30, module=mod))
        assert len(results) == 1
        assert called_with == [(10, 20, 30)]

    def test_call_alias(self):
        """call/N aliases call_goal/N."""
        mod = fresh_module()
        called_with = []
        def my_goal(a1, trail, k):
            called_with.append(a1)
            yield None
            return; yield
        results = list(call("Call", my_goal, 42, module=mod))
        assert len(results) == 1
        assert called_with == [42]

    def test_call_5(self):
        """call/5 with 4 extra args."""
        mod = fresh_module()
        called_with = []
        def my_goal(a1, a2, a3, a4, trail, k):
            called_with.append((a1, a2, a3, a4))
            yield None
            return; yield
        results = list(call("Call", my_goal, 1, 2, 3, 4, module=mod))
        assert len(results) == 1
        assert called_with == [(1, 2, 3, 4)]


# ── .clausal integration ────────────────────────────────────────────────────


_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class TestClausalImport:
    def test_squares(self):
        """squares/2 from meta_test.clausal."""
        mod = _load_module("meta_test", os.path.join(_FIXTURE_DIR, "meta_test.clausal"))
        x = Var()
        results = [_deref_walk(x) for _ in call("squares", [1, 2, 3], x, module=mod.__dict__["$module"])]
        assert results == [[1, 4, 9]]

    def test_positives(self):
        """positives/2 from meta_test.clausal."""
        mod = _load_module("meta_test", os.path.join(_FIXTURE_DIR, "meta_test.clausal"))
        x = Var()
        results = [_deref_walk(x) for _ in call("positives", [-1, 2, -3, 4], x, module=mod.__dict__["$module"])]
        assert results == [[2, 4]]

    def test_unique_members(self):
        """unique_members/2 from meta_test.clausal."""
        mod = _load_module("meta_test", os.path.join(_FIXTURE_DIR, "meta_test.clausal"))
        x = Var()
        results = [_deref_walk(x) for _ in call("unique_members", [1, 2, 1, 3, 2], x, module=mod.__dict__["$module"])]
        assert results == [[1, 2, 3]]

    def test_all_positive_pass(self):
        """all_positive succeeds for all positive list."""
        mod = _load_module("meta_test", os.path.join(_FIXTURE_DIR, "meta_test.clausal"))
        results = list(call("all_positive", [1, 2, 3], module=mod.__dict__["$module"]))
        assert len(results) == 1

    def test_all_positive_fail(self):
        """all_positive fails if any element is non-positive."""
        mod = _load_module("meta_test", os.path.join(_FIXTURE_DIR, "meta_test.clausal"))
        results = list(call("all_positive", [1, -2, 3], module=mod.__dict__["$module"]))
        assert results == []
