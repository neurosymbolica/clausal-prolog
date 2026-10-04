"""clausal.modules.py.scipy_optimize — scipy.optimize predicates for Clausal.

Provides optimisation routines from scipy.optimize as importable predicate
objects for use in .clausal files via::

    -import_from(py.scipy_optimize, [minimize, minimize_scalar, result_get, ...])

Tiers
-----
- **Tier 1**: linear_constraint, bounds (helper object constructors)
- **Tier 2** (returns result dict; use result_get to access fields):
    minimize_scalar     → dict {x, fun, success, message, nit, nfev}
    minimize           → dict {x, fun, jac, nfev, njev, nit, success, status, message}
    differential_evolution → dict {x, fun, success, message, ...}
    basin_hopping       → dict {x, fun, message, ...}
    dual_annealing      → dict {x, fun, success, message, ...}
    shgo_minimize       → dict {x, fun, success, message, ...}
    nonlinear_least_squares → dict {x, cost, fun, jac, ...}
    curve_fit           → dict {popt, pcov}
    root_scalar         → dict {root, iterations, function_calls, converged, flag}
                          (flag: a STRING, e.g. "converged")
    root               → dict {x, fun, fjac, nfev, success, message}

Helper:
    result_get(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.modules.py._helpers import _text_arg
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate, text_result


# ── Lazy scipy.optimize import ────────────────────────────────────────────

_scipy_optimize = None
_opt_lock = _threading.Lock()


def _ensure_opt():
    global _scipy_optimize
    if _scipy_optimize is not None:
        return
    with _opt_lock:
        if _scipy_optimize is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_optimize = _import_stdlib("scipy.optimize")


def _opt():
    _ensure_opt()
    return _scipy_optimize


# ── Dispatch function factory ─────────────────────────────────────────────

def _dispatch_fn(call: Callable) -> Callable:
    """Trampoline dispatch: inputs → result → unify RESULT."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        # args: (input_0, ..., input_{n-1}, result, trail)
        trail = args[-1]
        result_var = args[-2]
        inputs = [_text_arg(x) for x in args[:-2]]
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


# ── minimize_scalar ────────────────────────────────────────────────────────

minimize_scalar = _pred("minimize_scalar",
    (2, _dispatch_fn(lambda fun:
        _opt().minimize_scalar(fun))),
    (3, _dispatch_fn(lambda fun, method:
        _opt().minimize_scalar(fun, method=method))),
    (4, _dispatch_fn(lambda fun, method, bounds:
        _opt().minimize_scalar(fun, method=method, bounds=bounds))),
)


# ── minimize ──────────────────────────────────────────────────────────────

minimize = _pred("minimize",
    (3, _dispatch_fn(lambda fun, x0:
        _opt().minimize(fun, x0))),
    (4, _dispatch_fn(lambda fun, x0, method:
        _opt().minimize(fun, x0, method=method))),
    (5, _dispatch_fn(lambda fun, x0, method, options:
        _opt().minimize(fun, x0, method=method, options=options))),
)


# ── differential_evolution ─────────────────────────────────────────────────

differential_evolution = _pred("differential_evolution",
    (3, _dispatch_fn(lambda func, bounds:
        _opt().differential_evolution(func, bounds))),
    (4, _dispatch_fn(lambda func, bounds, seed:
        _opt().differential_evolution(func, bounds, seed=seed))),
)


# ── basin_hopping ──────────────────────────────────────────────────────────

basin_hopping = _pred("basin_hopping",
    (3, _dispatch_fn(lambda func, x0:
        _opt().basinhopping(func, x0))),
    (4, _dispatch_fn(lambda func, x0, iterations:
        _opt().basinhopping(func, x0, niter=iterations))),
)


# ── dual_annealing ─────────────────────────────────────────────────────────

dual_annealing = _pred("dual_annealing",
    (3, _dispatch_fn(lambda func, bounds:
        _opt().dual_annealing(func, bounds))),
    (4, _dispatch_fn(lambda func, bounds, seed:
        _opt().dual_annealing(func, bounds, seed=seed))),
)


# ── shgo_minimize ──────────────────────────────────────────────────────────

shgo_minimize = _pred("shgo_minimize",
    (3, _dispatch_fn(lambda func, bounds:
        _opt().shgo(func, bounds))),
)


# ── nonlinear_least_squares ─────────────────────────────────────────────────

