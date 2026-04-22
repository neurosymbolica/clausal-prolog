# jax_optax — Optimisers, Schedules, Losses (Optax)

[Optax](https://optax.readthedocs.io) is the de-facto functional
optimiser library for JAX. Its core abstraction is a
**`GradientTransformation`** — a pair of pure functions
`(init_fn, update_fn)` that initialise optimiser state from a params
pytree and turn `(grads, state) → (updates, new_state)`.

Because optax is already functional and state-threaded, every
operation maps cleanly onto Clausal's state-threading idiom. This
module completes the "you can train a model end-to-end in Clausal"
story alongside Phase 9 (pytrees), Phase 10 (`jax_nn`), and Phase 12
(function transforms).

All predicates are Tier 1 pure or Tier 3 state-threaded. None require
`++()` escapes for the standard training loop.

## Import

```clausal
-import_module(jax)
-import_from(py.jax_optax, [
    sgd, adam, adamw,
    chain, clip_by_global_norm, scale_by_schedule,
    cosine_decay_schedule, exponential_decay,
    init_optimizer, update_optimizer, apply_updates,
    softmax_cross_entropy, l2_loss, huber_loss,
    optimizer, schedule, schedule_at,
])
-import_from(py.jax_transforms, [value_and_grad])
```

---

## The training-loop trio

Three predicates form the heart of the wrapper.

### `init_optimizer(TX, PARAMS, STATE)`

Build the initial optimiser state from a params pytree. `TX` is a
`GradientTransformation` (anything returned by `sgd/2`, `adam/2`,
`chain/2`, etc.). `STATE` is opaque — thread it through arguments,
do not inspect it.

### `update_optimizer(TX, GRADS, STATE, RESULT)` — and `/5` with PARAMS

The hot path. Returns a tuple `(UPDATES, NEW_STATE)`; decompose with
Clausal's tuple syntax — the same convention used by `value_and_grad`,
`svd`, and the rest of `py.jax*`.

```clausal
update_optimizer(OPT, GRADS, STATE0, RESULT),
RESULT is (UPDATES, STATE1)
```

The `/5` form is required when the chain contains a transform that
needs to reference current parameters (`add_decayed_weights`,
`keep_params_nonnegative`, `multi_transform` with parameter labels).
Otherwise either arity works.

### `apply_updates(PARAMS, UPDATES, NEW_PARAMS)`

Element-wise add updates to params, leaf by leaf — handles arbitrary
pytrees.

> **Canonical home:** `py.jax_tree.apply_updates`. The same predicate
> is re-exported from `py.jax_optax` so existing imports keep
> working, but it is a pure pytree operation (not optimiser-specific).
> Both `optax.apply_updates` and `eqx.apply_updates` are thin wrappers
> around the same `tree_map`. Prefer the `py.jax_tree` import in new
> code.

### Minimal example

```clausal
Test("one SGD step on a flat array") <- (
    sgd(0.1, OPT),
    PARAMS is ++(jax.numpy.array([1.0, 2.0, 3.0])),
    init_optimizer(OPT, PARAMS, STATE0),
    GRADS is ++(jax.numpy.array([1.0, 1.0, 1.0])),
    update_optimizer(OPT, GRADS, STATE0, RESULT),
    RESULT is (UPDATES, _STATE1),
    apply_updates(PARAMS, UPDATES, NEW_PARAMS),
    array([0.9, 1.9, 2.9], EXPECTED),
    allclose(NEW_PARAMS, EXPECTED)
)
```

### With `value_and_grad`

```clausal
Test("one Adam step on x^2") <- (
    F is ++(lambda x: jax.numpy.sum(x ** 2)),
    PARAMS is ++(jax.numpy.array([3.0, 4.0])),
    value_and_grad(F, PARAMS, VG),
    VG is (_VAL, GRADS),
    adam(0.01, OPT),
    init_optimizer(OPT, PARAMS, STATE0),
    update_optimizer(OPT, GRADS, STATE0, RESULT),
    RESULT is (UPDATES, _STATE1),
    apply_updates(PARAMS, UPDATES, NEW)
)
```

---

## Optimisers

Each optimiser predicate has a `/2` form taking just the learning
rate and a `/3` form accepting an opts dict for the rest of the
hyperparameters.

```clausal
sgd(0.1, OPT_SGD)
sgd(0.1, {"momentum": 0.9, "nesterov": ++(True)}, OPT_NESTEROV)

adam(0.001, OPT_ADAM)
adam(0.001, {"b1": 0.9, "b2": 0.999, "eps": 1e-8}, OPT_ADAM_TUNED)

adamw(0.001, {"weight_decay": 0.01}, OPT_ADAMW)
```

The full list (`/2` and `/3` for each):
`sgd`, `adam`, `adamw`, `adagrad`, `rmsprop`, `lamb`, `lion`,
`noisy_sgd`, `optimistic_gradient_descent`.

Look up by name from the `optimizer/2` registry:

```clausal
optimizer("sgd", CTOR),
OPT is ++(CTOR(0.1))
```

---

## Composing transforms with `chain`

Optax's true power is composition. `chain([TX1, TX2, ...], TX)`
threads gradients through each transform in order — the canonical
recipe is "clip first, then optimise":

```clausal
clip_by_global_norm(1.0, CLIP),
adam(0.001, ADAM),
chain([CLIP, ADAM], OPT)
```

Transforms available as Tier 1 constructors (each returns a
`GradientTransformation`):

| Predicate | Effect |
|---|---|
| `scale(FACTOR, TX)` | Multiply updates by scalar |
| `scale_by_schedule(SCHED, TX)` | Multiply by a schedule (see below) |
| `scale_by_adam(TX)` / `(OPTS, TX)` | The Adam scaling rule alone |
| `clip(MAX_DELTA, TX)` | Element-wise clip |
| `clip_by_global_norm(MAX, TX)` | Global-norm clipping |
| `clip_by_block_rms(THRESH, TX)` | Per-block RMS clipping |
| `add_decayed_weights(WD, TX)` / `(WD, MASK, TX)` | Weight-decay term |
| `ema(DECAY, TX)` / `(DECAY, OPTS, TX)` | Exponential moving average |
| `add_noise(ETA, GAMMA, KEY, TX)` | Add Gaussian noise (needs PRNG key) |
| `zero_nans(TX)` | Replace NaN updates with 0 |
| `keep_params_nonnegative(TX)` | Project params back to ≥ 0 |
| `chain(TXS, TX)` | Compose a list of transforms |
| `masked(TX, MASK, TX2)` | Apply TX only to leaves where MASK is true |
| `multi_transform(TXS_BY_LABEL, LABELS, TX)` | Apply different TXs to parameter groups |
| `multi_steps(TX, EVERY_K, TX2)` | Accumulate gradients over K micro-batches |

Enumerate via `gradient_transform/2`.

---

## Schedules

Schedules are pure functions `step → value`. Build one, then either
evaluate it directly with `schedule_at/3` or wire it into an
optimiser with `scale_by_schedule/2`.

```clausal
cosine_decay_schedule(0.001, 1000, SCHED),
schedule_at(SCHED, 0, LR_AT_START),     % ≈ 0.001
schedule_at(SCHED, 500, LR_AT_MID),     % ≈ 0.0005
schedule_at(SCHED, 1000, LR_AT_END)     % ≈ 0.0
```

Wired into an optimiser, the canonical pattern is `chain` with a
unit-LR base and `scale_by_schedule`:

```clausal
cosine_decay_schedule(0.001, 1000, SCHED),
sgd(1.0, BASE),                          % unit LR
scale_by_schedule(SCHED, SCALER),
chain([BASE, SCALER], OPT)
```

The available schedule constructors (all Tier 1 pure):

| Predicate | Description |
|---|---|
| `constant_schedule(VALUE, SCHED)` | Always the same value |
| `linear_schedule(INIT, END, STEPS, SCHED)` | Linear interpolation |
| `exponential_decay(INIT, STEPS, RATE, SCHED)` / `(..., OPTS, SCHED)` | Exponential decay |
| `cosine_decay_schedule(INIT, STEPS, SCHED)` / `(INIT, STEPS, ALPHA, SCHED)` | Cosine decay |
| `warmup_cosine_decay_schedule(INIT, PEAK, WARMUP, DECAY, SCHED)` | Warmup then cosine |
| `piecewise_constant_schedule(INIT, BOUNDS_DICT, SCHED)` | Step-wise |
| `polynomial_schedule(INIT, END, POWER, STEPS, SCHED)` | Polynomial interpolation |
| `join_schedules(SCHEDS, BOUNDARIES, SCHED)` | Concatenate at step boundaries |
| `schedule_at(SCHED, STEP, VALUE)` | Evaluate at a step |

Argument order matches optax's own (`init_value, transition_steps,
decay_rate` for `exponential_decay`, etc.).

---

## Losses

Optax owns the loss surface — `jax.nn` provides activations but no
losses. All loss predicates are Tier 1 pure and operate per-element
(reduce yourself if you want a scalar):

| Predicate | Notes |
|---|---|
| `softmax_cross_entropy(LOGITS, LABELS, L)` | One-hot labels |
| `softmax_cross_entropy_with_integer_labels(LOGITS, LABELS, L)` | Integer class indices |
| `sigmoid_binary_cross_entropy(LOGITS, LABELS, L)` | Per-logit BCE |
| `l2_loss(PRED, L)` / `(PRED, TARGET, L)` | `0.5 * (pred - target)^2` |
| `huber_loss(PRED, TARGET, L)` / `(PRED, TARGET, DELTA, L)` | Robust to outliers |
| `cosine_distance(PRED, TARGET, L)` | `1 - cosine_sim` |
| `cosine_similarity(PRED, TARGET, L)` | |
| `kl_divergence(LOG_PRED, TARGETS, L)` | Note: log-predictions, plain targets |
| `hinge_loss(PRED, TARGET, L)` | Margin-based |
| `smooth_labels(LABELS, ALPHA, SMOOTHED)` | Label smoothing |

Enumerate via `loss_function/2`.

---

## Gradient accumulation

`multi_steps/3` wraps an inner optimiser so it only applies a real
update every K steps; intermediate steps accumulate gradients into
state. Defaults to mean-of-grads (`use_grad_mean=True`).

```clausal
sgd(1.0, INNER),
multi_steps(INNER, 4, OPT)
```

The first three `update_optimizer` calls return zero updates and a
state with the running grad sum; the fourth applies the accumulated
mean.

---

## Caveats

### `GradientTransformation` and `OptState` are opaque

These are first-class JAX values that flow through arguments. The
wrapper does not provide inspection predicates — thread them through
your loop, never pattern-match on them. `_deep_deref` preserves the
NamedTuple subclass so `tx.init` / `tx.update` attribute access
survives a Clausal round-trip.

If you need to log Adam's `mu` / `nu` for debugging, reach for
Phase 9 pytree predicates on the `OptState`:

```clausal
leaf(STATE, LEAF)
```

(Optax states are pytrees with a defined structure per transform.)

### Use `/5` `update_optimizer` when params matter

`add_decayed_weights`, `keep_params_nonnegative`, and
`multi_transform` with parameter labels need access to the current
parameters in `update`. If your chain contains any of these, use the
`/5` arity:

```clausal
update_optimizer(OPT, GRADS, STATE, PARAMS, RESULT)
```

Most optimisers (plain `sgd`, `adam`, `adamw`, `lion`, …) work with
either arity.

### `add_noise` requires a PRNG key

Unlike the other transforms, `add_noise` consumes a `jax.random` key.
Use Phase 2's `key/2` to construct one:

```clausal
key(42, K),
add_noise(0.01, 0.55, K, NOISE)
```

### Float precision on test assertions

Everything is float32 by default. Compare with `allclose/2,/4`, not
`array_list/2`, when checking against literal floats:

```clausal
% This will fail — bit-exact comparison.
array_list(NEW_PARAMS, [0.9, 1.9, 2.9])

% Use this instead.
array([0.9, 1.9, 2.9], EXPECTED),
allclose(NEW_PARAMS, EXPECTED)
```

### `chain` shadows `itertools.chain`

If you `-import_from(py.jax_optax, [chain])` and also call
`itertools.chain` via `++()`, name `it_chain` your itertools alias
or refer to it as `++(itertools.chain(...))`. No other optax name
collides with a Python stdlib symbol.

### Custom Clausal-defined transforms

Out of scope for this phase. The 30+ built-in optax transforms cover
nearly every published optimiser; if you genuinely need a custom
update rule that isn't a `chain` of existing pieces, use `++()` to
construct it directly with `optax.GradientTransformation(init_fn,
update_fn)`.

---

## Registries

For relational queries about what's available:

| Registry | Modes | Yields |
|---|---|---|
| `optimizer(NAME, CTOR)` | `(+,-)`, `(-,-)`, `(+,+)` | Optimiser constructor by name |
| `schedule(NAME, CTOR)` | same | Schedule constructor by name |
| `gradient_transform(NAME, CTOR)` | same | Transform constructor by name |
| `loss_function(NAME, FN)` | same | Loss function by name |

```clausal
findall(N, optimizer(N, _), NAMES)
```

The registries enumerate the curated wrapper-exposed surface, not
every public optax symbol — so the count is stable across optax
versions and reflects what's reachable from `py.jax_optax`.

---

## Comparison to other wrappers

| | jax_optax | torch (training-loop) |
|---|---|---|
| Optimiser construction | `sgd(LR, OPT)` — pure value | `Adam(params, LR, OPT)` — handle |
| State threading | Explicit `STATE` arg | Hidden in optimiser handle |
| Hot-path purity | Pure (no mutation) | `loss.backward()` mutates `.grad` |
| Backtracking-safe | ✅ | ❌ training loop stays as `++()` |

The functional shape is the whole reason the Clausal training story is
clean for JAX where it had to be carved out for PyTorch.
