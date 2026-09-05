# Copy-and-patch backend under the cell representation — evidence-based assessment

**Date:** 2026-09-05. **Method:** read-only inspection of `/workspace/clausal-copy_patch`
(primary, HEAD `94628650`, 2026-06-19), `/workspace/clausal-copy_patch_D` (HEAD `89a957d`,
2026-05-02), and the P3-2 worktree `/workspace/clausal-bug-fix/.claude/worktrees/p32-cell-flip`
(HEAD `7430e327`). No writes, no builds, no test runs anywhere.

## 0. Which checkout is primary

`/workspace/clausal-copy_patch` is the furthest-evolved and a strict superset.
`_D`'s Plan D series (`c4b5b0f`..`dbbbbe8`, "TrampolineDriver C iterator",
"StencilDispatchIterator C iterator", "resume_dispatch_fn in C") is present in the
primary checkout as rebased commits `15e7d84d`, `7973f41c`, `c6ba5ea8`, `6448826f`,
`51532c71`. `_D` stops at 2026-05-02 / 980 commits; primary runs to 2026-06-19 /
1192 commits and adds Phase 4c (jump-table dispatcher), Phase 4d (flex-array Frame),
Slice C (SegList deferred bind), Phase 8 D-2 (multi-suspendable tabled bodies),
Phase 9 D-4 (adapter deletion), the gc-on serial bench methodology, and five SLG
refcount-cycle fixes. **`_D` adds nothing the primary lacks.** All citations below are
to the primary checkout unless prefixed `_D:`.

---

## 1. Representation-coupling inventory

### 1.1 The stencil template library is essentially representation-free

`clausal/logic/runtime/stencils/templates/` — **102 `.c` templates**:

| family | count | representation coupling |
|---|---:|---|
| `fd_*.c` (CLP(FD) compare, 8 relations × 6 RHS shapes) | 48 | none — `PyLong_AsLongAndOverflow` on int slots |
| `arith_*.c` | 6 | none — same |
| `predicate_entry_{1..16}.c` | 16 | none — `resume_pc` jump table |
| everything else (unify, list-cons, build, frame, control flow, sub-call, yield) | 32 | delegating only |

**70 of 102 templates (69 %) cannot see a term at all.** Of the remaining 32, **zero
encode class layout in C**. Grep for CPython object-model APIs across all 102 templates
returns exactly two files (`unify_var_ground.c`, `unify_var_int.c`), and both use only
`PyLong_AsLongAndOverflow` / pointer identity — no `PyObject_GetAttrString`, no
`__match_args__`, no `_clausal_new`, no per-functor class identity.

The reason is architectural: every term operation exits the stencil through the
`Runtime` function-pointer table (`stencils/stencil_frame.h:388-470`) —
`rt->unify`, `rt->deref`, `rt->trail_mark/undo`, `rt->head_list_cons_unify`,
`rt->build_list_cons`, `rt->alloc_vars_into_slots` — or through a `HOLE_*_FN`
Python callback (7 templates: `init_frame.c`, `build_term.c`, `body_py_callback.c`,
`multi_star_head_match.c`, `shallow_iter.c`, `sub_call_suspendable*.c`,
`list_cons_body_build.c`). `build_term.c:47-57` is the whole file: call the callback,
tail-call the continuation. The representation lives *behind* that table, not in it.

### 1.2 Where the coupling actually is — three places

**(a) Compile-time term-shape analysis in the lowering pass.**
`clausal/logic/compiler/lower_stencil/` is 11,572 LOC over 17 files. Grep for
class-representation markers (`is_term_instance|term_field_names|PredicateMeta|
_clausal_new|Compound|SegList|ConcreteSeg|VarSeg|StarUnpack|DictTerm|SetTerm|
type().__name__`) hits **178 lines**, concentrated:

| file | LOC | coupled lines |
|---|---:|---:|
| `predicate/term_walk.py` | 212 | 59 |
| `predicate/callbacks.py` | 1,949 | 48 |
| `predicate/head_args.py` | 662 | 39 |
| `lower.py` | 2,240 | 13 |
| `predicate/pipeline.py` | 930 | 8 |
| `predicate/slots.py` | 1,009 | 7 |
| the other 11 files | 4,570 | 4 |

`term_walk.py` is the worst: it *is* the class-term grammar
(`walk_term`/`rebuild_term`, `term_walk.py:64-113` and `:115-212`), rebuilding via
`dataclasses.replace` or `type(term)(**kwargs)` and reading fields with
`getattr(term, fname)`.

**(b) Runtime Python callbacks that CONSTRUCT terms.**
`FrameInitializer._invoke` (`callbacks.py:340-393`) materialises every head pattern
per fresh frame entry; `_make_pattern_materializer` (`callbacks.py:136-218`) hand-rolls
fast paths for `[Var]` and `[Var, *Var]` and falls back to `_build_head_pattern` →
`rebuild_term`. `_BodyPatternBuilder` (`callbacks.py:395-511`) does the same for body
operands. `_MultiStarMatcher` (`callbacks.py:1585-1680`) enumerates list splits in Python.

