# scipy.optimize — Optimisation

The `scipy_optimize` module wraps [`scipy.optimize`](https://docs.scipy.org/doc/scipy/reference/optimize.html) as Clausal predicates. It covers scalar and multivariate minimisation, global optimisation, least-squares fitting, curve fitting, root finding, and linear/mixed-integer programming.

---

## Import

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:import"
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:import_ex2"
```

---

## Tiers

All optimisation predicates are **Tier 2**: RESULT is unified with a Python dict. Use `result_get(RESULT, FIELD, VALUE)` to extract individual fields.

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:tiers"
```

`linear_constraint` and `bounds` are helper object constructors whose RESULT is an opaque scipy object passed back to `mixed_integer_linear_program` or `linear_program`.

---

## Naming conventions

Predicate names use full English words; scipy's abbreviations are expanded:

| scipy function | Clausal predicate |
|---|---|
| `minimize_scalar` | `minimize_scalar` |
| `minimize` | `minimize` |
| `differential_evolution` | `differential_evolution` |
| `basinhopping` | `basin_hopping` |
| `dual_annealing` | `dual_annealing` |
| `shgo` | `shgo_minimize` |
| `least_squares` | `nonlinear_least_squares` |
| `curve_fit` | `curve_fit` |
| `root_scalar` | `root_scalar` |
| `root` | `root` |
| `linprog` | `linear_program` |
| `milp` | `mixed_integer_linear_program` |
| `linear_constraint` | `linear_constraint` |
| `bounds` | `bounds` |

`nonlinear_least_squares` is named to distinguish it from `least_squares` in `scipy_linalg` (which is linear least squares via `lstsq`).
`shgo_minimize` expands the acronym SHGO (Simplicial Homology Global Optimization) while indicating its role.

---

## Predicate catalogue

### Scalar minimisation

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:scalar_minimisation"
```

Example:

```clausal
minimize_quadratic(RESULT) <- (
    minimize_scalar(++(lambda x: (x - 3.0)**2), RESULT),
    result_get(RESULT, 'x', X),
    ++print(f"minimum at x={float(X):.4f}")
)
```

---

### Multivariate minimisation

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:multivariate_minimisation"
```

Example:

```clausal
-import_from(scipy_optimize, [minimize, result_get])

rosenbrock_minimum(X) <- (
    minimize(++(lambda x: (1 - x[0])**2 + 100*(x[1] - x[0]**2)**2),
             ++([0.0, 0.0]), 'L-BFGS-B', RESULT),
    result_get(RESULT, 'x', X)
)
```

---

### Global optimisation

These methods search for a global minimum and do not require a gradient.

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:global_optimisation"
```

Example — find global minimum of a multi-modal function:

```clausal
global_min(X) <- (
    differential_evolution(
        ++(lambda x: x[0]**2 * __import__('math').sin(4*x[0])),
        ++([ (-10, 10) ]),
        42,
        RESULT),
    result_get(RESULT, 'x', X)
)
```

---

### Least-squares and curve fitting

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:least_squares_and_curve_fitting"
```

Example — fit an exponential decay:

```clausal
-import_from(scipy_optimize, [curve_fit, result_get])

fit_decay(XDATA, YDATA, PARAMS) <- (
    curve_fit(++(lambda x, a, b: a * __import__('numpy').exp(-b * x)),
             XDATA, YDATA, ++([1.0, 0.5]), RESULT),
    result_get(RESULT, 'popt', PARAMS)
)
```

---

### root finding

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:root_finding"
```

Example:

```clausal
-import_from(scipy_optimize, [root_scalar, result_get])

square_root(N, ROOT) <- (
    N > 0,
    root_scalar(++(lambda x: x**2 - float(N)),
               'brentq', ++([0.0, float(N) + 1.0]), RESULT),
    result_get(RESULT, 'root', ROOT)
)
```

---

### Linear and mixed-integer programming

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:linear_and_mixed_integer_programming"
```

Example — two-variable LP:

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:linear_and_mixed_integer_programming_ex2"
```

Example — MILP with integrality constraints:

```clausal
-import_from(scipy_optimize, [mixed_integer_linear_program, linear_constraint, bounds, result_get])

integer_plan(X) <- (
    linear_constraint(++([[1.0, 1.0]]), ++([0.0]), ++([4.0]), CON),
    bounds(++([0.0, 0.0]), ++([3.0, 3.0]), BDS),
    mixed_integer_linear_program(++([-1.0, -2.0]), CON, ++([1, 1]), BDS, RESULT),
    result_get(RESULT, 'x', X)
)
```

---

### result_get

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:resultget"
```

Common fields by predicate:

| Predicate | Useful fields |
|---|---|
| `minimize`, `minimize_scalar` | `'x'`, `'fun'`, `'success'`, `'message'`, `'nit'` |
| `differential_evolution`, `dual_annealing`, `shgo_minimize` | `'x'`, `'fun'`, `'success'` |
| `basin_hopping` | `'x'`, `'fun'`, `'message'` |
| `nonlinear_least_squares` | `'x'`, `'cost'`, `'fun'`, `'success'` |
| `curve_fit` | `'popt'`, `'pcov'` |
| `root_scalar` | `'root'`, `'converged'`, `'iterations'` |
| `root` | `'x'`, `'fun'`, `'success'` |
| `linear_program`, `mixed_integer_linear_program` | `'x'`, `'fun'`, `'success'`, `'message'` |

---

## Complete example — Rosenbrock with gradient descent

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:complete_example"
```

---

## Notes

- **Callables**: pass Python functions via the [`++()` escape](python_integration.md) — e.g. `FUN=++(lambda x: x[0]**2)`. The predicate receives and passes on a plain Python callable; no special boundary wrapping is needed.
- **Array inputs**: X0, BOUNDS, and coefficient arrays should be passed as Python lists or NumPy arrays via `++()`.
- **Global methods** (`differential_evolution`, `dual_annealing`, `basin_hopping`, `shgo_minimize`) are stochastic or slow; pass `SEED=` for reproducibility in tests.
- **`nonlinear_least_squares` vs `least_squares`**: `nonlinear_least_squares` (from `scipy_optimize`) minimises `||fun(x)||²` for a nonlinear `fun`. `least_squares` (from [`scipy_linalg`](scipy_linalg.md)) solves the linear system `A @ x ≈ b` via `lstsq`. They are different operations.
- Predicates fail (no solution) when `result_get` cannot find the requested field, or when a bound `RESULT` does not unify with the computed value. Scipy exceptions propagate as Python exceptions.

---

*See also: [scipy.linalg](scipy_linalg.md) — linear algebra solvers used internally by optimizers.*
