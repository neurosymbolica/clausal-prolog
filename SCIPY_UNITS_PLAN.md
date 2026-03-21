# Dimensional Analysis Integration for SciPy Predicates

Plan for enabling the Clausal dimensional analysis system (Quantity / HasUnits)
to work transparently through all scipy wrapper predicates.

## Status

| Phase | Module(s) | Status |
|-------|-----------|--------|
| 1 | `_scipy_units.py` (shared infrastructure) | ✅ Done |
| 2 | `scipy_linalg.py` | ✅ Done |
| 3 | `scipy_differentiate.py` | ⬜ Pending |
| 4 | `scipy_integrate.py` | ⬜ Pending |
| 5 | `scipy_interpolate.py` | ⬜ Pending |
| 6 | `scipy_special.py`, `scipy_fft.py` | ✅ Done |
| 7 | `scipy_ndimage.py` | ⬜ Pending |
| 8 | `scipy_stats.py`, `scipy_optimize.py`, `scipy_cluster.py` | ⬜ Pending |
| 9 | `scipy_sparse.py`, `scipy_spatial.py` | ⬜ Pending |
| 10 | Documentation and tests | ⬜ Pending |

---

## Background

The dimensional analysis system (`clausal.terms.Quantity`, `HasUnits/2`,
`clausal.modules.py.units`) is a runtime assertion framework.  The intended
workflow is:

1. **Development** — annotate inputs, outputs, and intermediates with
   `HasUnits` goals and pass `Quantity` objects through the program.  Any
   dimensional error is caught immediately with a precise failure point.
2. **Verification** — once the test suite passes, the program is known to
   satisfy its dimensional invariants on those execution paths.
3. **Production** — strip `HasUnits` goals and stop passing `Quantity` objects.
   No overhead remains.

The scipy wrappers currently pass inputs straight to scipy, which cannot
handle `Quantity` objects.  This plan extends each wrapper so that:

- When `Quantity` inputs arrive, units are stripped, scipy is called on the
  raw values, and a `Quantity` with correctly computed output dims is returned.
- When plain float / array inputs arrive, scipy is called directly with
  **zero additional overhead** — the only cost is an `any(isinstance(...))`
  scan that short-circuits immediately.

---

## Quantity API quick reference (for implementors)

```python
from clausal.terms import Quantity, UnitsMismatch

# Construction
Quantity(value, dims)
#   value : int | float | np.ndarray  (SI base units)
#   dims  : dict[predicate, int] | _UnitsPredicate
#           if _UnitsPredicate, the scaling factor is applied automatically

# Properties
q.value   # raw numeric value — int, float, or ndarray
q.dims    # MappingProxyType[predicate, int]  ← NOT a plain dict
          # convert with dict(q.dims) before passing to _merge_dims

# Static helper
Quantity._merge_dims(a: dict, b: dict, sign: int) -> dict
# Returns a + sign*b with zero-exponent keys removed.
# Example: _merge_dims({Metre:1}, {Second:1}, -1) → {Metre:1, Second:-1}
# Both a and b must be plain dicts (not MappingProxyType).

# Exception
UnitsMismatch("message")   # raised for incompatible dimension combinations
                            # catchable in Clausal via  catch(..., UnitsMismatch(MSG), ...)
```

The `dims` keys are the unit predicate *objects* exported by
`clausal.modules.py.units` (e.g. the `Metre` singleton), not strings.  Two
`dims` dicts are equal when they contain the same predicate objects with the
same integer exponents.

---

## Unit semantics taxonomy

Before touching any code, every scipy function must be classified:

### 1 — Require dimensionless input

Transcendental and combinatorial functions whose arguments appear inside
`eˣ`, `x!`, `xⁿ` for non-integer n, `log(x)`, etc.  A dimensioned argument
is categorically wrong (not just ignored), so the wrapper should raise
`UnitsMismatch` if a `Quantity` with non-empty `dims` is passed.

If the caller's quantity happens to be dimensionless (`dims == {}`), it is
treated as a plain number — its `.value` is extracted and the function is
called normally, returning a plain result.

Examples: all of `scipy.special` (Gamma, Erf, Bessel, elliptic integrals,
hypergeometric, NormalCdf, LogSumExp, …).

### 2 — Pass-through

Linear operators applied element-wise or as a weighted sum over dimensionless
basis functions.  The function does not change the physical meaning of the
quantity; it only rearranges or scales the values.  Output inherits the
**same dims** as the relevant input array.

The rule for a two-array operation (e.g. convolution of signal with a
dimensionless kernel):

- If the kernel / weight array is dimensionless, output dims = signal dims.
- If the kernel has its own dims, output dims = signal dims + kernel dims
  (exponent-dict merge).

Examples:
- `scipy.fft` — DFT/IDFT: `X[k] = Σ x[n] e^{−2πink/N}`; complex exponentials
  are dimensionless, so output dims = input dims.
- `scipy.ndimage` — convolution, Gaussian filter (normalised kernel ⇒
  pass-through), morphological ops (dimensionless structuring element ⇒
  pass-through).

### 3 — Algebraic propagation

Output dims are determined from input dims by a fixed algebraic rule.  The
rule is a pure function of the dims dicts and (sometimes) array shapes.

Examples and their rules (see Phase 2 for full details):

| Predicate | Rule |
|---|---|
| `Norm(A)` | output = A's element dims |
| `Solve(A, b)` | output = b_dims − A_dims |
| `Inverse(A)` | output = −A_dims |
| `Determinant(A)` (n×n) | output = n · A_dims |
| `Cholesky(A)` | output = ½ · A_dims |
| `EigenDecompose` eigenvalues | output = A_dims |
| `EigenDecompose` eigenvectors | dimensionless |
| `Derivative(f, x)` | df_dims − dx_dims |
| `Hessian(f, x)` | df_dims − 2·dx_dims |
| `Quad(f, a, b)` | f_dims + x_dims |
| `Trapezoid(y, x)` | y_dims + x_dims |

