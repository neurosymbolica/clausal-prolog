# Phase 7 — Einsum and Advanced Math

Einstein summation and additional math operations not covered in Phase 1.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` helpers.

**File to modify:** `clausal/modules/py/torch.py`

---

## Predicates

### Einsum

| Name | Arity | Modes | Description |
|---|---|---|---|
| `einsum` | `/3` | `(+equation, +tensors, -result)` | Einstein summation |

`equation` is a string like `"ij,jk->ik"`. `tensors` is a list.

### Additional math

| Name | Arity | Modes | Description |
|---|---|---|---|
| `exp` | `/2` | `(+T, -R)` | Element-wise exponential |
| `log` | `/2` | `(+T, -R)` | Element-wise natural log |
| `sqrt` | `/2` | `(+T, -R)` | Element-wise square root |
| `pow` | `/3` | `(+T, +exp, -R)` | Element-wise power |
| `sin` | `/2` | `(+T, -R)` | Sine |
| `cos` | `/2` | `(+T, -R)` | Cosine |
| `tan` | `/2` | `(+T, -R)` | Tangent |
| `asin` | `/2` | `(+T, -R)` | Arcsine |
| `acos` | `/2` | `(+T, -R)` | Arccosine |
| `atan` | `/2` | `(+T, -R)` | Arctangent |
| `atan2` | `/3` | `(+Y, +X, -R)` | Two-argument arctangent |
| `sinh` | `/2` | `(+T, -R)` | Hyperbolic sine |
| `cosh` | `/2` | `(+T, -R)` | Hyperbolic cosine |
| `tanh` | `/2` | `(+T, -R)` | Hyperbolic tangent |
| `sigmoid` | `/2` | `(+T, -R)` | Logistic sigmoid |
| `log_softmax` | `/3` | `(+T, +dim, -R)` | Log-softmax |
| `floor` | `/2` | `(+T, -R)` | Floor |
| `ceil` | `/2` | `(+T, -R)` | Ceiling |
| `round` | `/2` | `(+T, -R)` | Round to nearest |
| `sign` | `/2` | `(+T, -R)` | Sign (-1, 0, +1) |
| `cumsum` | `/3` | `(+T, +dim, -R)` | Cumulative sum |
| `cumprod` | `/3` | `(+T, +dim, -R)` | Cumulative product |

### Bijective pairs among these

- `exp`/`log` (within floating point precision)
- `sin`/`asin`, `cos`/`acos`, `tan`/`atan` (within domain restrictions)
- `sqrt` is the inverse of squaring (partial)

---

## Context and Reference Patterns

All Tier 1 (pure). Same `_pure()` + `_pred()` pattern.

`einsum` needs `_deep_deref()` on the tensor list argument:

```python
einsum = _pred("einsum",
    (3, _pure(lambda eq, tensors: _th().einsum(eq, *tensors))),
)
```

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, einsum, exp, log, sin, asin,
                         sqrt, sigmoid, cumsum, shape, tensor_list])

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

# exp/log are inverses
Test("exp log roundtrip") <- (
    tensor([1.0, 2.0, 3.0], T),
    exp(T, E),
    log(E, T2),
    allclose(T, T2)
)

# sin/asin are inverses (within [-1, 1])
Test("sin asin roundtrip") <- (
    tensor([0.1, 0.5, 0.9], T),
    sin(T, S),
    asin(S, T2),
    allclose(T, T2)
)

# Cumulative sum
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
- All trig functions with known values
- `exp`/`log` roundtrip, `sin`/`asin` roundtrip
- `cumsum`/`cumprod` with known sequences
- `sigmoid` range (output in [0,1])
- `floor`/`ceil`/`round` with fractional inputs

---

## Docs

Update `docs/torch.md` with einsum and advanced math sections.

---

## Issues

_To be populated during implementation._
