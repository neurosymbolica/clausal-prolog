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
3. **`free`** — release `HANDLE` from the registry.

Handles are opaque integers. They are valid until `free` is called.

---

## Pipeline pattern

```clausal
-import_from(scipy_interpolate, [make_spline, eval_spline,
    spline_integral, spline_derivative, free])

spline_workflow(XS, YS, QUERY_XS, VALUES, AREA) <- (
    make_spline(XS, YS, 3, HANDLE),
    eval_spline(HANDLE, QUERY_XS, VALUES),
    spline_integral(HANDLE, 0.0, 10.0, AREA),
    free(HANDLE)
)
```

---

## Naming conventions

Predicate names use full English words where scipy uses abbreviations:

| scipy name | Clausal predicate |
|---|---|
| `make_interp_spline` | `make_spline` |
| `CubicSpline` | `make_cubic` |
| `PchipInterpolator` | `make_pchip` |
| `Akima1DInterpolator` | `make_akima` |
| `interp1d` | `make_linear1d` |
| `RegularGridInterpolator` | `make_regular_grid` |
| `RBFInterpolator` | `make_radial_basis` |

`PCHIP` (Piecewise Cubic Hermite Interpolating Polynomial) is kept as a recognised abbreviation. `RBF` is spelled out as `RadialBasis`. `1D` is expanded from scipy's `1d`.

---

## Predicate catalogue

### Constructors

#### `make_spline` — recommended 1-D spline

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors"
```

#### `make_cubic` — cubic spline with configurable boundary conditions

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex2"
```

#### `make_pchip` — monotone cubic (good for noisy data)

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex3"
```

#### `make_akima` — Akima 1-D interpolator

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex4"
```

#### `make_linear1d` — legacy piecewise interpolation

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex5"
```

#### `make_regular_grid` — N-D interpolation on a regular grid

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex6"
```

#### `make_radial_basis` — radial basis function interpolation

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:constructors_ex7"
```

---

### Evaluators

#### `eval_spline` — evaluate a 1-D interpolator

Works with handles from `make_spline`, `make_cubic`,
`make_pchip`, `make_akima`, and `make_linear1d`.

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:evaluators"
```

**Backward direction**: uses `scipy.optimize.brentq` root-finding over the spline's domain `[x_min, x_max]`. Succeeds with a single root for monotone splines; fails (no solution) when the target `Y` is outside the spline's range or the spline is not monotone over the whole domain. Use a monotone constructor (`make_pchip`) when the backward direction must be reliable.

Example — invert a spline to find the input that gives a target output:

```clausal
-import_from(scipy_interpolate, [make_pchip, eval_spline, free])

# Forward: evaluate the interpolator at x=2.5
spline_forward(XS, YS, RESULT) <- (
    make_pchip(XS, YS, H),
    eval_spline(H, 2.5, RESULT),
    free(H)
)

# Backward: find x such that spline(x) = target value
spline_invert(XS, YS, TARGET, X) <- (
    make_pchip(XS, YS, H),
    eval_spline(H, X, TARGET),
    free(H)
)
```

#### `eval_regular_grid` — evaluate an N-D regular-grid interpolator

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:evaluators_ex2"
```

#### `eval_radial_basis` — evaluate an RBF interpolator

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:evaluators_ex3"
```

---

### Spline utilities

These predicates operate on handles from any of the 1-D spline constructors
(`make_spline`, `make_cubic`, `make_pchip`, `make_akima`).

#### `spline_integral` — definite integral

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:spline_utilities"
```

#### `spline_derivative` — derivative spline

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:spline_utilities_ex2"
```

#### `spline_roots` — zero-crossings

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:spline_utilities_ex3"
```

---

### Lifecycle: `free`

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:lifecycle_free"
```

Good practice: call `free` when the interpolator is no longer needed to prevent unbounded registry growth.

---

## Complete examples

### 1-D spline fitting and evaluation

