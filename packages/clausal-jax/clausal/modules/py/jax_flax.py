"""clausal.modules.py.jax_flax — Flax Linen NN layers and init/apply.

`Flax <https://flax.readthedocs.io>`_'s **Linen** API is the second
major NN library for JAX. Unlike Equinox (Phase 17), where the model
**is** its parameters as a single pytree, Flax separates them: the
model is an architecture object, parameters live in a separate
"variables" pytree, and the two combine at apply time.

That separation drives the wrapper's shape: every model goes through
the explicit ``init`` / ``apply`` contract that Flax itself defines.

Import usage::

    -import_from(py.jax_flax, [
        dense, conv, layer_norm, dropout, sequential,
        init, apply, init_with_output,
        apply_mutable, apply_with_rngs,
        max_pool, avg_pool,
        layer_class,
    ])

Phase 18 — Flax Linen
----------------------
All predicates are Tier 1 pure or Tier 3 state-threaded. Flax NNX
(the newer mutable-state API) is out of scope for this phase — see
``implementation_plans/jax/phase18_flax.md`` Issue 1.

Layer constructors (Tier 1 pure; OPTS dict is the optional second
arity):
    dense(FEATURES, M)              / dense(FEATURES, OPTS, M)
    dense_general(FEATURES, M)      / opts variant
    einsum(SHAPE, EQUATION, M)      / opts variant
    conv(FEATURES, KERNEL, M)       / opts variant
    conv_transpose(FEATURES, KERNEL, M) / opts variant
    conv_local(FEATURES, KERNEL, M) / opts variant
    conv_lstm_cell(FEATURES, KERNEL, M) / opts variant
    embed(NUM_EMB, FEATURES, M)     / opts variant
    dropout(RATE, M)                / dropout(RATE, OPTS, M)
    layer_norm(M)                   / layer_norm(OPTS, M)
    group_norm(M)                   / group_norm(OPTS, M)
    instance_norm(M)                / opts variant
    rms_norm(M)                     / opts variant
    batch_norm(M)                   / opts variant
                                      [stateful — apply via apply_mutable]
    spectral_norm(LAYER, M)         / opts variant
    weight_norm(LAYER, M)           / opts variant
    prelu(M)                        / prelu(OPTS, M)
    gru_cell(FEATURES, M)           / opts variant
    lstm_cell(FEATURES, M)          / opts variant
    optimized_lstm_cell(FEATURES, M) / opts variant
    mgu_cell(FEATURES, M)           / opts variant
    simple_cell(FEATURES, M)        / opts variant
    rnn(CELL, M)                    / opts variant
    bidirectional(FWD_CELL, BWD_CELL, M) / opts variant
    multi_head_attention(NHEADS, QKV, M) / opts variant
    multi_head_dot_product_attention(NHEADS, QKV, M) / opts variant
    self_attention(NHEADS, QKV, M)  / opts variant
    sequential(LAYERS, M)

Init / apply (Tier 3 state-threaded — variables flow through):
    init(MODEL, KEY, EXAMPLE, VARS)
    init_with_output(MODEL, KEY, EXAMPLE, RESULT)  % RESULT is (OUT, VARS)
    apply(MODEL, VARS, INPUT, OUT)
    apply_mutable(MODEL, VARS, INPUT, MUTABLE_LIST, RESULT)
                                      % RESULT is (OUT, NEW_STATE)
    apply_with_rngs(MODEL, VARS, INPUT, RNGS_DICT, OUT)

Pool functions (Tier 1 pure — these are functions in Flax, not
Modules; no init/apply needed):
    max_pool(X, WINDOW, R)          / max_pool(X, WINDOW, OPTS, R)
    avg_pool(X, WINDOW, R)          / avg_pool(X, WINDOW, OPTS, R)

Layer enumeration (registry, side-channel for discovery only):
    layer_class(NAME, CLS)          % +/-, -/-

Naming
-------
Predicates use Flax's natural names (``init``, ``apply``,
``init_with_output``) rather than defensively-prefixed forms
(``flax_init``, ``flax_apply``). The module-qualified form
(``flax.init``, ``py.jax_flax.apply``) is always available for
disambiguation when a user imports into a namespace where a
collision matters. Across-module collisions are not the wrapper's
problem — that's what the module system is for.

Variables structure
--------------------
``init`` returns a dict: ``{"params": {...}}`` for plain layers,
``{"params": {...}, "batch_stats": {...}}`` with BatchNorm, etc.
Use Phase 9 pytree predicates (``leaf``, ``tree_flatten``) to
inspect.

Stateful BatchNorm
-------------------
Plain ``apply(BN, VARS, X, Y)`` will fail — BatchNorm needs its
``batch_stats`` collection mutable during training. Use
``apply_mutable(BN, VARS, X, ["batch_stats"], RESULT)`` and decompose
``RESULT is (OUT, NEW_STATE)``.

Stochastic Dropout
-------------------
Dropout's per-call randomness comes via ``apply_with_rngs/5``::

    apply_with_rngs(DROP, VARS, X, {"dropout": K_DROP}, Y)
"""

