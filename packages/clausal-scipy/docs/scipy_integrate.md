# scipy.integrate — Numerical Integration

The `scipy_integrate` module wraps [`scipy.integrate`](https://docs.scipy.org/doc/scipy/reference/integrate.html) as Clausal Prolog predicates. It covers adaptive quadrature (scalar and multi-dimensional), ODE solvers, and sampled-data integration methods.

---

## Import

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:import"
```

Or via the canonical `py.*` path:

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:import_ex2"
```

---

## Tiers

### Tier 1 — direct value

`cumulative_trapezoid`, `trapezoid`, and `simpson` return a NumPy array or scalar directly in `RESULT`.

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:tier_1"
```

### Tier 2 — result dict

Quadrature and ODE predicates (`quad`, `double_quad`, `triple_quad`, `n_quad`, `quad_vec`, `solve_initial_value_problem`, `ode_integrate`) return a Python dict in `RESULT`. Use `result_get(RESULT, FIELD, VALUE)` to extract individual fields.

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:tier_2"
```

---

## Naming conventions

Predicate names use full English words; scipy abbreviations are expanded:

| scipy function | Clausal Prolog predicate |
|---|---|
| `quad` | `quad` |
| `dblquad` | `double_quad` |
| `tplquad` | `triple_quad` |
| `nquad` | `n_quad` |
| `quad_vec` | `quad_vec` |
| `solve_ivp` | `solve_initial_value_problem` |
| `odeint` | `ode_integrate` |
| `cumulative_trapezoid` | `cumulative_trapezoid` |
| `trapezoid` | `trapezoid` |
| `simpson` | `simpson` |

---

## Predicate catalogue

### Scalar quadrature

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:scalar_quadrature"
```

Example:

```seam
-import_from(scipy_integrate, [quad, result_get])

integrate_sin(V) <- (
    quad(++(lambda x: __import__('math').sin(x)), ++(0.0), ++(3.14159265), RESULT),
    result_get(RESULT, 'value', V)
)
```

---

### Multi-dimensional quadrature

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:multi_dimensional_quadrature"
```

---

### ODE solvers

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:ode_solvers"
```

Example — exponential decay:

```seam
-import_from(scipy_integrate, [solve_initial_value_problem, result_get])

exponential_decay(T_FINAL, Y_FINAL) <- (
    solve_initial_value_problem(
        ++(lambda t, y: [-y[0]]),
        ++([0.0, float(T_FINAL)]),
        ++([1.0]),
        RESULT),
    result_get(RESULT, 'success', True),
    result_get(RESULT, 'y', Y),
    Y_FINAL is ++(float(Y[0, -1]))
)
```

---

### Sampled-data integration

These predicates operate on arrays of sample values.

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:sampled_data_integration"
```

Example:

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:sampled_data_integration_ex2"
```

---

### result_get

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:resultget"
```

Common fields by predicate:

| Predicate | Useful fields |
|---|---|
| `quad`, `double_quad`, `triple_quad`, `n_quad` | `'value'`, `'error'` |
| `quad_vec` | `'y'`, `'err'`, `'success'`, `'neval'`, `'message'` |
| `solve_initial_value_problem` | `'t'`, `'y'`, `'success'`, `'message'`, `'nfev'`, `'status'` |
| `ode_integrate` | `'y'` |

`'message'` is free-form text and comes back as a **string**
(`"The algorithm converged to the desired accuracy."`), not an atom.

---

## Complete examples

### Quadrature: integrate sin over [0, π]

```seam
-import_from(scipy_integrate, [quad, result_get])

sin_integral(VALUE) <- (
    quad(++(lambda x: __import__('math').sin(x)),
         ++(0.0),
         ++(3.14159265358979),
         RESULT),
    result_get(RESULT, 'value', VALUE)
)
```

### ODE: logistic growth

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:ode_logistic_growth"
```

### Sampled integration

```seam
--8<-- "tests/fixtures/docs/scipy_integrate_sigs.txt:sampled_integration"
```

---

## Dimensional analysis (Quantity support)

All integration predicates (except ODE solvers) are **quantity-aware**: when
inputs are [`Quantity(value, dims)`](units.md) objects, units are propagated through the
result automatically.

### Array-based quadrature

`trapezoid`, `simpson`, and `cumulative_trapezoid` compute output dims as:

| Form | Output dims |
|---|---|
| `trapezoid(Y, X, R)` | `y_dims + x_dims` |
| `trapezoid(Y, R)` | `y_dims` (unit spacing is dimensionless) |
| `simpson(Y, X, R)` | `y_dims + x_dims` |
| `cumulative_trapezoid(Y, X, R)` | `y_dims + x_dims` |

### Callable-based quadrature

`quad`, `quad_vec`, and other callable quadrature predicates use the same
probe-strip-wrap pattern as `scipy_differentiate`:

1. **Probe** — call `f(a)` once to discover whether `f` returns a `Quantity`.
2. **Strip and call** — pass `a.value`, `b.value` to scipy; if `f` is
   quantity-aware, re-wrap raw values before forwarding to `f`.
3. **Wrap output** — `value` and `error` fields get dims `f_dims + x_dims`.

### Fast path

when no input is a `Quantity`, scipy is called directly with **zero overhead**.

### ODE solvers (deferred)

`solve_initial_value_problem` and `ode_integrate` do not yet propagate units.
Their multi-variable state vectors and callable signatures require additional
design work (see `SCIPY_UNITS_PLAN.md` Phase 4c).

### Example

```
-import_from(scipy_integrate, [trapezoid, quad, result_get])
-import_from(py.units, [metre, second, newton, has_units])

% Velocity (m/s) integrated over time (s) gives displacement (m)
Test("trapezoid velocity times time") <- (
    trapezoid(++(numpy.array([0.0(metre/second), 10.0(metre/second), 20.0(metre/second)])),
              ++(numpy.array([0.0(second), 1.0(second), 2.0(second)])),
              R),
    has_units(R, metre))

% quad with quantity-aware function
Test("quad with units") <- (
    quad(++(lambda x: x * 1.0(newton/metre)),
         0.0(metre), 1.0(metre), RESULT),
    result_get(RESULT, 'value', V),
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
