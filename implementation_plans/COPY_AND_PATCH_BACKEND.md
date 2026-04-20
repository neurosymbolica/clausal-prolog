# Copy-and-Patch Native Backend — Proposal

Status: **proposal / investigation**. Nothing implemented. Sibling to
`LLVM_BACKEND.md` (alternative native-backend technique — both lower
the same `GoalOp` IR to native code; they differ in *how* native code
is produced). Companion to `COMPILER_TARGET_ARCHITECTURE.md` §6
("Future backends") which anticipates a C / LLVM / WASM slot this
proposal fills.

---

## 0. TL;DR

Produce native code for Clausal predicates by **stitching together
pre-compiled C templates** ("stencils") at clause-compilation time,
patching in operand immediates via a tiny runtime. The templates are
compiled offline by `clang -O2` with a `tailcall` calling convention;
the runtime is a few hundred lines of C that does `memcpy` + relocation
patching + `mprotect`. No LLVM or Rust at runtime; no runtime code
generator in the traditional sense; validated at scale by CPython 3.13+'s
own JIT (PEP 744).

Compile time is memcpy-fast, which is the right shape for a logic
language that recompiles predicates on `assertz`/`retract` and compiles
tabled answers on the fly. Code quality is near LLVM `-O2` within each
template; quality at the seams grows over time by adding fused and
shape-specialized templates to the library. The lowering pass (GoalOp
→ selected-stencil sequence) is pattern matching over IR trees — a
natural fit to write in Clausal itself once the infrastructure is
stable, matching the project's self-hosting trajectory.

This is an **alternative** to `LLVM_BACKEND.md`, not a supplement.
Both cannot be primary. §10 compares the two in detail.

---

## 1. Goals and non-goals

### Goals

- Native code execution for compiled predicates, without a runtime
  codegen library (no llvmlite, no Cranelift, no MIR) and no Rust
  dependency.
- Compile-to-native latency measured in microseconds per predicate,
  so `assertz`/`retract` / tabled-answer compilation is imperceptible.
- Zero regressions in Python interop: compiled predicates call Python
  builtins, `++()` escapes, scipy wrappers exactly as today.
- Coexistence with the Python backend (shallow + trampoline
  strategies) — same process, same `Database`, same `PredicateMeta`.
- Template library that grows over time — initial slice is general,
  subsequent slices add fused and shape-specialized templates that
  the lowering pass selects when applicable.
- Debugging and correctness parity with the Python backend — every
  compiled native predicate is round-trip testable against a Python
  reference and against an external oracle (Scryer via the existing
  PyO3 embedding).

### Non-goals (explicitly)

- **No custom GC.** Terms remain PyObjects allocated by CPython,
  refcounted as today. See §7. (This matches `LLVM_BACKEND.md` §6.)
- **No new term representation.** Tagged-struct PyObject layout stays.
  NaN-boxing and arena allocation are post-v1 experiments, out of
  scope here.
- **No rewrite of the IR.** The `GoalOp` closed set defined in
  `clausal/logic/compiler/ir.py` is the input; this backend defines
  *lowering*, not IR shape.
- **No replacement of the Python backend.** Each predicate chooses a
  backend at compile time; Python remains the fallback for features
  this backend doesn't implement yet.
- **No self-hosting of the code generator.** The *lowering pass*
  (GoalOp → stencil sequence) is a candidate for Clausal self-hosting
  (§9); the *stitcher* (patch + mprotect + execute) stays in C.

---

## 2. Why this technique, for this language

The research path (LLVM → Cranelift → copy-and-patch) converges here
for four reasons specific to Clausal.

### 2.1 The instruction vocabulary is bounded and small

The `GoalOp` closed set is 15 core ops (`ir.py:Unify`, `Dif`,
`StructuralEq`, `ArithEval`, `FDCompare`, `Sequence`, `Alternate`,
`Negate`, `Branch`, `MemberIn`, `SubCall`, `MetaCall`, `Fail`,
`PyThunkOp`, `ListPatternUnify`) plus 17 `MetaCall.kind` values (`once`,
`call_nth`, `count_all`, `setup_call_cleanup`, `call_cleanup`,
`freeze`, `when`, `findall`, `bagof`, `setof`, `throw`, `catch`,
`catch_error`, `catch_recover`, `forall`, `halt`, `naf_tabled`). That
gives a natural upper bound on the base template set of ~30–40
templates. Copy-and-patch's sweet spot is "a VM with a fixed small
instruction set" — exactly this shape.

### 2.2 Compile time dominates steady state for a logic language

Logic programs recompile on:

- `assertz(fact(...))` / `retract(...)` in dynamic predicates.
- Tabled-answer installation during SLG resolution.
- `$load` of `.clausal` modules (mitigated by the existing `.pyc`
  cache — but cache misses happen on every new file and every source
  edit).
- Meta-interpreter specialization (see
  `META_INTERPRETER_SPECIALIZATION.md`) will generate residual
  predicates at query time.

LLVM's JIT measures in seconds per predicate; Cranelift in
milliseconds; copy-and-patch in microseconds. For interactive REPL
work and for workloads where predicates are specialized per query, the
qualitative latency difference matters.

### 2.3 Triska-influenced semantics unlock specialization that Prolog can't

Clausal has no cut. Reified if-then-else is a clean conditional.
Monotonic/pure code is the default. CLP(FD/B/Q/R) is the arithmetic
story, not `is/2`. Dynamic predicates exist but are marked
`-dynamic`; most predicates are static and compile-time analyzable.

