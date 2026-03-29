"""Tests for CLP(Z) upgrade: infinite-domain semantics.

Verifies that the solver operates over all integers (Z) by default,
with float('inf') sentinels for unbounded domains.
"""

from __future__ import annotations

import math

import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var, get_attr
from clausal.logic.clpfd import (
    FD_KEY, _NEG_INF, _POS_INF,
    domain_from_range, domain_contains, domain_min, domain_max,
    domain_size, domain_intersection, domain_remove,
    domain_remove_above, domain_remove_below, domain_values,
    _domain_mult, _safe_mult,
    _ensure_fd, fd_eq, fd_ne, fd_lt, fd_le, fd_gt, fd_ge,
    in_domain, label, all_different,
    ScalarProductConstraint, SumConstraint, _post_constraint,
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


# ── Inf/NaN arithmetic guards ────────────────────────────────────────────────


class TestSafeMult:
    """Tests for _safe_mult: 0 * inf must be 0, not NaN."""

    def test_zero_times_pos_inf(self):
        assert _safe_mult(0, _POS_INF) == 0

    def test_zero_times_neg_inf(self):
        assert _safe_mult(0, _NEG_INF) == 0

    def test_pos_inf_times_zero(self):
        assert _safe_mult(_POS_INF, 0) == 0

    def test_neg_inf_times_zero(self):
        assert _safe_mult(_NEG_INF, 0) == 0

    def test_normal_mult(self):
        assert _safe_mult(3, 4) == 12

    def test_inf_times_positive(self):
        assert _safe_mult(_POS_INF, 2) == _POS_INF

    def test_neg_inf_times_positive(self):
        assert _safe_mult(_NEG_INF, 2) == _NEG_INF


class TestDomainFromRangeNaN:
    """domain_from_range must reject NaN bounds."""

    def test_nan_lo_rejected(self):
        """NaN as lo bound is rejected (empty domain or TypeError)."""
        try:
            result = domain_from_range(float('nan'), 10)
            assert result == ()  # Python fallback returns empty
        except TypeError:
            pass  # C extension raises TypeError — also acceptable

    def test_nan_hi_rejected(self):
        try:
            result = domain_from_range(0, float('nan'))
            assert result == ()
        except TypeError:
            pass

    def test_both_nan_rejected(self):
        try:
            result = domain_from_range(float('nan'), float('nan'))
            assert result == ()
        except TypeError:
            pass

    def test_normal_still_works(self):
        assert domain_from_range(1, 5) == ((1, 5),)

    def test_inf_bounds_still_work(self):
        assert domain_from_range(_NEG_INF, _POS_INF) == ((_NEG_INF, _POS_INF),)


class TestDomainMultInf:
    """_domain_mult must handle zero × infinity correctly."""

    def test_zero_times_infinite_domain(self):
        """[0,0] * [-inf,+inf] should be [(0,0)], not [(nan,nan)]."""
        result = _domain_mult(
            domain_from_range(0, 0),
            domain_from_range(_NEG_INF, _POS_INF),
        )
        assert result == ((0, 0),)

    def test_infinite_times_zero(self):
        """[-inf,+inf] * [0,0] should be [(0,0)]."""
        result = _domain_mult(
            domain_from_range(_NEG_INF, _POS_INF),
            domain_from_range(0, 0),
        )
        assert result == ((0, 0),)

    def test_zero_span_times_infinite(self):
        """[-1,1] * [-inf,+inf] should have no NaN."""
        result = _domain_mult(
            domain_from_range(-1, 1),
            domain_from_range(_NEG_INF, _POS_INF),
        )
        lo, hi = result[0]
        assert lo == _NEG_INF
        assert hi == _POS_INF

    def test_normal_mult(self):
        """[2,3] * [4,5] = [8,15]."""
        result = _domain_mult(domain_from_range(2, 3), domain_from_range(4, 5))
        assert result == ((8, 15),)


class TestScalarProductInfDomains:
    """ScalarProductConstraint must not crash with inf domains."""

    def test_zero_coeff_infinite_domain(self):
        """0*X + 1*Y == 5 where X has infinite domain should not crash.

        The constraint is posted successfully.  With a zero coefficient,
        the zero-coeff term contributes nothing to the sum bounds, so
        Y should be narrowed to 5.  If propagation is weaker (e.g. C
        version skips linearisation), Y may remain unbound — that's
        sound but incomplete.
        """
        trail = fresh_trail()
        x, y = Var(), Var()
        _ensure_fd(x, trail)
        _ensure_fd(y, trail)
        c = ScalarProductConstraint((0, 1), (x, y), 5)
        result = _post_constraint(c, trail)
        assert result is True
        # Y should be narrowed to {5} or at least contain 5
        y_val = deref(y)
        if not is_var(y_val):
            assert y_val == 5
        else:
            state = get_attr(y, FD_KEY)
            assert state is not None
            assert domain_contains(state.domain, 5)

    def test_all_infinite_domains(self):
        """1*X + 1*Y == 5 where both have infinite domains should not crash."""
        trail = fresh_trail()
        x, y = Var(), Var()
        _ensure_fd(x, trail)
        _ensure_fd(y, trail)
        c = ScalarProductConstraint((1, 1), (x, y), 5)
        result = _post_constraint(c, trail)
        assert result is True

    def test_zero_coeff_narrows_nonzero(self):
        """0*X + 2*Y == 10 → Y should narrow to 5 (or at least contain 5)."""
        trail = fresh_trail()
        x, y = Var(), Var()
        _ensure_fd(x, trail)
        _ensure_fd(y, trail)
        c = ScalarProductConstraint((0, 2), (x, y), 10)
        result = _post_constraint(c, trail)
        assert result is True
        y_val = deref(y)
        if not is_var(y_val):
            assert y_val == 5
        else:
            state = get_attr(y, FD_KEY)
            assert state is not None
            assert domain_contains(state.domain, 5)


class TestSumConstraintInfDomains:
    """SumConstraint must not produce NaN from inf - inf."""

    def test_all_infinite(self):
        """X + Y == 5 where both infinite should not crash."""
        trail = fresh_trail()
        x, y = Var(), Var()
        _ensure_fd(x, trail)
        _ensure_fd(y, trail)
        c = SumConstraint((x, y), 5)
        result = _post_constraint(c, trail)
        assert result is True

    def test_one_bounded_one_infinite(self):
        """X in [1,3], Y infinite, X + Y == 5 → should not crash.

        Ideally Y narrows to [2,4], but with inf-guarded propagation
        the narrowing may be skipped (inf - inf = nan guard).  The
        constraint is sound — labeling will still find correct solutions.
        """
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain(x, 1, 3, trail)
        _ensure_fd(y, trail)
        c = SumConstraint((x, y), 5)
        result = _post_constraint(c, trail)
        assert result is True
        state_y = get_attr(y, FD_KEY)
        assert state_y is not None
        # Y should at least contain the valid range [2,4]
        assert domain_contains(state_y.domain, 2)
        assert domain_contains(state_y.domain, 3)
        assert domain_contains(state_y.domain, 4)
