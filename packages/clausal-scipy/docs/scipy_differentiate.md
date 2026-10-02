# scipy.differentiate — Numerical Differentiation

The `scipy_differentiate` module wraps [`scipy.differentiate`](https://docs.scipy.org/doc/scipy/reference/differentiate.html) as Clausal predicates. It provides high-accuracy numerical derivatives, Jacobians, and Hessians using Richardson extrapolation.

---

## Import

```clausal
-import_from(scipy_differentiate, [derivative, jacobian, hessian, result_get])
```

---

## Tier

All predicates are **Tier 2 — result record**: they return a dict with named fields that can be accessed via `result_get`. The predicate always succeeds if SciPy can evaluate the function; a `success` field in the result indicates whether the requested accuracy was achieved.

---

## Naming conventions

The `Diff` prefix from the spec is dropped since these predicates live in the `scipy_differentiate` module. No abbreviations are used.

| scipy function | Clausal predicate |
|---|---|
| `differentiate.derivative` | `derivative` |
| `differentiate.jacobian` | `jacobian` |
| `differentiate.hessian` | `hessian` |

---

## Predicate catalogue

### `derivative(F, X, RESULT)`
### `derivative(F, X, ARGS, RESULT)`

Compute the scalar derivative of `F` at point `X` using Richardson extrapolation.

- `F`: a callable `f(x)` or `f(x, *args)` — must accept NumPy scalar inputs (use `numpy.sin`, not `math.sin`)
- `X`: scalar evaluation point (float or numpy scalar)
- `ARGS`: optional list of extra positional arguments to pass to `F`
- `RESULT`: result dict — see fields below

```clausal
--8<-- "tests/fixtures/docs/scipy_differentiate_sigs.txt:derivative"
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

### `jacobian(F, X, RESULT)`

Compute the jacobian matrix of a vector-valued function `F` at point `X`.

- `F`: a callable `f(x)` returning a 1-D NumPy array — must accept NumPy array inputs
- `X`: 1-D NumPy array of shape `(n,)`
- `RESULT`: result dict — see fields below

```clausal
--8<-- "tests/fixtures/docs/scipy_differentiate_sigs.txt:jacobian"
```

**Result fields** (note: `'x'` and `'nit'` are not present for jacobian):

| field | description |
|---|---|
| `'df'` | jacobian matrix (ndarray, shape `(m, n)`) |
| `'error'` | estimated error (ndarray, same shape as `df`) |
| `'success'` | bool array (same shape as `df`), `True` per element where tolerance met |
| `'status'` | integer status code array |
| `'nfev'` | number of function evaluations |

---

### `hessian(F, X, RESULT)`

Compute the hessian matrix of a scalar-valued function `F` at point `X`.

- `F`: a callable `f(x)` returning a scalar — must accept NumPy array inputs
- `X`: 1-D NumPy array of shape `(n,)`
- `RESULT`: result dict — see fields below

```clausal
--8<-- "tests/fixtures/docs/scipy_differentiate_sigs.txt:hessian"
```

**Result fields** (note: `'x'`, `'nit'`, and `'nfev'` are not present for hessian):

| field | description |
|---|---|
| `'ddf'` | hessian matrix (ndarray, shape `(n, n)`) |
| `'error'` | estimated error (ndarray, same shape as `ddf`) |
| `'success'` | bool array, `True` per element where tolerance met |
| `'status'` | integer status code array |

---

### `result_get(RESULT, FIELD, VALUE)`

Extract a named field from a differentiation result dict.

- `RESULT`: a result dict returned by `derivative`, `jacobian`, or `hessian`
- `FIELD`: string key — one of the field names listed above
- `VALUE`: unified with `RESULT[FIELD]`

Fails if `FIELD` is not present in `RESULT`.

```clausal
--8<-- "tests/fixtures/docs/scipy_differentiate_sigs.txt:resultget"
```

---

## Example

```clausal
--8<-- "tests/fixtures/docs/scipy_differentiate_sigs.txt:example"
```

---

## Notes

### NumPy-compatible functions
`scipy.differentiate` evaluates functions with NumPy scalar or array inputs internally. Always use NumPy equivalents:
- Use `numpy.sin`, `numpy.exp`, `numpy.log` — not `math.sin`, `math.exp`, `math.log`
- Lambda functions like `lambda x: x**2` work fine since `**` is overloaded for NumPy scalars

### Partial failures
For `jacobian` and `hessian`, `success` is a boolean array — some elements may be `False` if the function is poorly conditioned at that point. The predicate still succeeds; inspect the `success` field to determine which elements converged.

### `success=False` policy
Following the cross-cutting convention in `SCIPY_PORT.md`: a result with `success=False` still allows the predicate to succeed. The caller checks the `success` field. This makes it possible to inspect partial results.

---

## Dimensional analysis (Quantity support)

All differentiation predicates are **quantity-aware**: when `X` is a
[`Quantity(value, dims)`](units.md), units are propagated through the result
automatically.

### How it works

1. **Probe** — the wrapper calls `f(x_quantity)` once to discover whether `f`
   returns a `Quantity` (with output dims) or a plain number.  If `f` cannot
   accept a `Quantity` (e.g. it indexes into the array with `x[0]`), the probe
   fails gracefully and `f` is called with raw values instead.

2. **Strip and call** — `x.value` is passed to scipy; if `f` is
   quantity-aware, the wrapper re-wraps each raw value in a `Quantity` before
   forwarding to `f` and strips the result.

3. **Wrap output** — result dict fields are wrapped with the correct output
   dims:

   | Predicate | `df` / `ddf` dims | `error` dims |
   |---|---|---|
   | `derivative` | `f_dims - x_dims` | same as `df` |
   | `jacobian` | `f_dims - x_dims` | same as `df` |
   | `hessian` | `f_dims - 2 * x_dims` | same as `ddf` |

   The `'x'` field is wrapped with the input dims.

### Fast path

when `X` is a plain number or array (not a `Quantity`), scipy is called
directly with **zero additional overhead**.

### Example

```
-import_from(scipy_differentiate, [derivative, result_get])
-import_from(py.units, [metre, newton, has_units])

% f: metre -> newton (linear), so df/dx has units newton/metre
Test("derivative units") <- (
    K is ++(
        __import__('clausal.terms', fromlist=['Quantity']).Quantity(
            9.8,
            __import__('clausal.modules.py.units', fromlist=['newton','metre']).newton
            / __import__('clausal.modules.py.units', fromlist=['newton','metre']).metre
        )),
    derivative(++(lambda x, k=K: x * k), 1.0(metre), R),
    result_get(R, 'df', DF),
    has_units(DF, newton/metre))
```

### Limitations

- `Quantity` does not support `__getitem__` (array indexing).  Functions that
  use `x[0]`, `x[1]`, etc. cannot be probed for output units.  The wrapper
  falls back to passing raw values; `df` / `ddf` will be plain (unwrapped)
  but `'x'` in the result is still wrapped with input dims.
- The probe consumes one extra function evaluation.  For any non-trivial `f`
  this is negligible relative to scipy's own evaluation count.

---

*See also: [scipy.integrate](scipy_integrate.md) — numerical integration · [scipy.optimize](scipy_optimize.md) — derivative-based optimization.*
