# jax_nn — JAX Activations and Initializers

`jax.nn` is a small, sharply-scoped module — activation functions plus
a parameter-initializer registry, no module classes. Where PyTorch
wraps `torch.nn.Module` subclasses, JAX's neural-net world lives inside
library code like Flax or Equinox, leaving the core `jax.nn` surface
purely functional.

The Clausal wrapper follows that shape: two **registries** (activations
and initializers), plus convenience `_apply` predicates for the
activations users reach for most often, plus `init_array` for invoking
an initializer against a PRNG key and shape.

All predicates are Tier 1 pure.

## Import

```clausal
-import_from(py.jax_nn, [
    activation, initializer, init_array,
    relu_apply, sigmoid_apply, tanh_apply,
    softmax_apply, log_softmax_apply,
    gelu_apply, elu_apply, leaky_relu_apply,
    selu_apply, softplus_apply, silu_apply,
    one_hot
])
```

---

## Activation registry

### `activation(NAME, FN)`

Nondeterministic fact table keyed on JAX's own activation names.

| Modes | Behaviour |
|---|---|
| `(+NAME, -FN)` | Look up by name |
| `(-NAME, +FN)` | Reverse lookup |
| `(-NAME, -FN)` | Enumerate every activation |
| `(+NAME, +FN)` | Check |

```clausal
Test("activation lookup by name") <- (
    activation("relu", FN),
    FN != ++(None)
)
```

Enumerated names: `relu`, `relu6`, `sigmoid`, `tanh`, `softmax`,
`log_softmax`, `gelu`, `elu`, `leaky_relu`, `selu`, `softplus`, `silu`,
`swish`, `mish`, `hard_tanh`, `hard_sigmoid`, `hard_silu`, `hard_swish`,
`celu`, `glu`, `soft_sign`, `logsumexp`.

### Applied activations

Each commonly-used activation has an `_apply` predicate that calls it
against an array directly. The `_apply` suffix prevents name collision
with the registry atom (`"relu"` the string vs `relu_apply` the
predicate).

| Predicate | Semantics |
|---|---|
| `relu_apply(A, R)` | Element-wise ReLU |
| `sigmoid_apply(A, R)` | Same function as Phase 7's `sigmoid` |
| `tanh_apply(A, R)` | |
| `softmax_apply(A, AXIS, R)` | |
| `log_softmax_apply(A, AXIS, R)` | |
| `gelu_apply(A, R)` / `gelu_apply(A, APPROX, R)` | `APPROX` is truthy → use approximate form |
| `elu_apply(A, R)` | |
| `leaky_relu_apply(A, R)` / `(A, NEG_SLOPE, R)` | Default negative slope 0.01 |
| `selu_apply(A, R)` | |
| `softplus_apply(A, R)` | |
| `silu_apply(A, R)` | Also known as swish |

```clausal
Test("relu zeroes negatives") <- (
    array([-1.0, 0.0, 1.0, 2.0], A),
    relu_apply(A, R),
    array_list(R, [0.0, 0.0, 1.0, 2.0])
)
```

Phase 7 already provides `sigmoid/2`, `softmax/3`, `log_softmax/3` with
identical semantics — the Phase 10 `*_apply` forms exist so users can
stay inside one import block when working with neural-net code.

### `one_hot(X, NUM_CLASSES, R)` / `(X, NUM_CLASSES, DTYPE, R)`

Index-array-to-one-hot encoding:

```clausal
Test("one_hot basic") <- (
    array([0, 2, 1], X),
    one_hot(X, 3, R),
    array_list(R, [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
)
```

---

## Initializer registry

### `initializer(NAME, FACTORY)`

Same shape as `activation/2` — nondeterministic fact table. Enumerated
names: `zeros`, `ones`, `constant`, `normal`, `uniform`,
`truncated_normal`, `variance_scaling`, `glorot_normal`,
`glorot_uniform`, `xavier_normal`, `xavier_uniform`, `he_normal`,
`he_uniform`, `kaiming_normal`, `kaiming_uniform`, `lecun_normal`,
`lecun_uniform`, `orthogonal`, `delta_orthogonal`.

