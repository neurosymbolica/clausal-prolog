# Phase 17b — Equinox Stateful Modules (deferred)

Phase 17 ships Equinox **stateless-only** — `Linear`, `MLP`,
`LayerNorm`, etc., plus filter transforms, partition/combine,
serialisation. Stateful modules (`BatchNorm`, training-mode
`Dropout`, `LSTMCell` carrying hidden state across calls,
`StateIndex`, `StatefulLayer`) need a separate state-threading
contract that's worth its own phase.

This is a placeholder so the work has a named home in the phase
table. Promote to a full plan when a real caller surfaces.

---

## Scope

| Class / API | What it adds |
|---|---|
| `eqx.nn.State` | Opaque state pytree, threaded through arguments |
| `eqx.nn.make_with_state(Cls)` | Constructor returning `(model, state)` |
| `eqx.nn.BatchNorm` | Running mean/var + axis_name reduction |
| `eqx.nn.Dropout` (training-mode) | Per-call PRNG key + mask state |
| `eqx.nn.StateIndex` | Marker for state slots |
| `eqx.nn.StatefulLayer` | Mixin signalling stateful behaviour |

---

## Predicates (sketch)

| Predicate | Arity | Modes | Description |
|---|---|---|---|
| `make_stateful_layer` | `/4, /5` | `(+CLS_NAME, +OPTS, -MODEL, -STATE)` / `(..., +KEY, ...)` | `eqx.nn.make_with_state(...)` |
| `apply_stateful_module` | `/5` | `(+M, +X, +STATE, -Y, -NEW_STATE)` | Stateful call: state in, state out |
| `apply_stateful_module` | `/6` | `(+M, +X, +KWARGS, +STATE, -Y, -NEW_STATE)` | With kwargs (e.g. `{"key": K}` for training-mode `Dropout`) |
| `batch_norm` | `/3, /4` | `(+INPUT_SIZE, +AXIS_NAME, [+OPTS], -CLS)` | Returns the *class* — pair with `make_stateful_layer` |

Plus per-class predicates for `dropout`'s training-mode variant once
the threading contract is settled.

---

## Open design questions

1. **Stateful-vs-stateless dispatch.** Should `apply_module/3` from
   Phase 17 detect statefulness and fail / warn? Or do we keep two
   distinct predicates (`apply_module`, `apply_stateful_module`)
   and let users pick? Lean toward two distinct predicates — explicit
   beats implicit, especially around state threading.

2. **Constructor shape.** `make_with_state` takes a class and returns
   a callable that builds `(model, state)`. The Clausal-side
   ergonomics question: do we wrap that as one predicate
   `make_stateful_layer/N` that takes a class name string, or per
   stateful class (`batch_norm/?` etc.)?  Probably per-class for
   consistency with Phase 17 — but the registry-shaped `layer_class`
   is already there if a generic form is needed.

3. **Inference/training mode toggling.** Equinox uses
   `eqx.nn.inference_mode(model, value=True)` to swap between the
   two. Wrap as a predicate or leave as `++(eqx.nn.inference_mode(M))`?
   Trivial wrapper, probably worth doing.

4. **Reusing Phase 17's `dropout/2`.** Phase 17 ships `dropout/2`
   defaulting to `inference=True`. Phase 17b should add a
   training-mode variant — possibly `dropout/3` with a key, or a
   distinct `dropout_train/3` predicate. Decision deferred to the
   live phase.

5. **Pytree treatment of `State`.** `eqx.nn.State` is a registered
   pytree — Phase 9 predicates already work on it. The phase plan
   should document this so users know they can `leaf(STATE, L)`,
   `tree_flatten`, etc., to inspect what's in the state.

---

## Triggers to schedule this phase

- A user wants `BatchNorm` (the most common request).
- A user wants training-mode `Dropout` with a new key per step.
- An RNN training loop needs to thread `LSTMCell` hidden state
  across timesteps cleanly.

Until then, escape hatch is `++()`:
`++(eqx.nn.BatchNorm(input_size=64, axis_name="batch"))`.

---

## Cross-references

- Phase 17 (`phase17_equinox.md`) — the stateless surface this
  builds on
- Phase 9 (`phase9_pytrees.md`) — `State` is a pytree, so leaf
  enumeration etc. already work
- Phase 2 (`phase2_random.md`) — PRNG keys for training-mode
  `Dropout`
