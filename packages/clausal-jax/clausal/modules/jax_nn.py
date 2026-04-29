"""clausal.modules.jax_nn — JAX activations and initializers.

``jax.nn`` is small compared to ``torch.nn``: no module classes (JAX is
a function library — model classes live in Flax / Equinox). What it
does provide is a clean set of activation functions plus a parameter
initializer registry. Both map cleanly to Clausal fact tables.

Import usage::

    -import_from(py.jax_nn, [
        activation, initializer, init_array,
        relu_apply, sigmoid_apply, tanh_apply,
        softmax_apply, log_softmax_apply,
        gelu_apply, elu_apply, leaky_relu_apply,
        selu_apply, softplus_apply, silu_apply,
        one_hot,
    ])

Phase 10 — Activations and Initializers
-----------------------------------------

Registries (nondeterministic fact tables):
    activation(NAME, FN)        Enumerate or look up activation by name
    initializer(NAME, FACTORY)  Enumerate or look up initializer

Applied activations (Tier 1 pure):
    relu_apply(A, R)
    sigmoid_apply(A, R)         Alias of jax.nn.sigmoid (also in Phase 7)
    tanh_apply(A, R)
    softmax_apply(A, AXIS, R)
    log_softmax_apply(A, AXIS, R)
    gelu_apply(A, R)  / gelu_apply(A, APPROX, R)
    elu_apply(A, R)
    leaky_relu_apply(A, R)  / leaky_relu_apply(A, NEG_SLOPE, R)
    selu_apply(A, R)
    softplus_apply(A, R)
    silu_apply(A, R)             Also known as swish

One-hot encoding:
    one_hot(X, NUM_CLASSES, R) / one_hot(X, NUM_CLASSES, DTYPE, R)

Initializer application:
    init_array(FACTORY, KEY, SHAPE, A)
    init_array(FACTORY, KEY, SHAPE, DTYPE, A)

The `_apply` suffix disambiguates applied activations from registry
atoms. ``sigmoid_apply`` here is the same function as the Phase 7
``sigmoid``; both exist so users can stay inside one import block.

Initializers — direct vs factory
---------------------------------
The ``jax.nn.initializers`` registry mixes two kinds of objects:

* **Direct initializers** (``zeros``, ``ones``) — already callable as
  ``init(key, shape[, dtype])``.
* **Factories** (``glorot_uniform``, ``he_normal``, ``normal``, ...) —
  callable with no args (or config args) to *produce* an initializer.

``init_array/4,/5`` handles both: introspects the callable's signature
and, if the first required positional parameter is named ``key``,
calls it directly; otherwise calls it with no args first to build the
initializer. For initializers that need config args (e.g.
``variance_scaling(2.0, "fan_in", "normal")``), construct the
configured initializer via ``++()`` and pass that::

    F is ++(jax.nn.initializers.variance_scaling(2.0, "fan_in", "normal")),
    init_array(F, K, SHAPE, A)

The configured initializer is itself direct-callable, so this path
works identically to ``zeros``/``ones``.
"""

from __future__ import annotations

import inspect as _inspect
import threading as _threading

from clausal.modules.py._helpers import _pred, _pure, _fact_table_2
from clausal.modules.jax import _ensure_jax


# ── Lazy jax.nn / jax.nn.initializers import ──────────────────────────────

_jnn_mod = None
_jni_mod = None
_jn_lock = _threading.Lock()


def _jnn():
    global _jnn_mod
    if _jnn_mod is not None:
        return _jnn_mod
    with _jn_lock:
        if _jnn_mod is not None:
            return _jnn_mod
        _ensure_jax()
        from clausal.modules.py import _import_stdlib
        _jnn_mod = _import_stdlib("jax.nn")
    return _jnn_mod


def _jni():
    global _jni_mod
    if _jni_mod is not None:
        return _jni_mod
    with _jn_lock:
        if _jni_mod is not None:
            return _jni_mod
        _ensure_jax()
        from clausal.modules.py import _import_stdlib
        _jni_mod = _import_stdlib("jax.nn.initializers")
    return _jni_mod


# ═══════════════════════════════════════════════════════════════════════════
# Activation registry
# ═══════════════════════════════════════════════════════════════════════════

_ACTIVATION_NAMES = (
    "relu", "relu6", "sigmoid", "tanh", "softmax", "log_softmax",
    "gelu", "elu", "leaky_relu", "selu", "softplus", "silu",
    "swish", "mish", "hard_tanh", "hard_sigmoid", "hard_silu",
    "hard_swish", "celu", "glu", "soft_sign", "logsumexp",
)


def _build_activation_facts():
    jnn = _jnn()
    facts = []
    for name in _ACTIVATION_NAMES:
        fn = getattr(jnn, name, None)
        if fn is not None and callable(fn):
            facts.append((name, fn))
    return facts


