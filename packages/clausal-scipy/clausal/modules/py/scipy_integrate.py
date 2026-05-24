"""clausal.modules.py.scipy_integrate — scipy.integrate predicates for Clausal.

Provides numerical integration routines from scipy.integrate as importable
predicate objects for use in .clausal files via::

    -import_from(scipy_integrate, [Quad, Trapezoid, SolveInitialValueProblem, ResultGet, ...])

Tiers
-----
- **Tier 1** (direct value in RESULT):
    CumulativeTrapezoid  → array
    Trapezoid            → scalar or array
    Simpson              → scalar or array

- **Tier 2** (returns result dict; use ResultGet to access fields):
    Quad                 → dict {value, error}
    DoubleQuad           → dict {value, error}
    TripleQuad           → dict {value, error}
    NQuad                → dict {value, error}
    QuadVec              → dict {y, err, status, success, message, neval}
    SolveInitialValueProblem → dict {t, y, sol, t_events, y_events, nfev, njev, nlu,
                                      status, message, success}
    OdeIntegrate         → dict {y} or {y, infodict}

Helper:
    ResultGet(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE
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
    make_quantity_aware, probe_function_units,
    PASS_THROUGH_FIRST, STRIP_TO_PLAIN,
)


# ── Lazy scipy.integrate import ───────────────────────────────────────────

_scipy_integrate = None
_int_lock = _threading.Lock()


def _ensure_integrate():
    global _scipy_integrate
    if _scipy_integrate is not None:
        return
    with _int_lock:
        if _scipy_integrate is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_integrate = _import_stdlib("scipy.integrate")


def _integrate():
    _ensure_integrate()
    return _scipy_integrate


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
        except UnitsMismatch:
            raise
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


# ── Quantity-aware helpers (Phase 4) ──────────────────────────────────────

def _safe_probe(f, x_quantity):
    """Probe f with a Quantity; return (f_dims, True) or (None, False) on failure."""
    try:
        f_dims = probe_function_units(f, x_quantity)
        return f_dims, True
    except Exception:
        return None, False


def _make_f_stripped(f, x_dims, f_accepts_quantity):
    """Build a function that scipy can call with raw values."""
    if f_accepts_quantity and x_dims:
        def f_stripped(v):
            return strip_quantity(f(Quantity(v, x_dims)))
        return f_stripped
    return f


def _array_integrate_units(y, x):
    """Compute output dims for array-based quadrature: y_dims + x_dims."""
    has_q = isinstance(y, Quantity) or isinstance(x, Quantity)
    if not has_q:
        return None, strip_quantity(y), strip_quantity(x)
    y_dims = quantity_dims(y) or {}
    x_dims = quantity_dims(x) or {}
    out_dims = merge_dims(y_dims, x_dims, +1)
    return out_dims, strip_quantity(y), strip_quantity(x)


# ── Quad ──────────────────────────────────────────────────────────────────

def _quad_result(func, a, b, **kwargs):
    r = _integrate().quad(func, a, b, **kwargs)
    result = {'value': r[0], 'error': r[1]}
    if len(r) > 2:
        result['infodict'] = r[2]
    return result


def _quad_quantity_call(func, a, b, **kwargs):
    """Quantity-aware Quad: probe func, wrap bounds, wrap result."""
    if not isinstance(a, Quantity) and not isinstance(b, Quantity):
        return _quad_result(func, a, b, **kwargs)
    x_dims = quantity_dims(a) or quantity_dims(b) or {}
    # Probe f to discover output dims
    a_q = a if isinstance(a, Quantity) else Quantity(a, x_dims)
    f_dims, f_accepts_q = _safe_probe(func, a_q)
    f_for_scipy = _make_f_stripped(func, x_dims, f_accepts_q)
    r = _integrate().quad(f_for_scipy, strip_quantity(a), strip_quantity(b), **kwargs)
    result = {'value': r[0], 'error': r[1]}
    if len(r) > 2:
        result['infodict'] = r[2]
    if f_dims is not None:
        out_dims = merge_dims(f_dims, x_dims, +1)
        result['value'] = wrap_result(result['value'], out_dims)
        result['error'] = wrap_result(result['error'], out_dims)
    return result


Quad = _pred("Quad",
    (4, _dispatch_fn(lambda func, a, b:
        _quad_quantity_call(func, a, b))),
    (5, _dispatch_fn(lambda func, a, b, args:
        _quad_quantity_call(func, a, b, args=args))),
    (8, _dispatch_fn(lambda func, a, b, args, limit, epsabs, epsrel:
        _quad_quantity_call(func, a, b, args=args, limit=limit, epsabs=epsabs, epsrel=epsrel))),
)


# ── DoubleQuad ────────────────────────────────────────────────────────────

def _dblquad_result(func, a, b, gfun, hfun, **kwargs):
    r = _integrate().dblquad(func, a, b, gfun, hfun, **kwargs)
    return {'value': r[0], 'error': r[1]}


DoubleQuad = _pred("DoubleQuad",
    (6, _dispatch_fn(lambda func, a, b, gfun, hfun:
        _dblquad_result(func, a, b, gfun, hfun))),
    (8, _dispatch_fn(lambda func, a, b, gfun, hfun, epsabs, epsrel:
        _dblquad_result(func, a, b, gfun, hfun, epsabs=epsabs, epsrel=epsrel))),
)


# ── TripleQuad ────────────────────────────────────────────────────────────

def _tplquad_result(func, a, b, gfun, hfun, qfun, rfun, **kwargs):
    r = _integrate().tplquad(func, a, b, gfun, hfun, qfun, rfun, **kwargs)
    return {'value': r[0], 'error': r[1]}


TripleQuad = _pred("TripleQuad",
    (8, _dispatch_fn(lambda func, a, b, gfun, hfun, qfun, rfun:
        _tplquad_result(func, a, b, gfun, hfun, qfun, rfun))),
)


# ── NQuad ─────────────────────────────────────────────────────────────────

def _nquad_result(func, ranges, **kwargs):
    r = _integrate().nquad(func, ranges, **kwargs)
    result = {'value': r[0], 'error': r[1]}
    if len(r) > 2:
        result['out_dict'] = r[2]
    return result


NQuad = _pred("NQuad",
    (3, _dispatch_fn(lambda func, ranges:
        _nquad_result(func, ranges))),
    (4, _dispatch_fn(lambda func, ranges, args:
        _nquad_result(func, ranges, args=args))),
)


# ── QuadVec ───────────────────────────────────────────────────────────────

def _quad_vec_result(func, a, b):
    if not isinstance(a, Quantity) and not isinstance(b, Quantity):
        y, err, info = _integrate().quad_vec(func, a, b, full_output=True)
        return {
            'y': y, 'err': err, 'status': info.status,
            'success': info.success, 'message': info.message, 'neval': info.neval,
        }
    x_dims = quantity_dims(a) or quantity_dims(b) or {}
    a_q = a if isinstance(a, Quantity) else Quantity(a, x_dims)
    f_dims, f_accepts_q = _safe_probe(func, a_q)
    f_for_scipy = _make_f_stripped(func, x_dims, f_accepts_q)
    y, err, info = _integrate().quad_vec(
        f_for_scipy, strip_quantity(a), strip_quantity(b), full_output=True)
    result = {
        'y': y, 'err': err, 'status': info.status,
        'success': info.success, 'message': info.message, 'neval': info.neval,
    }
    if f_dims is not None:
        out_dims = merge_dims(f_dims, x_dims, +1)
        result['y'] = wrap_result(result['y'], out_dims)
        result['err'] = wrap_result(result['err'], out_dims)
    return result


QuadVec = _pred("QuadVec",
    (4, _dispatch_fn(lambda func, a, b:
        _quad_vec_result(func, a, b))),
)


# ── SolveInitialValueProblem ──────────────────────────────────────────────

def _solve_ivp_result(fun, t_span, y0, **kwargs):
    sol = _integrate().solve_ivp(fun, t_span, y0, **kwargs)
    return {
        't': sol.t,
        'y': sol.y,
        'sol': sol.sol,
        't_events': sol.t_events,
        'y_events': sol.y_events,
        'nfev': sol.nfev,
        'njev': sol.njev,
        'nlu': sol.nlu,
        'status': sol.status,
        'message': sol.message,
        'success': sol.success,
    }


SolveInitialValueProblem = _pred("SolveInitialValueProblem",
    (4, _dispatch_fn(lambda fun, t_span, y0:
        _solve_ivp_result(fun, t_span, y0))),
    (5, _dispatch_fn(lambda fun, t_span, y0, method:
        _solve_ivp_result(fun, t_span, y0, method=method))),
    (6, _dispatch_fn(lambda fun, t_span, y0, method, t_eval:
        _solve_ivp_result(fun, t_span, y0, method=method, t_eval=t_eval))),
)


# ── OdeIntegrate ──────────────────────────────────────────────────────────

def _odeint_result(func, y0, t, **kwargs):
    result = _integrate().odeint(func, y0, t, full_output=False, **kwargs)
    if isinstance(result, tuple):
        arr, info = result
        return {'y': arr, 'infodict': info}
    return {'y': result}


def _odeint_result_full(func, y0, t, args):
    arr, info = _integrate().odeint(func, y0, t, args=args, full_output=True)
    return {'y': arr, 'infodict': info}


OdeIntegrate = _pred("OdeIntegrate",
    (4, _dispatch_fn(lambda func, y0, t:
        _odeint_result(func, y0, t))),
    (5, _dispatch_fn(lambda func, y0, t, args:
        _odeint_result(func, y0, t, args=args))),
)


# ── CumulativeTrapezoid ───────────────────────────────────────────────────

def _cumtrap_quantity(y, x=None):
    if x is not None:
        out_dims, y_val, x_val = _array_integrate_units(y, x)
        result = _integrate().cumulative_trapezoid(y_val, x=x_val)
    else:
        if isinstance(y, Quantity):
            out_dims = quantity_dims(y) or {}
            result = _integrate().cumulative_trapezoid(strip_quantity(y))
        else:
            return _integrate().cumulative_trapezoid(y)
    return wrap_result(result, out_dims) if out_dims else result


CumulativeTrapezoid = _pred("CumulativeTrapezoid",
    (2, _dispatch_fn(lambda y:
        _cumtrap_quantity(y))),
    (3, _dispatch_fn(lambda y, x:
        _cumtrap_quantity(y, x))),
)


# ── Trapezoid ─────────────────────────────────────────────────────────────

def _trapezoid_quantity(y, x=None):
    if x is not None:
        out_dims, y_val, x_val = _array_integrate_units(y, x)
        result = _integrate().trapezoid(y_val, x=x_val)
    else:
        if isinstance(y, Quantity):
            out_dims = quantity_dims(y) or {}
            result = _integrate().trapezoid(strip_quantity(y))
        else:
            return _integrate().trapezoid(y)
    return wrap_result(result, out_dims) if out_dims else result


Trapezoid = _pred("Trapezoid",
    (2, _dispatch_fn(lambda y:
        _trapezoid_quantity(y))),
    (3, _dispatch_fn(lambda y, x:
        _trapezoid_quantity(y, x))),
)


# ── Simpson ───────────────────────────────────────────────────────────────

def _simpson_quantity(y, x=None):
    if x is not None:
        out_dims, y_val, x_val = _array_integrate_units(y, x)
        result = _integrate().simpson(y_val, x=x_val)
    else:
        if isinstance(y, Quantity):
            out_dims = quantity_dims(y) or {}
            result = _integrate().simpson(strip_quantity(y))
        else:
            return _integrate().simpson(y)
    return wrap_result(result, out_dims) if out_dims else result


Simpson = _pred("Simpson",
    (2, _dispatch_fn(lambda y:
        _simpson_quantity(y))),
    (3, _dispatch_fn(lambda y, x:
        _simpson_quantity(y, x))),
)


# ── Helper: ResultGet ─────────────────────────────────────────────────────

class _ResultGetPredicate:
    """ResultGet(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE.

    RESULT must be a dict (or dict-like).
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
        return "ResultGet/3"


ResultGet = _ResultGetPredicate()
