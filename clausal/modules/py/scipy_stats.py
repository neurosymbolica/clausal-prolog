"""clausal.modules.py.scipy_stats — scipy.stats predicates for Clausal.

Provides statistical routines from scipy.stats as importable predicate
objects for use in .clausal files via::

    -import_from(scipy_stats, [StatsMean, StatsPearsonCorrelation, ResultGet, ...])

Or via the canonical path::

    -import_from(py.scipy_stats, [StatsMean, ...])

Tiers
-----
- **Tier 1** — descriptive statistics: return a plain Python value or dict
    StatsDescribe, StatsMean, StatsGeometricMean, StatsHarmonicMean,
    StatsMode, StatsSkew, StatsKurtosis, StatsInterquartileRange,
    StatsZScore, StatsMedianAbsoluteDeviation

- **Tier 2** — result-dict predicates (use ResultGet to access fields):
    StatsPearsonCorrelation, StatsSpearmanCorrelation, StatsKendallTau,
    StatsLinearRegression, StatsTheilSlopes,
    StatsTTest1Sample, StatsTTestIndependent, StatsTTestRelated,
    StatsChiSquare, StatsChiSquareContingency, StatsFisherExact,
    StatsMannWhitneyU, StatsWilcoxon, StatsKruskal, StatsKs2samp,
    StatsNormalityTest, StatsShapiro

- **Tier 1 functional** — distribution evaluation:
    StatsDist(DIST, METHOD, X, RESULT) / StatsDist(DIST, METHOD, RESULT)
    StatsNormalPdf, StatsNormalCdf, StatsNormalPpf, StatsNormalRvs

- **Tier 3** — frozen distribution handles:
    StatsFreezeDist, StatsFrozenPdf, StatsFrozenCdf,
    StatsFrozenRvs, StatsFrozenStats, StatsFrozenFree

Helper:
    ResultGet(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Lazy scipy.stats import ───────────────────────────────────────────────

_scipy_stats = None
_stats_lock = _threading.Lock()


def _ensure_stats():
    global _scipy_stats
    if _scipy_stats is not None:
        return
    with _stats_lock:
        if _scipy_stats is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_stats = _import_stdlib("scipy.stats")


def _st():
    _ensure_stats()
    return _scipy_stats


# ── Predicate adapter ─────────────────────────────────────────────────────

class _SciPyStatsPredicate:
    """Dispatch adapter for a scipy.stats predicate.

    Supports multiple arities via ``_register(arity, fn)``.
    Arity counts include RESULT but not trail.
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> "_SciPyStatsPredicate":
        self._dispatch_fns[arity] = fn
        return self

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        # args layout: (input_0, ..., input_{n-1}, result, trail)
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"scipy.stats.{self._name}/{arities}"


# ── Dispatch function factory ─────────────────────────────────────────────

