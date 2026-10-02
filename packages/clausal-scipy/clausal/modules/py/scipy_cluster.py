"""clausal.modules.py.scipy_cluster — scipy.cluster predicates for Clausal.

Provides hierarchical clustering and vector quantisation routines from
``scipy.cluster.hierarchy`` and ``scipy.cluster.vq`` as importable predicate
objects for use in .clausal files via::

    -import_from(scipy_cluster, [linkage, flat_cluster, dendrogram,
                                  cophenet, inconsistent,
                                  k_means2, k_means, vector_quantize, whiten,
                                  result_get])

Tiers
-----
All predicates are **Tier 2** — they return result dicts (or plain NumPy
arrays for simple cases).  Use ``result_get`` to access named fields.

Hierarchical clustering (``scipy.cluster.hierarchy``):
    linkage         → linkage matrix Z (ndarray, shape (n-1, 4))
    flat_cluster     → flat cluster-assignment array (ndarray, shape (n,))
    dendrogram      → dict {icoord, dcoord, ivl, leaves, color_list}
    cophenet        → float c (coefficient) or dict {c, d} when Y supplied
    inconsistent    → inconsistency array (ndarray, shape (n-1, 4))

Vector quantisation (``scipy.cluster.vq``):
    k_means2         → dict {centroid, label}
    k_means          → dict {codebook, distortion}
    vector_quantize  → dict {code, dist}
    whiten          → normalised observation array (ndarray)

Helper:
    result_get(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


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


# ── linkage ───────────────────────────────────────────────────────────────

linkage = _pred("linkage",
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


# ── flat_cluster ───────────────────────────────────────────────────────────

flat_cluster = _pred("flat_cluster",
    (3, _dispatch_fn(lambda z, t:
        _hier().fcluster(z, t))),
    (4, _dispatch_fn(lambda z, t, criterion:
        _hier().fcluster(z, t, criterion=criterion))),
    (5, _dispatch_fn(lambda z, t, criterion, depth:
        _hier().fcluster(z, t, criterion=criterion, depth=depth))),
)


# ── dendrogram ────────────────────────────────────────────────────────────

def _dendrogram_result(z, **kwargs):
    result = _hier().dendrogram(z, no_plot=True, **kwargs)
    return {
        'icoord': result['icoord'],
        'dcoord': result['dcoord'],
        'ivl': result['ivl'],
        'leaves': result['leaves'],
        'color_list': result['color_list'],
    }


dendrogram = _pred("dendrogram",
    (2, _dispatch_fn(lambda z:
        _dendrogram_result(z))),
    (3, _dispatch_fn(lambda z, truncate_mode:
        _dendrogram_result(z, truncate_mode=truncate_mode))),
)


# ── cophenet ──────────────────────────────────────────────────────────────

def _cophenet_with_y(z, y):
    c, d = _hier().cophenet(z, y)
    return {'c': float(c), 'd': d}


cophenet = _pred("cophenet",
    # Without Y: returns the cophenetic distance array (condensed form)
    (2, _dispatch_fn(lambda z:
        _hier().cophenet(z))),
    # With Y: returns dict {'c': correlation coefficient, 'd': distances}
    (3, _dispatch_fn(_cophenet_with_y)),
)


# ── inconsistent ──────────────────────────────────────────────────────────

inconsistent = _pred("inconsistent",
    (2, _dispatch_fn(lambda z:
        _hier().inconsistent(z))),
    (3, _dispatch_fn(lambda z, depth:
        _hier().inconsistent(z, d=depth))),
)


# ── k_means2 ───────────────────────────────────────────────────────────────

def _kmeans2_result(data, k, **kwargs):
    centroid, label = _vq().kmeans2(data, k, **kwargs)
    return {'centroid': centroid, 'label': label}


k_means2 = _pred("k_means2",
    (3, _dispatch_fn(lambda data, k:
        _kmeans2_result(data, k))),
    (4, _dispatch_fn(lambda data, k, iterations:
        _kmeans2_result(data, k, iter=iterations))),
    (5, _dispatch_fn(lambda data, k, iterations, seed:
        _kmeans2_result(data, k, iter=iterations, seed=seed))),
)


# ── k_means ────────────────────────────────────────────────────────────────

def _kmeans_result(obs, k, **kwargs):
    codebook, distortion = _vq().kmeans(obs, k, **kwargs)
    return {'codebook': codebook, 'distortion': float(distortion)}


k_means = _pred("k_means",
    (3, _dispatch_fn(lambda obs, k:
        _kmeans_result(obs, k))),
    (4, _dispatch_fn(lambda obs, k, iterations:
        _kmeans_result(obs, k, iter=iterations))),
)


# ── vector_quantize ────────────────────────────────────────────────────────

def _vq_result(obs, code_book):
    code, dist = _vq().vq(obs, code_book)
    return {'code': code, 'dist': dist}


vector_quantize = _pred("vector_quantize",
    (3, _dispatch_fn(_vq_result)),
)


# ── whiten ────────────────────────────────────────────────────────────────

whiten = _pred("whiten",
    (2, _dispatch_fn(lambda obs:
        _vq().whiten(obs))),
)


# ── Helper: result_get ─────────────────────────────────────────────────────

class _ResultGetPredicate:
    """result_get(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE.

    RESULT must be a dict.
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
