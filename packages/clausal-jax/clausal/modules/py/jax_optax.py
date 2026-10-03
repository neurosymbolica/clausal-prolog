"""clausal.modules.py.jax_optax — Optax gradient transformations and optimisation.

`Optax <https://optax.readthedocs.io>`_ is the de-facto functional
optimiser library for JAX. Its core abstraction is
``GradientTransformation = (init_fn, update_fn)``: pure functions that
take parameters / gradients / state and produce updated state plus
parameter deltas. Because the API is already functional and
state-threaded, every operation maps cleanly onto Clausal's
state-threading idiom — no carve-outs, no impure escapes.

This module completes the "you can train a model end-to-end in
Clausal" story that started with Phase 9 (pytrees), Phase 10
(``jax_nn``) and Phase 12 (function transforms).

Import usage::

    -import_from(py.jax_optax, [
        sgd, adam, adamw,
        chain, clip_by_global_norm, scale_by_schedule,
        cosine_decay_schedule, exponential_decay,
        init_optimizer, update_optimizer, apply_updates,
        softmax_cross_entropy, l2_loss, huber_loss,
        optimizer, schedule, schedule_at,
    ])

Phase 16 — Optax
-----------------

Registries (Tier 2 — fact tables, nondeterministic):
    optimizer(NAME, CTOR)            Optimiser constructor by name
    schedule(NAME, CTOR)             Schedule constructor by name
    loss_function(NAME, FN)          Loss function by name

Optimiser constructors (Tier 1 pure):
    sgd(LR, TX) / sgd(LR, OPTS, TX)
    adam(LR, TX) / adam(LR, OPTS, TX)
    adamw, adagrad, rmsprop, lamb, lion, noisy_sgd,
    optimistic_gradient_descent

Gradient transforms (Tier 1 pure constructors):
    scale(FACTOR, TX)
    scale_by_schedule(SCHED, TX)
    scale_by_adam(TX) / scale_by_adam(OPTS, TX)
    clip(MAX_DELTA, TX)
    clip_by_global_norm(MAX_NORM, TX)
    clip_by_block_rms(THRESHOLD, TX)
    add_decayed_weights(WD, TX) / (WD, MASK, TX)
    ema(DECAY, TX) / (DECAY, OPTS, TX)
    add_noise(ETA, GAMMA, KEY, TX)
    zero_nans(TX)
    keep_params_nonnegative(TX)
    chain(TXS, TX)
    masked(TX, MASK, TX2)
    multi_transform(TXS_BY_LABEL, LABELS, TX)
    multi_steps(TX, EVERY_K, TX2)

Schedules (Tier 1 pure):
    constant_schedule(VALUE, SCHED)
    linear_schedule(INIT, END, STEPS, SCHED)
    exponential_decay(INIT, STEPS, RATE, SCHED) / (..., OPTS, SCHED)
    cosine_decay_schedule(INIT, STEPS, SCHED) / (INIT, STEPS, ALPHA, SCHED)
    warmup_cosine_decay_schedule(INIT, PEAK, WARMUP, DECAY, SCHED)
    piecewise_constant_schedule(INIT, BOUNDARIES_AND_SCALES, SCHED)
    polynomial_schedule(INIT, END, POWER, STEPS, SCHED)
    join_schedules(SCHEDS, BOUNDARIES, SCHED)
    schedule_at(SCHED, STEP, VALUE)

Training loop (Tier 3 — state-threaded):
    init_optimizer(TX, PARAMS, STATE)
    update_optimizer(TX, GRADS, STATE, RESULT)        % RESULT is (UPDATES, NEW_STATE)
    update_optimizer(TX, GRADS, STATE, PARAMS, RESULT)
    apply_updates(PARAMS, UPDATES, NEW_PARAMS)        % canonical home: py.jax_tree

Loss functions (Tier 1 pure):
    softmax_cross_entropy(LOGITS, LABELS, L)
    softmax_cross_entropy_with_integer_labels(LOGITS, LABELS, L)
    sigmoid_binary_cross_entropy(LOGITS, LABELS, L)
    l2_loss(PRED, L) / l2_loss(PRED, TARGET, L)
    huber_loss(PRED, TARGET, L) / (PRED, TARGET, DELTA, L)
    cosine_distance(PRED, TARGET, L)
    cosine_similarity(PRED, TARGET, L)
    kl_divergence(LOG_PRED, TARGETS, L)
    hinge_loss(PRED, TARGET, L)
    smooth_labels(LABELS, ALPHA, SMOOTHED)

Tuple results
--------------
``update_optimizer`` returns a Python tuple ``(updates, new_state)``;
decompose it with Clausal's tuple syntax, the same convention used by
``value_and_grad`` and the linalg decompositions::

    update_optimizer(OPT, GRADS, STATE0, RESULT),
    RESULT is (UPDATES, STATE1)

Opaque values
--------------
``GradientTransformation`` and ``OptState`` are first-class JAX values
that flow through arguments. Predicates do not inspect them; thread
them through your training loop.

PRNG key for ``add_noise``
---------------------------
``optax.add_noise`` requires a ``jax.random`` key. Use Phase 2's
``key/2`` to construct one and ``split_key/3`` to share keys with
other key-consumers.
"""

