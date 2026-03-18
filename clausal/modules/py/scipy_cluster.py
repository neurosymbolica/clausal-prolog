"""clausal.modules.py.scipy_cluster — scipy.cluster predicates for Clausal.

Provides hierarchical clustering and vector quantisation routines from
``scipy.cluster.hierarchy`` and ``scipy.cluster.vq`` as importable predicate
objects for use in .clausal files via::

    -import_from(scipy_cluster, [Linkage, FlatCluster, Dendrogram,
                                  Cophenet, Inconsistent,
                                  KMeans2, KMeans, VectorQuantize, Whiten,
                                  ResultGet])

Tiers
-----
All predicates are **Tier 2** — they return result dicts (or plain NumPy
arrays for simple cases).  Use ``ResultGet`` to access named fields.

Hierarchical clustering (``scipy.cluster.hierarchy``):
    Linkage         → linkage matrix Z (ndarray, shape (n-1, 4))
    FlatCluster     → flat cluster-assignment array (ndarray, shape (n,))
    Dendrogram      → dict {icoord, dcoord, ivl, leaves, color_list}
    Cophenet        → float c (coefficient) or dict {c, d} when Y supplied
    Inconsistent    → inconsistency array (ndarray, shape (n-1, 4))

Vector quantisation (``scipy.cluster.vq``):
    KMeans2         → dict {centroid, label}
    KMeans          → dict {codebook, distortion}
    VectorQuantize  → dict {code, dist}
    Whiten          → normalised observation array (ndarray)

Helper:
    ResultGet(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE


# ── Lazy scipy.cluster imports ─────────────────────────────────────────────

_scipy_hierarchy = None
_scipy_vq = None
_cluster_lock = _threading.Lock()


def _ensure_cluster():
    global _scipy_hierarchy, _scipy_vq
    if _scipy_hierarchy is not None:
        return
    with _cluster_lock:
        if _scipy_hierarchy is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_hierarchy = _import_stdlib("scipy.cluster.hierarchy")
        _scipy_vq = _import_stdlib("scipy.cluster.vq")


def _hier():
    _ensure_cluster()
    return _scipy_hierarchy


def _vq():
    _ensure_cluster()
    return _scipy_vq


# ── Predicate adapter ─────────────────────────────────────────────────────

class _SciPyClusterPredicate:
    """Dispatch adapter for a scipy.cluster predicate.

    Supports multiple arities via ``_register(arity, fn)``.
    Arity counts include RESULT but not trail.
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> "_SciPyClusterPredicate":
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
        return f"scipy.cluster.{self._name}/{arities}"


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


def _pred(name: str, *arity_fns) -> _SciPyClusterPredicate:
    """Create a ``_SciPyClusterPredicate`` from (arity, dispatch_fn) pairs."""
    p = _SciPyClusterPredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── Linkage ───────────────────────────────────────────────────────────────

Linkage = _pred("Linkage",
    (2, _dispatch_fn(lambda y:
        _hier().linkage(y))),
    (3, _dispatch_fn(lambda y, method:
        _hier().linkage(y, method=method))),
    (4, _dispatch_fn(lambda y, method, metric:
        _hier().linkage(y, method=method, metric=metric))),
    (5, _dispatch_fn(lambda y, method, metric, optimal_ordering:
        _hier().linkage(y, method=method, metric=metric,
                        optimal_ordering=optimal_ordering))),
)


# ── FlatCluster ───────────────────────────────────────────────────────────

FlatCluster = _pred("FlatCluster",
    (3, _dispatch_fn(lambda z, t:
        _hier().fcluster(z, t))),
    (4, _dispatch_fn(lambda z, t, criterion:
        _hier().fcluster(z, t, criterion=criterion))),
    (5, _dispatch_fn(lambda z, t, criterion, depth:
        _hier().fcluster(z, t, criterion=criterion, depth=depth))),
)


# ── Dendrogram ────────────────────────────────────────────────────────────

def _dendrogram_result(z, **kwargs):
    result = _hier().dendrogram(z, no_plot=True, **kwargs)
    return {
        'icoord': result['icoord'],
        'dcoord': result['dcoord'],
        'ivl': result['ivl'],
        'leaves': result['leaves'],
        'color_list': result['color_list'],
    }


Dendrogram = _pred("Dendrogram",
    (2, _dispatch_fn(lambda z:
        _dendrogram_result(z))),
    (3, _dispatch_fn(lambda z, truncate_mode:
        _dendrogram_result(z, truncate_mode=truncate_mode))),
)


# ── Cophenet ──────────────────────────────────────────────────────────────

def _cophenet_with_y(z, y):
    c, d = _hier().cophenet(z, y)
    return {'c': float(c), 'd': d}


Cophenet = _pred("Cophenet",
    # Without Y: returns the cophenetic distance array (condensed form)
    (2, _dispatch_fn(lambda z:
        _hier().cophenet(z))),
    # With Y: returns dict {'c': correlation coefficient, 'd': distances}
    (3, _dispatch_fn(_cophenet_with_y)),
)


# ── Inconsistent ──────────────────────────────────────────────────────────

Inconsistent = _pred("Inconsistent",
    (2, _dispatch_fn(lambda z:
        _hier().inconsistent(z))),
    (3, _dispatch_fn(lambda z, depth:
        _hier().inconsistent(z, d=depth))),
)


# ── KMeans2 ───────────────────────────────────────────────────────────────

def _kmeans2_result(data, k, **kwargs):
    centroid, label = _vq().kmeans2(data, k, **kwargs)
    return {'centroid': centroid, 'label': label}


KMeans2 = _pred("KMeans2",
    (3, _dispatch_fn(lambda data, k:
        _kmeans2_result(data, k))),
    (4, _dispatch_fn(lambda data, k, iterations:
        _kmeans2_result(data, k, iter=iterations))),
    (5, _dispatch_fn(lambda data, k, iterations, seed:
        _kmeans2_result(data, k, iter=iterations, seed=seed))),
)


# ── KMeans ────────────────────────────────────────────────────────────────

def _kmeans_result(obs, k, **kwargs):
    codebook, distortion = _vq().kmeans(obs, k, **kwargs)
    return {'codebook': codebook, 'distortion': float(distortion)}


KMeans = _pred("KMeans",
    (3, _dispatch_fn(lambda obs, k:
        _kmeans_result(obs, k))),
    (4, _dispatch_fn(lambda obs, k, iterations:
        _kmeans_result(obs, k, iter=iterations))),
)


# ── VectorQuantize ────────────────────────────────────────────────────────

def _vq_result(obs, code_book):
    code, dist = _vq().vq(obs, code_book)
    return {'code': code, 'dist': dist}


VectorQuantize = _pred("VectorQuantize",
    (3, _dispatch_fn(_vq_result)),
)


# ── Whiten ────────────────────────────────────────────────────────────────

Whiten = _pred("Whiten",
    (2, _dispatch_fn(lambda obs:
        _vq().whiten(obs))),
)


# ── Helper: ResultGet ─────────────────────────────────────────────────────

class _ResultGetPredicate:
    """ResultGet(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE.

    RESULT must be a dict.
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