from __future__ import annotations

import threading as _threading

from clausal.modules.py._helpers import _pred, _pure, _fact_table_2
from clausal.modules.py.jax import _ensure_jax  # noqa: F401 — surfaces JAX dep


# ═══════════════════════════════════════════════════════════════════════════
# Lazy import
# ═══════════════════════════════════════════════════════════════════════════

_flax = None
_flax_lock = _threading.Lock()


def _ensure_flax():
    global _flax
    if _flax is not None:
        return
    with _flax_lock:
        if _flax is not None:
            return
        from clausal.modules.py import _import_stdlib
        _flax = _import_stdlib("flax")


def _fnn():
    _ensure_flax()
    import flax.linen as _m
    return _m


# ═══════════════════════════════════════════════════════════════════════════
# Layer constructors — single positional arg, plus optional opts
# ═══════════════════════════════════════════════════════════════════════════

dense = _pred("dense",
    (2, _pure(lambda f: _fnn().Dense(f))),
    (3, _pure(lambda f, opts: _fnn().Dense(f, **opts))),
)

dense_general = _pred("dense_general",
    (2, _pure(lambda f: _fnn().DenseGeneral(f))),
    (3, _pure(lambda f, opts: _fnn().DenseGeneral(f, **opts))),
)

einsum = _pred("einsum",
    (3, _pure(lambda shape, eqn: _fnn().Einsum(shape, eqn))),
    (4, _pure(lambda shape, eqn, opts: _fnn().Einsum(shape, eqn, **opts))),
)

conv = _pred("conv",
    (3, _pure(lambda f, ks: _fnn().Conv(f, tuple(ks)))),
    (4, _pure(lambda f, ks, opts: _fnn().Conv(f, tuple(ks), **opts))),
)

conv_transpose = _pred("conv_transpose",
    (3, _pure(lambda f, ks: _fnn().ConvTranspose(f, tuple(ks)))),
    (4, _pure(lambda f, ks, opts:
              _fnn().ConvTranspose(f, tuple(ks), **opts))),
)

conv_local = _pred("conv_local",
    (3, _pure(lambda f, ks: _fnn().ConvLocal(f, tuple(ks)))),
    (4, _pure(lambda f, ks, opts: _fnn().ConvLocal(f, tuple(ks), **opts))),
)

conv_lstm_cell = _pred("conv_lstm_cell",
    (3, _pure(lambda f, ks: _fnn().ConvLSTMCell(f, tuple(ks)))),
    (4, _pure(lambda f, ks, opts:
              _fnn().ConvLSTMCell(f, tuple(ks), **opts))),
)

embed = _pred("embed",
    (3, _pure(lambda n, f: _fnn().Embed(n, f))),
    (4, _pure(lambda n, f, opts: _fnn().Embed(n, f, **opts))),
)