**(c) `rt->unify` itself.** `clausal/logic/variables/_variables.c:1096-1109` handles
tuples element-wise in C. Class-instance compounds do **not** reach that branch: they fall
to the `__unify__` protocol probe at `:1197` (`PyObject_GetAttrString`, twice, with an
`AttributeError` allocated per miss), which lands in the **Python** `__unify__` that
`PredicateMeta` generates — `clausal/logic/predicate.py:98-112` — a `for f in fields:
unify(getattr(self,f), getattr(other,f), trail)` loop that re-enters C `do_unify` per
field. **Every compound unification under the class representation is a C→Python→C bounce
per node.**

**(d) Head extraction.** `head_args.py:322-345`: heads that are `PredicateMeta`
instances are read with `term_field_names(head)` + `getattr` per field; anything that is
neither `Call`/`Compound`/`PredicateMeta`-instance raises `UnsupportedShape` and the whole
predicate falls back to the Python backend.

### 1.3 Runtime C helpers

| file | LOC | representation-coupled lines (grep) |
|---|---:|---:|
| `runtime/_list_unify.c` | 820 | 61 (SegList/ConcreteSeg/VarSeg construction + walk) |
| `runtime/_dispatch_helpers.c` | 2,145 | 11 |
| `runtime/_trampoline.c` | 1,100 | 5 |

**Summary of the inventory: ~5 % of the parked backend's own code touches term
representation, and none of it is in the native templates.** The coupling is in the
compile-time head/body analyser, three Python callbacks, and the shared `do_unify`
protocol — plus the fact that the class representation *forces* those callbacks to exist.

---

## 2. What the cell flip changes, area by area

### 2.1 Gets structurally simpler / faster

| coupled area | today (classes) | post-flip (cells) |
|---|---|---|
| **`rt->unify` on compounds** (`_variables.c:1096` vs `:1197`) | `GetAttrString("__unify__")` ×2 → Python loop → re-enter C per field | falls straight into the existing `PyTuple_Check` element-wise branch; **the whole tree unifies in C with zero Python frames**. Slot-0 is str-vs-str (interned pointer compare first). This branch already exists and needs no edit. |
| **head extraction** `head_args.py:322-345` | `term_field_names` + `getattr` per field, `UnsupportedShape` for anything exotic | a cell head arg is `arg[0]` (functor) + `arg[1:]` (args) — `PyTuple_GET_ITEM` |
| **head-pattern materialisation** `FrameInitializer._invoke` + `_make_pattern_materializer` | recursive Python `rebuild_term` / hand-rolled per-shape closures | a compound pattern is a tuple literal; a `BUILD_CELL` stencil calling `PyTuple_New` + N slot writes is a ~15-line template in the shape of the existing `build_var_list.c`. **The 57 %-of-wall callback that started this whole project becomes a C template.** |
| **functor test in a head arm** | `MatchClass` (~114 ns first arm, ~178 ns second — spec `tagged-tuple-term-representation.md:242-244`) | `MatchSequence([MatchValue(functor), *args])` (`head_match.py:76-96`) — ~48 ns / ~85-102 ns; in C, a `PyTuple_GET_ITEM(t,0)` pointer compare against an interned str |
| **first-arg index key** | `(type(a).__name__, len(term_field_names(a)))` — an isinstance chain + a `dataclasses.fields()` call + tuple build + hash, per dispatch (`arg_index.py` `_runtime_arg_key`) | `(arg[0], len(arg)-1)` from slot 0 — landed on the branch at `arg_index.py:96-103` |
| **compile-time `term_walk.py`** | 212 LOC of grammar over 8 node kinds | a cell is `type(x) is tuple` + slot recursion; the walker collapses to a handful of branches |
| **`_stencil_data_*` / stitcher / catalog** | — | unaffected (2,558 + 455 LOC, pure ABI machinery) |

### 2.2 Needs rework (the lowering emits against machinery that has moved)

- `head_args._extract_head_args` (`:322-345`) will **reject every cell head** —
  `isinstance(type(head), PredicateMeta)` is false for a tuple, so it raises
  `UnsupportedShape(category="head_shape")` and the predicate silently falls back.
  This is the same failure mode as the project's own **Key finding 1** (§3.1), rediscovered.
- `head_args._classify_head_arg` (`:223-300`) and `_is_cons_head_pattern` /
  `_top_level_multi_star_segments` need a cell arm; without it a compound head arg
  becomes a generic `_HeadPatternArg` materialised in Python — the slowest path.
- `term_walk.walk_term` (`:64-113`) has an `isinstance(term, (list, tuple))` branch that
  would walk a cell's **functor slot as if it were an argument**. `rebuild_term` (`:158-160`)
  would rebuild it as a plain tuple, which happens to be structurally right but semantically
  blind — free-var collection over head patterns would over-count.
- `callbacks._make_pattern_materializer` fast paths key on `list` / `StarUnpack` shapes;
  cells need a new arm (or, better, deletion in favour of a `BUILD_CELL` stencil).
- `arg_index` / `list_dispatch` interactions: the branch has already rewritten these
  (commits `9faba7df`, `431a42a2`, `a1248260`), including a new `_is_deeply_ground`
  budget-bounded gate — the parked lowering has no notion of it.

### 2.3 Unaffected

