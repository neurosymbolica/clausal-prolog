# torch_functional — nn.functional

Wraps commonly-used functions from `torch.nn.functional` — the stateless
functional API for neural network operations. These are pure functions
that don't require constructing `nn.Module` objects.

## Import

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:import"
```

---

## Tiers

| Tier | Predicates | Notes |
|------|-----------|-------|
| 1 — pure | All predicates | Stateless functional operations |

---

## Activations

Beyond Phase 1's `relu` and `softmax`, these additional activations are
available:

| Predicate | Arity | Description |
|-----------|-------|-------------|
| `leaky_relu` | `/2, /3` | Leaky ReLU; optional negative slope |
| `elu` | `/2, /3` | ELU; optional alpha |
| `selu` | `/2` | SELU |
| `gelu` | `/2` | GELU |
| `silu` | `/2` | SiLU / Swish |
| `mish` | `/2` | Mish |
| `hardswish` | `/2` | Hard Swish |
| `hardsigmoid` | `/2` | Hard Sigmoid |

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:activations"
```

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:activations_ex2"
```

---

## Convolutions

| Predicate | Arity | Description |
|-----------|-------|-------------|
| `conv1d` | `/3, /4` | 1D convolution |
| `conv2d` | `/3, /4` | 2D convolution |
| `conv3d` | `/3, /4` | 3D convolution |

The 3-arity form takes `(+input, +weight, -output)`. The 4-arity form
adds an opts dict for `bias`, `stride`, `padding`, `dilation`, `groups`.

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:convolutions"
```

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:convolutions_ex2"
```

---

## Pooling

| Predicate | Arity | Description |
|-----------|-------|-------------|
| `max_pool1d` | `/3, /4` | 1D max pooling |
| `max_pool2d` | `/3, /4` | 2D max pooling |
| `avg_pool1d` | `/3, /4` | 1D average pooling |
| `avg_pool2d` | `/3, /4` | 2D average pooling |
| `adaptive_avg_pool1d` | `/3` | Adaptive 1D average pooling |
| `adaptive_avg_pool2d` | `/3` | Adaptive 2D average pooling |

The 3-arity form takes `(+input, +kernel_size, -output)`. The 4-arity
form adds an opts dict for `stride`, `padding`, etc.

Adaptive pooling takes a target output size instead of a kernel size.

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:pooling"
```

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:pooling_ex2"
```

---

## Normalization

| Predicate | Arity | Description |
|-----------|-------|-------------|
| `batch_norm` | `/4, /5` | Batch normalization |
| `layer_norm` | `/3, /4` | Layer normalization |
| `normalize` | `/2, /3` | Lp normalization |

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:normalization"
```

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:normalization_ex2"
```

---

## Loss Functions

| Predicate | Arity | Description |
|-----------|-------|-------------|
| `cross_entropy` | `/3, /4` | Cross-entropy loss |
| `mse_loss` | `/3` | Mean squared error |
| `l1_loss` | `/3` | L1 / mean absolute error |
| `nll_loss` | `/3, /4` | Negative log-likelihood |
| `binary_cross_entropy` | `/3` | Binary cross-entropy |

The 4-arity forms accept an opts dict (e.g. `{"reduction": "none"}`).

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:loss_functions"
```

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:loss_functions_ex2"
```

---

## Dropout

| Predicate | Arity | Description |
|-----------|-------|-------------|
| `dropout` | `/2, /3` | Dropout |

The 2-arity form runs in eval mode (no dropout applied). The 3-arity
form accepts an opts dict for `p` (drop probability) and `training`.

```seam
--8<-- "tests/fixtures/docs/torch_functional_sigs.txt:dropout"
```
