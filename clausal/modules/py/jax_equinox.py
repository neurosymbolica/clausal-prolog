"""clausal.modules.py.jax_equinox — Equinox NN layers, filter transforms, pytree utilities.

`Equinox <https://docs.kidger.site/equinox/>`_ is the JAX library
that makes neural-net modules first-class pytrees. An ``eqx.Module``
is a registered JAX dataclass: instantiate once with the right
shapes plus a PRNG key, then apply it like any callable. The library
adds **filter** variants of JAX's transforms (``filter_jit``,
``filter_grad``, …) so trees containing non-array leaves (Python
functions, booleans, the modules themselves) work without manual
partitioning.

This module ties Phase 9 (pytrees), Phase 10 (activations), Phase 12
(transforms), and Phase 16 (optax) together into a complete training
story.

Import usage::

    -import_from(py.jax_equinox, [
        linear, mlp, layer_norm, sequential,
        apply_module,
        filter_grad_value, filter_value_and_grad, filter_jit_compile,
        partition, combine, tree_at_set,
        is_array, tree_equal,
        serialise, deserialise,
    ])

Phase 17 — Equinox (stateless surface)
---------------------------------------
All predicates are Tier 1 pure or Tier 4 IO (serialisation only).
Stateful modules (``BatchNorm``, training-mode ``Dropout``,
``StateIndex``, ``StatefulLayer``) are tracked under Phase 17b — see
``implementation_plans/jax/phase17b_equinox_stateful.md``.

Layer constructors (all key-required ones take KEY as the last
positional arg; OPTS dict goes immediately before KEY when present):
    linear(IN, OUT, KEY, M)                 / linear(IN, OUT, OPTS, KEY, M)
    mlp(IN, OUT, WIDTH, DEPTH, KEY, M)      / mlp(..., OPTS, KEY, M)
    conv(NDIMS, IN, OUT, KERNEL, KEY, M)    / conv(..., OPTS, KEY, M)
    conv1d(IN, OUT, KERNEL, KEY, M)         / conv1d(..., OPTS, KEY, M)
    conv2d(IN, OUT, KERNEL, KEY, M)         / conv2d(..., OPTS, KEY, M)
    conv3d(IN, OUT, KERNEL, KEY, M)         / conv3d(..., OPTS, KEY, M)
    conv_transpose(NDIMS, IN, OUT, KERNEL, KEY, M) / opts variant
    conv_transpose1d/2d/3d(IN, OUT, KERNEL, KEY, M) / opts variant
    gru_cell(IN, HIDDEN, KEY, M)            / opts variant
    lstm_cell(IN, HIDDEN, KEY, M)           / opts variant
    multihead_attention(NHEADS, QSIZE, KEY, M) / opts variant
    spectral_norm(LAYER, WEIGHT_NAME, KEY, M)  / opts variant
    embedding(NUM, SIZE, KEY, M)            / opts variant

Layer constructors (no key needed):
    layer_norm(SHAPE, M)                    / layer_norm(SHAPE, OPTS, M)
    group_norm(GROUPS, M)                   / group_norm(GROUPS, OPTS, M)
    rms_norm(SHAPE, M)                      / rms_norm(SHAPE, OPTS, M)
    dropout(P, M)                           / dropout(P, OPTS, M)
                                              [defaults inference=True;
                                               training-mode is Phase 17b]
    identity(M)                             / identity(OPTS, M)
    lambda_layer(FN, M)
    sequential(LAYERS, M)
    prelu(M)                                / prelu(INIT_ALPHA, M)
    rotary_positional_embedding(SIZE, M)    / opts variant
    weight_norm(LAYER, M)                   / opts variant

Pooling:
    max_pool1d(KERNEL, M)                   / max_pool1d(KERNEL, OPTS, M)
    max_pool2d(KERNEL, M)                   / opts variant
    max_pool3d(KERNEL, M)                   / opts variant
    avg_pool1d/2d/3d(KERNEL, M)             / opts variants
    adaptive_max_pool1d/2d/3d(TARGET_SHAPE, M)
    adaptive_avg_pool1d/2d/3d(TARGET_SHAPE, M)

Module application:
    apply_module(M, X, Y)                   % Equivalent to ++(M(X)),
                                              with deep-deref on X
    apply_module(M, X, KWARGS, Y)           % Apply with kwargs
                                              (e.g. {"key": K} for Dropout)

Filter transforms (Phase 12 analogues with filter semantics):
    filter_grad_value(F, X, G)
    filter_value_and_grad(F, X, RESULT)     % RESULT is (V, G)
    filter_jit_compile(F, F2)
    filter_vmap_apply(F, X, R)              / filter_vmap_apply(F, X, OPTS, R)
    filter_pmap_apply(F, X, R)              / filter_pmap_apply(F, X, OPTS, R)

Partition / combine (functional split of a pytree by filter spec):
    partition(TREE, FILTER, DIFF, STATIC)
    combine(DIFF, STATIC, TREE)

Functional updates by callable path:
    tree_at_set(WHERE, TREE, REPLACE, NEW_TREE)
    tree_at_apply(WHERE, TREE, FN, NEW_TREE)

Leaf checks (Tier 1 pure check predicates):
    is_array(X)                             % eqx.is_array
    is_inexact_array(X)                     % float / complex arrays only
    is_array_like(X)                        % arrays + Python scalars
    tree_equal(A, B)

Serialisation (Tier 4 IO — side-effecting; not backtracking-safe):
    serialise(TREE, PATH)
    deserialise(PATH, LIKE_TREE, TREE)

Layer enumeration (registry, side-channel for discovery only):
    layer_class(NAME, CLS)                  % +/-, -/-

`apply_updates` is intentionally NOT exported here — its canonical
home is ``py.jax_tree.apply_updates``. Both ``optax.apply_updates``
and ``eqx.apply_updates`` are thin wrappers around the same
``tree_map``.
"""