Everything the parked project actually spent its last three months on: the
`resume_pc` ABI (v9), the flex-array Frame, `predicate_entry_{1..16}` jump-table
dispatch, `POST_CHILD_RETRY`, `SUB_CALL_SUSPENDABLE` / multi-suspendable slots,
the SLG integration (Phases 5-7), the FD/arith template families, the trail
protocol, the frame slab allocator, the stitcher, the extractor
(`tools/extract_stencils.py`), and the whole benchmark harness.

### 2.4 Cross-check against spec §3c ("optimisations the representation unlocks")

`tagged-tuple-term-representation.md:327-372` lists 8. Relevance to the stencil world:

- **#4 cheap deep indexing** (`PyTuple_GET_ITEM` for multi-level/joint keys) — directly
  serves `arg_index` and would let a stencil do its own key extraction in C. **Real.**
- **#8 a C standard-order comparator** — removes the last funnel accessor with no C twin. **Real.**
- **#2 maximal structural sharing in copy_term** — helps tabled-answer copying,
  which is `bench_tabling` / `wrap_fib` territory. **Real but off the stencil hot path.**
- **#1/#3 hash-consing + self-keying tabling** — needs `Var.__hash__ = None` (§5) and is
  gated behind the interning hook, which the P3-2 handoff (item 10) says stays **OFF**
  because "the measured shape was negative". **Not available today.**
- **#5/#6/#7 columnar stores, marshal serialization, no class minting** — orthogonal to stencils.

---

## 3. The 2× plateau — autopsy from the repo's own ledgers

### 3.1 The starting point WAS representation, unambiguously

`benchmarks/STENCIL_AB_FINDINGS.md:1` (2026-04-22), the first A/B:

- **Key finding 1** (`:51-75`): *"every predicate in `clausal/examples/*.clausal` falls
  back to trampoline… Clausal's predicate heads (e.g. `Fib(N, F)`) are `PredicateMeta`-
  instance dataclasses, not `Call` or `Compound`. `_extract_head_args` rejects these with
  `unsupported head shape Fib`."* The class representation made the backend **unmeasurable
  on every committed workload**.
- **Key finding 2** (`:76-118`): stencil-eligible predicates ran **4-13× SLOWER**
  (`id2(X,Y) <- X = Y`: 13.73× at 10 000 reps; `append/3` concat: 4.63-6.72×).
- **Key finding 3** (`:110-147`), the cost split on `append/3` (size 50, 200 reps,
  stencil 0.437 s):
  - **57 %** `FrameInitializer._invoke` — Python head-pattern materialisation
  - **33 %** `SegList.__unify__` — Python term unification reached from `rt->unify`
  - **~10 %** ctypes dispatch entry/exit
  - **~0 %** the native stencils themselves

  That is **90 % of the gap in term construction and term unification**, both
  Python-resident *because of the representation*.
- `STENCIL_OVERHEAD_SKETCHES.md:1-16` records the same split and frames all three
  planned sketches around it.

### 3.2 The second representation crisis, and how it was closed

`audit/seglist_walk_asymmetry.md` (2026-05-07). Phase 4c-2's cap lift routed
`partition/4` and `Qsort/2` onto stencil for the first time and **`bench_qsort`
regressed 0.983× → 2.428×**. Attribution (`:96-118`):

```
 76 000 calls  0.227 s tottime  SegList.__walk__          (terms.py:213)
152 000 calls  0.061 s          _variables.walk           (downstream)
bench-wall breakdown of the 0.176 s post-B2.b stencil run:
  ~50 ms  SegList walk, consumer side
  ~25 ms  SegList construction, producer side (~400 ns per construction,
          3 dataclass __init__ at ~58 ns each)
  ~91 ms  pre-4c floor
```

Fixed by **Slice C** (`14175b0`) — not by changing the representation but by
*deferring the bind to SOLUTION_YIELD* so the plain-list producer path could be reused.
`bench_qsort` 1.92× → 0.40×, **−152.5 pts** (`STENCIL_AB_FINDINGS.md:4787-4795`).
Actual saving ≈140 ms vs the 75 ms projected, "suggesting eliminating SegList chains
also eliminated downstream walk cascades".

### 3.3 What dominated AT parking time — classify (a)/(b)/(c)

The last full attribution is `STENCIL_AB_FINDINGS.md:3649-3745` (2026-05-01, min-bench):

```
graph stencil (86.7 ms):     isolated stencil exec + scaffold 55.1 ms (63.6 %)
                             FrameInitializer._invoke         12.7 ms (14.7 %)
                             body_callbacks                    6.3 ms  (7.3 %)
nqueens stencil (761 ms):    isolated stencil exec + scaffold  697 ms (91.6 %)
                             body_callbacks                     38 ms  (5.0 %)
                             ShallowCalleeAdapter._invoke       26 ms  (3.4 %)
                             FrameInitializer._invoke            0 ms
```

plus the residual register in `todo/jit_page_self_time_investigation.md:10-17`:
**`do_unify` shared 37 % of stencil graph wall**; JIT-page self-time 5.4 %.

Classification:

| dominant overhead at parking | share | class |
|---|---|---|
| `do_unify` (shared with default backend) | **37 % of graph wall** | **(a) representation-bound.** The `__unify__` GetAttrString→Python→C bounce is exactly what cells delete. |
| per-callback ctypes-thunk dispatch (~1.5 µs/fire) | ~16 ms graph / ~250 ms nqueens | **(b) boundary-bound.** Cells reduce the *number* of callbacks (materialisation moves into C) but do not make a surviving thunk cheaper. |
| stencil bytecode + per-iter scaffold ("architectural floor") | ~9 ms graph / ~46 ms nqueens over default | **(b).** Untouched by cells. |
| JIT-page self-time | 5.4 % graph | **(b).** Template codegen quality. |
| `FrameInitializer` Python work | 14.7 % graph, 0 % nqueens | **(a).** Head-pattern materialisation → `PyTuple_New`. |
| `StepGenerator` / trampoline protocol layers | `todo/stepgenerator_layer_simplification.md`, ledger NN=05 on graph | **(c) partly overtaken.** See §4.3. |

**Correction to the author's memory.** The 2026-05-01 doc concluded
*"until the stencil itself or its callback-dispatch ABI changes, no Python-side slice
closes the gap on graph"* and projected a floor of **1.47× (graph)**. That conclusion
was **falsified by the repo's own later work** — graph reached **0.559×** by 2026-06-20.
So the parking-time "architectural floor" narrative is stale; what actually broke it was
Phase 4c (jump-table dispatcher), Phase 4d (flex-array Frame), Slice C (a representation
workaround), Phase 8 D-2 (multi-suspendable), and Phase 9 D-4 (adapter deletion) — mostly
(b)-class work, plus one (a)-class workaround.

### 3.4 The headline numbers at parking (source of truth: `benchmarks/bench_history.csv`)

Final recorded row set, `bench_history.csv` last 9 rows, commit `904523aa`,
timestamp `2026-06-20T06:26:34+00:00`, 40 samples, gc-on serial harness
(also reproduced in commit message `94628650`). **Ratio = stencil / default; lower is
faster; merge gate is ≤ 0.9×.**

| workload | default min (s) | stencil min (s) | ratio | speedup | gate |
|---|---:|---:|---:|---:|---|
| tabling | 0.7049 | 0.0819 | **0.116×** | 8.6× | ✓ |
| fib | 0.6793 | 0.1697 | **0.250×** | 4.0× | ✓ |
| qsort | 0.1482 | 0.0525 | **0.354×** | 2.8× | ✓ |
| cyclic_path | 1.0281 | 0.4922 | **0.479×** | 2.1× | ✓ |
| caller_color | 1.1554 | 0.6345 | **0.549×** | 1.8× | ✓ |
| graph | 0.0397 | 0.0222 | **0.559×** | 1.8× | ✓ |
| nqueens | 0.6551 | 0.4342 | **0.663×** | 1.5× | ✓ |
| wrap_fib | 0.6028 | 0.4197 | **0.696×** | 1.4× | ✓ |
| wrap_fib_runtime | 0.2172 | 0.2156 | **0.993×** | 1.0× | ✗ |

**Geometric mean 0.446× = 2.24× faster. Excluding the `tabling` outlier: 0.527× = 1.90×.**
The author's "around the 2× mark" is **exactly right as a geometric mean**, and it is a
mean over a range from 8.6× (tabling) to 1.0× (wrap_fib_runtime, the only gate failure).

Two caveats the ledger itself raises:
- The 2026-06-19 re-baseline commit (`94628650`) documents **~5 pts of environmental
  drift** on this machine over 5 weeks, verified by re-running the old code.
- The proposal's own targets (`COPY_AND_PATCH_BACKEND.md:2964`) were
  *"≥3× on N-queens, ≥5× on CLP(FD), ≥10× on specialized meta-interpreters"*.
  nqueens landed at **1.51×** — **half the target**. "2×" was the achievement, not the goal.

### 3.5 The parked backlog contains no representation item

All eight `benchmarks/opt_priority/*.ledger` files, at parking:

```
nqueens: 05 inline_predicates / 03 multi_star_matcher_per_call_enumeration
         02 jit_page_self_time / 02 mode_inference_skip_unify_on_bound
         02 per_builtin_stencil_lists
qsort:   04 per_builtin_stencil_lists / 02 jit_page_self_time
graph:   05 stepgenerator_layer_simplification / 04 jit_page_self_time
         03 head_exclusive_determinism_tightening / 02 c_direct_iterator_next_slot
         01 inline_predicates_multi_clause
wrap_fib:07 cb_migration_ledger_C9_TabledWrapperCallback
fib / tabling / caller_color / cyclic_path: EMPTY
```

Not one entry is representation-shaped. `mode_inference_skip_unify_on_bound` was closed
**NO-GO** — measured ~40 ns/skip, projected ~2 % (`graph.ledger`, citing
`audit/phase_10_mode_inference/b0_empirical_preflight.md`). The parked project had
**already routed around every representation cost it could reach from the backend side**;
what remained was boundary and codegen work. This is the strongest available evidence for
the "partly" in verdict (i).

---

## 4. Staleness and revival shape

### 4.1 Distance

- Rebase base: `git merge-base main origin/main` in the parked repo = **`d3f153ce`,
  2026-05-24 08:16 −0700** — which *is* the parked repo's `origin/main` tip, i.e. the
  branch was kept fully rebased onto canonical main until that date.
- **419 commits** on the parked branch since that base.
- **1,048 mainline commits** from that base to `5bcd66ec` (clone main), **1,075** to the
  P3-2 branch HEAD. **104 days.** 360 files changed under `clausal/`, +39,411 / −4,794.