### 4 — Intrinsically dimensionless output

Inputs may have units (or may be plain numbers), but the output is always
dimensionless: a probability, a count, a boolean flag, a cluster label, or a
pure ratio.

Behaviour: strip `.value` from any `Quantity` inputs, call scipy, return a
plain (non-`Quantity`) result.

Examples: `scipy.stats` test statistics and p-values; `scipy.cluster` cluster
labels; `scipy.optimize` success/status fields; `scipy.sparse` structural
queries.

### 5 — Context-dependent / deferred

Functions where the correct rule is non-trivial or depends on arguments that
are themselves callables.  Handled in later phases.

Examples: `SolveInitialValueProblem` (ODE system), sparse matrix arithmetic,
`scipy.stats` distribution handles.

---

## Zero-overhead design

The central mechanism is the `make_quantity_aware` wrapper applied to the
`call` callable *before* it is handed to `_dispatch_fn`.  The trampoline
infrastructure (`_dispatch_fn`, `_multi_dispatch`, etc.) is not modified.

```python
# Before:
Solve = _pred("Solve",
    (3, _dispatch_fn(_la_fn("solve"))),
)

# After:
Solve = _pred("Solve",
    (3, _dispatch_fn(make_quantity_aware(_la_fn("solve"), _SOLVE_UNITS))),
)
```

The wrapper:

```python
def make_quantity_aware(call, unit_propagator=None):
    def wrapped(*inputs):
        # ── fast path ──────────────────────────────────────────────────────
        if not any(isinstance(x, Quantity) for x in inputs):
            return call(*inputs)
        # ── quantity path ──────────────────────────────────────────────────
        stripped = [x.value if isinstance(x, Quantity) else x for x in inputs]
        result   = call(*stripped)
        if unit_propagator is not None:
            dims_list = [dict(x.dims) if isinstance(x, Quantity) else None
                         for x in inputs]
            out = unit_propagator(dims_list, result)
            if out is not None:
                return out   # may be a Quantity (scalar/array) or a dict
        return result
    return wrapped
```

The propagator receives `dims_list` as plain `dict` (never `MappingProxyType`)
and returns either:

- A `Quantity` wrapping the result — for Tier 1 predicates with a single
  output value.
- A modified copy of `result` (a `dict`) with selected fields replaced by
  `Quantity` objects — for Tier 2 predicates that return result dicts.
- `None` — to leave the result unwrapped (e.g. all inputs were dimensionless).

```python
# Example: scalar-output propagator (Tier 1 — Solve)
def _solve_units(dims_list, result):
    a_dims = dims_list[0] or {}
    b_dims = dims_list[1]
    if b_dims is None:
        return None
    out_dims = Quantity._merge_dims(b_dims, a_dims, -1)
    return wrap_result(result, out_dims)   # returns Quantity or plain

# Example: dict-output propagator (Tier 2 — EigenDecompose)
def _eigen_units(dims_list, result):
    a_dims = dims_list[0]
    if not a_dims:
        return None
    out = dict(result)
    out['eigenvalues'] = wrap_result(result['eigenvalues'], a_dims)
    # 'eigenvectors' is dimensionless — leave as plain array
    return out
```

When no `Quantity` objects are present the `any(isinstance(...))` scan
short-circuits on the first element that is not a `Quantity`; in the common
case of a plain numpy array it evaluates `isinstance(ndarray, Quantity)` once
and returns `False` immediately.  This is negligible compared to the cost of
any scipy call.

An optional global flag `_SCIPY_UNITS_ENABLED` (default `True`) can be set to
`False` before any scipy module is imported.  When `False`,
`make_quantity_aware` returns `call` unwrapped, so predicate objects are
identical to the current (pre-plan) objects and there is truly zero overhead
even for the isinstance scan.  This is the deployment option for environments
where every nanosecond matters.

---

## Phase 1 — Shared infrastructure

**New file**: `clausal/modules/py/_scipy_units.py`

This module is a pure Python utility with no Clausal-specific dependencies
beyond `clausal.terms.Quantity`.  All scipy wrappers import from it.

### Contents

```
_SCIPY_UNITS_ENABLED   bool flag, default True
```

**Helpers**

```python
def strip_quantity(x):
    """Return x.value if x is a Quantity, else x unchanged."""

def quantity_dims(x):
    """Return x.dims if x is a Quantity, else None."""

def merge_dims(a: dict, b: dict, sign: int) -> dict:
    """Return a + sign*b with zero-exponent keys removed.
    Delegates to Quantity._merge_dims."""

def wrap_result(value, dims: dict | None):
    """Return Quantity(value, dims) if dims is non-None and non-empty,
    else value unchanged."""
```

**Standard propagators**

```python
REQUIRE_DIMENSIONLESS   # raises UnitsMismatch if any input Quantity has dims != {}
PASS_THROUGH_FIRST      # output dims = dims of first input (or None if plain)
PASS_THROUGH_LAST       # output dims = dims of last non-result input
STRIP_TO_PLAIN          # strips inputs, returns plain result (category 4)
```

**The main factory**

```python
def make_quantity_aware(call, unit_propagator=None) -> Callable:
    """See design above.  Returns call unchanged when _SCIPY_UNITS_ENABLED
    is False."""
```

**Callable-probing utility** (used by Phases 3 and 4)

```python
def probe_function_units(f, x_quantity) -> dict | None:
    """Call f(x_quantity) once and return the output dims dict, or None.

    If f returns a Quantity, returns dict(result.dims).
    If f returns a plain number/array, returns None
    (f operates on raw values and does not propagate units).

    The probe consumes one function evaluation.  For scipy.differentiate and
    scipy.integrate this is negligible — scipy itself makes many evaluations.
    """
```

