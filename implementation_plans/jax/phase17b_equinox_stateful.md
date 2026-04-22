# Phase 17b — Equinox Stateful Modules

Phase 17 shipped Equinox **stateless-only**: `Linear`, `MLP`,
`LayerNorm`, and friends, plus filter transforms, partition/combine,
serialisation. Stateful modules (`BatchNorm`, training-mode
`Dropout`, `StatefulLayer` subclasses carrying state across calls)
need a separate state-threading contract — they pair a **model**
pytree with a separate **state** pytree, threaded through
applications, and constructed via `eqx.nn.make_with_state`.

This phase adds the stateful surface as a small, self-contained
extension to `py.jax_equinox`. No new module file; the predicates
live alongside the Phase 17 ones.

**File to edit:** `clausal/modules/py/jax_equinox.py`

**Depends on:**
- Phase 17 — stateless Equinox surface (layer constructors, apply,
  filter transforms)
- Phase 2 — PRNG keys (training-mode `Dropout` consumes a per-call
  key)
- Phase 9 — pytrees (`eqx.nn.State` is a pytree; leaf enumeration
  already works)

---

## Core Concepts

Stateful Equinox has two first-class values where Phase 17 had one:

| Equinox concept | Clausal | Notes |
|---|---|---|
| `eqx.Module` instance | first-class value | Same as Phase 17 |
| `eqx.nn.State` | first-class value (also a pytree) | Threaded through `apply_stateful_module` |
| `eqx.nn.make_with_state(Cls)(...)` | wraps construction; returns `(model, state)` | Per-class predicates bundle this |
| Inference / training mode | `eqx.nn.inference_mode(model, value=True)` returns a transformed pytree | Exposed as `inference_mode/2, /3` |

State is opaque. Users don't construct `State` directly; they receive
it from a stateful constructor and thread it back out through
`apply_stateful_module`. Inspection (if ever needed) is via Phase 9
pytree predicates — `leaf(STATE, L)`, `tree_flatten(STATE, _, _)`.

---

## Predicates

### Stateful layer constructors (two output slots for MODEL, STATE)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `batch_norm` | `/4` | `(+INPUT_SIZE, +AXIS_NAME, -MODEL, -STATE)` | `eqx.nn.BatchNorm` wrapped by `make_with_state` |
| `batch_norm` | `/5` | `(+INPUT_SIZE, +AXIS_NAME, +OPTS, -MODEL, -STATE)` | same, with extra kwargs (e.g. `mode`, `momentum`, `eps`) |
| `make_with_state` | `/4` | `(+CLS, +KWARGS, -MODEL, -STATE)` | Generic escape: any stateful class by Python class value + kwargs dict |

`batch_norm` is the only stateful layer with first-class ergonomics.
Other stateful layers (user-defined subclasses of `StatefulLayer`,
or `SpectralNorm` in non-standard configurations) go through the
generic `make_with_state/4`, which takes a class value and a kwargs
dict. `SpectralNorm` is a `StatefulLayer` subclass but its Phase 17
predicate already constructs it correctly for filter-grad use; the
stateful variant only matters if a user wants the running sigma as
state, which is esoteric.

### Module application (two output slots for Y, NEW_STATE)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `apply_stateful_module` | `/5` | `(+M, +X, +STATE, -Y, -NEW_STATE)` | `y, new_state = m(x, state)` |
| `apply_stateful_module` | `/6` | `(+M, +X, +KWARGS, +STATE, -Y, -NEW_STATE)` | same with kwargs (e.g. `{"key": K}` for training-mode `Dropout` layered inside a stateful `Sequential`) |

Plain stateless apply stays at `apply_module/3,/4` — callers pick
based on whether their module is stateful.

### Training-mode Dropout

| Name | Arity | Modes | Description |
|---|---|---|---|
| `dropout_train` | `/2` | `(+P, -M)` | `eqx.nn.Dropout(p, inference=False)` |
| `dropout_train` | `/3` | `(+P, +OPTS, -M)` | same with extra kwargs |

Training-mode Dropout is *stateless* — no `State` pytree — but
it consumes a **per-call PRNG key**, passed via `apply_module/4`
as `{"key": K}`:

```clausal
dropout_train(0.5, M),
apply_module(M, X, {"key": K}, Y)
```

Separated from `dropout/2` (Phase 17, `inference=True` default) so
the choice is explicit at construction time. Users who want
training-mode dropout opt in by name, matching the
explicit-beats-implicit principle.

### Inference-mode toggle

| Name | Arity | Modes | Description |
|---|---|---|---|
| `inference_mode` | `/2` | `(+PYTREE, -NEW_PYTREE)` | `eqx.nn.inference_mode(tree, value=True)` — flip any `inference` fields to `True` throughout the tree |
| `inference_mode` | `/3` | `(+PYTREE, +VALUE, -NEW_PYTREE)` | explicit value (`True`/`False`) |