from __future__ import annotations

import functools as _functools
import threading as _threading

from clausal.modules.py._helpers import _pred as _base_pred, _pure
from clausal.modules.py.jax import _ensure_jax  # noqa: F401 — surfaces JAX dep


# ═══════════════════════════════════════════════════════════════════════════
# Lazy import
# ═══════════════════════════════════════════════════════════════════════════

_optax = None
_optax_lock = _threading.Lock()


def _ensure_optax(context=""):
    """Import optax once.  When it is not installed, raise the ISO
    ``existence_error(module, optax)`` -- never a silent failure.  An
    optax that is installed but fails to import (one of ITS dependencies is
    missing) is not reported as absent: that error propagates as it is."""
    global _optax
    if _optax is not None:
        return
    with _optax_lock:
        if _optax is not None:
            return
        from clausal.modules.py import _import_stdlib
        try:
            _optax = _import_stdlib("optax")
        except ModuleNotFoundError as exc:
            if exc.name != "optax":
                raise
            from clausal.logic.exceptions import (  # noqa: PLC0415
                LogicException, existence_error)
            raise LogicException(existence_error(
                "module", "optax",
                f"{context}: optax is not installed" if context
                else "optax is not installed")) from None


def _ox():
    _ensure_optax()
    return _optax


def _needs_optax(name, arity, dispatch):
    """*dispatch* behind an optax presence check made OUTSIDE it: the
    ``_pure`` wrapper turns any exception in its function into failure, so
    the check cannot live there."""
    context = f"{name}/{arity}"

    @_functools.wraps(dispatch)
    def run(this_generator, _proceed, _fail, _catcher, *args):
        _ensure_optax(context)
        yield from dispatch(this_generator, _proceed, _fail, _catcher, *args)
    return run


def _pred(name, *arity_fns):
    """``_pred`` for an optax-backed predicate: every arity checks that
    optax is importable before it runs.  Register every predicate of this
    module through it (not ``_base_pred``), or a missing optax reads as
    "no solutions" again."""
    return _base_pred(name, *((arity, _needs_optax(name, arity, fn))
                              for arity, fn in arity_fns))


# ═══════════════════════════════════════════════════════════════════════════
# Optimiser constructors
# ═══════════════════════════════════════════════════════════════════════════

sgd = _pred("sgd",
    (2, _pure(lambda lr: _ox().sgd(lr))),
    (3, _pure(lambda lr, opts: _ox().sgd(lr, **opts))),
)

adam = _pred("adam",
    (2, _pure(lambda lr: _ox().adam(lr))),
    (3, _pure(lambda lr, opts: _ox().adam(lr, **opts))),
)

