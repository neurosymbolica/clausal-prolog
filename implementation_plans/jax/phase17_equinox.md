# Phase 17 — Equinox: Modules, Filter Transforms, Pytree Utilities

[Equinox](https://docs.kidger.site/equinox/) is the de-facto neural-net
library for JAX users who want models to *be* pytrees. An
`eqx.Module` is a JAX-registered dataclass: instantiate it once with
the right shapes and a PRNG key, then apply it like any callable.
Training is just gradient descent on the pytree.

This phase completes the JAX wrapper's NN story — Phase 9 (pytrees) +
Phase 10 (`jax_nn` activations/initializers) + Phase 12 (transforms) +
Phase 16 (optax) gave us params + losses + gradients + optimisers;
Equinox supplies the model-construction and filter-aware transform
layer that ties the rest together.

**File to create:** `clausal/modules/py/jax_equinox.py`

**Depends on:**
- Phase 1 — `_ensure_jax`, helpers
- Phase 2 — PRNG keys (every layer constructor takes one)
- Phase 9 — pytrees (`leaf`, `tree_flatten`)
- Phase 12 — function transforms (`jit_compile`, `grad_value` are the
  precedent for `filter_*` analogues)
- Phase 16 — optax (`apply_updates` overlaps; see Issue 4)

**External dependency:** `equinox` (lazy-imported via the same
`_ensure_*` pattern as `_ensure_jax`).

---

## Core Concepts

| Equinox concept | Clausal predicate | Notes |
|---|---|---|
| `eqx.Module` instance | First-class JAX value (a registered pytree) | Construct via `layer/3,/4`; apply via `apply_module/3` or `++(M(X))` |
| `eqx.nn.State` | First-class value (also a pytree) | Threaded via `apply_stateful_module/5` (see Issue 3) |
| Filter spec | Pytree of `bool` or callable | Passed to `partition/3` and `filter_*` |
| `(diff, static)` halves | A pair of pytrees | `partition` splits, `combine` rejoins |

Modules and states stay opaque (no inspection predicates beyond
`tree_flatten` / `leaf` from Phase 9). They flow through arguments;
attribute access uses `++()` when needed (e.g.
`++(model.weight)`).

---

## Predicates

### Layer construction (Tier 1 per-class constructors)

Each `eqx.nn.*` class gets its own predicate — lowercase snake_case
matching the rest of the JAX wrapper (`zeros`, `linspace`, `sgd`).
Constructor signature maps directly: positional args first, then any
required kwargs as a positional `OPTS` dict, then `KEY` last for
layers that need one.

**Layers needing a PRNG key** (positional-key arity ends with `KEY, M`):

| Predicate | Arity | Wraps | Required args |
|---|---|---|---|
| `linear` | `/4, /5` | `eqx.nn.Linear` | `in_features, out_features, [opts], key` |
| `mlp` | `/6, /7` | `eqx.nn.MLP` | `in_size, out_size, width_size, depth, [opts], key` |
| `conv` | `/5, /6` | `eqx.nn.Conv` | `num_spatial_dims, in_channels, out_channels, kernel_size, [opts], key` |
| `conv1d` / `conv2d` / `conv3d` | `/4, /5` | `eqx.nn.Conv1d` etc. | `in_channels, out_channels, kernel_size, [opts], key` |
| `conv_transpose` | `/5, /6` | `eqx.nn.ConvTranspose` | same shape as `conv` |
| `conv_transpose1d` / `2d` / `3d` | `/4, /5` | | same shape as conv variants |
| `embedding` | `/3, /4` | `eqx.nn.Embedding` | `num_embeddings, embedding_size, [opts], key` |
| `lstm_cell` | `/3, /4` | `eqx.nn.LSTMCell` | `input_size, hidden_size, [opts], key` |
| `gru_cell` | `/3, /4` | `eqx.nn.GRUCell` | `input_size, hidden_size, [opts], key` |
| `multihead_attention` | `/3, /4` | `eqx.nn.MultiheadAttention` | `num_heads, query_size, [opts], key` |
| `prelu` | `/2, /3` | `eqx.nn.PReLU` | `[init_alpha], [opts]` (key optional) |
| `spectral_norm` | `/3, /4` | `eqx.nn.SpectralNorm` | `layer, weight_name, [opts], key` |
| `weight_norm` | `/2, /3` | `eqx.nn.WeightNorm` | `layer, [opts]` |
| `rotary_positional_embedding` | `/2, /3` | `eqx.nn.RotaryPositionalEmbedding` | `embedding_size, [opts]` |

**Layers not needing a key** (no key arity):

| Predicate | Arity | Wraps |
|---|---|---|
| `layer_norm` | `/2, /3` | `eqx.nn.LayerNorm` |
| `group_norm` | `/3, /4` | `eqx.nn.GroupNorm` |
| `rms_norm` | `/2, /3` | `eqx.nn.RMSNorm` |
| `dropout` | `/2, /3` | `eqx.nn.Dropout` (inference-mode only — Issue 3) |
| `sequential` | `/2` | `eqx.nn.Sequential` (takes a list) |
| `identity` | `/1` | `eqx.nn.Identity` |
| `lambda_layer` | `/2` | `eqx.nn.Lambda` (renamed — `lambda` is reserved) |
| `shared` | `/2, /3` | `eqx.nn.Shared` |
| `pool` / `avg_poolNd` / `max_poolNd` | various | The pooling family |
| `adaptive_pool` / `adaptive_avg_poolNd` / `adaptive_max_poolNd` | various | Adaptive variants |

`OPTS` is a dict of optional constructor kwargs (e.g.
`{"use_bias": ++(False), "dtype": ++(jax.numpy.float64)}`). The
no-OPTS arity matches the all-defaults case; the OPTS arity unpacks
the dict as kwargs.

**Stateful classes deferred:** `BatchNorm`, `StateIndex`,
`StatefulLayer` are out of scope for this phase — see Issue 3.

```clausal
key(0, K0),
split_key(K0, 3, [K1, K2, K3]),
linear(4, 8, K1, FC1),
layer_norm(8, NORM),
linear(8, 1, K2, FC2),
sequential([FC1, NORM, FC2], MODEL),
apply_module(MODEL, INPUT, OUT)
```

### Layer enumeration registry (Tier 2 — fact table)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `layer_class` | `/2` | `(+N, -CLS)`, `(-N, -CLS)` | Enumerate all `eqx.nn.*` classes by name |

Side-channel for relational discovery — not the primary
construction path. Useful for users who want to introspect what
layer types Equinox supports without grepping the docs.

### Module application

| Name | Arity | Modes | Description |
|---|---|---|---|
| `apply_module` | `/3` | `(+M, +X, -Y)` | Apply a stateless module: equivalent to `++(M(X))` but deep-derefs `X` |
| `apply_module` | `/4` | `(+M, +X, +KWARGS, -Y)` | Apply with kwargs (e.g. `{"key": K}` for `Dropout`) |

### Filter transforms (Tier 1 pure)

Equinox's `filter_*` family handles pytrees containing non-array
leaves (Python functions, booleans, layers themselves). Same shape
as Phase 12, with filter semantics added.

| Name | Arity | Modes | Description |
|---|---|---|---|
| `filter_jit_compile` | `/2` | `(+F, -F2)` | `eqx.filter_jit(F)` |
| `filter_grad_value` | `/3` | `(+F, +X, -G)` | `eqx.filter_grad(F)(X)` |
| `filter_value_and_grad` | `/3` | `(+F, +X, -RESULT)` | `RESULT is (V, G)` |
| `filter_vmap_apply` | `/3` | `(+F, +X, -R)` | `eqx.filter_vmap(F)(X)` |
| `filter_vmap_apply` | `/4` | `(+F, +X, +OPTS, -R)` | OPTS for `in_axes`/`out_axes` |
| `filter_pmap_apply` | `/3, /4` | same | Parallel-map variant |

All take a filter spec implicitly (default: arrays differentiable,
everything else static). Custom filter specs come via the partition
predicates below.

### Partition / combine (Tier 1 pure, bidirectional)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `partition` | `/4` | `(+TREE, +FILTER, -DIFF, -STATIC)` | Split tree into differentiable / static halves |
| `combine` | `/3` | `(+DIFF, +STATIC, -TREE)` | Inverse of `partition` |

Bijection conceptually but implemented as two predicates because
backward mode doesn't need the filter spec. (Could collapse to a
single `partitioned/4` if we wanted to spend an arity on it; not
worth it given the asymmetry.)