These aren't stylistic preferences — they're the concrete properties
that make **determinism inference and mode inference tractable** on
Clausal programs where they are open research on general Prolog.
Mercury achieves Mercury-class performance by *requiring* these
annotations; Clausal can *infer* them on the monotonic-by-default
subset. That inference feeds into template selection: deterministic
predicates use cheap "just succeed or fail, no choice point" templates;
mode-known unifications use the read-only or build-only variants.

This specialization story is the *motivation* for copy-and-patch
over alternatives. General-purpose JITs don't know Clausal idioms;
a growing stencil library is exactly the shape of "bake in idiomatic
compilation, one pattern at a time."

### 2.4 CLP(FD) propagators are the largest under-exploited win

Scryer and SWI-Prolog ship general-purpose propagator frameworks.
Propagators are dispatched and their bodies interpret the constraint
they represent at runtime. Specialized-per-shape templates
(`all_different` of a known-size list; `#=` with one operand a
ground integer; linear constraint with constant coefficients) compiled
with full clang optimization would be competitive with hand-written
C constraint solvers, which Clausal could realistically beat Scryer
on. This is a backend-only win — no language changes, no user-facing
surface — and it's latent in the current architecture.

---

## 3. Relationship to existing plans

### 3.1 `LLVM_BACKEND.md`

Alternative technique for the same slot. Both lower `GoalOp` to
native code; both use a hand-rolled `Frame` struct for CPS-style
suspend/resume; both keep terms as PyObjects with Python refcounting;
both use a Maranget-style decision tree for head matching.

The difference is **where codegen happens**: LLVM plan emits IR
textually via llvmlite at clause-compilation time and runs LLVM's
backend; this plan pre-compiles C templates offline with clang and
stitches them at clause-compilation time. §10 compares tradeoffs.

If this plan proceeds, `LLVM_BACKEND.md` should be marked as an
archived alternative. The two approaches are **not composable** at
v1 scope — picking one commits the native-backend architecture.

### 3.2 `COMPILER_TARGET_ARCHITECTURE.md`

This plan fills the §6 "Future backends → C source backend" slot,
but takes the copy-and-patch variant rather than emitting `.c`
files for `cc` at compile time. The `GoalOp` IR, the Strategy
abstraction, the lowering-pass pattern, and the runtime/compile
boundary all stay unchanged. The new module is
`clausal/logic/compiler/lower_stencil.py` parallel to
`lower_python_{shallow,trampoline}.py`.

### 3.3 `CONTINUATION_TCO_PLAN.md`

The split-continuation protocol (`proceed` / `fail` / `catcher` as
three distinct continuation slots) is native to this plan — the
`Frame` struct has those three fields as first-class members, and
inter-predicate calls store them per call site. CPS-level TCO
becomes a direct tail-call at the machine level.

### 3.4 `META_INTERPRETER_SPECIALIZATION.md`

Partial deduction produces residual Clausal source that feeds back
through the normal compiler pipeline. With a copy-and-patch backend,
the residual predicates compile at microsecond latency, making
query-time specialization practical. The two plans are mutually
reinforcing.

### 3.5 `SCRYER_EMBEDDING.md` / `GPROLOG_EMBEDDING.md`

Scryer (embedded via PyO3) becomes the differential oracle for this
backend — any Clausal program whose semantics overlap with Scryer's
should produce identical solution sequences. This is the single
strongest validation asset for a native backend, and it's already
in-process.

---

## 4. Architecture

### 4.1 Pipeline shape

```
  .clausal source
       │
       ▼
  Parse + term expansion  (unchanged)
       │
       ▼
  compile_predicate(..., strategy=StencilStrategy())
       │
       ▼
  phases load → analyse → plan → head → body     (unchanged; same GoalOp IR)
       │
       ▼
  lower_stencil(goalop_tree, ctx)                 ← NEW
       │
       │   Produces a **stencil program**:
       │     - ordered list of (stencil_id, operand_values)
       │     - per-operand relocation kinds
       │     - entry point + frame layout
       │
       ▼
  stitcher.stitch(stencil_program, runtime_base)  ← NEW C runtime call
       │
       │   For each (stencil_id, operands):
       │     memcpy(dest, stencil_bytes[id], stencil_size[id])
       │     for each reloc in stencil_relocs[id]:
       │         value = resolve(operands[reloc.operand_idx],
       │                         runtime_base, dest, next_stencil_addr)
       │         apply_patch(dest + reloc.offset, value, reloc.kind)
       │
       ▼
  mprotect(..., PROT_READ | PROT_EXEC)
       │
       ▼
  install PyObject wrapper (PredicateMeta._dispatch_fn = ...)
```

The new artefacts are:

1. **Stencils** — per-opcode object-code blobs + relocation tables,
   generated offline at Clausal's *own build time* by clang from a
   fixed set of C source files. Shipped as data embedded in the
   Clausal wheel.
2. **Lowering pass** — `lower_stencil.py`: GoalOp tree → stencil
   program. Pure function. Selects templates (including fused and
   shape-specialized variants when applicable — see §6).
3. **Stitcher runtime** — a small C extension (target: a few hundred
   LOC) that takes a stencil program, allocates executable memory,
   copies and patches stencils, and returns a callable.
4. **Callable wrapper** — PyObject shim exposing the native entry
   point via `PredicateMeta._dispatch_fn`, so the trampoline and
   direct-call paths are oblivious to which backend produced the
   function.

### 4.2 Calling convention and frame layout

