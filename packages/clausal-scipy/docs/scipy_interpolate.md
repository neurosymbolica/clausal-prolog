# scipy.interpolate — Interpolation

The `scipy_interpolate` module wraps [`scipy.interpolate`](https://docs.scipy.org/doc/scipy/reference/interpolate.html) as Clausal predicates. It provides 1-D and N-D interpolators (splines, monotone cubics, radial basis functions, regular grids) via a **handle-based (Tier 3)** interface: construct an interpolator, use it, then release it.

---

## Import

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:import"
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:import_ex2"
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
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors"
```

#### `MakeCubic` — cubic spline with configurable boundary conditions

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex2"
```

#### `MakePCHIP` — monotone cubic (good for noisy data)

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex3"
```

#### `MakeAkima` — Akima 1-D interpolator

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex4"
```

#### `MakeLinear1D` — legacy piecewise interpolation

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex5"
```

#### `MakeRegularGrid` — N-D interpolation on a regular grid

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex6"
```

#### `MakeRadialBasis` — radial basis function interpolation

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex7"
```

---

### Evaluators

#### `EvalSpline` — evaluate a 1-D interpolator

Works with handles from `MakeSpline`, `MakeCubic`,
`MakePCHIP`, `MakeAkima`, and `MakeLinear1D`.

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:evaluators"
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
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:evaluators_ex2"
```

#### `EvalRadialBasis` — evaluate an RBF interpolator

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:evaluators_ex3"
```

---

### Spline utilities

These predicates operate on handles from any of the 1-D spline constructors
(`MakeSpline`, `MakeCubic`, `MakePCHIP`, `MakeAkima`).

#### `SplineIntegral` — definite integral

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:spline_utilities"
```

#### `SplineDerivative` — derivative spline

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:spline_utilities_ex2"
```

#### `SplineRoots` — zero-crossings

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:spline_utilities_ex3"
```

---

### Lifecycle: `Free`

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:lifecycle_free"
```

Good practice: call `Free` when the interpolator is no longer needed to prevent unbounded registry growth.

---

## Complete examples

### 1-D spline fitting and evaluation

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:spline_1d_fitting_and_evaluation"
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
are [`Quantity`](units.md) objects, units are stored in the handle and propagated through
evaluation, integration, and differentiation.

### How it works

The handle registry stores `(interpolant, x_dims, y_dims)` triples.  when
`Make*` receives `Quantity` inputs, it strips the values for scipy and records
the dims.  when no `Quantity` inputs are present, `x_dims` and `y_dims` are
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
-import_from(py.units, [metre, second, has_units])

% Position (m) as a function of time (s)
Test("spline with units") <- (
    MakeSpline(++(numpy.array([0.0(second), 1.0(second), 2.0(second)])),
               ++(numpy.array([0.0(metre), 5.0(metre), 20.0(metre)])),
               H),
    EvalSpline(H, 1.0(second), Y),
    has_units(Y, metre),
    SplineIntegral(H, 0.0(second), 2.0(second), AREA),
    has_units(AREA, metre*second),
    Free(H))
```

---

## Notes

- **Array inputs**: pass NumPy arrays or Python lists via [`++()`](python_integration.md).
- **Callables are not needed**: unlike optimize/integrate, interpolate predicates do not accept user-defined functions — all fitting is done from data arrays.
- **Handles are integers**: store a handle in a Clausal variable; it unifies like any other term.
- **Multiple handles**: each `Make*` call allocates a fresh handle; handles from `SplineDerivative` are also independent and must be freed separately.
- **Thread safety**: the handle registry is protected by a lock; predicates are safe to call concurrently. See [Free Threading](free_threading.md) for details.
- **interp1d deprecation**: `MakeLinear1D` wraps `scipy.interpolate.interp1d`, which is deprecated since SciPy 1.14. It fails gracefully if not available. Use `MakeSpline` with `K=1` for linear interpolation in new code.
- Predicates fail (yield no solution) when scipy raises an exception, or when a bound `RESULT` does not unify with the computed value.

---

*See also: [scipy.signal](scipy_signal.md) — signal processing · [scipy.special](scipy_special.md) — special functions for interpolation kernels.*