---

## Phase 2 — `scipy_linalg.py`

All predicates are modified; `_dispatch_fn` itself is unchanged.

### Tier 1 predicates — algebraic propagation

**`Solve(A, b)`** and **`Solve(A, b, assume_a)`**

x dims = b_dims − A_dims (component-wise exponent subtraction).  If A is
dimensionless (dims = {} or None), x has the same dims as b.

```python
def _solve_units(dims_list, result):
    a_dims = dims_list[0] or {}
    b_dims = dims_list[1]
    if b_dims is None:
        return None
    out_dims = merge_dims(b_dims, a_dims, -1)
    return wrap_result(result, out_dims)
```

**`LeastSquares(A, b)`** — same rule for the `'x'` field of the result dict;
`'residuals'` has dims of `b`²; `'s'` (singular values) has dims of A.

**`SolveTriangular(A, b)`** and **`SolveTriangular(A, b, lower)`** — same rule
as Solve.

**`Norm(A)`** and **`Norm(A, ord)`**

Output dims = A's element dims (Euclidean norm of a length-vector is a length).

**`Inverse(A)`** and **`PseudoInverse(A)`**

Output dims = negated A dims (`{k: -v for k,v in a_dims.items()}`).

**`Determinant(A)`** (n×n matrix)

Output dims = A_dims scaled by n.  The generic `make_quantity_aware` contract
passes only `(dims_list, result)` to the propagator — the result is the scalar
determinant and carries no shape information.  Determinant therefore uses a
custom wrapper instead of `make_quantity_aware`:

```python
def _det_call(inner_call):
    """Custom Determinant wrapper: captures matrix size for unit propagation."""
    def call(*inputs):
        a = inputs[0]
        if not isinstance(a, Quantity):
            return inner_call(a)
        a_dims = dict(a.dims)
        a_val  = a.value
        result = inner_call(a_val)
        if a_dims:
            n = a_val.shape[0]   # n×n matrix; shape available on stripped array
            out_dims = {k: v * n for k, v in a_dims.items()}
            return wrap_result(result, out_dims)
        return result
    return call

Determinant = _pred("Determinant",
    (2, _dispatch_fn(_det_call(_la_fn("det")))),
)
```

`n` is read from `a_val.shape[0]` (the stripped numpy array), which is
available inside the call wrapper but not inside a generic propagator.

**`Cholesky(A)`** and **`Cholesky(A, lower)`**

Cholesky factor L satisfies A = LLᵀ, so if A has dims D then L has dims D/2.
This requires fractional exponents, which the current `Quantity` system does
not support (integer-only exponents is a documented design constraint).
**Decision**: raise `UnitsMismatch` if A has non-trivial dims (i.e. require
dimensionless A); document this restriction.  Revisit if half-integer exponents
are added to the type system.

**`MatrixExponential(A)`, `MatrixLogarithm(A)`, `MatrixSquareRoot(A)`,
`MatrixFunction(A, func)`**

A must be dimensionless; raise `UnitsMismatch` otherwise (same reason as
transcendental functions).

**`LuFactor`, `CholeskyFactor`, `LuSolve`, `CholeskySolve`**

These are two-step factorisations.  Unit handling follows the same logic as
LuDecompose / CholeskySolve using Solve's rule.  The opaque factor tuple is
not wrapped in a Quantity; the solve step propagates units.

### Tier 2 predicates — result-dict propagation

For predicates that return a dict, the propagator receives `(dims_list,
result_dict)` and returns a **new dict** with selected fields replaced by
`Quantity` objects.  Fields that are dimensionless are left as plain arrays.

**`QrDecompose(A)`** → `{'q': Q, 'r': R}`

R is upper-triangular; if A = QR with A having dims D, Q is dimensionless and
R has dims D.

```python
def _qr_units(dims_list, result):
    a_dims = dims_list[0]
    if not a_dims:
        return None
    out = dict(result)
    out['r'] = wrap_result(result['r'], a_dims)
    # 'q' is orthogonal/unitary — dimensionless
    return out
```

**`SingularValueDecompose(A)`** → `{'u': U, 's': S, 'vh': Vh}`

U and Vh are unitary (dimensionless); singular values S have dims of A.

```python
def _svd_units(dims_list, result):
    a_dims = dims_list[0]
    if not a_dims:
        return None
    out = dict(result)
    out['s'] = wrap_result(result['s'], a_dims)
    return out
```

**`EigenDecompose(A)`** and **`EigenDecomposeHermitian(A)`** → `{'eigenvalues', 'eigenvectors'}`

Eigenvalues satisfy Av = λv ⇒ λ has same dims as A.  Eigenvectors are
dimensionless direction vectors.

```python
def _eigen_units(dims_list, result):
    a_dims = dims_list[0]
    if not a_dims:
        return None
    out = dict(result)
    out['eigenvalues'] = wrap_result(result['eigenvalues'], a_dims)
    # 'eigenvectors' left as plain array
    return out
```

**`LuDecompose(A)`** → `{'p': P, 'l': L, 'u': U}`

P is a permutation matrix (dimensionless).  L has dims of A (lower factor
absorbs the scale).  U is dimensionless when A is dimensioned, or vice versa —
the convention depends on scipy's normalisation.  Mark as "strip and return
plain" until confirmed by test.

**`Schur(A)`** → `{'t': T, 'z': Z}`

T (Schur form) has same dims as A; Z (unitary factor) is dimensionless.

```python
def _schur_units(dims_list, result):
    a_dims = dims_list[0]
    if not a_dims:
        return None
    out = dict(result)
    out['t'] = wrap_result(result['t'], a_dims)
    return out
```

**`LeastSquares(A, b)`** → `{'x', 'residuals', 'rank', 's'}`