Identical in shape to `LLVM_BACKEND.md` §3.1 — this is deliberate; the
design work there applies here.

Each nondeterministic predicate compiles to one native function:

```c
void pred(Frame *f, Runtime *rt) __attribute__((musttail_expected));
```

with `Frame`:

```c
struct Frame {
    int32_t      resume_pc;        // state-machine entry selector
    struct Frame *proceed;         // where to deliver solutions
    struct Frame *fail;            // where to resume on child exhaustion
    struct Frame *catcher;         // where thrown exceptions propagate
    int64_t      trail_mark;
    PyObject    *saved_vars[N];    // predicate-specific; N is known at
                                   // lowering time
};
```

The three continuation slots match `CONTINUATION_TCO_PLAN.md` §3.
Tail calls set `proceed` to the caller's `proceed` while keeping
`fail` and `catcher` at the caller's frame, so solutions bypass the
wrapper but completion and exception routing still walk through it.

Resume is a state-machine dispatch on `resume_pc`, which after
stencil stitching is a dense `switch` → jump table in the emitted
code. Each yield-point is a labelled state; the stencil for
`SolutionYield` stores the next `resume_pc` into the frame before
tail-calling into `proceed`.

Deterministic predicates (shallow strategy) compile to a simpler
shape — a `fastcc`-equivalent function returning `i1` success/fail,
with no frame allocation. The stencil runtime distinguishes the two
via the strategy flag on the predicate class.

### 4.3 Stencil anatomy

A stencil is a **C function** written with *externs* as holes for the
runtime-variable operands, compiled with `clang -O2
-fno-pic -mno-red-zone` (target dependent) to produce object code
with relocation entries for each extern. Example:

```c
/* stencil: UNIFY_VAR_CONST  (unify register R with constant C;
   on success tail-call CONTINUATION; on failure tail-call FAIL). */

extern int32_t REG_NUMBER;        /* patched: register index       */
extern PyObject *CONSTANT;        /* patched: constant-term pointer */
extern void (*CONTINUATION)(Frame*, Runtime*);  /* patched: next stencil */
extern void (*FAIL)(Frame*, Runtime*);          /* patched: frame->fail  */

__attribute__((musttail))
void unify_var_const(Frame *f, Runtime *rt) {
    PyObject *v = f->saved_vars[(uintptr_t)&REG_NUMBER];
    int64_t mark = trail_mark(rt->trail);
    if (unify(v, &CONSTANT, rt->trail)) {
        /* on success: leave trail marked for later undo on backtrack */
        return ((void(*)(Frame*, Runtime*))&CONTINUATION)(f, rt);
    }
    trail_undo(rt->trail, mark);
    return ((void(*)(Frame*, Runtime*))&FAIL)(f, rt);
}
```

At Clausal's build time, clang compiles this to:

- A byte blob (the machine code of the function body).
- A relocation table: `{offset: byte_offset, symbol: "REG_NUMBER",
  kind: ABS32}` for each extern reference.

Offline tooling (`tools/extract_stencils.py`) reads the object files
(via `elftools`, `pyelftools`, or a minimal hand-rolled ELF/Mach-O
reader) and emits a Python module:

```python
# clausal/logic/runtime/stencils/_stencils.py  (generated)

STENCILS = {
    "UNIFY_VAR_CONST": Stencil(
        code=b"\x48\x8b\x7f\x00\x48\x8d\x35\x00\x00\x00\x00...",
        size=42,
        relocs=[
            Reloc(offset=3,  operand="REG_NUMBER",   kind=ABS32),
            Reloc(offset=7,  operand="CONSTANT",     kind=PC32),
            Reloc(offset=25, operand="CONTINUATION", kind=PC32),
            Reloc(offset=30, operand="FAIL",         kind=PC32),
            Reloc(offset=14, operand="unify",        kind=PLT32),
            Reloc(offset=36, operand="trail_undo",   kind=PLT32),
        ],
        entry="unify_var_const",
    ),
    ...
}
```

The generated module is checked in and loaded by the stitcher. It is
architecture-specific; the build produces one per supported target
(x86-64 Linux, aarch64 Linux, aarch64 macOS, x86-64 macOS,
x86-64 Windows). Cross-compilation via `zig cc` (already recommended
elsewhere in the ecosystem) keeps build-host independence.

### 4.4 Stitcher

A small C extension, `clausal/logic/runtime/_stencil_stitcher.c`:

```c
static PyObject *
stitch(PyObject *self, PyObject *args) {
    /* args: sequence of (stencil_id, operand_values, ...) */
    /* returns: PyCapsule wrapping an executable blob + its
                function pointer + a cleanup callback */
    ...
}
```

The whole stitcher is expected to be ~300–500 LoC of C. Operations:

1. Compute total size by summing stencil sizes.
2. `mmap(PROT_READ | PROT_WRITE)` a slab, page-aligned.
3. For each `(stencil_id, operands)`:
   a. `memcpy(cursor, stencil.code, stencil.size)`.
   b. For each reloc: compute the final value (an integer operand,
      a PyObject pointer, a runtime-function address, or a
      forward/backward offset to another stencil in the same slab),
      and write it at `cursor + reloc.offset` in the format the
      reloc kind dictates.
   c. `cursor += stencil.size`.
4. `mprotect(slab, size, PROT_READ | PROT_EXEC)` — never
   `PROT_WRITE | PROT_EXEC` simultaneously (W^X).
5. Wrap the entry pointer in a PyCapsule, returning a callable
   PyObject that invokes the blob via its C signature.