### Tree-aware functional updates (Tier 1 pure)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `tree_at_set` | `/4` | `(+WHERE, +TREE, +REPLACE, -NEW_TREE)` | `eqx.tree_at(where, tree, replace=replace)` |
| `tree_at_apply` | `/4` | `(+WHERE, +TREE, +FN, -NEW_TREE)` | `eqx.tree_at(where, tree, replace_fn=fn)` |

`WHERE` is a Python callable returning the leaf(es) to replace,
typically `++(lambda m: m.weight)`. The two arities mirror optax's
`tx.update` two-shapes idea — pick the one that matches your access
pattern.

### Leaf check predicates (Tier 1 pure)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `is_array` | `/1` | `(+X)` | `eqx.is_array(X)` |
| `is_inexact_array` | `/1` | | Float / complex arrays only |
| `is_array_like` | `/1` | | Arrays + Python scalars |
| `tree_equal` | `/2` | `(+A, +B)` | `eqx.tree_equal(A, B) is True` |

Parallel to Phase 6's `has_nan` / `has_inf` / `all_finite`.

### Serialisation (Tier 4 — IO)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `serialise` | `/2` | `(+TREE, +PATH)` | `eqx.tree_serialise_leaves(path, tree)` |
| `deserialise` | `/3` | `(+PATH, +LIKE_TREE, -TREE)` | `eqx.tree_deserialise_leaves(path, like)` |