### 4.2 The parked branch is almost purely additive

`git diff --shortstat d3f153ce..main -- clausal/ tools/ benchmarks/ tests/`:
**267 files changed, 67,540 insertions(+), 185 deletions(−).** Only **11 files under
`clausal/` were modified at all** (as opposed to added): `trampoline.py`, `tabling.py`,
`solve.py`, `compiler_v2.py`, `compiler/predicate.py`, `predicate.py`, `compiler/ir.py`,
and four `builtins/*` files — together **+1,196 / −152**. That is the entire integration seam.

Additions by category:

| category | LOC | share |
|---|---:|---:|
| tests | 25,113 | 38 % |
| native assets (`runtime/*.c`, `stencils/`, `tools/gen_*`, `tools/extract_stencils.py`) | 16,943 | 25 % |
| lowering pass (`compiler/lower_stencil/`) | 11,572 | 17 % |
| bench harness + ledgers + findings | 11,097 | 17 % |
| mode inference / determinism | 948 | 1 % |
| integration seam | 1,196 | 2 % |

### 4.3 Which subsystems BOTH sides rewrote

Changed-line counts between the P3-2 HEAD's file and the parked repo's file
(`diff | grep -c '^[<>]'`):

| file | divergence | who rewrote it |
|---|---:|---|
| **`compiler/ir.py`** | **19** | *neither.* See below. |
| `compiler/terms_to_goalop.py` | 127 | mainline, lightly |
| `compiler/predicate.py` | 613 | both (parked: stencil backend selection; mainline: +495/−62 incl. cell head lifting) |
| `logic/predicate.py` | 996 | mainline (+950/−13 — atoms, `_clausal_new`, signature machinery) |
| `logic/solve.py` | 576 | both (parked: non-generator `solve`/`call`; mainline: drive-loop refactor) |
| `logic/tabling.py` | 1,403 | both (parked: stencil SLG suspension; mainline: WFS + drive-loop) |
| `logic/compiler_v2.py` | 1,445 | both (parked: stencil dispatch install; mainline: strict-atoms per-module pools, toklex) |
| `runtime/_list_unify.c` | 604 | both (parked: `head_list_cons_unify` + `build_list_cons`; mainline: cell/list work) |
| `variables/_variables.c` | 963 | both (parked: frame slab pool + capsule slots; mainline: cell branches in `do_walk`/`c_copy_term`/`c_collect_vars`/`c_is_ground`) |
| `runtime/_trampoline.c` | — | **both, same file, same purpose.** Merge base 816 LOC → parked 1,100 (TrampolineDriver + StencilDispatch type cache) vs mainline 974 (`drive_to_root_yield` one-core + `_trampoline_py.py` twin, commits `ffd406b2`..`d172c973`, 2026-08-26/27). |

**Two findings that dominate the revival calculus:**

1. **`compiler/ir.py` is effectively identical across the entire 3.5-month gap and the
   whole atom+cell pivot.** The only diff is the parked branch's *own* additive
   `SubCall.arg_modes` / `ArgMode` (7+7+1 lines) plus a `:=` vs `is` docstring word.
   The same 16 `GoalOp` classes, same field names. **The lowering pass's input contract
   survived P3-1 and P3-2 untouched.** This is the single best revival asset in the repo.

2. **The VarAPI capsule header is a strict prefix.**
   `diff p32-cell-flip/clausal/logic/variables/_variables_capi.h copy_patch/…` yields
   **0 `<` lines and 60 `>` lines** — mainline added *nothing* to the capsule in 3.5 months,
   so the parked `_harness.py` offsets (`_CAPI_OFFSET_DEREF=24`, `TRAIL_MARK=48`,
   `TRAIL_UNDO=56`, `UNIFY=96`) are all still valid. The stencil ABI's foundation is intact.

Against that: the **drive-loop refactor genuinely collides**. Mainline consolidated
`trampoline` / `solutions` / `_drive_until_yield` into one C core `drive_to_root_yield`
(`_trampoline.c:541-700`) with a **mandatory pure-Python twin** (`_trampoline_py.py`,
396 LOC) and a parity corpus (`tests/test_trampoline_parity.py`). Plan D-1 and D-3
(TrampolineDriver in C, driver fast-path on type) are largely **subsumed** — and their own
measured contribution was noise (D-1: −0.4 pts, D-3: **+1.6 pts**, per
`STENCIL_AB_FINDINGS.md:4527-4531`). Plan D-2 and D-4 (**−3.6 pts and −2.7 pts**, the
only real Plan D wins) live in `_dispatch_helpers.c`, which is stencil-only and additive —
those survive intact. **The overlap costs the parked project ~2 of its 4 Plan D slices,
and specifically the two that measured as noise.**

### 4.4 Recommendation: new plan on post-P3-2 main, re-extracting durable assets

**A rebase is not sane.** Not because of textual conflict volume (only 11 files conflict),
but because:

- The one *semantically* hard conflict — `_trampoline.c` + the new mandatory Python twin —
  is exactly the file the parked branch's last perf strand rewrote, and mainline's version
  now carries a twin-parity contract the parked version has never seen.
