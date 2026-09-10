# jax_flax — Flax Linen Models, Init, Apply

[Flax](https://flax.readthedocs.io)'s **Linen** API is the second
major NN library for JAX. Where Equinox (Phase 17) treats a model
*as* its parameters in a single pytree, Flax separates them: the
model is an architecture object, parameters live in a separate
"variables" pytree, and the two combine at apply time.

This wrapper covers Flax Linen. NNX (Flax's newer mutable-state
API) is out of scope for this phase — see
[`implementation_plans/jax/phase18_flax.md`](../implementation_plans/jax/phase18_flax.md)
Issue 1.

## Import

```clausal
-import_module(jax)
-import_module(flax)
-import_from(py.jax_random, [key, split_key])
-import_from(py.jax_tree, [apply_updates, leaf])
-import_from(py.jax_optax, [sgd, init_optimizer, update_optimizer])
-import_from(py.jax_transforms, [value_and_grad])
-import_from(py.jax_flax, [
    dense, conv, layer_norm, dropout, sequential,
    init, apply, init_with_output,
    apply_mutable, apply_with_rngs,
    max_pool, avg_pool,
])
```

---

## The init / apply discipline

Flax's defining contract: build the model, then call `init` with a
PRNG key + example input to get a variables pytree, then call
`apply` with `(variables, input)` for every forward pass. The
model carries no state.

```clausal
test("Dense init+apply round-trip") <- (
    dense(8, MODEL),
    key(0, K),
    EXAMPLE is ++(jax.numpy.ones(4)),
    init(MODEL, K, EXAMPLE, VARS),
    X is ++(jax.numpy.ones(4)),
    apply(MODEL, VARS, X, Y),
    shape(Y, [8])
)
```

Three apply variants cover stateful and stochastic cases:

| Predicate | When to use |
|---|---|
| `apply(M, VARS, X, Y)` | Pure stateless forward — most layers |
| `apply_mutable(M, VARS, X, MUTABLE_LIST, RESULT)` | Layers with mutable collections (`BatchNorm` → `["batch_stats"]`); `RESULT is (Y, NEW_STATE)` |
| `apply_with_rngs(M, VARS, X, RNGS_DICT, Y)` | Stochastic layers (`Dropout` in training mode) |

`init_with_output(M, K, EXAMPLE, RESULT)` combines `init` + first
forward pass when you need both at once; `RESULT is (Y, VARS)`.

### Naming

Predicates use Flax's natural names (`init`, `apply`,
`init_with_output`) rather than defensively-prefixed forms
(`flax_init`, `flax_apply`). Users importing into a namespace where
collision matters can use the module-qualified form
(`flax.init(...)`, `py.jax_flax.apply(...)`) or rename at the
import site.

---

## Layers

Each `nn.Module` subclass in `flax.linen` has its own predicate.
Construction takes the layer's required hyperparameters as
positional args, plus an optional `OPTS` dict for the rest:

```clausal
dense(8, FC1)                        % Dense(features=8)
dense(8, {"use_bias": False}, FC2)   % Dense(features=8, use_bias=False)
conv(16, [3, 3], CONV)               % Conv(features=16, kernel_size=(3,3))
layer_norm(NORM)                      % LayerNorm()  — no required args
embed(1000, 64, EMB)                 % Embed(num_embeddings=1000, features=64)
```

The full surface, by category:

| Category | Predicates |
|---|---|
| Linear / projection | `dense`, `dense_general`, `einsum` |
| Convolution | `conv`, `conv_transpose`, `conv_local`, `conv_lstm_cell` |
| Embedding | `embed` |
| Dropout | `dropout` |
| Normalisation | `layer_norm`, `group_norm`, `instance_norm`, `rms_norm`, `batch_norm`, `spectral_norm`, `weight_norm` |
| Activation | `prelu` |
| Recurrent cells | `gru_cell`, `lstm_cell`, `optimized_lstm_cell`, `mgu_cell`, `simple_cell` |
| Sequence wrappers | `rnn`, `bidirectional` |
| Attention | `multi_head_attention`, `multi_head_dot_product_attention`, `self_attention` |
| Composition | `sequential` |

