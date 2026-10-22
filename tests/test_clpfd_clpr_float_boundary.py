"""The CLP(Z) <-> CLP(R) bound seam at the float boundary.

An FD bound that flows into a real interval is rounded OUTWARD (a lower
bound never above the integer, an upper bound never below it), and a real
bound that flows into an FD domain is exact (``math.ceil``/``math.floor``
over the whole double range), in the C hook as in its Python twin.
Closes todo/done/clpfd-clpr-float-boundary-soundness-2026-09-03.md.
"""

from __future__ import annotations

import math
import sys

import pytest

from clausal.logic import clpfd
from clausal.logic.clpfd import (
    FD_KEY, _ensure_fd, _fd_hook, _c_fd_hook, _safe_float_hi,
    _safe_float_lo, domain_from_range, domain_max, domain_min, in_domain,
)
from clausal.logic.clpr import (
    REAL_KEY, RealVar, _get_var_interval, _promote_fd_to_real, in_real,
)
from clausal.logic.variables import (
    Trail, Var, deref, get_attr, put_attr, unify,
)

FLOAT_MAX = sys.float_info.max
INF = math.inf
BIG = 2 ** 60          # a double's ULP here is 256: 2**60 + 1 is not exact

HOOKS = [pytest.param(_c_fd_hook, id="c"), pytest.param(_fd_hook, id="py")]


def real(v):
    return get_attr(deref(v), REAL_KEY)


def fd_domain(v):
    return get_attr(deref(v), FD_KEY).domain


# ── FD -> real: outward rounding ─────────────────────────────────────────────


class TestFdBoundToFloat:
    @pytest.mark.parametrize("x", [BIG + 1, BIG - 1, -(BIG + 1), 3 ** 40 + 1])
    def test_lo_never_above_and_hi_never_below_the_integer(self, x):
        assert _safe_float_lo(x) <= x
        assert _safe_float_hi(x) >= x

    @pytest.mark.parametrize("x", [0, 7, -7, 2 ** 53, BIG, 10 ** 18, 5.5])
    def test_an_exact_value_is_not_loosened(self, x):
        assert _safe_float_lo(x) == x
        assert _safe_float_hi(x) == x

    def test_by_one_ulp_only(self):
        assert _safe_float_hi(BIG + 1) == math.nextafter(float(BIG), INF)
        assert _safe_float_lo(BIG - 1) == math.nextafter(float(BIG), -INF)

    def test_beyond_float_range_saturates(self):
        assert _safe_float_lo(10 ** 400) == FLOAT_MAX
        assert _safe_float_hi(10 ** 400) == INF
        assert _safe_float_lo(-(10 ** 400)) == -INF
        assert _safe_float_hi(-(10 ** 400)) == -FLOAT_MAX


class TestSyncRealFromFd:
    def test_bignum_hi_bound_is_not_cut_by_one_ulp(self):
        trail = Trail()
        x = Var()
        assert in_real(x, -INF, INF, trail)
        assert in_domain(x, 0, BIG + 1, trail)
        assert real(x).hi >= BIG + 1
        assert real(x).lo == 0.0

    def test_bignum_lo_bound_is_not_cut_by_one_ulp(self):
        trail = Trail()
        x = Var()
        assert in_real(x, -INF, INF, trail)
        assert in_domain(x, BIG - 1, 2 * BIG, trail)
        assert real(x).lo <= BIG - 1
        assert real(x).hi == float(2 * BIG)

    def test_the_cut_value_stays_admissible(self):
        """``X in 0..2**60+1`` then ``X = 2**60+1``: the real interval
        synced from the FD bound must still admit the integer."""
        trail = Trail()
        x = Var()
        assert in_real(x, -INF, INF, trail)
        assert in_domain(x, 0, BIG + 1, trail)
        assert unify(x, BIG + 1, trail)
        assert deref(x) == BIG + 1

    def test_small_bounds_sync_exactly(self):
        trail = Trail()
        x = Var()
        assert in_real(x, -INF, INF, trail)
        assert in_domain(x, -3, 10, trail)
        assert (real(x).lo, real(x).hi) == (-3.0, 10.0)


class TestClprReadsFdBounds:
    def test_promote_rounds_outward(self):
        trail = Trail()
        x = Var()
        assert in_domain(x, BIG - 1, BIG + 1, trail)
        _promote_fd_to_real(x, trail)
        assert real(x).lo <= BIG - 1
        assert real(x).hi >= BIG + 1

    def test_promote_beyond_float_range_does_not_overflow(self):
        trail = Trail()
        x = Var()
        assert in_domain(x, -(10 ** 400), 10 ** 400, trail)
        _promote_fd_to_real(x, trail)
        assert (real(x).lo, real(x).hi) == (-INF, INF)

    def test_var_interval_rounds_outward(self):
        trail = Trail()
        x = Var()
        assert in_domain(x, BIG - 1, BIG + 1, trail)
        lo, hi = _get_var_interval(x)
        assert lo <= BIG - 1
        assert hi >= BIG + 1


# ── real -> FD: exact over the whole double range, C and Python alike ───────


def fresh_real(lo, hi, trail):
    x = Var()
    assert in_real(x, lo, hi, trail)
    return x


