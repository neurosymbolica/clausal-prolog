# scipy.interpolate — Interpolation

The `scipy_interpolate` module wraps [`scipy.interpolate`](https://docs.scipy.org/doc/scipy/reference/interpolate.html) as Clausal predicates. It provides 1-D and N-D interpolators (splines, monotone cubics, radial basis functions, regular grids) via a **handle-based (Tier 3)** interface: construct an interpolator, use it, then release it.

---

## Import

```
-import_from(scipy_interpolate, [MakeSpline, EvalSpline, Free, ...])
```

Or via the canonical `py.*` path:

```
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

```
-import_from(scipy_interpolate, [MakeSpline, EvalSpline,
    SplineIntegral, SplineDerivative, Free])

SplineWorkflow(XS, YS, QUERY_XS, VALUES, AREA) <- (
    MakeSpline(XS, YS, 3, HANDLE) and
    EvalSpline(HANDLE, QUERY_XS, VALUES) and
    SplineIntegral(HANDLE, 0.0, 10.0, AREA) and
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

```
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

```
MakeCubic(X, Y, RESULT)
MakeCubic(X, Y, BC_TYPE, RESULT)
    → scipy.interpolate.CubicSpline(x, y, bc_type=BC_TYPE)
    BC_TYPE: 'not-a-knot' (default), 'clamped', 'natural', 'periodic',
             or a 2-tuple of (first_deriv, second_deriv) conditions
```

#### `MakePCHIP` — monotone cubic (good for noisy data)

```
MakePCHIP(X, Y, RESULT)
MakePCHIP(X, Y, EXTRAPOLATE, RESULT)
    → scipy.interpolate.PchipInterpolator(x, y, extrapolate=EXTRAPOLATE)
    EXTRAPOLATE: True (default) / False / None
    Preserves monotonicity; does not overshoot between data points.
```

#### `MakeAkima` — Akima 1-D interpolator

```
MakeAkima(X, Y, RESULT)
    → scipy.interpolate.Akima1DInterpolator(x, y)
    Less sensitive to outliers than cubic splines.
```

#### `MakeLinear1D` — legacy piecewise interpolation

```
MakeLinear1D(X, Y, RESULT)
MakeLinear1D(X, Y, KIND, RESULT)
    → scipy.interpolate.interp1d(x, y, kind=KIND)
    KIND: 'linear' (default), 'nearest', 'nearest-up', 'zero',
          'slinear', 'quadratic', 'cubic', 'previous', 'next'
    Note: deprecated in SciPy ≥ 1.14; prefer MakeSpline for new code.
```

#### `MakeRegularGrid` — N-D interpolation on a regular grid

```
MakeRegularGrid(POINTS, VALUES, RESULT)
MakeRegularGrid(POINTS, VALUES, METHOD, RESULT)
    → scipy.interpolate.RegularGridInterpolator(points, values, method=METHOD)
    POINTS: tuple of 1-D arrays, one per dimension (lengths m1, m2, …)
    VALUES: N-D array of shape (m1, m2, …)
    METHOD: 'linear' (default), 'nearest', 'slinear', 'cubic', 'quintic'
```

#### `MakeRadialBasis` — radial basis function interpolation

```
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

```
EvalSpline(HANDLE, X, RESULT)
EvalSpline(HANDLE, X, NU, RESULT)
    HANDLE: integer from any Make1D predicate
    X:      array of query points
    NU:     derivative order (default 0 = function value)
    RESULT: array of interpolated values
```

#### `EvalRegularGrid` — evaluate an N-D regular-grid interpolator

```
EvalRegularGrid(HANDLE, XI, RESULT)
EvalRegularGrid(HANDLE, XI, METHOD, RESULT)
    HANDLE: integer from MakeRegularGrid
    XI:     array of query points, shape (..., ndim)
    METHOD: override the interpolation method for this call
    RESULT: array of interpolated values
```

#### `EvalRadialBasis` — evaluate an RBF interpolator

```
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

```
SplineIntegral(HANDLE, A, B, RESULT)
    Compute the definite integral of the spline from A to B.
    HANDLE: spline handle
    A, B:   integration limits (scalars)
    RESULT: scalar — value of the integral
```

#### `SplineDerivative` — derivative spline

```
SplineDerivative(HANDLE, RESULT)
SplineDerivative(HANDLE, ORDER, RESULT)
    Return a new HANDLE for the ORDER-th derivative of the spline.
    ORDER:  derivative order (default 1)
    RESULT: new integer handle — must be freed separately
```

#### `SplineRoots` — zero-crossings

```
SplineRoots(HANDLE, RESULT)
    Return the real roots (zero-crossings) of the spline within its domain.
    RESULT: Python list of root values
    Note: only defined for CubicSpline; other spline types may raise an error.
```

---

### Lifecycle: `Free`

```
Free(HANDLE)
    Release HANDLE from the handle registry.
    Always succeeds, even if HANDLE is not registered.
```

Good practice: call `Free` when the interpolator is no longer needed to prevent unbounded registry growth.

---

## Complete examples

### 1-D spline fitting and evaluation

```
-import_from(scipy_interpolate, [MakeCubic, EvalSpline, Free])

% Fit a cubic spline to sample data and evaluate at new points.
FitAndEval(XS, YS, QUERY_XS, VALUES) <- (
    MakeCubic(XS, YS, HANDLE) and
    EvalSpline(HANDLE, QUERY_XS, VALUES) and
    Free(HANDLE)
)
```

### Spline integration and derivative

```
-import_from(scipy_interpolate, [MakeCubic, SplineIntegral,
    SplineDerivative, EvalSpline, Free])

SplineAnalysis(XS, YS, AREA, DERIV_AT_2) <- (
    MakeCubic(XS, YS, H) and
    SplineIntegral(H, 0.0, 4.0, AREA) and
    SplineDerivative(H, HD) and
    EvalSpline(HD, ++([2.0]), DVALS) and
    DERIV_AT_2 is ++(float(DVALS[0])) and
    Free(H) and
    Free(HD)
)
```

### N-D interpolation on a regular grid

```
-import_from(scipy_interpolate, [MakeRegularGrid, EvalRegularGrid, Free])

GridInterp(POINTS, VALUES, QUERY, RESULT) <- (
    MakeRegularGrid(POINTS, VALUES, HANDLE) and
    EvalRegularGrid(HANDLE, QUERY, RESULT) and
    Free(HANDLE)
)
```

### Radial basis function interpolation

```
-import_from(scipy_interpolate, [MakeRadialBasis, EvalRadialBasis, Free])

RbfInterp(SAMPLE_PTS, SAMPLE_VALS, QUERY_PTS, RESULT) <- (
    MakeRadialBasis(SAMPLE_PTS, SAMPLE_VALS, 'thin_plate_spline', HANDLE) and
    EvalRadialBasis(HANDLE, QUERY_PTS, RESULT) and
    Free(HANDLE)
)
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