`PATH` is a string filesystem path. `LIKE_TREE` provides the
structure and dtypes for deserialisation — typically the freshly
constructed model with the same hyperparameters.

---

## Context and Reference Patterns

### Lazy import

```python
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
```

### Per-class layer constructors

Each layer is a thin `_pure` wrapper:

```python
def _enn():
    _ensure_equinox()
    import equinox.nn as _m
    return _m


# Key-required layers
linear = _pred("linear",
    (4, _pure(lambda inf, outf, key: _enn().Linear(inf, outf, key=key))),
    (5, _pure(lambda inf, outf, opts, key:
              _enn().Linear(inf, outf, key=key, **opts))),
)

mlp = _pred("mlp",
    (6, _pure(lambda i, o, w, d, key:
              _enn().MLP(i, o, w, d, key=key))),
    (7, _pure(lambda i, o, w, d, opts, key:
              _enn().MLP(i, o, w, d, key=key, **opts))),
)

# Key-not-required layers
layer_norm = _pred("layer_norm",
    (2, _pure(lambda shape: _enn().LayerNorm(shape))),
    (3, _pure(lambda shape, opts: _enn().LayerNorm(shape, **opts))),
)

dropout = _pred("dropout",
    (2, _pure(lambda p: _enn().Dropout(p, inference=True))),
    (3, _pure(lambda p, opts: _enn().Dropout(p, **opts))),
)
```

Pattern is mechanical — one entry per class. The full list lives in
the module file; the table above (under Predicates) is the
authoritative catalogue. `dropout/2` defaults `inference=True`
because non-inference Dropout needs state threading (Issue 3).

### Layer-class registry (enumeration only)

```python
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
```

The registry uses Equinox's TitleCase class names (`"Linear"`,
`"MLP"`) — it returns the actual class, not the wrapper predicate.
For construction, use the per-class predicates with snake_case names.

### Apply predicates

`eqx.Module` instances are first-class callables; `apply_module/3` is
sugar for `++(M(X))`:

```python
apply_module = _pred("apply_module",
    (3, _pure(lambda m, x: m(x))),
    (4, _pure(lambda m, x, kwargs: m(x, **kwargs))),
)
```

### Filter transforms

Mirror Phase 12 but route through `eqx.filter_*`:

```python
filter_grad_value = _pred("filter_grad_value",
    (3, _pure(lambda f, x: _eqx().filter_grad(f)(x))),
)

filter_value_and_grad = _pred("filter_value_and_grad",
    (3, _pure(lambda f, x: tuple(_eqx().filter_value_and_grad(f)(x)))),
)

filter_jit_compile = _pred("filter_jit_compile",
    (2, _pure(lambda f: _eqx().filter_jit(f))),
)
```