class TestFdFromRealBound:
    @pytest.mark.parametrize("hook", HOOKS)
    def test_finite_lo_beyond_int64(self, hook):
        trail = Trail()
        y = Var()
        state = _ensure_fd(y, trail)
        x = fresh_real(1e300, INF, trail)
        assert hook(state, x, trail) is True
        assert fd_domain(x) == ((math.ceil(1e300), INF),)

    @pytest.mark.parametrize("hook", HOOKS)
    def test_hi_at_float_max(self, hook):
        trail = Trail()
        y = Var()
        state = _ensure_fd(y, trail)
        x = fresh_real(-INF, FLOAT_MAX, trail)
        assert hook(state, x, trail) is True
        assert fd_domain(x) == ((-INF, int(FLOAT_MAX)),)

    @pytest.mark.parametrize("hook", HOOKS)
    def test_finite_hi_beyond_int64_negative(self, hook):
        trail = Trail()
        y = Var()
        state = _ensure_fd(y, trail)
        x = fresh_real(-INF, -1e300, trail)
        assert hook(state, x, trail) is True
        assert fd_domain(x) == ((-INF, math.floor(-1e300)),)

    @pytest.mark.parametrize("hook", HOOKS)
    def test_lo_beyond_int64_wipes_a_small_domain(self, hook):
        trail = Trail()
        y = Var()
        assert in_domain(y, 0, 10 ** 6, trail)
        x = fresh_real(1e300, INF, trail)
        assert hook(get_attr(y, FD_KEY), x, trail) is False

    @pytest.mark.parametrize("hook", HOOKS)
    def test_hi_at_float_max_keeps_a_small_domain(self, hook):
        trail = Trail()
        y = Var()
        assert in_domain(y, 0, 10 ** 6, trail)
        x = fresh_real(-INF, FLOAT_MAX, trail)
        assert hook(get_attr(y, FD_KEY), x, trail) is True
        assert fd_domain(x) == ((0, 10 ** 6),)

    @pytest.mark.parametrize("hook", HOOKS)
    def test_bignum_fd_domain_meets_a_real_bound(self, hook):
        trail = Trail()
        y = Var()
        assert in_domain(y, 0, 10 ** 400, trail)
        x = fresh_real(-INF, 1e300, trail)
        assert hook(get_attr(y, FD_KEY), x, trail) is True
        assert fd_domain(x) == ((0, math.floor(1e300)),)

    @pytest.mark.parametrize("hook", HOOKS)
    def test_in_range_bounds_round_inward_to_integers(self, hook):
        trail = Trail()
        y = Var()
        state = _ensure_fd(y, trail)
        x = fresh_real(-2.5, 7.5, trail)
        assert hook(state, x, trail) is True
        assert fd_domain(x) == ((-2, 7),)

    @pytest.mark.parametrize("hook", HOOKS)
    def test_bounds_at_the_edge_of_int64(self, hook):
        trail = Trail()
        y = Var()
        state = _ensure_fd(y, trail)
        edge = 2.0 ** 63          # exact as a double; not an int64 value
        x = fresh_real(-edge, edge, trail)
        assert hook(state, x, trail) is True
        assert fd_domain(x) == ((-(2 ** 63), 2 ** 63),)

    @pytest.mark.parametrize("hook", HOOKS)
    @pytest.mark.parametrize("lo, hi", [
        (INF, 5.0), (INF, INF), (-INF, -INF), (3.0, -INF),
        (math.nan, 5.0), (0.0, math.nan), (math.nan, math.nan),
    ], ids=repr)
    def test_an_empty_interval_wipes_the_domain(self, hook, lo, hi):
        """An interval that admits nothing (a lower bound of +inf, an
        upper bound of -inf, a NaN bound) is the empty FD domain in both
        twins: the hook fails, raising nothing and keeping no value."""
        trail = Trail()
        y = Var()
        assert in_domain(y, 1, 10, trail)
        x = Var()
        put_attr(x, REAL_KEY, RealVar(lo, hi), trail)
        assert hook(get_attr(y, FD_KEY), x, trail) is False

    @pytest.mark.parametrize("lo, hi", [
        (INF, 5.0), (3.0, -INF), (2.0, 1.0), (math.nan, 5.0), (0.0, math.nan),
    ], ids=repr)
    def test_in_real_fails_on_an_empty_interval(self, lo, hi):
        trail = Trail()
        x = Var()
        assert in_real(x, lo, hi, trail) is False
        assert real(x) is None

    def test_in_real_accepts_a_point_and_an_unbounded_interval(self):
        trail = Trail()
        x, z = Var(), Var()
        assert in_real(x, 2.0, 2.0, trail)
        assert deref(x) == 2.0
        assert in_real(z, -INF, INF, trail)
        assert (real(z).lo, real(z).hi) == (-INF, INF)

    def test_post_domain_on_a_real_var_beyond_int64(self):
        trail = Trail()
        x = fresh_real(1e300, INF, trail)
        assert in_domain(x, 0, 10 ** 6, trail) is False
        trail2 = Trail()
        z = fresh_real(1e300, INF, trail2)
        assert in_domain(z, 0, 10 ** 400, trail2) is True
        assert domain_min(fd_domain(z)) == math.ceil(1e300)
        assert domain_max(fd_domain(z)) == 10 ** 400

    def test_unify_fd_var_with_real_var_beyond_int64(self):
        trail = Trail()
        y = Var()
        assert in_domain(y, 0, 10 ** 6, trail)
        x = fresh_real(1e300, INF, trail)
        assert unify(y, x, trail) is False
