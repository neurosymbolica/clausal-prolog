"""clausal.modules.py.scipy_differentiate — scipy.differentiate predicates for Clausal.

Provides numerical differentiation from ``scipy.differentiate`` as
importable predicate objects for use in .clausal files via::

    -import_from(scipy_differentiate, [Derivative, Jacobian, Hessian, ResultGet])

All predicates are **Tier 2 — result-record**: they return a dict with
fields that can be accessed via ``ResultGet``.

Predicate catalogue
-------------------
    Derivative(F, X, RESULT)              — scalar derivative at X
    Derivative(F, X, ARGS, RESULT)        — derivative with extra function args
    Jacobian(F, X, RESULT)               — Jacobian matrix at X
    Hessian(F, X, RESULT)                — Hessian matrix at X

Result dict fields
------------------
    Derivative / Jacobian result:
        'x'        — evaluation point (echo of input X)
        'df'       — derivative or Jacobian value
        'error'    — estimated error
        'success'  — bool (or bool array for Jacobian/Hessian)
        'status'   — integer status code
        'nfev'     — number of function evaluations
        'nit'      — number of iterations

    Hessian result:
        'x'        — evaluation point
        'ddf'      — Hessian matrix
        'error'    — estimated error
        'success'  — bool array
        'status'   — integer status code
        'nfev'     — number of function evaluations
        'nit'      — number of iterations

Helper:
    ResultGet(RESULT, FIELD, VALUE)  — extract RESULT[FIELD] → VALUE
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE


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
            result[field] = getattr(r, field)
        except AttributeError:
            pass
    return result


# ── Predicate adapter ──────────────────────────────────────────────────────

class _DifferentiatePredicate:
    """Dispatch adapter for a scipy.differentiate predicate.

    Supports multiple arities via ``_register(arity, fn)``.
    Arity counts include RESULT but not trail.
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> "_DifferentiatePredicate":
        self._dispatch_fns[arity] = fn
        return self

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"scipy.differentiate.{self._name}/{arities}"


# ── Dispatch function factory ──────────────────────────────────────────────

def _dispatch_fn(call: Callable, output_key: str) -> Callable:
    """Trampoline dispatch: call scipy function, convert result to dict, unify."""
    def dispatch(this_generator, parent, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            raw = call(*inputs)
            out = _rich_result_to_dict(raw, output_key)
        except Exception:
            yield (parent, DONE)
            return
        ok = bool(unify(result_var, out, trail))
        if ok:
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _pred(name: str, *arity_fns) -> _DifferentiatePredicate:
    p = _DifferentiatePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── Derivative ─────────────────────────────────────────────────────────────

Derivative = _pred("Derivative",
    (3, _dispatch_fn(
        lambda f, x: _diff().derivative(f, x),
        "df",
    )),
    (4, _dispatch_fn(
        lambda f, x, args: _diff().derivative(f, x, args=tuple(args)),
        "df",
    )),
)


# ── Jacobian ───────────────────────────────────────────────────────────────

Jacobian = _pred("Jacobian",
    (3, _dispatch_fn(
        lambda f, x: _diff().jacobian(f, x),
        "df",
    )),
)


# ── Hessian ────────────────────────────────────────────────────────────────

Hessian = _pred("Hessian",
    (3, _dispatch_fn(
        lambda f, x: _diff().hessian(f, x),
        "ddf",
    )),
)


# ── ResultGet ─────────────────────────────────────────────────────────────

def _result_get_dispatch(this_generator, parent, result, field, value, trail):
    result = deref(result)
    field = deref(field)
    value_var = value
    try:
        out = result[field]
    except (KeyError, TypeError):
        yield (parent, DONE)
        return
    ok = bool(unify(value_var, out, trail))
    if ok:
        yield (parent, None)
    yield (parent, DONE)


class _ResultGetPredicate:
    """Access a named field from a differentiate result dict."""

    def _get_dispatch(self) -> Callable:
        return _result_get_dispatch

    def __repr__(self) -> str:
        return "scipy.differentiate.ResultGet/3"


ResultGet = _ResultGetPredicate()