from __future__ import annotations

import threading as _threading

from clausal.modules.py._helpers import (
    _pred, _pure, _check_1, _check_2, _fact_table_2,
)
from clausal.modules.py.jax import _ensure_jax  # noqa: F401 — surfaces JAX dep


# ═══════════════════════════════════════════════════════════════════════════
# Lazy import
# ═══════════════════════════════════════════════════════════════════════════

_equinox = None
_equinox_lock = _threading.Lock()


def _ensure_equinox():
    global _equinox
    if _equinox is not None:
        return
    with _equinox_lock:
        if _equinox is not None:
            return
        from clausal.modules.py import _import_stdlib
        _equinox = _import_stdlib("equinox")


def _eqx():
    _ensure_equinox()
    return _equinox


def _enn():
    _ensure_equinox()
    import equinox.nn as _m
    return _m


# ═══════════════════════════════════════════════════════════════════════════
# Layer constructors — key-required
# ═══════════════════════════════════════════════════════════════════════════

linear = _pred("linear",
    (4, _pure(lambda i, o, k: _enn().Linear(i, o, key=k))),
    (5, _pure(lambda i, o, opts, k: _enn().Linear(i, o, key=k, **opts))),
)

mlp = _pred("mlp",
    (6, _pure(lambda i, o, w, d, k: _enn().MLP(i, o, w, d, key=k))),
    (7, _pure(lambda i, o, w, d, opts, k:
              _enn().MLP(i, o, w, d, key=k, **opts))),
)

conv = _pred("conv",
    (6, _pure(lambda nd, i, o, ks, k:
              _enn().Conv(nd, i, o, ks, key=k))),
    (7, _pure(lambda nd, i, o, ks, opts, k:
              _enn().Conv(nd, i, o, ks, key=k, **opts))),
)

conv1d = _pred("conv1d",
    (5, _pure(lambda i, o, ks, k: _enn().Conv1d(i, o, ks, key=k))),
    (6, _pure(lambda i, o, ks, opts, k:
              _enn().Conv1d(i, o, ks, key=k, **opts))),
)

conv2d = _pred("conv2d",
    (5, _pure(lambda i, o, ks, k: _enn().Conv2d(i, o, ks, key=k))),
    (6, _pure(lambda i, o, ks, opts, k:
              _enn().Conv2d(i, o, ks, key=k, **opts))),
)

conv3d = _pred("conv3d",
    (5, _pure(lambda i, o, ks, k: _enn().Conv3d(i, o, ks, key=k))),
    (6, _pure(lambda i, o, ks, opts, k:
              _enn().Conv3d(i, o, ks, key=k, **opts))),
)

conv_transpose = _pred("conv_transpose",
    (6, _pure(lambda nd, i, o, ks, k:
              _enn().ConvTranspose(nd, i, o, ks, key=k))),
    (7, _pure(lambda nd, i, o, ks, opts, k:
              _enn().ConvTranspose(nd, i, o, ks, key=k, **opts))),
)