```python
def _lstsq_units(dims_list, result):
    a_dims = dims_list[0] or {}
    b_dims = dims_list[1]
    if b_dims is None:
        return None
    out = dict(result)
    x_dims = Quantity._merge_dims(b_dims, a_dims, -1)
    out['x'] = wrap_result(result['x'], x_dims)
    # residuals: dims b² (sum of squared residuals)
    res_dims = Quantity._merge_dims(b_dims, b_dims, +1)
    out['residuals'] = wrap_result(result['residuals'], res_dims)
    # s (singular values): dims of A
    if a_dims:
        out['s'] = wrap_result(result['s'], a_dims)
    return out
```

### `ResultGet` — transparent to units

`ResultGet(RESULT, FIELD, VALUE)` already just returns `RESULT[FIELD]`.  Since
the dict fields are now `Quantity` objects where appropriate, `ResultGet`
propagates them automatically with no changes required.

### Example test code — `tests/fixtures/scipy_linalg_units_tests.clausal`

```clausal
-import_from(scipy_linalg, [Solve, Norm, Determinant, Inverse, EigenDecompose,
                             SingularValueDecompose, ResultGet])
-import_from(py.units, [Metre, Second, Newton, Kilogram, HasUnits])

# Solve: x has units b/A — Newton/Pascal = Newton/(Newton/m²) = m²
# A is dimensionless (Pascals per Pascal = 1), b is Newtons ⇒ x is Newtons
Test("solve preserves b units when A dimensionless") <- (
    Solve(++(numpy.array([[2.0,0.0],[0.0,3.0]])),
          ++(numpy.array([4.0(Newton), 9.0(Newton)])),
          X),
    HasUnits(X, Newton))

# Norm: norm of a length vector is a length
Test("norm of length vector has length units") <- (
    Norm(++(numpy.array([3.0(Metre), 4.0(Metre)])), N),
    HasUnits(N, Metre),
    N == 5.0(Metre))

# Determinant: 2×2 matrix of Metres → det has dims Metre²
Test("determinant of 2x2 metre matrix has metre squared units") <- (
    Determinant(++(numpy.array([[1.0(Metre), 0.0(Metre)],
                                [0.0(Metre), 2.0(Metre)]])), D),
    HasUnits(D, Metre**2))

# Inverse: inverse of a Newton matrix has Newton^-1 dims
Test("inverse dims are negated") <- (
    Inverse(++(numpy.array([[2.0(Newton), 0.0(Newton)],
                            [0.0(Newton), 4.0(Newton)]])), INV),
    HasUnits(INV, Newton**-1))

# EigenDecompose: eigenvalues have same units as A
Test("eigenvalues have same units as matrix") <- (
    EigenDecompose(++(numpy.diag([3.0(Newton), 5.0(Newton)])), R),
    ResultGet(R, 'eigenvalues', EV),
    HasUnits(EV, Newton))

# Dimensionless fast path — no Quantity wrapping, result is plain
Test("solve plain arrays returns plain result") <- (
    Solve(++(numpy.eye(2)), ++(numpy.array([1.0, 2.0])), X),
    X == ++(numpy.array([1.0, 2.0])))

# Dimensionless Quantity (dims={}) treated as plain number
Test("norm of dimensionless quantity returns plain") <- (
    Norm(++(numpy.array([3.0(), 4.0()])), N),
    N == 5.0)
```

---

## Phase 3 — `scipy_differentiate.py`

Differentiation has clean unit semantics and introduces the
callable-probing pattern.

**`Derivative(f, x)`** → `{'x', 'df', 'error', 'success', …}`

If x has dims `[U_x]`:

1. Call `probe_function_units(f, x_quantity)` to determine `f_dims` (or `None`
   if f returns plain numbers).  This consumes one extra function evaluation;
   for any non-trivial f it is negligible relative to scipy's own call count.
2. Wrap `f` for scipy: `f_stripped(v) = strip_quantity(f(Quantity(v, x_dims)))`.
3. Call scipy with `x.value` and `f_stripped`.
4. In the result dict, wrap `'x'` with x_dims and `'df'` with
   `Quantity._merge_dims(f_dims, x_dims, -1)` (df/dx dims).

The concrete wrapper (replaces the `_dispatch_fn` call for Derivative):

```python
def _derivative_quantity_call(f, x):
    """Handle Quantity x for Derivative: probe f, strip, call scipy, wrap result."""
    if not isinstance(x, Quantity):
        return None   # signal: use plain scipy call
    x_dims = dict(x.dims)
    f_dims = probe_function_units(f, x)   # one evaluation
    def f_stripped(v):
        arg = Quantity(v, x_dims) if x_dims else v
        return strip_quantity(f(arg))
    raw = _diff().derivative(f_stripped, x.value)
    result = _rich_result_to_dict(raw, 'df')
    result['x'] = wrap_result(result['x'], x_dims)
    if f_dims is not None:
        df_dims = Quantity._merge_dims(f_dims, x_dims, -1)
        result['df']    = wrap_result(result['df'],    df_dims)
        result['error'] = wrap_result(result['error'], df_dims)
    return result
```

The predicate dispatch checks for `None` return and falls through to the
standard `_dispatch_fn` path for plain inputs.

If x is plain (no units), call scipy unmodified.

**`Jacobian(f, x)`**

Same logic; `'df'` in the result is the Jacobian matrix, wrapped as
`Quantity(jacobian_array, f_dims_minus_x_dims)`.

**`Hessian(f, x)`**

`'ddf'` has dims `Quantity._merge_dims(f_dims, x_dims, -2)` (second
derivative: f_dims − 2·x_dims; the `sign` argument is −2, not −1).

Note on `'error'` fields: error estimates are in the same units as `'df'` /
`'ddf'` and are wrapped identically.

### Example test code — `tests/fixtures/scipy_differentiate_units_tests.clausal`

