# LLVM Backend — Investigation & Plan

Status: **proposal / investigation**. Nothing implemented. Sibling to `COMPILER_TARGET_ARCHITECTURE.md` §6 (which anticipates a native backend) and the Python backends under `clausal/logic/compiler/lower_python_*.py`.

## 1. Goal

A native code backend for the clausal compiler using **llvmlite** for IR emission and ORC for JIT, sharing the existing backend-agnostic `GoalOp` IR with the Python backends. Coexistence with the Python backends is required: LLVM-compiled predicates and Python-compiled predicates must interop in the same process.

## 2. What has to be lowered

Post-D5 IR (see `clausal/logic/compiler/ir.py`):

- **Control:** `Sequence`, `Alternate`, `Negate`, `Branch` (with optional reified-test / tabled-NAF hints)
- **Binding/constraint:** `Unify`, `Dif`, `StructuralEq`, `ArithEval`, `FDCompare`
- **Membership:** `MemberIn`
- **Calls:** `SubCall` (with `direct_bucket_ref`, `tail_recursive`, `destructive_reuse` hints), `MetaCall` (closed `kind` set over `once`, `call_nth`, `findall`, `bagof`, `setof`, `catch`, `throw`, `freeze`, `when`, `forall`, `naf_tabled`, …)
- **Low-level:** `ListPatternUnify`

Operands are raw logic-level terms: `Var`, `Compound`, scalars, `list`, `SegList`, `DictTerm`, `SetTerm`, `KWTerm`.

