"""Tests for CLP(Z) upgrade: infinite-domain semantics.

Verifies that the solver operates over all integers (Z) by default,
with float('inf') sentinels for unbounded domains.
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var, get_attr
from clausal.logic.clpfd import (
    FD_KEY, _NEG_INF, _POS_INF,
    domain_from_range, domain_contains, domain_min, domain_max,
    domain_size, domain_intersection, domain_remove,
    domain_remove_above, domain_remove_below, domain_values,
    _ensure_fd, fd_eq, fd_ne, fd_lt, fd_le, fd_gt, fd_ge,
    in_domain, label, all_different,
)


def fresh_trail() -> Trail:
    return Trail()


# ── TestInfiniteDomains ─────────────────────────────────────────────────────


class TestInfiniteDomains:
    def test_default_domain_is_infinite(self):
        trail = fresh_trail()
        x = Var()
        state = _ensure_fd(x, trail)
        assert state.domain == ((_NEG_INF, _POS_INF),)

    def test_domain_size_infinite(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_size(d) == _POS_INF

    def test_domain_size_half_bounded_above(self):
        d = domain_from_range(0, _POS_INF)
        assert domain_size(d) == _POS_INF

    def test_domain_size_half_bounded_below(self):
        d = domain_from_range(_NEG_INF, 5)
        assert domain_size(d) == _POS_INF

    def test_domain_size_finite(self):
        d = domain_from_range(1, 10)
        assert domain_size(d) == 10

    def test_domain_contains_infinite(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_contains(d, 0)
        assert domain_contains(d, 999999999)
        assert domain_contains(d, -999999999)

    def test_domain_min_infinite(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_min(d) == _NEG_INF

    def test_domain_max_infinite(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_max(d) == _POS_INF

    def test_domain_values_infinite_raises(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        with pytest.raises(ValueError, match="[Uu]nbounded"):
            list(domain_values(d))

    def test_domain_values_half_bounded_raises(self):
        d = domain_from_range(0, _POS_INF)
        with pytest.raises(ValueError, match="[Uu]nbounded"):
            list(domain_values(d))

    def test_domain_values_finite_works(self):
        d = domain_from_range(1, 3)
        assert list(domain_values(d)) == [1, 2, 3]


# ── TestInfiniteIntersection ────────────────────────────────────────────────


class TestInfiniteIntersection:
    def test_intersect_infinite_with_finite(self):
        d1 = domain_from_range(_NEG_INF, _POS_INF)
        d2 = domain_from_range(1, 10)
        result = domain_intersection(d1, d2)
        assert result == ((1, 10),)

    def test_intersect_infinite_with_infinite(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_intersection(d, d) == ((_NEG_INF, _POS_INF),)

    def test_intersect_half_bounded(self):
        d1 = domain_from_range(_NEG_INF, 5)
        d2 = domain_from_range(0, _POS_INF)
        result = domain_intersection(d1, d2)
        assert result == ((0, 5),)

    def test_remove_from_infinite(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        result = domain_remove(d, 5)
        assert len(result) == 2
        assert result[0][1] == 4
        assert result[1][0] == 6

    def test_remove_above_infinite(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        result = domain_remove_above(d, 10)
        assert result == ((_NEG_INF, 10),)

    def test_remove_below_infinite(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        result = domain_remove_below(d, 0)
        assert result == ((0, _POS_INF),)


# ── TestConstraintWithInfiniteDomains ───────────────────────────────────────


class TestConstraintWithInfiniteDomains:
    def test_eq_narrows_to_singleton(self):
        trail = fresh_trail()
        x = Var()
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5

    def test_lt_narrows_upper(self):
        trail = fresh_trail()
        x = Var()
        assert fd_lt(x, 10, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_max(state.domain) == 9
        assert domain_min(state.domain) == _NEG_INF

    def test_gt_narrows_lower(self):
        trail = fresh_trail()
        x = Var()
        assert fd_gt(x, 0, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_min(state.domain) == 1
        assert domain_max(state.domain) == _POS_INF

    def test_gt_and_lt_narrows_to_finite(self):
        trail = fresh_trail()
        x = Var()
        assert fd_gt(x, 0, trail)
        assert fd_lt(x, 10, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_min(state.domain) == 1
        assert domain_max(state.domain) == 9

    def test_ne_on_infinite(self):
        trail = fresh_trail()
        x = Var()
        assert fd_ne(x, 5, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert not domain_contains(state.domain, 5)
        assert domain_contains(state.domain, 4)
        assert domain_contains(state.domain, 6)

    def test_eq_chain_propagates(self):
        trail = fresh_trail()
        x, y = Var(), Var()
        assert fd_eq(x, y, trail)
        assert fd_eq(y, 5, trail)
        assert deref(x) == 5

    def test_all_different_infinite(self):
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert all_different([x, y, z], trail)
        assert fd_eq(x, 1, trail)
        state_y = get_attr(y, FD_KEY)
        assert state_y is not None
        assert not domain_contains(state_y.domain, 1)


# ── TestLabelInfinite ───────────────────────────────────────────────────────


class TestLabelInfinite:
    def test_label_bounded_from_constraints(self):
        trail = fresh_trail()
        x = Var()
        assert fd_gt(x, 0, trail)
        assert fd_lt(x, 4, trail)
        results = []
        for _ in label([x], trail):
            results.append(deref(x))
        assert results == [1, 2, 3]

    def test_label_unbounded_raises(self):
        trail = fresh_trail()
        x = Var()
        assert fd_gt(x, 0, trail)
        # x has domain (1, +inf) — cannot label
        with pytest.raises(ValueError, match="[Uu]nbounded"):
            next(label([x], trail))

    def test_label_fully_unbounded_raises(self):
        trail = fresh_trail()
        x = Var()
        _ensure_fd(x, trail)
        with pytest.raises(ValueError, match="[Uu]nbounded"):
            next(label([x], trail))

    def test_label_first_fail_prefers_finite(self):
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain(x, 1, 2, trail)
        assert fd_gt(y, 0, trail)
        assert fd_lt(y, 100, trail)
        # First-fail should pick x first (size 2 < size 99)
        results = []
        gen = label([x, y], trail)
        next(gen)
        assert not is_var(deref(x))


# ── TestBacktrackingWithInfinite ────────────────────────────────────────────


class TestBacktrackingWithInfinite:
    def test_undo_restores_infinite_domain(self):
        trail = fresh_trail()
        x = Var()
        _ensure_fd(x, trail)
        mark = trail.mark()
        assert fd_lt(x, 10, trail)
        state = get_attr(x, FD_KEY)
        assert domain_max(state.domain) == 9
        trail.undo(mark)
        state_after = get_attr(x, FD_KEY)
        if state_after is not None:
            assert domain_max(state_after.domain) == _POS_INF

    def test_undo_restores_after_eq(self):
        trail = fresh_trail()
        x = Var()
        mark = trail.mark()
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5
        trail.undo(mark)
        assert is_var(deref(x))


# ── TestExistingBehaviorUnchanged ───────────────────────────────────────────


class TestExistingBehaviorUnchanged:
    def test_nqueens_still_finds_92(self):
        from benchmarks.workloads import bench_nqueens
        assert bench_nqueens() == 92

    def test_in_domain_still_works(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 5, trail)
        state = get_attr(x, FD_KEY)
        assert state.domain == ((1, 5),)
        assert not unify(x, 7, trail)

    def test_sudoku_example_loads(self):
        from clausal.testing import load_clausal_module, collect_tests, run_test
        mod = load_clausal_module("clausal/examples/sudoku.clausal")
        tests = collect_tests(mod)
        for desc in tests:
            result = run_test(mod, desc)
            assert result.passed, f"sudoku test {desc!r} failed"
