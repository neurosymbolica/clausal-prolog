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


# ── Predicate adapter ─────────────────────────────────────────────────────

class _SciPyIntegratePredicate:
    """Dispatch adapter for a scipy.integrate predicate.

    Supports multiple arities via ``_register(arity, fn)``.
    Arity counts include RESULT but not trail.
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> "_SciPyIntegratePredicate":
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
        return f"scipy.integrate.{self._name}/{arities}"


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


def _pred(name: str, *arity_fns) -> _SciPyIntegratePredicate:
    """Create a ``_SciPyIntegratePredicate`` from (arity, dispatch_fn) pairs."""
    p = _SciPyIntegratePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── Quad ──────────────────────────────────────────────────────────────────

def _quad_result(func, a, b, **kwargs):
    r = _integrate().quad(func, a, b, **kwargs)
    result = {'value': r[0], 'error': r[1]}
    if len(r) > 2:
        result['infodict'] = r[2]
    return result


Quad = _pred("Quad",
    (4, _dispatch_fn(lambda func, a, b:
        _quad_result(func, a, b))),
    (5, _dispatch_fn(lambda func, a, b, args:
        _quad_result(func, a, b, args=args))),
    (8, _dispatch_fn(lambda func, a, b, args, limit, epsabs, epsrel:
        _quad_result(func, a, b, args=args, limit=limit, epsabs=epsabs, epsrel=epsrel))),
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
    y, err, info = _integrate().quad_vec(func, a, b, full_output=True)
    return {
        'y': y,
        'err': err,
        'status': info.status,
        'success': info.success,
        'message': info.message,
        'neval': info.neval,
    }


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

CumulativeTrapezoid = _pred("CumulativeTrapezoid",
    (2, _dispatch_fn(lambda y:
        _integrate().cumulative_trapezoid(y))),
    (3, _dispatch_fn(lambda y, x:
        _integrate().cumulative_trapezoid(y, x=x))),
)


# ── Trapezoid ─────────────────────────────────────────────────────────────

Trapezoid = _pred("Trapezoid",
    (2, _dispatch_fn(lambda y:
        _integrate().trapezoid(y))),
    (3, _dispatch_fn(lambda y, x:
        _integrate().trapezoid(y, x=x))),
)


# ── Simpson ───────────────────────────────────────────────────────────────

Simpson = _pred("Simpson",
    (2, _dispatch_fn(lambda y:
        _integrate().simpson(y))),
    (3, _dispatch_fn(lambda y, x:
        _integrate().simpson(y, x=x))),
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
