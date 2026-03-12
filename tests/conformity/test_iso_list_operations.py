"""ISO Prolog conformity: list operations.

ISO does not standardize most list predicates, but they are part of
virtually every Prolog's standard library.  This file tests clausal's
equivalents.

Clausal builtins:
  member/2, append/3, length/2, last/2, reverse/2,
  nth0/3, nth1/3, flatten/2, msort/2, sort/2,
  permutation/2, select/3, subtract/3, intersection/3,
  union/3, list_to_set/2, sum_list/2, max_list/2, min_list/2.

Membership idiom:
  Prolog's member/2 corresponds to clausal's ``in`` / ``not in`` operators
  in .clausal syntax.  ``X in List`` compiles to an In goal node;
  ``X not in List`` compiles to NotIn.  The member/2 builtin is also
  available for use via the call() API.

Differences from Prolog:
  - Lists are Python lists, not cons-pairs.
  - No partial lists (a list with Var tail).
    member/2 and append/3 operate on concrete Python lists.
  - sort/2 removes duplicates (like ISO sort/2).
    msort/2 preserves duplicates (like ISO msort/2).
  - nth0/3 is 0-based, nth1/3 is 1-based.
"""

from __future__ import annotations

import pytest
from clausal.logic.database import Module
from clausal.logic.solve import solve, once
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Call, LoadName, In, NotIn


def _call_results(functor, *args, mod=None):
    """Call builtin, collect deref'd values of all Var args per solution."""
    if mod is None:
        mod = Module("test")
    goal = Call(func=LoadName(name=functor), args=list(args), kwargs=[])
    results = []
    for _ in solve(goal, mod):
        results.append(tuple(deref(a) for a in args))
    return results


def _call_var(functor, *args, var_index=-1, mod=None):
    """Call builtin, collect deref'd value of one Var arg per solution."""
    if mod is None:
        mod = Module("test")
    goal = Call(func=LoadName(name=functor), args=list(args), kwargs=[])
    var = args[var_index]
    return [deref(var) for _ in solve(goal, mod)]


# ── member/2 ──────────────────────────────────────────────────────────────────


class TestMember:
    def test_member_found(self):
        """member(b, [a,b,c]) succeeds."""
        mod = Module("test")
        goal = Call(func=LoadName(name="member"), args=["b", ["a", "b", "c"]], kwargs=[])
        assert once(goal, mod) is not None

    def test_member_not_found(self):
        """member(d, [a,b,c]) fails."""
        mod = Module("test")
        goal = Call(func=LoadName(name="member"), args=["d", ["a", "b", "c"]], kwargs=[])
        assert once(goal, mod) is None

    def test_member_enumerates(self):
        """member(X, [1,2,3]) generates 1, 2, 3."""
        x = Var()
        results = _call_var("member", x, [1, 2, 3], var_index=0)
        assert results == [1, 2, 3]

    def test_member_empty_list(self):
        """member(X, []) fails."""
        x = Var()
        results = _call_var("member", x, [], var_index=0)
        assert results == []

    def test_member_duplicates(self):
        """member(X, [a,b,a]) generates a, b, a."""
        x = Var()
        results = _call_var("member", x, ["a", "b", "a"], var_index=0)
        assert results == ["a", "b", "a"]


# ── in / not in (idiomatic clausal membership) ───────────────────────────────


class TestInOperator:
    """The ``in`` operator is clausal's native syntax for membership.
    ``X in [1,2,3]`` compiles to an In goal node; ``X not in [1,2,3]``
    compiles to NotIn.  These correspond to Prolog's member/2."""

    def test_in_found(self):
        """'b' in ['a','b','c'] succeeds."""
        goal = In(left="b", right=["a", "b", "c"])
        assert once(goal, Module("test")) is not None

    def test_in_not_found(self):
        """'d' in ['a','b','c'] fails."""
        goal = In(left="d", right=["a", "b", "c"])
        assert once(goal, Module("test")) is None

    def test_in_enumerates(self):
        """X in [1,2,3] generates 1, 2, 3."""
        x = Var()
        goal = In(left=x, right=[1, 2, 3])
        results = [deref(x) for _ in solve(goal, Module("test"))]
        assert results == [1, 2, 3]

    def test_in_empty_list(self):
        """X in [] fails."""
        x = Var()
        goal = In(left=x, right=[])
        results = [deref(x) for _ in solve(goal, Module("test"))]
        assert results == []

    def test_in_duplicates(self):
        """X in ['a','b','a'] generates a, b, a."""
        x = Var()
        goal = In(left=x, right=["a", "b", "a"])
        results = [deref(x) for _ in solve(goal, Module("test"))]
        assert results == ["a", "b", "a"]

    def test_not_in_absent(self):
        """'d' not in ['a','b','c'] succeeds."""
        goal = NotIn(left="d", right=["a", "b", "c"])
        assert once(goal, Module("test")) is not None

    def test_not_in_present(self):
        """'b' not in ['a','b','c'] fails."""
        goal = NotIn(left="b", right=["a", "b", "c"])
        assert once(goal, Module("test")) is None

    def test_not_in_empty(self):
        """'x' not in [] succeeds (nothing is in an empty list)."""
        goal = NotIn(left="x", right=[])
        assert once(goal, Module("test")) is not None


