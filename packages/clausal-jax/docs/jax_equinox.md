# jax_equinox — Equinox Layers, Filter Transforms, Pytree Utilities

[Equinox](https://docs.kidger.site/equinox/) is the JAX library that
makes neural-net modules first-class pytrees. An `eqx.Module` is a
JAX-registered dataclass: instantiate once with the right shapes
plus a PRNG key, then apply it like any callable.

This module ties the wrapper's NN story together — Phase 9
(pytrees) + Phase 10 (`jax_nn` activations) + Phase 12 (transforms)
+ Phase 16 (optax) gave us params + losses + gradients +
optimisers; Equinox supplies the model-construction layer and the
**filter** variants of JAX's transforms (`filter_jit`, `filter_grad`,
…) so trees containing non-array leaves work without manual
partitioning.

## Import

```clausal
-import_module(jax)
-import_module(equinox)
-import_from(py.jax_random, [key, split_key])
-import_from(py.jax_tree, [apply_updates])
-import_from(py.jax_optax, [sgd, init_optimizer, update_optimizer])
-import_from(py.jax_equinox, [
    linear, mlp, layer_norm, sequential, dropout,
    apply_module,
    filter_grad_value, filter_value_and_grad, filter_jit_compile,
    partition, combine, tree_at_set,
    is_array, tree_equal,
    serialise, deserialise,
])
```

---

## Layer construction

Each `eqx.nn.*` class has a per-class predicate with a snake_case
name. Required positional args first; an optional `OPTS` dict last
for the rest of the constructor's keyword arguments. Layers that
need a PRNG key take it as the very last positional arg.

```clausal
key(0, K0),
split_key(K0, 3, [K1, K2, K3]),

linear(4, 8, K1, FC1),                      % standard form
linear(4, 8, {"use_bias": False}, K2, FC2), % opts variant
mlp(2, 1, 4, 1, K3, MODEL),                  % MLP(in, out, width, depth, key)
layer_norm(8, NORM)                          % no key needed
```

The full surface is enumerated in the module docstring. Categorisation:

| Category | Examples |
|---|---|
| Linear / MLP | `linear`, `mlp` |
| Convolution | `conv`, `conv1d`, `conv2d`, `conv3d`, `conv_transpose1d`/`2d`/`3d` |
| Pooling | `max_pool1d`/`2d`/`3d`, `avg_pool1d`/`2d`/`3d`, `adaptive_*_pool*` |
| Normalisation | `layer_norm`, `group_norm`, `rms_norm`, `weight_norm`, `spectral_norm` |
| Recurrent | `gru_cell`, `lstm_cell` |
| Attention / embedding | `multihead_attention`, `embedding`, `rotary_positional_embedding` |
| Activation / structural | `dropout`, `prelu`, `identity`, `lambda_layer`, `sequential` |

Why per-class instead of one generic `layer/3` constructor: see
[`implementation_plans/jax/todo/jax_registries_discussion.md`](../implementation_plans/jax/todo/jax_registries_discussion.md).
The short version is that registry-form construction has higher
call-site cost (string name + runtime-validated kwargs dict) than
per-class predicates with named positional args, and nobody
enumerates layer types when building a model.

The `lambda` class is renamed `lambda_layer` because `lambda` is
reserved.

### Discovery

If you genuinely want to enumerate available layer types
(introspection, code generation), the `layer_class/2` registry is
the side channel for that — it returns the actual `eqx.nn` class by
TitleCase name, not the wrapper predicate:

```clausal
findall(N, layer_class(N, _), NS)
```

---

## Module application

Equinox modules are first-class callables, so `++(M(X))` works
unchanged. `apply_module/3` is sugar that adds deep-deref over `X`
(useful when `X` is a list/tuple containing Vars) and makes the
application visually consistent with Phase 10's `relu_apply` etc:

```clausal
linear(4, 8, K, M),
X is ++(jax.numpy.ones(4)),
apply_module(M, X, Y)
```

For modules taking extra kwargs (e.g. training-mode `Dropout` with
a per-call key — see Phase 17b below), use the `/4` form:

```clausal
apply_module(MODEL, X, {"key": K}, Y)
```

---

## Stateful modules (Phase 17b)

Equinox's stateful layers pair a model pytree with a separate
`State` pytree, threaded explicitly. `BatchNorm` needs running
mean/variance; training-mode `Dropout` needs a per-call PRNG key;
both require a distinct contract from the stateless layers above.

### Constructors return `(MODEL, STATE)`

`batch_norm/4,/5` returns the model **and** its state as two output
slots (mirroring `partition/4`):

```clausal
batch_norm(3, "batch", BN, STATE),
batch_norm(3, "batch", {"mode": "batch"}, BN, STATE)
```

The axis name is a string (or a sequence of strings — BatchNorm
supports multi-axis reduction). `mode="batch"` is Equinox's
recommendation for new code; the `/4` arity falls back to
`mode="ema"` and triggers a deprecation warning.

