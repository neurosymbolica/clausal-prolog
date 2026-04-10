# Phase 4 — Linear Algebra

Pure tensor linear algebra operations. Many are bijective pairs
(inverse/inverse, decompose/reconstruct).

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` must exist with
`_pure()`, `_pred()`, `_deep_deref()`, `_ensure_torch()` helpers.

**File to modify:** `clausal/modules/py/torch.py`

**Overlap with scipy:** `scipy_linalg.py` covers the same operations
on numpy arrays (`Determinant`, `Inverse`, `SingularValueDecompose`,
`EigenDecompose`, `Solve`, `Cholesky`, `QrDecompose`, `LuDecompose`).
The PyTorch versions operate on tensors (GPU-accelerated, autograd-aware).
Users choose based on their data type — numpy arrays use scipy, tensors
use torch.

---

## Predicates

| Name | Arity | Modes | Bijective? | Description |
|---|---|---|---|---|
| `det` | `/2` | `(+A, -D)` | no | Determinant |
| `inv` | `/2` | `(+A, -B)` | self-inverse: `inv(inv(A)) == A` | Matrix inverse |
| `solve` | `/3` | `(+A, +B, -X)` | partial — given A,X can recover B | Solve AX=B |
| `svd` | `/2` | `(+A, -USV)` | yes — reconstruct via U @ diag(S) @ Vh | Singular value decomposition |
| `eig` | `/2` | `(+A, -EV)` | partial | Eigendecomposition |
| `cholesky` | `/2` | `(+A, -L)` | yes — A = L @ L.T | Cholesky decomposition |
| `qr` | `/2` | `(+A, -QR)` | yes — A = Q @ R | QR decomposition |
| `norm` | `/2, /3` | `(+A, -N)`, `(+A, +ord, -N)` | no | Matrix/vector norm |
| `matrix_rank` | `/2` | `(+A, -R)` | no | Matrix rank |
| `pinv` | `/2` | `(+A, -B)` | pseudo-self-inverse | Moore-Penrose pseudoinverse |
| `cross` | `/3` | `(+A, +B, -C)` | no | Cross product |
| `dot` | `/3` | `(+A, +B, -C)` | no | Dot product |

Decomposition results are tuples: `svd(A, (U, S, Vh))`, `eig(A, (L, V))`,
`qr(A, (Q, R))`. Users decompose with `is`: `(U, S, Vh) is RESULT`.

---

## Context and Reference Patterns

All predicates are Tier 1 (pure). Follow the `_pure()` + `_pred()` pattern
from Phase 1 in `clausal/modules/py/torch.py`.

For decompositions that return multiple values, the `_pure()` helper
already handles this — the result is a tuple that gets unified with the
output variable. Users decompose with Clausal's `is`:

```python
# Implementation
svd = _pred("svd",
    (2, _pure(lambda a: tuple(_th().linalg.svd(a)))),
)
```

All operations are in `torch.linalg` (not top-level `torch`).

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, det, inv, svd, solve, cholesky,
                         qr, norm, matmul, tensor_list])

# Determinant
Test("determinant of 2x2") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], A),
    det(A, D),
    tensor_list(D, V),
    V > -2.1,
    V < -1.9
)

# Inverse is self-inverse
Test("inv roundtrip") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], A),
    inv(A, B),
    inv(B, C),
    # C should be close to A
    norm(A, NA),
    tensor_list(NA, NV),
    NV > 0.0
)

# SVD decomposition
Test("svd decomposes") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], A),
    svd(A, RESULT),
    RESULT is (U, S, VH),
    shape(U, [2, 2]),
    shape(S, [2]),
    shape(VH, [2, 2])
)

# Solve AX = B
Test("solve linear system") <- (
    tensor([[1.0, 0.0], [0.0, 1.0]], A),
    tensor([3.0, 4.0], B),
    solve(A, B, X),
    tensor_list(X, [3.0, 4.0])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_linalg_tests.clausal`):
- Every predicate with shape verification
- Bijective roundtrips: `inv(inv(A))`, `cholesky` reconstruct, `qr` reconstruct
- `svd`/`eig`/`qr` decomposition and tuple unpacking
- Singular matrix handling (should fail, not crash)
- `norm` with default and explicit ord

**Python unit tests:** Not needed — all pure predicates.

---

## Docs

Update `docs/torch.md` with linear algebra section. All examples backed
by `.clausal` tests.

---

## Issues

1. **SVD full_matrices default.** `torch.linalg.svd` defaults to
   `full_matrices=True`, so for an `(m, n)` matrix with `m < n`, Vh is
   `(n, n)` not `(m, n)`. The plan's example had wrong shapes for the
   rectangular case. Tests corrected to match actual PyTorch behavior.

2. **No issues with `_pure()` pattern.** All 12 predicates fit cleanly
   into the existing `_pure()` helper. Decompositions returning
   `NamedTuple` needed `tuple()` wrapping to produce plain tuples for
   Clausal unification — same as the plan anticipated.

3. **`dot` is `torch.dot`, not `torch.linalg.dot`.** `torch.linalg` has
   no `dot` — it lives at the top-level `torch` namespace. `cross` is
   in `torch.linalg`.