# ── append/3 ──────────────────────────────────────────────────────────────────


class TestAppend:
    def test_append_two_lists(self):
        """append([1,2], [3,4], X) → X = [1,2,3,4]."""
        x = Var()
        results = _call_var("append", [1, 2], [3, 4], x, var_index=2)
        assert results == [[1, 2, 3, 4]]

    def test_append_empty_left(self):
        x = Var()
        results = _call_var("append", [], [1, 2], x, var_index=2)
        assert results == [[1, 2]]

    def test_append_empty_right(self):
        x = Var()
        results = _call_var("append", [1, 2], [], x, var_index=2)
        assert results == [[1, 2]]

    def test_append_both_empty(self):
        x = Var()
        results = _call_var("append", [], [], x, var_index=2)
        assert results == [[]]

    def test_append_split_mode(self):
        """append(X, Y, [1,2,3]) enumerates all splits."""
        x, y = Var(), Var()
        results = _call_results("append", x, y, [1, 2, 3])
        expected_x = [[], [1], [1, 2], [1, 2, 3]]
        expected_y = [[1, 2, 3], [2, 3], [3], []]
        assert [r[0] for r in results] == expected_x
        assert [r[1] for r in results] == expected_y


# ── length/2 ──────────────────────────────────────────────────────────────────


class TestLength:
    def test_length_of_list(self):
        """length([a,b,c], N) → N = 3."""
        n = Var()
        results = _call_var("length", ["a", "b", "c"], n, var_index=1)
        assert results == [3]

    def test_length_empty(self):
        n = Var()
        results = _call_var("length", [], n, var_index=1)
        assert results == [0]

    def test_length_one(self):
        n = Var()
        results = _call_var("length", [42], n, var_index=1)
        assert results == [1]


# ── last/2 ────────────────────────────────────────────────────────────────────


class TestLast:
    def test_last_element(self):
        """last([1,2,3], X) → X = 3."""
        x = Var()
        results = _call_var("last", [1, 2, 3], x, var_index=1)
        assert results == [3]

    def test_last_singleton(self):
        x = Var()
        results = _call_var("last", [42], x, var_index=1)
        assert results == [42]

    def test_last_empty_fails(self):
        x = Var()
        results = _call_var("last", [], x, var_index=1)
        assert results == []


# ── reverse/2 ────────────────────────────────────────────────────────────────


class TestReverse:
    def test_reverse_list(self):
        """reverse([1,2,3], X) → X = [3,2,1]."""
        x = Var()
        results = _call_var("reverse", [1, 2, 3], x, var_index=1)
        assert results == [[3, 2, 1]]

    def test_reverse_empty(self):
        x = Var()
        results = _call_var("reverse", [], x, var_index=1)
        assert results == [[]]

    def test_reverse_singleton(self):
        x = Var()
        results = _call_var("reverse", [42], x, var_index=1)
        assert results == [[42]]

    def test_reverse_involution(self):
        """reverse(reverse(L)) = L."""
        x = Var()
        results = _call_var("reverse", [1, 2, 3], x, var_index=1)
        y = Var()
        results2 = _call_var("reverse", results[0], y, var_index=1)
        assert results2 == [[1, 2, 3]]


# ── nth0/3 and nth1/3 ────────────────────────────────────────────────────────


class TestNth:
    def test_nth0_first(self):
        """nth0(0, [a,b,c], X) → X = a."""
        x = Var()
        results = _call_var("nth0", 0, ["a", "b", "c"], x, var_index=2)
        assert results == ["a"]

    def test_nth0_last(self):
        x = Var()
        results = _call_var("nth0", 2, ["a", "b", "c"], x, var_index=2)
        assert results == ["c"]

    def test_nth1_first(self):
        """nth1(1, [a,b,c], X) → X = a (1-based)."""
        x = Var()
        results = _call_var("nth1", 1, ["a", "b", "c"], x, var_index=2)
        assert results == ["a"]

    def test_nth1_last(self):
        x = Var()
        results = _call_var("nth1", 3, ["a", "b", "c"], x, var_index=2)
        assert results == ["c"]

    def test_nth0_out_of_range(self):
        x = Var()
        results = _call_var("nth0", 5, ["a", "b"], x, var_index=2)
        assert results == []

    def test_nth1_zero_fails(self):
        """nth1 is 1-based; 0 is out of range."""
        x = Var()
        results = _call_var("nth1", 0, ["a", "b"], x, var_index=2)
        assert results == []


# ── sort/2 and msort/2 ───────────────────────────────────────────────────────


