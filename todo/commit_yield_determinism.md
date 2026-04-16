# `commit` yield — producer-side determinism signalling

## The third control path

The current protocol has two control signals from a producer to its
consumer:

- **`proceed(value)`** (encoded `yield (parent, None)`) — here's a
  solution; I may have more.
- **`fail`** (encoded `yield (parent, DONE)`) — no more solutions;
  run your fail continuation.

There is a genuine third path that is neither:

- **`commit(value)`** — here's a solution, *and* I'm retiring.  I
  will produce no more.  Don't come back for another pull.

When the consumer receives `commit`, it consumes the value and
proceeds with its own continuation exactly as for `proceed`, but it
also de-registers the producer as a future source.  The consumer's
subsequent `fail` path walks straight past this callee to whatever
choice point sits above, instead of doing the redundant pull-cycle
that would have produced the trailing DONE.

## Savings

Per occurrence: one protocol hop saved at the end of each
semi-deterministic sub-call (the hop that delivers DONE after the
last solution).  Small individually, cumulative in recursive chains
where most calls turn out to be deterministic.

Orthogonal to continuation-TCO (`todo/continuation_tco.md`):

- continuation-TCO bypasses intermediate frames on the *solution*
  path of a call that has many solutions.
- `commit` bypasses the trailing *exhaustion* hop of a call that
  produces its last solution and finishes.

Both compose — a tail-delegating wrapper whose child commits on its
last solution inherits that commit onto its own solution emission.

## Where it comes from

Two sources at the callee:

1. **Structural** (compile-time).  The callee's control flow has
   provably exhausted alternatives after this yield.  Canonical
   case: the final yield inside the last clause of a predicate, with
   no pending non-determinism below.  The compiler can detect many
   of these statically.

2. **Dynamic** (runtime).  Indexing has pruned remaining clauses, or
   an earlier `!` has committed.  The callee discovers mid-execution
   that its current solution is its last.  Harder to detect; may
   require a runtime flag set when alternatives are eliminated.

Structural detection is where the big wins live and is the sensible
first target.

## Relation to cut

Cut (`!`) is program-directed commitment: "prune my alternatives up
to the cut barrier."  `commit` here is compiler/runtime-discovered
commitment: "I have no alternatives left after this solution."

They belong to the same family.  A clean unified model expresses
cut as emitting a `commit` plus an explicit "prune choice points up
to barrier X" action — two concepts instead of one monolithic
operation — which may simplify the handling of deep cut in
multi-frame scenarios.

## Protocol encoding

### Under the current tuple-yielding trampoline

A third sentinel value alongside `None` and `DONE` (named `FINAL`
in code; the "commit" terminology survives at the concept level):

```python
yield (parent, FINAL)   # "here's a solution, I'm done after this"
# Note: the value also rides in the tuple; either carry it in a
# triple `(parent, FINAL, value)`, or continue using the leaf-yield
# bindings-through-trail convention and only change the marker.
```

Consumer's while-loop detects `_st is FINAL` and breaks after
processing.  No additional pull needed.

### Under an LLVM backend with an explicit CP stack

- `proceed(value)` — leave my CP in place, return value to caller.
- `commit(value)`  — pop my CP, return value to caller.
- `fail`           — pop my CP, invoke caller's fail.

Three clean actions on the CP stack.  The tuple-protocol and CP-stack
encodings represent the same semantic primitive.

## Interaction with the split-continuation design

If the protocol gains `(proceed, fail, catcher)` continuation slots
(see `todo/continuation_tco.md`), `commit` does not need a fourth
slot.  It's a *variant action* on the existing `proceed` channel:
"invoke `proceed`, then mark me retired so the `fail` channel
bypasses me."

## Status

Parked.  Sequence with respect to continuation-TCO and LLVM:

1. Continuation-TCO / split-continuation protocol should land first
   — it establishes the channel structure `commit` plugs into.
2. `commit` then extends the `proceed` channel with the retirement
   variant.
3. LLVM backend design should account for both from the start — the
   CP-stack encoding makes both uniform and explicit.

## Open questions

- Static detection scope: which structural patterns can the compiler
  prove yield `commit`?  Last-yield-of-last-clause is obvious;
  beyond that needs analysis.
- Dynamic detection: does indexing's pruning happen early enough to
  flip `proceed` to `commit` on the producer's current yield?  Or
  is the flag-check cost higher than the saved hop?
- Does this subsume `todo/continuation_tco.md`'s "choicepoint
  elimination" musing?  (Partial: `commit` eliminates the implicit
  CP that trails a semi-deterministic call.  Cut and explicit CP
  management are separate concerns.)
