# Phase N-5 — `vmap`-batched proofs *(speculative)*

**Status: parked.** Not scheduled. The only phase in this track
that genuinely needs JAX rather than PyTorch. File exists to
record the question, not to plan the work.

---

## The question

Alternative unifications (the branches of proof search) are the
obvious candidate for `jax.vmap` — run all alternatives in parallel
on accelerator, discard the ones that fail. If it works, Clausal's
proof-search story becomes competitive with bespoke neural
architectures on GPU/TPU. If it doesn't, no headline claim falls
over.

The hard part is not running `vmap` over a pure function — that's
trivial. The hard part is that proof search involves:
- A **mutable trail** (`clausal/logic/variables/`) — a `vmap`ped
  proof wants per-lane trails, not one shared trail.
- **Groundness-keyed dispatch** (V2-2) — each lane may hit a
  different dispatch entry, which is not a vmappable operation.
- **Backtracking ordering** — SLD's leftmost-first, depth-first
  discipline becomes *a* discipline rather than *the* discipline
  under parallel evaluation.

None of these have a published treatment for logic programming.
The published work on vectorising Prolog-like systems either
restricts the language (Datalog, bottom-up) or accepts a
significant slowdown on serial workloads.

---

## What would move it forward

1. **A performance ceiling** — a workload where N-1/N-2/N-3 are
   known to be too slow, with measurements, and where the bottleneck
   is demonstrably alternative-branch fan-out rather than a per-call
   tensor op. Without this, we're optimising a cost we can't see.
2. **A restricted sub-language** — maybe `vmap`ping arbitrary proof
   search is intractable but `vmap`ping a specific, disciplined
   fragment (pure + single-level dispatch + no trail mutations
   that survive the call) is easy. Isolate that fragment first.
3. **An alternative to trail mutation** — functional union-find,
   persistent trails, or a pure recomputation strategy. Needs
   literature review; there's work on this in the theorem-proving
   community.

---

## Why it's parked

Three independent reasons, any one of which would be enough:

1. **No workload demands it.** See N-4's reasoning — speculative
   performance work is almost always scoped wrong.
2. **No published treatment exists** for the interaction between
   `vmap`, mutable trails, and runtime dispatch. This is the
   sentence from the sketch
   (`../NEUROSYMBOLIC_PLATFORM_SKETCH.md:86`) that warrants
   taking seriously.
3. **It pulls JAX into the critical path.** The rest of the track
   is PyTorch-first plus Flax NNX as a compilation target; N-5
   would make JAX load-bearing everywhere it touches. That's a
   much bigger dependency shift than any other phase and deserves
   its own scoping.

Revisit when:
- N-1..N-3 are stable and in regular use.
- A user has profiled a realistic workload and named branch
  fan-out as the bottleneck.
- The JAX dependency is already on the critical path for some
  other reason (e.g., a research project specifically using
  Flax NNX with autograd).

---

## Related reading

- JAX `vmap` documentation and the functional-array-programming
  literature it draws from.
- Any paper on parallel Prolog — most of them predate GPUs and
  reason about process-level parallelism; not directly
  applicable but useful for vocabulary.
- `clausal/logic/variables/` — the trail implementation this
  phase would have to rethink or work around.

---

## Issues

_To be populated if/when this phase is unparked._
