# Phase N-3 — Differentiable forward within a predicate

Gradients flow through native autograd *inside* a single neural-predicate
call, including across any unifications that bind differentiable
tensors to output variables. Proof structure stays classical — no
differentiable resolution, no soft clause choice, no vmap. After
this phase, the user can train on a loss computed from the final
bindings of a successful proof, as long as the differentiable work
is contained in one (or a chain of pure, autograd-transparent)
neural-predicate call(s).

This is where the sketch's "promised" scope ends
(`../NEUROSYMBOLIC_PLATFORM_SKETCH.md:69`).

---

## Rationale

~80% of the usability payoff for ~20% of the research risk. The
hard, unresolved research problems in differentiable Prolog
(differentiating through backtracking, soft unification, weighted
clause choice) all sit *outside* the single-predicate envelope.
Inside the envelope, autograd just needs to not be broken by the
engine — the tensors flow through unifications, the tape gets
preserved, and PyTorch / JAX handle the backward pass the way they
always do.

The main risk is that the unifier, the trail, or `_deep_deref`
does something that invalidates the autograd graph (copies a tensor,
detaches, breaks the leaf → grad chain). N-3 is the phase that
audits those paths and proves (by test) that they don't.

---

## Scope

### In scope
- Audit `clausal/logic/variables/` (C extension: `Var`, `Trail`,
  `unify`) and `clausal/logic/builtins.py` (`structural_unify`,
  `_deep_deref`) for tensor-safety: a `torch.Tensor` with
  `requires_grad=True` must survive unification and dereferencing
  with its `grad_fn` chain intact.
- Decide on a `_tensor_deref` path: either existing `_deep_deref`
  is already tape-safe (verify) or add a specialised branch for
  tensors that preserves the autograd tape explicitly.
- Document (and test) the guarantee: "if a differentiable tensor
  is bound to a variable by a neural predicate, and that variable
  is read out of a successful proof, `.backward()` on a loss
  computed from it propagates to the original parameters."
- Extend N-1's neural predicate adapter to opt into
  differentiable mode per registration: `neural_predicate(Name, Module, differentiable_=True)`.
  Default remains `False` (forward/check only) so we don't pay
  tape-construction cost for users who don't need gradients.
- One toy training loop as a showcase: a classification predicate
  backed by a small `nn.Module`, trained end-to-end with a standard
  `torch.optim.Adam` in a `++()` block that calls Clausal for the
  forward pass.

### Out of scope (intentionally)
- Differentiating through backtracking or multiple proof branches.
  That's N-5.
- Soft unification / fuzzy matching. Not planned.
- Weighted clause selection. That's N-4.
- JAX autograd. PyTorch only for this phase. JAX-backed NNX modules
  compiled in N-2 work, but via PyTorch-style `.grad` only after
  calling `torch.func.grad` or an equivalent shim that bridges the
  two; not in scope.
- Gradient checkpointing, mixed precision. Users can enable those
  on their modules; the engine is transparent to them.

### Assumes (prerequisites)
- [N-1](phase_n1_neural_predicates.md) — the adapter to opt into.
- [N-2](phase_n2_architecture_compilation.md) — *not strictly
  required*, but in practice N-3 is most interesting when N-2 has
  landed, because then the "train a synthesised architecture" story
  works end-to-end.
- **C-extension unifier** — `clausal/logic/variables/`. Any changes
  here need the rebuild step the existing build system already
  handles.

---

## File layout

```
clausal/logic/variables/                       # modify: audit unify / deref for tensor safety
clausal/logic/builtins.py                      # modify: _deep_deref tensor branch if needed
clausal/modules/py/torch_nn_predicates.py      # modify: differentiable_= registration flag
tests/test_differentiable_forward.py           # new: tape-preservation invariants
tests/test_neural_training_loop.py             # new: end-to-end training smoke test
clausal/examples/train_mlp.clausal             # new: showcase training loop
```

---

## Invariants to test

Concrete, executable. Each is a test case in
`tests/test_differentiable_forward.py`:

1. **Bind-through-unify preserves `grad_fn`.** A tensor with
   `requires_grad=True` bound to a `Var` via `structural_unify`,
   then read back via `deref`, has the same `grad_fn` identity.
2. **Deep-deref preserves `grad_fn`.** Same, via `_deep_deref`
   through nested list / dict structure.
3. **Backward reaches parameters.** After a neural-predicate call
   binds an output, `loss.backward()` on a function of that output
   populates `.grad` on the module's leaf parameters.
4. **Backtracking does not leak tape.** If a predicate binding is
   unwound via the trail, the undone binding does *not* leave
   dangling tape entries that keep the tensor alive after GC.
5. **Check mode does not require grad.** A check-mode call with
   `requires_grad=True` tensors on both sides works and doesn't
   build a tape (check mode compares; it doesn't differentiate).
6. **Non-differentiable default costs nothing.** Registration
   without `differentiable_=True` does not call `requires_grad_`
   or hold references that would prevent normal GC.

---

## Design notes

- **Probe first, decide second.** The first concrete task is to
  write test (1) and run it against the current unifier. If it
  passes, most of this phase is documenting the invariant and
  extending the adapter with the flag. If it fails, the C extension
  needs a targeted fix — at that point, investigate which path is
  losing the tape (copy? tuple flattening? `deref` under a walker?)
  and fix there, not at a higher layer.
- **Don't thread a `differentiable=True` flag through the engine.**
  The engine stays oblivious. The flag lives on the adapter and
  controls what the adapter does with its inputs (does it call
  `.requires_grad_(True)` on parameters? does it run in `no_grad`?).
  The unifier's guarantee is "I don't corrupt autograd tape," not
  "I know about autograd."
- **Training loop stays in `++()`.** No attempt to make
  `optimizer.step()` a predicate. The sketch is firm on this and
  so is `../pytorch/overview.md:166`. N-3 makes the *forward* pass
  callable as a goal and differentiable; the backward + step stays
  Python.
- **JAX path.** Out of scope for N-3, but leave the door open: the
  invariants above are phrased in terms of "autograd tape." On
  JAX, the analogue is "the traced function's computation graph,"
  and the same kind of tests apply. Revisit when / if JAX becomes
  the primary backend.

---

## Success criteria

- All six invariant tests above pass.
- `tests/test_neural_training_loop.py` trains a tiny MLP end-to-end
  via a Clausal-defined forward predicate, reaches a sensible loss
  on a synthetic dataset, and verifies parameters actually moved.
- `clausal/examples/train_mlp.clausal` is a one-screen program that
  demonstrates the workflow and reads as documentation.
- Documented guarantee in the module docstring of
  `clausal/modules/py/torch_nn_predicates.py`: "Tensors with
  `requires_grad=True` preserve their autograd tape across Clausal
  unifications." This is the one-line claim that N-3 is defending.

---

## Issues

_To be populated during implementation._