activation = _pred("activation",
    (2, _fact_table_2(_build_activation_facts)),
)


# ═══════════════════════════════════════════════════════════════════════════
# Initializer registry
# ═══════════════════════════════════════════════════════════════════════════

_INITIALIZER_NAMES = (
    "zeros", "ones", "constant", "normal", "uniform",
    "truncated_normal", "variance_scaling",
    "glorot_normal", "glorot_uniform",
    "xavier_normal", "xavier_uniform",
    "he_normal", "he_uniform",
    "kaiming_normal", "kaiming_uniform",
    "lecun_normal", "lecun_uniform",
    "orthogonal", "delta_orthogonal",
)


def _build_initializer_facts():
    jni = _jni()
    facts = []
    for name in _INITIALIZER_NAMES:
        obj = getattr(jni, name, None)
        if obj is not None:
            facts.append((name, obj))
    return facts


initializer = _pred("initializer",
    (2, _fact_table_2(_build_initializer_facts)),
)


# ═══════════════════════════════════════════════════════════════════════════
# Initializer application
# ═══════════════════════════════════════════════════════════════════════════
#
# An initializer is callable with (key, shape[, dtype]). A factory is
# callable with no args (or config args) to produce an initializer. We
# distinguish by inspecting the first required positional parameter:
# direct initializers require `key` as their first positional; factories
# require config args or nothing.

def _is_direct_initializer(fn):
    try:
        sig = _inspect.signature(fn)
    except (ValueError, TypeError):
        return False
    required = [
        p for p in sig.parameters.values()
        if p.default is p.empty
        and p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)
    ]
    return bool(required) and required[0].name == "key"


def _apply_initializer(factory, key, shape, dtype=None):
    # Accept a scalar for 1-D init or an iterable for any rank.
    if isinstance(shape, (list, tuple)):
        shape_tuple = tuple(int(d) for d in shape)
    else:
        shape_tuple = (int(shape),)
    init = factory if _is_direct_initializer(factory) else factory()
    if dtype is None:
        return init(key, shape_tuple)
    return init(key, shape_tuple, dtype)


init_array = _pred("init_array",
    (4, _pure(lambda factory, key, shape:
              _apply_initializer(factory, key, shape))),
    (5, _pure(lambda factory, key, shape, dtype:
              _apply_initializer(factory, key, shape, dtype))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Applied activations
# ═══════════════════════════════════════════════════════════════════════════

relu_apply = _pred("relu_apply",
    (2, _pure(lambda a: _jnn().relu(a))),
)

sigmoid_apply = _pred("sigmoid_apply",
    (2, _pure(lambda a: _jnn().sigmoid(a))),
)

tanh_apply = _pred("tanh_apply",
    (2, _pure(lambda a: _jnn().tanh(a))),
)

softmax_apply = _pred("softmax_apply",
    (3, _pure(lambda a, axis: _jnn().softmax(a, axis=int(axis)))),
)

log_softmax_apply = _pred("log_softmax_apply",
    (3, _pure(lambda a, axis: _jnn().log_softmax(a, axis=int(axis)))),
)

gelu_apply = _pred("gelu_apply",
    (2, _pure(lambda a: _jnn().gelu(a))),
    (3, _pure(lambda a, approx: _jnn().gelu(a, approximate=bool(approx)))),
)

elu_apply = _pred("elu_apply",
    (2, _pure(lambda a: _jnn().elu(a))),
)

leaky_relu_apply = _pred("leaky_relu_apply",
    (2, _pure(lambda a: _jnn().leaky_relu(a))),
    (3, _pure(lambda a, neg_slope:
              _jnn().leaky_relu(a, negative_slope=float(neg_slope)))),
)

selu_apply = _pred("selu_apply",
    (2, _pure(lambda a: _jnn().selu(a))),
)

softplus_apply = _pred("softplus_apply",
    (2, _pure(lambda a: _jnn().softplus(a))),
)

silu_apply = _pred("silu_apply",
    (2, _pure(lambda a: _jnn().silu(a))),
)

one_hot = _pred("one_hot",
    (3, _pure(lambda x, num_classes:
              _jnn().one_hot(x, int(num_classes)))),
    (4, _pure(lambda x, num_classes, dtype:
              _jnn().one_hot(x, int(num_classes), dtype=dtype))),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Registries
    "activation", "initializer",
    # Initializer application
    "init_array",
    # Applied activations
    "relu_apply", "sigmoid_apply", "tanh_apply",
    "softmax_apply", "log_softmax_apply",
    "gelu_apply", "elu_apply", "leaky_relu_apply",
    "selu_apply", "softplus_apply", "silu_apply",
    # One-hot
    "one_hot",
]