Relocation kinds supported: `R_X86_64_64`, `R_X86_64_32S`,
`R_X86_64_PC32`, `R_X86_64_PLT32`, `R_AARCH64_ABS64`,
`R_AARCH64_CALL26`, `R_AARCH64_ADR_PREL_PG_HI21`. CPython's JIT
(`cpython/Tools/jit/`) is a direct reference for what's actually
needed.

### 4.5 Head matching (Maranget decision tree)

Unchanged from `LLVM_BACKEND.md` §3.3. The decision-DAG builder
already has the algorithm planned; it produces a tree of
"deref → switch on tag → icmp on functor_id → recurse" tests.

In the stencil backend each decision node is a stencil instance:

- `DEREF_ARG_SWITCH_TAG` — loads arg, switches on `Term::tag`.
- `CHECK_FUNCTOR` — `icmp` on `functor_id`, branch.
- `MATCH_FAIL` — branch to next clause or fail continuation.

Stencil patching wires the `switch`-target addresses to the
appropriate downstream stencils in the same slab.

---

## 5. Caching

### 5.1 Parallel to `.pyc`-embed strategy

`LLVM_BACKEND.md` §5.2 proposes embedding LLVM bitcode in the `.pyc`
as a `bytes` literal. The stencil analogue is cleaner: the generated
native code for a whole module is a **stencil program** — a small
Python-serializable list of `(stencil_id, operand_values)` tuples, not
machine bytes. Since the stencils themselves are shipped with
Clausal, the module-specific cache holds only the selection and
operand values, which is compact and architecture-independent.

```python
# In generated .pyc for each .clausal module:
_STENCIL_PROGRAMS = {
    "append__3":      [(STENCIL_HEAD_MATCH_LIST, ...),
                       (STENCIL_UNIFY_VAR_VAR, 0, 1), ...],
    "reach__2":       [...],
}
_STENCIL_ABI = (STENCIL_SET_VERSION, RUNTIME_ABI_VERSION, TARGET_TRIPLE)
```

Advantages over the LLVM bitcode-in-pyc approach:

- **Architecture-independent cache content** — the `.pyc` is reusable
  across architectures if stencils exist for each (the operand values
  are just indices and pointers).
- **Smaller** — operand tuples compress better than bitcode.
- **Upgrade-safe** — stencil-set version bump invalidates cleanly
  via `_STENCIL_ABI`.
- **Reproducible** — identical source produces identical operand
  sequences; stencil bytes are the same across the world.

### 5.2 Runtime specializations

For JIT-indexing-triggered recompilation (profile-driven
specialization post-load), the specialized programs live in
`__clausalcache__/specializations/` keyed by profile histogram hash,
exactly as proposed in `LLVM_BACKEND.md` §5.2. Same mechanism; the
blobs are just much smaller.

---

## 6. Specialization pipeline

This is the durable win. The template set grows in phases; each new
template is a one-time template-authoring + stencil-regeneration cost
that pays off on every compiled predicate that uses it thereafter.
The lowering pass selects the most specialized applicable template.

### 6.1 Base set (phase P1 — ~30 templates)

One template per `GoalOp` kind, general (no mode/shape assumptions).

| Template                 | Lowers from          | Notes |
|--------------------------|----------------------|-------|
| `UNIFY`                  | `Unify`              | Generic unify(l, r, trail) + trail-mark/undo bracket |
| `DIF`                    | `Dif`                | `_dif` C call + attr-var constraint registration |
| `STRUCTURAL_EQ[_NEG]`    | `StructuralEq`       | No trail |
| `ARITH_EVAL`             | `ArithEval`          | Dispatch into CLP(FD) / native arithmetic runtime |
| `FD_<op>`                | `FDCompare`          | One per op ∈ {eq, ne, lt, le, gt, ge} |
| `SEQ_ENTER` / `SEQ_LEAVE`| `Sequence`           | Continuation threading |
| `ALT_PUSH` / `ALT_RETRY` / `ALT_TRUST` | `Alternate` | Classical try/retry/trust shape |
| `NEG_ENTER` / `NEG_LEAVE`| `Negate`             | NAF via nested-solver pattern |
| `ITE_REIFIED`            | `Branch` (reified_test) | Three-way if with deterministic test |
| `ITE_GENERAL`            | `Branch` (general)   | Nested-solver general ITE |
| `MEMBER_IN`              | `MemberIn`           | Iteration over collection |
| `SUB_CALL`               | `SubCall`            | Generic call through dispatch table |
| `SUB_CALL_DIRECT_BUCKET` | `SubCall` (hinted)   | Skip dispatch wrapper |
| `SUB_CALL_TAIL`          | `SubCall` (tail_position=True) | musttail to `proceed` |
| `TAIL_RECURSE`           | TRO-rewritten SubCall | Loop-restart |
| `META_<kind>`            | `MetaCall`           | One per kind (17 templates) — several (once, call_nth, catch, throw) are native; others (findall, bagof, freeze, when) tail-call into Python runtime initially |
| `LIST_PATTERN_UNIFY`     | `ListPatternUnify`   | Tail-calls into existing `_list_unify.c` helpers |
| `FAIL`                   | `Fail`               | Immediate tail-call to `fail` continuation |
| `PYTHUNK`                | `PyThunkOp`          | PyObject_Call with GIL-safe error path |
| `SOLUTION_YIELD`         | implicit at leaves   | Stores `resume_pc`, tail-calls `proceed` |
| `CHOICE_POINT_PUSH`      | at Alternate entry   | Frame alloc, trail mark |
| `CHOICE_POINT_POP`       | at Alternate exit    | Frame dealloc, trail undo |
| `PREDICATE_ENTRY`        | per predicate        | `switch(resume_pc)` dispatcher |
| `PREDICATE_DONE`         | per predicate        | Tail-call to `fail` continuation with DONE |