```clausal
--8<-- "tests/fixtures/docs/scipy_interpolate_sigs.txt:spline_1d_fitting_and_evaluation"
```

### Spline integration and derivative

```clausal
-import_from(scipy_interpolate, [make_cubic, spline_integral,
    spline_derivative, eval_spline, free])

spline_analysis(XS, YS, AREA, DERIV_AT_2) <- (
    make_cubic(XS, YS, H),
    spline_integral(H, 0.0, 4.0, AREA),
    spline_derivative(H, HD),
    eval_spline(HD, ++([2.0]), DVALS),
    DERIV_AT_2 is ++(float(DVALS[0])),
    free(H),
    free(HD)
)
```

### N-D interpolation on a regular grid

```clausal
-import_from(scipy_interpolate, [make_regular_grid, eval_regular_grid, free])

grid_interp(POINTS, VALUES, QUERY, RESULT) <- (
    make_regular_grid(POINTS, VALUES, HANDLE),
    eval_regular_grid(HANDLE, QUERY, RESULT),
    free(HANDLE)
)
```

### Radial basis function interpolation

```clausal
-import_from(scipy_interpolate, [make_radial_basis, eval_radial_basis, free])

rbf_interp(SAMPLE_PTS, SAMPLE_VALS, QUERY_PTS, RESULT) <- (
    make_radial_basis(SAMPLE_PTS, SAMPLE_VALS, 'thin_plate_spline', HANDLE),
    eval_radial_basis(HANDLE, QUERY_PTS, RESULT),
    free(HANDLE)
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

### unit propagation rules

| Operation | Output dims |
|---|---|
| `eval_spline(H, X, R)` | `y_dims` |
| `eval_spline(H, X, NU, R)` | `y_dims - NU * x_dims` |
| `spline_integral(H, A, B, R)` | `y_dims + x_dims` |
| `spline_derivative(H, R)` | new handle with `y_dims - x_dims` |
| `spline_derivative(H, ORDER, R)` | new handle with `y_dims - ORDER * x_dims` |
| `spline_roots(H, R)` | list of values with `x_dims` |
| `eval_regular_grid(H, XI, R)` | `y_dims` |
| `eval_radial_basis(H, X, R)` | `y_dims` |

### Example

```
-import_from(scipy_interpolate, [make_spline, eval_spline, spline_integral, free])
-import_from(py.units, [metre, second, has_units])

% Position (m) as a function of time (s)
Test("spline with units") <- (
    make_spline(++(numpy.array([0.0(second), 1.0(second), 2.0(second)])),
               ++(numpy.array([0.0(metre), 5.0(metre), 20.0(metre)])),
               H),
    eval_spline(H, 1.0(second), Y),
    has_units(Y, metre),
    spline_integral(H, 0.0(second), 2.0(second), AREA),
    has_units(AREA, metre*second),
    free(H))
```

---

## Notes

- **Array inputs**: pass NumPy arrays or Python lists via [`++()`](python_integration.md).
- **Callables are not needed**: unlike optimize/integrate, interpolate predicates do not accept user-defined functions — all fitting is done from data arrays.
- **Handles are integers**: store a handle in a Clausal variable; it unifies like any other term.
- **Multiple handles**: each `Make*` call allocates a fresh handle; handles from `spline_derivative` are also independent and must be freed separately.
- **Thread safety**: the handle registry is protected by a lock; predicates are safe to call concurrently. See [free Threading](free_threading.md) for details.
- **interp1d deprecation**: `make_linear1d` wraps `scipy.interpolate.interp1d`, which is deprecated since SciPy 1.14. It fails gracefully if not available. Use `make_spline` with `K=1` for linear interpolation in new code.
- Predicates fail (yield no solution) when scipy raises an exception, or when a bound `RESULT` does not unify with the computed value.

---

*See also: [scipy.signal](scipy_signal.md) — signal processing · [scipy.special](scipy_special.md) — special functions for interpolation kernels.*
