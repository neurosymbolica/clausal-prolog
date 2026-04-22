# JAX Wrapper — Overview

JAX is a numerical computing library that combines NumPy-style array
programming with composable function transformations — `jit`, `grad`,
`vmap`, `pmap` — and sharded execution across accelerators. Unlike
PyTorch (which is stateful by default and has a stateful autograd graph
attached to tensors), **JAX is functional by design**: arrays are
immutable, randomness is carried as explicit PRNG keys, and
differentiation is a function transform rather than a tensor property.

That functional bias is a gift for a relational wrapper. Where the
PyTorch plan had to carve out "the training loop stays impure",
the JAX plan has almost none of that — state threading is the library's
own convention, not a concession we impose.

The wrapper strategy: wrap JAX's functional surface as pure predicates,
treat PRNG key splitting and sharded placement as explicit state threading,
expose pytrees as first-class enumerables, and let function transforms
(`grad`, `jit`, `vmap`) compose with Clausal through small relational
shims.

## Phases

- [Phase 1 — Array Core](phase1_array_core.md) ✅ **Implemented**: creation, properties, math, shape ops, conversions
- [Phase 2 — PRNG Keys and Randomness](phase2_random.md) ✅ **Implemented**: `key/1`, `split_key/2`, `fold_in/3`, samplers
- [Phase 3 — Functional Updates (`.at`)](phase3_functional_updates.md) ✅ **Implemented**: `at_set`, `at_add`, `at_mul`, `at_get` as pure predicates
- [Phase 4 — Linear Algebra](phase4_linalg.md) ✅ **Implemented**: `det`, `inv`, `solve`, `svd`, `eig`, `eigh`, `cholesky`, `qr`, `norm`, `pinv`
- [Phase 5 — FFT](phase5_fft.md) ✅ **Implemented**: `fft_transform`, `real_fft`, `fft_shift`, `fft_frequencies` — bijective pairs
- [Phase 6 — Comparisons and Selection](phase6_comparisons.md) ✅ **Implemented**: `eq`, `gt`, `where`, `allclose`, logical ops, `masked_select`, `take`, `put_along_axis`
- [Phase 7 — Einsum and Advanced Math](phase7_advanced_math.md) ✅ **Implemented**: `einsum`, `logarithm`, `sine`/`cosine`/`tangent` (bijective), `sqrt`, `pow`, `atan2`, `sinh`/`cosh`/`tanh`, `sigmoid`, `softmax`, `log_softmax`, `logsumexp`, `floor`/`ceil`/`round`/`sign`, `cumsum`, `cumprod`
- [Phase 8 — Shape Extras](phase8_shape_extras.md) ✅ **Implemented**: `partition` (bidirectional, subsumes `split` + narrow use of `concatenate`), `array_split`, `hsplit`, `vsplit`, `dsplit`, `tile`, `repeat`, `flip` (bidirectional), `roll`, `pad`. Also merges `stack`+`unstack` into the bidirectional `stacked/3` (replacing Phase 1's `stack/3`).
- [Phase 9 — Pytrees](phase9_pytrees.md) ✅ **Implemented**: `leaf/2`, `leaf_with_path/3`, `tree_flatten/3` (bijective), `tree_structure`, `tree_leaves_list`, `all_leaves`, `treedef_is_leaf`, `tree_map`, `tree_map_n`, `tree_reduce`, `keystr` — in `py.jax_tree`
- [Phase 10 — Neural-Net Activations and Initializers](phase10_nn.md) ✅ **Implemented**: `activation/2` and `initializer/2` registries, `init_array/4,/5`, applied activations (`relu_apply`, `gelu_apply`, `leaky_relu_apply`, `one_hot`, etc.) — in `py.jax_nn`
- [Phase 11 — jax.scipy Special and Stats](phase11_scipy.md) ✅ **Implemented**: 22 special functions (`gamma_fn`, `gammaln`, `erf`, `expit`, `i0`, `logsumexp`, `beta_fn`, `polygamma`, …), `distribution/2` registry (23 distributions), and per-method predicates `pdf`/`logpdf`/`cdf`/`logcdf`/`sf`/`logsf`/`ppf`/`pmf`/`logpmf` — in `py.jax_scipy`
- [Phase 12 — Function Transforms](phase12_transforms.md) ✅ **Implemented**: `grad_value`, `value_and_grad`, `jvp_value`, `vjp_value`, `jacobian`/`jacfwd`/`jacrev`, `hessian`, `vmap_apply`/`pmap_apply`, `jit_compile`, `make_jaxpr`, `eval_shape` — in `py.jax_transforms`
- [Phase 13 — Sharding and Devices](phase13_sharding.md) ✅ **Implemented**: `jax_device`/`local_device` enumeration, `device_count`/`local_device_count`, `device_id`, `device_platform`, `device_of`, `make_mesh` + mesh inspection, `partition_spec`, `named_sharding`, `single_device_sharding`, `sharding` + `device_put`, check predicates (`is_committed`, `is_fully_addressable`, `is_deleted`) — in `py.jax_sharding`
- [Phase 14 — Creation Variants and Arithmetic Gaps](phase14_creation_arith.md) ✅ **Implemented**: `zeros_like`, `ones_like`, `full_like`, `empty`, `logspace`, `geomspace`, `meshgrid`, `diag`, `identity`, `sub`, `div`, `floor_div`, `mod`, `neg`, `reciprocal`
- [Phase 15 — Statistics and Selection](phase15_stats_selection.md) ✅ **Implemented**: `median`, `std`, `var`, `percentile`, `quantile`, `cov`, `corrcoef`, `argmin`, `argmax`, `sort`, `argsort`, `topk`, `nonzero`, `unique`, `argpartition`
- [Phase 16 — Optax (Optimisers, Schedules, Losses)](phase16_optax.md) ✅ **Implemented**: optimiser constructors (`sgd`, `adam`, `adamw`, …), gradient transforms (`chain`, `clip_by_global_norm`, `ema`, `scale_by_schedule`, …), schedules (`cosine_decay_schedule`, `warmup_cosine_decay_schedule`, …), training-loop trio (`init_optimizer`, `update_optimizer`, `apply_updates`), loss functions (`softmax_cross_entropy`, `huber_loss`, …) — in `py.jax_optax`. `apply_updates` lives canonically in `py.jax_tree` since it's a pure pytree op.
- [Phase 17 — Equinox (Models, Filter Transforms)](phase17_equinox.md) ✅ **Implemented (stateless surface)**: ~33 per-class layer constructors (`linear`, `mlp`, `conv2d`, `layer_norm`, `multihead_attention`, …), `apply_module`, filter transforms (`filter_grad_value`, `filter_value_and_grad`, `filter_jit_compile`, `filter_vmap_apply`, …), `partition`/`combine`, `tree_at_set`/`tree_at_apply`, leaf checks (`is_array`, `tree_equal`, …), `serialise`/`deserialise`, `layer_class` discovery registry — in `py.jax_equinox`
- [Phase 17b — Equinox Stateful Modules](phase17b_equinox_stateful.md) ⏸ **Deferred**: `BatchNorm`, training-mode `Dropout`, `StateIndex`, `StatefulLayer`, `make_with_state`, `apply_stateful_module`. Promote to a full plan when a real caller surfaces.

---

## Core Abstractions

JAX exposes five major surfaces, each with its own central concept:

### `jax.Array` — Immutable Multidimensional Array

The fundamental data type. Every array operation is pure: operations take
arrays in and produce new arrays out. There are no in-place mutations,
no attached autograd graph, no `requires_grad` flag.

- **Lifecycle:** create -> compute -> query properties -> extract data
- **Purity:** fully pure. `x = jnp.ones([3]); y = x + 1` never mutates `x`.
  `.at[i].set(v)` returns a new array — the original is untouched.
- **Key insight:** A `jax.Array` is characterised by data, shape, dtype,
  device, and sharding. These five properties are the natural predicate
  vocabulary. Compare to PyTorch, where `requires_grad` was a sixth
  property and mutation a constant hazard.

### `PRNGKey` — Explicit Random State

JAX refuses to hide randomness in a global: every sampler requires a
`PRNGKey`, and consuming a key forces the caller to split it first. This
is the same state-threading discipline Clausal expects from stateful
operations, straight out of the box.

- **Lifecycle:** `key(SEED, K0)` -> `split_key(K0, [K1, K2])` ->
  `normal(K1, SHAPE, ARR)` -> backtracking abandons `K1` and `ARR` together,
  leaving `K0` valid
- **Purity:** pure with explicit state threading — the `PRNGKey` flows
  through arguments the same way a difference list does
- **Key insight:** JAX already made the decision that pairs well with
  backtracking. There is no hidden global generator to worry about.

### Pytree — Structured Nested Containers

JAX operates on arbitrary nested containers (dicts, lists, tuples,
dataclasses) as long as they bottom out in arrays. This structure is
called a **pytree**, and `tree_flatten` / `tree_unflatten` is a strict
bijection: leaves + treedef <-> original structure.

- **Lifecycle:** build a pytree from model params / batches -> transform
  with `tree_map` / `tree_flatten` -> pass to a JAX function
- **Purity:** fully pure. Pytrees are plain Python containers; JAX just
  knows how to walk them.
- **Key insight:** pytrees are the natural fit for `findall`, relational
  enumeration, and bijective `tree_flatten` as a single predicate.

### Function Transforms — `grad`, `jit`, `vmap`, `pmap`

JAX exposes higher-order function transforms. `grad(f)` is a function
that returns a function; `jit(f)` returns a compiled version of `f`;
`vmap(f)` vectorises `f` over a new axis. Composable and pure.

- **Lifecycle:** take a Python (or Clausal-embedded) function ->
  transform it -> call the transformed function
- **Purity:** the transforms are pure. Evaluating a grad / vmap / jit of
  the same function with the same inputs produces the same outputs.
- **Key insight:** Clausal users typically want the *result* of a
  transform, not the transform itself. Wrap as one-shot predicates:
  `grad_value(F, X, G)` computes `jax.grad(f)(x)` and unifies `G`.

### Sharding — Devices and Meshes

JAX makes sharding explicit: an `Array` can have a `sharding` attribute
describing its distribution across devices. Meshes name logical axes;
`PartitionSpec` maps tensor dims to those axes.

- **Lifecycle:** enumerate `devices()` -> build a `make_mesh(...)` ->
  construct a `NamedSharding(mesh, P(...))` -> `device_put(ARR, SHARDING, OUT)`
- **Purity:** pure, modulo the fact that `device_put` may physically
  copy data. The resulting `Array` is still immutable.
- **Key insight:** sharding is data — meshes and partition specs are
  first-class values, enumerable and queryable.

---

## Bijective Relationships

### Strict bijections (both directions computable)

| Procedural pair | Predicate | Notes |
|---|---|---|
| `jnp.asarray(np_arr)` / `np.asarray(jax_arr)` | `jax_numpy(JARR, NPARR)` | Zero-copy when possible |
| `jnp.array(list)` / `arr.tolist()` | `array_list(ARR, LIST)` | Copies data |
| `jnp.fft.fft(x)` / `jnp.fft.ifft(y)` | `fft_transform(SIGNAL, FREQ)` | Complex FFT pair |
| `jnp.fft.rfft(x)` / `jnp.fft.irfft(y, n)` | `real_fft(SIGNAL, FREQ)` | Needs original length — pass opts |
| `jnp.fft.fftshift(x)` / `jnp.fft.ifftshift(y)` | `fft_shift(X, Y)` | Inverse shifts |
| `jnp.exp` / `jnp.log` | `logarithm(EXP, VAL)` | Bidirectional |
| `jnp.sin` / `jnp.arcsin` | `sine(ANGLE, VALUE)` | Partial (range limited) |
| `jnp.cos` / `jnp.arccos` | `cosine(ANGLE, VALUE)` | Partial |
| `jnp.tan` / `jnp.arctan` | `tangent(ANGLE, VALUE)` | Partial |
| `jtu.tree_flatten(t)` / `jtu.tree_unflatten(td, ls)` | `tree_flatten(TREE, TREEDEF, LEAVES)` | Strict |
| `jnp.linalg.inv(A)` | `inv(A, B)` | Self-inverse: `inv(inv(A)) == A` |
| `arr.T` / `arr.T` | `transpose(A, B)` | Self-inverse |
| `jnp.flip(a)` / `jnp.flip(a)` | `flip(A, R)` / `flip(A, AXIS, R)` | Self-inverse |
| `jnp.stack(ls, axis)` / `jnp.unstack(a, axis)` | `stacked(LS, AXIS, A)` | Bidirectional along `AXIS` |
| `jnp.split(a, n)` / `jnp.concatenate(ls, axis)` | `partition(A, N_OR_IDX, LS)` / `(A, N_OR_IDX, AXIS, LS)` | Bidirectional; `concatenate/3` stays for arbitrary-piece joins |
| `jr.key(seed)` / `jr.key_data(k)` | `key_bytes(KEY, BYTES)` | Bidirectional |

### Multi-mode property queries (query or constrain)

| Property | Predicate | Modes |
|---|---|---|
| `arr.shape` | `shape(ARR, SHAPE)` | `(+,-)` query, `(+,+)` check |
| `arr.dtype` | `dtype(ARR, DTYPE)` | `(+,-)` query, `(+,+)` check |
| `arr.device` | `device(ARR, DEVICE)` | `(+,-)` query, `(+,+)` check |
| `arr.sharding` | `sharding(ARR, SHARDING)` | `(+,-)` query, `(+,+)` check |
| `arr.ndim` | `dim(ARR, N)` | `(+,-)` query, `(+,+)` check |
| `arr.size` | `element_count(ARR, N)` | `(+,-)` query |

### Enumerables (nondeterministic via backtracking)

| Collection | Predicate | Yields |
|---|---|---|
| `jtu.tree_leaves(tree)` | `leaf(TREE, LEAF)` | Each leaf, in traversal order |
| `jtu.tree_leaves_with_path(tree)` | `leaf_with_path(TREE, PATH, LEAF)` | Leaf with key-path |
| `jax.devices()` | `jax_device(DEVICE)` | Each available device |
| `jax.local_devices()` | `local_device(DEVICE)` | Each locally-addressable device |
| Pytree subtree | `subtree(TREE, PATH, SUBTREE)` | Each subtree along a path |

### Registry fact tables

| Registry | Predicate | Source |
|---|---|---|
| Activations | `activation(NAME, FN)` | `jax.nn` module |
| Initializers | `initializer(NAME, FACTORY)` | `jax.nn.initializers` |
| Distributions | `distribution(NAME, MODULE)` | `jax.scipy.stats` submodules |
| Samplers | `sampler(NAME, FN)` | `jax.random` samplers |
| Dtypes | `dtype_info(DTYPE, KEY, VALUE)` | `jax.dtypes` + `jnp.finfo/iinfo` |

---

## Purity Analysis

### Pure (backtracking-safe)

- **Array math:** all `jax.numpy` arithmetic, reductions, comparisons,
  shape operations, type conversions. JAX's API is designed so none of
  these mutate.
- **Functional updates:** `arr.at[idx].set(v)` / `.add(v)` / `.mul(v)` /
  `.get()` — all return new arrays. Wrapped as `at_set/4`, `at_add/4`,
  etc.
- **Linalg, FFT, scipy.special:** all pure.
- **Pytree operations:** `tree_flatten`, `tree_unflatten`, `tree_map` —
  pure functions over pure data.
- **PRNG operations:** `key`, `split`, `fold_in`, and all samplers. They
  are pure given an input key.
- **Function transforms:** `grad`, `vmap`, `jit`, `jvp`, `vjp`. The
  transforms themselves are pure functions of functions.

### State-threaded (explicit, naturally relational)

- **PRNG:** every sampler consumes a key. The convention is
  `key_next(KEY0, KEY1)` or more commonly `split_key(KEY0, N, KEYS)`.
  Samplers are `normal(KEY, SHAPE, ARR)` — consume the key, produce the
  array. If backtracking abandons `ARR`, `KEY0` stayed valid; nothing was
  mutated.
- **Device placement:** `device_put(ARR, SHARDING, OUT)` produces a new
  array; old array still valid.

### Constraint-like

Largely absent from JAX. `jax.lax.while_loop` and `cond` are control
flow, not constraints. If anything constraint-like lives in JAX, it is
shape-polymorphism (`jax.numpy.shape_as_value`, `eval_shape`), and we
punt on shapes-as-constraints same as the PyTorch plan did.

### Impure

Almost nothing. A handful of entry points to accelerator control:
- `jax.device_put_replicated` — allocates on multiple devices
- `jax.clear_caches()` — clears JIT caches
- `jax.block_until_ready(arr)` — forces completion (affects timing,
  not values)

These stay as `++()` or thin impure wrappers documented as such.

---

## Why JAX Is Easier to Wrap Than PyTorch

1. **No in-place operations.** PyTorch has `add_`, `mul_`, `scatter_`
   everywhere; JAX has none. The wrapper never has to choose between
   "functional" and "in-place" variants.
2. **No `requires_grad` attribute.** Differentiation is `jax.grad(f)`,
   not `tensor.requires_grad = True`. The array predicate vocabulary is
   smaller.
3. **No optimizer state machine.** Optax (the de-facto JAX optimizer
   library) is functional: `opt_state = tx.update(grads, opt_state,
   params)`. State threading is already the idiom. If we later wrap
   Optax, the wrapping maps one-to-one.
4. **Explicit PRNG.** Where PyTorch sampling from a hidden generator
   ruins backtracking (the generator advances!), JAX sampling is pure
   given a key.
5. **Pytrees.** Relational enumeration has a first-class home.
6. **Immutable devices and shardings.** A `jax.Array` carries its
   sharding as a value; wrappers can query and constrain it without
   worrying about mutation.

The PyTorch plan devoted an entire section to "the training loop stays
as `++()`" because GPU mutation is intractable for backtracking. JAX has
no equivalent carve-out.

---

## Tier Classification

| Tier | Operations |
|---|---|
| **1 — Pure** | All `jnp` math, shape ops, type conversions, `.at` updates, linalg, FFT, activations, pytree ops, samplers, transforms, optax optimisers/schedules/transforms/losses, Equinox layer constructors / filter transforms / partition / combine / tree_at / leaf checks |
| **2 — Fact tables** | Activation registry, initializer registry, distribution registry, sampler registry, dtype catalogue, device enumeration, optax `optimizer`/`schedule`/`gradient_transform`/`loss_function` registries, Equinox `layer_class` registry |
| **3 — State-threaded** | PRNG keys (`split_key`), device placement (`device_put`), optax training loop (`init_optimizer`/`update_optimizer`). No handles — JAX values are first-class. (Equinox stateful modules — `BatchNorm`, training-mode `Dropout`, `eqx.nn.State` — land in Phase 17b.) |
| **4 — IO/Impure** | `clear_caches`, `block_until_ready`, `jax.distributed` initialization, Equinox `serialise`/`deserialise`. Stay as `++()` for the JAX ones; the Equinox IO predicates are wrapped but documented as not backtracking-safe. |

Note the absence of a handle tier: JAX has no persistent stateful objects
like PyTorch's `nn.Module` or `optim.Optimizer`. The closest thing is a
`Mesh`, but that's a plain value.

---

## Scope

### In scope (Phases 1-11)

**Array core** — creation, math, shape, properties, conversions,
functional updates. ~40 predicates covering daily usage.

**PRNG** — keys, splitting, samplers. ~15 predicates. Natural fit for
state threading; the most PyTorch-unlike area.

**Pytrees** — leaf enumeration, flatten/unflatten, `tree_map`,
`tree_structure`. ~8 predicates. JAX's superpower; Clausal's
enumeration gets it for free.

**Linalg, FFT, comparisons, advanced math, shape extras** — the same
"math library wrapping" surface as PyTorch, but easier because no
`requires_grad` and no device-mutation hazards.

**jax.nn** — activations and initializers as registries.

**jax.scipy** — special functions and the distribution shapes — overlaps
with the scipy wrappers, same as PyTorch, split by data type.

### In scope with care (Phases 12-13)

**Function transforms** — `grad`, `value_and_grad`, `jit`, `vmap`, `pmap`,
`jvp`, `vjp`. The challenge: these operate on *functions*, and Clausal
predicates are first-class enough that we can wrap a Clausal predicate
as a JAX-compatible Python callable. Start with the one-shot form —
`grad_value(F, X, G)` computes and unifies.

**Sharding** — mesh construction, device enumeration, `device_put`,
sharding queries. Useful for relational reasoning about distributed
arrays ("find a sharding where dim 0 is on axis 'data'").

### Out of scope (stay as `++()`)

**`jax.experimental.*`** — unstable APIs, pace changes too fast.

**`jax.lib`, `jax.interpreters`** — compiler internals.

**`jax.distributed`** — multi-host initialization.

**JIT cache management.** Side-effecting.

### Deferred

**Custom pytree node registration.** `jtu.register_pytree_node` extends
the pytree system with user types. Useful, but requires design work on
how Clausal-side classes round-trip.

**Shape-polymorphic constraints.** Using Clausal's solver infrastructure
to reason about JAX shapes. Research project.

**Flax integration.** Neural-network library built on JAX. Flax is
functional (pytree of params), with explicit `init` / `apply` and
mutable state collections. Maps cleanly onto the pytree phase but
has different conventions from Equinox (Phase 17). Worth a wrapper
plan of its own.

---

## Overlap with scipy / torch

JAX's `jax.numpy.linalg`, `jax.numpy.fft`, `jax.scipy.special`, and
`jax.scipy.stats` cover nearly the same ground as the existing scipy
wrappers (and PyTorch's equivalents). The split is the same as PyTorch:
different data types, users pick based on their arrays.

| JAX Phase | Overlaps with |
|---|---|
| Phase 4 (linalg) | `scipy_linalg.py`, `torch.py` linalg — all three implement `det`/`inv`/`solve`/`svd`/`cholesky`/`qr`/`norm` |
| Phase 5 (FFT) | `scipy_fft.py`, `torch.py` FFT — similar bijective shape |
| Phase 7 (advanced math) | `scipy_special.py`, `torch.py` math |
| Phase 10 (nn) | `torch_nn.py` activations — JAX has no nn.Module so we only share the activation registry |
| Phase 11 (scipy stats) | `scipy_stats.py`, `torch_distributions.py` — same distribution-shape |

The naming convention matches JAX's own: lowercase snake_case for
functions (`linalg.inv`, `fft.fft`, `scipy.special.gammaln`), atom names
for registry keys (`"relu"`, `"normal"`, `"glorot_uniform"`).

---

## Naming Strategy

Following the **least surprise for library users** principle, JAX
predicates use the library's own names. JAX itself is consistent with
NumPy/SciPy lowercase conventions, so there is no TitleCase/lowercase
split like scipy-vs-PyTorch produced.

| Element | Convention | Example |
|---|---|---|
| Predicate names | JAX's own names, lowercase | `linspace`, `dot`, `gradient`, `gammaln` |
| Registry atom keys | JAX's string names | `"relu"`, `"normal"`, `"glorot_uniform"` |
| Module path | `py.jax*` with submodule suffixes | `py.jax`, `py.jax_random`, `py.jax_scipy` |
| Dtype constants | JAX's dtype objects | `float32`, `float64`, `int32`, `bfloat16` |
| Exported helpers | snake_case | `zeros_like`, `value_and_grad` |

### Predicates that collapse bijective pairs

Where JAX has two functions that are inverses, the wrapper provides one
multi-mode predicate with a **noun name**, not a verb:

| JAX functions | Clausal predicate |
|---|---|
| `jnp.exp(x)` / `jnp.log(y)` | `logarithm(EXP, VAL)` |
| `jnp.sin(x)` / `jnp.arcsin(y)` | `sine(ANGLE, VALUE)` |
| `jnp.fft.fft(x)` / `jnp.fft.ifft(y)` | `fft_transform(SIGNAL, FREQ)` |
| `jnp.asarray(np_arr)` / `np.asarray(jax_arr)` | `jax_numpy(JAX_ARR, NP_ARR)` |
| `jtu.tree_flatten(t)` / `jtu.tree_unflatten(td, ls)` | `tree_flatten(TREE, TREEDEF, LEAVES)` |

This follows the PyTorch precedent (`tensor_numpy`, `tensor_list`,
`logarithm`, `sine`).

### Clashes with the JAX module name

`-import_from(py.jax, [...])` registers a Clausal module under the name
`jax`, which shadows `-import_module(jax)`. Mitigate by exporting
commonly-used JAX constants (dtypes, `float32`/`float64`/etc.,
`newaxis`) directly from `py.jax` via `__getattr__`, same as PyTorch.

### Python builtins

`any`, `all`, `sum`, `max`, `min`, `round`, `abs` — these match JAX's
own API and shadow Python builtins at the Clausal module level, same as
PyTorch. Module-scoped imports prevent collision in user code.

---

## Minimising `++()` Escapes

Everything Checklist H calls for, applied to JAX:

### Export library constants

From `py.jax` via `__getattr__`, export:
- Dtypes: `float16`, `float32`, `float64`, `bfloat16`, `int8`, `int16`,
  `int32`, `int64`, `uint8`, `uint16`, `uint32`, `uint64`, `bool_`,
  `complex64`, `complex128`
- Newaxis / indexing sentinels: `newaxis`
- Mathematical constants: `pi`, `e`, `inf`, `nan`

From `py.jax_random`, export sampler atoms: `"normal"`, `"uniform"`,
`"bernoulli"`, etc. as strings for the registry.

From `py.jax_sharding`, export `PartitionSpec` constructor helpers —
but `P("x", "y")` already works as a value, so we expose it as
`partition_spec/2` with an explicit predicate.

### String representations for non-comparable objects

- `device(ARR, DEV)` returns a string (`"cpu:0"`, `"gpu:0"`) rather than
  a `Device` object — strings unify, compare, and pattern-match.
- `sharding(ARR, REPR)` returns a string representation (`repr(sharding)`)
  for equality checks; use `NamedSharding` construction predicates for
  building new ones.
- `dtype(ARR, DT)` — JAX dtypes do compare sensibly with `==`, so keep
  them as objects. Constants are exported by name.

### Check predicates for boolean properties

- `is_committed(ARR)` — `arr.committed` check
- `is_fully_addressable(ARR)` — `arr.is_fully_addressable`
- `is_deleted(ARR)` — `arr.is_deleted`
- `has_nan(ARR)`, `has_inf(ARR)`, `all_finite(ARR)` — numeric checks
  following the PyTorch precedent

Never `++(arr.committed)` — `++()` in goal position is a silent no-op,
a trap already documented in the PyTorch overview's Design Notes.

### Module name shadowing

Document that `-import_from(py.jax, ...)` shadows `-import_module(jax)`.
Users who need both write:

```clausal
-import_module(jax)                # keep Python jax available via ++()
-import_from(py.jax, [zeros, ones, shape])   # Clausal predicates
```

Since the predicates are the 80% use case, the shadowing is usually
acceptable. Exported constants cover most escapes.

---

## Quantity (Units) Awareness

Follow the same `make_quantity_aware()` pattern from
`clausal/modules/py/_scipy_units.py`. Zero overhead when disabled.
Propagator assignments by phase:

| Phase | Propagator | Rationale |
|---|---|---|
| 1 (arithmetic: `add`, `mul`, `matmul`, `dot`) | algebraic | `add` matches dims, `mul`/`matmul` merge |
| 1 (shape ops: `reshape`, `squeeze`, `expand_dims`) | PASS_THROUGH_FIRST | dims unchanged |
| 1 (creation: `zeros`, `ones`, `arange`) | none | creates new arrays |
| 1 (properties) | none | queries, not numeric |
| 2 (samplers: `normal`, `uniform`) | none | generates dimensionless data by default |
| 3 (functional updates: `at_set`, `at_add`) | algebraic or PASS_THROUGH_FIRST | depends on op |
| 4 (linalg: `det`, `norm`) | STRIP_TO_PLAIN or algebraic | `det` strips, `inv` inverts dims |
| 4 (linalg: `inv`, `solve`) | algebraic | |
| 5 (FFT) | PASS_THROUGH_FIRST | output dims = input dims |
| 6 (comparisons) | STRIP_TO_PLAIN | output is bool |
| 7 (trig, exp/log) | REQUIRE_DIMENSIONLESS | angles/exponents dimensionless |
| 7 (cumsum, cumprod) | PASS_THROUGH_FIRST | same dims |
| 9 (pytree ops) | none | structural, not numeric |
| 10 (activations) | REQUIRE_DIMENSIONLESS | take raw scores |
| 11 (distributions: `logpdf`, `cdf`) | STRIP_TO_PLAIN | probabilities are dimensionless |
| 12 (transforms: `grad_value`) | algebraic | grad of f: Q → R is R / Q dims |
| 14 (arithmetic gaps) | algebraic | `sub`, `div`, `neg` |
| 15 (reductions: `median`, `std`, `var`) | PASS_THROUGH_FIRST / algebraic | `var` squares dims |

---

## Term Language

JAX's own types are the terms. `jax.Array`, `jax.numpy.dtype`,
`jax.Device`, `jax.sharding.Mesh`, `jax.sharding.NamedSharding`,
`jax.tree_util.PyTreeDef`, and `jax.random.PRNGKey` are all first-class.

### Core types (used directly from JAX)

| Type | Role | Example |
|---|---|---|
| `jax.Array` | The fundamental array | Result of any jnp operation |
| `jnp.dtype` / numpy dtype | Data type descriptor | `jnp.float32`, `jnp.int64` |
| `jax.Device` | Hardware location | `jax.devices()[0]` — represented as string in predicates |
| tuple | Shape | `(3, 4, 5)` |
| `jax.random.PRNGKey` (aka `KeyArray`) | Random state | `jr.key(0)` |
| `jtu.PyTreeDef` | Pytree structure (treedef) | Returned by `tree_flatten` |
| `jax.sharding.Mesh` | Device mesh | `jax.make_mesh((2,), ('x',))` |
| `jax.sharding.NamedSharding` | Sharding spec | `NamedSharding(mesh, P('x'))` |
| `jax.sharding.PartitionSpec` | Partition spec | `P('x', None)` |

### Wrapper-defined terms

Keep these minimal. The only new one is:

| Term | Constructor | Semantics |
|---|---|---|
| `dtype_info(DTYPE, KEY, VALUE)` | fact | Dtype property entry: bits, min/max, is_floating, is_complex |

Everything else flows through JAX's native types.

---

## Predicate Catalogue

### Array creation

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `array` | `/2, /3` | `(+DATA, -A)`, `(+DATA, +OPTS, -A)` | pure | Create array from list/nested list |
| `zeros` | `/2, /3` | `(+SHAPE, -A)`, `(+SHAPE, +OPTS, -A)` | pure | Zero array; OPTS for dtype |
| `ones` | `/2, /3` | | pure | Ones array |
| `full` | `/3, /4` | `(+SHAPE, +VALUE, -A)` | pure | Filled array |
| `arange` | `/2, /3, /4, /5` | | pure | Range array |
| `linspace` | `/4, /5` | `(+START, +END, +STEPS, -A)` | pure | Linearly spaced |
| `logspace` | `/4, /5` | | pure | Logarithmically spaced |
| `eye` | `/2, /3` | | pure | Identity matrix |

### Array properties (multi-mode)

| Name | Arity | Modes | Purity | Bijective? | Description |
|---|---|---|---|---|---|
| `shape` | `/2` | `(+A,-S)`, `(+A,+S)` check | pure | partial | Shape tuple |
| `dtype` | `/2` | `(+A,-D)`, `(+A,+D)` check | pure | partial | Dtype |
| `device` | `/2` | `(+A,-D)`, `(+A,+D)` check | pure | partial | Device (string) |
| `sharding` | `/2` | `(+A,-S)`, `(+A,+S)` check | pure | partial | Sharding (repr string) |
| `dim` | `/2` | `(+A,-N)` | pure | no | `ndim` |
| `element_count` | `/2` | `(+A,-N)` | pure | no | `size` |

### Shape operations

| Name | Arity | Modes | Purity | Bijective? | Description |
|---|---|---|---|---|---|
| `reshape` | `/3` | `(+A,+SHAPE,-A2)` | pure | with shape | Reshape array |
| `squeeze` | `/2, /3` | `(+A,-A2)`, `(+A,+AXIS,-A2)` | pure | `expand_dims` | Remove size-1 dims |
| `expand_dims` | `/3` | `(+A,+AXIS,-A2)` | pure | `squeeze` | Add size-1 dim |
| `transpose` | `/2, /3` | `(+A,-A2)`, `(+A,+AXES,-A2)` | pure | self-inverse | Transpose |
| `moveaxis` | `/4` | `(+A,+SRC,+DEST,-A2)` | pure | with inverse | Move axis |
| `swapaxes` | `/4` | `(+A,+A0,+A1,-A2)` | pure | self-inverse | Swap two axes |
| `broadcast_to` | `/3` | `(+A,+SHAPE,-A2)` | pure | no | Broadcast to shape |
| `concatenate` | `/3` | `(+ARRS,+AXIS,-A)` | pure | no | Concatenate |
| `stacked` | `/3` | `(+LS,+AXIS,-A)`, `(-LS,+AXIS,+A)` | pure | bijective | Forward `jnp.stack`, backward `jnp.unstack` |

### Math

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `matmul` | `/3` | `(+A,+B,-C)` | pure | Matrix multiply |
| `dot` | `/3` | | pure | Dot product |
| `add` | `/3` | | pure | Element-wise add |
| `sub` | `/3` | | pure | Element-wise subtract |
| `mul` | `/3` | | pure | Element-wise multiply |
| `div` | `/3` | | pure | Element-wise divide |
| `neg` | `/2` | `(+A,-B)` | pure | Negate |
| `abs` | `/2` | | pure | Absolute value |
| `sum` | `/2, /3` | | pure | Sum reduction |
| `mean` | `/2, /3` | | pure | Mean reduction |
| `max` | `/2, /3` | | pure | Max reduction |
| `min` | `/2, /3` | | pure | Min reduction |
| `clip` | `/4` | `(+A,+MIN,+MAX,-A2)` | pure | Clip values |

### Functional updates (`.at`) — new vs PyTorch

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `at_set` | `/4` | `(+A,+IDX,+VAL,-A2)` | pure | `A.at[IDX].set(VAL)` |
| `at_add` | `/4` | `(+A,+IDX,+VAL,-A2)` | pure | `A.at[IDX].add(VAL)` |
| `at_mul` | `/4` | | pure | |
| `at_min` | `/4` | | pure | |
| `at_max` | `/4` | | pure | |
| `at_get` | `/3` | `(+A,+IDX,-VAL)` | pure | `A.at[IDX].get()` |

### Conversions (bijective)

| Name | Arity | Modes | Purity | Bijective? |
|---|---|---|---|---|
| `jax_numpy` | `/2` | `(+A,-N)`, `(-A,+N)` | pure | yes |
| `array_list` | `/2` | `(+A,-L)`, `(-A,+L)` | pure | yes |

### PRNG (state-threaded)

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `key` | `/2` | `(+SEED,-K)` | pure | Create PRNG key from seed |
| `split_key` | `/3` | `(+K,+N,-KEYS)` | pure | Split key into N subkeys |
| `split_key` | `/2` | `(+K,-KEYS)` | pure | Split into 2 subkeys |
| `fold_in` | `/3` | `(+K,+DATA,-K2)` | pure | Fold data into key |
| `key_bytes` | `/2` | `(+K,-B)`, `(-K,+B)` | pure | Key ↔ raw bytes (bijective) |
| `normal` | `/3, /4` | `(+K,+SHAPE,-A)`, `(+K,+SHAPE,+OPTS,-A)` | pure | Normal sample |
| `uniform` | `/3, /4, /5` | | pure | Uniform sample |
| `bernoulli` | `/3, /4` | | pure | Bernoulli sample |
| `categorical` | `/3` | `(+K,+LOGITS,-A)` | pure | Categorical sample |
| `permutation` | `/3` | `(+K,+A,-A2)` | pure | Random permutation |
| `choice` | `/4, /5` | | pure | Random choice |
| `sampler` | `/2` | `(+NAME,-FN)`, `(-NAME,-FN)` | pure, nondet | Sampler registry |

### Pytree operations

| Name | Arity | Modes | Purity | Nondet? | Description |
|---|---|---|---|---|---|
| `leaf` | `/2` | `(+TREE,-LEAF)` | pure | yes | Enumerate leaves |
| `leaf_with_path` | `/3` | `(+TREE,-PATH,-LEAF)` | pure | yes | Leaves with key-path |
| `tree_flatten` | `/3` | `(+T,-TD,-LS)`, `(-T,+TD,+LS)` | pure | partial | Bijective flatten |
| `tree_structure` | `/2` | `(+T,-TD)` | pure | no | Get treedef |
| `tree_map` | `/3` | `(+F,+T,-T2)` | pure | no | Map function over leaves |
| `tree_reduce` | `/4` | `(+F,+T,+INIT,-R)` | pure | no | Reduce over leaves |
| `all_leaves` | `/1` | `(+LS)` | pure | no | Check list is all leaves |

### Function transforms

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `grad_value` | `/3` | `(+F,+X,-G)` | pure | Compute `grad(f)(x)` |
| `value_and_grad` | `/4` | `(+F,+X,-V,-G)` | pure | Compute `(value, grad)` |
| `jvp_value` | `/4` | `(+F,+PRIMALS,+TANGENTS,-OUT)` | pure | Forward-mode derivative |
| `vjp_value` | `/4` | `(+F,+X,-V,-VJP_FN)` | pure | Reverse-mode derivative |
| `vmap_apply` | `/3, /4` | `(+F,+X,-R)`, `(+F,+X,+AXES,-R)` | pure | Vectorised apply |
| `jit_compile` | `/2` | `(+F,-F2)` | pure | Return JIT-compiled version |

### Sharding and devices

| Name | Arity | Modes | Purity | Nondet? |
|---|---|---|---|---|
| `jax_device` | `/1` | `(-D)`, `(+D)` | pure | yes |
| `local_device` | `/1` | `(-D)`, `(+D)` | pure | yes |
| `device_count` | `/1` | `(-N)` | pure | no |
| `make_mesh` | `/3` | `(+SHAPE,+AXES,-MESH)` | pure | no |
| `partition_spec` | `/2` | `(+AXES,-P)` | pure | no |
| `named_sharding` | `/3` | `(+MESH,+P,-S)` | pure | no |
| `device_put` | `/3` | `(+A,+DEVICE_OR_SHARDING,-A2)` | pure | no |

### Registries (fact tables)

| Name | Arity | Modes | Purity | Source |
|---|---|---|---|---|
| `activation` | `/2` | `(+N,-F)`, `(-N,-F)` | pure, nondet | `jax.nn` |
| `initializer` | `/2` | | pure, nondet | `jax.nn.initializers` |
| `sampler` | `/2` | | pure, nondet | `jax.random` |
| `distribution` | `/2` | | pure, nondet | `jax.scipy.stats` |
| `dtype_info` | `/3` | | pure, nondet | `jax.dtypes` + `jnp.finfo/iinfo` |

---

## Submodule Breakdown

```
clausal/modules/py/jax.py             # Core: jnp creation, math, properties, shape, .at, linalg, fft, advanced math
clausal/modules/py/jax_random.py      # PRNG keys, samplers, sampler registry
clausal/modules/py/jax_nn.py          # Activation + initializer registries
clausal/modules/py/jax_scipy.py       # scipy.special, scipy.stats distributions
clausal/modules/py/jax_tree.py        # Pytree enumeration, flatten/unflatten, tree_map
clausal/modules/py/jax_transforms.py  # grad, vmap, jit, jvp, vjp
clausal/modules/py/jax_sharding.py    # Devices, meshes, sharding specs, device_put
clausal/modules/py/jax_optax.py       # Optimisers, schedules, gradient transforms, losses
clausal/modules/py/jax_equinox.py     # Equinox: layer constructors, filter transforms, partition/combine, tree_at, serialisation
```

`jax.py` is the main module and mirrors `torch.py`'s scope — array
creation, math, shape, properties, conversions, plus linalg and FFT
since JAX keeps them accessible via `jnp.linalg` / `jnp.fft` rather than
a separate library.

`jax_random.py`, `jax_nn.py`, `jax_scipy.py`, `jax_tree.py`,
`jax_transforms.py`, `jax_sharding.py`, `jax_optax.py`,
`jax_equinox.py` are all small focused modules following the
`torch_nn.py` / `torch_distributions.py` pattern.

Shared helpers (`_pure`, `_property_2`, `_bidir_2`, `_fact_table_2`,
`_deep_deref`, `_pred`) live in `clausal/modules/py/_helpers.py` —
already in place for PyTorch.

---

## Showcase Example

```clausal
-import_from(py.jax, [zeros, array, shape, dtype, matmul, add, sum,
                       array_list, float32, reshape, relu_apply])
-import_from(py.jax_random, [key, split_key, normal, uniform])
-import_from(py.jax_tree, [leaf, tree_map, tree_flatten])
-import_from(py.jax_transforms, [grad_value, value_and_grad, vmap_apply])

# Pure array computation — zero ++() escapes
two_layer(INPUT, W1, W2, OUT) <- (
    matmul(INPUT, W1, H),
    relu_apply(H, H2),
    matmul(H2, W2, OUT)
)

# PRNG key threading — state-threaded but backtracking-safe
Test("random weight initialisation") <- (
    key(42, K0),
    split_key(K0, 2, [K1, K2]),
    normal(K1, [784, 256], W1),
    normal(K2, [256, 10], W2),
    shape(W1, [784, 256]),
    shape(W2, [256, 10])
)

# Pytree enumeration — every leaf of a model parameter pytree
large_leaves(PARAMS, LEAVES) <- (
    findall(L, (leaf(PARAMS, L), element_count(L, N), N > 1000), LEAVES)
)

# Bijective pytree flatten
roundtrip_params(PARAMS) <- (
    tree_flatten(PARAMS, TD, LS),
    tree_flatten(REBUILT, TD, LS),
    PARAMS == REBUILT
)

# Gradient — one-shot predicate
Test("grad of x^2 at 3 is 6") <- (
    F is ++(lambda x: x ** 2),
    X is ++(jnp.array(3.0)),
    grad_value(F, X, G),
    array_list(G, 6.0)
)

# Vectorise a predicate-defined function
Test("vmap doubles each element") <- (
    F is ++(lambda x: x * 2),
    X is ++(jnp.arange(5)),
    vmap_apply(F, X, R),
    array_list(R, [0, 2, 4, 6, 8])
)

# Shape check in predicate mode
check_batch_shape(A, BATCH) <- (
    shape(A, S),
    S is (BATCH, *_)
)
```

---

## Design Notes

1. **`shape/2`, `dtype/2`, `device/2`, `sharding/2` are check-only in
   `(+A, +V)` mode.** They don't reshape/cast/transfer. For reshape use
   `reshape/3`; for casting use `astype/3`; for placement use
   `device_put/3`.

2. **No in-place operations to worry about.** JAX's functional update
   idiom (`arr.at[idx].set(v)`) is already pure. Wrapped as `at_set/4`
   etc.

3. **PRNG is state-threaded.** Callers split a key, pass one subkey to
   each consumer. If a sample is abandoned via backtracking, the consumed
   key goes with it; the pre-split key and any other subkeys remain
   valid. This is the same discipline as difference lists or DCG
   state threading — and JAX does it natively.

4. **`.clausal` syntax is Python.** Comments use `#` not `%`. Negation
   is `not(goal)` not `\+`. `++()` in goal position is a silent no-op
   — same trap as PyTorch; use `is_*` check predicates.

5. **Export constants to avoid `++()`.** Dtypes (`float32`, `int64`,
   `bfloat16`), constants (`pi`, `inf`, `nan`), and `newaxis` come out
   of `py.jax` via `__getattr__`.

6. **JAX `Array` equality is element-wise.** Comparing two `jax.Array`
   with `==` returns an array, not a scalar. Compare via `array_list`
   in tests, use `allclose/2`, or use Clausal comparison operators on
   scalars.

7. **Device and sharding as strings.** `device/2` returns `"cpu:0"` /
   `"gpu:0"`; `sharding/2` returns `repr(sharding)`. Strings are
   naturally relational.

8. **Registry maintenance.** Generate fact tables from introspection
   rather than hardcoding:
   - `activation/2`: walk `jax.nn` for callables with the right signature
   - `initializer/2`: walk `jax.nn.initializers`
   - `sampler/2`: walk `jax.random` for top-level sampling functions
   - `distribution/2`: walk `jax.scipy.stats` submodules
   This keeps registries current across JAX versions.

9. **`jax.Array` is abstract — be careful with `isinstance`.** Real
   arrays are `jax.Array` subclasses (e.g. `ArrayImpl`, `ShardedArray`).
   Check against `jax.Array` for `isinstance` guards.

10. **Tracers vs concrete arrays.** Under `jit`, JAX replaces arrays
    with abstract tracers. Predicates that inspect array *values* (not
    just dtype/shape) can't run under `jit`. This is only relevant if
    we ever wrap a Clausal predicate as a `jit`'d function — flagged
    for the transforms phase.

11. **PRNGKey is an array too.** Modern JAX (`jax.random.key(seed)`)
    returns a typed-key `Array` with `dtype=key<fry>`. Old-style
    `PRNGKey(seed)` is deprecated but still works, producing a `uint32[2]`
    array. The wrapper uses `jr.key` exclusively.
