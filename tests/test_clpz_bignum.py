"""Tests for CLP(Z) bignum domain bounds.

Verifies that the C-accelerator wrappers in ``_clpfd_core`` correctly fall
back to the Python reference implementations when domain bounds exceed
int64 range (e.g. Fibonacci above N=92), and that the constraint
propagators in ``_clpfd_propagate`` likewise dispatch to bignum-safe
helpers when operand domains contain such bounds.

See ``implementation_plans/clpfd/todo/clpz_bignum.md``.

Covers Slice 1+2 (domain ops in ``_clpfd_core.c``) and Slice 3
(``eq``/``lt``/``le`` propagators in ``_clpfd_propagate.c``).
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import (
    Var, Trail, deref, is_var, get_attr, put_attr, unify,
)
from clausal.logic.clpfd import (
    FD_KEY,
    _NEG_INF,
    _POS_INF,
    _ensure_fd,
    domain_from_range,
    domain_contains,
    domain_min,
    domain_max,
    domain_size,
    domain_singleton,
    domain_intersection,
    domain_remove,
    domain_remove_above,
    domain_remove_below,
    domain_values,
    fd_eq,
    fd_ne,
    fd_lt,
    fd_le,
    fd_gt,
    fd_ge,
    in_domain,
    SumConstraint,
    ScalarProductConstraint,
    _post_constraint,
    _py_domain_from_range,
    _py_domain_intersection,
    _py_domain_remove,
)


def fresh_trail() -> Trail:
    return Trail()


# Powers of two large enough to be unambiguously bignum (> 2**63).
BIG = 2**70
HUGE = 2**200


class TestBignumDomainConstruction:
    def test_domain_from_range_bignum_lo(self):
        d = domain_from_range(BIG, BIG + 100)
        assert d == ((BIG, BIG + 100),)

    def test_domain_from_range_bignum_hi(self):
        d = domain_from_range(0, HUGE)
        assert d == ((0, HUGE),)

    def test_domain_from_range_negative_bignum(self):
        d = domain_from_range(-BIG, BIG)
        assert d == ((-BIG, BIG),)

    def test_domain_from_range_empty_bignum(self):
        # lo > hi gives an empty domain
        d = domain_from_range(BIG + 1, BIG)
        assert d == ()

    def test_domain_from_range_bignum_matches_python(self):
        c_d = domain_from_range(BIG, BIG + 5)
        py_d = _py_domain_from_range(BIG, BIG + 5)
        assert c_d == py_d


class TestBignumDomainReads:
    def test_domain_min_bignum(self):
        d = ((BIG, BIG + 100),)
        assert domain_min(d) == BIG

    def test_domain_max_bignum(self):
        d = ((BIG, BIG + 100),)
        assert domain_max(d) == BIG + 100

    def test_domain_size_bignum_finite(self):
        d = ((BIG, BIG + 100),)
        assert domain_size(d) == 101

    def test_domain_size_bignum_huge(self):
        # Range size itself is a bignum.
        d = ((0, HUGE),)
        assert domain_size(d) == HUGE + 1

    def test_domain_size_bignum_with_inf(self):
        d = ((BIG, _POS_INF),)
        assert domain_size(d) == _POS_INF

    def test_domain_singleton_bignum(self):
        d = ((BIG, BIG),)
        assert domain_singleton(d) == BIG

    def test_domain_singleton_non_singleton_bignum(self):
        d = ((BIG, BIG + 1),)
        assert domain_singleton(d) is None


class TestBignumDomainContains:
    def test_contains_bignum_value(self):
        d = ((BIG, BIG + 100),)
        assert domain_contains(d, BIG) is True
        assert domain_contains(d, BIG + 50) is True
        assert domain_contains(d, BIG + 100) is True

    def test_not_contains_outside_bignum(self):
        d = ((BIG, BIG + 100),)
        assert domain_contains(d, BIG - 1) is False
        assert domain_contains(d, BIG + 101) is False

    def test_contains_int64_value_in_bignum_domain(self):
        # Domain is bignum, value is int64-fitting — must still fall back.
        d = ((-HUGE, HUGE),)
        assert domain_contains(d, 0) is True
        assert domain_contains(d, 5) is True

    def test_contains_bignum_value_in_int64_domain(self):
        # Domain fits in int64; value is bignum — must fall back to Python.
        d = ((0, 100),)
        assert domain_contains(d, BIG) is False


class TestBignumDomainIntersection:
    def test_bignum_with_bignum(self):
        d1 = ((BIG, BIG + 100),)
        d2 = ((BIG + 50, BIG + 200),)
        assert domain_intersection(d1, d2) == ((BIG + 50, BIG + 100),)

    def test_bignum_with_int64(self):
        d1 = ((BIG, BIG + 100),)
        d2 = ((0, BIG + 50),)
        assert domain_intersection(d1, d2) == ((BIG, BIG + 50),)

    def test_int64_with_int64_unaffected(self):
        # Regression: ordinary int64 path still works.
        d1 = ((1, 10),)
        d2 = ((5, 15),)
        assert domain_intersection(d1, d2) == ((5, 10),)

    def test_disjoint_bignum(self):
        d1 = ((BIG, BIG + 50),)
        d2 = ((BIG + 100, BIG + 200),)
        assert domain_intersection(d1, d2) == ()

    def test_intersection_matches_python_reference(self):
        d1 = ((BIG, BIG + 100),)
        d2 = ((BIG + 50, BIG + 200),)
        assert domain_intersection(d1, d2) == _py_domain_intersection(d1, d2)


class TestBignumDomainRemove:
    def test_remove_bignum_value(self):
        d = ((BIG, BIG + 5),)
        result = domain_remove(d, BIG + 2)
        assert result == ((BIG, BIG + 1), (BIG + 3, BIG + 5))

    def test_remove_endpoint_bignum(self):
        d = ((BIG, BIG + 5),)
        assert domain_remove(d, BIG) == ((BIG + 1, BIG + 5),)
        assert domain_remove(d, BIG + 5) == ((BIG, BIG + 4),)

    def test_remove_int64_value_from_bignum_domain(self):
        # Falls back because of bignum bound.
        d = ((-HUGE, HUGE),)
        result = domain_remove(d, 0)
        assert result == ((-HUGE, -1), (1, HUGE))

    def test_remove_matches_python_reference(self):
        d = ((BIG, BIG + 10),)
        assert domain_remove(d, BIG + 5) == _py_domain_remove(d, BIG + 5)

    def test_remove_int64_unaffected(self):
        d = ((1, 10),)
        assert domain_remove(d, 5) == ((1, 4), (6, 10))


class TestBignumDomainRemoveAboveBelow:
    def test_remove_above_bignum_limit(self):
        d = ((0, HUGE),)
        assert domain_remove_above(d, BIG) == ((0, BIG),)

    def test_remove_above_bignum_domain(self):
        d = ((BIG, BIG + 100),)
        assert domain_remove_above(d, BIG + 50) == ((BIG, BIG + 50),)

    def test_remove_below_bignum_limit(self):
        d = ((-HUGE, HUGE),)
        assert domain_remove_below(d, BIG) == ((BIG, HUGE),)

    def test_remove_below_bignum_domain(self):
        d = ((BIG, BIG + 100),)
        assert domain_remove_below(d, BIG + 50) == ((BIG + 50, BIG + 100),)

    def test_remove_above_inf_unchanged(self):
        # Regression: existing inf-handling preserved.
        d = ((BIG, BIG + 10),)
        assert domain_remove_above(d, _POS_INF) == d

    def test_remove_below_neg_inf_unchanged(self):
        d = ((BIG, BIG + 10),)
        assert domain_remove_below(d, _NEG_INF) == d


class TestBignumDomainValues:
    def test_values_bignum_finite(self):
        d = ((BIG, BIG + 3),)
        assert domain_values(d) == [BIG, BIG + 1, BIG + 2, BIG + 3]

    def test_values_bignum_unbounded_raises(self):
        d = ((BIG, _POS_INF),)
        with pytest.raises(ValueError, match="[Uu]nbounded"):
            list(domain_values(d))


class TestBignumPropagation:
    """Slice 3 — propagator-level bignum support.

    Posting an `==` / `<` / `<=` constraint that produces a bignum
    domain must narrow / unify correctly instead of raising
    ``OverflowError``.
    """

    def test_eq_var_bignum_int_binds(self):
        """X == 2**70 binds X to that bignum value."""
        trail = fresh_trail()
        x = Var()
        assert fd_eq(x, BIG, trail) is True
        assert deref(x) == BIG

    def test_eq_chain_bignum_propagates(self):
        """X == Y, Y == 2**100 → X = 2**100."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert fd_eq(x, y, trail)
        assert fd_eq(y, 2**100, trail)
        assert deref(x) == 2**100

    def test_eq_compound_bignum_via_linearise(self):
        """X == V + V with V = 2**62 + 1 binds X to 2**63 + 2 (bignum)."""
        from clausal.terms import Add
        trail = fresh_trail()
        v, x = Var(), Var()
        big = (1 << 62) + 1
        assert unify(v, big, trail)
        # Post X == v + v (linearisation produces constant past int64)
        assert fd_eq(x, Add(left=v, right=v), trail) is True
        assert deref(x) == 2 * big

    def test_lt_narrows_to_bignum(self):
        """X < 2**100 narrows X's upper bound to 2**100 - 1."""
        trail = fresh_trail()
        x = Var()
        assert fd_lt(x, 2**100, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_max(state.domain) == 2**100 - 1

    def test_gt_narrows_lower_to_bignum(self):
        """X > 2**100 narrows X's lower bound to 2**100 + 1."""
        trail = fresh_trail()
        x = Var()
        assert fd_gt(x, 2**100, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_min(state.domain) == 2**100 + 1

    def test_le_narrows_to_bignum(self):
        """X <= 2**100 narrows X's upper bound to 2**100."""
        trail = fresh_trail()
        x = Var()
        assert fd_le(x, 2**100, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_max(state.domain) == 2**100

    def test_ge_narrows_to_bignum(self):
        """X >= 2**100 narrows X's lower bound to 2**100."""
        trail = fresh_trail()
        x = Var()
        assert fd_ge(x, 2**100, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_min(state.domain) == 2**100

    def test_eq_inconsistent_bignum_fails(self):
        """X == 2**70, X == 2**100 → second post fails (wipeout)."""
        trail = fresh_trail()
        x = Var()
        assert fd_eq(x, BIG, trail)
        # x is bound to BIG; post a contradictory bignum equality.
        assert fd_eq(x, 2**100, trail) is False

    def test_ne_excludes_bignum_value(self):
        """X != 2**70 splits the default infinite domain at the bignum value."""
        trail = fresh_trail()
        x = Var()
        assert fd_ne(x, BIG, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert not domain_contains(state.domain, BIG)
        assert domain_contains(state.domain, BIG - 1)
        assert domain_contains(state.domain, BIG + 1)

    def test_ne_then_eq_consistent_bignum(self):
        """X != 2**70, X == 2**70 - 1 → x = 2**70 - 1."""
        trail = fresh_trail()
        x = Var()
        assert fd_ne(x, BIG, trail)
        assert fd_eq(x, BIG - 1, trail)
        assert deref(x) == BIG - 1

    def test_ne_then_eq_inconsistent_bignum(self):
        """X != 2**70, X == 2**70 → wipeout."""
        trail = fresh_trail()
        x = Var()
        assert fd_ne(x, BIG, trail)
        assert fd_eq(x, BIG, trail) is False


class TestSumScalarBignum:
    """Slice 4 — bignum fallback in sum_propagate / scalar_propagate.

    The C versions accumulate bounds in ``double``, which loses integer
    precision past 2**53.  Both bignum bounds and large-but-int64 sums
    must trigger the Python fallback to preserve exact integer results.
    """

    def _bound_var(self, lo, hi, trail):
        v = Var()
        assert in_domain(v, lo, hi, trail)
        return v

    def test_sum_bignum_operand_domains(self):
        """SumConstraint with operand domains > int64."""
        trail = fresh_trail()
        x = self._bound_var(BIG, BIG, trail)
        y = self._bound_var(BIG, BIG, trail)
        z = self._bound_var(BIG, BIG, trail)
        total = Var()
        _ensure_fd(total, trail)
        assert _post_constraint(SumConstraint((x, y, z), total), trail)
        assert deref(total) == 3 * BIG

    def test_sum_int64_but_double_imprecise(self):
        """Operands in int64 but running sum past 2^53.

        Without the bignum fallback, the C path would accumulate the
        sum in ``double`` and lose precision (3 * 2**60 has the low 6
        bits zeroed in float64), giving a wrong answer.
        """
        trail = fresh_trail()
        x = self._bound_var(2**60, 2**60, trail)
        y = self._bound_var(2**60, 2**60, trail)
        z = self._bound_var(2**60, 2**60, trail)
        total = Var()
        _ensure_fd(total, trail)
        assert _post_constraint(SumConstraint((x, y, z), total), trail)
        assert deref(total) == 3 * 2**60

    def test_sum_total_bignum(self):
        """Total domain is bignum, operands narrow to match."""
        trail = fresh_trail()
        x = Var()
        y = Var()
        # Constrain x and y individually, total is bignum
        assert in_domain(x, 0, 2**100, trail)
        assert in_domain(y, 0, 2**100, trail)
        total = self._bound_var(BIG, BIG, trail)
        assert _post_constraint(SumConstraint((x, y), total), trail)
        # Both operands narrowed to fit total
        sx = get_attr(x, FD_KEY)
        sy = get_attr(y, FD_KEY)
        assert domain_max(sx.domain) == BIG
        assert domain_max(sy.domain) == BIG

    def test_scalar_bignum_coefficient(self):
        """ScalarProductConstraint with a coefficient > int64."""
        trail = fresh_trail()
        x = self._bound_var(1, 1, trail)
        total = Var()
        _ensure_fd(total, trail)
        assert _post_constraint(
            ScalarProductConstraint((BIG,), (x,), total), trail)
        assert deref(total) == BIG

    def test_scalar_int64_but_double_imprecise(self):
        """ScalarProduct with running sum past 2^53."""
        trail = fresh_trail()
        x = self._bound_var(2**60, 2**60, trail)
        total = Var()
        _ensure_fd(total, trail)
        assert _post_constraint(
            ScalarProductConstraint((3,), (x,), total), trail)
        # 3 * 2**60 = 3458764513820540928, exact in int but not in double
        # past 2**53.
        assert deref(total) == 3 * 2**60

    def test_scalar_negative_bignum_coeff(self):
        """ScalarProductConstraint with a negative bignum coefficient."""
        trail = fresh_trail()
        x = self._bound_var(1, 1, trail)
        total = Var()
        _ensure_fd(total, trail)
        assert _post_constraint(
            ScalarProductConstraint((-BIG,), (x,), total), trail)
        assert deref(total) == -BIG

    def test_sum_int64_unaffected(self):
        """Regression: ordinary int64 sum still works on the fast path."""
        trail = fresh_trail()
        x = self._bound_var(1, 1, trail)
        y = self._bound_var(2, 2, trail)
        z = self._bound_var(3, 3, trail)
        total = Var()
        _ensure_fd(total, trail)
        assert _post_constraint(SumConstraint((x, y, z), total), trail)
        assert deref(total) == 6


class TestBignumIntegration:
    """End-to-end checks: the wrap_tabled_fib fixture under CLP(Z) must
    return correct bignum results for N well past Fib(92)."""

    def _run_wrap_fib(self, n):
        from clausal.testing import load_clausal_module
        from clausal.logic.solve import call

        mod = load_clausal_module("tests/fixtures/wrap_tabled_fib.clausal")
        lm = mod.__dict__["$module"]
        trail = Trail()
        r = Var()
        for _ in call("Wrap", n, r, module=lm, trail=trail):
            return deref(r)
        return None

    def test_wrap_fib_92_int64_boundary(self):
        """Fib(92) is the largest value still fitting in int64."""
        assert self._run_wrap_fib(92) == 7540113804746346429

    def test_wrap_fib_93_first_bignum(self):
        """Fib(93) is the first value above int64 — used to overflow."""
        assert self._run_wrap_fib(93) == 12200160415121876738

    def test_wrap_fib_100(self):
        """Fib(100) — 21 digits, well past int64."""
        assert self._run_wrap_fib(100) == 354224848179261915075

    def test_wrap_fib_200(self):
        """Fib(200) — 42 digits."""
        assert self._run_wrap_fib(200) == \
            280571172992510140037611932413038677189525


class TestBignumNoRegression:
    """Ensure Slice 1 didn't slow down or break the int64 fast path."""

    def test_int64_path_still_works(self):
        d = domain_from_range(1, 100)
        assert d == ((1, 100),)
        assert domain_min(d) == 1
        assert domain_max(d) == 100
        assert domain_size(d) == 100
        assert domain_contains(d, 50) is True
        assert domain_contains(d, 0) is False

    def test_inf_bound_still_works(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_size(d) == _POS_INF
        assert domain_min(d) == _NEG_INF
        assert domain_max(d) == _POS_INF


class TestBignumBeyondFloatRange:
    """Domain bounds whose *magnitude* exceeds a Python float's range
    (~1.7976931348623157e+308, i.e. bit_length > ~1024).

    ``_narrow`` (both the Python reference implementation and its C
    accelerator twin in ``_clpfd_propagate.c``) synchronises the CLP(R)
    real-interval attribute (when present) by converting the new FD
    bounds to ``float``.  ``2**70``- or ``2**100``-scale bignums (as used
    above in ``TestBignumPropagation``) still fit comfortably in a float's
    exponent range, so they never exercise this.  Values genuinely beyond
    float range (e.g. tabled Fibonacci growth past fib(~1475)) must still
    propagate: the float conversion is a CLP(R)-sync convenience, not a
    correctness requirement of CLP(Z) itself.
    """

    # Comfortably past float's ~1.8e+308 ceiling (2**1024-ish).
    BEYOND = 10 ** 400

    def test_lt_narrows_beyond_float_range(self):
        trail = fresh_trail()
        x = Var()
        assert fd_lt(x, self.BEYOND, trail) is True
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_max(state.domain) == self.BEYOND - 1

    def test_le_narrows_beyond_float_range(self):
        trail = fresh_trail()
        x = Var()
        assert fd_le(x, self.BEYOND, trail) is True
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_max(state.domain) == self.BEYOND

    def test_ge_narrows_lower_beyond_float_range(self):
        trail = fresh_trail()
        x = Var()
        assert fd_ge(x, self.BEYOND, trail) is True
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_min(state.domain) == self.BEYOND

    def test_eq_binds_beyond_float_range(self):
        trail = fresh_trail()
        x = Var()
        assert fd_eq(x, self.BEYOND, trail) is True
        assert deref(x) == self.BEYOND

    def test_negative_beyond_float_range_narrows(self):
        """Symmetric negative-magnitude bignum (sign must be preserved
        when the C/py float conversion saturates instead of erroring)."""
        trail = fresh_trail()
        x = Var()
        assert fd_gt(x, -self.BEYOND, trail) is True
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_min(state.domain) == -self.BEYOND + 1

    def test_narrow_syncs_clpr_beyond_float_range(self):
        """``_narrow`` itself (not the higher-level ``fd_lt`` et al, which
        reroute entirely to CLP(R) via ``_any_real`` once a var carries a
        REAL_KEY attribute) must not crash, and must not corrupt the real
        interval, when narrowing an FD domain whose bound is past float
        range: the FD bound saturates to +-inf for the purposes of the
        real-interval sync (CLP(R) already only has float precision, so
        this is the correct representation).
        """
        import math
        from collections import deque
        from clausal.logic import clpfd
        from clausal.logic.clpr import REAL_KEY, RealVar

        trail = fresh_trail()
        queue = deque()
        x = Var()
        put_attr(x, REAL_KEY, RealVar(-math.inf, math.inf), trail)

        dom = domain_from_range(0, self.BEYOND)
        assert clpfd._narrow(x, dom, trail, queue) is True

        fd_state = get_attr(x, FD_KEY)
        assert domain_max(fd_state.domain) == self.BEYOND

        real_state = get_attr(x, REAL_KEY)
        # FD bound saturates to +inf on the real side; real interval's
        # existing +inf upper bound is unaffected (min(inf, inf) == inf).
        assert real_state.hi == math.inf
        assert real_state.lo == 0.0
