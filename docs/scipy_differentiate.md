# scipy.differentiate — Numerical Differentiation

The `scipy_differentiate` module wraps [`scipy.differentiate`](https://docs.scipy.org/doc/scipy/reference/differentiate.html) as Clausal predicates. It provides high-accuracy numerical derivatives, Jacobians, and Hessians using Richardson extrapolation.

---

## Import

```
-import_from(scipy_differentiate, [Derivative, Jacobian, Hessian, ResultGet])
```

Or via the canonical `py.*` path:

```
-import_from(py.scipy_differentiate, [Derivative, Jacobian, Hessian, ResultGet])
```

---

## Tier

All predicates are **Tier 2 — result record**: they return a dict with named fields that can be accessed via `ResultGet`. The predicate always succeeds if SciPy can evaluate the function; a `success` field in the result indicates whether the requested accuracy was achieved.

---

## Naming conventions

The `Diff` prefix from the spec is dropped since these predicates live in the `scipy_differentiate` module. No abbreviations are used.

| scipy function | Clausal predicate |
|---|---|
| `differentiate.derivative` | `Derivative` |
| `differentiate.jacobian` | `Jacobian` |
| `differentiate.hessian` | `Hessian` |

---

## Predicate catalogue

### `Derivative(F, X, RESULT)`
### `Derivative(F, X, ARGS, RESULT)`

Compute the scalar derivative of `F` at point `X` using Richardson extrapolation.

- `F`: a callable `f(x)` or `f(x, *args)` — must accept NumPy scalar inputs (use `numpy.sin`, not `math.sin`)
- `X`: scalar evaluation point (float or numpy scalar)
- `ARGS`: optional list of extra positional arguments to pass to `F`
- `RESULT`: result dict — see fields below

```
Derivative(++(numpy.sin), 0.0, R),
ResultGet(R, 'df', DF)   % DF ≈ 1.0

Derivative(++(lambda x, a: a*x**2), 3.0, [5.0], R),
ResultGet(R, 'df', DF)   % DF ≈ 30.0 (d/dx 5x² = 10x; at x=3 → 30)
```

**Result fields**:

| field | description |
|---|---|
| `'x'` | evaluation point (echo of `X`) |
| `'df'` | derivative value |
| `'error'` | estimated absolute error |
| `'success'` | `True` if requested tolerance was achieved |
| `'status'` | integer status code (0 = success) |
| `'nfev'` | number of function evaluations |
| `'nit'` | number of Richardson extrapolation iterations |

---

### `Jacobian(F, X, RESULT)`

Compute the Jacobian matrix of a vector-valued function `F` at point `X`.

- `F`: a callable `f(x)` returning a 1-D NumPy array — must accept NumPy array inputs
- `X`: 1-D NumPy array of shape `(n,)`
- `RESULT`: result dict — see fields below

```
Jacobian(++(lambda x: numpy.array([x[0]**2, x[1]**3])),
         ++(numpy.array([2.0, 3.0])), R),
ResultGet(R, 'df', J)   % J ≈ [[4, 0], [0, 27]]
```

**Result fields** (note: `'x'` and `'nit'` are not present for Jacobian):

| field | description |
|---|---|
| `'df'` | Jacobian matrix (ndarray, shape `(m, n)`) |
| `'error'` | estimated error (ndarray, same shape as `df`) |
| `'success'` | bool array (same shape as `df`), `True` per element where tolerance met |
| `'status'` | integer status code array |
| `'nfev'` | number of function evaluations |

---

### `Hessian(F, X, RESULT)`

Compute the Hessian matrix of a scalar-valued function `F` at point `X`.

- `F`: a callable `f(x)` returning a scalar — must accept NumPy array inputs
- `X`: 1-D NumPy array of shape `(n,)`
- `RESULT`: result dict — see fields below

```
Hessian(++(lambda x: x[0]**2 + x[1]**2),
        ++(numpy.array([1.0, 2.0])), R),
ResultGet(R, 'ddf', H)  % H ≈ [[2, 0], [0, 2]]
```

**Result fields** (note: `'x'`, `'nit'`, and `'nfev'` are not present for Hessian):

| field | description |
|---|---|
| `'ddf'` | Hessian matrix (ndarray, shape `(n, n)`) |
| `'error'` | estimated error (ndarray, same shape as `ddf`) |
| `'success'` | bool array, `True` per element where tolerance met |
| `'status'` | integer status code array |

---

### `ResultGet(RESULT, FIELD, VALUE)`

Extract a named field from a differentiation result dict.

- `RESULT`: a result dict returned by `Derivative`, `Jacobian`, or `Hessian`
- `FIELD`: string key — one of the field names listed above
- `VALUE`: unified with `RESULT[FIELD]`

Fails if `FIELD` is not present in `RESULT`.

```
Derivative(++(lambda x: x**3), 2.0, R),
ResultGet(R, 'df', DF),    % DF ≈ 12.0
ResultGet(R, 'error', ERR) % ERR is the estimated error
```

---

## Example

```
-import_from(scipy_differentiate, [Derivative, Jacobian, ResultGet])
-import_from(numpy, [Array])

% Numerical derivative of x³ at x = 2 (exact answer: 12)
CubeDerivative(DF) <-
    Derivative(++(lambda x: x**3), 2.0, R),
    ResultGet(R, 'df', DF).

% Jacobian of f(x) = [x₀², x₁³] at [1, 2]
QuadraticJacobian(J) <-
    F is ++(lambda x: __import__('numpy').array([x[0]**2, x[1]**3])),
    X is ++(__import__('numpy').array([1.0, 2.0])),
    Jacobian(F, X, R),
    ResultGet(R, 'df', J).
```

---

## Notes

### NumPy-compatible functions
`scipy.differentiate` evaluates functions with NumPy scalar or array inputs internally. Always use NumPy equivalents:
- Use `numpy.sin`, `numpy.exp`, `numpy.log` — not `math.sin`, `math.exp`, `math.log`
- Lambda functions like `lambda x: x**2` work fine since `**` is overloaded for NumPy scalars

### Partial failures
For `Jacobian` and `Hessian`, `success` is a boolean array — some elements may be `False` if the function is poorly conditioned at that point. The predicate still succeeds; inspect the `success` field to determine which elements converged.

### `success=False` policy
Following the cross-cutting convention in `SCIPY_PORT.md`: a result with `success=False` still allows the predicate to succeed. The caller checks the `success` field. This makes it possible to inspect partial results.
