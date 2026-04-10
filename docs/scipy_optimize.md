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

All optimisation predicates are **Tier 2**: RESULT is unified with a Python dict. Use `ResultGet(RESULT, FIELD, VALUE)` to extract individual fields.

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:tiers"
```

`LinearConstraint` and `Bounds` are helper object constructors whose RESULT is an opaque scipy object passed back to `MixedIntegerLinearProgram` or `LinearProgram`.

---

## Naming conventions

Predicate names use full English words; scipy's abbreviations are expanded:

| scipy function | Clausal predicate |
|---|---|
| `minimize_scalar` | `MinimizeScalar` |
| `minimize` | `Minimize` |
| `differential_evolution` | `DifferentialEvolution` |
| `basinhopping` | `BasinHopping` |
| `dual_annealing` | `DualAnnealing` |
| `shgo` | `ShgoMinimize` |
| `least_squares` | `NonlinearLeastSquares` |
| `curve_fit` | `CurveFit` |
| `root_scalar` | `RootScalar` |
| `root` | `Root` |
| `linprog` | `LinearProgram` |
| `milp` | `MixedIntegerLinearProgram` |
| `LinearConstraint` | `LinearConstraint` |
| `Bounds` | `Bounds` |

`NonlinearLeastSquares` is named to distinguish it from `LeastSquares` in `scipy_linalg` (which is linear least squares via `lstsq`).
`ShgoMinimize` expands the acronym SHGO (Simplicial Homology Global Optimization) while indicating its role.

---

## Predicate catalogue

### Scalar minimisation

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:scalar_minimisation"
```

Example:

```clausal
MinimizeQuadratic(RESULT) <- (
    MinimizeScalar(++(lambda x: (x - 3.0)**2), RESULT),
    ResultGet(RESULT, 'x', X),
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
-import_from(scipy_optimize, [Minimize, ResultGet])

RosenbrockMinimum(X) <- (
    Minimize(++(lambda x: (1 - x[0])**2 + 100*(x[1] - x[0]**2)**2),
             ++([0.0, 0.0]), 'L-BFGS-B', RESULT),
    ResultGet(RESULT, 'x', X)
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
GlobalMin(X) <- (
    DifferentialEvolution(
        ++(lambda x: x[0]**2 * __import__('math').sin(4*x[0])),
        ++([ (-10, 10) ]),
        42,
        RESULT),
    ResultGet(RESULT, 'x', X)
)
```

---

### Least-squares and curve fitting

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:least_squares_and_curve_fitting"
```

Example — fit an exponential decay:

```clausal
-import_from(scipy_optimize, [CurveFit, ResultGet])

FitDecay(XDATA, YDATA, PARAMS) <- (
    CurveFit(++(lambda x, a, b: a * __import__('numpy').exp(-b * x)),
             XDATA, YDATA, ++([1.0, 0.5]), RESULT),
    ResultGet(RESULT, 'popt', PARAMS)
)
```

---

### Root finding

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:root_finding"
```

Example:

```clausal
-import_from(scipy_optimize, [RootScalar, ResultGet])

SquareRoot(N, ROOT) <- (
    N > 0,
    RootScalar(++(lambda x: x**2 - float(N)),
               'brentq', ++([0.0, float(N) + 1.0]), RESULT),
    ResultGet(RESULT, 'root', ROOT)
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
-import_from(scipy_optimize, [MixedIntegerLinearProgram, LinearConstraint, Bounds, ResultGet])

IntegerPlan(X) <- (
    LinearConstraint(++([[1.0, 1.0]]), ++([0.0]), ++([4.0]), CON),
    Bounds(++([0.0, 0.0]), ++([3.0, 3.0]), BDS),
    MixedIntegerLinearProgram(++([-1.0, -2.0]), CON, ++([1, 1]), BDS, RESULT),
    ResultGet(RESULT, 'x', X)
)
```

---

### ResultGet

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:resultget"
```

Common fields by predicate:

| Predicate | Useful fields |
|---|---|
| `Minimize`, `MinimizeScalar` | `'x'`, `'fun'`, `'success'`, `'message'`, `'nit'` |
| `DifferentialEvolution`, `DualAnnealing`, `ShgoMinimize` | `'x'`, `'fun'`, `'success'` |
| `BasinHopping` | `'x'`, `'fun'`, `'message'` |
| `NonlinearLeastSquares` | `'x'`, `'cost'`, `'fun'`, `'success'` |
| `CurveFit` | `'popt'`, `'pcov'` |
| `RootScalar` | `'root'`, `'converged'`, `'iterations'` |
| `Root` | `'x'`, `'fun'`, `'success'` |
| `LinearProgram`, `MixedIntegerLinearProgram` | `'x'`, `'fun'`, `'success'`, `'message'` |

---

## Complete example — Rosenbrock with gradient descent

```clausal
--8<-- "tests/fixtures/docs/scipy_optimize_sigs.txt:complete_example"
```

---

## Notes

- **Callables**: pass Python functions via the [`++()` escape](python_integration.md) — e.g. `FUN=++(lambda x: x[0]**2)`. The predicate receives and passes on a plain Python callable; no special boundary wrapping is needed.
- **Array inputs**: X0, BOUNDS, and coefficient arrays should be passed as Python lists or NumPy arrays via `++()`.
- **Global methods** (`DifferentialEvolution`, `DualAnnealing`, `BasinHopping`, `ShgoMinimize`) are stochastic or slow; pass `SEED=` for reproducibility in tests.
- **`NonlinearLeastSquares` vs `LeastSquares`**: `NonlinearLeastSquares` (from `scipy_optimize`) minimises `||fun(x)||²` for a nonlinear `fun`. `LeastSquares` (from [`scipy_linalg`](scipy_linalg.md)) solves the linear system `A @ x ≈ b` via `lstsq`. They are different operations.
- Predicates fail (no solution) when `ResultGet` cannot find the requested field, or when a bound `RESULT` does not unify with the computed value. Scipy exceptions propagate as Python exceptions.

---

*See also: [scipy.linalg](scipy_linalg.md) — linear algebra solvers used internally by optimizers.*
