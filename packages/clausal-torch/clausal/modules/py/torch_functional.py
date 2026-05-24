"""clausal.modules.py.torch_functional — nn.functional predicates for Clausal.

Wraps commonly-used functions from ``torch.nn.functional`` — the stateless
functional API for neural network operations::

    -import_from(torch_functional, [gelu, conv2d, max_pool2d,
        cross_entropy, mse_loss, layer_norm, normalize, dropout])

Activations (beyond Phase 1's relu/softmax)
--------------------------------------------
leaky_relu(T, R) / leaky_relu(T, SLOPE, R)     Leaky ReLU
elu(T, R) / elu(T, ALPHA, R)                    ELU
selu(T, R)                                       SELU
gelu(T, R)                                       GELU
silu(T, R)                                       SiLU / Swish
mish(T, R)                                       Mish
hardswish(T, R)                                   Hard Swish
hardsigmoid(T, R)                                 Hard Sigmoid

Convolutions
-------------
conv1d(INPUT, WEIGHT, OUTPUT) / conv1d(INPUT, WEIGHT, OPTS, OUTPUT)
conv2d(INPUT, WEIGHT, OUTPUT) / conv2d(INPUT, WEIGHT, OPTS, OUTPUT)
conv3d(INPUT, WEIGHT, OUTPUT) / conv3d(INPUT, WEIGHT, OPTS, OUTPUT)

OPTS dict for bias, stride, padding, dilation, groups.

Pooling
--------
max_pool1d(T, KERNEL, R) / max_pool1d(T, KERNEL, OPTS, R)
max_pool2d(T, KERNEL, R) / max_pool2d(T, KERNEL, OPTS, R)
avg_pool1d(T, KERNEL, R) / avg_pool1d(T, KERNEL, OPTS, R)
avg_pool2d(T, KERNEL, R) / avg_pool2d(T, KERNEL, OPTS, R)
adaptive_avg_pool1d(T, OUTPUT_SIZE, R)
adaptive_avg_pool2d(T, OUTPUT_SIZE, R)

Normalization
--------------
batch_norm(INPUT, MEAN, VAR, OUTPUT) / batch_norm(INPUT, MEAN, VAR, OPTS, OUTPUT)
layer_norm(INPUT, SHAPE, OUTPUT) / layer_norm(INPUT, SHAPE, OPTS, OUTPUT)
normalize(T, R) / normalize(T, OPTS, R)

Loss Functions
---------------
cross_entropy(INPUT, TARGET, LOSS) / cross_entropy(INPUT, TARGET, OPTS, LOSS)
mse_loss(INPUT, TARGET, LOSS)
l1_loss(INPUT, TARGET, LOSS)
nll_loss(INPUT, TARGET, LOSS) / nll_loss(INPUT, TARGET, OPTS, LOSS)
binary_cross_entropy(INPUT, TARGET, LOSS)

Dropout
--------
dropout(T, R) / dropout(T, OPTS, R)
"""

from __future__ import annotations

from clausal.modules.py._helpers import _pred, _pure
from clausal.modules.py.torch import _th


# ═══════════════════════════════════════════════════════════════════════════
# Activations
# ═══════════════════════════════════════════════════════════════════════════

def _F():
    return _th().nn.functional

leaky_relu = _pred("leaky_relu",
    (2, _pure(lambda t: _F().leaky_relu(t))),
    (3, _pure(lambda t, slope: _F().leaky_relu(t, negative_slope=slope))),
)

elu = _pred("elu",
    (2, _pure(lambda t: _F().elu(t))),
    (3, _pure(lambda t, alpha: _F().elu(t, alpha=alpha))),
)

selu = _pred("selu",
    (2, _pure(lambda t: _F().selu(t))),
)

gelu = _pred("gelu",
    (2, _pure(lambda t: _F().gelu(t))),
)

silu = _pred("silu",
    (2, _pure(lambda t: _F().silu(t))),
)

mish = _pred("mish",
    (2, _pure(lambda t: _F().mish(t))),
)

hardswish = _pred("hardswish",
    (2, _pure(lambda t: _F().hardswish(t))),
)