conv_transpose1d = _pred("conv_transpose1d",
    (5, _pure(lambda i, o, ks, k:
              _enn().ConvTranspose1d(i, o, ks, key=k))),
    (6, _pure(lambda i, o, ks, opts, k:
              _enn().ConvTranspose1d(i, o, ks, key=k, **opts))),
)

conv_transpose2d = _pred("conv_transpose2d",
    (5, _pure(lambda i, o, ks, k:
              _enn().ConvTranspose2d(i, o, ks, key=k))),
    (6, _pure(lambda i, o, ks, opts, k:
              _enn().ConvTranspose2d(i, o, ks, key=k, **opts))),
)

conv_transpose3d = _pred("conv_transpose3d",
    (5, _pure(lambda i, o, ks, k:
              _enn().ConvTranspose3d(i, o, ks, key=k))),
    (6, _pure(lambda i, o, ks, opts, k:
              _enn().ConvTranspose3d(i, o, ks, key=k, **opts))),
)

gru_cell = _pred("gru_cell",
    (4, _pure(lambda i, h, k: _enn().GRUCell(i, h, key=k))),
    (5, _pure(lambda i, h, opts, k: _enn().GRUCell(i, h, key=k, **opts))),
)

lstm_cell = _pred("lstm_cell",
    (4, _pure(lambda i, h, k: _enn().LSTMCell(i, h, key=k))),
    (5, _pure(lambda i, h, opts, k:
              _enn().LSTMCell(i, h, key=k, **opts))),
)

multihead_attention = _pred("multihead_attention",
    (4, _pure(lambda nh, qs, k:
              _enn().MultiheadAttention(nh, qs, key=k))),
    (5, _pure(lambda nh, qs, opts, k:
              _enn().MultiheadAttention(nh, qs, key=k, **opts))),
)

spectral_norm = _pred("spectral_norm",
    (4, _pure(lambda layer, wn, k:
              _enn().SpectralNorm(layer, wn, key=k))),
    (5, _pure(lambda layer, wn, opts, k:
              _enn().SpectralNorm(layer, wn, key=k, **opts))),
)

