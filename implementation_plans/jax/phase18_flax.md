# Phase 18 — Flax Linen: Models with Explicit Variables

[Flax](https://flax.readthedocs.io) is the second major NN library
for JAX. Unlike Equinox (Phase 17), where the model **is** its
parameters as a single pytree, Flax's **Linen** API splits them:
the model is an architecture object, parameters live in a separate
"variables" pytree, and the two combine at apply time.

That separation is the heart of the design call to make: it's a
different state-threading discipline from Equinox, and the wrapper
should follow Flax's own convention rather than try to make it
look like Equinox.

This phase wraps Flax Linen. NNX (Flax's newer mutable-state API)
is out of scope — different mental model, different file when /
if it lands. See Issue 1.

**File to create:** `clausal/modules/py/jax_flax.py`

**Depends on:**
- Phase 1 — `_ensure_jax`, helpers
- Phase 2 — PRNG keys (every `init` takes one)
- Phase 9 — pytrees (`variables` is a pytree dict)
- Phase 12 — function transforms (loss + gradient computation)
- Phase 16 — optax (training loop)
- Phase 17 — Equinox (sibling NN library; user docs cross-reference)

**External dependency:** `flax` (lazy-imported via the same
`_ensure_*` pattern as `_ensure_jax`).

---

## Core Concepts

| Flax concept | Clausal predicate | Notes |
|---|---|---|
| `nn.Module` instance (architecture) | First-class JAX value | Construct via per-class predicates (`dense`, `conv`, …) |
| Variables (`{params: ..., batch_stats: ...}`) | Pytree dict; first-class value | Returned by `init`, consumed by `apply` |
| `model.init(key, *example)` | `init/4` | Builds variables from a key + example input |
| `model.apply(variables, *inputs)` | `apply/4` | Forward pass; pure if `mutable=False` |
| `model.apply(..., mutable=[...])` | `apply_mutable/5` | Returns `(out, new_state)` for stateful collections |
| RNGs at apply time (e.g. for Dropout) | `apply_with_rngs/5` | Threaded via a `{name: key}` dict |
| Pooling functions (`nn.max_pool`, `nn.avg_pool`) | Direct functions, not Modules — `max_pool/4`, `avg_pool/4` | No init/apply needed |

Flax modules and variables stay opaque. Variables are a pytree of
dicts that Phase 9 predicates already enumerate and walk; no
Phase-18-specific introspection predicate.

---

## Predicates

### Layer constructors (~30 per-class, all Tier 1 pure)

Mirroring Phase 17's per-class pattern. Flax-specific notes:

- **No PRNG key at construction.** Unlike Equinox, Flax separates
  *describing* the layer from *initialising* it. The key flows in
  via `init`, not the constructor. So most layer predicates
  have one fewer arg than their Equinox counterparts.
- **Convolution is dimensionality-agnostic.** Flax has a single
  `nn.Conv` (and `nn.ConvTranspose`); the spatial-dims count is
  inferred from the input shape and `kernel_size` tuple. No
  `conv1d`/`2d`/`3d` split.
- **Normalisation layers don't take a shape.** `nn.LayerNorm()`,
  `nn.GroupNorm()`, etc. infer feature dims from input.

| Predicate | Arity | Wraps | Required args |
|---|---|---|---|
| `dense` | `/2, /3` | `nn.Dense` | `features, [opts]` |
| `dense_general` | `/2, /3` | `nn.DenseGeneral` | `features, [opts]` |
| `einsum` | `/3, /4` | `nn.Einsum` | `shape, equation, [opts]` |
| `conv` | `/3, /4` | `nn.Conv` | `features, kernel_size, [opts]` |
| `conv_transpose` | `/3, /4` | `nn.ConvTranspose` | same shape |
| `conv_local` | `/3, /4` | `nn.ConvLocal` | same shape |
| `conv_lstm_cell` | `/3, /4` | `nn.ConvLSTMCell` | `features, kernel_size, [opts]` |
| `embed` | `/3, /4` | `nn.Embed` | `num_embeddings, features, [opts]` |
| `dropout` | `/2, /3` | `nn.Dropout` | `rate, [opts]` |
| `layer_norm` | `/1, /2` | `nn.LayerNorm` | `[opts]` |
| `group_norm` | `/1, /2` | `nn.GroupNorm` | `[opts]` |
| `instance_norm` | `/1, /2` | `nn.InstanceNorm` | `[opts]` |
| `rms_norm` | `/1, /2` | `nn.RMSNorm` | `[opts]` |
| `batch_norm` | `/1, /2` | `nn.BatchNorm` | `[opts]` (stateful — see Issue 4) |
| `spectral_norm` | `/2, /3` | `nn.SpectralNorm` | `layer, [opts]` |
| `weight_norm` | `/2, /3` | `nn.WeightNorm` | `layer, [opts]` |
| `prelu` | `/1, /2` | `nn.PReLU` | `[opts]` |
| `gru_cell` | `/2, /3` | `nn.GRUCell` | `features, [opts]` |
| `lstm_cell` | `/2, /3` | `nn.LSTMCell` | `features, [opts]` |
| `optimized_lstm_cell` | `/2, /3` | `nn.OptimizedLSTMCell` | same shape |
| `mgu_cell` | `/2, /3` | `nn.MGUCell` | same shape |
| `simple_cell` | `/2, /3` | `nn.SimpleCell` | same shape |
| `rnn` | `/2, /3` | `nn.RNN` | `cell, [opts]` |
| `bidirectional` | `/3, /4` | `nn.Bidirectional` | `forward_rnn, backward_rnn, [opts]` |
| `multi_head_attention` | `/3, /4` | `nn.MultiHeadAttention` | `num_heads, qkv_features, [opts]` |
| `multi_head_dot_product_attention` | `/3, /4` | `nn.MultiHeadDotProductAttention` | same shape |
| `self_attention` | `/3, /4` | `nn.SelfAttention` | `num_heads, qkv_features, [opts]` |
| `sequential` | `/2` | `nn.Sequential` | `layers` |

**Skipped (niche / Fp8 internals):** `Fp8DirectDotGeneralOp`,
`Fp8DotGeneral`, `Fp8DotGeneralOp`, `Fp8Einsum`,
`NANOOFp8DotGeneralOp`. Users can `++(nn.Fp8DotGeneral(...))` if
they need them.

### Init / apply (Tier 3 state-threaded)

The defining shape of the wrapper. Three variants for the apply
side cover stateless, stateful (mutable collections), and
stochastic (RNG-threading):

| Name | Arity | Modes | Description |
|---|---|---|---|
| `init` | `/4` | `(+M, +KEY, +EXAMPLE, -VARS)` | `model.init(key, example)` |
| `init_with_output` | `/4` | `(+M, +KEY, +EXAMPLE, -RESULT)` | `RESULT is (OUT, VARS)` — `model.init_with_output(...)`, no extra forward pass |
| `apply` | `/4` | `(+M, +VARS, +INPUT, -OUT)` | `model.apply(variables, input)` |
| `apply_mutable` | `/5` | `(+M, +VARS, +INPUT, +MUTABLE_LIST, -RESULT)` | `RESULT is (OUT, NEW_STATE)` — for `BatchNorm` |
| `apply_with_rngs` | `/5` | `(+M, +VARS, +INPUT, +RNGS_DICT, -OUT)` | For `Dropout` and other stochastic layers |

Naming uses Flax's own names (`init`, `apply`,
`init_with_output`) rather than defensively-prefixed forms
(`flax_init`, `flax_apply`). Users importing into a namespace
where collision matters can either rename at the import site or
use the module-qualified form (`flax.init`,
`py.jax_flax.apply`). Across-module collisions are not the
wrapper's problem — that's what the module system is for.

### Pooling functions (Tier 1 pure, not Modules)

Flax's pool ops are *functions*, not Modules — they don't go
through `init`/`apply`:

| Name | Arity | Modes | Description |
|---|---|---|---|
| `max_pool` | `/3` | `(+X, +WINDOW, -R)` | `nn.max_pool(x, window_shape=W)` |
| `max_pool` | `/4` | `(+X, +WINDOW, +OPTS, -R)` | OPTS for stride/padding |
| `avg_pool` | `/3, /4` | same | `nn.avg_pool` |

### Layer enumeration registry (Tier 2 fact table)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `layer_class` | `/2` | `(+N, -CLS)`, `(-N, -CLS)` | Enumerate all `flax.linen.*` Module subclasses |

Side-channel for discovery — not the construction surface.

---

## Context and Reference Patterns

### Lazy import

```python
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
```

### Layer constructors

Flax layers take all hyperparameters as keyword arguments at
construction time; we follow Equinox's `(required positional,
[opts dict])` shape:

```python
dense = _pred("dense",
    (2, _pure(lambda f: _fnn().Dense(f))),
    (3, _pure(lambda f, opts: _fnn().Dense(f, **opts))),
)