hardsigmoid = _pred("hardsigmoid",
    (2, _pure(lambda t: _F().hardsigmoid(t))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Convolutions
# ═══════════════════════════════════════════════════════════════════════════

conv1d = _pred("conv1d",
    (3, _pure(lambda inp, weight: _F().conv1d(inp, weight))),
    (4, _pure(lambda inp, weight, opts: _F().conv1d(inp, weight, **opts))),
)

conv2d = _pred("conv2d",
    (3, _pure(lambda inp, weight: _F().conv2d(inp, weight))),
    (4, _pure(lambda inp, weight, opts: _F().conv2d(inp, weight, **opts))),
)

conv3d = _pred("conv3d",
    (3, _pure(lambda inp, weight: _F().conv3d(inp, weight))),
    (4, _pure(lambda inp, weight, opts: _F().conv3d(inp, weight, **opts))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Pooling
# ═══════════════════════════════════════════════════════════════════════════

max_pool1d = _pred("max_pool1d",
    (3, _pure(lambda t, kernel: _F().max_pool1d(t, kernel))),
    (4, _pure(lambda t, kernel, opts: _F().max_pool1d(t, kernel, **opts))),
)

max_pool2d = _pred("max_pool2d",
    (3, _pure(lambda t, kernel: _F().max_pool2d(t, kernel))),
    (4, _pure(lambda t, kernel, opts: _F().max_pool2d(t, kernel, **opts))),
)

avg_pool1d = _pred("avg_pool1d",
    (3, _pure(lambda t, kernel: _F().avg_pool1d(t, kernel))),
    (4, _pure(lambda t, kernel, opts: _F().avg_pool1d(t, kernel, **opts))),
)

avg_pool2d = _pred("avg_pool2d",
    (3, _pure(lambda t, kernel: _F().avg_pool2d(t, kernel))),
    (4, _pure(lambda t, kernel, opts: _F().avg_pool2d(t, kernel, **opts))),
)

adaptive_avg_pool1d = _pred("adaptive_avg_pool1d",
    (3, _pure(lambda t, output_size: _F().adaptive_avg_pool1d(t, output_size))),
)

adaptive_avg_pool2d = _pred("adaptive_avg_pool2d",
    (3, _pure(lambda t, output_size: _F().adaptive_avg_pool2d(t, output_size))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Normalization
# ═══════════════════════════════════════════════════════════════════════════

batch_norm = _pred("batch_norm",
    (4, _pure(lambda inp, mean, var: _F().batch_norm(inp, mean, var))),
    (5, _pure(lambda inp, mean, var, opts: _F().batch_norm(inp, mean, var, **opts))),
)

layer_norm = _pred("layer_norm",
    (3, _pure(lambda inp, shape: _F().layer_norm(inp, shape))),
    (4, _pure(lambda inp, shape, opts: _F().layer_norm(inp, shape, **opts))),
)

normalize = _pred("normalize",
    (2, _pure(lambda t: _F().normalize(t))),
    (3, _pure(lambda t, opts: _F().normalize(t, **opts))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Loss functions
# ═══════════════════════════════════════════════════════════════════════════

cross_entropy = _pred("cross_entropy",
    (3, _pure(lambda inp, target: _F().cross_entropy(inp, target))),
    (4, _pure(lambda inp, target, opts: _F().cross_entropy(inp, target, **opts))),
)

mse_loss = _pred("mse_loss",
    (3, _pure(lambda inp, target: _F().mse_loss(inp, target))),
)

l1_loss = _pred("l1_loss",
    (3, _pure(lambda inp, target: _F().l1_loss(inp, target))),
)

nll_loss = _pred("nll_loss",
    (3, _pure(lambda inp, target: _F().nll_loss(inp, target))),
    (4, _pure(lambda inp, target, opts: _F().nll_loss(inp, target, **opts))),
)

binary_cross_entropy = _pred("binary_cross_entropy",
    (3, _pure(lambda inp, target: _F().binary_cross_entropy(inp, target))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Dropout
# ═══════════════════════════════════════════════════════════════════════════

dropout = _pred("dropout",
    (2, _pure(lambda t: _F().dropout(t, training=False))),
    (3, _pure(lambda t, opts: _F().dropout(t, **opts))),
)


# ── Module-level exports ─────────────────────────────────────────────────

__all__ = [
    # Activations
    "leaky_relu", "elu", "selu", "gelu", "silu", "mish",
    "hardswish", "hardsigmoid",
    # Convolutions
    "conv1d", "conv2d", "conv3d",
    # Pooling
    "max_pool1d", "max_pool2d", "avg_pool1d", "avg_pool2d",
    "adaptive_avg_pool1d", "adaptive_avg_pool2d",
    # Normalization
    "batch_norm", "layer_norm", "normalize",
    # Loss functions
    "cross_entropy", "mse_loss", "l1_loss", "nll_loss",
    "binary_cross_entropy",
    # Dropout
    "dropout",
]