### Serialisation

`tree_serialise_leaves` writes to an open file or path. Wrap to
accept a path string:

```python
def _serialise(tree, path):
    _ensure_equinox()
    _eqx().tree_serialise_leaves(path, tree)
    return True   # `_pure` needs a unifiable result; True trivially unifies


serialise = _pred("serialise",
    (2, _pure(_serialise)),
)
```

`deserialise` returns the populated tree:

```python
deserialise = _pred("deserialise",
    (3, _pure(lambda path, like: _eqx().tree_deserialise_leaves(path, like))),
)
```

---

## Example Usage

```clausal
-import_module(jax)
-import_from(py.jax, [array, array_list, shape, allclose])
-import_from(py.jax_random, [key, split_key])
-import_from(py.jax_optax, [sgd, init_optimizer, update_optimizer])
-import_from(py.jax_tree, [apply_updates])             % NB: canonical home
-import_from(py.jax_equinox, [
    linear, mlp, layer_norm, sequential, layer_class,
    apply_module,
    filter_grad_value, filter_value_and_grad, filter_jit_compile,
    partition, combine, tree_at_set,
    is_array, tree_equal,
    serialise, deserialise
])
-import_module(equinox)

Test("Linear forward shape") <- (
    key(0, K),
    linear(4, 8, K, MODEL),
    X is ++(jax.numpy.ones(4)),
    apply_module(MODEL, X, Y),
    shape(Y, [8])
)  # nv

Test("MLP train one step with optax") <- (
    key(0, K0),
    split_key(K0, 2, [K_INIT, _]),
    mlp(2, 1, 4, 1, K_INIT, MODEL),
    XS is ++(jax.numpy.array([[1.0, 2.0], [3.0, 4.0]])),
    YS is ++(jax.numpy.array([[5.0], [6.0]])),
    LOSS_FN is ++(lambda m, xs, ys:
        jax.numpy.mean((jax.vmap(m)(xs) - ys) ** 2)),
    F is ++(lambda m: LOSS_FN(m, XS, YS)),
    filter_value_and_grad(F, MODEL, RESULT),
    RESULT is (_LOSS, GRADS),
    sgd(0.01, OPT),
    init_optimizer(OPT, MODEL, STATE),
    update_optimizer(OPT, GRADS, STATE, UPD_RES),
    UPD_RES is (UPDATES, _),
    apply_updates(MODEL, UPDATES, NEW_MODEL),
    not tree_equal(MODEL, NEW_MODEL)
)  # nv

Test("partition / combine round-trip") <- (
    key(0, K),
    linear(3, 5, K, MODEL),
    FILTER is ++(equinox.is_array),
    partition(MODEL, FILTER, DIFF, STATIC),
    combine(DIFF, STATIC, REBUILT),
    tree_equal(MODEL, REBUILT)
)  # nv

Test("layer_class registry exposes Linear and Conv2d") <- (
    layer_class("Linear", _),
    layer_class("Conv2d", _),
    layer_class("LayerNorm", _)
)  # nv
```

---

## Tests

`tests/fixtures/jax_equinox_tests.clausal`:

- Stateless layer construction: `Linear`, `MLP`, `LayerNorm`,
  `Sequential`, `Identity` — assert output shape matches expected
- `apply_module` on `Linear` and `MLP`
- `apply_module/4` with kwargs (e.g. `Dropout` with `key`)
- Filter transforms: `filter_grad_value` on a Linear loss,
  `filter_value_and_grad` tuple decomposition, `filter_jit_compile`
  produces a callable that returns the same value
- Partition / combine round-trip — `tree_equal` after rebuild
- `tree_at_set` mutates a single leaf and leaves the rest equal
- `is_array` / `is_inexact_array` / `is_array_like` discriminate
  correctly
- Serialise / deserialise round-trip — write to a tmp path, read
  back, `tree_equal` against the original
- End-to-end: construct an MLP, run one optax step, assert the model
  changed

Python unit tests (in `test_jax_infra.py`):
- Module imports cleanly (lazy-import test)
- All exports resolve
- `layer_class` registry has at least 40 entries (loose floor in
  case Equinox adds layers)

---

## Docs