```clausal
-import_from(scipy_differentiate, [Derivative, Jacobian, Hessian, ResultGet])
-import_from(py.units, [Metre, Second, Newton, HasUnits])

# f: Metre → Newton, so df/dx has units Newton/Metre
Test("derivative units Newton per Metre") <- (
    Derivative(++(lambda x: x * 9.8(Newton/Metre)), 1.0(Metre), R),
    ResultGet(R, 'df', DF),
    HasUnits(DF, Newton/Metre))

# x-echo in result dict keeps input units
Test("derivative result x has input units") <- (
    Derivative(++(lambda x: x * 2.0(Newton/Metre)), 3.0(Metre), R),
    ResultGet(R, 'x', X),
    HasUnits(X, Metre))

# error estimate has same units as df
Test("derivative error has same units as df") <- (
    Derivative(++(lambda x: x * 2.0(Newton/Metre)), 3.0(Metre), R),
    ResultGet(R, 'error', E),
    HasUnits(E, Newton/Metre))

# plain f (returns float, not Quantity): result df is plain
Test("derivative of plain function returns plain df") <- (
    Derivative(++(lambda x: x.value ** 2), 3.0(Metre), R),
    ResultGet(R, 'df', DF),
    DF == 6.0)

# no units on x — plain fast path
Test("derivative no units plain fast path") <- (
    Derivative(++(lambda x: x**2), 3.0, R),
    ResultGet(R, 'df', DF),
    DIFF is ++(abs(float(DF) - 6.0)),
    DIFF < 1e-8)
```

---

## Phase 4 — `scipy_integrate.py`

### 4a — Array-based quadrature (no callable involved)

**`Trapezoid(y, x)`**, **`CumulativeTrapezoid(y, x)`**, **`Simpson(y, x)`**

Output dims = y_dims + x_dims.  Straightforward algebraic propagator; no
callable probing needed.

### 4b — Callable-based quadrature

**`Quad(f, a, b)`** and variants

If a or b is a `Quantity` with dims `[U_x]`:

1. Probe `f(a)` — call `probe_function_units(f, a)` — to get `f_dims`.
   This consumes one extra function evaluation (negligible).
2. Build `f_stripped(v) = strip_quantity(f(Quantity(v, x_dims) if x_dims else v))`.
3. Call `scipy.integrate.quad(f_stripped, a.value, b.value)`.
4. Wrap result dict `'value'` with `Quantity._merge_dims(f_dims, x_dims, +1)`
   if `f_dims` is not `None`; otherwise leave `'value'` plain.

If a and b are plain, call scipy unmodified (fast path).

```python
def _quad_quantity_call(func, a, b):
    """Quantity-aware Quad: probe func, wrap bounds, wrap result."""
    if not isinstance(a, Quantity) and not isinstance(b, Quantity):
        return None   # signal: use plain _quad_result
    x_dims = dict(a.dims) if isinstance(a, Quantity) else {}
    f_dims = probe_function_units(func, a)   # one evaluation; f_dims or None
    def f_stripped(v):
        arg = Quantity(v, x_dims) if x_dims else v
        return strip_quantity(func(arg))
    r = _integrate().quad(f_stripped,
                          strip_quantity(a), strip_quantity(b))
    result = {'value': r[0], 'error': r[1]}
    if f_dims is not None:
        out_dims = Quantity._merge_dims(f_dims, x_dims, +1)
        result['value'] = wrap_result(result['value'], out_dims)
        result['error'] = wrap_result(result['error'], out_dims)
    return result
```

**`DoubleQuad(f, a, b, gfun, hfun)`**

Same pattern; `f` takes `(y, x)`.  Probe `f(gfun(a), a)` to get `f_dims`.
x-dims from a/b; y-dims from `gfun(a)` if it returns a Quantity.
Output dims = `Quantity._merge_dims(Quantity._merge_dims(f_dims, x_dims, +1), y_dims, +1)`.

**`TripleQuad`** and **`NQuad`**: follow the same pattern recursively.

**`QuadVec(f, a, b)`** — same as Quad; `'y'` field is a vector, wrapped in
full with output dims.

### Example test code — `tests/fixtures/scipy_integrate_units_tests.clausal`

```clausal
-import_from(scipy_integrate, [Quad, Trapezoid, CumulativeTrapezoid, Simpson, ResultGet])
-import_from(py.units, [Metre, Second, Newton, HasUnits])

% Trapezoid: velocity (m/s) over time (s) → displacement (m)
Test("trapezoid velocity times time gives metres") <- (
    Trapezoid(++(numpy.array([0.0(Metre/Second), 10.0(Metre/Second), 20.0(Metre/Second)])),
              ++(numpy.array([0.0(Second),       1.0(Second),        2.0(Second)])),
              RESULT),
    HasUnits(RESULT, Metre))

% Trapezoid: dimensionless fast path
Test("trapezoid plain arrays returns plain") <- (
    Trapezoid([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], RESULT),
    DIFF is ++(abs(float(RESULT) - 4.0)),
    DIFF < 1e-10)

% Quad: f(x) = x (Newton/Metre * x Metre = Newton), over [0 m, 1 m]
% ∫₀¹ x dx = 0.5, units Newton/Metre * Metre = Newton
Test("quad with units propagates f_dims times x_dims") <- (
    Quad(++(lambda x: x * 1.0(Newton/Metre)),
         0.0(Metre), 1.0(Metre), RESULT),
    ResultGet(RESULT, 'value', V),
    HasUnits(V, Newton))

% Quad: plain function (no Quantity returned) — result is plain
Test("quad plain function over dimensioned bounds returns plain value") <- (
    Quad(++(lambda x: x.value),
         0.0(Metre), 1.0(Metre), RESULT),
    ResultGet(RESULT, 'value', V),
    DIFF is ++(abs(float(V) - 0.5)),
    DIFF < 1e-9)

% Quad: no units anywhere — fast path, result identical to existing behaviour
Test("quad no units fast path") <- (
    Quad(++(lambda x: x), 0.0, 1.0, RESULT),
    ResultGet(RESULT, 'value', V),
    DIFF is ++(abs(float(V) - 0.5)),
    DIFF < 1e-9)
```