- `tabling.py` (1,403 changed lines) has been rewritten twice independently: the parked
  branch's Phase 5-7 stencil SLG suspension vs mainline's WFS truth surface + delay sets.
  Reconciling those by rebase means replaying 419 commits against a moving SLG core.
- The lowering pass's **head/body analysis is now wrong by construction** (§2.2), so even
  a clean rebase produces a backend that silently falls back on every cell-headed
  predicate — the 2026-04-22 Key-finding-1 failure, again.
- `logic/predicate.py` (+950/−13) and the removal of data-functor class minting change
  what `_extract_head_args` is even looking at.

**The right shape is a new plan on post-P3-2 main that re-extracts:**

| asset | LOC | portability |
|---|---:|---|
| stencil template library (102 `.c` + `stencil_frame.h`) | ~9,800 | **verbatim**, minus the head-pattern materialisation callbacks it can now replace with a `BUILD_CELL` template |
| extractor + generators (`tools/extract_stencils.py`, `gen_arith_stencils.py`, `gen_predicate_entry.py`) | 1,291 | **verbatim** |
| stitcher + harness + stencil catalog data | 4,332 | **verbatim** (capsule offsets verified still valid) |
| `_dispatch_helpers.c` (StencilDispatchIterator, D-2/D-4) | 2,145 | **verbatim** — additive, stencil-only |
| bench harness, ledgers, 4,818-line findings log | 11,097 | **verbatim**, and it is the only calibrated A/B methodology in the repo (gc-on serial, 40-sample min, interleaved, noise %) |
| lowering *architecture* (17-file pipeline, op-kind registry, slot allocator, labels, linker, inliner, assemblers, callbacks base) | 11,572 | **~80 % portable**; ~1,500-2,500 LOC of head/body term-shape analysis rewrites against cell-shaped IR |
| `mode_inference.py` / `determinism.py` | 948 | portable; mode inference already measured NO-GO for its original purpose |
| integration seam | 1,196 | **rewrite** against the new drive loop / tabling / predicate |
| tests | 25,113 | ~70 % portable (the term-shape fixtures need cell forms) |

**Durable-asset fraction: ~70-75 % of the ~67.5 k added lines port with little or no change
(native assets 25 %, bench 17 %, most of the lowering 14 %, most tests 27 % — call it
~75 %); ~20 % is rework (head/body analysis, the Python term callbacks, the term-shape
fixtures); ~5 % is discard (the integration seam, Plan D-1/D-3, the SegList workarounds
Slice C built).** The `ir.py` identity result means the rewrite is *localised* — the
lowering pass keeps its input and its output (a stitch plan) and changes only its middle.

---

## 5. The verdict

### (i) "A lot of the difficulty was representation" — **PARTLY TRUE, and the timing matters**

**True at the start, decisively.** The very first A/B (`STENCIL_AB_FINDINGS.md:51-147`,
2026-04-22) found (1) the class representation made the backend *unmeasurable* — every
committed workload's `PredicateMeta`-instance head was rejected by `_extract_head_args`;
and (2) of the 4-13× slowdown on the workloads that *did* compile, **90 % was term
construction (57 %) plus term unification through Python (33 %)**, with the native
stencils contributing "~zero". Two of the three founding design sketches
(`STENCIL_OVERHEAD_SKETCHES.md`) exist solely to route around the representation.
The qsort crisis of 2026-05-07 (`audit/seglist_walk_asymmetry.md`) was a second,
independent representation blow-up — a 2.43× regression, 75 ms of it in `SegList.__walk__`
and dataclass `__init__`.

**False at the end.** By parking, all of that had been engineered around: `BUILD_VAR_LIST`,
`UNIFY_LIST_CONS_HEAD`, `init_frame_body_vars` in C, `LIST_CONS_HEAD_BIND_AT_YIELD`,
type-specialised UNIFY. The parking-time attribution (`:3649-3745`) is
**ctypes-thunk dispatch, stencil-bytecode scaffold, and JIT-page self-time**; the eight
`opt_priority` ledgers contain **zero** representation entries and the one mode-inference
lever was closed NO-GO at ~2 %. The one big representation-bound residual that *survived*
is `do_unify`'s **37 % of graph wall** — and even that is shared with the default backend.

So: **representation caused most of the early difficulty and forced ~5 % of the codebase
into shapes it would not otherwise have taken, but by 2026-06 it was no longer what was
holding the numbers back.** The honest framing is "cells would have made the road far
shorter and the code far smaller — they are less of a lever on the destination the project
had already reached."

### (ii) "Benchmarks should improve under cells" — **YES in specific, nameable places; NO in the places that actually dominated at parking**

**Where cells help:**
- **`do_unify` on compounds.** The class `__unify__` C→Python→C bounce per node
  (`predicate.py:98-112` reached from `_variables.c:1197`) disappears into the existing
  C tuple branch (`_variables.c:1096`). This is the 37 % bucket. **Biggest single win.**
- **Head-pattern materialisation.** `FrameInitializer._invoke` was 14.7 % of graph wall
  and 57 % of the original `append/3` wall. Under cells it is `PyTuple_New` + N stores —
  a `BUILD_CELL` stencil in the shape of the existing `build_var_list.c`, i.e. it stops
  being a callback at all.
