"""clausal.modules.scipy_interpolate — scipy.interpolate predicates for Clausal.

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

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate
from clausal.terms import Quantity, UnitsMismatch
from clausal.modules._scipy_units import (
    strip_quantity, quantity_dims, merge_dims, wrap_result,
)


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

_INTERP_REGISTRY: dict[int, tuple] = {}
_registry_lock = _threading.Lock()
_registry_counter = [0]


def _alloc_handle(obj: object, x_dims=None, y_dims=None) -> int:
    """Store *(obj, x_dims, y_dims)* in the registry and return its integer handle."""
    with _registry_lock:
        _registry_counter[0] += 1
        handle = _registry_counter[0]
        _INTERP_REGISTRY[handle] = (obj, x_dims, y_dims)
    return handle


def _lookup_handle(handle: int) -> tuple:
    """Return ``(interpolant, x_dims, y_dims)``; dims are ``None`` when no units."""
    entry = _INTERP_REGISTRY.get(handle)
    if entry is None:
        raise KeyError(f"Unknown interpolator handle: {handle!r}")
    return entry


# ── Shared dispatch helpers ────────────────────────────────────────────────

def _make_dispatch(constructor: Callable) -> Callable:
    """Dispatch fn: deref all inputs, call constructor, alloc handle, unify."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            obj = constructor(*inputs)
            handle = _alloc_handle(obj)
        except UnitsMismatch:
            raise
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
    return dispatch


def _make_dispatch_units(constructor: Callable) -> Callable:
    """Like _make_dispatch but extracts Quantity dims from the first two inputs (x, y)."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        x_dims = quantity_dims(inputs[0]) if len(inputs) > 0 else None
        y_dims = quantity_dims(inputs[1]) if len(inputs) > 1 else None
        stripped = [strip_quantity(v) for v in inputs]
        try:
            obj = constructor(*stripped)
            handle = _alloc_handle(obj, x_dims, y_dims)
        except UnitsMismatch:
            raise
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
    return dispatch


def _eval_dispatch(evaluator: Callable) -> Callable:
    """Dispatch fn: deref all inputs, call evaluator(obj, inputs...), unify.

    The evaluator receives ``(interpolant, x_dims, y_dims, *remaining_inputs)``.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        raw_inputs = [deref(x) for x in args[:-2]]
        handle_val = raw_inputs[0]
        try:
            obj, x_dims, y_dims = _lookup_handle(int(handle_val))
            out = evaluator(obj, x_dims, y_dims, *raw_inputs[1:])
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


# ── MakeSpline ───────────────────────────────────────────────────────
# scipy.interpolate.make_interp_spline(x, y, k=3, bc_type=None)

MakeSpline = _pred("MakeSpline",
    (3, _make_dispatch_units(lambda x, y:
        _si().make_interp_spline(x, y))),
    (4, _make_dispatch_units(lambda x, y, k:
        _si().make_interp_spline(x, y, k=k))),
    (5, _make_dispatch_units(lambda x, y, k, bc_type:
        _si().make_interp_spline(x, y, k=k, bc_type=bc_type))),
)


# ── MakeCubic ────────────────────────────────────────────────────────
# scipy.interpolate.CubicSpline(x, y, bc_type=...)

MakeCubic = _pred("MakeCubic",
    (3, _make_dispatch_units(lambda x, y:
        _si().CubicSpline(x, y))),
    (4, _make_dispatch_units(lambda x, y, bc_type:
        _si().CubicSpline(x, y, bc_type=bc_type))),
)


# ── MakePCHIP ────────────────────────────────────────────────────────
# scipy.interpolate.PchipInterpolator(x, y, extrapolate=...)

MakePCHIP = _pred("MakePCHIP",
    (3, _make_dispatch_units(lambda x, y:
        _si().PchipInterpolator(x, y))),
    (4, _make_dispatch_units(lambda x, y, extrapolate:
        _si().PchipInterpolator(x, y, extrapolate=extrapolate))),
)


# ── MakeAkima ────────────────────────────────────────────────────────
# scipy.interpolate.Akima1DInterpolator(x, y)

MakeAkima = _pred("MakeAkima",
    (3, _make_dispatch_units(lambda x, y:
        _si().Akima1DInterpolator(x, y))),
)


# ── MakeLinear1D ─────────────────────────────────────────────────────
# scipy.interpolate.interp1d(x, y, kind=...) — deprecated in SciPy ≥ 1.14

def _make_linear1d_arity3(this_generator, _proceed, _fail, _catcher, *args):
    trail = args[-1]
    result_var = args[-2]
    x, y = deref(args[0]), deref(args[1])
    x_dims = quantity_dims(x)
    y_dims = quantity_dims(y)
    try:
        interp1d = getattr(_si(), "interp1d", None)
        if interp1d is None:
            raise AttributeError("interp1d not available in this scipy version")
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            obj = interp1d(strip_quantity(x), strip_quantity(y))
        handle = _alloc_handle(obj, x_dims, y_dims)
    except UnitsMismatch:
        raise
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


