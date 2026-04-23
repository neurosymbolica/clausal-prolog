# Phase N-1 — Neural predicate adapters

Register a `torch.nn.Module` as a Clausal predicate with no new
engine machinery. Groundness-keyed dispatch (V2-2) handles the two
usable modes: forward (inputs ground → bind outputs) and check
(both sides ground → verify). No gradients yet — N-3 adds those.
After this phase, a user can call a pretrained HuggingFace model
as a goal.

---

## Rationale

Falls out of an existing pattern: `_ScipySpecialPredicate` in
`clausal/modules/py/scipy_special.py:30` already exemplifies
"wrap a Python callable as a multi-arity predicate with a
dispatch function that routes by arity and mode." Neural modules
are the same shape of wrapper with one extra axis (the module
holds state — its parameters — but for the purpose of a single
forward call, that state is an opaque handle).

PyTorch first because the pretrained-model ecosystem lives there.
Flax NNX is the *compilation target* introduced in N-2; it is not
an import target. Keep the two use cases distinct so the adapter
story stays crisp.

---

## Scope

### In scope
- New module `clausal/modules/py/torch_nn_predicates.py` (name TBD;
  may merge into `torch_nn.py` from the PyTorch-wrapper track —
  see *Interaction with the PyTorch wrapper* below).
- `_NeuralPredicate` adapter class: wraps an `nn.Module` instance,
  exposes a multi-arity callable surface, registers into a Clausal
  module alongside ordinary predicates.
- `neural_predicate/2` builtin or declaration: `neural_predicate(Name, Module)`
  installs a module under `Name` in the importing module's namespace.
- Groundness-keyed dispatch entries: forward mode (`(+inputs, -outputs)`)
  runs `module(*inputs)`; check mode (`(+inputs, +outputs)`) runs
  the forward and compares (element-wise `torch.equal` or `allclose`
  for float tensors — pick and document).
- Showcase: load a HuggingFace encoder, call it as a goal, bind
  the resulting embedding tensor to a variable.

### Out of scope (intentionally)
- Gradients. N-3.
- Training loop (`backward`, `optimizer.step`). Stays in Python.
- Batched alternatives under `vmap`. N-5.
- Soft/weighted clause choice. N-4.
- Synthesising modules from terms. That is N-2, and the result of
  N-2 is a concrete `nnx.Module` that can be wrapped by this phase's
  adapter like any other neural predicate.

### Assumes (prerequisites)
- **V2-2 groundness-keyed dispatch** — `clausal/logic/predicate.py`,
  `PredicateMeta._get_dispatch`. Memory entry: "V2-2 done".
- **V3-1 module system** — `-import_from(py.torch_nn_predicates, ...)`.
  The `clausal/modules/` package is the right home (see
  `clausal/modules/regex.py` for the adapter-backed module pattern).
- **Existing PyTorch wrapper (Phases 1–3)** — tensor creation,
  property queries, bijective conversions. Neural predicates
  produce and consume `torch.Tensor` values that the user will
  want to inspect with `shape/2`, `tensor_list/2`, etc.

---

## File layout

```
clausal/modules/py/torch_nn_predicates.py     # new: _NeuralPredicate adapter + registration
clausal/modules/torch_nn_predicates.py        # new: re-export alias (module-path form)
tests/test_neural_predicates.py               # new: adapter, dispatch modes, error paths
tests/fixtures/neural_predicate_basic.clausal # new: smoke test fixture
clausal/examples/huggingface_as_goal.clausal  # new: showcase — pretrained encoder as predicate
```

If the PyTorch wrapper's `torch_nn.py` (planned in
`../pytorch/phase2_conversions_modules.md`) lands first or in
parallel, merge this phase's content into that file rather than
create a new module. Check before writing — don't fork the wrapper.

---

## Predicate / API catalogue

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `neural_predicate` | `/2` | `(+name, +module)` | impure (installs) | Register `MODULE` under `NAME` in the current Clausal module |
| `(registered name)` | `/N+1` | `(+input_1, ..., +input_N, -output)` forward | pure wrt proof (no param mutation) | Run forward pass |
| `(registered name)` | `/N+1` | `(+input_1, ..., +input_N, +output)` check | pure | Run forward and verify output matches |

Registered predicates are named by the user; the `/N+1` arity
depends on how many tensor inputs the module's `forward` takes.
Start with single-input forward (vision backbones, encoders);
multi-input (cross-attention, encoder-decoder) is a straightforward
extension once the single-input case works.

Tolerance for check mode: default `atol=1e-6, rtol=1e-5` matching
PyTorch's `allclose` defaults, overridable per registration.

---

## Design notes

- **State treatment.** The `nn.Module` is an opaque handle. The
  adapter holds a Python reference; the user never sees the
  parameters as Clausal terms in this phase. Parameter enumeration
  is the PyTorch wrapper's job (`parameter/2`, `named_parameter/3`
  in `pytorch/overview.md:398`).
- **Device placement.** Pass through whatever device the module
  and its inputs already live on. Don't add implicit `.to(...)`;
  that's a user concern.
- **Eval vs. train mode.** Default to `module.eval()` on registration
  — check-mode and forward-mode calls shouldn't mutate batchnorm
  stats. If a training loop needs train-mode, the user calls
  `++(module.train())` before the goal.
- **Deep-deref.** Tensors arrive through the unifier and need
  `_deep_deref()` before being passed to `module(...)`. Reuse the
  `_pure()` helper pattern from the PyTorch wrapper
  (`../pytorch/overview.md:517` — the "deep-deref required" lesson).
- **Exception translation.** A shape mismatch in forward raises
  `RuntimeError` inside `module.__call__`. Catch and convert to
  predicate failure, matching the PyTorch wrapper's posture on
  shape errors (`../pytorch/overview.md:192`).

---

## Success criteria

- `tests/test_neural_predicates.py` has ≥ 20 tests covering:
  registration, forward mode on a trivial `nn.Linear`, forward mode
  on a realistic `nn.Sequential`, check mode passing, check mode
  failing, device pass-through, shape-mismatch → predicate failure,
  eval mode default, multi-arity (single-input modules only).
- `clausal/examples/huggingface_as_goal.clausal` loads a small
  pretrained model (e.g. `sentence-transformers/all-MiniLM-L6-v2`
  or a tiny local model — pick something CI can actually run),
  wraps it, and produces an embedding. The example doubles as
  documentation; keep it readable.
- The showcase from `../NEUROSYMBOLIC_PLATFORM_SKETCH.md` rationale
  ("call a pretrained model as a goal") is one line in user-facing
  code after the `-import_from` declaration.

---

## Issues

_To be populated during implementation._