Notable Flax-vs-Equinox differences:

- **`conv` is dimensionality-agnostic** — Flax has one `Conv`; the
  spatial dims count is inferred from input shape and `kernel_size`
  tuple. No `conv1d`/`conv2d`/`conv3d` split.
- **Norms infer feature dims from input** — `layer_norm()` /
  `rms_norm()` take no required args at construction.
- **No PRNG key at construction** — the key flows in via `init`,
  not the constructor. This is the main shape difference from
  Equinox layer constructors (which take `KEY` as the last positional
  arg).

For relational discovery of available layer types, the
`layer_class/2` registry returns the actual `flax.linen` class by
TitleCase name — same shape as Equinox's:

```clausal
findall(N, layer_class(N, _), NS)
```

---

## Variables structure

`init` returns a dict pytree:

| Module type | Shape |
|---|---|
| Plain layer (Dense, Conv, …) | `{"params": {…}}` |
| BatchNorm | `{"params": {…}, "batch_stats": {…}}` |
| Models with submodules | Nested dicts following the module hierarchy |

Phase 9 pytree predicates work on `VARS` directly:

```clausal
init(MODEL, K, EXAMPLE, VARS),
findall(L, leaf(VARS, L), LEAVES),
length(LEAVES, N)
```

`leaf/2`, `tree_flatten/3`, `tree_map/3` etc. all enumerate /
transform the variables exactly as they would any other pytree.

---

## Stateful layers — `apply_mutable`

`BatchNorm` accumulates running statistics in a `batch_stats`
collection. Plain `apply/4` will fail because that collection isn't
mutable in the default apply call:

```clausal
batch_norm({"use_running_average": False}, BN),
init(BN, K, EXAMPLE, VARS),
apply_mutable(BN, VARS, X, ["batch_stats"], RESULT),
RESULT is (Y, NEW_STATE)
```

`NEW_STATE` is the updated `batch_stats` collection — thread it
through your training loop and merge back into `VARS` between
epochs.

The `MUTABLE_LIST` is whatever subset of variable collections should
be allowed to mutate in this apply call. Collections not listed
behave as in plain `apply/4`.

---

## Stochastic layers — `apply_with_rngs`

`Dropout` (in non-deterministic mode) needs a per-call PRNG key.
Flax's convention is a `{name: key}` dict mapping each stochastic
collection to its key:

```clausal
dropout(0.5, {"deterministic": False}, DROP),
key(0, K0),
split_key(K0, 2, [K_INIT, K_DROP]),
init(DROP, K_INIT, EXAMPLE, VARS),
apply_with_rngs(DROP, VARS, X, {"dropout": K_DROP}, Y)
```

For inference / evaluation, construct `Dropout` with
`{"deterministic": True}` and use plain `apply/4` — no RNG dict
needed.

---

## Pool functions — not Modules

Flax exposes pooling as **functions**, not Modules. They don't go
through `init`/`apply`:

```clausal
X is ++(jax.numpy.ones((1, 8, 8, 3))),
max_pool(X, [2, 2], {"strides": [2, 2]}, R)   % halves spatial dims
avg_pool(X, [2, 2], R)                         % stride defaults to 1
```

`window_shape` and `strides` accept either a list (Clausal-friendly)
or a tuple — the wrapper coerces lists to tuples for known shape
opts. The same is true of `padding` when not a string.

---

## End-to-end: training an MLP

Combining Phase 12 (`value_and_grad`) + Phase 16 (optax) + Phase 18
(this module). Variables flow through every step:

```clausal
test("MLP one optax SGD step changes the variables") <- (
    dense(4, FC1),
    dense(1, FC2),
    sequential([FC1, FC2], MODEL),
    key(0, K0),
    split_key(K0, 2, [K_INIT, _]),
    EXAMPLE is ++(jax.numpy.ones(2)),
    init(MODEL, K_INIT, EXAMPLE, VARS),
    XS is ++(jax.numpy.array([[1.0, 2.0], [3.0, 4.0]])),
    YS is ++(jax.numpy.array([[5.0], [6.0]])),
    LOSS_FN is ++(lambda v: jax.numpy.mean(
        (jax.vmap(MODEL.apply, in_axes=(None, 0))(v, XS) - YS) ** 2)),
    value_and_grad(LOSS_FN, VARS, VG),
    VG is (_LOSS, GRADS),
    sgd(0.01, OPT),
    init_optimizer(OPT, VARS, STATE),
    update_optimizer(OPT, GRADS, STATE, UR),
    UR is (UPDATES, _),
    apply_updates(VARS, UPDATES, NEW_VARS)
)
```

Notes:
- `apply_updates` comes from `py.jax_tree` (canonical home — it's a
  pure pytree op, not optimiser-specific).
- The loss closure uses `MODEL.apply` directly inside `++()`. You
  *could* wrap with the `apply/4` predicate, but that's clunky
  inside a JAX-traced function — staying in pure-Python for the
  loss body is the natural Flax idiom.
- Plain `value_and_grad` (not `filter_value_and_grad`) is correct
  here: variables are pure-array pytrees, so JAX's grad sees them
  directly.

---

## Comparison to Equinox (Phase 17)

| | Flax Linen | Equinox |
|---|---|---|
| What is "the model"? | Architecture object (no params yet) | Pytree containing params |
| Where do params live? | Separate `variables` pytree | Inside the model |
| Construction | `dense(8, M)` | `linear(4, 8, K, M)` (key at construction) |
| Forward pass | `apply(M, VARS, X, Y)` | `apply_module(M, X, Y)` or `++(M(X))` |
| Stateful layers | `apply_mutable/5` | (Phase 17b — stateful surface deferred) |
| Filter transforms | Not needed; vars are pure arrays | `filter_grad_value`, `filter_value_and_grad`, … |
| Custom modules | Out of scope (escape via `++()`) | Out of scope (same) |

Pick whichever matches the upstream code or community you're
working with. Both compose with optax (Phase 16) and the pytree
predicates (Phase 9) the same way.

---

## Caveats

### `apply` will fail on BatchNorm

Use `apply_mutable(BN, VARS, X, ["batch_stats"], RESULT)`. Plain
`apply/4` raises because the `batch_stats` collection isn't mutable
by default. This is Flax's design, not a wrapper bug.

### `Dropout` needs configuration

`Dropout(rate)` at construction is *underspecified* — the
`deterministic` kwarg must be set either at construction
(`dropout(0.5, {"deterministic": True}, M)`) or implicitly by
matching the apply-time arg shape. The wrapper exposes only the
`deterministic`-at-construction path; for runtime toggling, escape
to `++()`.

### Custom user-defined Linen modules

The heart of Flax is `class MyModel(nn.Module): @nn.compact def
__call__(self, x): ...`. We don't wrap module *definition* — only
the ~28 pre-built layers. For custom architectures:

```clausal
MODEL is ++(define_my_model())
init(MODEL, K, X, VARS)
```

The init/apply contract still works; you just construct the model
instance from raw Python.

### Pool ops are functions, not Modules

`max_pool` and `avg_pool` operate on arrays directly. Don't try to
feed them to `init`/`apply` — they have no parameters.

### NNX deferred

Flax's newer NNX API (mutable references, more PyTorch-like) is out
of scope for Phase 18. If a real caller needs it, that becomes
Phase 18b with its own wrapper file (`jax_flax_nnx.py`) — different
state-threading discipline, different mental model.

### Filter transforms not needed

Equinox needed `filter_grad`/`filter_value_and_grad` because Equinox
models contain non-array leaves (Python functions for activations).
Flax variables are pure-array pytrees, so plain `grad_value` /
`value_and_grad` from Phase 12 work directly. No `filter_*` siblings
in `py.jax_flax`.

### `apply_updates` works as-is

The gradients pytree from `value_and_grad(loss_fn, vars)` matches
`vars`'s structure, and `py.jax_tree.apply_updates` adds them leaf
by leaf. The Equinox-driven None-handling fix to `apply_updates`
carries over with no extra work.