layer_norm = _pred("layer_norm",
    (1, _pure(lambda: _fnn().LayerNorm())),
    (2, _pure(lambda opts: _fnn().LayerNorm(**opts))),
)

conv = _pred("conv",
    (3, _pure(lambda f, ks: _fnn().Conv(f, ks))),
    (4, _pure(lambda f, ks, opts: _fnn().Conv(f, ks, **opts))),
)
```

### `init` / `apply`

```python
init = _pred("init",
    (4, _pure(lambda m, key, example: m.init(key, example))),
)

apply = _pred("apply",
    (4, _pure(lambda m, variables, x: m.apply(variables, x))),
)

# init_with_output returns (out, variables) — single tuple result
init_with_output = _pred("init_with_output",
    (4, _pure(lambda m, key, example:
              tuple(m.init_with_output(key, example)))),
)
```

For mutable / RNG variants, `m.apply(...)` itself returns a tuple
when `mutable` is non-empty:

```python
apply_mutable = _pred("apply_mutable",
    (5, _pure(lambda m, vars_, x, mutable:
              tuple(m.apply(vars_, x, mutable=mutable)))),
)

apply_with_rngs = _pred("apply_with_rngs",
    (5, _pure(lambda m, vars_, x, rngs:
              m.apply(vars_, x, rngs=rngs))),
)
```

### Pool functions

```python
max_pool = _pred("max_pool",
    (3, _pure(lambda x, w: _fnn().max_pool(x, tuple(w)))),
    (4, _pure(lambda x, w, opts:
              _fnn().max_pool(x, tuple(w), **opts))),
)
```

---

## Example Usage

```clausal
-import_module(jax)
-import_module(flax)
-import_from(py.jax, [array, array_list, shape, allclose])
-import_from(py.jax_random, [key, split_key])
-import_from(py.jax_tree, [apply_updates])
-import_from(py.jax_optax, [sgd, init_optimizer, update_optimizer])
-import_from(py.jax_transforms, [value_and_grad])
-import_from(py.jax_flax, [
    dense, layer_norm, sequential, dropout,
    init, apply, apply_with_rngs,
    init_with_output, apply_mutable,
    max_pool, avg_pool,
    layer_class
])