def _dispatch_fn(call: Callable) -> Callable:
    """Trampoline dispatch: inputs → result → unify RESULT."""
    def dispatch(this_generator, parent, *args):
        # args: (input_0, ..., input_{n-1}, result, trail)
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = call(*inputs)
        except Exception:
            yield (parent, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _pred(name: str, *arity_fns) -> _SciPyStatsPredicate:
    """Create a ``_SciPyStatsPredicate`` from (arity, dispatch_fn) pairs."""
    p = _SciPyStatsPredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── Result normalization helpers ──────────────────────────────────────────

# ── Result normalization helpers ──────────────────────────────────────────

def _stat_pvalue(r) -> dict:
    return {'statistic': float(r.statistic), 'pvalue': float(r.pvalue)}


# ── Descriptive statistics (Tier 1) ──────────────────────────────────────

def _describe_result(r) -> dict:
    return {
        'nobs': r.nobs,
        'minmax': r.minmax,
        'mean': r.mean,
        'variance': r.variance,
        'skewness': r.skewness,
        'kurtosis': r.kurtosis,
    }


StatsDescribe = _pred("StatsDescribe",
    (2, _dispatch_fn(lambda a: _describe_result(_st().describe(a)))),
)

StatsMean = _pred("StatsMean",
    (2, _dispatch_fn(lambda a: float(_st().tmean(a)))),
)

StatsGeometricMean = _pred("StatsGeometricMean",
    (2, _dispatch_fn(lambda a: float(_st().gmean(a)))),
)

StatsHarmonicMean = _pred("StatsHarmonicMean",
    (2, _dispatch_fn(lambda a: float(_st().hmean(a)))),
)


def _mode_result(r) -> dict:
    # scipy >= 1.11 mode returns scalar; older returns array
    mode_val = r.mode
    count_val = r.count
    if hasattr(mode_val, '__len__'):
        mode_val = float(mode_val[0])
        count_val = int(count_val[0])
    else:
        mode_val = float(mode_val)
        count_val = int(count_val)
    return {'mode': mode_val, 'count': count_val}


StatsMode = _pred("StatsMode",
    (2, _dispatch_fn(lambda a: _mode_result(_st().mode(a)))),
)

StatsSkew = _pred("StatsSkew",
    (2, _dispatch_fn(lambda a: float(_st().skew(a)))),
)

StatsKurtosis = _pred("StatsKurtosis",
    (2, _dispatch_fn(lambda a: float(_st().kurtosis(a)))),
)

StatsInterquartileRange = _pred("StatsInterquartileRange",
    (2, _dispatch_fn(lambda x: float(_st().iqr(x)))),
)

StatsZScore = _pred("StatsZScore",
    (2, _dispatch_fn(lambda a: list(_st().zscore(a)))),
)

StatsMedianAbsoluteDeviation = _pred("StatsMedianAbsoluteDeviation",
    (2, _dispatch_fn(lambda x: float(_st().median_abs_deviation(x)))),
)


# ── Correlation and regression (Tier 2) ──────────────────────────────────

StatsPearsonCorrelation = _pred("StatsPearsonCorrelation",
    (3, _dispatch_fn(lambda x, y: _stat_pvalue(_st().pearsonr(x, y)))),
)

StatsSpearmanCorrelation = _pred("StatsSpearmanCorrelation",
    (2, _dispatch_fn(lambda a: _stat_pvalue(_st().spearmanr(a)))),
    (3, _dispatch_fn(lambda a, b: _stat_pvalue(_st().spearmanr(a, b)))),
)

StatsKendallTau = _pred("StatsKendallTau",
    (3, _dispatch_fn(lambda x, y: _stat_pvalue(_st().kendalltau(x, y)))),
)


def _linregress_result(r) -> dict:
    return {
        'slope': float(r.slope),
        'intercept': float(r.intercept),
        'rvalue': float(r.rvalue),
        'pvalue': float(r.pvalue),
        'stderr': float(r.stderr),
        'intercept_stderr': float(r.intercept_stderr),
    }


StatsLinearRegression = _pred("StatsLinearRegression",
    (3, _dispatch_fn(lambda x, y: _linregress_result(_st().linregress(x, y)))),
)


def _theilslopes_result(r) -> dict:
    return {
        'slope': float(r.slope),
        'intercept': float(r.intercept),
        'low_slope': float(r.low_slope),
        'high_slope': float(r.high_slope),
    }


StatsTheilSlopes = _pred("StatsTheilSlopes",
    (2, _dispatch_fn(lambda y: _theilslopes_result(_st().theilslopes(y)))),
    (3, _dispatch_fn(lambda y, x: _theilslopes_result(_st().theilslopes(y, x)))),
)


# ── Parametric hypothesis tests (Tier 2) ─────────────────────────────────

def _ttest_result(r) -> dict:
    d = _stat_pvalue(r)
    if hasattr(r, 'df'):
        d['df'] = float(r.df)
    return d


StatsTTest1Sample = _pred("StatsTTest1Sample",
    (3, _dispatch_fn(lambda a, popmean: _ttest_result(_st().ttest_1samp(a, popmean)))),
)

StatsTTestIndependent = _pred("StatsTTestIndependent",
    (3, _dispatch_fn(lambda a, b: _ttest_result(_st().ttest_ind(a, b)))),
    (4, _dispatch_fn(lambda a, b, equal_var: _ttest_result(_st().ttest_ind(a, b, equal_var=bool(equal_var))))),
)

StatsTTestRelated = _pred("StatsTTestRelated",
    (3, _dispatch_fn(lambda a, b: _ttest_result(_st().ttest_rel(a, b)))),
)


StatsChiSquare = _pred("StatsChiSquare",
    (2, _dispatch_fn(lambda f_obs: _stat_pvalue(_st().chisquare(f_obs)))),
    (3, _dispatch_fn(lambda f_obs, f_exp: _stat_pvalue(_st().chisquare(f_obs, f_exp=f_exp)))),
)


def _chi2_contingency_result(r) -> dict:
    return {
        'statistic': float(r.statistic),
        'pvalue': float(r.pvalue),
        'dof': int(r.dof),
        'expected_freq': r.expected_freq,
    }


StatsChiSquareContingency = _pred("StatsChiSquareContingency",
    (2, _dispatch_fn(lambda observed: _chi2_contingency_result(_st().chi2_contingency(observed)))),
)


StatsFisherExact = _pred("StatsFisherExact",
    (2, _dispatch_fn(lambda table: _stat_pvalue(_st().fisher_exact(table)))),
)


# ── Nonparametric tests (Tier 2) ──────────────────────────────────────────

StatsMannWhitneyU = _pred("StatsMannWhitneyU",
    (3, _dispatch_fn(lambda x, y: _stat_pvalue(_st().mannwhitneyu(x, y)))),
)

StatsWilcoxon = _pred("StatsWilcoxon",
    (2, _dispatch_fn(lambda x: _stat_pvalue(_st().wilcoxon(x)))),
    (3, _dispatch_fn(lambda x, y: _stat_pvalue(_st().wilcoxon(x, y)))),
)


def _kruskal_call(groups):
    """StatsKruskal takes a list of arrays; unpack for scipy."""
    return _stat_pvalue(_st().kruskal(*groups))


StatsKruskal = _pred("StatsKruskal",
    (2, _dispatch_fn(_kruskal_call)),
)

StatsKs2samp = _pred("StatsKs2samp",
    (3, _dispatch_fn(lambda data1, data2: _stat_pvalue(_st().ks_2samp(data1, data2)))),
)

StatsNormalityTest = _pred("StatsNormalityTest",
    (2, _dispatch_fn(lambda a: _stat_pvalue(_st().normaltest(a)))),
)

StatsShapiro = _pred("StatsShapiro",
    (2, _dispatch_fn(lambda x: _stat_pvalue(_st().shapiro(x)))),
)


# ── Distribution interface (Tier 1 functional) ────────────────────────────

def _dist_method_x(dist_name, method_name, x):
    """Call dist.method(x) for distributions that take a point argument."""
    dist = getattr(_st(), dist_name)
    fn = getattr(dist, method_name)
    result = fn(x)
    try:
        return float(result)
    except (TypeError, ValueError):
        return result


def _dist_method_no_x(dist_name, method_name):
    """Call dist.method() for methods that take no point argument (e.g. entropy)."""
    dist = getattr(_st(), dist_name)
    fn = getattr(dist, method_name)
    result = fn()
    try:
        return float(result)
    except (TypeError, ValueError):
        return result


class _StatsDistPredicate(_SciPyStatsPredicate):
    """StatsDist(DIST, METHOD, X, RESULT) and StatsDist(DIST, METHOD, RESULT)."""

    def __init__(self):
        super().__init__("StatsDist")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, parent, *args):
        trail = args[-1]
        arity = len(args) - 1  # exclude trail
        if arity == 4:
            # StatsDist(DIST, METHOD, X, RESULT)
            dist_name, method_name, x, result_var = [deref(a) for a in args[:-1]]
            try:
                out = _dist_method_x(dist_name, method_name, x)
            except Exception:
                yield (parent, DONE)
                return
        elif arity == 3:
            # StatsDist(DIST, METHOD, RESULT)
            dist_name, method_name, result_var = [deref(a) for a in args[:-1]]
            try:
                out = _dist_method_no_x(dist_name, method_name)
            except Exception:
                yield (parent, DONE)
                return
        else:
            yield (parent, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)