- **Index-key extraction** — `(arg[0], len(arg)-1)` vs an isinstance chain +
  `dataclasses.fields()` + tuple + hash, per dispatch.
- **Head arm dispatch** — MatchSequence/literal ~48 ns vs MatchClass ~114 ns first arm
  (spec `:242-244`), and in C a pointer compare on an interned str.
- **Structure-heavy and tabling-heavy workloads** (`bench_tabling`, `wrap_fib`, `qsort`)
  where compound construction and copying dominate.

**Where cells do NOT help — expectations to keep honest:**
- **Per-callback ctypes-thunk dispatch, ~1.5 µs per fire** — ~16 ms on graph, **~250 ms on
  nqueens**. Cells reduce how *many* callbacks exist; a surviving thunk costs the same.
- **Stencil bytecode + per-iteration scaffold** — the ~10 µs/call on graph, ~7.5 ms/call
  on nqueens "isolated stencil exec" bucket, 63-92 % of stencil wall. Untouched.
- **JIT-page self-time, 5.4 %.** Template codegen quality. Untouched.
- **The whole FD/arith family (54 of 102 templates)** — integer arithmetic on `saved_vars`
  slots. Untouched. `bench_nqueens` and `bench_wrap_fib_runtime` are FD-dominated
  (`wrap_fib.ledger`: "~75 % of cprofile attribution" is shared CLP(ℤ)/fd_eq machinery) —
  **expect ~nothing from cells on the two workloads closest to the gate.**
- **`bench_fib`** — already 4.0×, no compound terms in the hot path.
- **A warning from the repo's own analysis:** `todo/done/type_specialized_unify_stencils.md:11-15`
  records that the **default** backend has a *higher* `do_unify` fraction than stencil
  (~50 %+ vs 37 %), so *"attacking `do_unify` generically would worsen the merge ratio."*
  Cells are exactly such a generic attack. **Expect the stencil/default *ratios* in
  `bench_history.csv` to get WORSE under cells even as absolute wall improves on both
  sides.** The 0.9× merge gate would need re-derivation; the existing ratio ledger is not
  a valid post-cell yardstick.

### (iii) Compounding toward the Scryer gap — **partly real, and one of the two headline numbers is being double-counted**

The two numbers cited:

- **"walkers 13-25× on cells"** — this is from `f35db0f4` (P3-2 Task 2C):
  *"Micro A/B (min of 7 interleaved rounds, 5000 iterations), **Python twin vs C**:
  copy_term 3.9× on the cell-free 30-deep Compound chain … 25× on a 30-deep cell chain,
  13× on a meta-interpreter-shaped mix; term_variables 6.6×/15.5×; ground/1 13×/25×."*
  **This is C-vs-Python-twin, not cells-vs-classes.** It measures the *recovery* of the
  C fast path after Task 2 had temporarily forced the Python twins to run unconditionally
  (because `c_copy_term` / `c_collect_vars` / `c_is_ground` had no tuple branch). It is a
  restoration to par, not a new headroom the stencil backend can also bank.
  **Do not compound this with anything.**
- **"struct_tabling 1.83× vs pre-flip base"** — from `9faba7df` (P3-2 Task 4):
  *"Spot A/B (bench_struct_tabling, interleaved, vs branch base 5bcd66ec): ~1.83× faster."*
  This **is** a genuine cells-vs-classes engine win, on a deliberately walker-heavy
  workload (spec §3c: "walker share 56 % of profile"). Predicted by the Phase-2
  measurement B/A = 0.561. **Real, and bankable — but it is a single spot check on the
  workload chosen to maximise it, and the branch's Task 9 formal perf gate has not run
  yet** (HEAD is at Task 8).

**Where compounding is real:**
- Cells make `do_unify`, `copy_term`, `term_variables`, `is_ground` and answer-copying
  faster **in C, underneath the stencil backend**. A stencil that calls `rt->unify`
  inherits that speedup directly — it does not bypass it. Same for the SLG answer path
  in `wrap_fib` / `tabling`.
- Cells **delete** stencil-side Python callbacks rather than speeding them up. That is
  additive with the (b)-class boundary work still on the backlog (`shallow_iter_inline_c_drive`,
  `cb_migration C-9`, `stepgenerator_layer_simplification`): fewer callbacks × cheaper
  remaining thunks genuinely multiplies.