# Embedding: key is optional in Equinox, but the common case provides
# one. Expose the with-key form; callers wanting to supply a weight
# directly use ++() with `eqx.nn.Embedding(weight=W)`.
embedding = _pred("embedding",
    (4, _pure(lambda n, s, k: _enn().Embedding(n, s, key=k))),
    (5, _pure(lambda n, s, opts, k:
              _enn().Embedding(n, s, key=k, **opts))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Layer constructors — no key needed
# ═══════════════════════════════════════════════════════════════════════════

layer_norm = _pred("layer_norm",
    (2, _pure(lambda shape: _enn().LayerNorm(shape))),
    (3, _pure(lambda shape, opts: _enn().LayerNorm(shape, **opts))),
)

group_norm = _pred("group_norm",
    (2, _pure(lambda groups: _enn().GroupNorm(groups))),
    (3, _pure(lambda groups, opts: _enn().GroupNorm(groups, **opts))),
)

rms_norm = _pred("rms_norm",
    (2, _pure(lambda shape: _enn().RMSNorm(shape))),
    (3, _pure(lambda shape, opts: _enn().RMSNorm(shape, **opts))),
)

# Dropout: defaults to inference=True. Training-mode dropout (with
# per-call PRNG key) is Phase 17b — see the plan for details.
dropout = _pred("dropout",
    (2, _pure(lambda p: _enn().Dropout(p, inference=True))),
    (3, _pure(lambda p, opts:
              _enn().Dropout(p, **{"inference": True, **opts}))),
)

identity = _pred("identity",
    (1, _pure(lambda: _enn().Identity())),
    (2, _pure(lambda opts: _enn().Identity(**opts))),
)

# Lambda renamed to lambda_layer — `lambda` is reserved in Python /
# Clausal both.
lambda_layer = _pred("lambda_layer",
    (2, _pure(lambda fn: _enn().Lambda(fn))),
)

sequential = _pred("sequential",
    (2, _pure(lambda layers: _enn().Sequential(layers))),
)

prelu = _pred("prelu",
    (1, _pure(lambda: _enn().PReLU())),
    (2, _pure(lambda init_alpha: _enn().PReLU(init_alpha))),
)

rotary_positional_embedding = _pred("rotary_positional_embedding",
    (2, _pure(lambda s: _enn().RotaryPositionalEmbedding(s))),
    (3, _pure(lambda s, opts:
              _enn().RotaryPositionalEmbedding(s, **opts))),
)

weight_norm = _pred("weight_norm",
    (2, _pure(lambda layer: _enn().WeightNorm(layer))),
    (3, _pure(lambda layer, opts: _enn().WeightNorm(layer, **opts))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Pooling
# ═══════════════════════════════════════════════════════════════════════════

max_pool1d = _pred("max_pool1d",
    (2, _pure(lambda ks: _enn().MaxPool1d(ks))),
    (3, _pure(lambda ks, opts: _enn().MaxPool1d(ks, **opts))),
)

max_pool2d = _pred("max_pool2d",
    (2, _pure(lambda ks: _enn().MaxPool2d(ks))),
    (3, _pure(lambda ks, opts: _enn().MaxPool2d(ks, **opts))),
)

max_pool3d = _pred("max_pool3d",
    (2, _pure(lambda ks: _enn().MaxPool3d(ks))),
    (3, _pure(lambda ks, opts: _enn().MaxPool3d(ks, **opts))),
)

avg_pool1d = _pred("avg_pool1d",
    (2, _pure(lambda ks: _enn().AvgPool1d(ks))),
    (3, _pure(lambda ks, opts: _enn().AvgPool1d(ks, **opts))),
)

avg_pool2d = _pred("avg_pool2d",
    (2, _pure(lambda ks: _enn().AvgPool2d(ks))),
    (3, _pure(lambda ks, opts: _enn().AvgPool2d(ks, **opts))),
)

avg_pool3d = _pred("avg_pool3d",
    (2, _pure(lambda ks: _enn().AvgPool3d(ks))),
    (3, _pure(lambda ks, opts: _enn().AvgPool3d(ks, **opts))),
)

adaptive_max_pool1d = _pred("adaptive_max_pool1d",
    (2, _pure(lambda t: _enn().AdaptiveMaxPool1d(t))),
)

adaptive_max_pool2d = _pred("adaptive_max_pool2d",
    (2, _pure(lambda t: _enn().AdaptiveMaxPool2d(t))),
)

adaptive_max_pool3d = _pred("adaptive_max_pool3d",
    (2, _pure(lambda t: _enn().AdaptiveMaxPool3d(t))),
)

adaptive_avg_pool1d = _pred("adaptive_avg_pool1d",
    (2, _pure(lambda t: _enn().AdaptiveAvgPool1d(t))),
)

adaptive_avg_pool2d = _pred("adaptive_avg_pool2d",
    (2, _pure(lambda t: _enn().AdaptiveAvgPool2d(t))),
)

adaptive_avg_pool3d = _pred("adaptive_avg_pool3d",
    (2, _pure(lambda t: _enn().AdaptiveAvgPool3d(t))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Module application
# ═══════════════════════════════════════════════════════════════════════════

apply_module = _pred("apply_module",
    (3, _pure(lambda m, x: m(x))),
    (4, _pure(lambda m, x, kwargs: m(x, **kwargs))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Filter transforms (Phase 12 analogues, filter-aware)
# ═══════════════════════════════════════════════════════════════════════════

filter_grad_value = _pred("filter_grad_value",
    (3, _pure(lambda f, x: _eqx().filter_grad(f)(x))),
)

filter_value_and_grad = _pred("filter_value_and_grad",
    (3, _pure(lambda f, x: tuple(_eqx().filter_value_and_grad(f)(x)))),
)

filter_jit_compile = _pred("filter_jit_compile",
    (2, _pure(lambda f: _eqx().filter_jit(f))),
)

filter_vmap_apply = _pred("filter_vmap_apply",
    (3, _pure(lambda f, x: _eqx().filter_vmap(f)(x))),
    (4, _pure(lambda f, x, opts: _eqx().filter_vmap(f, **opts)(x))),
)

filter_pmap_apply = _pred("filter_pmap_apply",
    (3, _pure(lambda f, x: _eqx().filter_pmap(f)(x))),
    (4, _pure(lambda f, x, opts: _eqx().filter_pmap(f, **opts)(x))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Partition / combine
# ═══════════════════════════════════════════════════════════════════════════
#
# eqx.partition(tree, filter_spec) returns a 2-tuple (diff, static).
# We expose it as 4-arity with two output slots so users don't have
# to decompose a tuple — the partition step is in the hot path of
# every filter_grad call and the slight non-uniformity is justified.

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _deep_deref


def _partition_4_dispatch(this_generator, _proceed, _fail, _catcher,
                          tree_var, filter_var, diff_var, static_var, trail):
    tree = _deep_deref(tree_var)
    flt = _deep_deref(filter_var)
    try:
        diff, static = _eqx().partition(tree, flt)
    except Exception:
        yield (_fail, DONE)
        return
    if unify(diff_var, diff, trail) and unify(static_var, static, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


partition = _pred("partition",
    (4, _partition_4_dispatch),
)

combine = _pred("combine",
    (3, _pure(lambda diff, static: _eqx().combine(diff, static))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Functional updates by callable path
# ═══════════════════════════════════════════════════════════════════════════

tree_at_set = _pred("tree_at_set",
    (4, _pure(lambda where, tree, replace:
              _eqx().tree_at(where, tree, replace=replace))),
)

tree_at_apply = _pred("tree_at_apply",
    (4, _pure(lambda where, tree, fn:
              _eqx().tree_at(where, tree, replace_fn=fn))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Leaf checks
# ═══════════════════════════════════════════════════════════════════════════

is_array = _pred("is_array",
    (1, _check_1(lambda x: bool(_eqx().is_array(x)))),
)

is_inexact_array = _pred("is_inexact_array",
    (1, _check_1(lambda x: bool(_eqx().is_inexact_array(x)))),
)

is_array_like = _pred("is_array_like",
    (1, _check_1(lambda x: bool(_eqx().is_array_like(x)))),
)

tree_equal = _pred("tree_equal",
    (2, _check_2(lambda a, b: bool(_eqx().tree_equal(a, b)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Serialisation (Tier 4 — IO)
# ═══════════════════════════════════════════════════════════════════════════
#
# These touch the filesystem; not backtracking-safe — re-running
# serialise/2 on redo will overwrite the file silently. Commit
# serialisation at end-of-loop, not inside a search.


def _serialise_2_dispatch(this_generator, _proceed, _fail, _catcher,
                          tree_var, path_var, trail):
    tree = _deep_deref(tree_var)
    path = _deep_deref(path_var)
    try:
        _eqx().tree_serialise_leaves(path, tree)
    except Exception:
        yield (_fail, DONE)
        return
    yield (_proceed, None)
    yield (_fail, DONE)


serialise = _pred("serialise",
    (2, _serialise_2_dispatch),
)

deserialise = _pred("deserialise",
    (3, _pure(lambda path, like:
              _eqx().tree_deserialise_leaves(path, like))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Layer-class registry (discovery side-channel)
# ═══════════════════════════════════════════════════════════════════════════
#
# Returns the actual eqx.nn class by TitleCase name. Construction goes
# through the per-class predicates above; this registry is for users
# who want to introspect what layer types Equinox supports without
# grepping the docs.

def _build_layer_class_facts():
    _ensure_equinox()
    import equinox as eqx
    import equinox.nn as enn
    import inspect
    out = []
    for n in dir(enn):
        if n.startswith("_"):
            continue
        cls = getattr(enn, n)
        if inspect.isclass(cls) and issubclass(cls, eqx.Module):
            out.append((n, cls))
    return out


layer_class = _pred("layer_class",
    (2, _fact_table_2(_build_layer_class_facts)),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Layer constructors — key-required
    "linear", "mlp",
    "conv", "conv1d", "conv2d", "conv3d",
    "conv_transpose", "conv_transpose1d", "conv_transpose2d",
    "conv_transpose3d",
    "gru_cell", "lstm_cell",
    "multihead_attention", "spectral_norm", "embedding",
    # Layer constructors — no key
    "layer_norm", "group_norm", "rms_norm",
    "dropout", "identity", "lambda_layer", "sequential",
    "prelu", "rotary_positional_embedding", "weight_norm",
    # Pooling
    "max_pool1d", "max_pool2d", "max_pool3d",
    "avg_pool1d", "avg_pool2d", "avg_pool3d",
    "adaptive_max_pool1d", "adaptive_max_pool2d", "adaptive_max_pool3d",
    "adaptive_avg_pool1d", "adaptive_avg_pool2d", "adaptive_avg_pool3d",
    # Apply
    "apply_module",
    # Filter transforms
    "filter_grad_value", "filter_value_and_grad",
    "filter_jit_compile", "filter_vmap_apply", "filter_pmap_apply",
    # Partition / combine
    "partition", "combine",
    # Functional updates
    "tree_at_set", "tree_at_apply",
    # Leaf checks
    "is_array", "is_inexact_array", "is_array_like", "tree_equal",
    # Serialisation
    "serialise", "deserialise",
    # Registry
    "layer_class",
]
