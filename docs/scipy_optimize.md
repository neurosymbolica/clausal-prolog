# scipy.optimize — Optimisation

The `scipy_optimize` module wraps [`scipy.optimize`](https://docs.scipy.org/doc/scipy/reference/optimize.html) as Clausal predicates. It covers scalar and multivariate minimisation, global optimisation, least-squares fitting, curve fitting, root finding, and linear/mixed-integer programming.

---

## Import

```clausal
# skip
-import_from(scipy_optimize, [Minimize, MinimizeScalar, ResultGet, ...])
```

Or via the canonical `py.*` path:

```clausal
# skip
-import_from(py.scipy_optimize, [Minimize, MinimizeScalar, ...])
```

---

## Tiers

All optimisation predicates are **Tier 2**: RESULT is unified with a Python dict. Use `ResultGet(RESULT, FIELD, VALUE)` to extract individual fields.

```clausal
# skip
Minimize(++(lambda x: x[0]**2 + x[1]**2), ++([1.0, 1.0]), RESULT),
ResultGet(RESULT, 'x', X),
ResultGet(RESULT, 'success', OK).
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
# skip
MinimizeScalar(FUN, RESULT)
    Minimise a scalar function of one variable (Brent method by default).
    RESULT: dict {x, fun, success, message, nit, nfev}

MinimizeScalar(FUN, METHOD, RESULT)
    METHOD: 'brent' (default), 'golden', or 'bounded'

MinimizeScalar(FUN, METHOD, BOUNDS, RESULT)
    BOUNDS: (lower, upper) — required when METHOD='bounded'
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
# skip
Minimize(FUN, X0, RESULT)
    Minimise a multivariate function starting from X0 (BFGS by default).
    FUN:    Python callable accepting a 1-D array, returning a scalar
    X0:     initial guess (Python list or NumPy array)
    RESULT: dict {x, fun, jac, nfev, njev, nit, success, status, message}

Minimize(FUN, X0, METHOD, RESULT)
    METHOD: 'Nelder-Mead', 'Powell', 'CG', 'BFGS', 'L-BFGS-B',
            'TNC', 'COBYLA', 'SLSQP', 'trust-constr', and others

Minimize(FUN, X0, METHOD, OPTIONS, RESULT)
    OPTIONS: Python dict of solver options (e.g. {'maxiter': 1000, 'disp': False})
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
# skip
DifferentialEvolution(FUNC, BOUNDS, RESULT)
    BOUNDS: list of (min, max) pairs, one per variable
    RESULT: dict {x, fun, success, message, nit, nfev, ...}

DifferentialEvolution(FUNC, BOUNDS, SEED, RESULT)
    SEED: integer for reproducibility

BasinHopping(FUNC, X0, RESULT)
    X0:     initial guess (1-D array or list)
    RESULT: dict {x, fun, message, ...}

BasinHopping(FUNC, X0, ITERATIONS, RESULT)
    ITERATIONS: number of basin-hopping iterations (default 100)

DualAnnealing(FUNC, BOUNDS, RESULT)
    RESULT: dict {x, fun, success, message, nit, nfev, ...}

DualAnnealing(FUNC, BOUNDS, SEED, RESULT)

ShgoMinimize(FUNC, BOUNDS, RESULT)
    Simplicial Homology Global Optimisation.
    RESULT: dict {x, fun, success, message, ...}
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
# skip
NonlinearLeastSquares(FUN, X0, RESULT)
    Nonlinear least-squares minimisation of sum(FUN(x)**2).
    FUN:    callable returning a 1-D array of residuals
    X0:     initial parameter guess
    RESULT: dict {x, cost, fun, jac, grad, optimality,
                  active_mask, nfev, njev, status, message, success}

NonlinearLeastSquares(FUN, X0, BOUNDS, RESULT)
    BOUNDS: 2-tuple (lower_bounds, upper_bounds) for parameters

CurveFit(F, XDATA, YDATA, RESULT)
    Fit F(xdata, *params) to ydata using nonlinear least squares.
    F:      callable F(x, p1, p2, ...) → predicted y values
    RESULT: dict {popt, pcov}
              popt: optimal parameter values
              pcov: estimated covariance of popt

CurveFit(F, XDATA, YDATA, P0, RESULT)
    P0: initial parameter guess (list)
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
# skip
RootScalar(F, RESULT)
    Find a root of a scalar function.
    RESULT: dict {root, iterations, function_calls, converged, flag}

RootScalar(F, METHOD, RESULT)
    METHOD: 'bisect', 'brentq', 'brenth', 'ridder', 'toms748',
            'newton', 'secant', 'halley'

RootScalar(F, METHOD, BRACKET, RESULT)
    BRACKET: [lower, upper] — required for bracketing methods
             ('bisect', 'brentq', 'brenth', 'ridder', 'toms748')

RootScalar(F, METHOD, X0, X1, RESULT)
    X0, X1: starting points — used by iterative methods
            ('newton' uses X0; 'secant' uses X0 and X1)

Root(FUN, X0, RESULT)
    Find a root of a vector function FUN: R^n → R^n.
    X0:     initial guess (1-D array)
    RESULT: dict {x, fun, fjac, nfev, njev, status, success, message}

Root(FUN, X0, METHOD, RESULT)
    METHOD: 'hybr' (default), 'lm', 'broyden1', 'broyden2', 'anderson',
            'linearmixing', 'diagbroyden', 'excitingmixing', 'krylov', 'df-sane'
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
# skip
LinearProgram(C, RESULT)
    Minimise C @ x subject to x >= 0 (no constraints).
    C:      cost vector (1-D array)
    RESULT: OptimizeResult dict {x, fun, ineqlin, eqlin, status, success, message, nit}

LinearProgram(C, A_UB, B_UB, RESULT)
    Subject to A_UB @ x <= B_UB

LinearProgram(C, A_UB, B_UB, A_EQ, B_EQ, RESULT)
    Subject to A_UB @ x <= B_UB and A_EQ @ x == B_EQ

LinearProgram(C, A_UB, B_UB, A_EQ, B_EQ, BOUNDS, RESULT)
    BOUNDS: sequence of (lower, upper) per variable (None means unbounded)

MixedIntegerLinearProgram(C, RESULT)
    Minimise C @ x with all variables continuous (no constraints).
    RESULT: OptimizeResult dict {x, fun, mip_node_count, mip_dual_bound,
                                  mip_gap, status, success, message}

MixedIntegerLinearProgram(C, CONSTRAINTS, INTEGRALITY, BOUNDS, RESULT)
    CONSTRAINTS:  LinearConstraint object (from LinearConstraint predicate)
    INTEGRALITY:  array: 0 = continuous, 1 = integer per variable
    BOUNDS:       Bounds object (from Bounds predicate)

LinearConstraint(A, LB, UB, RESULT)
    Create a scipy.optimize.LinearConstraint object.
    LB <= A @ x <= UB
    Passes RESULT to MixedIntegerLinearProgram as CONSTRAINTS=

Bounds(LB, UB, RESULT)
    Create a scipy.optimize.Bounds object.
    LB <= x <= UB element-wise
    Passes RESULT to LinearProgram or MixedIntegerLinearProgram as BOUNDS=
```

Example — two-variable LP:

```clausal
# skip
-import_from(scipy_optimize, [LinearProgram, ResultGet])

# Maximise x1 + 2*x2 subject to x1 + x2 <= 4, x1,x2 >= 0
# equivalent to: minimise -x1 - 2*x2
LpSolution(X) <- (
    LinearProgram(++([-1.0, -2.0]), ++([[1.0, 1.0]]), ++([4.0]), RESULT),
    ResultGet(RESULT, 'x', X)
)
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
# skip
ResultGet(RESULT, FIELD, VALUE)
    Extract a named field from any Tier 2 result dict.
    RESULT: a dict returned by a Tier 2 predicate
    FIELD:  a ground string key (e.g. 'x', 'fun', 'success', 'root', 'popt')
    VALUE:  unified with RESULT[FIELD]
    Fails if RESULT is not subscriptable, FIELD is absent, or VALUE does not unify.
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
# skip
-import_from(scipy_optimize, [Minimize, ResultGet])

# The Rosenbrock function — minimum at (1, 1) with value 0
Rosenbrock(X, Y) <-
    (X - 1.0)**2 + 100.0 * (Y - X**2)**2.

RosenbrockMin(X, Y) <- (
    Minimize(
        ++(lambda v: (v[0] - 1.0)**2 + 100.0*(v[1] - v[0]**2)**2),
        ++([0.0, 0.0]),
        'L-BFGS-B',
        RESULT),
    ResultGet(RESULT, 'x', V),
    X is ++float(V[0]),
    Y is ++float(V[1])
)
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
