# Phase 11 — nn.functional

Wraps commonly-used functions from `torch.nn.functional` — the functional
(stateless) API for neural network operations. These are pure functions
that don't require constructing `nn.Module` objects.

**Depends on:** Phase 1 — `clausal/modules/py/torch.py` helpers.

**File to modify:** `clausal/modules/py/torch.py` (or a new
`clausal/modules/py/torch_functional.py` if torch.py is getting large)

**Overlap with nn.Module:** Many of these have `nn.Module` equivalents
(e.g. `F.relu` vs `nn.ReLU()`). The functional forms are useful for
one-off operations without constructing a module. Phase 1 already
wraps `relu/2` and `softmax/3` — this phase adds the rest.

---

## Predicates

### Activations (beyond Phase 1's relu/softmax)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `leaky_relu` | `/2, /3` | `(+T, -R)`, `(+T, +slope, -R)` | Leaky ReLU |
| `elu` | `/2, /3` | `(+T, -R)`, `(+T, +alpha, -R)` | ELU |
| `selu` | `/2` | `(+T, -R)` | SELU |
| `gelu` | `/2` | `(+T, -R)` | GELU |
| `silu` | `/2` | `(+T, -R)` | SiLU / Swish |
| `mish` | `/2` | `(+T, -R)` | Mish |
| `hardswish` | `/2` | `(+T, -R)` | Hard Swish |
| `hardsigmoid` | `/2` | `(+T, -R)` | Hard Sigmoid |

### Convolutions

| Name | Arity | Modes | Description |
|---|---|---|---|
| `conv1d` | `/3, /4` | `(+input, +weight, -output)`, `(+input, +weight, +opts, -output)` | 1D convolution |
| `conv2d` | `/3, /4` | `(+input, +weight, -output)`, `(+input, +weight, +opts, -output)` | 2D convolution |
| `conv3d` | `/3, /4` | as above | 3D convolution |

`opts` dict for bias, stride, padding, dilation, groups.

### Pooling

| Name | Arity | Modes | Description |
|---|---|---|---|
| `max_pool1d` | `/3, /4` | `(+T, +kernel, -R)`, `(+T, +kernel, +opts, -R)` | 1D max pooling |
| `max_pool2d` | `/3, /4` | as above | 2D max pooling |
| `avg_pool1d` | `/3, /4` | as above | 1D average pooling |
| `avg_pool2d` | `/3, /4` | as above | 2D average pooling |
| `adaptive_avg_pool1d` | `/3` | `(+T, +output_size, -R)` | Adaptive 1D avg pool |
| `adaptive_avg_pool2d` | `/3` | `(+T, +output_size, -R)` | Adaptive 2D avg pool |

### Normalization

| Name | Arity | Modes | Description |
|---|---|---|---|
| `batch_norm` | `/3, /4` | `(+input, +mean, +var, -output)`, with opts | Batch normalization |
| `layer_norm` | `/3, /4` | `(+input, +shape, -output)`, with opts | Layer normalization |
| `normalize` | `/2, /3` | `(+T, -R)`, `(+T, +opts, -R)` | Lp normalization |

### Loss functions (functional form)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `cross_entropy` | `/3, /4` | `(+input, +target, -loss)`, with opts | Cross-entropy loss |
| `mse_loss` | `/3` | `(+input, +target, -loss)` | Mean squared error |
| `l1_loss` | `/3` | `(+input, +target, -loss)` | L1 / mean absolute error |
| `nll_loss` | `/3, /4` | `(+input, +target, -loss)`, with opts | Negative log-likelihood |
| `binary_cross_entropy` | `/3` | `(+input, +target, -loss)` | Binary cross-entropy |

### Dropout

| Name | Arity | Modes | Description |
|---|---|---|---|
| `dropout` | `/2, /3` | `(+T, -R)`, `(+T, +opts, -R)` | Dropout (training mode) |

---

## Context and Reference Patterns

All Tier 1 (pure). Convolutions, pooling, and normalization take `opts`
dicts for keyword arguments (stride, padding, etc.) — follow the opts
dict pattern from Phase 1 creation functions.

Functional operations live in `torch.nn.functional`:

```python
conv2d = _pred("conv2d",
    (3, _pure(lambda inp, weight: _th().nn.functional.conv2d(inp, weight))),
    (4, _pure(lambda inp, weight, opts: _th().nn.functional.conv2d(inp, weight, **opts))),
)
```

---

## Example Usage

```clausal
-import_from(py.torch, [tensor, randn, shape])
-import_from(py.torch_functional, [gelu, conv2d, max_pool2d,
    cross_entropy, mse_loss, layer_norm, normalize])

# GELU activation
Test("gelu") <- (
    tensor([-1.0, 0.0, 1.0], T),
    gelu(T, R),
    shape(R, [3])
)

# 2D convolution
Test("conv2d shape") <- (
    randn([1, 1, 5, 5], INPUT),
    randn([1, 1, 3, 3], WEIGHT),
    conv2d(INPUT, WEIGHT, OUTPUT),
    shape(OUTPUT, [1, 1, 3, 3])
)

# Max pooling
Test("max_pool2d") <- (
    randn([1, 1, 4, 4], INPUT),
    max_pool2d(INPUT, 2, OUTPUT),
    shape(OUTPUT, [1, 1, 2, 2])
)

# Cross-entropy loss
Test("cross_entropy") <- (
    randn([3, 5], LOGITS),
    tensor([0, 2, 1], TARGETS),
    cross_entropy(LOGITS, TARGETS, LOSS),
    shape(LOSS, [])    # scalar
)

# MSE loss
Test("mse_loss") <- (
    tensor([1.0, 2.0, 3.0], PRED),
    tensor([1.0, 2.0, 3.0], TARGET),
    mse_loss(PRED, TARGET, LOSS),
    tensor_list(LOSS, 0.0)
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_functional_tests.clausal`):
- All activations with shape verification
- Conv1d/2d/3d with expected output shapes
- Pooling with expected output shapes
- Loss functions with known inputs
- Layer norm / batch norm shape preservation
- Opts dict for stride, padding, etc.

---

## Docs

Create `docs/torch_functional.md` or update `docs/torch.md`.

---

## Issues

_To be populated during implementation._