adamw = _pred("adamw",
    (2, _pure(lambda lr: _ox().adamw(lr))),
    (3, _pure(lambda lr, opts: _ox().adamw(lr, **opts))),
)

adagrad = _pred("adagrad",
    (2, _pure(lambda lr: _ox().adagrad(lr))),
    (3, _pure(lambda lr, opts: _ox().adagrad(lr, **opts))),
)

rmsprop = _pred("rmsprop",
    (2, _pure(lambda lr: _ox().rmsprop(lr))),
    (3, _pure(lambda lr, opts: _ox().rmsprop(lr, **opts))),
)

lamb = _pred("lamb",
    (2, _pure(lambda lr: _ox().lamb(lr))),
    (3, _pure(lambda lr, opts: _ox().lamb(lr, **opts))),
)

lion = _pred("lion",
    (2, _pure(lambda lr: _ox().lion(lr))),
    (3, _pure(lambda lr, opts: _ox().lion(lr, **opts))),
)

noisy_sgd = _pred("noisy_sgd",
    (2, _pure(lambda lr: _ox().noisy_sgd(lr))),
    (3, _pure(lambda lr, opts: _ox().noisy_sgd(lr, **opts))),
)

optimistic_gradient_descent = _pred("optimistic_gradient_descent",
    (2, _pure(lambda lr: _ox().optimistic_gradient_descent(lr))),
    (3, _pure(lambda lr, opts: _ox().optimistic_gradient_descent(lr, **opts))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Gradient-transform constructors
# ═══════════════════════════════════════════════════════════════════════════

scale = _pred("scale",
    (2, _pure(lambda factor: _ox().scale(factor))),
)

scale_by_schedule = _pred("scale_by_schedule",
    (2, _pure(lambda sched: _ox().scale_by_schedule(sched))),
)

scale_by_adam = _pred("scale_by_adam",
    (1, _pure(lambda: _ox().scale_by_adam())),
    (2, _pure(lambda opts: _ox().scale_by_adam(**opts))),
)

clip = _pred("clip",
    (2, _pure(lambda max_delta: _ox().clip(max_delta))),
)

clip_by_global_norm = _pred("clip_by_global_norm",
    (2, _pure(lambda max_norm: _ox().clip_by_global_norm(max_norm))),
)

clip_by_block_rms = _pred("clip_by_block_rms",
    (2, _pure(lambda threshold: _ox().clip_by_block_rms(threshold))),
)

add_decayed_weights = _pred("add_decayed_weights",
    (2, _pure(lambda wd: _ox().add_decayed_weights(wd))),
    (3, _pure(lambda wd, mask: _ox().add_decayed_weights(wd, mask))),
)

ema = _pred("ema",
    (2, _pure(lambda decay: _ox().ema(decay))),
    (3, _pure(lambda decay, opts: _ox().ema(decay, **opts))),
)

# Optax's add_noise needs a key; pass it positionally to match.
add_noise = _pred("add_noise",
    (4, _pure(lambda eta, gamma, key: _ox().add_noise(eta, gamma, key))),
)

zero_nans = _pred("zero_nans",
    (1, _pure(lambda: _ox().zero_nans())),
)

keep_params_nonnegative = _pred("keep_params_nonnegative",
    (1, _pure(lambda: _ox().keep_params_nonnegative())),
)

# chain takes *args in optax; Clausal-side pass a list.
chain = _pred("chain",
    (2, _pure(lambda txs: _ox().chain(*txs))),
)

masked = _pred("masked",
    (3, _pure(lambda inner, mask: _ox().masked(inner, mask))),
)

multi_transform = _pred("multi_transform",
    (3, _pure(lambda txs, labels: _ox().multi_transform(txs, labels))),
)

# MultiSteps is a class; its returned value behaves as a GradientTransformation.
multi_steps = _pred("multi_steps",
    (3, _pure(lambda tx, every_k: _ox().MultiSteps(tx, every_k))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Schedules
# ═══════════════════════════════════════════════════════════════════════════

constant_schedule = _pred("constant_schedule",
    (2, _pure(lambda value: _ox().constant_schedule(value))),
)

linear_schedule = _pred("linear_schedule",
    (4, _pure(lambda init, end, steps:
              _ox().linear_schedule(init, end, int(steps)))),
)

# optax order: (init_value, transition_steps, decay_rate, ...)
exponential_decay = _pred("exponential_decay",
    (4, _pure(lambda init, steps, rate:
              _ox().exponential_decay(init, int(steps), rate))),
    (5, _pure(lambda init, steps, rate, opts:
              _ox().exponential_decay(init, int(steps), rate, **opts))),
)

cosine_decay_schedule = _pred("cosine_decay_schedule",
    (3, _pure(lambda init, steps:
              _ox().cosine_decay_schedule(init, int(steps)))),
    (4, _pure(lambda init, steps, alpha:
              _ox().cosine_decay_schedule(init, int(steps), alpha))),
)

warmup_cosine_decay_schedule = _pred("warmup_cosine_decay_schedule",
    (5, _pure(lambda init, peak, warmup, decay:
              _ox().warmup_cosine_decay_schedule(
                  init, peak, int(warmup), int(decay)))),
)

piecewise_constant_schedule = _pred("piecewise_constant_schedule",
    (3, _pure(lambda init, bounds:
              # bounds is dict[int, float]; Clausal-side dict has int keys.
              _ox().piecewise_constant_schedule(init, dict(bounds)))),
)

polynomial_schedule = _pred("polynomial_schedule",
    (5, _pure(lambda init, end, power, steps:
              _ox().polynomial_schedule(init, end, power, int(steps)))),
)

join_schedules = _pred("join_schedules",
    (3, _pure(lambda scheds, boundaries:
              _ox().join_schedules(scheds, [int(b) for b in boundaries]))),
)

schedule_at = _pred("schedule_at",
    (3, _pure(lambda sched, step: sched(int(step)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Training loop
# ═══════════════════════════════════════════════════════════════════════════

init_optimizer = _pred("init_optimizer",
    (3, _pure(lambda tx, params: tx.init(params))),
)

update_optimizer = _pred("update_optimizer",
    (4, _pure(lambda tx, grads, state: tuple(tx.update(grads, state)))),
    (5, _pure(lambda tx, grads, state, params:
              tuple(tx.update(grads, state, params)))),
)

# `apply_updates` is a pure pytree operation, not optimiser-specific —
# canonical implementation lives in py.jax_tree. Re-exported here so
# callers who import from py.jax_optax don't break.
from clausal.modules.py.jax_tree import apply_updates as _apply_updates
apply_updates = _apply_updates


# ═══════════════════════════════════════════════════════════════════════════
# Loss functions
# ═══════════════════════════════════════════════════════════════════════════

softmax_cross_entropy = _pred("softmax_cross_entropy",
    (3, _pure(lambda logits, labels: _ox().softmax_cross_entropy(logits, labels))),
)

softmax_cross_entropy_with_integer_labels = _pred(
    "softmax_cross_entropy_with_integer_labels",
    (3, _pure(lambda logits, labels:
              _ox().softmax_cross_entropy_with_integer_labels(logits, labels))),
)

sigmoid_binary_cross_entropy = _pred("sigmoid_binary_cross_entropy",
    (3, _pure(lambda logits, labels:
              _ox().sigmoid_binary_cross_entropy(logits, labels))),
)

l2_loss = _pred("l2_loss",
    (2, _pure(lambda pred: _ox().l2_loss(pred))),
    (3, _pure(lambda pred, target: _ox().l2_loss(pred, target))),
)

huber_loss = _pred("huber_loss",
    (3, _pure(lambda pred, target: _ox().huber_loss(pred, target))),
    (4, _pure(lambda pred, target, delta:
              _ox().huber_loss(pred, target, delta=delta))),
)

cosine_distance = _pred("cosine_distance",
    (3, _pure(lambda pred, target: _ox().cosine_distance(pred, target))),
)

cosine_similarity = _pred("cosine_similarity",
    (3, _pure(lambda pred, target: _ox().cosine_similarity(pred, target))),
)

kl_divergence = _pred("kl_divergence",
    (3, _pure(lambda log_pred, targets: _ox().kl_divergence(log_pred, targets))),
)

hinge_loss = _pred("hinge_loss",
    (3, _pure(lambda pred, target: _ox().hinge_loss(pred, target))),
)

smooth_labels = _pred("smooth_labels",
    (3, _pure(lambda labels, alpha: _ox().smooth_labels(labels, alpha))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Registries (fact tables)
# ═══════════════════════════════════════════════════════════════════════════

# The wrapper exposes registries of the Python callables that *construct*
# optimisers / schedules / transforms, plus the loss functions themselves.
# Predicates already exist for each; the registries are for relational
# enumeration ("which optimisers exist?") and for `++(CTOR(args))` escape
# hatches when the per-name predicate doesn't fit.

_OPTIMIZER_NAMES = (
    "sgd", "adam", "adamw", "adagrad", "rmsprop",
    "lamb", "lion", "noisy_sgd", "optimistic_gradient_descent",
)

_SCHEDULE_NAMES = (
    "constant_schedule", "linear_schedule", "exponential_decay",
    "cosine_decay_schedule", "warmup_cosine_decay_schedule",
    "piecewise_constant_schedule", "polynomial_schedule",
    "join_schedules",
)

_LOSS_NAMES = (
    "softmax_cross_entropy",
    "softmax_cross_entropy_with_integer_labels",
    "sigmoid_binary_cross_entropy",
    "l2_loss", "huber_loss",
    "cosine_distance", "cosine_similarity",
    "kl_divergence", "hinge_loss",
    "smooth_labels",
)


def _build_named_facts(names):
    def _facts():
        ox = _ox()
        out = []
        for n in names:
            fn = getattr(ox, n, None)
            if fn is not None:
                out.append((n, fn))
        return out
    return _facts


from clausal.modules.py._helpers import _fact_table_2

optimizer = _pred("optimizer",
    (2, _fact_table_2(_build_named_facts(_OPTIMIZER_NAMES))),
)

schedule = _pred("schedule",
    (2, _fact_table_2(_build_named_facts(_SCHEDULE_NAMES))),
)

loss_function = _pred("loss_function",
    (2, _fact_table_2(_build_named_facts(_LOSS_NAMES))),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Optimisers
    "sgd", "adam", "adamw", "adagrad", "rmsprop",
    "lamb", "lion", "noisy_sgd", "optimistic_gradient_descent",
    # Gradient transforms
    "scale", "scale_by_schedule", "scale_by_adam",
    "clip", "clip_by_global_norm", "clip_by_block_rms",
    "add_decayed_weights", "ema", "add_noise",
    "zero_nans", "keep_params_nonnegative",
    "chain", "masked", "multi_transform", "multi_steps",
    # Schedules
    "constant_schedule", "linear_schedule", "exponential_decay",
    "cosine_decay_schedule", "warmup_cosine_decay_schedule",
    "piecewise_constant_schedule", "polynomial_schedule",
    "join_schedules", "schedule_at",
    # Training loop
    "init_optimizer", "update_optimizer", "apply_updates",
    # Losses
    "softmax_cross_entropy",
    "softmax_cross_entropy_with_integer_labels",
    "sigmoid_binary_cross_entropy",
    "l2_loss", "huber_loss",
    "cosine_distance", "cosine_similarity",
    "kl_divergence", "hinge_loss",
    "smooth_labels",
    # Registries
    "optimizer", "schedule", "loss_function",
]