def _make_linear1d_arity4(this_generator, _proceed, _fail, _catcher, *args):
    trail = args[-1]
    result_var = args[-2]
    x, y, kind = deref(args[0]), deref(args[1]), deref(args[2])
    x_dims = quantity_dims(x)
    y_dims = quantity_dims(y)
    try:
        interp1d = getattr(_si(), "interp1d", None)
        if interp1d is None:
            raise AttributeError("interp1d not available in this scipy version")
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            obj = interp1d(strip_quantity(x), strip_quantity(y), kind=kind)
        handle = _alloc_handle(obj, x_dims, y_dims)
    except UnitsMismatch:
        raise
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


MakeLinear1D = _pred("MakeLinear1D",
    (3, _make_linear1d_arity3),
    (4, _make_linear1d_arity4),
)


# ── MakeRegularGrid ──────────────────────────────────────────────────
# scipy.interpolate.RegularGridInterpolator(points, values, method=...)

MakeRegularGrid = _pred("MakeRegularGrid",
    (3, _make_dispatch_units(lambda points, values:
        _si().RegularGridInterpolator(points, values))),
    (4, _make_dispatch_units(lambda points, values, method:
        _si().RegularGridInterpolator(points, values, method=method))),
)


# ── MakeRadialBasis ──────────────────────────────────────────────────────────
# scipy.interpolate.RBFInterpolator(y, d, kernel=..., smoothing=...)
# Note: RBFInterpolator(y, d) — first arg is sample points, second is values

MakeRadialBasis = _pred("MakeRadialBasis",
    (3, _make_dispatch_units(lambda x, y:
        _si().RBFInterpolator(x, y))),
    (4, _make_dispatch_units(lambda x, y, function:
        _si().RBFInterpolator(x, y, kernel=function))),
    (5, _make_dispatch_units(lambda x, y, function, smooth:
        _si().RBFInterpolator(x, y, kernel=function, smoothing=smooth))),
)


# ── EvalSpline ───────────────────────────────────────────────────────
# Evaluate a spline (or its NU-th derivative) at points X.
# Works for BSpline, CubicSpline, PchipInterpolator, Akima1DInterpolator.
# Arity-3 form is bidirectional: given Y, find X via brentq root-finding.

def _eval_spline_bwd(interp, y_target):
    """Find x such that interp(x) == y_target via brentq."""
    import scipy.optimize as _opt
    # Determine search bounds from spline knot range
    t = interp.t if hasattr(interp, 't') else interp.x
    a, b = float(t[0]), float(t[-1])
    try:
        x = _opt.brentq(lambda v: float(interp(v)) - float(y_target), a, b)
        return x
    except ValueError:
        raise ValueError(
            f"No root found for spline in [{a}, {b}]: "
            f"target {y_target} may be outside range")


