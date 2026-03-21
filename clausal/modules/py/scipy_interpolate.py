"""clausal.modules.py.scipy_interpolate — scipy.interpolate predicates for Clausal.

Provides interpolation routines from scipy.interpolate as importable predicate
objects for use in .clausal files via::

    -import_from(scipy_interpolate, [MakeSpline, EvalSpline, Free, ...])

Or via the canonical ``py.*`` path::

    -import_from(py.scipy_interpolate, [MakeSpline, EvalSpline, ...])

Tiers
-----
All predicates are **Tier 3** (handle-based): stateful interpolator objects are
constructed with ``Make*`` predicates, which return an opaque integer
``HANDLE``.  The handle is passed to evaluation or query predicates.
``Free(HANDLE)`` releases the object from the registry.

Handle predicates
-----------------
Constructors — return an integer HANDLE:
    MakeSpline(X, Y, RESULT)
    MakeSpline(X, Y, K, RESULT)
    MakeSpline(X, Y, K, BC_TYPE, RESULT)
        → scipy.interpolate.make_interp_spline(x, y, k=K, bc_type=BC_TYPE)
        Recommended 1-D spline constructor; returns a BSpline object.

    MakeCubic(X, Y, RESULT)
    MakeCubic(X, Y, BC_TYPE, RESULT)
        → scipy.interpolate.CubicSpline(x, y, bc_type=BC_TYPE)

    MakePCHIP(X, Y, RESULT)
    MakePCHIP(X, Y, EXTRAPOLATE, RESULT)
        → scipy.interpolate.PchipInterpolator(x, y, extrapolate=EXTRAPOLATE)
        Monotone cubic; good for data with outliers.

    MakeAkima(X, Y, RESULT)
        → scipy.interpolate.Akima1DInterpolator(x, y)

    MakeLinear1D(X, Y, RESULT)
    MakeLinear1D(X, Y, KIND, RESULT)
        → scipy.interpolate.interp1d(x, y, kind=KIND)
        Supports: 'linear','nearest','nearest-up','zero','slinear',
                  'quadratic','cubic','previous','next'
        Note: deprecated in SciPy ≥ 1.14; prefer MakeSpline for new code.

    MakeRegularGrid(POINTS, VALUES, RESULT)
    MakeRegularGrid(POINTS, VALUES, METHOD, RESULT)
        → scipy.interpolate.RegularGridInterpolator(points, values, method=METHOD)
        N-D interpolation on a regular (rectilinear) grid.

    MakeRadialBasis(X, Y, RESULT)
    MakeRadialBasis(X, Y, FUNCTION, RESULT)
    MakeRadialBasis(X, Y, FUNCTION, SMOOTH, RESULT)
        → scipy.interpolate.RBFInterpolator(x, y, kernel=FUNCTION, smoothing=SMOOTH)

Evaluators — look up HANDLE and call the interpolator:
    EvalSpline(HANDLE, X, RESULT)
    EvalSpline(HANDLE, X, NU, RESULT)
        Evaluate spline (or its NU-th derivative) at points X.

    EvalRegularGrid(HANDLE, XI, RESULT)
    EvalRegularGrid(HANDLE, XI, METHOD, RESULT)

    EvalRadialBasis(HANDLE, X, RESULT)

Spline utilities (operate on BSpline/CubicSpline/Pchip/Akima handles):
    SplineIntegral(HANDLE, A, B, RESULT)
        Definite integral of the spline from A to B.

    SplineDerivative(HANDLE, RESULT)
    SplineDerivative(HANDLE, ORDER, RESULT)
        Returns a new HANDLE for the derivative spline.

    SplineRoots(HANDLE, RESULT)
        Returns the real roots (zero-crossings) of the spline as a list.

Lifecycle:
    Free(HANDLE)
        Release HANDLE from the registry.  Always succeeds.

Pipeline pattern::

    MakeSpline(Xs, Ys, 3, HANDLE),
    EvalSpline(HANDLE, NewXs, Values),
    SplineIntegral(HANDLE, 0.0, 10.0, Area),
    Free(HANDLE).
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE


# ── Lazy scipy.interpolate import ─────────────────────────────────────────

_scipy_interpolate = None
_interp_import_lock = _threading.Lock()


def _ensure_interpolate():
    global _scipy_interpolate
    if _scipy_interpolate is not None:
        return
    with _interp_import_lock:
        if _scipy_interpolate is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_interpolate = _import_stdlib("scipy.interpolate")


def _si():
    _ensure_interpolate()
    return _scipy_interpolate


# ── Handle registry ────────────────────────────────────────────────────────

_INTERP_REGISTRY: dict[int, object] = {}
_registry_lock = _threading.Lock()
_registry_counter = [0]


def _alloc_handle(obj: object) -> int:
    """Store *obj* in the registry and return its integer handle."""
    with _registry_lock:
        _registry_counter[0] += 1
        handle = _registry_counter[0]
        _INTERP_REGISTRY[handle] = obj
    return handle


def _lookup_handle(handle: int) -> object:
    """Return the object registered under *handle*, or raise KeyError."""
    obj = _INTERP_REGISTRY.get(handle)
    if obj is None:
        raise KeyError(f"Unknown interpolator handle: {handle!r}")
    return obj


# ── Predicate adapter ─────────────────────────────────────────────────────

class _SciPyInterpPredicate:
    """Base dispatch adapter for scipy.interpolate predicates.

    Subclasses override ``_get_dispatch`` / provide ``_dispatch``.
    Multi-arity predicates can register per-arity callables via ``_register``.
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> "_SciPyInterpPredicate":
        self._dispatch_fns[arity] = fn
        return self

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        # args: (input_0, ..., input_{n-1}, result, trail)
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"scipy.interpolate.{self._name}/{arities}"


