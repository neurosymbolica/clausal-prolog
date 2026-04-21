# Phase 10 — Neural-Net Activations and Initializers

`jax.nn` is small compared to `torch.nn`: it has no module classes (JAX
is a function library — model classes live in Flax/Equinox). What JAX
does provide is a clean set of activation functions and parameter
initializers. Both map cleanly to registries.

**File to create:** `clausal/modules/py/jax_nn.py`

**Depends on:** Phase 1 — `jax.py` lazy import helpers. Phase 2 —
`jax_random.py` keys for initializer application.

---

## Predicates

### Activation registry

| Name | Arity | Modes | Purity | Nondet? | Description |
|---|---|---|---|---|---|
| `activation` | `/2` | `(+N, -F)`, `(-N, -F)`, `(-N, +F)` | pure | yes | Enumerate `jax.nn` activations |

### Applied activations (wrappers for common ones)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `relu_apply` | `/2` | `(+A, -R)` | |
| `sigmoid_apply` | `/2` | | (sigmoid already in Phase 7 math — alias) |
| `tanh_apply` | `/2` | | |
| `softmax_apply` | `/3` | `(+A, +AXIS, -R)` | |
| `log_softmax_apply` | `/3` | | |
| `gelu_apply` | `/2, /3` | `(+A, -R)`, `(+A, +APPROX, -R)` | |
| `elu_apply` | `/2` | | |
| `leaky_relu_apply` | `/2, /3` | `(+A, -R)`, `(+A, +NEG_SLOPE, -R)` | |
| `selu_apply` | `/2` | | |
| `softplus_apply` | `/2` | | |
| `silu_apply` | `/2` | | Aka swish |
| `one_hot` | `/3, /4` | `(+X, +NUM_CLASSES, -R)`, `(+X, +NUM_CLASSES, +DTYPE, -R)` | |

The `_apply` suffix distinguishes applied functions from the registry
atoms.

### Initializer registry

| Name | Arity | Modes | Purity | Nondet? | Description |
|---|---|---|---|---|---|
| `initializer` | `/2` | `(+N, -FACTORY)`, `(-N, -FACTORY)`, `(-N, +FACTORY)` | pure | yes | `jax.nn.initializers` registry |

### Initializer application

| Name | Arity | Modes | Description |
|---|---|---|---|
| `init_array` | `/4, /5` | `(+INIT, +KEY, +SHAPE, -A)`, `(+INIT, +KEY, +SHAPE, +DTYPE, -A)` | Apply an initializer factory |

Note: `init` is a misleading name (confusable with "initialize");
`init_array` is clearer. An initializer factory is a callable
`(key, shape[, dtype]) -> array`.

---

## Context and Reference Patterns

### Activation registry via introspection

Similar to PyTorch Phase 3. Whitelist rather than `dir(jax.nn)` to
avoid internals:

```python
def _build_activation_facts():
    _ensure_jax()
    import jax.nn as jnn
    wanted = [
        "relu", "relu6", "sigmoid", "tanh", "softmax", "log_softmax",
        "gelu", "elu", "leaky_relu", "selu", "softplus", "silu",
        "swish", "mish", "hard_tanh", "hard_sigmoid", "hard_silu",
        "hard_swish", "celu", "glu", "soft_sign", "logsumexp",
    ]
    facts = []
    for name in wanted:
        fn = getattr(jnn, name, None)
        if fn is not None and callable(fn):
            facts.append((name, fn))
    return facts

activation = _pred("activation",
    (2, _fact_table_2(_build_activation_facts)),
)
```

### Initializer registry

`jax.nn.initializers.xavier_normal()` returns a *factory* — calling it
gives back a function `(key, shape, dtype) -> array`. The registry
stores the factory-creating function:

```python
def _build_initializer_facts():
    _ensure_jax()
    import jax.nn.initializers as ji
    wanted = [
        "zeros", "ones", "constant", "normal", "uniform",
        "truncated_normal", "variance_scaling",
        "glorot_normal", "glorot_uniform",
        "xavier_normal", "xavier_uniform",
        "he_normal", "he_uniform",
        "kaiming_normal", "kaiming_uniform",
        "lecun_normal", "lecun_uniform",
        "orthogonal", "delta_orthogonal",
    ]
    facts = []
    for name in wanted:
        factory = getattr(ji, name, None)
        if factory is not None:
            facts.append((name, factory))
    return facts
```

### `init_array`

The factory must first be called with no args (or with its config args)
to produce the actual initializer, then called with (key, shape). The
typical zero-arg path:

```python
init_array = _pred("init_array",
    (4, _pure(lambda factory, key, shape:
              factory()(key, tuple(shape)))),
    (5, _pure(lambda factory, key, shape, dtype:
              factory()(key, tuple(shape), dtype))),
)
```

For initializers that need args (e.g. `constant(0.5)`), users construct
the configured factory directly via `++()`.

### Applied activations

Thin wrappers:

```python
relu_apply = _pred("relu_apply",
    (2, _pure(lambda a: _jnn().relu(a))),
)

gelu_apply = _pred("gelu_apply",
    (2, _pure(lambda a: _jnn().gelu(a))),
    (3, _pure(lambda a, approx: _jnn().gelu(a, approximate=bool(approx)))),
)
```

---

## Example Usage

```clausal
-import_from(py.jax, [array, shape, array_list, zeros, ones])
-import_from(py.jax_random, [key])
-import_from(py.jax_nn, [activation, initializer, init_array,
                          relu_apply, softmax_apply, gelu_apply,
                          one_hot])

Test("enumerate activations") <- (
    findall(N, activation(N, _), NS),
    member("relu", NS),
    member("sigmoid", NS),
    member("gelu", NS)
)

Test("relu zeroes negatives") <- (
    array([-1.0, 0.0, 1.0], A),
    relu_apply(A, R),
    array_list(R, [0.0, 0.0, 1.0])
)

Test("softmax sums to 1") <- (
    array([1.0, 2.0, 3.0], A),
    softmax_apply(A, 0, R),
    sum(R, S),
    array_list(S, V),
    V > 0.99,
    V < 1.01
)

Test("enumerate initializers") <- (
    findall(N, initializer(N, _), NS),
    member("glorot_uniform", NS),
    member("he_normal", NS),
    member("zeros", NS)
)

Test("init_array with glorot_uniform") <- (
    initializer("glorot_uniform", FACTORY),
    key(0, K),
    init_array(FACTORY, K, [10, 5], W),
    shape(W, [10, 5])
)

Test("one_hot encoding") <- (
    array([0, 2, 1], X),
    one_hot(X, 3, R),
    array_list(R, [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
)
```

---

## Tests

`tests/fixtures/jax_nn_tests.clausal`:
- Activation registry: specific lookup, findall, reverse lookup
- Each applied activation with a value spot-check
- Initializer registry: findall, lookup
- `init_array` with common initializers
- `one_hot` for small cases
- Determinism of initializers given the same key

---

## Docs

Create `docs/jax_nn.md`:
- `jax.nn` vs `torch.nn` — function vs module library
- Activation registry and applied forms
- Initializer registry and application
- Pattern: use pytrees (Phase 9) to initialise a parameter tree

---

## Issues

_To be populated during implementation._

1. **`variance_scaling` initializer** takes config args. The simple
   `init_array` path calls the factory with no args — which fails for
   variance_scaling. Document that configured initializers need a
   `++()` escape, or add a variant that passes through kwargs.
2. **Activation name collisions with Phase 7 math.** `sigmoid_apply`
   vs `sigmoid` — the former lives here, the latter in Phase 7.
   Document the split.
