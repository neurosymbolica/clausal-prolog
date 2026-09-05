# Subinterpreters and cells (design note, 2026-09-05)

Author's observation during P3-2 close-out: "if we use immutable tuples to
represent terms, that makes using Python's subinterpreters much easier, and
could be a way to achieve large speedups through AND/OR parallelism."

## Assessment recorded at the time: the instinct is correct and specific

PEP 734's shareable set is {str, bytes, int, float, bool, None, tuples of
shareable}. Pre-flip terms (PredicateMeta instances) were unshareable and
interpreter-locked; post-flip a GROUND cell is natively shareable through
subinterpreter channels (copied in C, no pickle). Three P3-era decisions
compound this:
- P3-1 §1a: terms became picklable/process-portable for free → the
  MULTIPROCESSING rung works today with zero new machinery.
- P3-2 Task 2 ruling: cells compare slot 0 by ==, never `is` — accidental
  future-proofing, since sys.intern is per-interpreter and pointer identity
  would not survive the boundary.
- Tabling's canonical keys are already ground-tuple-shaped
  (_normalize_for_key) → a shared cross-interpreter answer-table service has
  shareable keys by construction.

**Supersedes in part:** /workspace/clausal-parallelism/implementation_plans/
free_threaded/FREE_THREADED_PARALLELISM.md claims free-threading enables
"parallelism that subinterpreters fundamentally cannot" — written pre-cells,
when NOTHING crossed the boundary. Post-cells that blanket dismissal is
wrong for ground-term traffic; it survives only for fine-grained
shared-binding AND-parallelism.

## Obstacles (honest)

1. Only ground terms cross: Var/DictTerm/thunks are interpreter-local —
   boundary traffic must be canonicalized/renumbered (tabling-key machinery
   is the template).
2. C extensions are single-phase init today → will not import in
   subinterpreters / force the shared GIL. Needs PEP 489 multi-phase init +
   PEP 684 per-interpreter-GIL declaration. This audit OVERLAPS the
   free-threaded plan's thread-safety audit — one "C extension
   modernization" prerequisite serves both rungs.
3. Per-worker program import cost (the .pyc path + CLAUSAL_BYTECODE_TAG
   discipline matter); answer streaming is copying — fine coarse-grained,
   prohibitive fine-grained.

## Fit

- Coarse OR-parallelism = the Muse copying model, and copying is cheap
  exactly because terms are tuples: parallel findall over independent
  ground subgoals, portfolio solve, parallel tabled subgoals with a shared
  table service. Natural.
- Fine-grained AND-parallelism (shared bindings): NOT a subinterpreter fit;
  free-threading territory (the existing plan, now ~9% single-thread
  overhead on 3.14).

## The ladder (post-cells) and sequencing

1. TODAY, zero machinery: multiprocessing portfolio/OR-parallel experiments
   (terms pickle) — measure the appetite on the query-parallel legal-rules
   workloads before building anything.
2. Subinterpreters after the C-extension modernization prerequisite —
   same-process workers, native tuple transfer; composes with stencil-v2
   (per-interpreter JIT pages).
3. Free-threading for the shared-binding slice, per the existing plan.

Not Phase-3 work; explore after P3-3 alongside (not inside) stencil-v2.
No new requirements on P3-3 beyond what the stencil-seam ruling already
demands.