# ── Shared dispatch helpers ────────────────────────────────────────────────

def _make_dispatch(constructor: Callable) -> Callable:
    """Dispatch fn: deref all inputs, call constructor, alloc handle, unify."""
    def dispatch(this_generator, parent, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            obj = constructor(*inputs)
            handle = _alloc_handle(obj)
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
    return dispatch


def _eval_dispatch(evaluator: Callable) -> Callable:
    """Dispatch fn: deref all inputs, call evaluator(obj, inputs...), unify."""
    def dispatch(this_generator, parent, *args):
        trail = args[-1]
        result_var = args[-2]
        raw_inputs = [deref(x) for x in args[:-2]]
        handle_val = raw_inputs[0]
        try:
            obj = _lookup_handle(int(handle_val))
            out = evaluator(obj, *raw_inputs[1:])
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


def _pred(name: str, *arity_fns) -> _SciPyInterpPredicate:
    """Create a ``_SciPyInterpPredicate`` from (arity, dispatch_fn) pairs."""
    p = _SciPyInterpPredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── MakeSpline ───────────────────────────────────────────────────────
# scipy.interpolate.make_interp_spline(x, y, k=3, bc_type=None)

MakeSpline = _pred("MakeSpline",
    (3, _make_dispatch(lambda x, y:
        _si().make_interp_spline(x, y))),
    (4, _make_dispatch(lambda x, y, k:
        _si().make_interp_spline(x, y, k=k))),
    (5, _make_dispatch(lambda x, y, k, bc_type:
        _si().make_interp_spline(x, y, k=k, bc_type=bc_type))),
)


# ── MakeCubic ────────────────────────────────────────────────────────
# scipy.interpolate.CubicSpline(x, y, bc_type=...)

MakeCubic = _pred("MakeCubic",
    (3, _make_dispatch(lambda x, y:
        _si().CubicSpline(x, y))),
    (4, _make_dispatch(lambda x, y, bc_type:
        _si().CubicSpline(x, y, bc_type=bc_type))),
)


# ── MakePCHIP ────────────────────────────────────────────────────────
# scipy.interpolate.PchipInterpolator(x, y, extrapolate=...)

MakePCHIP = _pred("MakePCHIP",
    (3, _make_dispatch(lambda x, y:
        _si().PchipInterpolator(x, y))),
    (4, _make_dispatch(lambda x, y, extrapolate:
        _si().PchipInterpolator(x, y, extrapolate=extrapolate))),
)


# ── MakeAkima ────────────────────────────────────────────────────────
# scipy.interpolate.Akima1DInterpolator(x, y)

MakeAkima = _pred("MakeAkima",
    (3, _make_dispatch(lambda x, y:
        _si().Akima1DInterpolator(x, y))),
)


# ── MakeLinear1D ─────────────────────────────────────────────────────
# scipy.interpolate.interp1d(x, y, kind=...) — deprecated in SciPy ≥ 1.14

def _make_linear1d_arity3(this_generator, parent, *args):
    trail = args[-1]
    result_var = args[-2]
    x, y = deref(args[0]), deref(args[1])
    try:
        interp1d = getattr(_si(), "interp1d", None)
        if interp1d is None:
            raise AttributeError("interp1d not available in this scipy version")
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            obj = interp1d(x, y)
        handle = _alloc_handle(obj)
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


def _make_linear1d_arity4(this_generator, parent, *args):
    trail = args[-1]
    result_var = args[-2]
    x, y, kind = deref(args[0]), deref(args[1]), deref(args[2])
    try:
        interp1d = getattr(_si(), "interp1d", None)
        if interp1d is None:
            raise AttributeError("interp1d not available in this scipy version")
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            obj = interp1d(x, y, kind=kind)
        handle = _alloc_handle(obj)
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


MakeLinear1D = _pred("MakeLinear1D",
    (3, _make_linear1d_arity3),
    (4, _make_linear1d_arity4),
)


# ── MakeRegularGrid ──────────────────────────────────────────────────
# scipy.interpolate.RegularGridInterpolator(points, values, method=...)

MakeRegularGrid = _pred("MakeRegularGrid",
    (3, _make_dispatch(lambda points, values:
        _si().RegularGridInterpolator(points, values))),
    (4, _make_dispatch(lambda points, values, method:
        _si().RegularGridInterpolator(points, values, method=method))),
)


# ── MakeRadialBasis ──────────────────────────────────────────────────────────
# scipy.interpolate.RBFInterpolator(y, d, kernel=..., smoothing=...)
# Note: RBFInterpolator(y, d) — first arg is sample points, second is values

MakeRadialBasis = _pred("MakeRadialBasis",
    (3, _make_dispatch(lambda x, y:
        _si().RBFInterpolator(x, y))),
    (4, _make_dispatch(lambda x, y, function:
        _si().RBFInterpolator(x, y, kernel=function))),
    (5, _make_dispatch(lambda x, y, function, smooth:
        _si().RBFInterpolator(x, y, kernel=function, smoothing=smooth))),
)


# ── EvalSpline ───────────────────────────────────────────────────────
# Evaluate a spline (or its NU-th derivative) at points X.
# Works for BSpline, CubicSpline, PchipInterpolator, Akima1DInterpolator.

EvalSpline = _pred("EvalSpline",
    (3, _eval_dispatch(lambda obj, x:
        obj(x))),
    (4, _eval_dispatch(lambda obj, x, nu:
        obj(x, nu=int(nu)))),
)


# ── EvalRegularGrid ──────────────────────────────────────────────────

EvalRegularGrid = _pred("EvalRegularGrid",
    (3, _eval_dispatch(lambda obj, xi:
        obj(xi))),
    (4, _eval_dispatch(lambda obj, xi, method:
        obj(xi, method=method))),
)


# ── EvalRadialBasis ──────────────────────────────────────────────────────────

EvalRadialBasis = _pred("EvalRadialBasis",
    (3, _eval_dispatch(lambda obj, x:
        obj(x))),
)


# ── SplineIntegral ───────────────────────────────────────────────────
# Definite integral from A to B; calls handle.integrate(a, b).

SplineIntegral = _pred("SplineIntegral",
    (4, _eval_dispatch(lambda obj, a, b:
        float(obj.integrate(a, b)))),
)


# ── SplineDerivative ─────────────────────────────────────────────────
# Returns a new handle for the derivative spline.
# arity 2: (handle, result)   — default order=1
# arity 3: (handle, order, result)

def _spline_derivative_arity2(this_generator, parent, *args):
    trail = args[-1]
    result_var = args[-2]
    handle_val = deref(args[0])
    try:
        obj = _lookup_handle(int(handle_val))
        deriv_obj = obj.derivative()
        new_handle = _alloc_handle(deriv_obj)
    except Exception:
        yield (parent, DONE)
        return
    try:
        ok = bool(unify(result_var, new_handle, trail))
    except (ValueError, TypeError):
        ok = False
    if ok:
        yield (parent, None)
    yield (parent, DONE)


def _spline_derivative_arity3(this_generator, parent, *args):
    trail = args[-1]
    result_var = args[-2]
    handle_val = deref(args[0])
    order = deref(args[1])
    try:
        obj = _lookup_handle(int(handle_val))
        deriv_obj = obj.derivative(nu=int(order))
        new_handle = _alloc_handle(deriv_obj)
    except Exception:
        yield (parent, DONE)
        return
    try:
        ok = bool(unify(result_var, new_handle, trail))
    except (ValueError, TypeError):
        ok = False
    if ok:
        yield (parent, None)
    yield (parent, DONE)


SplineDerivative = _pred("SplineDerivative",
    (2, _spline_derivative_arity2),
    (3, _spline_derivative_arity3),
)


# ── SplineRoots ──────────────────────────────────────────────────────
# Returns the real roots (zero-crossings) of the spline as a Python list.
# arity 2: (handle, result)

SplineRoots = _pred("SplineRoots",
    (2, _eval_dispatch(lambda obj: list(obj.roots()))),
)


# ── Free ─────────────────────────────────────────────────────────────

class _FreePredicate(_SciPyInterpPredicate):
    """Free(HANDLE) — release interpolator handle from registry."""

    def __init__(self):
        super().__init__("Free")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, parent, *args):
        handle_val = deref(args[0])
        with _registry_lock:
            _INTERP_REGISTRY.pop(int(handle_val), None)
        yield (parent, None)
        yield (parent, DONE)

    def __repr__(self) -> str:
        return "scipy.interpolate.Free/1"


Free = _FreePredicate()
