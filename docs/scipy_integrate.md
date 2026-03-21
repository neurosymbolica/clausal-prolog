# scipy.integrate — Numerical Integration

The `scipy_integrate` module wraps [`scipy.integrate`](https://docs.scipy.org/doc/scipy/reference/integrate.html) as Clausal predicates. It covers adaptive quadrature (scalar and multi-dimensional), ODE solvers, and sampled-data integration methods.

---

## Import

```clausal
-import_from(scipy_integrate, [Quad, Trapezoid, SolveInitialValueProblem, ResultGet, ...])
```

Or via the canonical `py.*` path:

```clausal
-import_from(py.scipy_integrate, [Quad, Trapezoid, ...])
```

---

## Tiers

### Tier 1 — direct value

`CumulativeTrapezoid`, `Trapezoid`, and `Simpson` return a NumPy array or scalar directly in `RESULT`.

```clausal
Trapezoid(++([1.0, 2.0, 3.0]), RESULT),
% RESULT is unified with 4.0
```

### Tier 2 — result dict

Quadrature and ODE predicates (`Quad`, `DoubleQuad`, `TripleQuad`, `NQuad`, `QuadVec`, `SolveInitialValueProblem`, `OdeIntegrate`) return a Python dict in `RESULT`. Use `ResultGet(RESULT, FIELD, VALUE)` to extract individual fields.

```clausal
Quad(++(lambda x: __import__('math').sin(x)), ++(0.0), ++(3.14159), RESULT),
ResultGet(RESULT, 'value', V),
ResultGet(RESULT, 'error', E).
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
Quad(FUNC, A, B, RESULT)
    Adaptive integration of FUNC(x) from A to B (QUADPACK DQAGS/DQAGSE).
    RESULT: dict {value, error}

Quad(FUNC, A, B, ARGS, RESULT)
    ARGS: tuple of extra arguments passed to FUNC as FUNC(x, *ARGS).

Quad(FUNC, A, B, ARGS, LIMIT, EPSABS, EPSREL, RESULT)
    LIMIT:  max number of sub-intervals (default 50)
    EPSABS: absolute error tolerance (default 1.49e-8)
    EPSREL: relative error tolerance (default 1.49e-8)
```

Example:

```clausal
-import_from(scipy_integrate, [Quad, ResultGet])

IntegrateSin(V) <- (
    Quad(++(lambda x: __import__('math').sin(x)), ++(0.0), ++(3.14159265), RESULT) and
    ResultGet(RESULT, 'value', V)
)
```

---

### Multi-dimensional quadrature

```clausal
DoubleQuad(FUNC, A, B, GFUN, HFUN, RESULT)
    Double integral of FUNC(y, x) over a<=x<=b, gfun(x)<=y<=hfun(x).
    FUNC:  callable FUNC(y, x) → scalar
    GFUN, HFUN: lower/upper y-limit functions (callables or constants)
    RESULT: dict {value, error}

DoubleQuad(FUNC, A, B, GFUN, HFUN, EPSABS, EPSREL, RESULT)

TripleQuad(FUNC, A, B, GFUN, HFUN, QFUN, RFUN, RESULT)
    Triple integral of FUNC(z, y, x).
    QFUN, RFUN: lower/upper z-limit functions
    RESULT: dict {value, error}

NQuad(FUNC, RANGES, RESULT)
    N-dimensional integration via iterated quad.
    RANGES: list of [lower, upper] pairs, one per variable
    RESULT: dict {value, error}

NQuad(FUNC, RANGES, ARGS, RESULT)
    ARGS: extra arguments for FUNC.

QuadVec(FUNC, A, B, RESULT)
    Adaptive integration of a vector-valued or scalar function.
    RESULT: dict {y, err, status, success, message, neval}
```

---

### ODE solvers

```clausal
SolveInitialValueProblem(FUN, T_SPAN, Y0, RESULT)
    Solve dy/dt = FUN(t, y), y(T_SPAN[0]) = Y0, integrate to T_SPAN[1].
    FUN:    callable FUN(t, y) → array of derivatives
    T_SPAN: [t0, tf] — integration interval
    Y0:     initial state (list or array)
    RESULT: dict {t, y, sol, t_events, y_events, nfev, njev, nlu,
                  status, message, success}
    Note: result.y has shape (n_vars, n_timepoints); y[i, -1] is final
          value of variable i.

SolveInitialValueProblem(FUN, T_SPAN, Y0, METHOD, RESULT)
    METHOD: 'RK45' (default), 'RK23', 'DOP853', 'Radau', 'BDF', 'LSODA'

SolveInitialValueProblem(FUN, T_SPAN, Y0, METHOD, T_EVAL, RESULT)
    T_EVAL: array of time points at which to evaluate the solution.

OdeIntegrate(FUNC, Y0, T, RESULT)
    Integrate dy/dt = FUNC(y, t) using LSODA (legacy interface).
    FUNC:   callable FUNC(y, t) → array
    Y0:     initial state
    T:      array of time points (result includes all these points)
    RESULT: dict {y} where y has shape (len(T), n_vars)

OdeIntegrate(FUNC, Y0, T, ARGS, RESULT)
    ARGS: tuple of extra arguments for FUNC.
```

Example — exponential decay:

```clausal
-import_from(scipy_integrate, [SolveInitialValueProblem, ResultGet])

ExponentialDecay(T_FINAL, Y_FINAL) <- (
    SolveInitialValueProblem(
        ++(lambda t, y: [-y[0]]),
        ++([0.0, float(T_FINAL)]),
        ++([1.0]),
        RESULT) and
    ResultGet(RESULT, 'success', True) and
    ResultGet(RESULT, 'y', Y) and
    Y_FINAL is ++(float(Y[0, -1]))
)
```

---

### Sampled-data integration

These predicates operate on arrays of sample values.

```clausal
CumulativeTrapezoid(Y, RESULT)
    Cumulatively integrate Y using the composite trapezoidal rule.
    Y:      1-D array of sample values (uniform spacing dx=1)
    RESULT: array of length len(Y)-1

CumulativeTrapezoid(Y, X, RESULT)
    X: sample positions (non-uniform spacing allowed)

Trapezoid(Y, RESULT)
    Total trapezoidal integration of Y (uniform dx=1).
    RESULT: scalar

Trapezoid(Y, X, RESULT)
    X: sample positions.

Simpson(Y, RESULT)
    Total integration using composite Simpson's rule (uniform dx=1).
    Requires an odd number of sample points (even number of sub-intervals).
    RESULT: scalar

Simpson(Y, X, RESULT)
    X: sample positions.
```

Example:

```clausal
-import_from(scipy_integrate, [Trapezoid, CumulativeTrapezoid])

TrapezoidIntegral(Y, RESULT) <- Trapezoid(Y, RESULT).

CumulativeIntegral(Y, CUMULATIVE) <- CumulativeTrapezoid(Y, CUMULATIVE).
```

---

### ResultGet

```clausal
ResultGet(RESULT, FIELD, VALUE)
    Extract a named field from any Tier 2 result dict.
    RESULT: dict returned by a Tier 2 predicate
    FIELD:  a ground string key
    VALUE:  unified with RESULT[FIELD]
    Fails if RESULT is not subscriptable, FIELD is absent, or VALUE does not unify.
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
         RESULT) and
    ResultGet(RESULT, 'value', VALUE)
)
```

### ODE: logistic growth

```clausal
-import_from(scipy_integrate, [SolveInitialValueProblem, ResultGet])

% dy/dt = r*y*(1 - y/K), y(0) = y0
LogisticGrowth(R, K, Y0, T_FINAL, Y_FINAL) <- (
    SolveInitialValueProblem(
        ++(lambda t, y: [R * y[0] * (1.0 - y[0] / K)]),
        ++([0.0, float(T_FINAL)]),
        ++([float(Y0)]),
        'RK45',
        RESULT) and
    ResultGet(RESULT, 'success', True) and
    ResultGet(RESULT, 'y', Y) and
    Y_FINAL is ++(float(Y[0, -1]))
)
```

### Sampled integration

```clausal
-import_from(scipy_integrate, [Trapezoid, Simpson, CumulativeTrapezoid])

% Integrate a sampled signal using multiple methods
CompareIntegrals(Y, TRAP, SIMP) <- (
    Trapezoid(Y, TRAP) and
    Simpson(Y, SIMP)
)
```

---

## Notes

- **Callables**: pass Python functions via `++()` — e.g. `++(lambda x: math.sin(x))`.
- **Array inputs**: Y0, T_SPAN, T_EVAL and sample arrays should be passed as Python lists or NumPy arrays via `++()`.
- **solve_ivp result shape**: `result['y']` has shape `(n_vars, n_timepoints)` — rows are variables, columns are time points. Access the last value of variable 0 as `y[0, -1]`.
- **odeint result shape**: `result['y']` has shape `(n_timepoints, n_vars)` — rows are time points, columns are variables. Access the last value of variable 0 as `y[-1, 0]`.
- Predicates fail (no solution) when scipy raises an exception, or when a bound `RESULT` does not unify with the computed value.
