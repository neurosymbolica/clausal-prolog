# scipy.integrate — Numerical Integration

The `scipy_integrate` module wraps [`scipy.integrate`](https://docs.scipy.org/doc/scipy/reference/integrate.html) as Clausal predicates. It covers adaptive quadrature (scalar and multi-dimensional), ODE solvers, and sampled-data integration methods.

---

## Import

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:import"
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:import_ex2"
```

---

## Tiers

### Tier 1 — direct value

`CumulativeTrapezoid`, `Trapezoid`, and `Simpson` return a NumPy array or scalar directly in `RESULT`.

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:tier_1"
```

### Tier 2 — result dict

Quadrature and ODE predicates (`Quad`, `DoubleQuad`, `TripleQuad`, `NQuad`, `QuadVec`, `SolveInitialValueProblem`, `OdeIntegrate`) return a Python dict in `RESULT`. Use `ResultGet(RESULT, FIELD, VALUE)` to extract individual fields.

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:tier_2"
```

---

## Naming conventions

Predicate names use full English words; scipy abbreviations are expanded:

| scipy function | Clausal predicate |
|---|---|
| `quad` | `Quad` |
| `dblquad` | `DoubleQuad` |
| `tplquad` | `TripleQuad` |
| `nquad` | `NQuad` |
| `quad_vec` | `QuadVec` |
| `solve_ivp` | `SolveInitialValueProblem` |
| `odeint` | `OdeIntegrate` |
| `cumulative_trapezoid` | `CumulativeTrapezoid` |
| `trapezoid` | `Trapezoid` |
| `simpson` | `Simpson` |

---

## Predicate catalogue

### Scalar quadrature

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:scalar_quadrature"
```

Example:

```clausal
-import_from(scipy_integrate, [Quad, ResultGet])

IntegrateSin(V) <- (
    Quad(++(lambda x: __import__('math').sin(x)), ++(0.0), ++(3.14159265), RESULT),
    ResultGet(RESULT, 'value', V)
)
```

---

### Multi-dimensional quadrature

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:multi_dimensional_quadrature"
```

---

### ODE solvers

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:ode_solvers"
```

Example — exponential decay:

```clausal
-import_from(scipy_integrate, [SolveInitialValueProblem, ResultGet])

ExponentialDecay(T_FINAL, Y_FINAL) <- (
    SolveInitialValueProblem(
        ++(lambda t, y: [-y[0]]),
        ++([0.0, float(T_FINAL)]),
        ++([1.0]),
        RESULT),
    ResultGet(RESULT, 'success', True),
    ResultGet(RESULT, 'y', Y),
    Y_FINAL is ++(float(Y[0, -1]))
)
```

---

### Sampled-data integration

These predicates operate on arrays of sample values.

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:sampled_data_integration"
```

Example:

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:sampled_data_integration_ex2"
```

---

### ResultGet

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:resultget"
```

Common fields by predicate:

| Predicate | Useful fields |
|---|---|
| `Quad`, `DoubleQuad`, `TripleQuad`, `NQuad` | `'value'`, `'error'` |
| `QuadVec` | `'y'`, `'err'`, `'success'`, `'neval'`, `'message'` |
| `SolveInitialValueProblem` | `'t'`, `'y'`, `'success'`, `'message'`, `'nfev'`, `'status'` |
| `OdeIntegrate` | `'y'` |

---

## Complete examples

### Quadrature: integrate sin over [0, π]

```clausal
-import_from(scipy_integrate, [Quad, ResultGet])

SinIntegral(VALUE) <- (
    Quad(++(lambda x: __import__('math').sin(x)),
         ++(0.0),
         ++(3.14159265358979),
         RESULT),
    ResultGet(RESULT, 'value', VALUE)
)
```

### ODE: logistic growth

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:ode_logistic_growth"
```

### Sampled integration

```clausal
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:sampled_integration"
```

---

## Dimensional analysis (Quantity support)

All integration predicates (except ODE solvers) are **quantity-aware**: when
inputs are [`Quantity(value, dims)`](units.md) objects, units are propagated through the
result automatically.

### Array-based quadrature

`Trapezoid`, `Simpson`, and `CumulativeTrapezoid` compute output dims as:

| Form | Output dims |
|---|---|
| `Trapezoid(Y, X, R)` | `y_dims + x_dims` |
| `Trapezoid(Y, R)` | `y_dims` (unit spacing is dimensionless) |
| `Simpson(Y, X, R)` | `y_dims + x_dims` |
| `CumulativeTrapezoid(Y, X, R)` | `y_dims + x_dims` |

### Callable-based quadrature

`Quad`, `QuadVec`, and other callable quadrature predicates use the same
probe-strip-wrap pattern as `scipy_differentiate`:

1. **Probe** — call `f(a)` once to discover whether `f` returns a `Quantity`.
2. **Strip and call** — pass `a.value`, `b.value` to scipy; if `f` is
   quantity-aware, re-wrap raw values before forwarding to `f`.
3. **Wrap output** — `value` and `error` fields get dims `f_dims + x_dims`.

### Fast path

when no input is a `Quantity`, scipy is called directly with **zero overhead**.

### ODE solvers (deferred)

`SolveInitialValueProblem` and `OdeIntegrate` do not yet propagate units.
Their multi-variable state vectors and callable signatures require additional
design work (see `SCIPY_UNITS_PLAN.md` Phase 4c).

### Example

```
-import_from(scipy_integrate, [Trapezoid, Quad, ResultGet])
-import_from(py.units, [metre, second, newton, has_units])

% Velocity (m/s) integrated over time (s) gives displacement (m)
Test("trapezoid velocity times time") <- (
    Trapezoid(++(numpy.array([0.0(metre/second), 10.0(metre/second), 20.0(metre/second)])),
              ++(numpy.array([0.0(second), 1.0(second), 2.0(second)])),
              R),
    has_units(R, metre))

% Quad with quantity-aware function
Test("quad with units") <- (
    Quad(++(lambda x: x * 1.0(newton/metre)),
         0.0(metre), 1.0(metre), RESULT),
    ResultGet(RESULT, 'value', V),
    has_units(V, newton))
```

---

## Notes

- **Callables**: pass Python functions via [`++()`](python_integration.md) — e.g. `++(lambda x: math.sin(x))`.
- **Array inputs**: Y0, T_SPAN, T_EVAL and sample arrays should be passed as Python lists or NumPy arrays via `++()`.
- **solve_ivp result shape**: `result['y']` has shape `(n_vars, n_timepoints)` — rows are variables, columns are time points. Access the last value of variable 0 as `y[0, -1]`.
- **odeint result shape**: `result['y']` has shape `(n_timepoints, n_vars)` — rows are time points, columns are variables. Access the last value of variable 0 as `y[-1, 0]`.
- Predicates fail (no solution) when scipy raises an exception, or when a bound `RESULT` does not unify with the computed value.

---

*See also: [scipy.differentiate](scipy_differentiate.md) — numerical differentiation · [scipy.optimize](scipy_optimize.md) — optimization using integrals.*