Create `docs/jax_equinox.md`:

- Position relative to Phase 16 — Equinox provides the *model*; optax
  provides the *optimiser*; the two compose via the same pytree
- Layer registry vs. per-layer constructors — why the registry won
- Filter transforms — when to reach for `filter_grad_value` vs. plain
  `grad_value` (answer: when your tree contains non-array leaves —
  almost always for Equinox models)
- Partition / combine — typical use case is freezing parts of a model
- `tree_at_set` for surgical updates
- Serialisation
- Caveats from the Issues section

Update `implementation_plans/jax/overview.md`:
- Add Phase 17 row to the phases list
- Add Phase 17b row marked "Stateful Modules (deferred)" with link
  to a stub `phase17b_equinox_stateful.md`
- Move "Flax / Equinox integration" half (keep the Flax half for
  later) from Deferred to a new "✅ Implemented" row mentioning
  Equinox
- Update Tier table
- Add `jax_equinox.py` to the submodule layout

Pre-Phase-17 refactor (`apply_updates` lift):
- Edit `clausal/modules/py/jax_tree.py` to define the canonical
  `apply_updates/3`
- Edit `clausal/modules/py/jax_optax.py` to alias
  `apply_updates = _jax_tree.apply_updates`
- Update `docs/jax_optax.md` to point at `py.jax_tree.apply_updates`
  as canonical
- Update `docs/jax_tree.md` (or create section) to document the new
  predicate
- Update Phase 16 plan's training-loop section with the same
  redirect

---

## Issues

1. **Per-class layer constructors, not a registry.** Earlier draft
   collapsed all 43 `nn.*` classes through one `layer/3,/4` predicate
   backed by a string-name registry. Switched to per-class
   predicates (`linear`, `mlp`, `layer_norm`, …) because the
   call-site cost of the registry form
   (`layer("Linear", {"in_features": ...}, K, M)` plus runtime kwarg
   validation) outweighs the wrapper-side ease of a single
   dispatcher. Phase 10's `activation/2` registry exists because
   users genuinely *enumerate* activations; nobody enumerates layer
   types when building a model. `layer_class/2` survives as a
   discovery-only side channel.

2. **`apply_module/3` vs. just using `++(M(X))`.** Equinox modules
   are callables, so `++(M(X))` works without any wrapper. We expose
   `apply_module/3` as sugar for two reasons: (a) it deep-derefs `X`
   (lists/dicts containing Vars resolve correctly), and (b) it
   makes module application pattern-visible in code. Cost is one
   extra predicate; benefit is consistency with Phase 10
   `relu_apply` etc.

3. **Stateful modules (`BatchNorm`, training-mode `Dropout`)
   tracked as Phase 17b.** Equinox 0.13's `eqx.nn.State` returns a
   separate pytree of state alongside the module; you call
   `eqx.nn.make_with_state(Model)(args)` to get `(model, state)`,
   then `model(x, state)` returns `(y, new_state)`. Wrapping this
   needs a paired `make_stateful_layer/5` constructor and an
   `apply_stateful_module/5` apply predicate (state in, state out).
   Phase 17 ships stateless-only — `Dropout` defaults to
   `inference=True`. Phase 17b is the named home for the stateful
   surface: its scope is `BatchNorm`, `StateIndex`, `StatefulLayer`,
   training-mode `Dropout`, and the `make_with_state` /
   `apply_stateful_module` pair (~6 predicates). Listed in
   `overview.md`'s phase table as "Phase 17b — Stateful Modules
   (deferred)" with a placeholder `phase17b_equinox_stateful.md` to
   capture details when scheduled.

4. **`apply_updates` lifted to `py.jax_tree`.** Both
   `optax.apply_updates` and `eqx.apply_updates` are pure pytree
   operations (`tree_map(lambda p, u: p + u, params, updates)`),
   not optimiser- or NN-specific. Pre-Phase-17 refactor: define the
   canonical predicate in `py.jax_tree`, alias from `py.jax_optax`
   for backwards compatibility (same Phase-11 `logsumexp` pattern),
   and don't expose from `py.jax_equinox`. Outcome: equinox never
   has to import from optax, and there's exactly one
   implementation. Touches `clausal/modules/py/jax_tree.py`,
   `clausal/modules/py/jax_optax.py`,
   `tests/fixtures/jax_optax_tests.clausal` (only if test imports
   need updating; the alias preserves the old import path so they
   may not), `docs/jax_optax.md`, `docs/jax_tree.md`, and the
   Phase 16 plan.