### 6.2 Shape specialization (phase P2)

Multiple templates per `GoalOp`, selected by the lowering pass based
on static term analysis.

**Unify:**
- `UNIFY_VAR_VAR` — both sides are Vars
- `UNIFY_VAR_CONST` — one Var, one ground constant
- `UNIFY_VAR_STRUCT` — one Var, one known-functor compound
- `UNIFY_CONST_CONST` — two ground values (specializes to `structural_eq`)
- `UNIFY_LIST_CONS` — head-tail list patterns

Each clang-compiled with full knowledge of the argument shapes; the
generic `UNIFY` becomes a fallback. This multiplies the base
`UNIFY` template by ~5 but eliminates runtime dispatch in the common
case.

**ArithEval / FDCompare:**
- `FD_EQ_GROUND` — both sides ground (becomes Python-int compare)
- `FD_EQ_VAR_CONST` — var #= const (domain-intersect)
- `FD_EQ_LINEAR` — linear constraint with constant coefficients

**SubCall:**
- `SUB_CALL_DET` — callee known deterministic (no frame alloc)
- `SUB_CALL_SEMIDET` — callee known at-most-one (no retry)

Shape information comes from the analyse phase —
`COMPILER_TARGET_ARCHITECTURE.md` §11 already specifies
`AnalysedPredicate` as the vehicle for this metadata.

### 6.3 Mode specialization (phase P3)

Requires mode analysis (phase P5 in §8). Per-mode variants of
`UNIFY` and `SUB_CALL`:

- `UNIFY_IN_VAR` — ground term vs var (becomes `bind`)
- `UNIFY_IN_IN`  — both ground (becomes structural-eq)
- `UNIFY_OUT_VAR` — fresh var vs var (becomes pointer copy)

This is where Mercury's class of wins becomes accessible — the
compiler emits the cheapest unification operation given mode
information.

### 6.4 Fusion (phase P4)

Common sequences fused into single templates, compiled with clang's
full optimizer crossing the boundary:

- `DEREF_THEN_UNIFY_VAR` — deref + unify fused
- `TRAIL_MARK_BODY_UNDO` — for known-local trail scopes
- `CHECK_FUNCTOR_EXTRACT_ARGS` — head-match operation cluster
- `SUB_CALL_THEN_YIELD` — common tail-position pattern

Fusion opportunities are discovered by profiling; each fusion is an
additive template library expansion, no change to existing code paths.

### 6.5 Domain-specific (phase P5)

- **CLP(FD) propagators**: `PROP_ALL_DIFFERENT_N`, `PROP_SUM_CONST`,
  `PROP_LINEAR_GROUND_COEFS`, `PROP_ELEMENT_ARRAY`. Each parameterized
  by shape; clang optimizes the propagator body per shape at build
  time.
- **Tabling**: `TABLE_LOOKUP`, `TABLE_SUSPEND`, `TABLE_RESUME`,
  `COMPLETION_CHECK`. First-class tabling ops rather than runtime
  library calls.
- **DCG-style state**: `DCG_STATE_READ`, `DCG_STATE_WRITE`.

These are Clausal-specific wins no general compiler can match.

### 6.6 Selection algorithm

The lowering pass walks the `GoalOp` tree; at each node it asks "what
is the most specific template applicable here?" and records the
selection. Selection is a pattern-matching problem over the
annotated IR — exactly what Clausal is good at. §9 argues this
selector is a natural candidate to self-host.

---

## 7. Memory management and Python FFI

### 7.1 Terms as PyObjects

Unchanged. Compiled native code allocates terms via `PyObject_New`
(or `PyObject_GC_New` for cyclic-capable types like Compound),
holds references via `Py_IncRef`/`Py_DecRef`. CPython's cyclic GC
handles Compound graphs that form cycles through `tp_traverse`
(already defined on the existing Python-side term classes; needs
ensuring the C-side allocator emits trackable objects).

The FFI boundary is trivial: every stencil can call into the existing
C-extension API (`unify`, `deref`, `_dif`, `put_attr`, etc.) by name
— these become relocations against symbols already exported by
`clausal/logic/variables/_variables.so`.

### 7.2 Refcounting overhead is accepted

§3 of the research note made this explicit. Cost: refcount traffic
on every term bind and rebind is the dominant allocation-heavy-path
cost. But this is *already* the cost today (every compiled Python
predicate refcounts as it binds), so the native backend doesn't
regress on this axis — it just doesn't improve it either. Arena
allocation for non-escaping terms is a post-v1 optimization slice
if profiling justifies it.

### 7.3 Free-threading (PEP 703)

Refcount ops go through `Py_IncRef` / `Py_DecRef` library calls,
never inlined `iadd`. This keeps the backend correct under PEP 703
nogil builds (atomic/biased/deferred refcounting). Stencils must
not be compiled with inlined refcount macros — they must call the
ABI functions.

### 7.4 `tp_traverse` requirement

