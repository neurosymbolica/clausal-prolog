"""Tests for clausal.modules.py.scipy_stats — scipy.stats predicates.

Tests are organised per function family and cover:
- correct result for typical inputs
- multi-arity variants (optional args)
- unification succeeds when RESULT is unbound
- unification fails when RESULT is bound to a wrong value
- Tier 2 dict results accessed via ResultGet
- Tier 3 frozen distribution handle lifecycle
"""

import pytest

pytest.importorskip("scipy", reason="scipy not installed")

import numpy as np
import scipy.stats as scipy_stats

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_stats import (
    StatsDescribe, StatsMean, StatsGeometricMean, StatsHarmonicMean,
    StatsMode, StatsSkew, StatsKurtosis, StatsInterquartileRange,
    StatsZScore, StatsMedianAbsoluteDeviation,
    StatsPearsonCorrelation, StatsSpearmanCorrelation, StatsKendallTau,
    StatsLinearRegression, StatsTheilSlopes,
    StatsTTest1Sample, StatsTTestIndependent, StatsTTestRelated,
    StatsChiSquare, StatsChiSquareContingency, StatsFisherExact,
    StatsMannWhitneyU, StatsWilcoxon, StatsKruskal, StatsKs2samp,
    StatsNormalityTest, StatsShapiro,
    StatsDist,
    StatsNormalPdf, StatsNormalCdf, StatsNormalPpf, StatsNormalRvs,
    StatsFreezeDist, StatsFrozenPdf, StatsFrozenCdf,
    StatsFrozenRvs, StatsFrozenStats, StatsFrozenFree,
    ResultGet,
)


# ── Test drivers ──────────────────────────────────────────────────────────

def _drive(pred, *args):
    """Call predicate with a fresh Var as RESULT; return first solution value."""
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, None, None, *args, result, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


def _drive_result_get(result_dict, field):
    """Use ResultGet to extract a field from a dict result."""
    value = Var()
    dispatch = ResultGet._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, None, None, result_dict, field, value, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(value)
    return None


def _fails_with_wrong_result(pred, *args):
    """Return True if predicate yields no solution when RESULT is bound to a wrong value."""
    trail = Trail()
    result_bound = object()  # will not unify with any result
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, result_bound, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


# Sample data
_DATA1 = [2.0, 3.0, 5.0, 7.0, 11.0]
_DATA2 = [1.0, 2.0, 3.0, 4.0, 5.0]


# ── TestStatsDescribe ─────────────────────────────────────────────────────

class TestStatsDescribe:
    def test_returns_dict(self):
        # nv
        r = _drive(StatsDescribe, _DATA1)
        assert isinstance(r, dict)

    def test_nobs(self):
        # nv
        r = _drive(StatsDescribe, _DATA1)
        assert r['nobs'] == 5

    def test_mean_approx(self):
        # nv
        r = _drive(StatsDescribe, _DATA1)
        assert abs(r['mean'] - np.mean(_DATA1)) < 1e-9

    def test_minmax(self):
        # nv
        r = _drive(StatsDescribe, _DATA1)
        assert r['minmax'][0] == 2.0
        assert r['minmax'][1] == 11.0

    def test_has_all_keys(self):
        # nv
        r = _drive(StatsDescribe, _DATA1)
        for key in ('nobs', 'minmax', 'mean', 'variance', 'skewness', 'kurtosis'):
            assert key in r


# ── TestStatsMean ─────────────────────────────────────────────────────────

class TestStatsMean:
    def test_simple(self):
        # nv
        r = _drive(StatsMean, [1.0, 2.0, 3.0])
        assert abs(r - 2.0) < 1e-9

    def test_float_result(self):
        # nv
        r = _drive(StatsMean, _DATA1)
        assert isinstance(r, float)

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(StatsMean, [1.0, 2.0, 3.0])


# ── TestStatsGeometricMean ────────────────────────────────────────────────────────

class TestStatsGeometricMean:
    def test_simple(self):
        # gmean([1, 4]) = 2.0
        # nv
        r = _drive(StatsGeometricMean, [1.0, 4.0])
        assert abs(r - 2.0) < 1e-9

    def test_float_result(self):
        # nv
        r = _drive(StatsGeometricMean, [2.0, 8.0])
        assert isinstance(r, float)


