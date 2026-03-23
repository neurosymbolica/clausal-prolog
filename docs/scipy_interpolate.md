# scipy.interpolate — Interpolation

The `scipy_interpolate` module wraps [`scipy.interpolate`](https://docs.scipy.org/doc/scipy/reference/interpolate.html) as Clausal predicates. It provides 1-D and N-D interpolators (splines, monotone cubics, radial basis functions, regular grids) via a **handle-based (Tier 3)** interface: construct an interpolator, use it, then release it.

---

## Import

```clausal
# skip
-import_from(scipy_interpolate, [MakeSpline, EvalSpline, Free, ...])
```

Or via the canonical `py.*` path:

```clausal
# skip
-import_from(py.scipy_interpolate, [MakeSpline, EvalSpline, ...])
```

---

## Tier 3 — handle-based interface

All interpolators are **stateful Python objects** stored in a module-level registry. Predicates follow a lifecycle pattern:

1. **`Make*`** — construct an interpolator, get back an integer `HANDLE`.
2. **`Eval*` / `Spline*`** — look up `HANDLE`, evaluate or query.
3. **`Free`** — release `HANDLE` from the registry.

Handles are opaque integers. They are valid until `Free` is called.

---

## Pipeline pattern

```clausal
-import_from(scipy_interpolate, [MakeSpline, EvalSpline,
    SplineIntegral, SplineDerivative, Free])

SplineWorkflow(XS, YS, QUERY_XS, VALUES, AREA) <- (
    MakeSpline(XS, YS, 3, HANDLE),
    EvalSpline(HANDLE, QUERY_XS, VALUES),
    SplineIntegral(HANDLE, 0.0, 10.0, AREA),
    Free(HANDLE)
)
```

---

## Naming conventions

Predicate names use full English words where scipy uses abbreviations:

| scipy name | Clausal predicate |
|---|---|
| `make_interp_spline` | `MakeSpline` |
| `CubicSpline` | `MakeCubic` |
| `PchipInterpolator` | `MakePCHIP` |
| `Akima1DInterpolator` | `MakeAkima` |
| `interp1d` | `MakeLinear1D` |
| `RegularGridInterpolator` | `MakeRegularGrid` |
| `RBFInterpolator` | `MakeRadialBasis` |

`PCHIP` (Piecewise Cubic Hermite Interpolating Polynomial) is kept as a recognised abbreviation. `RBF` is spelled out as `RadialBasis`. `1D` is expanded from scipy's `1d`.

---

## Predicate catalogue

### Constructors

#### `MakeSpline` — recommended 1-D spline

```clausal
# skip
MakeSpline(X, Y, RESULT)
MakeSpline(X, Y, K, RESULT)
MakeSpline(X, Y, K, BC_TYPE, RESULT)
    → scipy.interpolate.make_interp_spline(x, y, k=K, bc_type=BC_TYPE)
    X:       1-D array of sample positions (strictly increasing)
    Y:       1-D array of sample values
    K:       spline degree (default 3 = cubic)
    BC_TYPE: boundary conditions — None or list of (order, value) pairs
    RESULT:  integer handle
```

#### `MakeCubic` — cubic spline with configurable boundary conditions

```clausal
# skip
MakeCubic(X, Y, RESULT)
MakeCubic(X, Y, BC_TYPE, RESULT)
    → scipy.interpolate.CubicSpline(x, y, bc_type=BC_TYPE)
    BC_TYPE: 'not-a-knot' (default), 'clamped', 'natural', 'periodic',
             or a 2-tuple of (first_deriv, second_deriv) conditions
```

#### `MakePCHIP` — monotone cubic (good for noisy data)

```clausal
# skip
MakePCHIP(X, Y, RESULT)
MakePCHIP(X, Y, EXTRAPOLATE, RESULT)
    → scipy.interpolate.PchipInterpolator(x, y, extrapolate=EXTRAPOLATE)
    EXTRAPOLATE: True (default) / False / None
    Preserves monotonicity; does not overshoot between data points.
```

#### `MakeAkima` — Akima 1-D interpolator

```clausal
# skip
MakeAkima(X, Y, RESULT)
    → scipy.interpolate.Akima1DInterpolator(x, y)
    Less sensitive to outliers than cubic splines.
```

#### `MakeLinear1D` — legacy piecewise interpolation

```clausal
# skip
MakeLinear1D(X, Y, RESULT)
MakeLinear1D(X, Y, KIND, RESULT)
    → scipy.interpolate.interp1d(x, y, kind=KIND)
    KIND: 'linear' (default), 'nearest', 'nearest-up', 'zero',
          'slinear', 'quadratic', 'cubic', 'previous', 'next'
    Note: deprecated in SciPy ≥ 1.14; prefer MakeSpline for new code.
```

#### `MakeRegularGrid` — N-D interpolation on a regular grid

```clausal
# skip
MakeRegularGrid(POINTS, VALUES, RESULT)
MakeRegularGrid(POINTS, VALUES, METHOD, RESULT)
    → scipy.interpolate.RegularGridInterpolator(points, values, method=METHOD)
    POINTS: tuple of 1-D arrays, one per dimension (lengths m1, m2, …)
    VALUES: N-D array of shape (m1, m2, …)
    METHOD: 'linear' (default), 'nearest', 'slinear', 'cubic', 'quintic'
```

#### `MakeRadialBasis` — radial basis function interpolation

```clausal
# skip
MakeRadialBasis(X, Y, RESULT)
MakeRadialBasis(X, Y, FUNCTION, RESULT)
MakeRadialBasis(X, Y, FUNCTION, SMOOTH, RESULT)
    → scipy.interpolate.RBFInterpolator(x, y, kernel=FUNCTION, smoothing=SMOOTH)
    X:        2-D array of sample points, shape (n_samples, n_dims)
    Y:        1-D array of sample values, length n_samples
    FUNCTION: kernel name — 'linear', 'thin_plate_spline', 'cubic', 'quintic',
              'multiquadric' (default), 'inverse_multiquadric',
              'inverse_quadratic', 'gaussian'
    SMOOTH:   smoothing parameter (0 = exact interpolation, default 0)
```

---

### Evaluators

#### `EvalSpline` — evaluate a 1-D interpolator

Works with handles from `MakeSpline`, `MakeCubic`,
`MakePCHIP`, `MakeAkima`, and `MakeLinear1D`.

```clausal
# skip
EvalSpline(HANDLE, X, Y)                   # bidirectional (arity-3)
    X ground, Y unbound → Y = spline(x)    # forward: evaluate at query point(s)
    Y ground, X unbound → X = root-find    # backward: find x such that spline(x) = y
    Both ground         → consistency check: succeeds iff spline(x) ≈ y

EvalSpline(HANDLE, X, NU, RESULT)          # unidirectional (arity-4)
    HANDLE: integer from any Make1D predicate
    X:      query point(s)
    NU:     derivative order (default 0 = function value)
    RESULT: interpolated value(s) at X
```

**Backward direction**: uses `scipy.optimize.brentq` root-finding over the spline's domain `[x_min, x_max]`. Succeeds with a single root for monotone splines; fails (no solution) when the target `Y` is outside the spline's range or the spline is not monotone over the whole domain. Use a monotone constructor (`MakePCHIP`) when the backward direction must be reliable.

Example — invert a spline to find the input that gives a target output:

```clausal
-import_from(scipy_interpolate, [MakePCHIP, EvalSpline, Free])

# Forward: evaluate the interpolator at x=2.5
SplineForward(XS, YS, RESULT) <- (
    MakePCHIP(XS, YS, H),
    EvalSpline(H, 2.5, RESULT),
    Free(H)
)

# Backward: find x such that spline(x) = target value
SplineInvert(XS, YS, TARGET, X) <- (
    MakePCHIP(XS, YS, H),
    EvalSpline(H, X, TARGET),
    Free(H)
)
```

#### `EvalRegularGrid` — evaluate an N-D regular-grid interpolator

```clausal
# skip
EvalRegularGrid(HANDLE, XI, RESULT)
EvalRegularGrid(HANDLE, XI, METHOD, RESULT)
    HANDLE: integer from MakeRegularGrid
    XI:     array of query points, shape (..., ndim)
    METHOD: override the interpolation method for this call
    RESULT: array of interpolated values
```

#### `EvalRadialBasis` — evaluate an RBF interpolator

```clausal
# skip
EvalRadialBasis(HANDLE, X, RESULT)
    HANDLE: integer from MakeRadialBasis
    X:      2-D array of query points, shape (n_query, n_dims)
    RESULT: 1-D array of interpolated values
```

---

### Spline utilities

These predicates operate on handles from any of the 1-D spline constructors
(`MakeSpline`, `MakeCubic`, `MakePCHIP`, `MakeAkima`).

#### `SplineIntegral` — definite integral

```clausal
# skip
SplineIntegral(HANDLE, A, B, RESULT)
    Compute the definite integral of the spline from A to B.
    HANDLE: spline handle
    A, B:   integration limits (scalars)
    RESULT: scalar — value of the integral
```

#### `SplineDerivative` — derivative spline

```clausal
# skip
SplineDerivative(HANDLE, RESULT)
SplineDerivative(HANDLE, ORDER, RESULT)
    Return a new HANDLE for the ORDER-th derivative of the spline.
    ORDER:  derivative order (default 1)
    RESULT: new integer handle — must be freed separately
```

#### `SplineRoots` — zero-crossings

```clausal
# skip
SplineRoots(HANDLE, RESULT)
    Return the real roots (zero-crossings) of the spline within its domain.
    RESULT: Python list of root values
    Note: only defined for CubicSpline; other spline types may raise an error.
```

---

### Lifecycle: `Free`

```clausal
# skip
Free(HANDLE)
    Release HANDLE from the handle registry.
    Always succeeds, even if HANDLE is not registered.
```

Good practice: call `Free` when the interpolator is no longer needed to prevent unbounded registry growth.

---

## Complete examples

### 1-D spline fitting and evaluation

```clausal
# skip
-import_from(scipy_interpolate, [MakeCubic, EvalSpline, Free])

# Fit a cubic spline to sample data and evaluate at new points.
FitAndEval(XS, YS, QUERY_XS, VALUES) <- (
    MakeCubic(XS, YS, HANDLE),
    EvalSpline(HANDLE, QUERY_XS, VALUES),
    Free(HANDLE)
)
```

### Spline integration and derivative

```clausal
-import_from(scipy_interpolate, [MakeCubic, SplineIntegral,
    SplineDerivative, EvalSpline, Free])

SplineAnalysis(XS, YS, AREA, DERIV_AT_2) <- (
    MakeCubic(XS, YS, H),
    SplineIntegral(H, 0.0, 4.0, AREA),
    SplineDerivative(H, HD),
    EvalSpline(HD, ++([2.0]), DVALS),
    DERIV_AT_2 is ++(float(DVALS[0])),
    Free(H),
    Free(HD)
)
```

### N-D interpolation on a regular grid

```clausal
-import_from(scipy_interpolate, [MakeRegularGrid, EvalRegularGrid, Free])

GridInterp(POINTS, VALUES, QUERY, RESULT) <- (
    MakeRegularGrid(POINTS, VALUES, HANDLE),
    EvalRegularGrid(HANDLE, QUERY, RESULT),
    Free(HANDLE)
)
```

### Radial basis function interpolation

```clausal
-import_from(scipy_interpolate, [MakeRadialBasis, EvalRadialBasis, Free])

RbfInterp(SAMPLE_PTS, SAMPLE_VALS, QUERY_PTS, RESULT) <- (
    MakeRadialBasis(SAMPLE_PTS, SAMPLE_VALS, 'thin_plate_spline', HANDLE),
    EvalRadialBasis(HANDLE, QUERY_PTS, RESULT),
    Free(HANDLE)
)
```

---

## Dimensional analysis (Quantity support)

All interpolation predicates are **quantity-aware**: when `X` and `Y` arrays
are `Quantity` objects, units are stored in the handle and propagated through
evaluation, integration, and differentiation.

### How it works

The handle registry stores `(interpolant, x_dims, y_dims)` triples.  When
`Make*` receives `Quantity` inputs, it strips the values for scipy and records
the dims.  When no `Quantity` inputs are present, `x_dims` and `y_dims` are
`None` and all evaluation returns plain values — **zero overhead**.

### Unit propagation rules

| Operation | Output dims |
|---|---|
| `EvalSpline(H, X, R)` | `y_dims` |
| `EvalSpline(H, X, NU, R)` | `y_dims - NU * x_dims` |
| `SplineIntegral(H, A, B, R)` | `y_dims + x_dims` |
| `SplineDerivative(H, R)` | new handle with `y_dims - x_dims` |
| `SplineDerivative(H, ORDER, R)` | new handle with `y_dims - ORDER * x_dims` |
| `SplineRoots(H, R)` | list of values with `x_dims` |
| `EvalRegularGrid(H, XI, R)` | `y_dims` |
| `EvalRadialBasis(H, X, R)` | `y_dims` |

### Example

```
-import_from(scipy_interpolate, [MakeSpline, EvalSpline, SplineIntegral, Free])
-import_from(py.units, [Metre, Second, HasUnits])

% Position (m) as a function of time (s)
Test("spline with units") <- (
    MakeSpline(++(numpy.array([0.0(Second), 1.0(Second), 2.0(Second)])),
               ++(numpy.array([0.0(Metre), 5.0(Metre), 20.0(Metre)])),
               H),
    EvalSpline(H, 1.0(Second), Y),
    HasUnits(Y, Metre),
    SplineIntegral(H, 0.0(Second), 2.0(Second), AREA),
    HasUnits(AREA, Metre*Second),
    Free(H))
```

---

## Notes

- **Array inputs**: pass NumPy arrays or Python lists via `++()`.
- **Callables are not needed**: unlike optimize/integrate, interpolate predicates do not accept user-defined functions — all fitting is done from data arrays.
- **Handles are integers**: store a handle in a Clausal variable; it unifies like any other term.
- **Multiple handles**: each `Make*` call allocates a fresh handle; handles from `SplineDerivative` are also independent and must be freed separately.
- **Thread safety**: the handle registry is protected by a lock; predicates are safe to call concurrently.
- **interp1d deprecation**: `MakeLinear1D` wraps `scipy.interpolate.interp1d`, which is deprecated since SciPy 1.14. It fails gracefully if not available. Use `MakeSpline` with `K=1` for linear interpolation in new code.
- Predicates fail (yield no solution) when scipy raises an exception, or when a bound `RESULT` does not unify with the computed value.

---

*See also: [scipy.signal](scipy_signal.md) — signal processing · [scipy.special](scipy_special.md) — special functions for interpolation kernels.*
