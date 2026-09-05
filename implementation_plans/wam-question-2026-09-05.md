# The WAM question (design note, 2026-09-05)

Raised by the author during P3-2 close-out, alongside the stencil-v2 revival
decision: "if we are considering a stencil compiler, would it be better to
move to a WAM (in C)? The old reasons against were low-level structures —
tagged unions, memory management — but we have just gone lower level. Weigh
against the generator trampoline's flexibility (tabling took WAMs years;
it was natural here)."

## Assessment recorded at the time

**WAM decomposes into two independent bets; the answer differs per bet.**

1. **Control model (instruction set, env/choice-point stacks, WAM stack
   discipline): NO, on the merits.** Suspension fights the WAM's stack
   discipline — XSB's SLG-WAM (freeze registers, forward trail) is the
   cost exhibit. The modern counter-evidence is SWI: it added tabling by
   first adding delimited continuations to its VM and building tabling as
   a library on top — conceding that engine-level suspension flexibility
   beats baked-in machine support. The generator trampoline already IS
   the delimited-continuations position; Clausal's tabling/WFS/NAF fell
   out of it naturally. Scryer (WAM in Rust) is fast and still lacks that
   tabling story.

2. **Term memory (tagged machine words, arena heap, pointer-reset
   backtracking, in-place binding): SEPARABLE, LATER, EVIDENCE-GATED.**
   Correction to the premise: P3-2 went lower-level in SHAPE only — cells
   are still PyObjects (refcounts, GC, headers, Var objects). The old
   objections were about the allocation half, which was deliberately not
   crossed (spec + copy-patch proposal both: "no custom GC, terms remain
   PyObjects"). Crossing it costs the identity Python seam (terms ARE
   Python values everywhere — builtins, ++ escapes, scipy, the parked
   classes-as-functors seam); a WAM heap turns that into a marshalling
   codec at every boundary. BUT cells make the memory bet more takeable
   later: a cell has an obvious arena/tagged-word encoding, and the
   funnel discipline already hides the representation behind accessors —
   so "WAM-flavored data, trampoline control" is available incrementally,
   possibly per-predicate for stencil-compiled code only. The copy-patch
   proposal itself parks NaN-boxing/arena as post-v1 experiments.

**Sequencing:** stencil-v2 (see stencil-v2-scoping-memo.md) is what
generates the deciding evidence — after it lands on cells, the residual
gap vs Scryer decomposes into boundary/dispatch overhead (stencils'
domain) vs PyObject allocation tax (the memory bet's domain). The
parking-time profile said boundary costs dominated; if that holds
post-cells, the memory bet may never pay its seam cost. Decide after
stencil-v2 profiling, not before.

**Interaction with current work:** none for P3-2; for P3-3, the same
backend-pluggable dispatch seam ruled in for stencils serves an arena
experiment identically. No new requirement.