Each term type that holds references to other terms needs a
C-level `tp_traverse` implementation. The existing term types
(defined in Python via `PredicateMeta` or as C types in
`_variables.c`) need audit; any that rely on Python-level
`__iter__`-based traversal must gain an explicit `tp_traverse`.
This is a small one-time change and must land *before* the native
backend is used in anger, or cyclic Compound graphs leak.

---

## 8. Staged roadmap

Gate each slice on the Python backend staying green (baseline
≈10,400 tests — see `memory/reference_test_baseline.md`). Each
slice is an independent, reviewable change.

### Phase P — Discovery spike (1–2 weeks, explicit go/no-go gate)

Mirrors `LLVM_BACKEND.md` Phase P, but for stencils.

- Hand-write three templates (`SEQ_ENTER`, `UNIFY`,
  `SUB_CALL`) as C source.
- Build stencil extractor (read ELF `.o`, produce Python data).
- Build minimal stitcher (`memcpy` + patch `PC32` and `ABS64` only).
- Hand-craft a stencil program for `member/2`, execute, validate
  against Python backend.
- Test `musttail` elimination on x86-64 Linux, aarch64 macOS,
  x86-64 Windows.
- Soak test: refcount balance across 10⁶ backtracks.

Go/no-go gate: if `musttail` fails on any supported target, or if
refcount leaks under failure paths, re-scope (fall back to C
codegen + cached `.so` files, or defer native backend entirely).

### Slice S0 — Scaffolding

- New subpackage: `clausal/logic/compiler/lower_stencil/`
  (parallel to `lower_python_*`)
- New runtime subpackage:
  `clausal/logic/runtime/stencils/` — stencil data, stitcher C
  extension, PyCapsule wrapper.
- Feature flag: `CLAUSAL_BACKEND=stencil|python` env var;
  `StencilStrategy` implementing the `Strategy` protocol.
- No behavior change; pipeline untouched.

### Slice S1 — Base stencil set (phase P1 above)

- Author ~30 template C files.
- Extend extractor to handle all needed relocation kinds.
- Implement `lower_stencil.py` for the general (non-specialized)
  case — one template per GoalOp kind, one per MetaCall kind.
- Predicate entry: `PREDICATE_ENTRY` (switch-on-resume) stencil.
- Validate by cross-testing a subset of predicates: compile with
  both Python and stencil backends, assert identical solution
  sequences via the existing test harness.
- Target: `append/3`, `member/2`, `reach/2`, simple arithmetic
  predicates, no meta-calls, no tabling, no CLP.

### Slice S2 — Head matching

- Implement Maranget decision-tree builder (shared with the LLVM
  plan in principle; extract to `clausal/logic/compiler/head_dag.py`).
- Head-match stencils: `DEREF_ARG_SWITCH_TAG`, `CHECK_FUNCTOR`,
  `MATCH_FAIL`.
- Groundness-keyed dispatch wired into stencil program assembly.
- Target: clause bodies with non-trivial head patterns compile and
  pass.

### Slice S3 — Shape specialization (phase P2)

- Add variant templates for `UNIFY_VAR_VAR`, `UNIFY_VAR_CONST`,
  `UNIFY_VAR_STRUCT`, `UNIFY_CONST_CONST`, `FD_EQ_GROUND`,
  `FD_EQ_VAR_CONST`.
- Extend lowering pass to pattern-match on operand shapes.
- Benchmark against S1 on a chosen corpus.

### Slice S4 — Cache integration

- `.pyc`-embedded stencil program blobs.
- `__clausalcache__/specializations/` store for runtime
  specializations.
- ABI-version guard + fallback path.

### Slice S5 — MetaCall kinds (non-Python-bound first)

- Native stencils for `once`, `call_nth`, `count_all`, `throw`,
  `catch`, `catch_error`, `catch_recover`, `forall`, `halt`.
- Remaining kinds (`findall`, `bagof`, `setof`, `freeze`, `when`,
  `setup_call_cleanup`, `call_cleanup`) tail-call into existing
  Python runtime via PyObject_Call — no regression, just no
  native win for these yet.

### Slice S6 — Determinism inference

- Implement a determinism-inference pass in `compiler/optimisations/`:
  output `det | semidet | multi | nondet` per predicate.
- Use inference results to select `SUB_CALL_DET` / `SUB_CALL_SEMIDET`
  stencils where applicable.
- Triska-style purity hints: predicates built purely from pure
  builtins, `->` reified ITE, and other deterministic calls
  inherit determinism.

### Slice S7 — Mode inference + mode specialization (phase P3)

- Mode inference pass (optional annotations, inferred where possible).
- `UNIFY_IN_*`, `UNIFY_OUT_*` templates.
- Propagates through call graphs.

### Slice S8 — Fusion (phase P4)

- Profile-driven identification of hot sequences.
- Add fused templates as the profile directs.
- Extend lowering pass to pattern-match fused sequences.

### Slice S9 — CLP(FD) propagator specialization (phase P5)

- Specialized propagator stencils by shape.
- Integration with existing CLP(FD) runtime
  (`clausal/logic/clpfd.py`).
- Benchmark against Scryer on a CLP(FD) corpus.

### Slice S10 — Tabling-aware compilation

- First-class tabling stencils: `TABLE_LOOKUP`, `TABLE_SUSPEND`,
  `TABLE_RESUME`, `COMPLETION_CHECK`.
- Integration with existing `clausal/logic/tabling.py`.

### Slice S11 — JIT-indexing hookup

- Tie into profile-driven dispatch rewriting (see
  `todo/jit_indexing.md` if present).
- Rebuild stencil program with updated dispatch tree on threshold trip.
- Atomic pointer swap; old blob stays alive until in-flight
  frames retire.