Other stateful layers go through the generic `make_with_state/4`,
which takes a class value and a kwargs dict:

```clausal
BN_CLS is ++(equinox.nn.BatchNorm),
make_with_state(BN_CLS, {"input_size": 3, "axis_name": "batch",
                         "mode": "batch"}, BN, STATE)
```

This is the escape for user-defined `StatefulLayer` subclasses or
stateful variants of `SpectralNorm`.

### Apply threads state in and out

`apply_stateful_module/5` calls `m(x, state)` and unifies `Y` with
the output, `NEW_STATE` with the updated state:

```clausal
apply_stateful_module(M, X, STATE, Y, NEW_STATE)
apply_stateful_module(M, X, {"key": K}, STATE, Y, NEW_STATE)
```

Two output slots — state threading is the primary flow, not an
afterthought.

### BatchNorm needs `vmap` for training mode

BatchNorm's `axis_name` is a *named batch axis* that only exists
under `jax.vmap` or `jax.shard_map`. Calling a training-mode
BatchNorm on a raw input errors with "Found an unbound axis name".
Wrap it yourself and pass the vmapped module to
`apply_stateful_module`:

```clausal
batch_norm(3, "batch", {"mode": "batch"}, BN, STATE),
X is ++(jax.numpy.ones((4, 3))),
VMAPPED is ++(jax.vmap(BN, axis_name="batch",
                       in_axes=(0, None), out_axes=(0, None))),
apply_stateful_module(VMAPPED, X, STATE, Y, NEW_STATE)
```

Inference mode skips the reduction and applies to unbatched inputs
— the usual eval path.

### `inference_mode` flips `inference` fields across the tree

`eqx.nn.inference_mode` walks the pytree and sets each
`.inference` field to the target value. Use it to swap a trained
model for evaluation:

```clausal
inference_mode(MODEL, EVAL_MODEL),         % value=True default
inference_mode(EVAL_MODEL, False, TRAIN_MODEL) % explicit switch back
```

The `/2` arity defaults to `value=True` since that's the common
swap direction.

### Training-mode Dropout: `dropout_train` + per-call key

`dropout_train/2,/3` constructs `Dropout(p, inference=False)`. It
has no `State` pytree (dropout is stochastic, not stateful) but
consumes a per-call PRNG key — applied via `apply_module/4`:

```clausal
dropout_train(0.5, D),
apply_module(D, X, {"key": K}, Y)
```

Split from Phase 17's `dropout/2` (inference-mode default) so the
train/eval choice is explicit at construction time. Mixing them is
a common bug; two names is clearer than a boolean hidden in an
opts dict.

### `is_stateful` check predicate

Mirrors `is_array`:

```clausal
batch_norm(3, "batch", BN, _STATE),
is_stateful(BN),        % succeeds

key(0, K),
linear(3, 3, K, LIN),
not is_stateful(LIN)    % succeeds (Linear is stateless)
```

### `State` inspection via Phase 9 pytree predicates

`eqx.nn.State` is a registered pytree; Phase 9's `leaf/2`,
`tree_flatten/3` work on it unchanged:

```clausal
batch_norm(3, "batch", _BN, STATE),
findall(L, leaf(STATE, L), LEAVES)
```

Useful when debugging running statistics or serialising state
alongside a model.

---

---

## Filter transforms

JAX's bare `grad` / `jit` / `vmap` only handle pytrees of arrays.
Equinox models contain non-array leaves (Python functions for
activations, booleans for `use_bias`, etc.), so the bare transforms
fail. The `filter_*` variants partition the tree implicitly:
arrays are differentiable, everything else is static.

| Predicate | Mirrors | Use when… |
|---|---|---|
| `filter_grad_value(F, X, G)` | `grad_value` (Phase 12) | `X` is an Equinox module |
| `filter_value_and_grad(F, X, RESULT)` | `value_and_grad` | same; `RESULT is (V, G)` |
| `filter_jit_compile(F, F2)` | `jit_compile` | same |
| `filter_vmap_apply(F, X, R)` | `vmap_apply` | same |
| `filter_pmap_apply(F, X, R)` | `pmap_apply` | same |

These coexist with the Phase 12 transforms; pick by call site. Raw
JAX users want plain `grad_value`; Equinox users want
`filter_grad_value` by default.

---

## Partition / combine

Sometimes you want explicit control over the differentiable / static
split — e.g. to freeze part of a model.

```clausal
partition(MODEL, ++(equinox.is_array), DIFF, STATIC),
% ... train DIFF, leave STATIC alone ...
combine(NEW_DIFF, STATIC, NEW_MODEL)
```

The filter spec (second arg) is either:
- a callable returning bool per leaf (`++(equinox.is_array)`,
  `++(equinox.is_inexact_array)`, or your own); or
- an explicit pytree mirroring the model with `True`/`False` at each
  leaf.

`partition/4` is one of the few predicates with two output slots
(`DIFF`, `STATIC`) instead of returning a tuple — the partition step
is in the hot path of every `filter_grad` call and the slight
non-uniformity is justified.