dropout = _pred("dropout",
    (2, _pure(lambda r: _fnn().Dropout(r))),
    (3, _pure(lambda r, opts: _fnn().Dropout(r, **opts))),
)

# Norms — no required positional args
layer_norm = _pred("layer_norm",
    (1, _pure(lambda: _fnn().LayerNorm())),
    (2, _pure(lambda opts: _fnn().LayerNorm(**opts))),
)

group_norm = _pred("group_norm",
    (1, _pure(lambda: _fnn().GroupNorm())),
    (2, _pure(lambda opts: _fnn().GroupNorm(**opts))),
)

instance_norm = _pred("instance_norm",
    (1, _pure(lambda: _fnn().InstanceNorm())),
    (2, _pure(lambda opts: _fnn().InstanceNorm(**opts))),
)

rms_norm = _pred("rms_norm",
    (1, _pure(lambda: _fnn().RMSNorm())),
    (2, _pure(lambda opts: _fnn().RMSNorm(**opts))),
)

batch_norm = _pred("batch_norm",
    (1, _pure(lambda: _fnn().BatchNorm())),
    (2, _pure(lambda opts: _fnn().BatchNorm(**opts))),
)

spectral_norm = _pred("spectral_norm",
    (2, _pure(lambda layer: _fnn().SpectralNorm(layer))),
    (3, _pure(lambda layer, opts: _fnn().SpectralNorm(layer, **opts))),
)

weight_norm = _pred("weight_norm",
    (2, _pure(lambda layer: _fnn().WeightNorm(layer))),
    (3, _pure(lambda layer, opts: _fnn().WeightNorm(layer, **opts))),
)

prelu = _pred("prelu",
    (1, _pure(lambda: _fnn().PReLU())),
    (2, _pure(lambda opts: _fnn().PReLU(**opts))),
)

# Recurrent cells
gru_cell = _pred("gru_cell",
    (2, _pure(lambda f: _fnn().GRUCell(f))),
    (3, _pure(lambda f, opts: _fnn().GRUCell(f, **opts))),
)

lstm_cell = _pred("lstm_cell",
    (2, _pure(lambda f: _fnn().LSTMCell(f))),
    (3, _pure(lambda f, opts: _fnn().LSTMCell(f, **opts))),
)

optimized_lstm_cell = _pred("optimized_lstm_cell",
    (2, _pure(lambda f: _fnn().OptimizedLSTMCell(f))),
    (3, _pure(lambda f, opts: _fnn().OptimizedLSTMCell(f, **opts))),
)

mgu_cell = _pred("mgu_cell",
    (2, _pure(lambda f: _fnn().MGUCell(f))),
    (3, _pure(lambda f, opts: _fnn().MGUCell(f, **opts))),
)

simple_cell = _pred("simple_cell",
    (2, _pure(lambda f: _fnn().SimpleCell(f))),
    (3, _pure(lambda f, opts: _fnn().SimpleCell(f, **opts))),
)

# RNN sequence wrappers
rnn = _pred("rnn",
    (2, _pure(lambda cell: _fnn().RNN(cell))),
    (3, _pure(lambda cell, opts: _fnn().RNN(cell, **opts))),
)

bidirectional = _pred("bidirectional",
    (3, _pure(lambda fwd, bwd: _fnn().Bidirectional(fwd, bwd))),
    (4, _pure(lambda fwd, bwd, opts:
              _fnn().Bidirectional(fwd, bwd, **opts))),
)

# Attention
multi_head_attention = _pred("multi_head_attention",
    (3, _pure(lambda nh, qkv: _fnn().MultiHeadAttention(nh, qkv))),
    (4, _pure(lambda nh, qkv, opts:
              _fnn().MultiHeadAttention(nh, qkv, **opts))),
)