- Cells make new templates *possible* that were impractical under classes: a `BUILD_CELL`
  template, a C standard-order comparator (spec §3c #8), C-side multi-level index keys
  (#4). Each is a new lever, not a rescaling of an old one.

**Where it is double-counting:**
- **A stencil that bypasses the Python walker does not also get the walker's C speedup.**
  Concretely: `BUILD_VAR_LIST` and `LIST_CONS_HEAD_BIND_AT_YIELD` already build terms in C
  without touching `copy_term`; the 3.9-25× C-walker numbers are not available to them a
  second time. Likewise `FrameInitializer`'s materialisation cost can be paid once — either
  by making the Python materialiser cheaper (cells) or by moving it into a template
  (`BUILD_CELL`) — not twice.
- **The 13-25× figure is C-vs-Python, so pairing it with a stencil speedup double-counts
  the same "get out of Python" move.**
- **The 2.24× stencil geomean and the 1.83× cell win are not multiplicative to 4.1×.**
  They overlap on exactly the term-construction/unification work both attack, and they
  are measured on disjoint workload sets (`bench_struct_tabling` is not in the stencil
  merge-gate nine). The defensible claim is: cells raise the *absolute* floor for both
  backends; the stencil backend's *marginal* contribution on top of a cell engine is
  smaller than 2.24×, concentrated in control flow, FD/arith, and dispatch — the parts
  cells do not touch.

**Net on the Scryer gap.** No 6-30× Scryer figure appears anywhere in either repo
(the only Scryer references are the PyO3 differential oracle and the CLP(FD) propagator
argument at `COPY_AND_PATCH_BACKEND.md:151-161`), so that target is unverifiable from
these artifacts. What *is* in the repo: the backend's own aspirational targets were
**≥3× on N-queens / ≥5× on CLP(FD) / ≥10× on meta-interpreters**
(`COPY_AND_PATCH_BACKEND.md:2964`), and nqueens shipped at **1.51×**. A cell-native
stencil backend is a credible route to close *that* shortfall — chiefly by making
compound-heavy predicates stencil-eligible in the first place and by deleting the
materialisation callbacks — but the 2.24× and the 1.83× should be treated as **overlapping
attacks on the same Python-boundary cost**, not as factors to multiply.

---

## Appendix — evidence trail

Parked repo (`/workspace/clausal-copy_patch`, read-only):
- `benchmarks/STENCIL_AB_FINDINGS.md:1,51-75,76-118,110-147,3649-3745,4510-4619,4725-4818`
- `benchmarks/bench_history.csv` (last 9 rows, `904523aa`, 2026-06-20T06:26:34Z)
- commit `94628650` message (re-baseline, per-workload gate table, env-drift note)
- `benchmarks/opt_priority/{fib,nqueens,qsort,graph,tabling,caller_color,wrap_fib,cyclic_path}.ledger`
- `implementation_plans/COPY_AND_PATCH_BACKEND.md:75-95` (non-goal "No new term
  representation"), `:151-161`, `:2964`
- `implementation_plans/copy_and_patch/STENCIL_OVERHEAD_SKETCHES.md:1-16,150`
- `implementation_plans/copy_and_patch/audit/seglist_walk_asymmetry.md:30-118`
- `implementation_plans/copy_and_patch/todo/jit_page_self_time_investigation.md:10-17`
- `implementation_plans/copy_and_patch/todo/done/type_specialized_unify_stencils.md:11-15`
- `implementation_plans/copy_and_patch/todo/done/mode_inference_skip_unify_on_bound.md:18-21`
- `implementation_plans/copy_and_patch/todo/README.md` (open-item register)
- `clausal/logic/runtime/stencils/templates/` (102 `.c`), `stencil_frame.h:388-470`
- `clausal/logic/compiler/lower_stencil/predicate/head_args.py:290-345,223-300`
- `clausal/logic/compiler/lower_stencil/predicate/term_walk.py:64-113,115-212`
- `clausal/logic/compiler/lower_stencil/predicate/callbacks.py:136-218,220-393,395-511,1585-1680`
- `clausal/logic/variables/_variables.c:1096-1109,1189-1233`
- `clausal/logic/predicate.py:98-112,123-162`
- `clausal/logic/runtime/stencils/_harness.py:441-466` (capsule offsets)

Cell-flip worktree (`/workspace/clausal-bug-fix/.claude/worktrees/p32-cell-flip`, read-only):
- `implementation_plans/tagged-tuple-term-representation.md:22-49,233-278,327-372,373-383,480-530`
- `implementation_plans/p32-cell-flip-handoff.md` (recon anchors 1-11)
- `implementation_plans/p32-cell-default-flip.md:547-565` (Task 9 perf gate, not yet run)
- commit `f35db0f4` (C walkers learn cells; the 3.9×/25×/13× micro A/B — **C vs Python twin**)
- commit `9faba7df` (slot-0 indexing; the ~1.83× `bench_struct_tabling` spot A/B)
- `clausal/logic/compiler/head_match.py:76-96` (`_cell_match_pattern`)
- `clausal/logic/compiler/arg_index.py:84-140` (cell index key), `:163-180` (`_is_deeply_ground`)
- `clausal/logic/compiler/terms_to_ast.py:558-561` (`cell_literal_ast`)
- `clausal/logic/cells.py:114,187-306`
- `clausal/logic/runtime/_trampoline.c:509-563,675-760,910-918` (one drive core)
- `clausal/logic/_trampoline_py.py` (mandatory Python twin)

Cross-repo diffs (read-only `diff`, changed-line counts):
- `compiler/ir.py`: **19** (parked's own `arg_modes` only)
- `variables/_variables_capi.h`: **0 `<` / 60 `>`** — mainline added nothing; ABI prefix stable
- `terms_to_goalop.py` 127 · `compiler/predicate.py` 613 · `logic/predicate.py` 996 ·
  `solve.py` 576 · `tabling.py` 1,403 · `compiler_v2.py` 1,445 · `_list_unify.c` 604 ·
  `_variables.c` 963
- merge base `d3f153ce` (2026-05-24); 419 parked commits since; 1,048 mainline commits to
  `5bcd66ec`, 1,075 to `7430e327`
- parked branch vs base: 267 files, **+67,540 / −185**; only 11 `clausal/` files modified