def _eval_spline_bidir(this_generator, _proceed, _fail, _catcher, *args):
    """Bidirectional dispatch for EvalSpline(HANDLE, X, RESULT).

    HANDLE always ground.
    X ground, RESULT unbound → forward evaluation.
    RESULT ground, X unbound → backward root-finding via brentq.
    Both ground              → consistency check.
    """
    trail      = args[-1]
    handle_raw = args[0]
    x_raw      = args[1]
    result_raw = args[2]
    handle     = deref(handle_raw)
    x          = deref(x_raw)
    y          = deref(result_raw)

    try:
        obj, x_dims, y_dims = _lookup_handle(int(handle))
    except Exception:
        yield (_fail, DONE)
        return

    if not is_var(x) and is_var(y):
        try:
            x_val = strip_quantity(x)
            out = obj(x_val)
            out = wrap_result(out, y_dims) if y_dims else out
        except UnitsMismatch:
            raise
        except Exception:
            yield (_fail, DONE)
            return
        if unify(result_raw, out, trail):
            yield (_proceed, None)

    elif is_var(x) and not is_var(y):
        try:
            y_val = strip_quantity(y)
            out = _eval_spline_bwd(obj, y_val)
            out = wrap_result(out, x_dims) if x_dims else out
        except UnitsMismatch:
            raise
        except Exception:
            yield (_fail, DONE)
            return
        if unify(x_raw, out, trail):
            yield (_proceed, None)

    elif not is_var(x) and not is_var(y):
        # both ground: consistency check
        try:
            x_val = strip_quantity(x)
            out = obj(x_val)
            out = wrap_result(out, y_dims) if y_dims else out
        except UnitsMismatch:
            raise
        except Exception:
            yield (_fail, DONE)
            return
        try:
            ok = bool(unify(result_raw, out, trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (_proceed, None)

    yield (_fail, DONE)


def _eval_spline_nu(obj, x_dims, y_dims, x, nu):
    """Evaluate spline NU-th derivative at x, with unit propagation."""
    x_val = strip_quantity(x)
    raw = obj(x_val, nu=int(nu))
    if y_dims is None:
        return raw
    nu_int = int(nu)
    if nu_int == 0:
        out_dims = y_dims
    else:
        out_dims = merge_dims(y_dims, x_dims or {}, -nu_int)
    return wrap_result(raw, out_dims)


EvalSpline = _pred("EvalSpline",
    (3, _eval_spline_bidir),
    (4, _eval_dispatch(_eval_spline_nu)),
)


# ── EvalRegularGrid ──────────────────────────────────────────────────

def _eval_regular_grid(obj, x_dims, y_dims, xi, method=None):
    xi_val = strip_quantity(xi)
    raw = obj(xi_val) if method is None else obj(xi_val, method=method)
    return wrap_result(raw, y_dims) if y_dims else raw


EvalRegularGrid = _pred("EvalRegularGrid",
    (3, _eval_dispatch(lambda obj, x_dims, y_dims, xi:
        _eval_regular_grid(obj, x_dims, y_dims, xi))),
    (4, _eval_dispatch(lambda obj, x_dims, y_dims, xi, method:
        _eval_regular_grid(obj, x_dims, y_dims, xi, method=method))),
)


# ── EvalRadialBasis ──────────────────────────────────────────────────────────

EvalRadialBasis = _pred("EvalRadialBasis",
    (3, _eval_dispatch(lambda obj, x_dims, y_dims, x:
        wrap_result(obj(strip_quantity(x)), y_dims) if y_dims else obj(x))),
)


# ── SplineIntegral ───────────────────────────────────────────────────
# Definite integral from A to B; calls handle.integrate(a, b).

def _spline_integral(obj, x_dims, y_dims, a, b):
    """Definite integral from a to b; output dims = y_dims + x_dims."""
    raw = float(obj.integrate(strip_quantity(a), strip_quantity(b)))
    if y_dims is None:
        return raw
    out_dims = merge_dims(y_dims, x_dims or {}, +1)
    return wrap_result(raw, out_dims)


SplineIntegral = _pred("SplineIntegral",
    (4, _eval_dispatch(_spline_integral)),
)


# ── SplineDerivative ─────────────────────────────────────────────────
# Returns a new handle for the derivative spline.
# arity 2: (handle, result)   — default order=1
# arity 3: (handle, order, result)

def _spline_derivative_arity2(this_generator, _proceed, _fail, _catcher, *args):
    trail = args[-1]
    result_var = args[-2]
    handle_val = deref(args[0])
    try:
        obj, x_dims, y_dims = _lookup_handle(int(handle_val))
        deriv_obj = obj.derivative()
        new_y_dims = merge_dims(y_dims, x_dims or {}, -1) if y_dims is not None else None
        new_handle = _alloc_handle(deriv_obj, x_dims, new_y_dims)
    except UnitsMismatch:
        raise
    except Exception:
        yield (_fail, DONE)
        return
    try:
        ok = bool(unify(result_var, new_handle, trail))
    except (ValueError, TypeError):
        ok = False
    if ok:
        yield (_proceed, None)
    yield (_fail, DONE)


def _spline_derivative_arity3(this_generator, _proceed, _fail, _catcher, *args):
    trail = args[-1]
    result_var = args[-2]
    handle_val = deref(args[0])
    order = deref(args[1])
    try:
        obj, x_dims, y_dims = _lookup_handle(int(handle_val))
        deriv_obj = obj.derivative(nu=int(order))
        new_y_dims = merge_dims(y_dims, x_dims or {}, -int(order)) if y_dims is not None else None
        new_handle = _alloc_handle(deriv_obj, x_dims, new_y_dims)
    except UnitsMismatch:
        raise
    except Exception:
        yield (_fail, DONE)
        return
    try:
        ok = bool(unify(result_var, new_handle, trail))
    except (ValueError, TypeError):
        ok = False
    if ok:
        yield (_proceed, None)
    yield (_fail, DONE)


SplineDerivative = _pred("SplineDerivative",
    (2, _spline_derivative_arity2),
    (3, _spline_derivative_arity3),
)


# ── SplineRoots ──────────────────────────────────────────────────────
# Returns the real roots (zero-crossings) of the spline as a Python list.
# arity 2: (handle, result)

def _spline_roots(obj, x_dims, y_dims):
    """Return roots of the spline, wrapped with x_dims if present."""
    roots = list(obj.roots())
    if x_dims:
        return [wrap_result(r, x_dims) for r in roots]
    return roots


SplineRoots = _pred("SplineRoots",
    (2, _eval_dispatch(_spline_roots)),
)


# ── Free ─────────────────────────────────────────────────────────────

class _FreePredicate(ModulePredicate):
    """Free(HANDLE) — release interpolator handle from registry."""

    def __init__(self):
        super().__init__("Free")

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        handle_val = deref(args[0])
        with _registry_lock:
            _INTERP_REGISTRY.pop(int(handle_val), None)
        yield (_proceed, None)
        yield (_fail, DONE)

    def __repr__(self) -> str:
        return "scipy.interpolate.Free/1"


Free = _FreePredicate()
