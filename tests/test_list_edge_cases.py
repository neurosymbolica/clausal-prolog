"""Edge-case tests for list patterns Phases 1–4.

Tests cover corner cases not exercised by the main test_search.py suite:
 - Phase 1: [*ALL], multiple fixed before star, exact-length match, empty list
 - Phase 2: repeated vars (triple, cross-pattern), bidirectional edge cases
 - Phase 3: multiple _ in non-list, [*_], _ interactions
 - Phase 4: multiple fixed between stars, longer lists, single-element lists
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

from clausal.logic.database import Module
from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.import_hook import _load_module
import clausal.import_hook


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(filename: str) -> Module:
    path = os.path.join(os.path.dirname(__file__), "clausal_modules", filename)
    name = f"_edge_{filename.replace('.', '_')}"
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _edge_mod() -> Module:
    return _load("list_edge_cases.clausal")


def _lists_mod() -> Module:
    return _load("lists.clausal")


def _multistar_mod() -> Module:
    return _load("multistar.clausal")


def _anon_mod() -> Module:
    return _load("anon.clausal")


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1 edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestPhase1EdgeCases:
    """Basic [HEAD, *TAIL] decomposition edge cases."""

    def test_capture_all_empty(self):
        """[*ALL] on empty list → ALL=[]."""
        mod = _edge_mod()
        r = Var()
        results = [deref(r) for _ in call("capture_all", [], r, module=mod)]
        assert results == [[]]

    def test_capture_all_nonempty(self):
        """[*ALL] on [1,2,3] → ALL=[1,2,3]."""
        mod = _edge_mod()
        r = Var()
        results = [deref(r) for _ in call("capture_all", [1, 2, 3], r, module=mod)]
        assert results == [[1, 2, 3]]

    def test_capture_all_singleton(self):
        """[*ALL] on [42] → ALL=[42]."""
        mod = _edge_mod()
        r = Var()
        results = [deref(r) for _ in call("capture_all", [42], r, module=mod)]
        assert results == [[42]]

    def test_three_and_rest(self):
        """[A, B, C, *REST] extracts first three and remainder."""
        mod = _edge_mod()
        a, b, c, rest = Var(), Var(), Var(), Var()
        results = [
            (deref(a), deref(b), deref(c), deref(rest))
            for _ in call("three_and_rest", [10, 20, 30, 40, 50], a, b, c, rest, module=mod)
        ]
        assert results == [(10, 20, 30, [40, 50])]

    def test_three_and_rest_exact(self):
        """[A, B, C, *REST] with exactly 3 elements → REST=[]."""
        mod = _edge_mod()
        a, b, c, rest = Var(), Var(), Var(), Var()
        results = [
            (deref(a), deref(b), deref(c), deref(rest))
            for _ in call("three_and_rest", [10, 20, 30], a, b, c, rest, module=mod)
        ]
        assert results == [(10, 20, 30, [])]

    def test_three_and_rest_too_short(self):
        """[A, B, C, *REST] with 2 elements → no match."""
        mod = _edge_mod()
        a, b, c, rest = Var(), Var(), Var(), Var()
        results = list(call("three_and_rest", [10, 20], a, b, c, rest, module=mod))
        assert results == []

    def test_exactly_two_match(self):
        """[A, B] matches exactly a 2-element list."""
        mod = _edge_mod()
        a, b = Var(), Var()
        results = [(deref(a), deref(b)) for _ in call("exactly_two", [1, 2], a, b, module=mod)]
        assert results == [(1, 2)]

    def test_exactly_two_too_short(self):
        mod = _edge_mod()
        a, b = Var(), Var()
        results = list(call("exactly_two", [1], a, b, module=mod))
        assert results == []

    def test_exactly_two_too_long(self):
        mod = _edge_mod()
        a, b = Var(), Var()
        results = list(call("exactly_two", [1, 2, 3], a, b, module=mod))
        assert results == []

    def test_is_empty_succeeds(self):
        mod = _edge_mod()
        results = list(call("is_empty", [], module=mod))
        assert len(results) == 1

    def test_is_empty_fails_nonempty(self):
        mod = _edge_mod()
        results = list(call("is_empty", [1], module=mod))
        assert results == []

    def test_head_tail_regression(self):
        """Single-star [HEAD, *TAIL] still works (regression after multi-star)."""
        mod = _edge_mod()
        h, t = Var(), Var()
        results = [(deref(h), deref(t)) for _ in call("head_tail", [1, 2, 3], h, t, module=mod)]
        assert results == [(1, [2, 3])]

    def test_head_tail_singleton(self):
        mod = _edge_mod()
        h, t = Var(), Var()
        results = [(deref(h), deref(t)) for _ in call("head_tail", [99], h, t, module=mod)]
        assert results == [(99, [])]

    def test_head_tail_empty_fails(self):
        mod = _edge_mod()
        h, t = Var(), Var()
        results = list(call("head_tail", [], h, t, module=mod))
        assert results == []

    def test_length_zero(self):
        """length([], N) → N=0."""
        mod = _lists_mod()
        n = Var()
        results = [deref(n) for _ in call("length", [], n, module=mod)]
        assert results == [0]

    def test_length_three(self):
        mod = _lists_mod()
        n = Var()
        results = [deref(n) for _ in call("length", [1, 2, 3], n, module=mod)]
        assert results == [3]

    def test_length_singleton(self):
        mod = _lists_mod()
        n = Var()
        results = [deref(n) for _ in call("length", ["a"], n, module=mod)]
        assert results == [1]

    def test_length_check_correct(self):
        """length([1,2], 2) succeeds."""
        mod = _lists_mod()
        results = list(call("length", [1, 2], 2, module=mod))
        assert len(results) == 1

    def test_length_check_wrong(self):
        """length([1,2], 5) fails."""
        mod = _lists_mod()
        results = list(call("length", [1, 2], 5, module=mod))
        assert results == []


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2 edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestPhase2EdgeCases:
    """Repeated vars + bidirectional list unification edge cases."""

    def test_all_same_succeeds(self):
        """all_same(X, X, X) — triple repeat, all equal."""
        mod = _edge_mod()
        results = list(call("all_same", 5, 5, 5, module=mod))
        assert len(results) == 1

    def test_all_same_fails(self):
        """all_same(X, X, X) — fails when not all equal."""
        mod = _edge_mod()
        results = list(call("all_same", 5, 5, 6, module=mod))
        assert results == []

    def test_all_same_query_mode(self):
        """all_same(X, X, X) — with Var, binds all to same value."""
        mod = _edge_mod()
        x = Var()
        results = [deref(x) for _ in call("all_same", 42, 42, x, module=mod)]
        assert results == [42]

    def test_head_is(self):
        """head_is(X, [X, *_]) — extracts head and verifies match."""
        mod = _edge_mod()
        results = list(call("head_is", 1, [1, 2, 3], module=mod))
        assert len(results) == 1

    def test_head_is_fails(self):
        """head_is(X, [X, *_]) — fails when X != head."""
        mod = _edge_mod()
        results = list(call("head_is", 99, [1, 2, 3], module=mod))
        assert results == []

    def test_head_is_query(self):
        """head_is(X, [X, *_]) — extracts head into X."""
        mod = _edge_mod()
        x = Var()
        results = [deref(x) for _ in call("head_is", x, [10, 20], module=mod)]
        assert results == [10]

    def test_append_single_elements(self):
        """append([1], [2], R) → R=[1,2]."""
        mod = _lists_mod()
        r = Var()
        results = [deref(r) for _ in call("append", [1], [2], r, module=mod)]
        assert results == [[1, 2]]

    def test_append_compute_middle(self):
        """append([1], Y, [1, 2, 3]) → Y=[2,3]."""
        mod = _lists_mod()
        y = Var()
        results = [deref(y) for _ in call("append", [1], y, [1, 2, 3], module=mod)]
        assert results == [[2, 3]]

    def test_append_all_vars_with_ground_result(self):
        """append(X, Y, [1]) — 2 splits."""
        mod = _lists_mod()
        x, y = Var(), Var()
        pairs = [(deref(x), deref(y)) for _ in call("append", x, y, [1], module=mod)]
        assert ([], [1]) in pairs
        assert ([1], []) in pairs
        assert len(pairs) == 2

    def test_append_nested_lists(self):
        """append([[1]], [[2]], R) → R=[[1],[2]]."""
        mod = _lists_mod()
        r = Var()
        results = [deref(r) for _ in call("append", [[1]], [[2]], r, module=mod)]
        assert results == [[[1], [2]]]

    def test_last_two_elements(self):
        """last([1,2], X) → X=2."""
        mod = _lists_mod()
        x = Var()
        results = [deref(x) for _ in call("last", [1, 2], x, module=mod)]
        assert results == [2]

    def test_last_nested_list_element(self):
        """last([1, [2, 3]], X) → X=[2,3]."""
        mod = _lists_mod()
        x = Var()
        results = [deref(x) for _ in call("last", [1, [2, 3]], x, module=mod)]
        assert results == [[2, 3]]

    def test_last_empty_fails(self):
        """last([], X) → no solution."""
        mod = _lists_mod()
        x = Var()
        results = list(call("last", [], x, module=mod))
        assert results == []

    def test_bookend_single(self):
        """bookend([X]) — singleton is a bookend."""
        mod = _edge_mod()
        results = list(call("bookend", [1], module=mod))
        assert len(results) >= 1

    def test_bookend_same(self):
        """bookend([1, 2, 3, 1]) — first == last."""
        mod = _edge_mod()
        results = list(call("bookend", [1, 2, 3, 1], module=mod))
        assert len(results) >= 1

    def test_bookend_different_fails(self):
        """bookend([1, 2, 3, 4]) — first != last."""
        mod = _edge_mod()
        results = list(call("bookend", [1, 2, 3, 4], module=mod))
        assert results == []

    def test_bookend_two_same(self):
        """bookend([5, 5]) — two equal elements."""
        mod = _edge_mod()
        results = list(call("bookend", [5, 5], module=mod))
        assert len(results) >= 1

    def test_bookend_two_different_fails(self):
        """bookend([1, 2]) — two different elements."""
        mod = _edge_mod()
        results = list(call("bookend", [1, 2], module=mod))
        assert results == []


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3 edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestPhase3EdgeCases:
    """Anonymous _ variable edge cases."""

    def test_ignore_first_two(self):
        """ignore_first_two(_, _, X, X) — ignores first two, binds third and fourth."""
        mod = _edge_mod()
        results = list(call("ignore_first_two", "a", "b", 7, 7, module=mod))
        assert len(results) == 1

    def test_ignore_first_two_mismatch(self):
        """ignore_first_two(_, _, X, X) — fails when third != fourth."""
        mod = _edge_mod()
        results = list(call("ignore_first_two", "a", "b", 7, 8, module=mod))
        assert results == []

    def test_ignore_first_two_query(self):
        """ignore_first_two(_, _, X, X) — query mode: bind X."""
        mod = _edge_mod()
        x = Var()
        results = [deref(x) for _ in call("ignore_first_two", "a", "b", 42, x, module=mod)]
        assert results == [42]

    def test_is_list_empty(self):
        """is_list([*_]) — empty list is a list."""
        mod = _edge_mod()
        results = list(call("is_list", [], module=mod))
        assert len(results) == 1

    def test_is_list_nonempty(self):
        """is_list([*_]) — non-empty list is a list."""
        mod = _edge_mod()
        results = list(call("is_list", [1, 2, 3], module=mod))
        assert len(results) == 1

    def test_is_list_non_list_fails(self):
        """is_list([*_]) — non-list fails."""
        mod = _edge_mod()
        results = list(call("is_list", 42, module=mod))
        assert results == []

    def test_is_list_string_fails(self):
        """is_list([*_]) — string is not a list."""
        mod = _edge_mod()
        results = list(call("is_list", "hello", module=mod))
        assert results == []

    def test_has_pair_three_elements(self):
        """has_pair with 3 elements succeeds."""
        mod = _anon_mod()
        results = list(call("has_pair", [1, 2, 3], module=mod))
        assert len(results) >= 1

    def test_first_two_element_list(self):
        """first([H, *_], H) with 2-element list."""
        mod = _anon_mod()
        r = Var()
        results = [deref(r) for _ in call("first", [10, 20], r, module=mod)]
        assert results == [10]

    def test_second_exactly_two(self):
        """second([_, SECOND, *_], SECOND) with exactly 2 elements."""
        mod = _anon_mod()
        r = Var()
        results = [deref(r) for _ in call("second", [10, 20], r, module=mod)]
        assert results == [20]

    def test_second_fails_singleton(self):
        """second([_, SECOND, *_], SECOND) fails on singleton."""
        mod = _anon_mod()
        r = Var()
        results = list(call("second", [10], r, module=mod))
        assert results == []

    def test_member_of_pair_both(self):
        """member_of_pair(X, [X, X]) where X matches both positions → two solutions."""
        mod = _anon_mod()
        results = list(call("member_of_pair", 1, [1, 1], module=mod))
        assert len(results) == 2

    def test_const_numeric_input(self):
        """const(_, 42) with numeric input."""
        mod = _anon_mod()
        r = Var()
        results = [deref(r) for _ in call("const", 999, r, module=mod)]
        assert results == [42]

    def test_const_list_input(self):
        """const(_, 42) with list input."""
        mod = _anon_mod()
        r = Var()
        results = [deref(r) for _ in call("const", [1, 2, 3], r, module=mod)]
        assert results == [42]


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4 edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestPhase4EdgeCases:
    """Multi-star [*A, *B] combinatorial backtracking edge cases."""

    def test_split_longer_list(self):
        """split([1..5], A, B) → 6 solutions."""
        mod = _multistar_mod()
        a, b = Var(), Var()
        results = [(deref(a), deref(b)) for _ in call("split", [1, 2, 3, 4, 5], a, b, module=mod)]
        assert len(results) == 6
        assert results[0] == ([], [1, 2, 3, 4, 5])
        assert results[-1] == ([1, 2, 3, 4, 5], [])

    def test_split3_singleton(self):
        """split3([X, *A, *B], X, A, B) with singleton → X=elem, A=[], B=[]."""
        mod = _multistar_mod()
        x, a, b = Var(), Var(), Var()
        results = [
            (deref(x), deref(a), deref(b))
            for _ in call("split3", [42], x, a, b, module=mod)
        ]
        assert results == [(42, [], [])]

    def test_split3_two_elements(self):
        """split3([X, *A, *B], X, A, B) with [1,2] → 2 solutions."""
        mod = _multistar_mod()
        x, a, b = Var(), Var(), Var()
        results = [
            (deref(x), deref(a), deref(b))
            for _ in call("split3", [1, 2], x, a, b, module=mod)
        ]
        assert results == [(1, [], [2]), (1, [2], [])]

    def test_around_singleton(self):
        """around([*A, X, *B], X, [A, B]) with [1] → X=1, A=[], B=[]."""
        mod = _multistar_mod()
        x, p = Var(), Var()
        results = [(deref(x), deref(p)) for _ in call("around", [1], x, p, module=mod)]
        assert results == [(1, [[], []])]

    def test_around_duplicates(self):
        """around with duplicate values — finds element at each position."""
        mod = _multistar_mod()
        x, p = Var(), Var()
        results = [(deref(x), deref(p)) for _ in call("around", [1, 2, 1], x, p, module=mod)]
        assert len(results) == 3
        assert (1, [[], [2, 1]]) in results
        assert (2, [[1], [1]]) in results
        assert (1, [[1, 2], []]) in results

    def test_split3way_singleton(self):
        """split3way([1], A, B, C) — 3 solutions (one non-empty segment)."""
        mod = _multistar_mod()
        a, b, c = Var(), Var(), Var()
        results = [
            (deref(a), deref(b), deref(c))
            for _ in call("split3way", [1], a, b, c, module=mod)
        ]
        assert len(results) == 3
        assert ([], [], [1]) in results
        assert ([], [1], []) in results
        assert ([1], [], []) in results

    def test_split3way_three(self):
        """split3way([1,2,3], A, B, C) — 10 solutions (C(5,2) = 10)."""
        mod = _multistar_mod()
        a, b, c = Var(), Var(), Var()
        results = [
            (deref(a), deref(b), deref(c))
            for _ in call("split3way", [1, 2, 3], a, b, c, module=mod)
        ]
        # n=3, k=3 stars → C(n+k-1, k-1) = C(5,2) = 10
        assert len(results) == 10

    def test_bracket_basic(self):
        """bracket([*A, X, Y, *B], X, Y, A, B) — two fixed between stars."""
        mod = _edge_mod()
        x, y, a, b = Var(), Var(), Var(), Var()
        results = [
            (deref(x), deref(y), deref(a), deref(b))
            for _ in call("bracket", [1, 2, 3, 4], x, y, a, b, module=mod)
        ]
        # Possible positions for (X, Y):
        # (1,2) → A=[], B=[3,4]
        # (2,3) → A=[1], B=[4]
        # (3,4) → A=[1,2], B=[]
        assert len(results) == 3
        assert (1, 2, [], [3, 4]) in results
        assert (2, 3, [1], [4]) in results
        assert (3, 4, [1, 2], []) in results

    def test_bracket_too_short(self):
        """bracket needs at least 2 elements (for X and Y)."""
        mod = _edge_mod()
        x, y, a, b = Var(), Var(), Var(), Var()
        results = list(call("bracket", [1], x, y, a, b, module=mod))
        assert results == []

    def test_bracket_exact_two(self):
        """bracket([1,2], X, Y, A, B) → one solution."""
        mod = _edge_mod()
        x, y, a, b = Var(), Var(), Var(), Var()
        results = [
            (deref(x), deref(y), deref(a), deref(b))
            for _ in call("bracket", [1, 2], x, y, a, b, module=mod)
        ]
        assert results == [(1, 2, [], [])]

    def test_split_backtracking_cleanup(self):
        """Verify bindings are properly cleaned between backtracking iterations."""
        mod = _multistar_mod()
        a, b = Var(), Var()
        all_results = []
        for _ in call("split", [1, 2, 3], a, b, module=mod):
            all_results.append((deref(a), deref(b)))
        # Each result should be independent — no leaking from previous iteration
        for i, (ra, rb) in enumerate(all_results):
            assert ra + rb == [1, 2, 3], f"Solution {i}: {ra} + {rb} != [1,2,3]"

    def test_around_empty_fails(self):
        """around([], X, P) — no element to find."""
        mod = _multistar_mod()
        x, p = Var(), Var()
        results = list(call("around", [], x, p, module=mod))
        assert results == []

    def test_split3_empty_fails(self):
        """split3([], X, A, B) — needs at least one element for X."""
        mod = _multistar_mod()
        x, a, b = Var(), Var(), Var()
        results = list(call("split3", [], x, a, b, module=mod))
        assert results == []
