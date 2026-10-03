"""clausal.modules.py.scipy_differentiate — scipy.differentiate predicates for Clausal.

Provides numerical differentiation from ``scipy.differentiate`` as
importable predicate objects for use in .clausal files via::

    -import_from(scipy_differentiate, [derivative, jacobian, hessian, result_get])

All predicates are **Tier 2 — result-record**: they return a dict with
fields that can be accessed via ``result_get``.

Predicate catalogue
-------------------
    derivative(F, X, RESULT)              — scalar derivative at X
    derivative(F, X, ARGS, RESULT)        — derivative with extra function args
    jacobian(F, X, RESULT)               — jacobian matrix at X
    hessian(F, X, RESULT)                — hessian matrix at X

Result dict fields
------------------
    derivative / jacobian result:
        'x'        — evaluation point (echo of input X)
        'df'       — derivative or jacobian value
        'error'    — estimated error
        'success'  — bool (or bool array for jacobian/hessian)
        'status'   — integer status code
        'nfev'     — number of function evaluations
        'nit'      — number of iterations

    hessian result:
        'x'        — evaluation point
        'ddf'      — hessian matrix
        'error'    — estimated error
        'success'  — bool array
        'status'   — integer status code
        'nfev'     — number of function evaluations
        'nit'      — number of iterations

Helper:
    result_get(RESULT, FIELD, VALUE)  — extract RESULT[FIELD] → VALUE
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate
from clausal.terms import Quantity, UnitsMismatch
from clausal.modules.py._scipy_units import (
    strip_quantity, quantity_dims, merge_dims, wrap_result,
    probe_function_units, _SCIPY_UNITS_ENABLED,
)


# ── Lazy scipy.differentiate import ───────────────────────────────────────

_scipy_differentiate = None
_differentiate_lock = _threading.Lock()


def _ensure_differentiate():
    global _scipy_differentiate
    if _scipy_differentiate is not None:
        return
    with _differentiate_lock:
        if _scipy_differentiate is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_differentiate = _import_stdlib("scipy.differentiate")


def _diff():
    _ensure_differentiate()
    return _scipy_differentiate


# ── Result conversion ──────────────────────────────────────────────────────

def _rich_result_to_dict(r, output_key: str) -> dict:
    """Convert a scipy _RichResult to a plain dict with all available fields."""
    # The set of available fields varies by function (derivative has 'x' and
    # 'nit'; jacobian and hessian do not).  Build the dict dynamically.
    candidate_fields = ("x", output_key, "error", "success", "status", "nfev", "nit")
    result = {}
    for field in candidate_fields:
        try:
            value = getattr(r, field)
        except AttributeError:
            continue
        # A scalar call gives NumPy scalars (np.True_, np.int32(...)): hand
        # them back as the Python bool/int/float they stand for, so a goal
        # like ``OK == True`` compares them.  Arrays are left alone.
        if hasattr(value, "item") and getattr(value, "ndim", None) == 0:
            value = value.item()
        result[field] = value
    return result


# ── Dispatch function factory ──────────────────────────────────────────────

def _dispatch_fn(call: Callable, output_key: str) -> Callable:
    """Trampoline dispatch: call scipy function, convert result to dict, unify."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            raw = call(*inputs)
            out = _rich_result_to_dict(raw, output_key)
        except UnitsMismatch:
            raise
        except Exception:
            yield (_fail, DONE)
            return
        ok = bool(unify(result_var, out, trail))
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _pred(name: str, *arity_fns) -> ModulePredicate:
    p = ModulePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── Quantity-aware call wrappers ───────────────────────────────────────────

def _safe_probe(f, x_quantity):
    """Probe f with a Quantity; return (f_dims, True) or (None, False) on failure.

    Returns ``(dims_dict, True)`` when *f* accepts a Quantity and returns one,
    ``(None, True)`` when *f* accepts a Quantity but returns a plain value, and
    ``(None, False)`` when *f* cannot handle a Quantity input at all (e.g. it
    tries to index into the Quantity object).
    """
    try:
        f_dims = probe_function_units(f, x_quantity)
        return f_dims, True
    except Exception:
        return None, False


def _make_f_stripped(f, x_dims, f_accepts_quantity):
    """Build a function that scipy can call with raw values.

    If *f* accepts Quantity objects, wraps the raw value in a Quantity before
    calling *f* and strips the result.  Otherwise, passes the raw value
    directly.
    """
    if f_accepts_quantity and x_dims:
        def f_stripped(v):
            return strip_quantity(f(Quantity(v, x_dims)))
        return f_stripped
    return f


def _derivative_quantity_call(f, x):
    """Handle Quantity x for derivative: probe f, strip, call scipy, wrap result."""
    if not isinstance(x, Quantity):
        return _diff().derivative(f, x)
    x_dims = dict(x.dims)
    f_dims, f_accepts_q = _safe_probe(f, x)
    f_for_scipy = _make_f_stripped(f, x_dims, f_accepts_q)
    raw = _diff().derivative(f_for_scipy, x.value)
    result = _rich_result_to_dict(raw, 'df')
    if x_dims:
        result['x'] = wrap_result(result['x'], x_dims)
    if f_dims is not None:
        df_dims = merge_dims(f_dims, x_dims, -1)
        result['df']    = wrap_result(result['df'],    df_dims)
        result['error'] = wrap_result(result['error'], df_dims)
    return result