5. **`tree_at`'s `where` arg is a Python callable.** The natural
   Clausal-side construction is `++(lambda m: m.weight)`, which
   captures attribute access at trace time. Easy to construct,
   awkward to enumerate. We don't try to provide a path-list version
   — Equinox's design genuinely is "pass a callable returning the
   leaves you want." Documented prominently.

6. **Filter spec construction.** The `+FILTER` arg in
   `partition/4` is a pytree of `bool` or callables. Common values:
   `++(eqx.is_array)`, `++(eqx.is_inexact_array)`, or an explicit
   pytree mirroring the model with `True` / `False` at each leaf.
   The wrapper passes whatever is given; we don't try to construct
   filter specs ourselves. Examples in `docs/jax_equinox.md`.

7. **Filter transforms vs. Phase 12 transforms.** They share a name
   space (`grad_value` vs. `filter_grad_value`) and almost the same
   shape. We do *not* try to merge them — Equinox users want filter
   semantics by default; raw-JAX users want non-filter semantics by
   default. Two distinct names is clearer than one with a switch.

8. **Serialisation is Tier 4 IO.** Touches the filesystem.
   `serialise/2` returns `True` (the only "value" worth unifying
   against), making it backtracking-unsafe — re-serialising on
   redo will overwrite the file silently. Documented as
   side-effecting; users should commit serialisation at end-of-loop
   and not inside a search.

9. **PRNG key in OPTS dict, not standalone.** Considered passing
   the key as a separate kwarg in OPTS (`{"key": K, ...}`). Rejected
   because Equinox itself accepts the key as a *keyword-only* arg —
   matching the wrapper to its surface. The `/4` arity exists so
   the key never gets confused with a regular hyperparameter.

10. **Quantity awareness mostly N/A.** Modules consume and produce
    arrays in dimensionless feature space. The exception is
    something like `Linear(in, out)` applied to a quantity-tagged
    array — the propagator would have to track that the weights are
    dimensionless and the output inherits the input's dimension.
    Treat as out-of-scope first pass; users wanting unit-aware
    layers escape to `++()`.

11. **Equinox version pinning.** Equinox 0.13 is the development
    target. The `nn.State` API stabilised in 0.11; layer constructor
    signatures haven't changed since 0.10. Floor at 0.11 in
    pyproject.toml (whenever JAX deps get pinned generally).

12. **Module name shadowing.** `layer`, `partition`, `combine`,
    `serialise`, `deserialise`, `is_array`, `tree_equal` — none
    shadow Python stdlib symbols. `combine` is in `itertools`-adjacent
    territory but Python doesn't have `combine` in stdlib. Clean.

---

## Out of Scope

- **Stateful modules** — Phase 17b (Issue 3)
- **Custom `eqx.Module` subclassing from Clausal** — would need a
  bridge for Clausal-side dataclass-like terms; Phase 9-style pytree
  registration territory
- **`eqx.error_if` / `eqx.debug.breakpoint_if`** — niche; defer
- **`eqx.Enumeration` / `eqx.AbstractClassVar`** — implementation
  detail; not user-facing
- **Flax integration** — separate phase (Flax has different
  conventions: explicit `init` / `apply`, mutable state collections)

---

## Estimated Surface

| Category | Predicate count |
|---|---|
| Per-class layer constructors (~40 stateless classes, 2 arities each) | ~40 names, ~80 arities |
| Layer-class registry | 1 |
| Module application | 1 (with 2 arities) |
| Filter transforms | 5 (~7 arities with opts variants) |
| Partition / combine | 2 |
| Tree updates (`tree_at_*`) | 2 |
| Leaf checks + `tree_equal` | 4 |
| Serialisation | 2 |
| **Total predicate names** | ~57 |
| **Total registered arities** | ~100 |

Larger than Optax's 50 names, mostly because every `nn.*` class gets
its own predicate. The trade-off is intentional: per-call ergonomics
matter more than wrapper-side line count.
