# Neurosymbolic Platform — Phase Index

Companion to the sibling documents one level up:
- `../neurosymbolic_platform.md` — motivation (written before Clausal
  was known to the author; reads as an ambient case for the whole
  category).
- `../NEUROSYMBOLIC_PLATFORM_SKETCH.md` — the Clausal-specific sketch
  that identifies the five genuinely new phases and argues their
  ordering. **Source of truth for rationale.** If a phase plan here
  disagrees with the sketch, fix the sketch first.

This folder contains one actionable plan per phase. The shared
conventions for writing and phasing plans in this repo live in
[`../EXTERNAL_WRAPPER_CHECKLIST.md`](../EXTERNAL_WRAPPER_CHECKLIST.md) —
originally written for library-wrapper plans but with general
applicability (Step 10 phasing, Step 11 Issues sections, phase
self-containment, docs-backed-by-tests rule). These plans follow
it where it applies; deviations are called out per phase.

This track is **not a wrapper**, so some sections of the checklist
(bijective map, purity tiers for library ops, Quantity propagators)
are not directly applicable. The parts that do apply:
- **Step 10** — phased implementation with self-contained phase files
- **Step 11** — Issues section in each phase file, populated during
  implementation
- **Checklist A** — naming conventions (least surprise for library
  users: `torch.nn.Module` stays `nn.Module`, Flax `nnx.Linear` stays
  `Linear`, etc.)
- **Checklist I** — `.clausal` syntax rules apply to any example
  or test fixture produced by this track
- **Design Principles** 1–10 at the end of the checklist apply
  throughout

---

## Phases

| Phase | File | Character | Status |
|---|---|---|---|
| N-1 | [Neural predicate adapters](phase_n1_neural_predicates.md) | engineering, pattern reuse | not started |
| N-2 | [Architecture compilation](phase_n2_architecture_compilation.md) | engineering, headline demo | not started |
| N-3 | [Differentiable forward within a predicate](phase_n3_differentiable_forward.md) | engineering, differentiation slice | not started |
| N-4 | [Rule-weight learning](phase_n4_rule_weight_learning.md) | research ticket | parked |
| N-5 | [vmap-batched proofs](phase_n5_vmap_batched_proofs.md) | research ticket | parked |

---

## Build order

```
N-1  ──┐
       ├──▶  N-3  ──┐
N-2  ──┘            │
                    ▼
                (engineering envelope ends here)

N-4, N-5: research tickets, parked until a concrete workload demands them.
```

- **N-1 and N-2 are siblings**, buildable in parallel. They share
  no code, but both land before N-3 because N-3 needs a working
  neural-predicate to train through (N-1) and a target to synthesise
  (N-2).
- **N-3 is the end of "promised" scope** per the sketch. It is
  where the platform claim "gradients flow through proofs" starts
  to be literally true, within the single-predicate envelope.
- **N-4 and N-5 are research**, not the next step after N-3. Don't
  schedule them on the calendar; wait for a workload that would
  benefit and scope them then.

---

## What to build first

Per the sketch (`../NEUROSYMBOLIC_PLATFORM_SKETCH.md:92`), the
answer is **N-2 (architecture compilation)**:

- It lands entirely inside Clausal's existing machinery (term
  expansion V3-2 plus a new compilation sink).
- It produces a sharp demo that validates the homoiconic claim —
  pattern-match and synthesise a transformer variant, then compile
  it.
- It doesn't require committing to any differentiation research.

N-1 is the parallel sibling that unblocks "call a pretrained model
as a goal" and is a direct application of the adapter pattern
already used by `_ScipySpecialPredicate`.

---

## Shared abstractions (read once, cite from phase files)

### Backend split

| Backend | Role in this track |
|---|---|
| PyTorch | Import target for pretrained models (HuggingFace etc.). N-1. |
| Flax NNX | Compilation target for synthesised architectures. N-2. |
| JAX (vmap/jit) | Only required by N-5. Not a dependency of N-1..N-4. |

The two-backend decision is load-bearing: NNX modules are plain
Python objects with explicit parameters, which is the cleanest sink
for term-driven generation. PyTorch is where the pretrained-model
ecosystem lives. Keep the adapter story on the PyTorch side and
the synthesis story on the NNX side; don't cross the wires.

### Existing Clausal features reused

| Feature | Where it's defined | Reused by |
|---|---|---|
| Groundness-keyed dispatch (V2-2) | `clausal/logic/predicate.py:_get_dispatch` | N-1 (forward vs. check), N-4 (weighted dispatch) |
| Adapter predicate pattern | `clausal/modules/py/scipy_special.py` (`_ScipySpecialPredicate`) | N-1 |
| Term expansion (V3-2) | `clausal/logic/term_expansion.py` | N-2 (architecture → IR rewrite) |
| Module system (V3-1) | `clausal/logic/compiler_v2.py`, `clausal/modules/` | N-1, N-2 (new modules live here) |
| Attributed variables / trail | `clausal/logic/variables/` (C extension) | N-3 (autograd tape preservation), N-5 (vmap interaction) |
| PyThunk / `++()` interop | `clausal/terms.py`, `clausal/templating/term_rewriting.py` | N-1 (escape hatches), N-2 (callable parameters) |

### Out of scope for the whole track

- **Training loop orchestration.** Loss, optimizer step, scheduler.
  Stays in Python via `++()` — same stance as `pytorch/overview.md`
  takes for `torch.optim`. State-threading GPU tensors through
  backtracking is not worth the cost.
- **Multi-machine / distributed training.** Orchestration, not
  logic programming.
- **Shape-as-constraints (CLP-style shape inference).** Interesting,
  but its own research project; see the note in
  `pytorch/overview.md:241`.