multi_head_dot_product_attention = _pred("multi_head_dot_product_attention",
    (3, _pure(lambda nh, qkv:
              _fnn().MultiHeadDotProductAttention(nh, qkv))),
    (4, _pure(lambda nh, qkv, opts:
              _fnn().MultiHeadDotProductAttention(nh, qkv, **opts))),
)

self_attention = _pred("self_attention",
    (3, _pure(lambda nh, qkv: _fnn().SelfAttention(nh, qkv))),
    (4, _pure(lambda nh, qkv, opts:
              _fnn().SelfAttention(nh, qkv, **opts))),
)

# Composition
sequential = _pred("sequential",
    (2, _pure(lambda layers: _fnn().Sequential(layers))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Init / apply (state-threaded; this IS the Flax discipline)
# ═══════════════════════════════════════════════════════════════════════════

init = _pred("init",
    (4, _pure(lambda m, key, example: m.init(key, example))),
)

# init_with_output returns (output, variables) — single tuple result.
init_with_output = _pred("init_with_output",
    (4, _pure(lambda m, key, example:
              tuple(m.init_with_output(key, example)))),
)

apply = _pred("apply",
    (4, _pure(lambda m, variables, x: m.apply(variables, x))),
)

# When mutable is non-empty, m.apply returns (out, new_state) — tuple.
apply_mutable = _pred("apply_mutable",
    (5, _pure(lambda m, variables, x, mutable:
              tuple(m.apply(variables, x, mutable=mutable)))),
)

apply_with_rngs = _pred("apply_with_rngs",
    (5, _pure(lambda m, variables, x, rngs:
              m.apply(variables, x, rngs=rngs))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Pool functions (Tier 1 pure — these are functions in Flax, not Modules)
# ═══════════════════════════════════════════════════════════════════════════

# Flax's pool functions require tuples (not lists) for shape args
# like `strides`. Coerce known shape-tuple opts so callers can pass
# either form from Clausal.
_POOL_TUPLE_OPTS = ("strides", "window_shape", "padding")


def _coerce_pool_opts(opts):
    out = dict(opts)
    for k in _POOL_TUPLE_OPTS:
        if k in out and isinstance(out[k], list):
            out[k] = tuple(out[k])
    return out


max_pool = _pred("max_pool",
    (3, _pure(lambda x, w: _fnn().max_pool(x, tuple(w)))),
    (4, _pure(lambda x, w, opts:
              _fnn().max_pool(x, tuple(w), **_coerce_pool_opts(opts)))),
)

avg_pool = _pred("avg_pool",
    (3, _pure(lambda x, w: _fnn().avg_pool(x, tuple(w)))),
    (4, _pure(lambda x, w, opts:
              _fnn().avg_pool(x, tuple(w), **_coerce_pool_opts(opts)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Layer-class registry (discovery side-channel)
# ═══════════════════════════════════════════════════════════════════════════

def _build_layer_class_facts():
    _ensure_flax()
    import flax.linen as nn
    import inspect
    out = []
    for n in dir(nn):
        if n.startswith("_"):
            continue
        cls = getattr(nn, n)
        if inspect.isclass(cls) and issubclass(cls, nn.Module):
            out.append((n, cls))
    return out


layer_class = _pred("layer_class",
    (2, _fact_table_2(_build_layer_class_facts)),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Layer constructors — single positional arg
    "dense", "dense_general", "einsum",
    "conv", "conv_transpose", "conv_local", "conv_lstm_cell",
    "embed", "dropout",
    "layer_norm", "group_norm", "instance_norm", "rms_norm",
    "batch_norm", "spectral_norm", "weight_norm",
    "prelu",
    "gru_cell", "lstm_cell", "optimized_lstm_cell",
    "mgu_cell", "simple_cell",
    "rnn", "bidirectional",
    "multi_head_attention", "multi_head_dot_product_attention",
    "self_attention",
    "sequential",
    # Init / apply
    "init", "init_with_output", "apply",
    "apply_mutable", "apply_with_rngs",
    # Pool functions
    "max_pool", "avg_pool",
    # Registry
    "layer_class",
]