class TestSort:
    def test_sort_removes_duplicates(self):
        """ISO: sort([3,1,2,1], X) → X = [1,2,3]."""
        x = Var()
        results = _call_var("sort", [3, 1, 2, 1], x, var_index=1)
        assert results == [[1, 2, 3]]

    def test_sort_already_sorted(self):
        x = Var()
        results = _call_var("sort", [1, 2, 3], x, var_index=1)
        assert results == [[1, 2, 3]]

    def test_sort_empty(self):
        x = Var()
        results = _call_var("sort", [], x, var_index=1)
        assert results == [[]]

    def test_msort_preserves_duplicates(self):
        """msort([3,1,2,1], X) → X = [1,1,2,3]."""
        x = Var()
        results = _call_var("msort", [3, 1, 2, 1], x, var_index=1)
        assert results == [[1, 1, 2, 3]]

    def test_sort_strings(self):
        x = Var()
        results = _call_var("sort", ["c", "a", "b"], x, var_index=1)
        assert results == [["a", "b", "c"]]


# ── flatten/2 ────────────────────────────────────────────────────────────────


class TestFlatten:
    def test_flatten_nested(self):
        """flatten([1,[2,[3]],4], X) → X = [1,2,3,4]."""
        x = Var()
        results = _call_var("flatten", [1, [2, [3]], 4], x, var_index=1)
        assert results == [[1, 2, 3, 4]]

    def test_flatten_already_flat(self):
        x = Var()
        results = _call_var("flatten", [1, 2, 3], x, var_index=1)
        assert results == [[1, 2, 3]]

    def test_flatten_empty(self):
        x = Var()
        results = _call_var("flatten", [], x, var_index=1)
        assert results == [[]]


# ── permutation/2 ────────────────────────────────────────────────────────────


class TestPermutation:
    def test_permutation_generates_all(self):
        """permutation([1,2,3], X) generates 6 permutations."""
        x = Var()
        results = _call_var("permutation", [1, 2, 3], x, var_index=1)
        assert len(results) == 6
        assert [1, 2, 3] in results
        assert [3, 2, 1] in results

    def test_permutation_empty(self):
        x = Var()
        results = _call_var("permutation", [], x, var_index=1)
        assert results == [[]]

    def test_permutation_singleton(self):
        x = Var()
        results = _call_var("permutation", [42], x, var_index=1)
        assert results == [[42]]


# ── select/3 ─────────────────────────────────────────────────────────────────


class TestSelect:
    def test_select_element(self):
        """select(2, [1,2,3], X) → X = [1,3]."""
        x = Var()
        results = _call_var("select", 2, [1, 2, 3], x, var_index=2)
        assert [1, 3] in results

    def test_select_first(self):
        x = Var()
        results = _call_var("select", 1, [1, 2, 3], x, var_index=2)
        assert [2, 3] in results

    def test_select_not_found(self):
        x = Var()
        results = _call_var("select", 9, [1, 2, 3], x, var_index=2)
        assert results == []


# ── Set operations ────────────────────────────────────────────────────────────


class TestSetOperations:
    def test_subtract(self):
        """subtract([1,2,3,4], [2,4], X) → X = [1,3]."""
        x = Var()
        results = _call_var("subtract", [1, 2, 3, 4], [2, 4], x, var_index=2)
        assert results == [[1, 3]]

    def test_intersection(self):
        """intersection([1,2,3], [2,3,4], X) → X = [2,3]."""
        x = Var()
        results = _call_var("intersection", [1, 2, 3], [2, 3, 4], x, var_index=2)
        assert results == [[2, 3]]

    def test_union(self):
        """union([1,2], [2,3], X) → X = [1,2,3]."""
        x = Var()
        results = _call_var("union", [1, 2], [2, 3], x, var_index=2)
        assert results == [[1, 2, 3]]

    def test_list_to_set(self):
        """list_to_set([1,2,1,3,2], X) → X = [1,2,3]."""
        x = Var()
        results = _call_var("list_to_set", [1, 2, 1, 3, 2], x, var_index=1)
        assert results == [[1, 2, 3]]


# ── Aggregate operations ─────────────────────────────────────────────────────


class TestAggregates:
    def test_sum_list(self):
        """sum_list([1,2,3,4], X) → X = 10."""
        x = Var()
        results = _call_var("sum_list", [1, 2, 3, 4], x, var_index=1)
        assert results == [10]

    def test_sum_list_empty(self):
        x = Var()
        results = _call_var("sum_list", [], x, var_index=1)
        assert results == [0]

    def test_max_list(self):
        """max_list([3,1,4,1,5], X) → X = 5."""
        x = Var()
        results = _call_var("max_list", [3, 1, 4, 1, 5], x, var_index=1)
        assert results == [5]

    def test_min_list(self):
        """min_list([3,1,4,1,5], X) → X = 1."""
        x = Var()
        results = _call_var("min_list", [3, 1, 4, 1, 5], x, var_index=1)
        assert results == [1]

    def test_max_list_singleton(self):
        x = Var()
        results = _call_var("max_list", [42], x, var_index=1)
        assert results == [42]
