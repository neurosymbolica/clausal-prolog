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
test("activation lookup by name") <- (
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
test("relu zeroes negatives") <- (
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
test("one_hot basic") <- (
    array([0, 2, 1], X),
    one_hot(X, 3, R),
    array_list(R, [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
)
```

---

## Defaults cheatsheet — JAX vs PyTorch

Defaults used by the two-arg `_apply` predicates (and the three-arg
`softmax_apply`/`log_softmax_apply`), alongside PyTorch's
`torch.nn.functional` equivalents. Call out the ones in **bold** —
those disagree between the libraries, so a PyTorch migrator relying on
defaults will get a different numeric result.

| Predicate | JAX default | PyTorch default | Notes |
|---|---|---|---|
| `relu_apply(A, R)` | — | — | Same |
| `sigmoid_apply(A, R)` | — | — | Same |
| `tanh_apply(A, R)` | — | — | Same |
| `softmax_apply(A, AXIS, R)` | axis is required | `dim=None` (warns, infers) | Clausal requires the axis explicitly — no silent default |
| `log_softmax_apply(A, AXIS, R)` | axis is required | `dim=None` (warns, infers) | Same story |
| **`gelu_apply(A, R)`** | **`approximate=True` (tanh form)** | **`approximate='none'` (exact)** | Different numerics. Pass `gelu_apply(A, 0, R)` to force the exact form. |
| `gelu_apply(A, APPROX, R)` | bool; `0` → exact, `1` → tanh | string `'none'` / `'tanh'` | Type of the flag differs — Clausal uses a truthy int/bool, PyTorch a string |
| `elu_apply(A, R)` | `alpha=1.0` | `alpha=1.0` | Same. No arity with `alpha` — wrap via `++()` to override |
| `leaky_relu_apply(A, R)` | `negative_slope=0.01` | `negative_slope=0.01` | Same |
| `leaky_relu_apply(A, NEG_SLOPE, R)` | explicit | explicit | Same numeric meaning |
| `selu_apply(A, R)` | — | — | Same (fixed `alpha`/`scale`) |
| `softplus_apply(A, R)` | `beta=1`, no threshold | `beta=1.0`, `threshold=20.0` | JAX has no threshold override, PyTorch clips for large `x`; numerically indistinguishable at typical magnitudes |
| `silu_apply(A, R)` | — | — | Same. PyTorch's `silu` == JAX's `silu` == "swish" |
| `one_hot(X, NUM_CLASSES, R)` | axis defaults to `-1`; float dtype | same axis; float dtype | `num_classes` is required in both (PyTorch accepts `-1` to auto-size, which JAX doesn't) |

`gelu` is the one real trap. Phase 10 preserves JAX's default, so
`gelu_apply(A, R)` matches `jax.nn.gelu(x)` bit-for-bit; that's the
right default if you're writing JAX-native code, and the wrong one if
you're porting a PyTorch model. For ports, make the approximation
explicit:

```clausal
gelu_apply(A, 0, R)    # exact — matches torch.nn.functional.gelu(x)
gelu_apply(A, 1, R)    # tanh — matches jax.nn.gelu(x) default
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
test("init_array with glorot_uniform") <- (
    initializer("glorot_uniform", F),
    key(0, K),
    init_array(F, K, [10, 5], W),
    shape(W, [10, 5])
)

test("init_array with zeros (direct initializer)") <- (
    initializer("zeros", F),
    key(0, K),
    init_array(F, K, [3], W),
    array_list(W, [0.0, 0.0, 0.0])
)
```

`init_array` is deterministic given the same key:

```clausal
test("same key → same sample") <- (
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
test("constant 0.5 initializer") <- (
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
test("1-D glorot fails") <- (
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