---

## Surgical updates with `tree_at`

`tree_at_set` and `tree_at_apply` replace or transform individual
leaves of a model identified by a callable `WHERE` returning the
leaf(s) to update:

```clausal
tree_at_set(++(lambda m: m.bias), MODEL, NEW_BIAS, NEW_MODEL),

tree_at_apply(++(lambda m: m.bias), MODEL, ++(lambda b: b * 0), ZEROED)
```

The natural Clausal-side `WHERE` is a Python lambda capturing
attribute access — `++(lambda m: m.weight)` for a single leaf,
`++(lambda m: (m.layers[0].weight, m.layers[1].bias))` for
multiple.

---

## Leaf checks

Parallel to Phase 6's `has_nan` / `has_inf` / `all_finite`:

| Predicate | Succeeds iff |
|---|---|
| `is_array(X)` | `eqx.is_array(X)` — JAX or NumPy array |
| `is_inexact_array(X)` | floating-point or complex array only |
| `is_array_like(X)` | array or Python scalar |
| `tree_equal(A, B)` | both pytrees have identical structure and values |

---

## Serialisation

`serialise/2` writes a model's leaves to a file path; `deserialise/3`
reads them back, given a "like" tree to provide structure and
dtypes:

```clausal
% Train and save
linear(3, 5, K, MODEL),
serialise(MODEL, "/tmp/model.eqx"),

% Reload — reconstruct an empty model with the same hyperparams
linear(3, 5, K, LIKE),
deserialise("/tmp/model.eqx", LIKE, LOADED)
```

These touch the filesystem — they're Tier 4 IO, **not
backtracking-safe**. Re-running `serialise/2` on redo will overwrite
the file silently. Commit serialisation at end-of-loop, not inside a
search.

---

## End-to-end: training an MLP

The full loop combining Phase 16 (optax) + Phase 17 (equinox) +
Phase 12 (filter transforms):

```clausal
Test("MLP one optax SGD step changes the model") <- (
    key(0, K0),
    split_key(K0, 2, [K_INIT, _]),
    mlp(2, 1, 4, 1, K_INIT, MODEL),
    LOSS_FN is ++(lambda m: jax.numpy.mean(
        (jax.vmap(m)(jax.numpy.array([[1.0, 2.0], [3.0, 4.0]]))
         - jax.numpy.array([[5.0], [6.0]])) ** 2)),
    filter_value_and_grad(LOSS_FN, MODEL, VG),
    VG is (_LOSS, GRADS),
    sgd(0.01, OPT),
    init_optimizer(OPT, MODEL, STATE),
    update_optimizer(OPT, GRADS, STATE, UR),
    UR is (UPDATES, _),
    apply_updates(MODEL, UPDATES, NEW_MODEL),
    not tree_equal(MODEL, NEW_MODEL)
)
```

Note the imports: `apply_updates` comes from `py.jax_tree` (its
canonical home — it's a pure pytree operation, not optimiser- or
NN-specific). It's also re-exported from `py.jax_optax` for
backwards compatibility, but `py.jax_tree` is the preferred import.

`apply_updates` understands `None` updates: when
`filter_value_and_grad` returns gradients with `None` at
non-differentiable leaves (Equinox modules contain Python functions
for activations, etc.), the predicate keeps the original leaf
unchanged at those slots. This matches `eqx.apply_updates`'s
behaviour, and is more permissive than raw `optax.apply_updates` —
which is why having one canonical home for the operation in
`py.jax_tree` is the right call.

---

## Caveats

### Pooling defaults to stride=1

Equinox's pooling layers default `stride=1` (different from
PyTorch's default of stride=kernel_size). Pass `{"stride": K}` in
opts to get the PyTorch-equivalent behaviour:

```clausal
max_pool2d(2, {"stride": 2}, M)   % halves spatial dims
max_pool2d(2, M)                   % stride 1 — output is 7x7 from 8x8
```

### `tree_equal` returns a JAX array, not bool

`eqx.tree_equal` returns `Array(True, dtype=bool)`. The wrapper
coerces with `bool(...)` so `tree_equal/2` works as a normal Clausal
check predicate. If you want the underlying array (e.g. to feed it
into another JAX op), reach for `++(equinox.tree_equal(A, B))`.

### Filter transforms vs Phase 12 transforms

Both `grad_value` (Phase 12) and `filter_grad_value` (Phase 17)
exist. They're not interchangeable:

- Phase 12 transforms work on raw arrays / array-only pytrees.
- Phase 17 filter transforms work on Equinox models (or any pytree
  with non-array leaves).

If you call `grad_value` on an Equinox module you'll get an error
about non-differentiable leaves; reach for `filter_grad_value`
instead.

### `apply_module/3` vs `++(M(X))`

Both work and produce the same result. Use `apply_module/3` when
`X` is structured Clausal-side (lists/tuples with Vars to deref).
Use `++(M(X))` when you've already got a JAX value in hand and
want to skip the predicate dispatch.