def _derivative_quantity_call_args(f, x, args):
    """Handle Quantity x for derivative with extra args."""
    if not isinstance(x, Quantity):
        return _diff().derivative(f, x, args=tuple(args))
    x_dims = dict(x.dims)
    f_with_args = lambda v: f(v, *args)
    f_dims, f_accepts_q = _safe_probe(f_with_args, x)
    if f_accepts_q and x_dims:
        def f_stripped(v, *a):
            return strip_quantity(f(Quantity(v, x_dims), *a))
    else:
        f_stripped = f
    raw = _diff().derivative(f_stripped, x.value, args=tuple(args))
    result = _rich_result_to_dict(raw, 'df')
    if x_dims:
        result['x'] = wrap_result(result['x'], x_dims)
    if f_dims is not None:
        df_dims = merge_dims(f_dims, x_dims, -1)
        result['df']    = wrap_result(result['df'],    df_dims)
        result['error'] = wrap_result(result['error'], df_dims)
    return result


def _jacobian_quantity_call(f, x):
    """Handle Quantity x for jacobian: probe f, strip, call scipy, wrap result."""
    if not isinstance(x, Quantity):
        return _diff().jacobian(f, x)
    x_dims = dict(x.dims)
    f_dims, f_accepts_q = _safe_probe(f, x)
    f_for_scipy = _make_f_stripped(f, x_dims, f_accepts_q)
    raw = _diff().jacobian(f_for_scipy, x.value)
    result = _rich_result_to_dict(raw, 'df')
    if x_dims and 'x' in result:
        result['x'] = wrap_result(result['x'], x_dims)
    if f_dims is not None:
        df_dims = merge_dims(f_dims, x_dims, -1)
        result['df']    = wrap_result(result['df'],    df_dims)
        if 'error' in result:
            result['error'] = wrap_result(result['error'], df_dims)
    return result


def _hessian_quantity_call(f, x):
    """Handle Quantity x for hessian: probe f, strip, call scipy, wrap result."""
    if not isinstance(x, Quantity):
        return _diff().hessian(f, x)
    x_dims = dict(x.dims)
    f_dims, f_accepts_q = _safe_probe(f, x)
    f_for_scipy = _make_f_stripped(f, x_dims, f_accepts_q)
    raw = _diff().hessian(f_for_scipy, x.value)
    result = _rich_result_to_dict(raw, 'ddf')
    if x_dims and 'x' in result:
        result['x'] = wrap_result(result['x'], x_dims)
    if f_dims is not None:
        # hessian: second derivative → f_dims − 2·x_dims
        ddf_dims = merge_dims(f_dims, x_dims, -2)
        result['ddf']   = wrap_result(result['ddf'],   ddf_dims)
        if 'error' in result:
            result['error'] = wrap_result(result['error'], ddf_dims)
    return result


# ── Dispatch wrapper for quantity-aware calls ─────────────────────────────

def _dispatch_fn_quantity(call: Callable, output_key: str) -> Callable:
    """Like _dispatch_fn but for calls that return a dict directly (quantity path)."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = call(*inputs)
            if type(out) is not dict:
                # Plain scipy result object -- convert to dict.  (scipy's
                # _RichResult SUBCLASSES dict, so isinstance would wrongly
                # pass it through unconverted, NumPy scalars and all.)
                out = _rich_result_to_dict(out, output_key)
        except UnitsMismatch:
            raise
        except Exception:
            yield (_fail, DONE)
            return
        ok = bool(unify(result_var, out, trail))
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


# ── derivative ─────────────────────────────────────────────────────────────

derivative = _pred("derivative",
    (3, _dispatch_fn_quantity(_derivative_quantity_call, "df")),
    (4, _dispatch_fn_quantity(_derivative_quantity_call_args, "df")),
)


# ── jacobian ───────────────────────────────────────────────────────────────

jacobian = _pred("jacobian",
    (3, _dispatch_fn_quantity(_jacobian_quantity_call, "df")),
)


# ── hessian ────────────────────────────────────────────────────────────────

hessian = _pred("hessian",
    (3, _dispatch_fn_quantity(_hessian_quantity_call, "ddf")),
)


# ── result_get ─────────────────────────────────────────────────────────────

def _result_get_dispatch(this_generator, _proceed, _fail, _catcher, result, field, value, trail):
    result = deref(result)
    field = deref(field)
    value_var = value
    try:
        out = result[field]
    except (KeyError, TypeError):
        yield (_fail, DONE)
        return
    ok = bool(unify(value_var, out, trail))
    if ok:
        yield (_proceed, None)
    yield (_fail, DONE)


class _ResultGetPredicate:
    """Access a named field from a differentiate result dict."""

    def _get_dispatch(self) -> Callable:
        return _result_get_dispatch

    def __repr__(self) -> str:
        return "scipy.differentiate.result_get/3"


result_get = _ResultGetPredicate()