### 4c — ODE integration (deferred)

**`SolveInitialValueProblem(f, t_span, y0)`**

Complex: f(t, y) returns dy/dt.  If y0 has dims `[U_y]` and t_span has dims
`[U_t]`, f must return dims `[U_y/U_t]`.  The result dict fields `'t'` (dims
`[U_t]`) and `'y'` (dims `[U_y]`) must be wrapped.

Deferred to a follow-up because:
- t_span is a two-element sequence, not a single Quantity.
- The solution array `'y'` is 2-D (rows = state variables, each potentially
  with different units in a heterogeneous system).
- Requires wrapping f as a quantity-aware callable and post-processing the
  full result dict.

**`OdeIntegrate`**: same deferral.

---

## Phase 5 — `scipy_interpolate.py`

Interpolants are Tier 3 (handle/registry).  The handle currently stores the
scipy interpolant object directly.  Units are tracked by storing a
`(interpolant, x_dims, y_dims)` tuple instead.

### Handle registry changes

The existing registry and allocation helpers change minimally:

```python
# Before
_INTERP_REGISTRY: dict[int, object] = {}

def _alloc_handle(obj: object) -> int:
    with _registry_lock:
        _registry_counter[0] += 1
        handle = _registry_counter[0]
        _INTERP_REGISTRY[handle] = obj
    return handle

def _lookup_handle(handle: int) -> object:
    obj = _INTERP_REGISTRY.get(handle)
    if obj is None:
        raise KeyError(f"Unknown interpolator handle: {handle!r}")
    return obj

# After  — store (interpolant, x_dims, y_dims); None means "no units"
_INTERP_REGISTRY: dict[int, tuple] = {}

def _alloc_handle(obj, x_dims=None, y_dims=None) -> int:
    with _registry_lock:
        _registry_counter[0] += 1
        handle = _registry_counter[0]
        _INTERP_REGISTRY[handle] = (obj, x_dims, y_dims)
    return handle

def _lookup_handle(handle: int) -> tuple:
    """Return (interpolant, x_dims, y_dims); dims are None when no units."""
    entry = _INTERP_REGISTRY.get(handle)
    if entry is None:
        raise KeyError(f"Unknown interpolator handle: {handle!r}")
    return entry
```

All existing `_alloc_handle(interp)` call sites (in `Make*` dispatch functions)
become `_alloc_handle(interp)` — the default `x_dims=None, y_dims=None` keeps
backward compatibility for the plain (no-units) case.  Only the new
quantity-aware paths pass explicit dims.

### Changes to `Make*` predicates

Each `Make*` dispatch function currently ends with:

```python
handle = _alloc_handle(interp_obj)
return handle
```

The quantity-aware version adds unit extraction before constructing the
interpolant:

```python
def _make_spline_call(x, y, k=3, bc_type=None):
    x_dims = dict(x.dims) if isinstance(x, Quantity) else None
    y_dims = dict(y.dims) if isinstance(y, Quantity) else None
    x_val  = strip_quantity(x)
    y_val  = strip_quantity(y)
    interp = _si().make_interp_spline(x_val, y_val, k=k, bc_type=bc_type)
    return _alloc_handle(interp, x_dims, y_dims)
```

All other `Make*` predicates (`MakeCubic`, `MakePCHIP`, `MakeAkima`,
`MakeLinear1D`, `MakeRegularGrid`, `MakeRadialBasis`) follow the same pattern.

### Changes to `Eval*` predicates

```python
def _eval_spline_call(handle, x, nu=0):
    interp, x_dims, y_dims = _lookup_handle(handle)
    # Check/strip x units
    if x_dims is not None and isinstance(x, Quantity):
        if dict(x.dims) != x_dims:
            raise UnitsMismatch(
                f"Spline expects x with dims {x_dims}, got {dict(x.dims)}")
        x_val = x.value
    else:
        x_val = strip_quantity(x)
    raw = interp(x_val, nu=nu) if nu else interp(x_val)
    if y_dims is None:
        return raw
    # ν-th derivative: dims y / dims x^ν
    if nu == 0:
        out_dims = y_dims
    else:
        out_dims = Quantity._merge_dims(y_dims, x_dims, -nu)
    return wrap_result(raw, out_dims)
```

`SplineIntegral(HANDLE, A, B, RESULT)` — integral adds one power of x_dims:
output dims = `Quantity._merge_dims(y_dims, x_dims, +1)`.

`SplineDerivative(HANDLE, ORDER, RESULT)` — returns a new handle storing the
derivative spline with adjusted `y_dims`:
`new_y_dims = Quantity._merge_dims(y_dims, x_dims, -order)`.

**Handle registry change** is backward-compatible: the existing plain-object
form `_alloc_handle(interp)` stores `(interp, None, None)`, which causes all
`Eval*` functions to return plain arrays as before.

---

## Phase 6 — `scipy_special.py` (require dimensionless) and `scipy_fft.py` (pass-through)

### `scipy_special.py`

All 78 special-function predicates wrap their call with
`make_quantity_aware(..., REQUIRE_DIMENSIONLESS)`.

**Implementation note**: Rather than wrapping each predicate inline, `_pred()`
was modified to automatically apply `make_quantity_aware(call,
REQUIRE_DIMENSIONLESS)` for every registered arity.  For bidirectional
predicates (Erf, ErfComplement, NormalCdf, Logit, GammaInc,
GammaIncComplement, BetaInc, Boxcox, Boxcox1p), a `_bidir_q(fwd, bwd,
n_fixed=0)` helper wraps both callables before passing to `_bidir_dispatch`.