---

## 9. Self-hosting the lowering pass

The selector — walk an annotated `GoalOp` tree and emit a stencil
program — is a pure functional pattern-matching transformation over
structured terms. This is **Clausal's home turf**: a handful of
relations matching on GoalOp/operand structure, emitting stencil-id
+ operand-tuple terms.

```clausal
LowerOp(Unify(L, R), Ctx, [Stencil('UNIFY_VAR_CONST', REG, C)]) <- (
    IsVar(L), IsGround(R),
    RegisterIndex(L, Ctx, REG),
    ConstantHandle(R, Ctx, C)
)
LowerOp(Unify(L, R), Ctx, [Stencil('UNIFY_VAR_VAR', REG_L, REG_R)]) <- (
    IsVar(L), IsVar(R),
    RegisterIndex(L, Ctx, REG_L),
    RegisterIndex(R, Ctx, REG_R)
)
LowerOp(Unify(L, R), Ctx, [Stencil('UNIFY', L, R)]) <- (
    %% fallback — generic
    true
)
...
```

This is a natural match for the project's self-hosting ambitions
without requiring the stitcher or the GC or the parser to be
self-hosted. Scope of the self-hosting experiment is contained: one
pure pass, easily A/B tested against a Python implementation of the
same logic.

Not for v1. First implement the lowering pass in Python
(`lower_stencil.py`), validate it against a large test corpus, and
*then* consider porting to Clausal. At that point the self-hosting
slice is a mechanical reimplementation with behavioural equivalence
as acceptance criterion.

---

## 10. Comparison with `LLVM_BACKEND.md`

| Axis                                  | LLVM backend                      | Stencil backend                |
|---------------------------------------|-----------------------------------|--------------------------------|
| Runtime dependency (size)             | llvmlite + LLVM shlib (~70 MB)    | ~500 LoC C stitcher            |
| Compile latency per predicate         | seconds (LLVM optimization)       | microseconds (memcpy + patch)  |
| Steady-state code quality             | LLVM-O2 globally                  | LLVM-O2 per-template, seams unoptimized |
| Code quality trajectory               | Fixed by LLVM                     | Improves with template library |
| Runtime-codegen flexibility           | Arbitrary per-predicate IR        | Fixed template set             |
| Architecture support                  | All LLVM targets for free         | Per-target stencil build needed |
| Build-time complexity                 | llvmlite wheel                    | clang + stencil extractor      |
| Clausal-specific optimization         | General optimizer, unaware of logic idioms | Template library *is* the optimization |
| CLP(FD) specialization lever          | Per-call recompilation            | Per-shape templates at build time |
| Cache artefact                        | LLVM bitcode (arch-specific, ~MB) | Stencil program (arch-independent, ~KB) |
| Free-threading compatibility          | Same as any C ext                 | Same as any C ext              |
| GC story                              | CPython refcount + `tp_traverse`  | CPython refcount + `tp_traverse` |
| Self-hosting trajectory for lowering  | Possible but awkward (LLVM IR APIs) | Natural (pattern-match → stencil-id + operands) |
| Prior art at scale                    | Numba, rustc's alt-codegen        | CPython 3.13+ JIT (PEP 744)    |
| Maturity risk                         | llvmlite version matrix, LLVM ABI churn | New tooling, but pattern is validated |
| Reversibility                         | Replace with Cranelift / C codegen | Replace with LLVM backend      |

**Net:** LLVM wins on per-predicate code quality and flexibility for
programs where whole-predicate optimization matters. Stencil wins on
compile latency, runtime footprint, architectural alignment with
Clausal's bounded op set, and the specialization-pipeline trajectory
that turns the template library into the optimizer.

For Clausal's profile (Triska-influenced semantics, CLP(FD) central,
dynamic assert/retract, first-class tabling, self-hosting ambition),
stencil is the better fit. For a project where the hot path is
numeric kernels embedded in logic code, LLVM would be better. This
proposal argues the former, but §13 open questions include whether
to build both and switch by predicate.

---

## 11. Open questions / risks

### Q1. Is `tail` calling convention sufficient across targets?

The whole architecture depends on `[[clang::musttail]]` working on
x86-64 Linux, aarch64 Linux, aarch64 macOS, x86-64 macOS, x86-64
Windows (MSVC uses a different attribute syntax — `__declspec(
musttail_call)` is not the same). Phase P spike must verify this.
Fallback: trampoline in C (returning a next-stencil-pointer from each
stencil; the C driver loops). Performance cost: branch prediction on
one indirect jump per opcode. Tolerable.

### Q2. Do clang-emitted relocations match across clang versions?

Unlikely to change for basic relocation kinds (`PC32`, `ABS64`), but
needs version-pinning and CI against the supported clang range.
Mitigation: ABI version in stencil data + mismatch fallback.

### Q3. What happens with LTO-like cross-stencil optimization?

Pure copy-and-patch has the "unoptimized seams" problem. Partial
mitigation via fusion templates (phase P4). Deeper mitigation is
out of scope — it would require either tracing JIT (out of
technique) or LTO at stitch time (defeats the point).

### Q4. Exception safety

`LogicException` unwinding currently walks the `catcher` chain via
Python's `.throw()`. Native stencils must participate — either by
staying entirely within a C-level unwind (fast but needs DWARF or
hand-rolled landing pads) or by returning a sentinel that the
stitcher-emitted epilogue routes back to Python's exception machinery.
The latter is simpler and probably adequate; Phase P should
validate it.

