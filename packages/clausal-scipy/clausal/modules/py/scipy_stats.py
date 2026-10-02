"""clausal.modules.py.scipy_stats — scipy.stats predicates for Clausal.

Provides statistical routines from scipy.stats as importable predicate
objects for use in .clausal files via::

    -import_from(scipy_stats, [stats_mean, stats_pearson_correlation, result_get, ...])

Or via the canonical path::

    -import_from(py.scipy_stats, [stats_mean, ...])

Tiers
-----
- **Tier 1** — descriptive statistics: return a plain Python value or dict
    stats_describe, stats_mean, stats_geometric_mean, stats_harmonic_mean,
    stats_mode, stats_skew, stats_kurtosis, stats_interquartile_range,
    stats_z_score, stats_median_absolute_deviation

- **Tier 2** — result-dict predicates (use result_get to access fields):
    stats_pearson_correlation, stats_spearman_correlation, stats_kendall_tau,
    stats_linear_regression, stats_theil_slopes,
    stats_t_test1_sample, stats_t_test_independent, stats_t_test_related,
    stats_chi_square, stats_chi_square_contingency, stats_fisher_exact,
    stats_mann_whitney_u, stats_wilcoxon, stats_kruskal, stats_ks2samp,
    stats_normality_test, stats_shapiro

- **Tier 1 functional** — distribution evaluation:
    stats_dist(DIST, METHOD, X, RESULT) / stats_dist(DIST, METHOD, RESULT)
    stats_normal_pdf, stats_normal_cdf, stats_normal_ppf, stats_normal_rvs

- **Tier 3** — frozen distribution handles:
    stats_freeze_dist, stats_frozen_pdf, stats_frozen_cdf,
    stats_frozen_rvs, stats_frozen_stats, stats_frozen_free

Helper:
    result_get(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


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


# ── Dispatch function factory ─────────────────────────────────────────────

def _dispatch_fn(call: Callable) -> Callable:
    """Trampoline dispatch: inputs → result → unify RESULT."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        # args: (input_0, ..., input_{n-1}, result, trail)
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = call(*inputs)
        except Exception:
            yield (_fail, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _pred(name: str, *arity_fns) -> ModulePredicate:
    """Create a ``ModulePredicate`` from (arity, dispatch_fn) pairs."""
    p = ModulePredicate(name)
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


stats_describe = _pred("stats_describe",
    (2, _dispatch_fn(lambda a: _describe_result(_st().describe(a)))),
)

stats_mean = _pred("stats_mean",
    (2, _dispatch_fn(lambda a: float(_st().tmean(a)))),
)

stats_geometric_mean = _pred("stats_geometric_mean",
    (2, _dispatch_fn(lambda a: float(_st().gmean(a)))),
)

stats_harmonic_mean = _pred("stats_harmonic_mean",
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


stats_mode = _pred("stats_mode",
    (2, _dispatch_fn(lambda a: _mode_result(_st().mode(a)))),
)

stats_skew = _pred("stats_skew",
    (2, _dispatch_fn(lambda a: float(_st().skew(a)))),
)

stats_kurtosis = _pred("stats_kurtosis",
    (2, _dispatch_fn(lambda a: float(_st().kurtosis(a)))),
)

stats_interquartile_range = _pred("stats_interquartile_range",
    (2, _dispatch_fn(lambda x: float(_st().iqr(x)))),
)

stats_z_score = _pred("stats_z_score",
    (2, _dispatch_fn(lambda a: list(_st().zscore(a)))),
)

stats_median_absolute_deviation = _pred("stats_median_absolute_deviation",
    (2, _dispatch_fn(lambda x: float(_st().median_abs_deviation(x)))),
)


# ── Correlation and regression (Tier 2) ──────────────────────────────────

stats_pearson_correlation = _pred("stats_pearson_correlation",
    (3, _dispatch_fn(lambda x, y: _stat_pvalue(_st().pearsonr(x, y)))),
)

stats_spearman_correlation = _pred("stats_spearman_correlation",
    (2, _dispatch_fn(lambda a: _stat_pvalue(_st().spearmanr(a)))),
    (3, _dispatch_fn(lambda a, b: _stat_pvalue(_st().spearmanr(a, b)))),
)

stats_kendall_tau = _pred("stats_kendall_tau",
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


stats_linear_regression = _pred("stats_linear_regression",
    (3, _dispatch_fn(lambda x, y: _linregress_result(_st().linregress(x, y)))),
)


def _theilslopes_result(r) -> dict:
    return {
        'slope': float(r.slope),
        'intercept': float(r.intercept),
        'low_slope': float(r.low_slope),
        'high_slope': float(r.high_slope),
    }


stats_theil_slopes = _pred("stats_theil_slopes",
    (2, _dispatch_fn(lambda y: _theilslopes_result(_st().theilslopes(y)))),
    (3, _dispatch_fn(lambda y, x: _theilslopes_result(_st().theilslopes(y, x)))),
)


# ── Parametric hypothesis tests (Tier 2) ─────────────────────────────────

def _ttest_result(r) -> dict:
    d = _stat_pvalue(r)
    if hasattr(r, 'df'):
        d['df'] = float(r.df)
    return d


stats_t_test1_sample = _pred("stats_t_test1_sample",
    (3, _dispatch_fn(lambda a, popmean: _ttest_result(_st().ttest_1samp(a, popmean)))),
)

stats_t_test_independent = _pred("stats_t_test_independent",
    (3, _dispatch_fn(lambda a, b: _ttest_result(_st().ttest_ind(a, b)))),
    (4, _dispatch_fn(lambda a, b, equal_var: _ttest_result(_st().ttest_ind(a, b, equal_var=bool(equal_var))))),
)

stats_t_test_related = _pred("stats_t_test_related",
    (3, _dispatch_fn(lambda a, b: _ttest_result(_st().ttest_rel(a, b)))),
)


stats_chi_square = _pred("stats_chi_square",
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


stats_chi_square_contingency = _pred("stats_chi_square_contingency",
    (2, _dispatch_fn(lambda observed: _chi2_contingency_result(_st().chi2_contingency(observed)))),
)


stats_fisher_exact = _pred("stats_fisher_exact",
    (2, _dispatch_fn(lambda table: _stat_pvalue(_st().fisher_exact(table)))),
)


# ── Nonparametric tests (Tier 2) ──────────────────────────────────────────

stats_mann_whitney_u = _pred("stats_mann_whitney_u",
    (3, _dispatch_fn(lambda x, y: _stat_pvalue(_st().mannwhitneyu(x, y)))),
)

stats_wilcoxon = _pred("stats_wilcoxon",
    (2, _dispatch_fn(lambda x: _stat_pvalue(_st().wilcoxon(x)))),
    (3, _dispatch_fn(lambda x, y: _stat_pvalue(_st().wilcoxon(x, y)))),
)


def _kruskal_call(groups):
    """stats_kruskal takes a list of arrays; unpack for scipy."""
    return _stat_pvalue(_st().kruskal(*groups))


stats_kruskal = _pred("stats_kruskal",
    (2, _dispatch_fn(_kruskal_call)),
)

stats_ks2samp = _pred("stats_ks2samp",
    (3, _dispatch_fn(lambda data1, data2: _stat_pvalue(_st().ks_2samp(data1, data2)))),
)

stats_normality_test = _pred("stats_normality_test",
    (2, _dispatch_fn(lambda a: _stat_pvalue(_st().normaltest(a)))),
)

stats_shapiro = _pred("stats_shapiro",
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


class _StatsDistPredicate(ModulePredicate):
    """stats_dist(DIST, METHOD, X, RESULT) and stats_dist(DIST, METHOD, RESULT)."""

    def __init__(self):
        super().__init__("stats_dist")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        arity = len(args) - 1  # exclude trail
        if arity == 4:
            # stats_dist(DIST, METHOD, X, RESULT)
            dist_name, method_name, x, result_var = [deref(a) for a in args[:-1]]
            try:
                out = _dist_method_x(dist_name, method_name, x)
            except Exception:
                yield (_fail, DONE)
                return
        elif arity == 3:
            # stats_dist(DIST, METHOD, RESULT)
            dist_name, method_name, result_var = [deref(a) for a in args[:-1]]
            try:
                out = _dist_method_no_x(dist_name, method_name)
            except Exception:
                yield (_fail, DONE)
                return
        else:
            yield (_fail, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)


stats_dist = _StatsDistPredicate()

# Normal distribution shortcuts
stats_normal_pdf = _pred("stats_normal_pdf",
    (2, _dispatch_fn(lambda x: float(_st().norm.pdf(x)))),
    (4, _dispatch_fn(lambda x, loc, scale: float(_st().norm.pdf(x, loc=loc, scale=scale)))),
)

stats_normal_cdf = _pred("stats_normal_cdf",
    (2, _dispatch_fn(lambda x: float(_st().norm.cdf(x)))),
    (4, _dispatch_fn(lambda x, loc, scale: float(_st().norm.cdf(x, loc=loc, scale=scale)))),
)

stats_normal_ppf = _pred("stats_normal_ppf",
    (2, _dispatch_fn(lambda q: float(_st().norm.ppf(q)))),
    (4, _dispatch_fn(lambda q, loc, scale: float(_st().norm.ppf(q, loc=loc, scale=scale)))),
)

stats_normal_rvs = _pred("stats_normal_rvs",
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


class _StatsFreezePredicate(ModulePredicate):
    """stats_freeze_dist(DIST, PARAMS_DICT, RESULT)."""

    def __init__(self):
        super().__init__("stats_freeze_dist")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        dist_name = deref(args[0])
        params_dict = deref(args[1])
        result_var = args[2]
        try:
            handle = _freeze_dist(dist_name, params_dict)
        except Exception:
            yield (_fail, DONE)
            return
        try:
            ok = bool(unify(result_var, handle, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)


stats_freeze_dist = _StatsFreezePredicate()


class _StatsFrozenMethodPredicate(ModulePredicate):
    """Base for stats_frozen_pdf."""

    def __init__(self, name: str, method_name: str):
        super().__init__(name)
        self._method_name = method_name

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        handle = deref(args[0])
        x = deref(args[1])
        result_var = args[2]
        try:
            dist = _lookup_handle(int(handle))
            fn = getattr(dist, self._method_name)
            out = float(fn(x))
        except Exception:
            yield (_fail, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)


stats_frozen_pdf = _StatsFrozenMethodPredicate("stats_frozen_pdf", "pdf")


class _StatsFrozenCdfPredicate(ModulePredicate):
    """stats_frozen_cdf(HANDLE, X, P) — bidirectional CDF / quantile.

    HANDLE ground always.
    X ground, P unbound → P = dist.cdf(x)
    P ground, X unbound → X = dist.ppf(p)
    Both ground          → consistency check via cdf
    """

    def __init__(self):
        super().__init__("stats_frozen_cdf")

    def _get_dispatch(self):
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
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
            yield (_fail, DONE)
            return

        if not is_var(x) and is_var(p):
            out = float(dist.cdf(x))
            if unify(p_raw, out, trail):
                yield (_proceed, None)

        elif is_var(x) and not is_var(p):
            out = float(dist.ppf(p))
            if unify(x_raw, out, trail):
                yield (_proceed, None)

        elif not is_var(x) and not is_var(p):
            out = float(dist.cdf(x))
            try:
                ok = bool(unify(p_raw, out, trail))
            except (ValueError, TypeError):
                ok = False
            if ok:
                yield (_proceed, None)

        yield (_fail, DONE)


stats_frozen_cdf = _StatsFrozenCdfPredicate()


class _StatsFrozenRvsPredicate(ModulePredicate):
    """stats_frozen_rvs(HANDLE, RESULT) and stats_frozen_rvs(HANDLE, SIZE, RESULT)."""

    def __init__(self):
        super().__init__("stats_frozen_rvs")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
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
            yield (_fail, DONE)
            return
        try:
            dist = _lookup_handle(int(handle))
            out = dist.rvs(size=size) if size is not None else float(dist.rvs())
        except Exception:
            yield (_fail, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)


stats_frozen_rvs = _StatsFrozenRvsPredicate()


class _StatsFrozenStatsPredicate(ModulePredicate):
    """stats_frozen_stats(HANDLE, RESULT) — returns dict with 'mean' and 'var'."""

    def __init__(self):
        super().__init__("stats_frozen_stats")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        handle = deref(args[0])
        result_var = args[1]
        try:
            dist = _lookup_handle(int(handle))
            mean, var = dist.stats(moments='mv')
            out = {'mean': float(mean), 'var': float(var)}
        except Exception:
            yield (_fail, DONE)
            return
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)


stats_frozen_stats = _StatsFrozenStatsPredicate()


class _StatsFrozenFreePredicate(ModulePredicate):
    """stats_frozen_free(HANDLE) — release frozen distribution from registry."""

    def __init__(self):
        super().__init__("stats_frozen_free")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        handle = deref(args[0])
        with _frozen_lock:
            _FROZEN_DIST_REGISTRY.pop(int(handle), None)
        yield (_proceed, None)
        yield (_fail, DONE)


stats_frozen_free = _StatsFrozenFreePredicate()


# ── Helper: result_get ─────────────────────────────────────────────────────

class _ResultGetPredicate:
    """result_get(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE.

    RESULT must be a dict (or object with attribute access via getattr).
    FIELD must be a ground string key.
    VALUE is unified with the retrieved value.
    """

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, result, field, value, trail):
        result = deref(result)
        field = deref(field)
        if not isinstance(field, str):
            yield (_fail, DONE)
            return
        # Try getattr first, then dict subscript
        val = _MISSING = object()
        if hasattr(result, field):
            val = getattr(result, field)
        if val is _MISSING:
            try:
                val = result[field]
            except (KeyError, TypeError):
                yield (_fail, DONE)
                return
        try:
            ok = bool(unify(value, val, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)

    def __repr__(self) -> str:
        return "result_get/3"


result_get = _ResultGetPredicate()