StatsDist = _StatsDistPredicate()

# Normal distribution shortcuts
StatsNormalPdf = _pred("StatsNormalPdf",
    (2, _dispatch_fn(lambda x: float(_st().norm.pdf(x)))),
    (4, _dispatch_fn(lambda x, loc, scale: float(_st().norm.pdf(x, loc=loc, scale=scale)))),
)

StatsNormalCdf = _pred("StatsNormalCdf",
    (2, _dispatch_fn(lambda x: float(_st().norm.cdf(x)))),
    (4, _dispatch_fn(lambda x, loc, scale: float(_st().norm.cdf(x, loc=loc, scale=scale)))),
)

StatsNormalPpf = _pred("StatsNormalPpf",
    (2, _dispatch_fn(lambda q: float(_st().norm.ppf(q)))),
    (4, _dispatch_fn(lambda q, loc, scale: float(_st().norm.ppf(q, loc=loc, scale=scale)))),
)

StatsNormalRvs = _pred("StatsNormalRvs",
    (1, _dispatch_fn(lambda: float(_st().norm.rvs()))),
    (3, _dispatch_fn(lambda loc, scale: float(_st().norm.rvs(loc=loc, scale=scale)))),
    (4, _dispatch_fn(lambda loc, scale, size: _st().norm.rvs(loc=loc, scale=scale, size=size))),
)


