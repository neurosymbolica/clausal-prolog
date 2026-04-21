# Phase 7 — Einsum and Advanced Math

Einstein summation plus additional math operations, including bijective
trig pairs.

**File to modify:** `clausal/modules/py/jax.py`

**Depends on:** Phase 1, Phase 5 (`_bidir_2` re-use).

---

## Predicates

### Einsum

| Name | Arity | Modes | Description |
|---|---|---|---|
| `einsum` | `/3` | `(+EQ, +ARRS, -R)` | `jnp.einsum(eq, *arrs)` |

### Bijective pairs (single multi-mode predicate each)

| Name | Arity | Modes | Collapses | Notes |
|---|---|---|---|---|
| `logarithm` | `/2` | `(+X, -Y)`, `(-X, +Y)` | `jnp.exp` / `jnp.log` | `Y = log(X)` |
| `sine` | `/2` | same | `jnp.sin` / `jnp.arcsin` | Partial — range limited |
| `cosine` | `/2` | same | `jnp.cos` / `jnp.arccos` | Partial |
| `tangent` | `/2` | same | `jnp.tan` / `jnp.arctan` | Partial |

### Non-bijective (one-way)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `sqrt` | `/2` | `(+A, -R)` | |
| `pow` | `/3` | `(+A, +E, -R)` | Element-wise power |
| `atan2` | `/3` | `(+Y, +X, -R)` | Two-arg arctangent |
| `sinh` | `/2` | | |
| `cosh` | `/2` | | |
| `tanh` | `/2` | | |
| `sigmoid` | `/2` | | `jax.nn.sigmoid` |
| `softmax` | `/3` | `(+A, +AXIS, -R)` | `jax.nn.softmax` |
| `log_softmax` | `/3` | | `jax.nn.log_softmax` |
| `logsumexp` | `/3` | `(+A, +AXIS, -R)` | `jax.scipy.special.logsumexp` |
| `floor` | `/2` | | |
| `ceil` | `/2` | | |
| `round` | `/2` | | |
| `sign` | `/2` | | |
| `cumsum` | `/3` | `(+A, +AXIS, -R)` | |
| `cumprod` | `/3` | | |

---

## Context and Reference Patterns

### Einsum

```python
einsum = _pred("einsum",
    (3, _pure(lambda eq, arrs: _jnp_mod().einsum(eq, *arrs))),
)
```

`arrs` is a list of arrays from Clausal.

### Bijective trig and exp/log

Same `_bidir_2` as FFT:

```python
logarithm = _pred("logarithm",
    (2, _bidir_2(
        forward=lambda x: _jnp_mod().log(x),
        backward=lambda y: _jnp_mod().exp(y),
    )),
)

sine = _pred("sine",
    (2, _bidir_2(
        forward=lambda angle: _jnp_mod().sin(angle),
        backward=lambda value: _jnp_mod().arcsin(value),
    )),
)
```

Name direction: the predicate *name* describes the natural reading of
the second arg. `sine(ANGLE, VALUE)` — "VALUE is the sine of ANGLE".
Forward: given angle, produce value. Backward: given value, produce
angle (via arcsin, partial).

### Softmax and log_softmax

These are in `jax.nn`, not `jax.numpy`:

```python
def _jnn():
    _ensure_jax()
    import jax.nn as _m
    return _m

softmax = _pred("softmax",
    (3, _pure(lambda a, axis: _jnn().softmax(a, axis=int(axis)))),
)
```

### `logsumexp` is in scipy.special

```python
def _jss():
    return _jnp_mod().__class__.__module__  # placeholder
    # Real: import jax.scipy.special

logsumexp = _pred("logsumexp",
    (3, _pure(lambda a, axis: _jss().logsumexp(a, axis=int(axis)))),
)
```

(Place in Phase 11 instead if cleaner — decide during implementation.)

---

## Example Usage

```clausal
-import_from(py.jax, [array, shape, array_list,
                      einsum, logarithm, sine, cosine, tangent,
                      sqrt, pow, sigmoid, softmax, cumsum])

Test("einsum matmul") <- (
    array([[1.0, 2.0], [3.0, 4.0]], A),
    array([[5.0, 6.0], [7.0, 8.0]], B),
    einsum("ij,jk->ik", [A, B], R),
    shape(R, [2, 2])
)

Test("logarithm forward") <- (
    array(1.0, X),
    logarithm(X, Y),
    array_list(Y, 0.0)
)

Test("logarithm backward") <- (
    array(0.0, Y),
    logarithm(X, Y),
    array_list(X, 1.0)
)

Test("sine roundtrip") <- (
    array(0.5, ANGLE),
    sine(ANGLE, VALUE),
    sine(ANGLE2, VALUE),
    array_list(ANGLE2, A),
    A > 0.49,
    A < 0.51
)

Test("cumsum along axis") <- (
    array([[1.0, 2.0], [3.0, 4.0]], A),
    cumsum(A, 0, R),
    array_list(R, [[1.0, 2.0], [4.0, 6.0]])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/jax_math_tests.clausal`):
- `einsum` with common equations: matmul, trace, diag extract
- Bijective pairs forward/backward/roundtrip
- Non-bijective math with value spot-checks
- `softmax` sums to 1 along its axis

---

## Docs

Update `docs/jax.md` with an Advanced Math section. Highlight the
bijective trig/exp pairs.

---

## Issues

_To be populated during implementation._

1. **`logsumexp` location.** `jax.scipy.special.logsumexp` vs
   `jax.nn.logsumexp` — both exist. Pick one; note alias.
2. **`arcsin`/`arccos` domain.** Outside [-1, 1] returns NaN. Tests
   must stay in-domain; failure-mode behaviour documented.
3. **`softmax` on non-float input.** JAX silently promotes to float.