# ── TestStatsHarmonicMean ────────────────────────────────────────────────────────

class TestStatsHarmonicMean:
    def test_simple(self):
        # hmean([1, 1]) = 1.0
        # nv
        r = _drive(StatsHarmonicMean, [1.0, 1.0])
        assert abs(r - 1.0) < 1e-9

    def test_harmonic_two(self):
        # hmean([2, 6]) = 3.0
        # nv
        r = _drive(StatsHarmonicMean, [2.0, 6.0])
        assert abs(r - 3.0) < 1e-9


# ── TestStatsMode ─────────────────────────────────────────────────────────

class TestStatsMode:
    def test_returns_dict(self):
        # nv
        r = _drive(StatsMode, [1, 2, 2, 3])
        assert isinstance(r, dict)
        assert 'mode' in r
        assert 'count' in r

    def test_mode_value(self):
        # nv
        r = _drive(StatsMode, [1, 2, 2, 3])
        assert abs(r['mode'] - 2.0) < 1e-9

    def test_count_value(self):
        # nv
        r = _drive(StatsMode, [1, 2, 2, 3])
        assert r['count'] == 2


# ── TestStatsSkew ─────────────────────────────────────────────────────────

class TestStatsSkew:
    def test_symmetric_near_zero(self):
        # nv
        r = _drive(StatsSkew, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert abs(r) < 1e-9

    def test_float_result(self):
        # nv
        r = _drive(StatsSkew, _DATA1)
        assert isinstance(r, float)


# ── TestStatsKurtosis ─────────────────────────────────────────────────────

class TestStatsKurtosis:
    def test_returns_float(self):
        # nv
        r = _drive(StatsKurtosis, _DATA1)
        assert isinstance(r, float)


# ── TestStatsInterquartileRange ──────────────────────────────────────────────────────────

class TestStatsInterquartileRange:
    def test_simple(self):
        # IQR of [1,2,3,4,5]: Q3=4, Q1=2 → 2
        # nv
        r = _drive(StatsInterquartileRange, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert abs(r - scipy_stats.iqr([1.0, 2.0, 3.0, 4.0, 5.0])) < 1e-9

    def test_float_result(self):
        # nv
        r = _drive(StatsInterquartileRange, _DATA1)
        assert isinstance(r, float)


# ── TestStatsZScore ───────────────────────────────────────────────────────

class TestStatsZScore:
    def test_returns_list(self):
        # nv
        r = _drive(StatsZScore, [1.0, 2.0, 3.0])
        assert isinstance(r, list)
        assert len(r) == 3

    def test_mean_zero(self):
        # nv
        r = _drive(StatsZScore, [1.0, 2.0, 3.0])
        assert abs(sum(r) / len(r)) < 1e-9


# ── TestStatsMedianAbsoluteDeviation ───────────────────────────────────────────

class TestStatsMedianAbsoluteDeviation:
    def test_returns_float(self):
        # nv
        r = _drive(StatsMedianAbsoluteDeviation, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert isinstance(r, float)

    def test_value(self):
        # nv
        r = _drive(StatsMedianAbsoluteDeviation, [1.0, 2.0, 3.0, 4.0, 5.0])
        expected = float(scipy_stats.median_abs_deviation([1.0, 2.0, 3.0, 4.0, 5.0]))
        assert abs(r - expected) < 1e-9


# ── TestStatsPearsonCorrelation ─────────────────────────────────────────────────────

class TestStatsPearsonCorrelation:
    def test_perfect_correlation(self):
        # nv
        x = [1.0, 2.0, 3.0]
        r = _drive(StatsPearsonCorrelation, x, x)
        assert r is not None
        assert abs(r['statistic'] - 1.0) < 1e-9

    def test_returns_dict(self):
        # nv
        r = _drive(StatsPearsonCorrelation, _DATA1, _DATA2)
        assert isinstance(r, dict)
        assert 'statistic' in r
        assert 'pvalue' in r

    def test_result_get_statistic(self):
        # nv
        r = _drive(StatsPearsonCorrelation, _DATA1, _DATA2)
        stat = _drive_result_get(r, 'statistic')
        assert stat is not None

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(StatsPearsonCorrelation, _DATA1, _DATA2)


# ── TestStatsSpearmanCorrelation ────────────────────────────────────────────────────

class TestStatsSpearmanCorrelation:
    def test_one_array(self):
        # nv
        r = _drive(StatsSpearmanCorrelation, np.array([[1, 2], [2, 3], [3, 4]]))
        assert r is not None
        assert 'statistic' in r

    def test_two_arrays(self):
        # nv
        r = _drive(StatsSpearmanCorrelation, _DATA1, _DATA2)
        assert r is not None
        assert 'statistic' in r

    def test_perfect_rank_correlation(self):
        # nv
        x = [1.0, 2.0, 3.0]
        r = _drive(StatsSpearmanCorrelation, x, x)
        assert abs(r['statistic'] - 1.0) < 1e-9


# ── TestStatsKendallTau ───────────────────────────────────────────────────

class TestStatsKendallTau:
    def test_returns_dict(self):
        # nv
        r = _drive(StatsKendallTau, _DATA1, _DATA2)
        assert isinstance(r, dict)
        assert 'statistic' in r
        assert 'pvalue' in r

    def test_perfect_agreement(self):
        # nv
        x = [1.0, 2.0, 3.0]
        r = _drive(StatsKendallTau, x, x)
        assert abs(r['statistic'] - 1.0) < 1e-9


# ── TestStatsLinearRegression ───────────────────────────────────────────────────

class TestStatsLinearRegression:
    def test_returns_dict(self):
        # nv
        r = _drive(StatsLinearRegression, [1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
        assert isinstance(r, dict)

    def test_slope_intercept(self):
        # nv
        r = _drive(StatsLinearRegression, [1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
        assert abs(r['slope'] - 2.0) < 1e-9
        assert abs(r['intercept']) < 1e-9

    def test_has_all_fields(self):
        # nv
        r = _drive(StatsLinearRegression, _DATA1, _DATA2)
        for key in ('slope', 'intercept', 'rvalue', 'pvalue', 'stderr', 'intercept_stderr'):
            assert key in r

    def test_result_get_slope(self):
        # nv
        r = _drive(StatsLinearRegression, [1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
        slope = _drive_result_get(r, 'slope')
        assert abs(float(slope) - 2.0) < 1e-9


# ── TestStatsTheilSlopes ──────────────────────────────────────────────────

class TestStatsTheilSlopes:
    def test_two_arg(self):
        # nv
        r = _drive(StatsTheilSlopes, [2.0, 4.0, 6.0])
        assert 'slope' in r

    def test_three_arg(self):
        # nv
        r = _drive(StatsTheilSlopes, [2.0, 4.0, 6.0], [1.0, 2.0, 3.0])
        assert 'slope' in r

    def test_has_all_fields(self):
        # nv
        r = _drive(StatsTheilSlopes, _DATA2)
        for key in ('slope', 'intercept', 'low_slope', 'high_slope'):
            assert key in r


# ── TestStatsTTest1Sample ───────────────────────────────────────────────────

class TestStatsTTest1Sample:
    def test_returns_dict(self):
        # nv
        r = _drive(StatsTTest1Sample, [1.0, 2.0, 3.0], 2.0)
        assert isinstance(r, dict)
        assert 'statistic' in r
        assert 'pvalue' in r

    def test_same_mean_low_t(self):
        # Data with mean 2.0, testing against popmean=2.0 → stat near 0
        # nv
        r = _drive(StatsTTest1Sample, [1.0, 2.0, 3.0], 2.0)
        assert abs(r['statistic']) < 1e-9

    def test_result_get_pvalue(self):
        # nv
        r = _drive(StatsTTest1Sample, [1.0, 2.0, 3.0], 2.0)
        pv = _drive_result_get(r, 'pvalue')
        assert pv is not None


# ── TestStatsTTestIndependent ─────────────────────────────────────────────────────

class TestStatsTTestIndependent:
    def test_two_arg(self):
        # nv
        r = _drive(StatsTTestIndependent, _DATA1, _DATA2)
        assert 'statistic' in r

    def test_three_arg_equal_var(self):
        # nv
        r = _drive(StatsTTestIndependent, _DATA1, _DATA2, True)
        assert 'statistic' in r

    def test_three_arg_unequal_var(self):
        # nv
        r = _drive(StatsTTestIndependent, _DATA1, _DATA2, False)
        assert 'statistic' in r


# ── TestStatsTTestRelated ─────────────────────────────────────────────────────

class TestStatsTTestRelated:
    def test_returns_dict(self):
        # nv
        r = _drive(StatsTTestRelated, _DATA1, [d + 0.1 for d in _DATA1])
        assert 'statistic' in r
        assert 'pvalue' in r


# ── TestStatsChiSquare ────────────────────────────────────────────────────

class TestStatsChiSquare:
    def test_one_arg(self):
        # nv
        r = _drive(StatsChiSquare, [10, 20, 30])
        assert 'statistic' in r
        assert 'pvalue' in r

    def test_two_arg_with_expected(self):
        # nv
        r = _drive(StatsChiSquare, [10, 20, 30], [15, 15, 30])
        assert 'statistic' in r

    def test_uniform_distribution(self):
        # [10, 10, 10] matches uniform expected → statistic ~ 0
        # nv
        r = _drive(StatsChiSquare, [10, 10, 10])
        assert abs(r['statistic']) < 1e-9


# ── TestStatsChiSquareContingency ──────────────────────────────────────────────

class TestStatsChiSquareContingency:
    def test_returns_dict(self):
        # nv
        table = [[10, 20], [30, 40]]
        r = _drive(StatsChiSquareContingency, table)
        assert isinstance(r, dict)

    def test_has_dof(self):
        # nv
        table = [[10, 20], [30, 40]]
        r = _drive(StatsChiSquareContingency, table)
        assert 'dof' in r
        assert r['dof'] == 1

    def test_has_expected_freq(self):
        # nv
        table = [[10, 20], [30, 40]]
        r = _drive(StatsChiSquareContingency, table)
        assert 'expected_freq' in r


# ── TestStatsFisherExact ──────────────────────────────────────────────────

class TestStatsFisherExact:
    def test_returns_dict(self):
        # nv
        table = [[8, 2], [1, 5]]
        r = _drive(StatsFisherExact, table)
        assert isinstance(r, dict)
        assert 'statistic' in r
        assert 'pvalue' in r

    def test_pvalue_range(self):
        # nv
        table = [[8, 2], [1, 5]]
        r = _drive(StatsFisherExact, table)
        assert 0.0 <= r['pvalue'] <= 1.0


# ── TestStatsMannWhitneyU ─────────────────────────────────────────────────

class TestStatsMannWhitneyU:
    def test_returns_dict(self):
        # nv
        r = _drive(StatsMannWhitneyU, _DATA1, _DATA2)
        assert 'statistic' in r
        assert 'pvalue' in r

    def test_pvalue_range(self):
        # nv
        r = _drive(StatsMannWhitneyU, _DATA1, _DATA2)
        assert 0.0 <= r['pvalue'] <= 1.0


# ── TestStatsWilcoxon ─────────────────────────────────────────────────────

class TestStatsWilcoxon:
    def test_one_sample(self):
        # nv
        r = _drive(StatsWilcoxon, [1.0, -2.0, 3.0, -1.0, 2.0])
        assert 'statistic' in r
        assert 'pvalue' in r

    def test_two_sample(self):
        # nv
        r = _drive(StatsWilcoxon, _DATA1, _DATA2)
        assert 'statistic' in r


# ── TestStatsKruskal ──────────────────────────────────────────────────────

class TestStatsKruskal:
    def test_returns_dict(self):
        # nv
        r = _drive(StatsKruskal, [[1, 2, 3], [4, 5, 6]])
        assert 'statistic' in r
        assert 'pvalue' in r

    def test_three_groups(self):
        # nv
        r = _drive(StatsKruskal, [[1, 2], [3, 4], [5, 6]])
        assert r is not None

    def test_wrong_result_fails(self):
        # nv
        assert _fails_with_wrong_result(StatsKruskal, [[1, 2, 3], [4, 5, 6]])


# ── TestStatsKs2samp ──────────────────────────────────────────────────────

class TestStatsKs2samp:
    def test_returns_dict(self):
        # nv
        r = _drive(StatsKs2samp, _DATA1, _DATA2)
        assert 'statistic' in r
        assert 'pvalue' in r

    def test_identical_samples_zero_stat(self):
        # nv
        r = _drive(StatsKs2samp, [1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert abs(r['statistic']) < 1e-9


# ── TestStatsNormalityTest ───────────────────────────────────────────────────

class TestStatsNormalityTest:
    def test_returns_dict(self):
        # nv
        np.random.seed(42)
        data = np.random.normal(0, 1, 100)
        r = _drive(StatsNormalityTest, data)
        assert 'statistic' in r
        assert 'pvalue' in r


# ── TestStatsShapiro ──────────────────────────────────────────────────────

class TestStatsShapiro:
    def test_returns_dict(self):
        # nv
        r = _drive(StatsShapiro, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert 'statistic' in r
        assert 'pvalue' in r

    def test_pvalue_range(self):
        # nv
        r = _drive(StatsShapiro, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert 0.0 <= r['pvalue'] <= 1.0


# ── TestStatsDist ─────────────────────────────────────────────────────────

class TestStatsDist:
    def test_norm_pdf_at_zero(self):
        # norm.pdf(0) = 1/sqrt(2*pi)
        # nv
        result = Var()
        dispatch = StatsDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', 'pdf', 0.0, result, trail)
        val = None
        for parent, sentinel in gen:
            if sentinel is None:
                val = deref(result)
                break
        assert val is not None
        import math
        assert abs(val - 1.0 / math.sqrt(2 * math.pi)) < 1e-9

    def test_norm_cdf_at_zero(self):
        # nv
        result = Var()
        dispatch = StatsDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', 'cdf', 0.0, result, trail)
        val = None
        for parent, sentinel in gen:
            if sentinel is None:
                val = deref(result)
                break
        assert val is not None
        assert abs(val - 0.5) < 1e-9

    def test_norm_entropy_no_x(self):
        # StatsDist(DIST, METHOD, RESULT) — 3-arity
        # nv
        result = Var()
        dispatch = StatsDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', 'entropy', result, trail)
        val = None
        for parent, sentinel in gen:
            if sentinel is None:
                val = deref(result)
                break
        assert val is not None
        import math
        expected = float(scipy_stats.norm.entropy())
        assert abs(val - expected) < 1e-9


# ── TestStatsNormalPdf ──────────────────────────────────────────────────────

class TestStatsNormalPdf:
    def test_at_zero(self):
        # nv
        r = _drive(StatsNormalPdf, 0.0)
        import math
        assert abs(r - 1.0 / math.sqrt(2 * math.pi)) < 1e-9

    def test_with_loc_scale(self):
        # nv
        r = _drive(StatsNormalPdf, 1.0, 1.0, 1.0)
        expected = float(scipy_stats.norm.pdf(1.0, loc=1.0, scale=1.0))
        assert abs(r - expected) < 1e-9

    def test_wrong_arity_returns_none(self):
        # 2-arity loc+scale call expects 4-arg form; wrong arity should fail
        # nv
        r = _drive(StatsNormalPdf, 0.0, 1.0)  # arity 3 — not registered
        assert r is None


# ── TestStatsNormalCdf ──────────────────────────────────────────────────────

class TestStatsNormalCdf:
    def test_at_zero(self):
        # nv
        r = _drive(StatsNormalCdf, 0.0)
        assert abs(r - 0.5) < 1e-9

    def test_with_loc_scale(self):
        # nv
        r = _drive(StatsNormalCdf, 2.0, 1.0, 2.0)
        expected = float(scipy_stats.norm.cdf(2.0, loc=1.0, scale=2.0))
        assert abs(r - expected) < 1e-9


# ── TestStatsNormalPpf ──────────────────────────────────────────────────────

class TestStatsNormalPpf:
    def test_median(self):
        # nv
        r = _drive(StatsNormalPpf, 0.5)
        assert abs(r) < 1e-9

    def test_with_loc_scale(self):
        # nv
        r = _drive(StatsNormalPpf, 0.5, 5.0, 1.0)
        expected = float(scipy_stats.norm.ppf(0.5, loc=5.0, scale=1.0))
        assert abs(r - expected) < 1e-9


# ── TestStatsNormalRvs ──────────────────────────────────────────────────────

class TestStatsNormalRvs:
    def test_scalar_result(self):
        # 1-arity: StatsNormalRvs(RESULT)
        # nv
        result = Var()
        dispatch = StatsNormalRvs._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, result, trail)
        val = None
        for parent, sentinel in gen:
            if sentinel is None:
                val = deref(result)
                break
        assert isinstance(val, float)

    def test_with_loc_scale(self):
        # nv
        r = _drive(StatsNormalRvs, 0.0, 1.0)
        assert isinstance(r, float)

    def test_with_size(self):
        # nv
        r = _drive(StatsNormalRvs, 0.0, 1.0, 5)
        assert r is not None
        assert len(r) == 5


# ── TestStatsFreezeDist ───────────────────────────────────────────────────

class TestStatsFreezeDist:
    def test_returns_int_handle(self):
        # nv
        result = Var()
        dispatch = StatsFreezeDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', {'loc': 0.0, 'scale': 1.0}, result, trail)
        handle = None
        for parent, sentinel in gen:
            if sentinel is None:
                handle = deref(result)
                break
        assert isinstance(handle, int)
        # cleanup
        from clausal.modules.py.scipy_stats import _FROZEN_DIST_REGISTRY
        _FROZEN_DIST_REGISTRY.pop(handle, None)

    def test_pdf_via_handle(self):
        # nv
        result = Var()
        dispatch = StatsFreezeDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', {'loc': 0.0, 'scale': 1.0}, result, trail)
        handle = None
        for parent, sentinel in gen:
            if sentinel is None:
                handle = deref(result)
                break

        # StatsFrozenPdf
        pdf_result = Var()
        pdf_dispatch = StatsFrozenPdf._get_dispatch()
        trail2 = Trail()
        gen2 = pdf_dispatch(None, None, None, None, handle, 0.0, pdf_result, trail2)
        val = None
        for parent, sentinel in gen2:
            if sentinel is None:
                val = deref(pdf_result)
                break

        import math
        assert abs(val - 1.0 / math.sqrt(2 * math.pi)) < 1e-9

        # cleanup
        from clausal.modules.py.scipy_stats import _FROZEN_DIST_REGISTRY
        _FROZEN_DIST_REGISTRY.pop(handle, None)

    def test_frozen_stats(self):
        # nv
        result = Var()
        dispatch = StatsFreezeDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', {'loc': 3.0, 'scale': 2.0}, result, trail)
        handle = None
        for parent, sentinel in gen:
            if sentinel is None:
                handle = deref(result)
                break

        stats_result = Var()
        stats_dispatch = StatsFrozenStats._get_dispatch()
        trail2 = Trail()
        gen2 = stats_dispatch(None, None, None, None, handle, stats_result, trail2)
        val = None
        for parent, sentinel in gen2:
            if sentinel is None:
                val = deref(stats_result)
                break
        assert abs(val['mean'] - 3.0) < 1e-9
        assert abs(val['var'] - 4.0) < 1e-9

        from clausal.modules.py.scipy_stats import _FROZEN_DIST_REGISTRY
        _FROZEN_DIST_REGISTRY.pop(handle, None)

    def test_frozen_free_removes_handle(self):
        # nv
        from clausal.modules.py.scipy_stats import _FROZEN_DIST_REGISTRY

        result = Var()
        dispatch = StatsFreezeDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', {'loc': 0.0, 'scale': 1.0}, result, trail)
        handle = None
        for parent, sentinel in gen:
            if sentinel is None:
                handle = deref(result)
                break

        assert handle in _FROZEN_DIST_REGISTRY

        free_dispatch = StatsFrozenFree._get_dispatch()
        trail2 = Trail()
        gen2 = free_dispatch(None, None, None, None, handle, trail2)
        for _ in gen2:
            pass

        assert handle not in _FROZEN_DIST_REGISTRY

    def test_frozen_cdf(self):
        # nv
        result = Var()
        dispatch = StatsFreezeDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', {'loc': 0.0, 'scale': 1.0}, result, trail)
        handle = None
        for parent, sentinel in gen:
            if sentinel is None:
                handle = deref(result)
                break

        cdf_result = Var()
        cdf_dispatch = StatsFrozenCdf._get_dispatch()
        trail2 = Trail()
        gen2 = cdf_dispatch(None, None, None, None, handle, 0.0, cdf_result, trail2)
        val = None
        for parent, sentinel in gen2:
            if sentinel is None:
                val = deref(cdf_result)
                break
        assert abs(val - 0.5) < 1e-9

        from clausal.modules.py.scipy_stats import _FROZEN_DIST_REGISTRY
        _FROZEN_DIST_REGISTRY.pop(handle, None)

    def test_frozen_ppf(self):
        # nv
        result = Var()
        dispatch = StatsFreezeDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', {'loc': 0.0, 'scale': 1.0}, result, trail)
        handle = None
        for parent, sentinel in gen:
            if sentinel is None:
                handle = deref(result)
                break

        # Backward direction of StatsFrozenCdf: StatsFrozenCdf(handle, x_var, 0.5)
        # x_var unbound, p=0.5 ground → x_var = dist.ppf(0.5)
        ppf_result = Var()
        cdf_dispatch = StatsFrozenCdf._get_dispatch()
        trail2 = Trail()
        gen2 = cdf_dispatch(None, None, None, None, handle, ppf_result, 0.5, trail2)
        val = None
        for parent, sentinel in gen2:
            if sentinel is None:
                val = deref(ppf_result)
                break
        assert abs(val) < 1e-9

        from clausal.modules.py.scipy_stats import _FROZEN_DIST_REGISTRY
        _FROZEN_DIST_REGISTRY.pop(handle, None)

    def test_frozen_rvs_scalar(self):
        # nv
        result = Var()
        dispatch = StatsFreezeDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', {'loc': 0.0, 'scale': 1.0}, result, trail)
        handle = None
        for parent, sentinel in gen:
            if sentinel is None:
                handle = deref(result)
                break

        rvs_result = Var()
        rvs_dispatch = StatsFrozenRvs._get_dispatch()
        trail2 = Trail()
        gen2 = rvs_dispatch(None, None, None, None, handle, rvs_result, trail2)
        val = None
        for parent, sentinel in gen2:
            if sentinel is None:
                val = deref(rvs_result)
                break
        assert isinstance(val, float)

        from clausal.modules.py.scipy_stats import _FROZEN_DIST_REGISTRY
        _FROZEN_DIST_REGISTRY.pop(handle, None)

    def test_frozen_rvs_with_size(self):
        # nv
        result = Var()
        dispatch = StatsFreezeDist._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, 'norm', {'loc': 0.0, 'scale': 1.0}, result, trail)
        handle = None
        for parent, sentinel in gen:
            if sentinel is None:
                handle = deref(result)
                break

        rvs_result = Var()
        rvs_dispatch = StatsFrozenRvs._get_dispatch()
        trail2 = Trail()
        gen2 = rvs_dispatch(None, None, None, None, handle, 10, rvs_result, trail2)
        val = None
        for parent, sentinel in gen2:
            if sentinel is None:
                val = deref(rvs_result)
                break
        assert val is not None
        assert len(val) == 10

        from clausal.modules.py.scipy_stats import _FROZEN_DIST_REGISTRY
        _FROZEN_DIST_REGISTRY.pop(handle, None)


# ── TestResultGet ─────────────────────────────────────────────────────────

class TestResultGet:
    def test_get_from_dict(self):
        # nv
        d = {'statistic': 3.14, 'pvalue': 0.05}
        v = _drive_result_get(d, 'statistic')
        assert abs(v - 3.14) < 1e-9

    def test_missing_field_fails(self):
        # nv
        d = {'statistic': 1.0}
        v = _drive_result_get(d, 'pvalue')
        assert v is None

    def test_non_string_field_fails(self):
        # nv
        value = Var()
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        field_var = Var()
        gen = dispatch(None, None, None, None, {'x': 1}, field_var, value, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0

    def test_bind_existing_value(self):
        # nv
        d = {'pvalue': 0.05}
        value = 0.05
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, d, 'pvalue', value, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 1

    def test_wrong_value_fails(self):
        # nv
        d = {'pvalue': 0.05}
        dispatch = ResultGet._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, d, 'pvalue', 0.99, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── Fixture integration ───────────────────────────────────────────────────

import os
from clausal.logic.solve import call
from clausal.import_hook import _load_module

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}.clausal")
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


class TestScipyStatsFixture:
    """Run Test predicates from tests/fixtures/scipy_stats_tests.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_stats_tests")

    @pytest.mark.parametrize("name", [
        "mean of list",
        "pearsonr perfect correlation",
        "linregress slope",
        "ttest1samp mean equal",
        "norm pdf at zero",
        "norm cdf at zero",
        "norm ppf median",
        "chisquare uniform",
        "ks2samp identical",
        "shapiro returns dict",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"