# ── Tier 3: Frozen distribution handles ───────────────────────────────────

_FROZEN_DIST_REGISTRY: dict[int, object] = {}
_frozen_lock = _threading.Lock()
_frozen_counter = [0]


def _alloc_handle(dist_obj) -> int:
    with _frozen_lock:
        _frozen_counter[0] += 1
        handle = _frozen_counter[0]
        _FROZEN_DIST_REGISTRY[handle] = dist_obj
    return handle


def _lookup_handle(handle: int):
    dist = _FROZEN_DIST_REGISTRY.get(handle)
    if dist is None:
        raise KeyError(f"Unknown frozen distribution handle: {handle}")
    return dist


def _freeze_dist(dist_name, params_dict):
    dist_cls = getattr(_st(), dist_name)
    frozen = dist_cls(**params_dict)
    return _alloc_handle(frozen)


class _StatsFreezePredicate(_SciPyStatsPredicate):
    """StatsFreezeDist(DIST, PARAMS_DICT, RESULT)."""

    def __init__(self):
        super().__init__("StatsFreezeDist")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, parent, *args):
        trail = args[-1]
        dist_name = deref(args[0])
        params_dict = deref(args[1])
        result_var = args[2]
        try:
            handle = _freeze_dist(dist_name, params_dict)
        except Exception:
            yield (parent, DONE)
            return
        try:
            ok = bool(unify(result_var, handle, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)


StatsFreezeDist = _StatsFreezePredicate()


class _StatsFrozenMethodPredicate(_SciPyStatsPredicate):
    """Base for StatsFrozenPdf."""

    def __init__(self, name: str, method_name: str):
        super().__init__(name)
        self._method_name = method_name

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, parent, *args):
        trail = args[-1]
        handle = deref(args[0])
        x = deref(args[1])
        result_var = args[2]
        try:
            dist = _lookup_handle(int(handle))
            fn = getattr(dist, self._method_name)
            out = float(fn(x))
        except Exception:
            yield (parent, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)


StatsFrozenPdf = _StatsFrozenMethodPredicate("StatsFrozenPdf", "pdf")