### Q5. Debuggability

No DWARF info for stencil-stitched code by default. Options:

1. Emit side-table mapping code addresses → IR opcode → Clausal
   source line; use it in traceback formatting.
2. Ship debug variants of each stencil with DWARF, switch at load
   time under a debug flag.
3. Fall back to the Python backend when a debugger is attached
   (CPython's JIT does this).

Option 1 is the minimum viable debugging path; option 3 is the
best UX. Both are tractable, neither is free.

### Q6. Security: executable memory

`mprotect(..., PROT_READ | PROT_EXEC)` on a freshly-mapped slab. W^X
discipline: we never map RWX simultaneously. macOS on aarch64 requires
`mmap(..., MAP_JIT)` + `pthread_jit_write_protect_np()`; stitcher
must handle this target-specifically.

### Q7. Impact on `META_INTERPRETER_SPECIALIZATION.md`

Partial deduction produces residual Clausal source. Under the stencil
backend, specialization of a meta-interpreter against an object program
compiles to native code per residual predicate — turning the 10–400×
speedup projected in that plan into *compiled* 10–400× rather than
interpreted. Synergy, not conflict.

### Q8. Benchmarks

Nothing here is measured yet. The comparison with LLVM, the
specialization wins, the compile-time claim — all are projections.
A benchmark harness is a prerequisite for slice S3 and beyond.
`BENCHMARKING.md` (existing plan) should be extended to cover
native-backend comparisons once S1 lands.

### Q9. What about just "C codegen + cached `.so`"?

An alternative design: emit `.c` files per predicate, `zig cc -O2
-shared` them, `dlopen` the result. Much simpler tooling; compile
latency is seconds rather than microseconds. For a static workload
where predicates don't change, this is fine — the `.pyc`-style
cache amortizes cost. For `assertz`/tabling, compile latency becomes
a UX problem.

Recommendation: the C-codegen path is a *lower-risk first slice*
before committing to stencil tooling. Slice S0.5 could emit `.c`,
build `.so`, load via `dlopen` — gets us native code on a well-trodden
path and validates the runtime layout, `Frame` struct, Python FFI.
Then S1 switches to stencils for the compile-latency win. This
hedges the stencil-tooling risk identified in Phase P.

### Q10. Mercury LLDS / mid-IR intermediate

If the direct `GoalOp → stencil program` lowering proves ungainly,
insert a Mercury-LLDS-inspired mid-IR between them (explicit
register-allocated abstract machine). This is the `LLVM_BACKEND.md`
§9 escape hatch reproduced. Do not pre-commit; introduce if the
lowering pass grows hair.

---

## 12. Validation strategy

### 12.1 Differential testing against the Python backend

Every predicate in the existing test corpus compiled with both
backends; assert identical solution sequences. This is mechanical once
the `Strategy` abstraction supports a second backend (already
designed to support it).

### 12.2 Differential testing against Scryer

Scryer-via-PyO3 (see `SCRYER_EMBEDDING.md`) provides a second
reference. For pure Prolog subsets of Clausal programs, run both
Clausal-stencil and Scryer, compare. Scryer's choice of solution
order is a known divergence risk; comparison has to be set-valued
for unordered-solution queries.

### 12.3 Soak tests

- Refcount balance across 10⁶ backtracks (catches INCREF/DECREF
  imbalance in stencils).
- Memory churn with cyclic Compound graphs (catches missing
  `tp_traverse`).
- PEP 703 free-threaded build: contended predicate dispatch over
  shared `PredicateMeta` (catches refcount atomicity bugs in
  stencils).

### 12.4 Benchmarks

- N-queens at N ∈ {10, 12, 14}.
- Tabled path search on large graphs.
- SEND+MORE=MONEY and similar CLP(FD) puzzles.
- A Datalog corpus via the existing benchmarking infrastructure.
- Meta-interpreter specialization: specialized vs. interpreted,
  both backends.

Targets: stencil ≥3× Python backend on N-queens, ≥5× on CLP(FD),
≥10× on specialized meta-interpreters. These are aspirational; S1
may land slower on some axes and earn wins in later slices.

---

## 13. Bottom line

A copy-and-patch backend gives Clausal native code execution with
microsecond compile latency, no runtime codegen library dependency,
and a specialization pipeline that turns the template library into
the language-specific optimizer Clausal actually needs. The design
inherits every useful decision from `LLVM_BACKEND.md` (Frame +
`tailcc` + musttail, Maranget decision trees, PyObject-refcounted
terms, `.pyc`-embedded cache) and replaces the one piece that doesn't
fit — runtime LLVM codegen — with the technique CPython's own JIT
validates at scale.

The plan is staged so each slice is independently landable and
reviewable. The spike in Phase P answers the go/no-go questions
before the expensive slices. The specialization phases (S3, S6, S7,
S8, S9) are where the sustained performance trajectory lives; v1
lands at general-template quality (already faster than the Python
backend), and specialization compounds from there.

The friendship with Triska is technically relevant: his semantic
program (no cut, reified ITE, monotonic default, CLP(FD) arithmetic,
WFS tabling) is exactly the set of commitments that make
determinism/mode inference tractable, which feeds the specialization
pipeline, which is how this backend earns its keep. A general
Prolog with cut and operational negation would get meaningfully less
out of the same infrastructure.

Open work before any code: Phase P spike (1–2 weeks), which answers
the `musttail` / relocation / refcount-under-JIT questions that
dominate the design-validity risk.
