# Phase 7 — Einsum and Advanced Math

Einstein summation and additional math operations not covered in Phase 1.
Inverse pairs are collapsed into single bijective predicates using `_bidir_2`.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` helpers.
Phase 5 — `_bidir_3_mid` helper for arity-3 bijective predicates.

**File to modify:** `clausal/modules/py/torch.py`

---

## Predicates

### Einsum

| Name | Arity | Modes | Description |
|---|---|---|---|
| `einsum` | `/3` | `(+equation, +tensors, -result)` | Einstein summation |

`equation` is a string like `"ij,jk->ik"`. `tensors` is a list.

### Bijective predicates (inverse pairs collapsed)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `logarithm` | `/2` | `(+EXP, -VAL)` exp, `(-EXP, +VAL)` log | `VAL = e^EXP`. Bind either side. |
| `sine` | `/2` | `(+ANGLE, -VAL)` sin, `(-ANGLE, +VAL)` asin | Sine / arcsine. Domain: `VAL` in [-1, 1]. |
| `cosine` | `/2` | `(+ANGLE, -VAL)` cos, `(-ANGLE, +VAL)` acos | Cosine / arccosine. |
| `tangent` | `/2` | `(+ANGLE, -VAL)` tan, `(-ANGLE, +VAL)` atan | Tangent / arctangent. |

These use `_bidir_2` — same pattern as `tensor_numpy`, `tensor_list`,
and the FFT predicates from Phase 5.

### Non-bijective math (one-directional)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `sqrt` | `/2` | `(+T, -R)` | Square root (not bijective — squaring is lossy for negatives) |
| `pow` | `/3` | `(+T, +exp, -R)` | Element-wise power |
| `atan2` | `/3` | `(+Y, +X, -R)` | Two-argument arctangent (not the inverse of tangent) |
| `sinh` | `/2` | `(+T, -R)` | Hyperbolic sine |
| `cosh` | `/2` | `(+T, -R)` | Hyperbolic cosine |
| `tanh` | `/2` | `(+T, -R)` | Hyperbolic tangent |
| `sigmoid` | `/2` | `(+T, -R)` | Logistic sigmoid |
| `log_softmax` | `/3` | `(+T, +dim, -R)` | Log-softmax |
| `floor` | `/2` | `(+T, -R)` | Floor (not invertible) |
| `ceil` | `/2` | `(+T, -R)` | Ceiling (not invertible) |
| `round` | `/2` | `(+T, -R)` | Round (not invertible) |
| `sign` | `/2` | `(+T, -R)` | Sign — returns -1, 0, +1 (not invertible) |
| `abs` | `/2` | `(+T, -R)` | Absolute value (already in Phase 1) |
| `cumsum` | `/3` | `(+T, +dim, -R)` | Cumulative sum |
| `cumprod` | `/3` | `(+T, +dim, -R)` | Cumulative product |

Hyperbolic functions could be bijective (`sinh`/`asinh` etc.) but the
inverse hyperbolic functions are rarely used. Defer to a future phase
if demand arises.

---

## Context and Reference Patterns

Bijective predicates use `_bidir_2` from Phase 1/2. Example:

```python
logarithm = _pred("logarithm",
    (2, _bidir_2(
        forward_fn=lambda x: _th().exp(x),     # exponent -> value
        backward_fn=lambda y: _th().log(y),     # value -> exponent
    )),
)

sine = _pred("sine",
    (2, _bidir_2(
        forward_fn=lambda a: _th().sin(a),      # angle -> value
        backward_fn=lambda v: _th().asin(v),    # value -> angle
    )),
)
```

Non-bijective predicates use the standard `_pure()` pattern.

`einsum` needs `_deep_deref()` on the tensor list argument:

```python
einsum = _pred("einsum",
    (3, _pure(lambda eq, tensors: _th().einsum(eq, *tensors))),
)
```

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, einsum, logarithm, sine, cosine,
                         sqrt, sigmoid, cumsum, shape, tensor_list,
                         allclose])

# Einsum: matrix multiply via string notation
Test("einsum matmul") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], A),
    tensor([[5.0, 6.0], [7.0, 8.0]], B),
    einsum("ij,jk->ik", [A, B], C),
    shape(C, [2, 2])
)

# Einsum: trace
Test("einsum trace") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], A),
    einsum("ii->", [A], T),
    tensor_list(T, 5.0)
)

# logarithm is bijective: exp direction
Test("logarithm forward (exp)") <- (
    tensor([0.0, 1.0, 2.0], EXPONENT),
    logarithm(EXPONENT, VALUE),
    # VALUE = [1.0, e, e^2]
    shape(VALUE, [3])
)

# logarithm is bijective: log direction
Test("logarithm backward (log)") <- (
    tensor([1.0, 2.0, 3.0], VALUE),
    logarithm(EXPONENT, VALUE),
    # EXPONENT = [0.0, ln(2), ln(3)]
    shape(EXPONENT, [3])
)

# logarithm roundtrip
Test("logarithm roundtrip") <- (
    tensor([1.0, 2.0, 3.0], X),
    logarithm(X, Y),
    logarithm(X2, Y),
    allclose(X, X2)
)

# sine is bijective
Test("sine roundtrip") <- (
    tensor([0.1, 0.5, 0.9], ANGLE),
    sine(ANGLE, VALUE),
    sine(ANGLE2, VALUE),
    allclose(ANGLE, ANGLE2)
)

# Cumulative sum (not bijective)
Test("cumsum") <- (
    tensor([1.0, 2.0, 3.0, 4.0], T),
    cumsum(T, 0, R),
    tensor_list(R, [1.0, 3.0, 6.0, 10.0])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_math_tests.clausal`):
- `einsum` with various equations (matmul, trace, outer product, batch matmul)
- `logarithm` in both directions + roundtrip
- `sine`, `cosine`, `tangent` in both directions + roundtrip
- `cumsum`/`cumprod` with known sequences
- `sigmoid` range (output in [0,1])
- `floor`/`ceil`/`round` with fractional inputs
- `sqrt`, `pow` with known values

---

## Docs

Update `docs/torch.md` with einsum and advanced math sections. Note
which predicates are bijective.

---

## Issues

1. **`tanh` near-boundary test**: Initial test using `gt(tanh([-10, ...]), -1.0)`
   failed because `tanh(-10.0) ≈ -1.0` within float precision. Replaced with
   a shape test and a `tanh(0) = 0` exactness test.
2. **`abs/2` already in Phase 1**: Skipped — no duplicate registration needed.
3. **`einsum` trace returns 0-dim tensor**: The `einsum("ii->", ...)` equation
   produces a scalar (0-dim) tensor, not a Python float. Tests use `allclose`
   against a `tensor([5.0])` which works because PyTorch broadcasts.