class _StatsFrozenCdfPredicate(_SciPyStatsPredicate):
    """StatsFrozenCdf(HANDLE, X, P) — bidirectional CDF / quantile.

    HANDLE ground always.
    X ground, P unbound → P = dist.cdf(x)
    P ground, X unbound → X = dist.ppf(p)
    Both ground          → consistency check via cdf
    """

    def __init__(self):
        super().__init__("StatsFrozenCdf")

    def _get_dispatch(self):
        return self._dispatch

    def _dispatch(self, this_generator, parent, *args):
        trail      = args[-1]
        handle_raw = args[0]
        x_raw      = args[1]
        p_raw      = args[2]
        handle     = deref(handle_raw)
        x          = deref(x_raw)
        p          = deref(p_raw)

        try:
            dist = _lookup_handle(int(handle))
        except Exception:
            yield (parent, DONE)
            return

        if not is_var(x) and is_var(p):
            out = float(dist.cdf(x))
            if unify(p_raw, out, trail):
                yield (parent, None)

        elif is_var(x) and not is_var(p):
            out = float(dist.ppf(p))
            if unify(x_raw, out, trail):
                yield (parent, None)

        elif not is_var(x) and not is_var(p):
            out = float(dist.cdf(x))
            try:
                ok = bool(unify(p_raw, out, trail))
            except (ValueError, TypeError):
                ok = False
            if ok:
                yield (parent, None)

        yield (parent, DONE)


StatsFrozenCdf = _StatsFrozenCdfPredicate()


class _StatsFrozenRvsPredicate(_SciPyStatsPredicate):
    """StatsFrozenRvs(HANDLE, RESULT) and StatsFrozenRvs(HANDLE, SIZE, RESULT)."""

    def __init__(self):
        super().__init__("StatsFrozenRvs")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, parent, *args):
        trail = args[-1]
        arity = len(args) - 1  # exclude trail
        if arity == 2:
            handle = deref(args[0])
            result_var = args[1]
            size = None
        elif arity == 3:
            handle = deref(args[0])
            size = deref(args[1])
            result_var = args[2]
        else:
            yield (parent, DONE)
            return
        try:
            dist = _lookup_handle(int(handle))
            out = dist.rvs(size=size) if size is not None else float(dist.rvs())
        except Exception:
            yield (parent, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)


StatsFrozenRvs = _StatsFrozenRvsPredicate()


class _StatsFrozenStatsPredicate(_SciPyStatsPredicate):
    """StatsFrozenStats(HANDLE, RESULT) — returns dict with 'mean' and 'var'."""

    def __init__(self):
        super().__init__("StatsFrozenStats")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, parent, *args):
        trail = args[-1]
        handle = deref(args[0])
        result_var = args[1]
        try:
            dist = _lookup_handle(int(handle))
            mean, var = dist.stats(moments='mv')
            out = {'mean': float(mean), 'var': float(var)}
        except Exception:
            yield (parent, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)


StatsFrozenStats = _StatsFrozenStatsPredicate()


class _StatsFrozenFreePredicate(_SciPyStatsPredicate):
    """StatsFrozenFree(HANDLE) — release frozen distribution from registry."""

    def __init__(self):
        super().__init__("StatsFrozenFree")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, parent, *args):
        trail = args[-1]
        handle = deref(args[0])
        with _frozen_lock:
            _FROZEN_DIST_REGISTRY.pop(int(handle), None)
        yield (parent, None)
        yield (parent, DONE)


StatsFrozenFree = _StatsFrozenFreePredicate()


# ── Helper: ResultGet ─────────────────────────────────────────────────────

class _ResultGetPredicate:
    """ResultGet(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE.

    RESULT must be a dict (or object with attribute access via getattr).
    FIELD must be a ground string key.
    VALUE is unified with the retrieved value.
    """

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, parent, result, field, value, trail):
        result = deref(result)
        field = deref(field)
        if not isinstance(field, str):
            yield (parent, DONE)
            return
        # Try getattr first, then dict subscript
        val = _MISSING = object()
        if hasattr(result, field):
            val = getattr(result, field)
        if val is _MISSING:
            try:
                val = result[field]
            except (KeyError, TypeError):
                yield (parent, DONE)
                return
        try:
            ok = bool(unify(value, val, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)

    def __repr__(self) -> str:
        return "ResultGet/3"


ResultGet = _ResultGetPredicate()
