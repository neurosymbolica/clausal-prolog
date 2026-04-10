# Phase 13 — Creation Variants and Arithmetic Gaps

Fills gaps in tensor creation (`*_like` variants, `rand`, `randint`) and
basic arithmetic (`sub`, `div`, `neg`).

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` and
`clausal/modules/py/_helpers.py`.

**File to modify:** `clausal/modules/py/torch.py`

---

## Predicates

### Creation variants

| Name | Arity | Modes | Description |
|---|---|---|---|
| `zeros_like` | `/2` | `(+T, -R)` | Zero tensor with same shape/dtype/device as T |
| `ones_like` | `/2` | `(+T, -R)` | Ones tensor, same shape/dtype/device |
| `full_like` | `/3` | `(+T, +value, -R)` | Filled tensor, same shape/dtype/device |
| `empty` | `/2, /3` | `(+shape, -T)`, `(+shape, +opts, -T)` | Uninitialized tensor |
| `rand` | `/2, /3` | `(+shape, -T)`, `(+shape, +opts, -T)` | Uniform random [0, 1) |
| `randint` | `/3, /4` | `(+low, +high, +shape, -T)`, with opts | Random integers |
| `logspace` | `/4, /5` | `(+start, +end, +steps, -T)`, with opts | Logarithmically spaced |
| `diag` | `/2, /3` | `(+T, -R)`, `(+T, +diagonal, -R)` | Create diagonal matrix or extract diagonal |

`diag` is multi-mode: if input is 1D, creates a 2D diagonal matrix;
if input is 2D, extracts the diagonal. PyTorch handles this automatically.

### Arithmetic gaps

| Name | Arity | Modes | Description |
|---|---|---|---|
| `sub` | `/3` | `(+A, +B, -C)` | Element-wise subtract |
| `div` | `/3` | `(+A, +B, -C)` | Element-wise divide |
| `neg` | `/2` | `(+T, -R)` | Element-wise negate |

---

## Context and Reference Patterns

All Tier 1 (pure). Use `_pure` and `_pred` from `_helpers.py`.

`*_like` functions take a tensor as template:

```python
zeros_like = _pred("zeros_like",
    (2, _pure(lambda t: _th().zeros_like(t))),
)
```

`diag` is interesting — PyTorch's `torch.diag` is bidirectional by
nature (1D -> 2D or 2D -> 1D), making it a natural Clausal predicate.

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, zeros, zeros_like, ones_like, full_like,
                         rand, randint, diag, sub, div, neg,
                         shape, dtype, tensor_list])

Test("zeros_like preserves shape and dtype") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], T),
    zeros_like(T, Z),
    shape(Z, [2, 2]),
    dtype(T, DT),
    dtype(Z, DT)
)

Test("diag from 1D creates matrix") <- (
    tensor([1.0, 2.0, 3.0], V),
    diag(V, M),
    shape(M, [3, 3])
)

Test("diag from 2D extracts diagonal") <- (
    tensor([[1.0, 2.0], [3.0, 4.0]], M),
    diag(M, V),
    tensor_list(V, [1.0, 4.0])
)

Test("sub") <- (
    tensor([5.0, 3.0], A),
    tensor([2.0, 1.0], B),
    sub(A, B, C),
    tensor_list(C, [3.0, 2.0])
)

Test("div") <- (
    tensor([6.0, 8.0], A),
    tensor([2.0, 4.0], B),
    div(A, B, C),
    tensor_list(C, [3.0, 2.0])
)

Test("neg") <- (
    tensor([1.0, -2.0, 3.0], T),
    neg(T, R),
    tensor_list(R, [-1.0, 2.0, -3.0])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_creation2_tests.clausal`):
- All `*_like` variants preserving shape/dtype
- `rand`/`randint` shape verification
- `diag` both directions (1D->2D and 2D->1D)
- `sub`, `div`, `neg` with known values
- `logspace` shape and value checks
- `empty` shape verification

---

## Docs

Update `docs/torch.md` with creation variants and arithmetic sections.

---

## Issues

None — all predicates implemented cleanly following existing patterns.