Python trampoline shape (the reference we're replacing): generators yield `(next_gen, value)` to a `while gen: gen, value = gen.send(value)` dispatcher (`clausal/logic/trampoline.py:96–132`). TRO rewrites tail-recursive calls to `while True` + arg reassignment. Trail is mark/undo around every `Unify` / `Alternate` / `MemberIn`. Shallow shape is nested generators + `_found` flags.

Head matching is currently Python `match`/`case` + list-star guards (`head_match.py:131–337`).

## 3. Architecture

### 3.1 Coroutine strategy: hand-rolled `Frame` + `tailcc`, not `llvm.coro.*`

Each nondet predicate becomes:

```
void pred(Frame* f, Runtime* rt)   ; calling convention = tailcc
```

with `Frame` a struct we own:

```
{ resume_pc: i32
, proceed:    Frame*       ; where to deliver solutions
, fail:       Frame*       ; where to resume on child exhaustion
, catcher:    Frame*       ; where thrown exceptions propagate
, trail_mark: i64
, saved_vars: [N × Term*]
, … predicate-specific slots
}
```

The three continuation slots replace a single `parent` pointer; see
`CONTINUATION_TCO_PLAN.md` §3 for the semantic model (why the three
concerns must be separate and what each one carries).  Normal calls
set all three to the caller's frame; tail calls set `proceed` to
the caller's `proceed` while keeping `fail` and `catcher` pointing
at the caller, so solutions bypass the caller's frame but completion
and exception routing still walk through it.

Entry block dispatches on `resume_pc` via `switch`. LLVM lowers dense switches to jump tables — codegen quality matches computed-goto. Resume = `musttail call tailcc @pred(frame, rt)` — the trampoline becomes implicit (tail calls don't grow the stack).

**Why not `llvm.coro.*`:**

- `retcon` is the cleanest conceptual fit but depends on `token` SSA values; llvmlite's Python IR builder has weak token support (numba/llvmlite historical issues) — ends up round-tripping textual IR through `parse_assembly`.
- Requires the CoroEarly/Split/Elide/Cleanup pass pipeline; llvmlite's new-PM exposes it but legacy MCJIT/PM paths silently drop the intrinsics.
- Opaque frame layout: the trail and any future GC can't walk live vars.
- We'd still need our own choicepoint stack.

Hand-rolled wins on layout control (trail-walkable frames, debuggable), and `tailcc` + `musttail` + SROA gives near-coro performance on hot paths.

**Computed-goto option:** LLVM supports `indirectbr` + `blockaddress(@fn,%bb)` and llvmlite exposes them (`branch_indirect`, `Function.blockaddress`). `blockaddress` is function-local, so this only works inside one mega-function. Default to `switch`; reach for `indirectbr` only if profiling demands it.

### 3.2 Shallow predicates: `fastcc` functions, often `alwaysinline`

Deterministic preds:

```
i1 @pred_shallow(Term* a0, Term* a1, Runtime* rt)   ; fastcc
```

Return `i1` success/fail. A trampolined caller does a plain call + branch on the result. Small ones get `alwaysinline`. Same module, same `Runtime*`; trail logging is unchanged.

### 3.3 Pattern matching: Maranget decision tree + `switch` on tag

Runtime term layout: `{ tag: i8, payload: union }` — tagged struct first; revisit NaN-boxing later behind benchmarks. `Compound = {tag=COMPOUND, functor_id: i32, arity: i16, args: Term*[]}`.

Head-match lowering:

1. Build a Maranget decision DAG over the clause heads (standard ML-style pattern compilation).
2. Emit: deref arg → `switch` on tag → on `COMPOUND`, `icmp eq` on `functor_id` → recurse per arg.
3. Default edge = next clause (or fail on the last).
4. Attach `!prof` metadata when JIT-indexing profile data is available (see §4.1).

`ListPatternUnify` lowers to explicit segment-scan loops — no LLVM magic needed, just plain IR + runtime helpers.

### 3.4 Unification and trail

`unify`, `deref`, `bind` live in a C `runtime.c` built as `runtime.so` and linked in via ORC. The IR calls them as normal externals. A later pass may inline a specialized `unify` for ground/constant-tag cases discovered at compile time (e.g. `unify(Compound(foo/2, …), Var)` → direct structure build + bind).

Trail: `mark` = load SP; `undo(mark)` = loop popping `(Var*, old_value)` back to SP. Pure LLVM, no intrinsics.

## 4. Fit with pending compiler proposals

### 4.1 JIT indexing (`todo/jit_indexing.md`)

The proposal — profile the first N calls, rebuild dispatch at a 10k-call threshold — fits LLVM *better* than Python:

- Profile counters live in the `Runtime*` struct; bump via a single load/add/store at dispatch entry.
- Threshold trip re-invokes the backend for that predicate with observed-frequency `!prof` metadata on the decision tree.
- Dispatch swap = atomic pointer store into a per-predicate function-pointer slot (ORC tracks the two module versions). No GIL / free-threading atomicity worry — plain pointer swap. Old `Frame`s in flight keep executing the old code; they're referenced by frame pointer, not by module.
- Old module stays loaded until the last in-flight frame retires (refcount on module version).

This is cleaner than the Python plan's "replace installed dispatch function" approach, and the concern raised in `todo/jit_indexing.md` about free-threaded atomicity of dispatch replacement disappears.

### 4.2 Inline body in dispatch (`todo/inline_body_in_dispatch.md`)

For single-clause buckets, mark the body function `alwaysinline`. LLVM handles the rest. No separate mechanism needed.

### 4.3 Target architecture doc

`COMPILER_TARGET_ARCHITECTURE.md §6` explicitly anticipates "explicit choice-point stack plus continuations, or a WAM-style environment frame" as a low-level strategy — the `Frame` + `tailcc` design matches that slot directly. The backend-agnostic `GoalOp` IR is the pivot point: JIT indexing and inline-body rewrites happen as IR-level transforms *before* backend selection, so they light up on both Python and LLVM from the same implementation.

## 5. Caching

### 5.1 Current state

There is **no compiler-level artifact cache**. Caching rides on CPython's import system:

- `.clausal` modules are compiled in-process via a source-to-code import hook (`tests/test_pycache.py` exercises this); CPython marshals the resulting module to `__pycache__/*.pyc`, source-hash invalidated.
- `PredicateMeta._get_dispatch()` memoizes the installed dispatch as a method reference — in-memory only, rebuilt per process.
- No content-hashed IR cache, no persistent dispatch cache.

### 5.2 LLVM cache design — embed bitcode in `.pyc`

LLVM codegen is *not* cheap per process, so we need a cache. The cleanest design **reuses `__pycache__/` by embedding the bitcode as a `bytes` literal in the generated Python AST**:

```python
_LLVM_BITCODE = b"\x42\x43\xc0\xde..."   # llvm.Module.as_bitcode()
_LLVM_SPECS   = {"pred/2": 0, "other/3": 1, ...}
_LLVM_ABI     = (LLVM_VERSION, RUNTIME_ABI_VERSION, BACKEND_VERSION)
```

CPython's marshal handles `bytes` natively; the blob ships inside the `.pyc` with no extra infrastructure. On module import, an init hook calls `llvmlite.binding.parse_bitcode(_LLVM_BITCODE)` and hands the module to ORC.

**Why this is better than a sidecar `__clausalcache__/`:**

- Zero new cache infrastructure; rides the mechanism `tests/test_pycache.py` already exercises.
- Invalidation is correct by construction: source change → `.pyc` thrown out → bitcode regenerated. No parallel invalidation logic, no race between `.pyc` and sidecar.
- One artifact per module (not N per-predicate files). Ships with the `.pyc` wherever it goes.

**Constraints:**

1. **AOT only.** `.pyc` is written once at source-compile time. Runtime JIT-indexing specializations (§4.1) produced *after* import cannot go back into the `.pyc` — they need a small separate store (specialization blobs keyed by profile histogram hash, under `__clausalcache__/specializations/`). This store is strictly additive; the AOT case, which dominates hit rate, is fully handled by `.pyc`.
2. **Size.** Bitcode for a large module may reach hundreds of KB. Acceptable — marshal stores `bytes` efficiently and this is smaller than most vendored wheels.
3. **Python version coupling.** A Python upgrade invalidates the `.pyc` and forces bitcode regen even though nothing LLVM-relevant changed. Minor one-time cost per upgrade.
4. **ABI version guard.** `.pyc` won't catch an llvmlite/LLVM upgrade on the same Python. Embed `_LLVM_ABI` as shown; module init checks it and falls back to recompilation on mismatch. Belt-and-braces: also fold `_LLVM_ABI` into the content hash used for the specializations store so stale specializations are discarded on upgrade.
5. **Shallow preds and `runtime.so`** are built once and shipped as binary artifacts outside this cache.

Slice L7 (§8) should be re-scoped accordingly: the primary path is the `.pyc`-embedded blob; the `__clausalcache__/specializations/` store only lands once L8 (JIT indexing hookup) needs it.

## 6. Python interop during transition

Every predicate gets a uniform `invoke(frame, rt)` entry regardless of backend. Python-lowered preds get wrapped in a shim that adapts between Python generator protocol and the `Frame`/`Runtime` ABI. The shim pays allocation + attribute-access overhead; the point of the LLVM backend is to move hot predicates *off* it, not to make the shim itself fast.

Term ownership during the transition: keep allocating `Compound`/`list`/`Var` via the Python C API so refcount semantics stay correct. The native backend still participates in refcounting at FFI boundaries. Move to an arena + trail-driven free only after the backend is stable (see §7, risk 3).

## 7. Open questions / risks

1. **Term representation** — tagged struct vs. NaN-boxed `i64`. Tagged struct first (simpler interop with existing Python `Var`/`Compound` during migration); NaN-boxing is a post-v1 benchmarking exercise.
2. **Python interop shim overhead** — dominates for calls that cross the boundary. Mitigation: fuse enough of a predicate's call graph into LLVM that hot loops never cross back. Probably requires a "build closure of hot preds" pass.
3. **GC / allocation** — current runtime relies on CPython refcounts for `Compound`/`list`. Options: (a) keep Python C API allocation (compatible, slow); (b) arena + explicit free on trail-undo (correct long-term). Start with (a); (b) is its own slice.
4. **`MetaCall` kinds with Python semantics** (`findall`, `bagof`, `setof`, `freeze`, `when`) — wrap Python callbacks initially; native implementations post-v1.
5. **llvmlite version** — need 0.41+ for the new pass manager and opaque pointers. Many tutorials predate opaque pointers and will mislead.
6. **Coro pipeline avoided** — if we ever *do* want `llvm.coro.*`, we'll need the new-PM pipeline wired up and textual-IR round-tripping for `token` values.
7. **Tabled predicates / `naf_tabled`** — tabling requires a shared table store. The LLVM backend calls back into the Python runtime's table store for v1; native tabling is post-v1.

## 8. Slice plan

Gate each slice on the existing Python backend staying green (baseline 10409 ex-trealla; see `memory/reference_test_baseline.md`).

**Phase P — Discovery spike (1–2 weeks, explicit go/no-go gate before L2).** The coroutine design is clear on paper; what needs validation is that the toolchain holds up in practice. Hand-write IR for a single nondet predicate (`member/2`) with the C runtime stub, and get the end-to-end `.pyc`-embed path working. Concretely, answer:

- Does `tailcc musttail` actually eliminate the stack on x86-64 Linux, ARM64 macOS, and Windows? (Ping-pong mutual recursion that would blow a C stack in seconds.)
- What llvmlite version is installed? Does it expose `tailcc`, opaque pointers, the new pass manager, `blockaddress`/`indirectbr`?
- ORC ↔ Python C API interop under refcounting: JITed code calling `Py_INCREF`/`Py_DECREF` across exceptions, under the free-threaded build. Soak test for leaks/segfaults.
- Does SROA actually scalarize frame fields with our store-before-tailcall / load-on-resume access pattern? (This is the whole perf argument for hand-rolled frames vs `llvm.coro`.)
- Bitcode round-trip through `.pyc`: emit → marshal via synthetic AST module → import → `parse_bitcode` → execute. Measure size.
- **Two-way interop shim** on a single predicate: JIT-compiled `member/2` called from a Python-lowered clause, and vice-versa, inside one solve. Most likely place to surface an architectural surprise.

If the spike surfaces a blocker (llvmlite token/tailcc gap, refcount breakage under JIT, SROA failure), the design is re-scoped before further investment — possibly toward a WAM-shaped mid-IR (see §9) or a C backend instead of direct LLVM IR emission.

- **L0 — Scaffolding:** add `clausal/logic/compiler/lower_llvm/` package; wire llvmlite import behind a feature flag; no behavior change.
- **L1 — Runtime skeleton:** ship `runtime.c` with `Term`, `Var`, `Trail`, `unify`, `deref`, `alloc_frame`. Build as `runtime.so`, loaded via llvmlite ORC. Validate by hand-writing tiny IR that calls it. (L0+L1 together constitute Phase P.)
- **L2 — Shallow backend:** `lower_llvm_shallow.py` paralleling `lower_python_shallow.py`. Target only deterministic preds. Side-by-side test against the Python backend on a test subset.
- **L3 — Frame + tailcc for nondet:** `lower_llvm_trampoline.py`. Implement `Sequence`, `Unify`, `Alternate`, `SubCall` first. `switch` on `resume_pc`.
- **L4 — Head matching:** Maranget decision-tree builder, reusing pattern extraction from `head_match.py`. Emit `switch` tree.
- **L5 — Remaining IR ops:** `Branch`, `Negate`, `MemberIn`, `ArithEval`, `FDCompare`, `ListPatternUnify`, `Dif`, `StructuralEq`.
- **L6 — `MetaCall`:** most kinds call back into Python runtime via FFI shim initially; `once` / `call_nth` / `catch` / `throw` lowered natively.
- **L7 — Bitcode cache:** implement `__clausalcache__/` artifact cache (§5.2). Load path first; specialization-blob path after L8.
- **L8 — JIT indexing hookup:** once `todo/jit_indexing.md` lands on the Python side, extend the trigger to re-emit LLVM bitcode with `!prof` metadata and swap function pointers via ORC. Verify old in-flight frames keep executing the old module correctly.
- **L9 — Inline-body in dispatch:** mark single-clause bucket bodies `alwaysinline`; measure.

Each slice is a standalone, reviewable change with its own tests. L0–L2 can land without committing to the full architecture — they're a spike that validates the toolchain.

## 9. WAM-shaped mid-IR — deferred, but on the table

The plan as written lowers `GoalOp` → LLVM IR directly. The standard compiler-textbook path is high-level IR → **register-machine IR** → native; Mercury's HLDS → MLDS → C/LLVM is exactly this, and for the same reason — the register-allocated intermediate makes native emission close to mechanical.

A WAM-flavored mid-IR (explicit argument registers, explicit choicepoint/trail ops, explicit environment-frame slots — `put_variable`, `get_structure`, `try_me_else`, `retry_me_else`, `trust_me`, etc.) would make the LLVM emission pass close to a transliteration:

- `put_variable Ai, Xj` → one store
- `try_me_else L` → frame alloc + resume-PC store
- `get_structure f/n, Ai` → tag check + functor compare + arg-pointer loads
- `call p/n` → `musttail call tailcc @p(frame, rt)`

It would also give the JIT-indexing rewrite a uniform low-level shape to operate on (much easier than rewriting a tree-shaped `GoalOp`), and it would be a natural spot to hang a future C backend if the LLVM toolchain ever proves too fragile.

**Not for v1.** The `GoalOp` IR is small enough that direct lowering is tractable. Introduce the mid-IR **if and when** direct lowering starts growing hair — the likely trigger is `MetaCall` dispatch, or the JIT-indexing rewrite in L8 turning ugly. This is an architectural escape hatch to keep in mind, not a slice to schedule up front.

**Explicitly not the same as "WAM interpreter in Python".** Running a bytecode dispatch loop in Python would be a perf regression — CPython's own eval loop already specializes the AST we emit. The mid-IR here is compile-time only; it exists as a data structure that feeds LLVM emission, never as an interpreter.

## 10. Bottom line

Hand-rolled `Frame` + `tailcc musttail` + `switch`-on-`resume_pc` + Maranget decision trees, shallow preds as `fastcc` (often `alwaysinline`), C runtime for `unify`/deref/trail, bitcode embedded in `.pyc` as a `bytes` literal with a small sidecar store for runtime JIT specializations. Skip `llvm.coro.*` and `indirectbr` until profiling justifies them. Phase P discovery spike before committing to L2+. Mid-IR in reserve for when direct lowering stops scaling. The existing IR separation and the pending JIT-indexing / inline-body proposals align with the design rather than fighting it — the LLVM backend is additive, not a rewrite.
