# A PREDICATE that both APPLIES and READS an imported dual-declared /0 atom gets the class for the read

**Found:** 2026-09-06, P3-3 Task 5b residual (report §6.1; reviewer F6 corrected the granularity). Deterministic and
narrow; parked by controller ruling, carried to the P3-3 final review.

**Shape.** Owner declares `k` as an atom in its `-module` list AND has a fact
`k,` (so its binding is the /0 `PredicateMeta` class post-P3-1). An importer
`-import_from(owner, [k, …])` and, in the SAME PREDICATE (globals are collected
per predicate, `compiler/predicate.py::_collect_globals_info`), both applies
`k(…)` at arity N>0 AND reads `k` in data position (`get(P, k, V)`, list
element, `==` operand). Task 5b resolves the imported name once per predicate
under a single dotted globals key; that key cannot hold both "the class (for
the applied-form diagnostic)" and "the atom str (for the data read)". Task 5b
chose the class → the applied form gets its proper arity diagnostic, and the
data read in that predicate misses silently (`[]`).

Reviewer-verified matrix (one importer file): `mx_read(V) <- (prof(P), get(P,
k, V))` → `[1]` (fixed); `mx_apply(X) <- k(X)` → `PredicateArityMismatchError`
(diagnostic preserved); `mx_both(V, X) <- (…get…, k(X))` → `[]` (the hole; was
`[]` before Task 5b too — nothing regressed). Consequence worth noting: the same
spelling can now mean different things in two predicates of one file. The
peer-reported corpus shapes do not have the mixed usage.

**Fix sketch.** Move the sub-shape-2 str lowering into the AST rewrite so
data-position occurrences lower to the str literal per SITE rather than per
module — which needs a walker over constructed clause-head term instances
(fields hold `LoadName` nodes by Step 3). Alternative: have `_process_imports`
bind the atom str for owner-declared atoms and let the applied form be caught
by Task 4's O2 check, which already sees a str binding with no functor
signature (verify the diagnostic wording stays the same).

**Also from the same report (§6.3, §6.5), same area, lower priority:**
- Sub-shape 1 reroute covers clause BODIES only; an applied `k(a, 2)` in a
  clause HEAD argument keeps today's lowering.
- Sub-shape-1 call sites resolve through `_DbDispatchAdapter`, not the `$disp_`
  bake, because `_process_imports` still clobbers the local `PredicateMeta` with
  the imported atom str; declining to clobber would restore the bake but changes
  `getattr(mod, name)`, which Task 5b fenced off.
