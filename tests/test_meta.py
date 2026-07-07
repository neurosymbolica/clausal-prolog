"""Tests for V2-10 meta-predicates: find_all, bag_of, set_of, for_all, call/N."""

from __future__ import annotations

from clausal.logic.database import Module
from clausal.logic.solve import call, solve, _deref_walk
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import And, Call, LoadName, Gt


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
        # nv
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="findall"), args=[
            x,
            Call(func=LoadName(name="in_"), args=[x, [1, 2, 3]], kwargs=[]),
            bag,
        ], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[1, 2, 3]]

    def test_find_all_with_filter(self):
        """find_all(X, (member(X, [1,2,3]) and X > 1), Bag) → [2, 3]"""
        # nv
        x = Var()
        bag = Var()
        inner = And(
            left=Call(func=LoadName(name="in_"), args=[x, [1, 2, 3]], kwargs=[]),
            right=Gt(left=x, right=1),
        )
        goal = Call(func=LoadName(name="findall"), args=[x, inner, bag], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[2, 3]]

    def test_find_all_fail_empty_list(self):
        """find_all(X, fail, Bag) → [] (succeeds with empty list)"""
        # nv
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="findall"), args=[x, False, bag], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[]]

    def test_find_all_template_expression(self):
        """find_all([X,Y], cross product) → cartesian product"""
        # nv
        x = Var()
        y = Var()
        bag = Var()
        inner = And(
            left=Call(func=LoadName(name="in_"), args=[x, ["a", "b"]], kwargs=[]),
            right=Call(func=LoadName(name="in_"), args=[y, [1, 2]], kwargs=[]),
        )
        goal = Call(func=LoadName(name="findall"), args=[[x, y], inner, bag], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[["a", 1], ["a", 2], ["b", 1], ["b", 2]]]

    def test_find_all_no_side_effects(self):
        """find_all should undo bindings from inner goal."""
        # nv
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="findall"), args=[
            x,
            Call(func=LoadName(name="in_"), args=[x, [10, 20]], kwargs=[]),
            bag,
        ], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[10, 20]]

    def test_find_all_nested(self):
        """Nested find_all: outer collects inner results."""
        # nv
        x = Var()
        y = Var()
        inner_bag = Var()
        outer_bag = Var()
        inner_fa = Call(func=LoadName(name="findall"), args=[
            x,
            Call(func=LoadName(name="in_"), args=[x, [1, 2]], kwargs=[]),
            inner_bag,
        ], kwargs=[])
        # Outer: for each Y in [10,20], find_all X in [1,2], collect inner_bag
        outer_goal = Call(func=LoadName(name="findall"), args=[
            [y, inner_bag],
            And(
                left=Call(func=LoadName(name="in_"), args=[y, [10, 20]], kwargs=[]),
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
        # nv
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="bagof"), args=[
            x,
            Call(func=LoadName(name="in_"), args=[x, [1, 2]], kwargs=[]),
            bag,
        ], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[1, 2]]

    def test_bag_of_fails_on_empty(self):
        """bag_of(X, fail, _) → fails (no solutions)"""
        # nv
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="bagof"), args=[x, False, bag], kwargs=[])
        results = solutions_of(goal)
        assert results == []


# ── set_of/3 ──────────────────────────────────────────────────────────────────


class TestSetOf:
    def test_set_of_dedup(self):
        """set_of(X, member(X, [1,1,2,2,3]), Bag) → [1,2,3]"""
        # nv
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="setof"), args=[
            x,
            Call(func=LoadName(name="in_"), args=[x, [1, 1, 2, 2, 3]], kwargs=[]),
            bag,
        ], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[1, 2, 3]]

    def test_set_of_fails_on_empty(self):
        """set_of with no solutions fails."""
        # nv
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="setof"), args=[x, False, bag], kwargs=[])
        results = solutions_of(goal)
        assert results == []

    def test_set_of_is_sorted(self):
        """set_of returns a sorted list with duplicates removed (ISO /
        docs/meta_predicates.md). Reversed from the previous insertion-order
        behaviour by A03-F005 — findall/bagof still preserve order."""
        # nv
        x = Var()
        bag = Var()
        goal = Call(func=LoadName(name="setof"), args=[
            x,
            Call(func=LoadName(name="in_"), args=[x, [3, 1, 2, 1, 3]], kwargs=[]),
            bag,
        ], kwargs=[])
        results = bindings(goal, bag)
        assert results == [[1, 2, 3]]


# ── for_all/2 ────────────────────────────────────────────────────────────────


class TestForAll:
    def test_for_all_succeeds(self):
        """for_all(member(X, [2,4,6]), X > 0) → succeeds"""
        # nv
        x = Var()
        cond = Call(func=LoadName(name="in_"), args=[x, [2, 4, 6]], kwargs=[])
        action = Gt(left=x, right=0)
        goal = Call(func=LoadName(name="forall"), args=[cond, action], kwargs=[])
        results = solutions_of(goal)
        assert len(results) == 1

    def test_for_all_fails(self):
        """for_all(member(X, [2,-1,6]), X > 0) → fails"""
        # nv
        x = Var()
        cond = Call(func=LoadName(name="in_"), args=[x, [2, -1, 6]], kwargs=[])
        action = Gt(left=x, right=0)
        goal = Call(func=LoadName(name="forall"), args=[cond, action], kwargs=[])
        results = solutions_of(goal)
        assert results == []

    def test_for_all_vacuously_true(self):
        """for_all(fail, _) → succeeds (vacuously true)."""
        # nv
        x = Var()
        goal = Call(func=LoadName(name="forall"), args=[
            False,
            Gt(left=x, right=0),
        ], kwargs=[])
        results = solutions_of(goal)
        assert len(results) == 1


# ── call/N ───────────────────────────────────────────────────────────────────


class TestCallN:
    def test_call_1(self):
        """call(Goal) where Goal is a lambda-like callable."""
        # nv
        mod = fresh_module()
        x = Var()
        results = [deref(x) for _ in call("call", x, module=mod)]
        # call/1 with unbound goal — not callable, should produce no solutions
        assert results == []

    def test_call_goal_4(self):
        """call_goal with 3 extra args."""
        # nv
        mod = fresh_module()
        # We need a callable that takes 3 extra args + trail + k
        called_with = []
        def my_goal(a1, a2, a3, trail, k):
            called_with.append((a1, a2, a3))
            yield None
            return; yield
        results = list(call("call_goal", my_goal, 10, 20, 30, module=mod))
        assert len(results) == 1
        assert called_with == [(10, 20, 30)]

    def test_call_alias(self):
        """call/N aliases call_goal/N."""
        # nv
        mod = fresh_module()
        called_with = []
        def my_goal(a1, trail, k):
            called_with.append(a1)
            yield None
            return; yield
        results = list(call("call", my_goal, 42, module=mod))
        assert len(results) == 1
        assert called_with == [42]

    def test_call_5(self):
        """call/5 with 4 extra args."""
        # nv
        mod = fresh_module()
        called_with = []
        def my_goal(a1, a2, a3, a4, trail, k):
            called_with.append((a1, a2, a3, a4))
            yield None
            return; yield
        results = list(call("call", my_goal, 1, 2, 3, 4, module=mod))
        assert len(results) == 1
        assert called_with == [(1, 2, 3, 4)]


# ── .clausal integration ────────────────────────────────────────────────────
# TestClausalImport removed: behavior moved to tests/fixtures/meta_test.clausal.