nonlinear_least_squares = _pred("nonlinear_least_squares",
    (3, _dispatch_fn(lambda fun, x0:
        _opt().least_squares(fun, x0))),
    (4, _dispatch_fn(lambda fun, x0, bounds:
        _opt().least_squares(fun, x0, bounds=bounds))),
)


# ── curve_fit ──────────────────────────────────────────────────────────────

def _curve_fit_2(f, xdata, ydata):
    popt, pcov = _opt().curve_fit(f, xdata, ydata)
    return {'popt': popt, 'pcov': pcov}


def _curve_fit_3(f, xdata, ydata, p0):
    popt, pcov = _opt().curve_fit(f, xdata, ydata, p0=p0)
    return {'popt': popt, 'pcov': pcov}


curve_fit = _pred("curve_fit",
    (4, _dispatch_fn(_curve_fit_2)),
    (5, _dispatch_fn(_curve_fit_3)),
)


# ── root_scalar ────────────────────────────────────────────────────────────

def _root_scalar_result(r):
    # ``flag`` is SciPy's free-form status message ("converged"), so it is a
    # string ('$chars', s), like an optimizer's message (ruled 2026-10-04).
    return {
        'root': r.root,
        'iterations': r.iterations,
        'function_calls': r.function_calls,
        'converged': r.converged,
        'flag': text_result(r.flag),
    }


root_scalar = _pred("root_scalar",
    (2, _dispatch_fn(lambda f:
        _root_scalar_result(_opt().root_scalar(f)))),
    (3, _dispatch_fn(lambda f, method:
        _root_scalar_result(_opt().root_scalar(f, method=method)))),
    (4, _dispatch_fn(lambda f, method, bracket:
        _root_scalar_result(_opt().root_scalar(f, method=method, bracket=bracket)))),
    (5, _dispatch_fn(lambda f, method, x0, x1:
        _root_scalar_result(_opt().root_scalar(f, method=method, x0=x0, x1=x1)))),
)


# ── root ──────────────────────────────────────────────────────────────────

root = _pred("root",
    (3, _dispatch_fn(lambda fun, x0:
        _opt().root(fun, x0))),
    (4, _dispatch_fn(lambda fun, x0, method:
        _opt().root(fun, x0, method=method))),
)


# ── linear_program ─────────────────────────────────────────────────────────

linear_program = _pred("linear_program",
    (2, _dispatch_fn(lambda c:
        _opt().linprog(c))),
    (4, _dispatch_fn(lambda c, a_ub, b_ub:
        _opt().linprog(c, A_ub=a_ub, b_ub=b_ub))),
    (6, _dispatch_fn(lambda c, a_ub, b_ub, a_eq, b_eq:
        _opt().linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq))),
    (7, _dispatch_fn(lambda c, a_ub, b_ub, a_eq, b_eq, bounds:
        _opt().linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds))),
)


# ── mixed_integer_linear_program ─────────────────────────────────────────────

mixed_integer_linear_program = _pred("mixed_integer_linear_program",
    (2, _dispatch_fn(lambda c:
        _opt().milp(c))),
    (5, _dispatch_fn(lambda c, constraints, integrality, bounds:
        _opt().milp(c, constraints=constraints, integrality=integrality, bounds=bounds))),
)


# ── linear_constraint ──────────────────────────────────────────────────────

linear_constraint = _pred("linear_constraint",
    (4, _dispatch_fn(lambda a, lb, ub:
        _opt().LinearConstraint(a, lb=lb, ub=ub))),
)


# ── bounds ────────────────────────────────────────────────────────────────

bounds = _pred("bounds",
    (3, _dispatch_fn(lambda lb, ub:
        _opt().Bounds(lb=lb, ub=ub))),
)


# ── Helper: result_get ─────────────────────────────────────────────────────

class _ResultGetPredicate:
    """result_get(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE.

    RESULT must be a dict (or dict-like, e.g. OptimizeResult).
    FIELD must be a ground key, an atom or a string.
    VALUE is unified with the retrieved value.  The ``message`` field is
    free-form text, so it answers a string ``('$chars', s)`` (a list of
    them for ``basin_hopping``), not an atom (ruled 2026-10-04).
    """

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, result, field, value, trail):
        result = deref(result)
        field = _text_arg(field)
        if not isinstance(field, str):
            yield (_fail, DONE)
            return
        try:
            val = result[field]
        except (KeyError, TypeError):
            yield (_fail, DONE)
            return
        if field == "message" and isinstance(val, (str, list)):
            val = text_result(val)
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