`REQUIRE_DIMENSIONLESS` is a propagator that:
- If any input `Quantity` has non-empty `dims`: raises `UnitsMismatch` with a
  message naming the predicate and the offending dims.
- If all `Quantity` inputs have `dims == {}` (dimensionless): extracts
  `.value` from each and returns the plain scipy result (no `Quantity` wrapping).
- If all inputs are plain (no `Quantity`): fast path — this branch is never
  reached because `make_quantity_aware` only calls the propagator when at least
  one `Quantity` is present.

```python
def _require_dimensionless_propagator(dims_list, result):
    for d in dims_list:
        if d is not None and d:   # non-None and non-empty
            raise UnitsMismatch(
                f"Special function requires dimensionless arguments; "
                f"got dims {d}")
    return None   # dimensionless Quantities: return plain result (value already stripped)
```

### Example test code — `tests/fixtures/scipy_special_units_tests.clausal`

```clausal
-import_from(scipy_special, [Gamma, Erf, BesselJ, NormalCdf])
-import_from(py.units, [Metre, Second])

% Plain number: works as before
Test("gamma plain passes") <- (
    Gamma(5.0, R),
    DIFF is ++(abs(float(R) - 24.0)),
    DIFF < 1e-9)

% Dimensionless Quantity (dims={}): allowed — value extracted, result is plain
Test("gamma dimensionless quantity passes") <- (
    Gamma(5.0(), R),
    DIFF is ++(abs(float(R) - 24.0)),
    DIFF < 1e-9)

% Dimensioned Quantity: UnitsMismatch raised, catchable
Test("gamma dimensioned raises UnitsMismatch") <- catch(
    Gamma(5.0(Metre), _R),
    UnitsMismatch(_MSG),
    true)

Test("erf dimensioned raises UnitsMismatch") <- catch(
    Erf(1.0(Second), _R),
    UnitsMismatch(_MSG),
    true)

% Ratio of dimensioned values is dimensionless — Erf then works
Test("erf of dimensionless ratio works") <- (
    X := 3.0(Metre),
    SIGMA := 2.0(Metre),
    Z := X / SIGMA,       % Z is dimensionless Quantity
    Erf(Z, R),
    R > 0.9)
```

### `scipy_fft.py` (pass-through)

All FFT predicates (`Fft`, `Ifft`, `Rfft`, `Irfft`, `Fft2`, `FftN`, …):

Wrap each call with `make_quantity_aware(..., PASS_THROUGH_FIRST)`.

The output array has the same dims as the input array.  The frequency-domain
representation of a voltage signal has units of volts — stripping units before
the FFT and re-attaching them to the output is the correct physical semantics.

If the input is plain (no units), the fast path is taken unchanged.

**Implementation note**: Rather than wrapping each predicate inline, `_dispatch_fn()`
and `_fft_fn()` were modified to apply `make_quantity_aware(..., PASS_THROUGH_FIRST)`
centrally.  For bidirectional `_fft_bidir_n` lambdas (with explicit `n`
argument), each lambda is wrapped individually at the call site.

---

## Phase 7 — `scipy_ndimage.py` (pass-through / lenient)

Most ndimage operations use a normalised kernel (dimensionless, sums to 1 for
filters, binary structure element for morphological ops).

**Signal-style filters** (`gaussian_filter`, `uniform_filter`, `convolve`,
`correlate`, `median_filter`, `percentile_filter`, etc.)

- Input array → output array.
- If kernel/weights argument is present and is a `Quantity`, output dims =
  merge of input dims and kernel dims.
- If kernel is plain (the usual case), output dims = input array's dims
  (pass-through).

**Morphological** (`binary_dilation`, `binary_erosion`, `label`,
`binary_fill_holes`, etc.)

These return boolean or integer arrays.  Output is always dimensionless
regardless of input dims; use `STRIP_TO_PLAIN`.

**Measurement functions** (`sum`, `mean`, `variance`, `standard_deviation`,
`minimum`, `maximum`, `center_of_mass`)

- `sum`, `mean` → same dims as input.
- `variance`, `standard_deviation` → standard deviation same dims; variance
  is dims².
- `center_of_mass` → if index array has units, output has those units.
- Others → dimensionless.

Implement the common cases; leave edge cases as `STRIP_TO_PLAIN` with a note.

---

## Phase 8 — `scipy_stats.py`, `scipy_optimize.py`, `scipy_cluster.py`

### `scipy_stats.py`

**Test statistics** (t-test, chi-square, Kolmogorov-Smirnov, …):

Inputs may have units (measurements); the test strips them (a t-statistic is
dimensionless).  Use `STRIP_TO_PLAIN` for all test predicates.

**Distribution handles** (Tier 3):

Distributions have `loc` and `scale` parameters.  If `loc` and `scale` are
`Quantity` objects, store their dims in the handle.  `pdf` calls return
`1/scale_dims`; `cdf`/`sf` return dimensionless; `rvs` / `ppf` return
`scale_dims`.  This is a follow-up item after the basic distribution predicates
are stabilised.

### `scipy_optimize.py`

The objective function is a scalar real-valued function; minimisation is
inherently dimensionless.  The result `'x'` (optimal parameters) may or may
not have units depending on the problem.

Use `STRIP_TO_PLAIN` for now.  A follow-up could probe the initial guess `x0`
for units and attach them to the result `'x'` field (the optimal point has the
same units as the search space).

### `scipy_cluster.py`

- `KMeans` centroids → same units as input data.
- `KMeans` labels → dimensionless integers.
- Linkage matrix values → same units as input (distances).

Implement centroid propagation; everything else `STRIP_TO_PLAIN`.

---

## Phase 9 — `scipy_sparse.py`, `scipy_spatial.py`

### `scipy_sparse.py`