The `/2` arity fits the common eval-time swap (`MODEL_EVAL is
inference_mode(MODEL, ...)`); the `/3` arity supports explicit
switch-back to training.

### Check predicate

| Name | Arity | Modes | Description |
|---|---|---|---|
| `is_stateful` | `/1` | `(+X)` | Succeeds iff `X` is an instance of `eqx.nn.StatefulLayer` |

Parallel to `is_array`. Lets users discriminate in relational code
without groveling through `isinstance` escapes.

---

## Example Usage

```clausal
-import_module(jax)
-import_module(equinox)
-import_from(py.jax, [shape, array_list, allclose])
-import_from(py.jax_random, [key])
-import_from(py.jax_equinox, [
    batch_norm, dropout_train, inference_mode, is_stateful,
    apply_module, apply_stateful_module
])

Test("batch_norm applied in inference mode, no vmap needed") <- (
    batch_norm(3, "batch", {"mode": "batch"}, BN, STATE),
    BN_EVAL is inference_mode(BN),
    X is ++(jax.numpy.ones(3)),
    apply_stateful_module(BN_EVAL, X, STATE, Y, _NEW_STATE),
    shape(Y, [3])
)  # nv

Test("batch_norm training via jax.vmap for the axis_name") <- (
    batch_norm(3, "batch", {"mode": "batch"}, BN, STATE),
    X is ++(jax.numpy.ones((4, 3))),
    VMAPPED is ++(jax.vmap(BN, axis_name="batch",
                           in_axes=(0, None), out_axes=(0, None))),
    apply_stateful_module(VMAPPED, X, STATE, Y, NEW_STATE),
    shape(Y, [4, 3])
)  # nv

Test("training-mode dropout needs a per-call key") <- (
    dropout_train(0.5, D),
    X is ++(jax.numpy.ones(8)),
    key(42, K),
    apply_module(D, X, {"key": K}, Y),
    # With p=0.5 some entries zero, some scaled — never the input
    not array_list(Y, [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
)  # nv

Test("inference_mode swaps a BatchNorm's inference field") <- (
    batch_norm(3, "batch", BN, _),
    BN_EVAL is inference_mode(BN),
    ++(BN.inference) == False,
    ++(BN_EVAL.inference) == True
)  # nv

Test("is_stateful discriminates") <- (
    batch_norm(3, "batch", BN, _),
    is_stateful(BN),
    key(0, K),
    # Linear is not stateful
    not is_stateful_linear(K)
)  # nv
```

---

## Tests

Add to `tests/fixtures/jax_equinox_tests.clausal` under a new
"Stateful modules (Phase 17b)" section:

- `batch_norm/4` constructs a model + state
- `batch_norm/5` with `mode="batch"` constructs correctly
- `apply_stateful_module/5` on inference-mode BatchNorm without
  vmap (shape-only check)
- `apply_stateful_module/5` on vmap-wrapped BatchNorm (via `++()`
  escape for the vmap) — preserves batch shape
- `dropout_train/2` constructs a training-mode Dropout; apply via
  `apply_module/4` with per-call key produces non-identity output
- `inference_mode/2` flips `inference=False` to `True` on a
  stateful module
- `inference_mode/3` with explicit `value=False` toggles back
- `is_stateful/1` succeeds on BatchNorm, fails on Linear
- `make_with_state/4` generic form constructs BatchNorm equivalently
  to `batch_norm/5`

Python unit tests in `tests/test_jax_infra.py` or similar:
- All new exports resolve at import time

---

## Docs

Extend `docs/jax_equinox.md` with a new "Stateful modules (Phase
17b)" section placed after the existing "Module application"
section and before "Filter transforms". Cover:

- Why state is separate: Equinox's pytree-purity rule — state is
  data, not a hidden attribute
- `batch_norm` → `(MODEL, STATE)` — the two-output-slot shape
- `apply_stateful_module` vs `apply_module` — when to reach for
  which
- Training-mode Dropout: `dropout_train` + `apply_module/4` with
  per-call key
- `inference_mode` — what it flips and why (swaps `inference`
  fields across any stateful layer in the tree)
- vmap requirement for BatchNorm with a real batch axis — point at
  the escape pattern (`++(jax.vmap(BN, axis_name=..., in_axes=(0,
  None), out_axes=(0, None)))`); note that inference mode applies
  without vmap
- `is_stateful` as a check predicate

Update `implementation_plans/jax/overview.md`:
- Flip Phase 17b row from "⏸ Deferred" to "✅ Implemented"
- Note the new Tier 3 entries for stateful apply

Update `clausal/modules/py/jax_equinox.py` module docstring's
"Phase 17" heading to mention Phase 17b additions, listing the new
predicates.

---

## Issues