Test("Dense forward shape") <- (
    dense(8, MODEL),
    key(0, K),
    EXAMPLE is ++(jax.numpy.ones(4)),
    init(MODEL, K, EXAMPLE, VARS),
    X is ++(jax.numpy.ones(4)),
    apply(MODEL, VARS, X, Y),
    shape(Y, [8])
)  # nv

Test("MLP via sequential then optax SGD step") <- (
    dense(8, FC1),
    dense(2, FC2),
    sequential([FC1, FC2], MODEL),
    key(0, K0),
    split_key(K0, 2, [K_INIT, _]),
    EXAMPLE is ++(jax.numpy.ones(4)),
    init(MODEL, K_INIT, EXAMPLE, VARS),
    XS is ++(jax.numpy.array([[1.0, 2.0, 3.0, 4.0]])),
    YS is ++(jax.numpy.array([[5.0, 6.0]])),
    LOSS_FN is ++(lambda v: jax.numpy.mean(
        (MODEL.apply(v, XS) - YS) ** 2)),
    value_and_grad(LOSS_FN, VARS, VG),
    VG is (_LOSS, GRADS),
    sgd(0.01, OPT),
    init_optimizer(OPT, VARS, STATE),
    update_optimizer(OPT, GRADS, STATE, UR),
    UR is (UPDATES, _),
    apply_updates(VARS, UPDATES, NEW_VARS)
)  # nv