The registry mixes two object types:

- **Direct initializers** (`zeros`, `ones`) — callable as
  `init(key, shape[, dtype])`.
- **Factories** (`glorot_uniform`, `he_normal`, `normal`, ...) —
  callable with no args (or config args) to produce an initializer.

`init_array/4,/5` normalises both shapes, so users don't care about
the distinction.

### `init_array(FACTORY, KEY, SHAPE, A)` / `(FACTORY, KEY, SHAPE, DTYPE, A)`

Invoke an initializer:

```clausal
Test("init_array with glorot_uniform") <- (
    initializer("glorot_uniform", F),
    key(0, K),
    init_array(F, K, [10, 5], W),
    shape(W, [10, 5])
)

Test("init_array with zeros (direct initializer)") <- (
    initializer("zeros", F),
    key(0, K),
    init_array(F, K, [3], W),
    array_list(W, [0.0, 0.0, 0.0])
)
```

`init_array` is deterministic given the same key:

```clausal
Test("same key → same sample") <- (
    initializer("glorot_uniform", F),
    key(7, K),
    init_array(F, K, [4, 2], W1),
    init_array(F, K, [4, 2], W2),
    array_list(W1, LS),
    array_list(W2, LS)
)
```

### Configured initializers

Some initializers need config arguments — `constant(0.5)`,
`variance_scaling(2.0, "fan_in", "normal")`, etc. These can't be built
from the bare registry entry; construct them via `++()` and pass the
result straight into `init_array`. With `-import_module(jax)` at the
top of the file, the Python-side access path stays clean:

```clausal
Test("constant 0.5 initializer") <- (
    F is ++(jax.nn.initializers.constant(0.5)),
    key(0, K),
    init_array(F, K, [3], W),
    array_list(W, [0.5, 0.5, 0.5])
)
```

The configured result is already an initializer (takes `(key, shape)`
directly), which `init_array`'s signature-introspection detects and
calls without an extra `()` step.

### Shape requirements

Some initializers constrain the shape. `glorot_*`, `xavier_*`,
`he_*`, `kaiming_*`, `lecun_*` need **at least 2 dimensions** (they
compute fan-in / fan-out). A 1-D call fails with a `ValueError` from
JAX, which surfaces as predicate failure:

```clausal
Test("1-D glorot fails") <- (
    initializer("glorot_uniform", F),
    key(0, K),
    not init_array(F, K, [8], _W)    # fails — 1-D not allowed
)
```

---

## Pattern — initialise a parameter pytree

Combine `init_array` with Phase 9's pytree operations to initialise a
whole model's worth of parameters. With a small config-pytree mapping
layer name to shape, `tree_map_n` (or a Python-side helper) builds the
parameter tree. This keeps the random-key splitting explicit and
backtracking-safe:

```clausal
-import_from(py.jax_random, [key, split_key])
-import_from(py.jax_nn, [initializer, init_array])

# Two-layer MLP: 784 -> 256 -> 10
init_mlp(SEED, W1, W2) <- (
    initializer("glorot_uniform", F),
    key(SEED, K),
    split_key(K, 2, [K1, K2]),
    init_array(F, K1, [784, 256], W1),
    init_array(F, K2, [256, 10], W2)
)
```

If a later goal fails, the abandoned keys `K1`/`K2` and weights are
dropped cleanly — `K` remains valid for a re-split.

---

## Deferred

- **Custom initializer registration.** Users can still build
  initializers inline via `++(...)`. A registry-side `register/2`
  predicate is not provided — JAX itself doesn't register
  initializers, they're just functions.
- **Flax / Equinox module wrappers.** Those live in their own libraries
  and would get their own Clausal wrapper — Phase 10 covers only the
  `jax.nn` surface.
