# torch_functional — nn.functional

Wraps commonly-used functions from `torch.nn.functional` — the stateless
functional API for neural network operations. These are pure functions
that don't require constructing `nn.Module` objects.

## Import

```clausal
# skip
-import_from(py.torch_functional, [gelu, conv2d, max_pool2d,
    cross_entropy, mse_loss, layer_norm, normalize, dropout])
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

```clausal
# skip
tensor([-1.0, 0.0, 1.0], T),
gelu(T, R),
shape(R, [3])
```

```clausal
# skip
tensor([-1.0, 0.0, 1.0], T),
leaky_relu(T, 0.2, R)
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

```clausal
# skip
randn([1, 1, 5, 5], INPUT),
randn([1, 1, 3, 3], WEIGHT),
conv2d(INPUT, WEIGHT, OUTPUT),
shape(OUTPUT, [1, 1, 3, 3])
```

```clausal
# skip
conv2d(INPUT, WEIGHT, {"padding": 1, "stride": 2}, OUTPUT)
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

```clausal
# skip
randn([1, 1, 4, 4], INPUT),
max_pool2d(INPUT, 2, OUTPUT),
shape(OUTPUT, [1, 1, 2, 2])
```

```clausal
# skip
randn([1, 1, 10, 10], INPUT),
adaptive_avg_pool2d(INPUT, [3, 3], OUTPUT),
shape(OUTPUT, [1, 1, 3, 3])
```

---

## Normalization

| Predicate | Arity | Description |
|-----------|-------|-------------|
| `batch_norm` | `/4, /5` | Batch normalization |
| `layer_norm` | `/3, /4` | Layer normalization |
| `normalize` | `/2, /3` | Lp normalization |

```clausal
# skip
randn([2, 3, 4], INPUT),
layer_norm(INPUT, [4], OUTPUT),
shape(OUTPUT, [2, 3, 4])
```

```clausal
# skip
randn([2, 3, 4], INPUT),
zeros([3], MEAN),
ones([3], VAR),
batch_norm(INPUT, MEAN, VAR, OUTPUT)
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

```clausal
# skip
randn([3, 5], LOGITS),
tensor([0, 2, 1], TARGETS),
cross_entropy(LOGITS, TARGETS, LOSS),
shape(LOSS, [])
```

```clausal
# skip
tensor([1.0, 2.0, 3.0], PRED),
tensor([1.0, 2.0, 3.0], TARGET),
mse_loss(PRED, TARGET, LOSS)
```

---

## Dropout

| Predicate | Arity | Description |
|-----------|-------|-------------|
| `dropout` | `/2, /3` | Dropout |

The 2-arity form runs in eval mode (no dropout applied). The 3-arity
form accepts an opts dict for `p` (drop probability) and `training`.

```clausal
# skip
tensor([1.0, 2.0, 3.0], T),
dropout(T, R)
```
