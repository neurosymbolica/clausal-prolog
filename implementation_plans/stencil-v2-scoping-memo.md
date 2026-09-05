# Stencil-v2 scoping memo (copy-and-patch backend revival, post-cells)

**Written:** 2026-09-05, at P3-2 (cell default flip) close-out. **Source:**
`implementation_plans/copy-patch-cells-assessment-2026-09-05.md` — a read-only, evidence-
based inspection of the parked copy-and-patch stencil JIT (`/workspace/clausal-copy_patch`,
parked ~2026-06-20 at geomean 2.24x vs the default backend) against the P3-2 cell
representation. Read that document for the full evidence trail; this memo is the scoping
summary the assessment's own timing ruling asked for. Memory: `copy-patch-backend-status`.

**This is a scoping memo, not a plan.** It does not authorize starting stencil-v2 work. The
assessment's timing ruling (2026-09-05, recorded in the P3-2 ledger) is explicit: the
full revival plan comes **after P3-3**, because P3-3's state relocation changes the exact
integration seam the revival needs to target (see "What rewrites" below).

## What revives (durable, ~70-75% of the parked branch's ~67.5k added lines)

| asset | LOC | portability |
|---|---:|---|
| stencil template library (102 `.c` files + `stencil_frame.h`) | ~9,800 | **verbatim** — 70 of 102 templates never see a term at all; zero encode class layout; grep for CPython object-model APIs across all 102 hits exactly 2 files, both int-only |
| extractor + generators (`tools/extract_stencils.py`, `gen_arith_stencils.py`, `gen_predicate_entry.py`) | 1,291 | **verbatim** |
| stitcher + harness + stencil catalog data | 4,332 | **verbatim** — the VarAPI capsule header is a strict prefix of the current one (0 removed lines, 60 added, over the whole 3.5-month gap): `_CAPI_OFFSET_DEREF=24`, `TRAIL_MARK=48`, `TRAIL_UNDO=56`, `UNIFY=96` are all still valid offsets |
| `_dispatch_helpers.c` (StencilDispatchIterator, Plan D-2/D-4) | 2,145 | **verbatim** — additive, stencil-only; these are specifically the two Plan-D slices that measured as REAL wins (−3.6 and −2.7 points), unlike D-1/D-3 (measured as noise, and largely subsumed by mainline's drive-loop refactor anyway) |
| bench harness, ledgers, 4,818-line findings log | 11,097 | **verbatim** — the only calibrated A/B methodology in either repo (gc-on serial, 40-sample minimum, interleaved, noise %) |
| lowering *architecture* (17-file pipeline: op-kind registry, slot allocator, labels, linker, inliner, assembler, callback base) | ~11,572 total, ~80% portable | **`compiler/ir.py` — the lowering pass's INPUT contract — changed 19 lines across the entire 3.5-month gap and the whole atom+cell pivot.** Same 16 `GoalOp` classes, same field names. This is the single best revival asset in the repo: whatever P3-3 does, the shape a stencil compiler would consume from the existing IR is essentially untouched. |
| `mode_inference.py`/`determinism.py` | 948 | portable; already measured NO-GO for its ORIGINAL purpose (~2%) — re-evaluate purpose, don't assume it's dead weight |
| tests | 25,113, ~70% portable | term-shape fixtures need cell forms; the rest (control-flow, arithmetic, dispatch-shape tests) transfers |

## What rewrites (smaller under cells — the head/body analysis, not the templates)

- **Compile-time term-shape analysis in the lowering pass**
  (`clausal/logic/compiler/lower_stencil/`, ~1,500-2,500 of the ~11,572 LOC): grep for
  class-representation markers (`is_term_instance`, `term_field_names`, `PredicateMeta`,
  `_clausal_new`, `Compound`, `SegList`, `type().__name__`) hits 178 lines, concentrated in
  the head/body term-shape analysis that decides what a predicate's dispatch pattern looks
  like. Under cells this analysis is SMALLER, not just different: a cell's shape is
  `(functor, *args)` uniformly, so the branching the parked code needed to distinguish
  class-instance layouts from lists from compounds collapses. Concretely: `FrameInitializer`
  (the parked backend's head-pattern MATERIALISATION callback, 14.7% of graph wall and 57%
  of the original `append/3` wall at parking) becomes a `BUILD_CELL` template in the shape
  of the existing `build_var_list.c` — it stops being a Python callback at all.
- **The Python term callbacks generally** — every `HOLE_*_FN` callback that exists because
  the parked backend had to drop into Python to build or inspect a class-instance term can,
  in principle, become a native template once the term shape is a plain tuple. This is where
  most of the ~20% "rework" share of the 67.5k lines lives, and where the actual engineering
  effort of a revival concentrates.
- **The integration seam** (`compiler/predicate.py` stencil-backend selection, `_dispatch_fn`
  swap, ~1,196 LOC) — **complete rewrite, not adaptation.** This is the ~5% "discard" share.
  It must target whatever P3-3 builds for predicate-state/dispatch (see the stencil-seam
  planning input already folded into the P3-3 outline and handoff:
  `implementation_plans/p33-state-relocation-handoff.md`).

## The ratio-optics warning: re-derive the gate baseline post-cells

**Do not reuse the parked branch's `bench_history.csv` ratios as a revival gate.** The
assessment found a specific, named hazard: `todo/done/type_specialized_unify_stencils.md`
records that the DEFAULT (non-stencil) backend has a *higher* `do_unify` fraction than the
stencil backend (~50%+ vs 37% at parking), so "attacking `do_unify` generically would worsen
the merge ratio." **Cells are exactly such a generic attack** — they speed up `do_unify`,
`copy_term`, `term_variables`, and `is_ground` in C, underneath BOTH backends. A stencil
that calls `rt->unify` inherits that speedup directly; so does the default backend calling
the same C function. Expect the stencil/default *ratio* to get WORSE under cells even as
absolute wall-clock time improves on both sides. **Any revival plan must re-derive its own
gate baseline on cell-native code, not import the parked branch's historical ratios.**

## The double-counting caveat

Two numbers from this branch's own execution must NOT be multiplied together, and must not
be multiplied with the parked backend's 2.24x geomean either:

- **"Walkers 13-25x on cells"** (P3-2 Task 2C, `f35db0f4`) is **C-vs-Python-twin**, not
  cells-vs-classes. It measures the RECOVERY of the C fast path after the flip had
  temporarily forced the Python twins to run unconditionally (no tuple branch existed yet).
  It is a restoration to par, not new headroom a stencil backend can also bank.
- **"struct_tabling 1.83x vs pre-flip base"** (P3-2 Task 4, `9faba7df`) IS a genuine
  cells-vs-classes engine win, on a workload chosen to maximize it (walker-heavy). It is
  real and bankable, but it is a single spot check, and it and the parked backend's 2.24x
  geomean overlap on the exact same term-construction/unification cost — they are not
  multiplicative. The defensible framing: cells raise the *absolute* floor for both
  backends; a stencil backend's *marginal* contribution on top of a cell engine is smaller
  than 2.24x, concentrated in control flow, FD/arithmetic, and dispatch — the parts cells do
  not touch (see the assessment §5(iii) for the full accounting, including where a
  `BUILD_CELL` template and C-side multi-level index keys become NEW levers rather than a
  rescaling of old ones).

## Timing

1. **P3-3** (state relocation + qualified goals) — must land first; it changes the
   dispatch/predicate-state seam a revival plan would target. The stencil-seam planning
   input is already folded into P3-3's outline and handoff.
2. **Full stencil-v2 plan** — written after P3-3 merges, on post-P3-3 main, as a NEW plan
   (never a rebase of the parked branch — 419 vs 1,075+ diverged commits, with
   `drive-loop`/`tabling` rewritten independently and incompatibly on both sides). Re-derive
   the perf gate baseline on cell-native code before setting any numeric target.
3. Not before then. This memo and the source assessment are the scoping record for that
   future plan to start from — they are not a green light to begin re-extraction now.