1. **Two output slots, not a tuple.** Stateful constructors and
   `apply_stateful_module` use two separate output slots for MODEL
   + STATE and Y + NEW_STATE rather than a tuple result. Rationale:
   it matches `partition/4` (the precedent for a hot-path pair),
   avoids forcing `RESULT is (A, B)` decomposition at every call
   site, and makes state threading visually explicit. Flax's
   `apply_mutable/5` uses a tuple result instead — the Equinox
   convention differs because state threading is the *primary*
   flow here, not an optional `mutable=` toggle.

2. **`batch_norm` is the only per-class stateful wrapper.** Other
   stateful candidates (`SpectralNorm`'s state variant, user
   subclasses of `StatefulLayer`) are rare enough that the generic
   `make_with_state/4` escape is the right answer. Adding a
   per-class predicate per stateful layer for completeness would
   cost more than the use frequency justifies. If a real caller
   for another stateful layer surfaces, add a dedicated predicate
   then.

3. **BatchNorm needs vmap for training mode.** `axis_name` is a
   named batch axis that only exists under `jax.vmap` or
   `jax.shard_map`. Calling a training-mode BatchNorm on raw input
   errors with "Found an unbound axis name". The wrapper doesn't
   try to vmap automatically — it would have to guess the batch
   axis. Users compose `++(jax.vmap(BN, axis_name=..., in_axes=...,
   out_axes=...))` themselves and pass the result to
   `apply_stateful_module/5`. Inference mode skips the reduction,
   so it applies without vmap — useful for tests and the common
   eval path.

4. **Training-mode Dropout stays stateless.** `Dropout(p,
   inference=False)` has no `State` pytree; it consumes a per-call
   PRNG key via `{"key": K}` kwargs. So it reuses
   `apply_module/4`, not `apply_stateful_module`. Named
   `dropout_train` (rather than a `dropout/3` opts variant) so the
   choice is explicit at construction time — `dropout` means
   inference-mode; `dropout_train` means training-mode. Two names
   are clearer than a boolean hidden in opts.

5. **`inference_mode/2` defaults to `value=True`.** The `/2` arity
   mirrors the common eval-time swap (`MODEL_EVAL is
   inference_mode(MODEL)`); the `/3` arity lets users be explicit
   when switching back to training. Matches `eqx.nn.inference_mode`
   itself, whose `value` kwarg defaults to `True`.

6. **`make_with_state/4` takes a class value, not a name.** The
   generic form mirrors the Python API:
   `eqx.nn.make_with_state(Cls)(**kwargs)`. Users already have the
   class via `++(equinox.nn.BatchNorm)` or via the `layer_class/2`
   registry; forcing a name-based lookup on top would duplicate
   the registry. Kwargs-only (no positional args) because Equinox
   stateful constructors are kwargs-dominant in practice.

7. **`State` is a registered pytree.** Users can introspect it
   with Phase 9 predicates (`leaf(STATE, L)`, `tree_flatten(STATE,
   _, _)`) — no new inspection predicates needed. Documented as a
   forward-reference.

8. **No new `apply_stateful_vmap` predicate.** Callers who need
   vmap around a stateful apply compose `++(jax.vmap(M,
   axis_name=..., in_axes=(0, None), out_axes=(0, None)))` and
   pass the vmapped module to `apply_stateful_module/5`. Adding
   a bespoke vmap+apply predicate would hard-code one axis-spec
   pattern; the escape is general.

9. **`StateIndex` and `StatefulLayer` subclassing are out of
   scope.** `StateIndex` is the marker Equinox uses internally to
   register state slots on custom `StatefulLayer` subclasses. That
   path needs a Clausal-side way to define an `eqx.Module`
   subclass, which is the same territory as custom pytree
   registration (deferred across the JAX wrapper generally). Users
   who hit this use `++()` to define the class in Python and reach
   back through `make_with_state/4`.

---

## Out of Scope

- Custom `StatefulLayer` subclassing from Clausal (same territory
  as custom pytree registration — deferred wrapper-wide)
- `StateIndex` as a Clausal-facing constructor
- Dedicated vmap+apply predicate for stateful modules
- Flax NNX's mutable-state surface (Phase 18b territory)

---

## Estimated Surface

| Category | Predicate count |
|---|---|
| Stateful constructors (`batch_norm` + `make_with_state`) | 2 names, 3 arities |
| Stateful apply | 1 name, 2 arities |
| Training-mode Dropout | 1 name, 2 arities |
| Inference-mode toggle | 1 name, 2 arities |
| Check predicate | 1 name, 1 arity |
| **Total predicate names** | 6 |
| **Total registered arities** | 10 |

Small, focused addition. Fits the extend-in-place model — no new
Python module file, no new import path.

---

## Cross-references

- Phase 17 (`phase17_equinox.md`) — the stateless surface this
  builds on
- Phase 9 (`phase9_pytrees.md`) — `State` is a pytree, so leaf
  enumeration etc. already work
- Phase 2 (`phase2_random.md`) — PRNG keys for training-mode
  `Dropout`
- Phase 18 (`phase18_flax.md`) — Flax's different answer to
  stateful layers (mutable collections + `apply_mutable`), for
  contrast