Test("Dropout needs RNG at apply") <- (
    dropout(0.5, MODEL),
    key(0, K0),
    EXAMPLE is ++(jax.numpy.ones(4)),
    init(MODEL, K0, EXAMPLE, VARS),
    X is ++(jax.numpy.ones(4)),
    split_key(K0, 2, [_, K_DROP]),
    apply_with_rngs(MODEL, VARS, X, {"dropout": K_DROP}, Y),
    shape(Y, [4])
)  # nv

Test("max_pool halves spatial dims") <- (
    X is ++(jax.numpy.ones((1, 8, 8, 3))),
    max_pool(X, [2, 2], {"strides": ++((2, 2))}, R),
    shape(R, [1, 4, 4, 3])
)  # nv
```

---

## Tests

`tests/fixtures/jax_flax_tests.clausal`:

- Layer construction smoke (Dense, Conv, LayerNorm, Embed, RNN
  cell) — assert `init` returns a non-empty pytree
- `init` + `apply` round-trip on Dense, MLP-via-sequential
- `init_with_output` matches a separate `init` + `apply`
- `apply_with_rngs` for Dropout
- `apply_mutable` for BatchNorm — assert `(out, new_state)`
  decomposes
- Pooling functions: `max_pool`, `avg_pool` shape correctness
- End-to-end: MLP → loss → grad → optax step → params change
- Pytree predicates from Phase 9 work on `VARS` (`leaf(VARS, L)`,
  `tree_flatten(VARS, ...)`)
- `layer_class` registry has at least 30 entries

Python unit tests:
- Lazy-import behaviour
- `_pred` arities for representative predicates

---

## Docs

Create `docs/jax_flax.md`:

- Position vs Equinox — model and params separated, not a single
  pytree
- The init/apply discipline; when to use each variant
- Variables shape (`{params: ..., batch_stats: ...}`) and how Phase 9
  pytree predicates work on it
- Stateful layers: `apply_mutable` for BatchNorm
- Stochastic layers: `apply_with_rngs` for Dropout
- Pool functions vs layer Modules — different surface
- Custom Linen modules — currently `++()`-only
- Caveats from Issues

Update `implementation_plans/jax/overview.md`:
- Add Phase 18 row
- Move "Flax integration" from Deferred to Implemented
- Update Tier table
- Add `jax_flax.py` to submodule layout

---

## Issues

1. **Linen-only first pass; NNX deferred.** Flax has two APIs:
   **Linen** (the original — functional, explicit init/apply) and
   **NNX** (newer, mutable-state, more PyTorch-like). NNX wasn't
   present in `flax 0.12.7`'s top-level package; it landed in Flax
   0.10. Wrapping NNX requires a different state-threading
   discipline (mutable references, not explicit variables) and
   deserves its own phase plan. Track as **Phase 18b — Flax NNX**
   with a stub when scheduled.

2. **Custom user-defined modules are out of scope.** The heart of
   Flax is `class MyModel(nn.Module): @nn.compact def __call__(self,
   x): ...` — user-defined classes inheriting from `nn.Module`. We
   do **not** try to provide a Clausal-side way to define new
   modules. Users escape via `++()`:

   ```clausal
   MODEL is ++(define_my_model())
   init(MODEL, K, X, VARS)
   ```

   The wrapper covers the ~30 pre-built layers and the init/apply
   contract. Custom architecture is a future phase if a real
   caller needs it (would also need pytree node registration, see
   the cross-phase Deferred list).

3. **Variables structure varies by module.** A module with only
   trainable params has `{"params": {...}}`. With BatchNorm:
   `{"params": {...}, "batch_stats": {...}}`. With Dropout RNGs at
   apply: still just `{"params": ...}` — RNGs are per-call, not
   stored. Users learn to read the variables via Phase 9 pytree
   predicates. Documented but not abstracted.

4. **`BatchNorm` requires `mutable` apply.** Construction works
   stateless, but `apply(BN_MODEL, VARS, X, Y)` will fail —
   BatchNorm needs its `batch_stats` collection to be mutable
   during training. Use `apply_mutable(MODEL, VARS, X,
   ["batch_stats"], RESULT)`. Documented in `docs/jax_flax.md`
   prominently.

5. **Apply-time vs init-time RNGs.** Flax separates the init key
   (architecture-defining randomness, e.g. weight init) from
   apply-time keys (per-call randomness, e.g. dropout masks).
   `apply_with_rngs/5` takes an `{name: key}` dict matching
   Flax's `apply(..., rngs=...)` shape. Match Flax's convention
   exactly.

6. **`init` returns dict in modern Flax, not FrozenDict.** Older
   Flax versions returned `flax.core.FrozenDict`. 0.12+ returns a
   plain dict. The wrapper passes through whatever Flax returns —
   downstream code that pattern-matches on dict-likeness works
   either way. Pinned floor at flax 0.10 in pyproject.toml whenever
   JAX deps get pinned.

7. **`apply_updates` works as-is.** Just like Equinox, the
   gradients pytree from `value_and_grad(loss_fn, vars)` matches
   the structure of `vars`, and `py.jax_tree.apply_updates` adds
   them leaf by leaf. The Equinox-driven None-handling fix to
   `apply_updates` (commit 7bda6fc) carries over — no extra work
   needed.

8. **Module name shadowing.** `dense`, `conv`, `dropout`, `embed`,
   `sequential`, `init`, `apply` — none shadow Python stdlib
   symbols. `apply` was a Python 2 builtin removed in Python 3;
   `init` is a method-name convention, not a top-level callable.
   Users who want to disambiguate from other wrappers' similarly-
   named predicates use the module-qualified form
   (`flax.init`, `py.jax_flax.apply`).

9. **No `apply_module/3` sugar in this module.** Equinox has it
   because Equinox modules are callables (`M(X)` works directly).
   Flax modules are *not* callables outside of the `apply` context
   — calling `M(X)` on a freshly-constructed Linen module raises a
   "module unbound" error. The init/apply discipline IS the apply
   surface.

10. **Filter transforms not needed.** Equinox needed `filter_grad`
    etc. because Equinox models contain non-array leaves (Python
    functions for activations). Flax variables are *just* arrays
    (params / batch_stats are all arrays); plain `grad` / `vmap` /
    `jit` from Phase 12 work directly on them. So no
    `filter_*` siblings in `py.jax_flax`.

11. **Quantity awareness mostly N/A.** Same as Equinox — modules
    consume and produce arrays in dimensionless feature space.
    Quantity-tagged inputs would need per-layer propagator
    decisions; out of scope first pass.

12. **Pool ops as functions, not Modules.** Flax's `nn.max_pool`
    and `nn.avg_pool` are *functions*, not Modules — they don't
    need init/apply. We expose them as direct predicates
    (`max_pool/3,/4`) alongside the layer constructors. Make this
    visually distinct in docs so users don't try to feed them to
    `init`.

---

## Out of Scope

- **Flax NNX** — Phase 18b
- **Custom user-defined Linen modules** — Issue 2
- **`flax.training.train_state.TrainState`** — convenience class for
  bundling params + optimiser state; users build the equivalent
  with Phase 16 + Phase 9 predicates directly
- **`flax.serialization`** — Flax has its own serialisation; users
  who need it escape to `++()` or use `pickle` via stdlib. Wrap
  only if a real caller asks
- **`flax.struct.dataclass`** — Flax's pytree-dataclass helper;
  same territory as custom pytree node registration (Deferred
  cross-phase)

---

## Estimated Surface

| Category | Predicate count |
|---|---|
| Per-class layer constructors (~28 layers, 2 arities each) | ~28 names, ~56 arities |
| Init / apply variants | 5 |
| Pool functions | 2 (×2 arities = 4) |
| Layer-class registry | 1 |
| **Total predicate names** | ~36 |
| **Total registered arities** | ~66 |

Smaller than Phase 17 (Equinox: ~57 names, ~100 arities) — Flax
has fewer pre-built layers, no per-dimensionality conv split, and
no pooling Modules. The init/apply contract adds 5 predicates that
Equinox doesn't need (where Equinox's "model is its params" fuses
the two roles).