Sparse matrices follow the same algebraic rules as dense linalg.  Wrap
construction predicates to record element dims in the handle; propagate through
`SparseSolve`, `SparseNorm`, and arithmetic predicates.

### `scipy_spatial.py`

**Distance functions** (`PairwiseDistances`, `CDistances`)

If input points have dims `[U]` (e.g. metres), pairwise distances also have
dims `[U]`.  Implement pass-through from the input coordinate array.

**KDTree** (Tier 3 handle)

Store coordinate dims in the handle.  `KdTreeQuery` returns distances (same
dims as coordinates) and indices (dimensionless).

---

## Phase 10 — Documentation and tests

### Documentation additions

**`docs/units.md`** — new section: *Dimensional analysis with SciPy predicates*

- Explain the four categories (require dimensionless / pass-through / algebraic
  / intrinsically dimensionless output).
- Show worked examples for each category.
- Explain the zero-overhead toggle: "pass plain arrays/scalars when dimensional
  analysis is not needed; the wrappers call scipy directly with no wrapping
  overhead".
- Show how `HasUnits` and scipy wrappers compose: assert units on inputs before
  the call, and on the result after.

**`SCIPY_PORT.md`** — add a *Dimensional analysis* subsection to the
architecture overview noting that all Tier 1/2 predicates are quantity-aware
from Phase 2 onwards.

### Test fixtures

One test file per module:

| File | Tests |
|---|---|
| `tests/fixtures/scipy_linalg_units_tests.clausal` | Solve (units of b/A), Norm, Det (scaled dims), Inverse (negated dims), EigenDecompose (eigenvalue units) |
| `tests/fixtures/scipy_differentiate_units_tests.clausal` | Derivative of f: Metre→Newton gives Newton/Metre; Jacobian |
| `tests/fixtures/scipy_integrate_units_tests.clausal` | Trapezoid (area under velocity curve = metres), Quad with dimensioned bounds |
| `tests/fixtures/scipy_interpolate_units_tests.clausal` | Make with units, Eval propagates units, derivative spline units |
| `tests/fixtures/scipy_fft_units_tests.clausal` | FFT of voltage signal returns voltage, IFFT round-trip |
| `tests/fixtures/scipy_special_units_tests.clausal` | Gamma(5) passes, Gamma(5(m)) raises UnitsMismatch |
| `tests/fixtures/scipy_ndimage_units_tests.clausal` | gaussian_filter pass-through, label dimensionless |

---

## Implementation order and dependencies

```
Phase 1  _scipy_units.py              (no deps; foundational)
  │
  ├─ Phase 2  scipy_linalg.py         (algebraic rules only; no callables)
  ├─ Phase 6  scipy_fft.py            (PASS_THROUGH_FIRST; trivial)
  ├─ Phase 3  scipy_differentiate.py  (introduces callable-probing pattern)
  │     │
  │     └─ Phase 4  scipy_integrate.py  (reuses callable-probing from Phase 3)
  │
  ├─ Phase 5  scipy_interpolate.py    (handle-store pattern; independent)
  ├─ Phase 7  scipy_ndimage.py        (pass-through + STRIP_TO_PLAIN mix)
  ├─ Phase 8  stats / optimize / cluster
  └─ Phase 9  sparse / spatial

Phase 10  docs + tests                (one test file per phase, written
                                       alongside the phase implementation)
```

Phases 2, 3, 5, and 6 can be implemented in parallel once Phase 1 is done.
Phase 4 depends on the callable-probing utilities from Phase 3.

---

## Design constraints and notes

- **Integer-only exponents**: `Quantity` supports only integer exponents.
  Cholesky (½ power) and `MatrixSquareRoot` (½ power) therefore require
  dimensionless inputs for now.  If half-integer support is added to the type
  system later, these predicates can be updated.

- **Array wrapping**: a `Quantity` wraps a numpy array as a single object —
  `Quantity(ndarray, dims)`.  There is no array-of-Quantities.  All elements
  of the array share the same dims, which matches the common case (a vector of
  positions, an array of voltages, etc.).

- **Result dict fields**: each field in a Tier 2 result dict is individually
  wrapped or left plain.  `ResultGet` is transparent to Quantity wrapping —
  it just returns `RESULT[FIELD]`, whatever that is.

- **Callable-probing cost**: probing `f` once consumes one function evaluation.
  For `scipy.differentiate` and `scipy.integrate`, scipy itself makes many
  evaluations; one extra is negligible.  For functions where the probe would be
  expensive, the user can pass a plain callable and accept dimensionless output.

- **`UnitsMismatch` propagation and the broad `except Exception`**: several
  modules (`scipy_integrate`, `scipy_optimize`, `scipy_stats`) wrap the
  `call(*inputs)` in `_dispatch_fn` with a broad `except Exception` that
  converts any error into a predicate failure (silently).  A `UnitsMismatch`
  raised inside `make_quantity_aware` would be swallowed and show up as a
  silent backtrack rather than a visible dimensional error.

  Fix: in every `_dispatch_fn` that has this broad catch, re-raise
  `UnitsMismatch` before the general handler:

  ```python
  try:
      out = call(*inputs)
  except UnitsMismatch:
      raise                # let dimensional errors surface
  except Exception:
      yield (parent, DONE)
      return
  ```

  Modules that already have no broad catch (`scipy_linalg`, `scipy_fft`,
  `scipy_differentiate`) need no change.  Check each module's `_dispatch_fn`
  before implementing the phase.

  In Clausal code, `UnitsMismatch` is caught via:
  ```clausal
  catch(Goal, UnitsMismatch(MSG), Recovery)
  ```

- **Global disable flag**: setting `_scipy_units._SCIPY_UNITS_ENABLED = False`
  *before importing any scipy module* returns all `make_quantity_aware` calls
  as no-ops.  Predicate objects are then identical to pre-plan objects.  This
  is the deployment option for performance-critical code once correctness has
  been verified.
