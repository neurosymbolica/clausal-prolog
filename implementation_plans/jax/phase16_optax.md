# Phase 16 — Optax: Gradient Transformations and Optimisation

[Optax](https://optax.readthedocs.io) is the de-facto functional
optimiser library for JAX. Its core abstraction is
`GradientTransformation = (init_fn, update_fn)`: pure functions that
take parameters / gradients / state and produce updated state plus
parameter deltas. Because the API is already functional and
state-threaded, every operation maps cleanly onto Clausal's
state-threading idiom — no carve-outs, no impure escapes.

This phase completes the "you can train a model end-to-end in
Clausal" story that started with Phase 9 (pytrees), Phase 10
(`jax_nn`) and Phase 12 (function transforms).

**File to create:** `clausal/modules/py/jax_optax.py`

**Depends on:**
- Phase 1 (`clausal/modules/py/jax.py`) — `_ensure_jax`, helpers
- Phase 9 (`jax_tree.py`) — params and updates are pytrees
- Phase 12 (`jax_transforms.py`) — gradients come from `grad_value` /
  `value_and_grad`

**External dependency:** `optax` (lazy-imported via the same
`_ensure_*` pattern as `_ensure_jax`).

---

## Core Concepts

| Optax concept | Clausal predicate | Notes |
|---|---|---|
| `GradientTransformation` | Plain JAX value, opaque | Constructed by `sgd/N`, `adam/N`, …; passed to `init_optimizer` / `update_optimizer` |
| `OptState` | Plain JAX value, opaque | Threaded through the training loop |
| `Schedule` | `Callable[[int], float]` | Constructed by `constant_schedule/1` etc.; evaluated by `schedule_at/3` |
| `Params` | Pytree of arrays | Same as Phase 9 |
| `Updates` | Pytree of arrays matching `Params` | Same as Phase 9 |

`GradientTransformation` and `OptState` stay opaque (no inspection
predicates). Like JAX's `Mesh` or `PRNGKey`, they're first-class values
that flow through arguments — wrapper exposes constructors and
consumers, not introspection.

---

## Predicates

### Optimiser registry (Tier 2 — fact table)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `optimizer` | `/2` | `(+N, -CTOR)`, `(-N, -CTOR)` | Enumerate / look up an optimiser constructor by name |

`optimizer("adam", CTOR)` unifies `CTOR` with the Python callable
`optax.adam`, suitable for `++(CTOR(0.001))` if a user wants to
sidestep the per-optimiser predicates.

### Optimiser constructors (Tier 1 — pure)

Each returns a `GradientTransformation`. Standard optax surface:

| Name | Arity | Modes | Description |
|---|---|---|---|
| `sgd` | `/2, /3` | `(+LR, -TX)`, `(+LR, +OPTS, -TX)` | `optax.sgd` — OPTS for momentum, nesterov |
| `adam` | `/2, /3` | | `optax.adam` |
| `adamw` | `/2, /3` | | Adam with decoupled weight decay |
| `adagrad` | `/2, /3` | | |
| `rmsprop` | `/2, /3` | | |
| `lamb` | `/2, /3` | | |
| `lion` | `/2, /3` | | |
| `noisy_sgd` | `/2, /3` | | |
| `optimistic_gradient_descent` | `/2, /3` | | |

Uniform shape: `LR` first (positional, the most common knob);
hyperparameter dict in the `/3` arity. Mirrors the `zeros/2,/3` pattern
already in `py.jax`.

### Gradient-transform constructors (Tier 1 — pure)

These are the building blocks that `chain` composes:

| Name | Arity | Modes | Description |
|---|---|---|---|
| `scale` | `/2` | `(+FACTOR, -TX)` | Multiply updates by scalar |
| `scale_by_schedule` | `/2` | `(+SCHED, -TX)` | Scale by a schedule (use to wire schedules into optimisers) |
| `scale_by_adam` | `/1, /2` | | The Adam scaling rule on its own |
| `clip` | `/2` | `(+MAX_DELTA, -TX)` | Clip updates element-wise |
| `clip_by_global_norm` | `/2` | `(+MAX_NORM, -TX)` | Global-norm clipping |
| `clip_by_block_rms` | `/2` | | Per-block RMS clipping |
| `add_decayed_weights` | `/2, /3` | `(+WD, -TX)`, `(+WD, +MASK, -TX)` | Weight-decay term |
| `ema` | `/2, /3` | `(+DECAY, -TX)` | Exponential moving average |
| `add_noise` | `/4` | `(+ETA, +GAMMA, +KEY, -TX)` | Add Gaussian noise to updates (key required by optax) |
| `zero_nans` | `/1` | `(-TX)` | Replace NaN updates with 0 |
| `keep_params_nonnegative` | `/1` | `(-TX)` | Project params back to ≥ 0 |
| `chain` | `/2` | `(+TXS, -TX)` | Compose a list of transforms |
| `masked` | `/3` | `(+TX, +MASK, -TX2)` | Apply TX only to leaves where MASK is true |
| `multi_transform` | `/3` | `(+TXS_BY_LABEL, +LABELS, -TX)` | Apply different TXs to different parameter groups |
| `multi_steps` | `/3` | `(+TX, +EVERY_K, -TX2)` | Accumulate gradients over K micro-batches |

`chain([clip_by_global_norm(1.0), adam(0.001)], TX)` is the
canonical wiring idiom; the Clausal equivalent is built up positionally
with the predicates above.

### Schedules (Tier 1 — pure constructors + Tier 2 registry)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `schedule` | `/2` | `(+N, -CTOR)`, `(-N, -CTOR)` | Schedule registry |
| `constant_schedule` | `/2` | `(+VALUE, -SCHED)` | Always the same value |
| `linear_schedule` | `/4` | `(+INIT, +END, +STEPS, -SCHED)` | Linear interpolation |
| `exponential_decay` | `/4, /5` | `(+INIT, +STEPS, +RATE, -SCHED)`; `/5` adds `+OPTS` | Exponential decay (optax order: init, transition_steps, decay_rate) |
| `cosine_decay_schedule` | `/3, /4` | `(+INIT, +STEPS, +ALPHA, -SCHED)` | Cosine decay |
| `warmup_cosine_decay_schedule` | `/5` | `(+INIT, +PEAK, +WARMUP_STEPS, +DECAY_STEPS, -SCHED)` | Common LR shape |
| `piecewise_constant_schedule` | `/3` | `(+INIT, +BOUNDARIES_AND_SCALES, -SCHED)` | Step-wise |
| `polynomial_schedule` | `/5` | `(+INIT, +END, +POWER, +STEPS, -SCHED)` | |
| `join_schedules` | `/3` | `(+SCHEDS, +BOUNDARIES, -SCHED)` | Concatenate schedules at step boundaries |
| `schedule_at` | `/3` | `(+SCHED, +STEP, -VALUE)` | Evaluate a schedule at a given step |

`schedule_at` is the only predicate that *consumes* a schedule
without wrapping it in a transform. Use it for logging or assertions.

### Training-loop predicates (Tier 3 — state-threaded)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `init_optimizer` | `/3` | `(+TX, +PARAMS, -STATE)` | `tx.init(params)` — build initial state |
| `update_optimizer` | `/4` | `(+TX, +GRADS, +STATE, -RESULT)` | `tx.update(grads, state)` — `RESULT is (UPDATES, NEW_STATE)` |
| `update_optimizer` | `/5` | `(+TX, +GRADS, +STATE, +PARAMS, -RESULT)` | `tx.update(grads, state, params)` — for transforms that need params (e.g. `add_decayed_weights`) |
| `apply_updates` | `/3` | `(+PARAMS, +UPDATES, -NEW_PARAMS)` | Pure pytree op; canonical home `py.jax_tree.apply_updates`, re-exported here for ergonomics |

The two arities of `update_optimizer` reflect optax's own signature.
Most transforms accept both shapes; the `/5` form is required for
weight-decay-style transforms that need to reference `params`. Both
arities return a single 2-tuple — decompose with
`RESULT is (UPDATES, NEW_STATE)`, matching `value_and_grad`, `svd`,
`qr` and the rest of the multi-output convention used throughout
`py.jax*`.

### Loss functions (Tier 1 — pure)

JAX's `jax.nn` provides activations but not losses; optax owns this
surface. No overlap with Phase 10.

| Name | Arity | Modes | Description |
|---|---|---|---|
| `softmax_cross_entropy` | `/3` | `(+LOGITS, +LABELS, -L)` | Soft-target cross-entropy |
| `softmax_cross_entropy_with_integer_labels` | `/3` | | Hard-label variant |
| `sigmoid_binary_cross_entropy` | `/3` | | |
| `l2_loss` | `/2, /3` | `(+PRED, -L)`, `(+PRED, +TARGET, -L)` | Squared error |
| `huber_loss` | `/3, /4` | `(+PRED, +TARGET, -L)`, `(+PRED, +TARGET, +DELTA, -L)` | |
| `cosine_distance` | `/3` | `(+A, +B, -L)` | |
| `cosine_similarity` | `/3` | | |
| `kl_divergence` | `/3` | `(+LOG_PRED, +TARGETS, -L)` | optax takes log-predictions and plain targets, not two log-probs |
| `hinge_loss` | `/3` | | |
| `smooth_labels` | `/3` | `(+LABELS, +ALPHA, -SMOOTHED)` | Label smoothing |

### Inspection (Tier 2)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `loss_function` | `/2` | `(+N, -FN)`, `(-N, -FN)` | Enumerate losses |

---

## Context and Reference Patterns

### Lazy import

Mirrors `_ensure_jax`:

```python
_optax = None
_optax_lock = _threading.Lock()


def _ensure_optax():
    global _optax
    if _optax is not None:
        return
    with _optax_lock:
        if _optax is not None:
            return
        from clausal.modules.py import _import_stdlib
        _optax = _import_stdlib("optax")


def _ox():
    _ensure_optax()
    return _optax
```

### Optimiser constructors

```python
sgd = _pred("sgd",
    (2, _pure(lambda lr: _ox().sgd(lr))),
    (3, _pure(lambda lr, opts: _ox().sgd(lr, **opts))),
)

adam = _pred("adam",
    (2, _pure(lambda lr: _ox().adam(lr))),
    (3, _pure(lambda lr, opts: _ox().adam(lr, **opts))),
)
```

### Training-loop predicates

`update_optimizer` is the heart of the wrapper. Two arities map to
optax's two call shapes:

```python
def _update_5(tx, grads, state):
    updates, new_state = tx.update(grads, state)
    return updates, new_state


def _update_6(tx, grads, state, params):
    updates, new_state = tx.update(grads, state, params)
    return updates, new_state


update_optimizer = _pred("update_optimizer",
    (5, _pure_two_outputs(_update_5)),
    (6, _pure_two_outputs(_update_6)),
)
```

(`_pure_two_outputs` already exists per Phase 12 issue 1; if not, use
`_pure(lambda *args: tuple(_update_N(*args)))` and require callers to
decompose with `RESULT is (UPDATES, NEW_STATE)`. Decision below.)

### `chain` accepts a list

```python
chain = _pred("chain",
    (2, _pure(lambda txs: _ox().chain(*txs))),
)
```

Clausal-side `[CLIP, ADAM]` becomes `optax.chain(CLIP, ADAM)`.

### Schedule application via `scale_by_schedule`

The optax idiom for plumbing a schedule into an optimiser:

```clausal
cosine_decay_schedule(0.001, 10000, 0.0, SCHED),
sgd(1.0, OPT_RAW),                        # base optimiser at unit LR
scale_by_schedule(SCHED, SCALER),
chain([OPT_RAW, SCALER], OPTIMIZER)
```

The alternative — `optax.inject_hyperparams(adam)(learning_rate=sched)`
— is deferred (issue 6).

### Loss functions

Pure pass-through:

```python
softmax_cross_entropy = _pred("softmax_cross_entropy",
    (3, _pure(lambda logits, labels: _ox().softmax_cross_entropy(logits, labels))),
)
```

---

## Example Usage

```clausal
-import_from(py.jax, [array, array_list, allclose, sum])
-import_from(py.jax_random, [key, split_key, normal])
-import_from(py.jax_transforms, [value_and_grad])
-import_from(py.jax_optax, [
    sgd, adam, chain, clip_by_global_norm,
    cosine_decay_schedule, scale_by_schedule,
    init_optimizer, update_optimizer, apply_updates,
    softmax_cross_entropy, l2_loss,
    optimizer, schedule_at
])
-import_module(jax)

Test("simple SGD step on a single param") <- (
    sgd(0.1, OPT),
    PARAMS is ++(jax.numpy.array([1.0, 2.0, 3.0])),
    init_optimizer(OPT, PARAMS, STATE0),
    GRADS is ++(jax.numpy.array([1.0, 1.0, 1.0])),
    update_optimizer(OPT, GRADS, STATE0, UPDATES, _),
    apply_updates(PARAMS, UPDATES, NEW_PARAMS),
    array_list(NEW_PARAMS, [0.9, 1.9, 2.9])
)

Test("adam with grad of x^2") <- (
    F is ++(lambda x: jax.numpy.sum(x ** 2)),
    PARAMS is ++(jax.numpy.array([3.0, 4.0])),
    value_and_grad(F, PARAMS, RESULT),
    RESULT is (_, GRADS),
    adam(0.01, OPT),
    init_optimizer(OPT, PARAMS, STATE0),
    update_optimizer(OPT, GRADS, STATE0, UPDATES, STATE1),
    apply_updates(PARAMS, UPDATES, NEW_PARAMS),
    # Adam's first step magnitude is ~LR per param, regardless of grad scale
    shape(NEW_PARAMS, [2])
)

Test("chain: clip then adam") <- (
    clip_by_global_norm(1.0, CLIP),
    adam(0.001, ADAM),
    chain([CLIP, ADAM], OPT),
    PARAMS is ++(jax.numpy.zeros(10)),
    init_optimizer(OPT, PARAMS, _STATE)
)

Test("cosine schedule wired with scale_by_schedule") <- (
    cosine_decay_schedule(0.001, 1000, 0.0, SCHED),
    schedule_at(SCHED, 0, LR0),
    schedule_at(SCHED, 500, LR_MID),
    schedule_at(SCHED, 1000, LR_END),
    LR0 > 0.0009,
    LR_MID > 0.0,
    LR_END < 0.0001,
    sgd(1.0, BASE),
    scale_by_schedule(SCHED, SCALER),
    chain([BASE, SCALER], OPT)
)

Test("softmax cross-entropy on one-hot label") <- (
    LOGITS is ++(jax.numpy.array([2.0, 1.0, 0.1])),
    LABELS is ++(jax.numpy.array([1.0, 0.0, 0.0])),
    softmax_cross_entropy(LOGITS, LABELS, L),
    array_list(L, V),
    V > 0.4, V < 0.5
)

Test("enumerate available optimisers") <- (
    findall(N, optimizer(N, _), NS),
    member("sgd", NS),
    member("adam", NS),
    member("adamw", NS)
)
```

---

## Tests

`tests/fixtures/jax_optax_tests.clausal`:

- One-step SGD on a fixed-grad scalar — assert exact arithmetic
- One-step Adam — assert update magnitude is ~LR per param
- `chain([clip_by_global_norm(1.0), adam(0.001)])` — verify the chain
  builds and a step runs without error
- Schedule round-trip: build → `schedule_at` → check expected values
  at endpoints / midpoint
- `scale_by_schedule` integrated with `sgd(1.0, _)` matches manual
  schedule × identity
- Loss functions: spot-check `softmax_cross_entropy`,
  `l2_loss`, `huber_loss` at known values
- Pytree params: `init_optimizer` and `update_optimizer` work with
  a `{"w": …, "b": …}` pytree — assert `NEW_PARAMS` keys match
- Registry enumeration: `optimizer/2`, `schedule/2`,
  `loss_function/2` — `length(NS, K)` matches the wrapper's curated
  list. (`gradient_transform/2` was removed as a follow-up — see
  `todo/jax_registries_discussion.md` (now
  `implementation_plans/jax/todo/jax_registries_discussion.md`);
  gradient transforms compose
  positionally with `chain`, no name-as-data use case.)
- `multi_steps`: gradient accumulation over 4 micro-batches equals one
  big-batch step

Python unit tests (in `tests/test_jax_infra.py` or a sibling):
- Module imports cleanly even when `optax` is absent (lazy)
- `_ensure_optax` is thread-safe (mirror the `_ensure_jax` test)

---

## Docs

Create `docs/jax_optax.md`:

- Position relative to `jax_transforms` (you compute grads with
  `value_and_grad`; you consume them with `update_optimizer`)
- The `init` / `update` / `apply_updates` triplet — annotated minimal
  loop
- Schedules: when to use `schedule_at` vs. `scale_by_schedule`
- `chain` recipes — clip-then-Adam, weight-decay, EMA-of-params
- `multi_steps` for gradient accumulation
- Loss-function catalogue with input shape conventions
- Caveats from the Issues section (esp. opaque `OptState`, label shape
  conventions, `multi_transform` labelling)

Update `docs/jax.md` "Submodules" section to add `jax_optax`.

Update `implementation_plans/jax/overview.md`:

- Add Phase 16 row to the phases list
- Move "Optax integration" from "Deferred" to a new "✅ Implemented"
  row
- Update the Tier classification table to mention optax under Tier 1
  (pure transforms, schedules, losses) and Tier 3 (training-loop
  state)

---

## Issues

1. **Tuple decomposition for `update_optimizer`.** Optax's `update`
   returns `(updates, new_state)`. Two options: `_pure_two_outputs`
   (predicate has two output args, `/5` and `/6` arities as listed
   above), or single output as a 2-tuple decomposed with `is (U, S)`.
   **Recommendation:** two outputs, matching the way Phase 4
   `solve(A, B, X)` handled multi-output. The `is (V, G)` style from
   Phase 12 was chosen for *symmetry with linalg decompositions* — but
   `update` is in the hot path of every training step, and the
   ergonomics matter more here than there.

2. **Opaque `OptState`.** `OptState` is a recursive named-tuple whose
   shape depends on the transform. Predicates do not inspect it; users
   thread it through arguments and never look inside. Documented in
   `docs/jax_optax.md` "State is opaque". If a real use case for
   inspection appears (e.g. logging Adam's `mu` / `nu` for debugging),
   add `optimizer_state_tree(STATE, TREE)` later — pytree predicates
   from Phase 9 already handle it once the user has the tree.

3. **`add_decayed_weights` and `update_optimizer/5` vs `/6`.**
   Some transforms require `params` in `update`; others ignore it.
   Optax tolerates extra `params=None` for transforms that don't need
   it. Both arities exist; users pick based on what's in their chain.
   Docs note: "if your chain contains `add_decayed_weights` or any
   parameter-dependent transform, use `/6`."

4. **`chain` accepts a list, not varargs.** Clausal-side
   `chain([T1, T2, T3], TX)` becomes `optax.chain(*lst)` inside the
   wrapper. Trivial; flagged because it differs from optax's own
   call shape.

5. **`multi_transform` labelling.** `optax.multi_transform({label:
   tx}, label_pytree)` requires the labels to be a pytree mirroring
   the params with leaves drawn from the dict's keys. Building these
   is fiddly. First pass: expose `multi_transform/3` as-is, document
   the labelling shape, and let users build the label pytree with
   Phase 9 predicates plus `++()`. Convenience constructors
   (`label_by_path`, `label_by_predicate`) deferred.

6. **`inject_hyperparams` skipped.** Optax provides
   `inject_hyperparams(adam)(learning_rate=schedule)` so a schedule
   becomes a *hyperparameter* on the optimiser rather than a separate
   `scale_by_schedule` step. More ergonomic in some cases, but the
   `chain([base, scale_by_schedule(s)])` form is equivalent and
   already covered. Add later only if a caller hits the difference
   (e.g. needs to inspect the schedule from the OptState).

7. **Loss-function input conventions.**
   `softmax_cross_entropy` takes one-hot labels;
   `softmax_cross_entropy_with_integer_labels` takes integer
   class indices. Shapes for both must batch-broadcast. Common pitfall
   — documented prominently. Tests cover both shapes.

8. **GradientTransformation cannot be deep-derefed.** A
   `GradientTransformation` is a NamedTuple of two Python functions.
   `_deep_deref` would walk into the closures and try to re-Clausal
   them. Use `_pure` everywhere (which holds the value opaquely);
   never expose a predicate that takes a `GradientTransformation`
   inside a Clausal term that gets pattern-matched.

9. **No Clausal-side update functions for first pass.** A Clausal user
   *could* in principle write a custom update rule as a
   `predicate(grads, state, params, updates, new_state)` and have
   the wrapper register it as a `GradientTransformation`. This needs
   the same Clausal-callable-as-Python-callable bridge that Phase 12's
   `grad_value` already uses — but for *both* `init_fn` and
   `update_fn`, with state-shape contracts. **Out of scope for first
   pass.** Document; revisit if a user asks. The 30+ built-in
   transforms already cover almost every published optimiser.

10. **Optax version pinning.** Optax has had API churn historically
    (`optax.adam` signature changed circa 0.1.x, `multi_transform`
    semantics tightened in 0.2.x). Pin a tested floor in
    `pyproject.toml` (or whatever the project uses for optional deps —
    JAX itself is currently un-pinned, so optax probably follows the
    same convention). Lock in the floor at the version used to
    develop the phase and bump deliberately.

11. **Quantity awareness.**
    - `apply_updates`: algebraic — params and updates share dims
    - `init_optimizer`, `update_optimizer`: PASS_THROUGH on params /
      grads; OptState carries no units
    - Loss functions: STRIP_TO_PLAIN — losses are scalars
    - Schedules: REQUIRE_DIMENSIONLESS on the step input; output is
      dimensionless (it's a multiplier on a learning rate)
    - Optimiser / transform constructors: none — they create values

12. **Module name shadowing.** `chain` is the only optax name that
    collides with a Python stdlib symbol (`itertools.chain`). At the
    Clausal module level this only matters for users who
    `-import_from(py.jax_optax, [chain])` and also use `++(chain(…))`
    expecting `itertools`. Documented in the "Gotcha — predicates
    that shadow stdlib names" section of `docs/jax.md`. No other
    clashes (`scale`, `clip`, `mask`, `ema`, `sgd`, `adam` are all
    unique to optax in stdlib).

---

## Out of Scope

- **Custom Clausal-defined `GradientTransformation`s** (issue 9)
- **`inject_hyperparams`** (issue 6)
- **Lookahead / SAM / gradient-surgery transforms** —
  `optax.lookahead`, `optax.contrib.*`. Stable surface only for first
  pass.
- **`optax.tree_utils`** — pytree helpers that overlap with Phase 9.
  Re-export only if a real gap appears.
- **Distributed / pjit integration** — `optax.MultiSteps` works under
  `jit` but distributed training is out of scope until a Phase 17
  pjit/Flax cluster lands.

---

## Estimated Surface

| Category | Predicate count |
|---|---|
| Optimiser constructors | ~9 (×2 arities ≈ 18 entries) |
| Gradient-transform constructors | ~14 |
| Schedule constructors + `schedule_at` | ~9 |
| Training loop (`init`, `update`, `apply_updates`) | 3 (with `update` ×2 arities) |
| Loss functions | ~10 |
| Registries | 3 (`optimizer`, `schedule`, `loss_function`) |
| **Total predicate names** | ~50 |
| **Total registered arities** | ~70 |

Comparable in scope to Phase 11 (scipy, ~22 special functions + 9
distribution methods + 1 registry) and Phase 13 (sharding, ~15
predicates).
