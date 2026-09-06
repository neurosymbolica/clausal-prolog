# MIR as a native backend for the engine — assessment

**Date:** 2026-09-06. **Question put:** *"Fast, low-latency compilation, ideally skipping
the C parsing and talking directly in its IR. We could vendor it and customise it to our
needs, it's not a lot of C code."* — assessed against the cell term representation that
landed this week (P3-2/P3-3) and against the parked copy-and-patch stencil JIT.

**Method.** MIR master was cloned and **built and run locally** (HEAD `a8ab7c3`,
2026-06-19; also tag `v1.0.0`, 2024-05-17, for a regression cross-check). Four probe
programs were written against MIR's C API and measured. Everything marked *measured*
below was run on this host; everything else is marked *estimated* or *cited*. Engine
files were read read-only in the P3-3 worktree; nothing outside this file was written.

**Measurement host.** aarch64 Linux (kernel 6.8.0, Debian 12, gcc 12.2.0, 8 cores,
4 KiB pages, CPU implementer `0x61` — Apple silicon under a Linux VM). CPython 3.13.3,
GIL enabled. **This is not an x86-64 measurement**; treat absolute numbers as
order-of-magnitude and the A/B ratios as the signal.

---

## 1. What MIR is, in ten lines

1. A strongly typed, register-based medium-level IR plus a JIT code generator, by
   Vladimir Makarov (the GCC register-allocator author). MIT licence.
2. Two translation units to embed: `mir.c` (7,034 lines) and `mir-gen.c` (10,038 lines).
   Target files (`mir-x86_64.c`, `mir-gen-aarch64.c`, …) are `#include`d **into** those,
   not compiled separately (`mir.c:6941-6956`, `mir-gen.c:317-332`).
3. Total core surface ≈ 23.4 K LOC by the author's own count; no external dependencies
   beyond libc and `-lm`. `c2mir` (the C11 front end, 15.5 K lines) is **not needed** and
   is what we skip when we build IR directly.
4. Targets: x86-64, aarch64, ppc64le, s390x, riscv64 on Linux; x86-64 + aarch64 on macOS;
   x86-64 on Windows (README badges + disclaimer).
5. Three execution modes on the same IR: an interpreter (`MIR_set_interp_interface`),
   ahead-of-time generation (`MIR_set_gen_interface` / explicit `MIR_gen`), and lazy
   generation on first call (`MIR_set_lazy_gen_interface`) or on first execution of each
   basic block (`MIR_set_lazy_bb_gen_interface`).
6. Four optimisation levels, 0–3 (`MIR_gen_set_optimize_level`): 0 = RA + codegen only;
   1 adds code selection; 2 (default) adds CSE + sparse conditional constant propagation;
   3 adds register renaming and loop-invariant motion.
7. Optimisation pipeline: simplify, **inlining**, CFG, SSA (Braun), GVN, copy prop, dead
   store/code elimination, out-of-SSA, jump opts, machinize, coalesce, priority-based
   linear-scan RA with live-range splitting, code selection.
8. Everything lives in a `MIR_context_t`. Grep for file-scope mutable statics in `mir.c`,
   `mir-gen.c`, `mir-interp.c`, `mir-x86_64.c` returns **only `const` tables** — no
   process-global mutable state. Contexts are independent; MIR.md:15-16 states threads may
   use MIR freely provided each thread has its own context.
9. Calls are plain platform C ABI. `MIR_load_external(ctx, name, addr)` binds any C symbol
   — including CPython C-API functions and our capsule function pointers — to an import.
10. Published performance (author's, i5-13600K/FC37/GCC-12.3.1): MIR-gen compiles the
    sieve benchmark in **249 µs vs GCC -O2's 27.1 ms (109×)**, and the generated code runs
    at **1/0.92 ≈ 1.09× of GCC -O2 wall** on that benchmark; over 15 C benchmarks the C
    front end's code is **0.91 geomean of GCC -O2**. MIR's interpreter is 6–10× slower
    than its generated code.

---

## 2. Lowering one clause to MIR IR

Target clause, cell heads:

```
grandparent(X, Z) <- parent(X, Y), parent(Y, Z).
```

Under the P3-2 representation the incoming goal is a Python tuple cell
`("grandparent", A0, A1)` — slot 0 an interned `str`, slots 1..n the arguments.
On a 64-bit GIL build (verified on this host, CPython 3.13.3) the layout is
`ob_refcnt@0, ob_type@8, ob_size@16, ob_item[i]@24+8i`. `Var` is
`{PyObject_HEAD; PyObject *binding; uint64_t var_id;}` (`_variables_capi.h:41-45`) →
`binding@16`, `var_id@24`. **Do not hard-code these** — see §6.3; they are baked as MIR
immediates from `offsetof` at extension build time. They are written as literals here only
for readability.

### 2.1 The IR the builder emits

This is the actual textual dump of IR built with `MIR_new_func_arr` / `MIR_new_insn` /
`MIR_new_call_insn` and printed with `MIR_output_item` — produced by the probe, not
hand-written:

```mir
clause_0:	func	i64, i64:goal, i64:trail, i64:k
	local	i64:t, i64:x, i64:y, i64:z, i64:m, i64:ok, i64:g, i64:a1
# 3 args, 8 locals, 0 globals
	mov	t, i64:16(goal)          # PyTuple_GET_SIZE(goal)
	bne	L2, t, 3                 # arity+1 != 3 -> fail
	mov	t, i64:24(goal)          # ob_item[0] — the functor spelling
	beq	L1, t, <functor ptr>     # interned-str identity hit: the common case
	call	p_rcb, cl_richcmp, ok, t, <functor ptr>, 2   # fallback: RichCompareBool(_, _, Py_EQ)
	bf	L2, ok
L1:
	mov	t, i64:32(goal)          # ob_item[1] = A0
	call	p_deref, cl_deref, x, t  # VarAPI->deref  (borrowed ref)
	mov	t, i64:40(goal)          # ob_item[2] = A1
	call	p_deref, cl_deref, z, t
	call	p_mark, cl_trail_mark, m, trail     # VarAPI->trail_mark
	call	p_newvar, cl_new_var, y             # fresh Y
	mov	a1, x
	call	p_call, cl_call, ok, <disp parent/2>, a1, trail, k   # body goal 1
	bf	L2, ok
	mov	a1, y
	call	p_call, cl_call, ok, <disp parent/2>, a1, trail, k   # body goal 2
	bf	L2, ok
	call	p_unify, cl_unify, ok, y, z, trail   # VarAPI->unify
	bf	L2, ok
	mov	g, 1
	jmp	L3
L2:
	call	p_undo, cl_trail_undo, trail, m      # VarAPI->trail_undo(trail, mark)
	mov	g, 0
L3:
	ret	g
	endfunc
```

### 2.2 The builder calls that produce it

```c
/* prototypes and imports, once per module */
MIR_type_t r1[] = {MIR_T_I64};
MIR_var_t v[3] = {{"a", MIR_T_I64}, {"b", MIR_T_I64}, {"tr", MIR_T_I64}};
p_unify = MIR_new_proto_arr (ctx, "p_unify", 1, r1, 3, v);
i_unify = MIR_new_import (ctx, "cl_unify");            /* resolved by MIR_load_external */

/* the clause function */
MIR_var_t args[3] = {{"goal", MIR_T_I64}, {"trail", MIR_T_I64}, {"k", MIR_T_I64}};
MIR_item_t fi = MIR_new_func_arr (ctx, "clause_0", 1, r1, 3, args);
MIR_func_t  f = MIR_get_item_func (ctx, fi);
MIR_reg_t   t = MIR_new_func_reg (ctx, f, MIR_T_I64, "t");
MIR_label_t Lfail = MIR_new_label (ctx);

/* size test: t = *(i64*)(goal + 16); if (t != 3) goto Lfail; */
MIR_append_insn (ctx, fi, MIR_new_insn (ctx, MIR_MOV,
    MIR_new_reg_op (ctx, t),
    MIR_new_mem_op (ctx, MIR_T_I64, /*disp*/ 16,
                    MIR_reg (ctx, "goal", f), /*index*/ 0, /*scale*/ 1)));
MIR_append_insn (ctx, fi, MIR_new_insn (ctx, MIR_BNE,
    MIR_new_label_op (ctx, Lfail), MIR_new_reg_op (ctx, t), MIR_new_int_op (ctx, 3)));

/* slot-0 identity compare, then the RichCompareBool fallback */
MIR_append_insn (ctx, fi, MIR_new_insn (ctx, MIR_BEQ,
    MIR_new_label_op (ctx, Lfun), MIR_new_reg_op (ctx, t),
    MIR_new_int_op (ctx, (int64_t) (intptr_t) functor_obj)));
MIR_append_insn (ctx, fi, MIR_new_call_insn (ctx, 6,
    MIR_new_ref_op (ctx, p_rcb), MIR_new_ref_op (ctx, i_rcb),
    MIR_new_reg_op (ctx, ok), MIR_new_reg_op (ctx, t),
    MIR_new_int_op (ctx, (int64_t) (intptr_t) functor_obj), MIR_new_int_op (ctx, 2)));

MIR_finish_func (ctx);            /* … then MIR_finish_module, MIR_load_module,
                                     MIR_load_external ×N, MIR_link, MIR_gen */
```

`MIR_new_call_insn(ctx, nops, proto, callee, [results…], [args…])` — `nops` counts
prototype + callee + results + args. A miscount is a segfault, not a diagnostic
(hit once while writing the probe).

### 2.3 First-arg dispatch

Two shapes are available and both are natural MIR:

- **Small arity, dense functor set:** the chain of `beq` on the interned slot-0 pointer
  shown above, one per clause arm — exactly the "pointer-first, `RichCompareBool` on miss"
  discipline the operator specified. A NaN can never be a functor, so no float arm is
  needed on the identity path.
- **Wide indexes:** `MIR_SWITCH` (index + label list) or `MIR_LADDR`/`MIR_JMPI`
  (take a label's address, then indirect-jump to it — MIR's "labels as values", MIR.md:437-440).
  `LADDR`/`JMPI` is the direct analogue of the parked backend's
  `predicate_entry_{1..16}` jump-table dispatcher and of its `resume_pc` protocol.

### 2.4 The step protocol — the one shape MIR cannot express directly

The engine's compiled dispatch is a **Python generator function**
`f(this_generator, proceed, fail, catcher, *args, trail)` yielding `(target, value)`
pairs, driven by `StepGenerator` and `drive_to_root_yield`
(`_trampoline.c:124-136, 238-288, 562-563`). Native code cannot *be* a Python generator.
A MIR backend must do what the parked stencil backend did: a heap frame holding the
clause's live values plus a `resume_pc`, an entry `SWITCH`/`JMPI` on `resume_pc`, and a
C-level iterator object (`_dispatch_helpers.c`'s `StencilDispatchIterator`, 2,145 LOC,
which the assessment of 2026-09-05 rated **verbatim-portable**) presenting `send()` to
the drive loop. MIR gives this a first-class instruction (`LADDR`/`JMPI`) where the
stencil backend had to build it out of tail-called stencils.

---

## 3. What the cell representation buys and costs a JIT

### 3.1 Buys

| operation | class representation | cell representation, from JIT-emitted code |
|---|---|---|
| read functor | `type(x).__name__` / `term_field_names` + `getattr` | one `mov` from `ob_item[0]` |
| read argument *i* | `getattr(x, fields[i])` — a dict/descriptor lookup | one `mov` from `24+8i(x)` |
| arity | `len(dataclasses.fields(...))` | one `mov` from `ob_size@16` |
| functor test | `MatchClass`, isinstance chain | `beq` on an interned pointer, `RichCompareBool` only on miss |
| atom test | zero-field-class isinstance | `ob_size == 1 && type(ob_item[0]) is str` — two loads and two compares |
| index key | `(type(a).__name__, len(fields(a)))` — chain + tuple + hash | `(ob_item[0], ob_size-1)` read in place, no allocation |
| unify a compound | `GetAttrString("__unify__")` ×2 → Python loop → re-enter C per field | the existing C tuple×tuple arm in `do_unify` (`_variables.c:1118-1131`) |

The decisive one is the last. The 2026-09-05 assessment measured `do_unify` at **37 % of
stencil graph wall**, and attributed it to the class `__unify__` C→Python→C bounce per
node. Under cells that bounce is gone for every compound. **Everything a JIT wants to do
to a term is now an array index or a pointer compare.** Head-arg extraction — the thing
that made every committed workload fall back to the trampoline in the parked backend's
first A/B (`_extract_head_args` rejecting `PredicateMeta` heads) — becomes
`PyTuple_GET_ITEM`, i.e. it stops being a special case at all.

### 3.2 Costs

- **Materialising a cell is `PyTuple_New(n+1)` plus n+1 stores plus n+1 increfs.** A
  logic-variable-free WAM would write a heap cell; we call the allocator. Mitigations that
  the representation makes available: `PyTuple_New` is served from CPython's tuple free
  lists for small n; slot-0 spellings are interned constants, so their incref is on an
  immortal-ish object; ground sub-terms can be *shared* rather than rebuilt (spec §3c #2,
  "maximal structural sharing").
- **Refcounts are the JIT's problem now.** See §6.3.
- **Strings are `str`, denoting a char list.** Head arms over string literals need both a
  `str`-vs-`str` arm and the char-list arms (`"abc"` vs `[X,Y,Z]` binding `X=("a",)`, and
  `"abc"` vs `[H|T]` giving `T="bc"` as a slice — spec §6.2). In generated code this is
  three shapes, not one, and the honest answer is that all three should call out to
  `_list_unify`'s C entry points rather than being open-coded per clause.
- **Lists are Python `list`/`SegList`/`SegString`, not `'.'/2` cells** (spec §5.4). A JIT
  cannot pretend a list is a cell; list-shaped heads keep needing the dedicated
  `head_list_cons_unify` / `build_list_cons` helpers the parked backend already has.
- **A cell is not self-describing about groundness.** Deep-index keys and
  `_is_deeply_ground` gates remain runtime work; the representation does not make them
  free, only cheap to walk.

### 3.3 Net

The cell representation is *substantially* better for a native backend than the class
representation was, and — this is the important asymmetry — it is better for **any**
native backend, MIR or stencil, by the same amount. It does not discriminate between the
two candidate backends. What it changes is that the head/body analysis a native backend
needs shrinks (the 2026-09-05 assessment put the parked lowering pass's rewrite at
1,500–2,500 of 11,572 LOC, and said the result is *smaller* than what it replaces).

---

## 4. Latency and throughput — measured

### 4.1 Compile latency (measured on this host)

Probe: build 200 distinct copies of the §2 clause function (28 MIR instructions, 7 external
calls, 3 labels) through the C API; time IR construction and `MIR_gen` per function.

```
O0  build_ir  5.66 us/fn   MIR_gen   54.79 us/fn   exec  12.1 ns/call
O1  build_ir  2.46 us/fn   MIR_gen   64.62 us/fn   exec  11.9 ns/call
O2  build_ir  2.48 us/fn   MIR_gen  109.41 us/fn   exec  12.2 ns/call
O3  build_ir  2.55 us/fn   MIR_gen   91.16 us/fn   exec  12.4 ns/call
```

(O0's higher `build_ir` is first-iteration warm-up — same code path at every level.
O3 < O2 is within run-to-run noise on this host.)

Read: **~2.5 µs to build a clause's IR, 55–110 µs to compile it to machine code.**
For a module of 200 predicates that is ~11 ms at O0 or ~22 ms at O2 of added import time —
material but not disqualifying, and it is exactly the cost the lazy interfaces exist to
defer. On an x86-64 desktop expect these to be several times smaller (the author's sieve
figure is 249 µs for a whole function at O2 on an i5-13600K).

### 4.2 The text front door vs the C API (measured)

Probe: emit the same 200 clauses as MIR *text* (751 bytes/clause, 150 KB total) and time
`MIR_scan_string` on the whole thing:

```
text size 150344 bytes (751 B/clause)
MIR_scan_string  18.63 us/fn  (3.73 ms total)
```

**The text route costs ~7.5× the C API (18.6 µs vs 2.5 µs per clause) but is still only
~15–25 % of the `MIR_gen` cost.** That makes "generate MIR text from Python, hand it to
`MIR_scan_string`" a *viable prototype front door* — it is not the bottleneck — while the
C API is the right end state. See §5.2.

### 4.3 Inlining the capsule (measured — the key differentiator)

The operator's framing was: MIR gets "real register allocation and inlining of the capsule
calls if we expose them as MIR functions rather than externals". This was tested directly.
Two builds of the same clause body, differing only in how `deref` is reached — as an
external C call, or as a MIR function called with `MIR_INLINE` (which `MIR_link` expands
in place). Two deref sites per call; args are bound `Var`s at deref depth 1; 20 M calls:

```
deref as external   O2  exec  6.90 ns/call
MIR-deref inlined   O2  exec  4.58 ns/call
deref as external   O2  exec  7.33 ns/call
MIR-deref inlined   O2  exec  4.31 ns/call
deref as external   O2  exec  7.21 ns/call
MIR-deref inlined   O2  exec  5.65 ns/call
deref as external   O0  exec  8.87 ns/call
MIR-deref inlined   O0  exec  4.54 ns/call
```

**Measured: ~1.2–2.2 ns saved per deref site; ~35 % off this micro-shape's wall.** The
mechanism is real and cheap to use: rewrite the four or five hottest capsule primitives
(`deref`, `is_var`, `trail_mark`, the bound/unbound test, the tuple slot fetch) as ~10-line
MIR functions once at backend init, and every clause that calls them gets them inlined and
register-allocated into its own body. **This is a capability the stencil backend
structurally cannot have** — a stencil's boundary is a fixed binary blob; MIR's is an IR
the optimiser can see through.

Caveat: these are stub callees with perfect branch prediction and no cache pressure. The
*ratio* is the signal; the absolute nanoseconds are a floor, not a prediction.

### 4.4 Against the parked stencil numbers

The parked stencil backend's final recorded state (`bench_history.csv`, commit `904523aa`,
2026-06-20, 40 samples, gc-on serial): geomean **0.446× = 2.24× faster** than the Python
backend across nine workloads (8.6× on tabling, 4.0× on fib, down to 1.0× — a gate failure
— on `wrap_fib_runtime`). Its parking-time cost attribution was **ctypes-thunk dispatch
(~1.5 µs per callback fire), stencil-bytecode + per-iteration scaffold, and JIT-page
self-time**, plus `do_unify`'s 37 %.

Honest comparison:

| | copy-and-patch stencils | MIR |
|---|---|---|
| compile cost per predicate | ~0 (memcpy + relocation patching) | **55–110 µs measured**, deferrable via lazy interfaces |
| code quality | whatever clang emitted for each stencil, stitched; **no cross-stencil register allocation** — the parked ledgers name "JIT-page self-time 5.4 %" and "stencil bytecode + scaffold 63–92 % of stencil wall" as the residual | one function, one register allocator, GVN/CSE/DCE across the whole clause; **capsule calls inlinable (measured §4.3)** |
| boundary to Python callbacks | ctypes thunk, ~1.5 µs/fire, the dominant parked overhead | same problem *if* you keep Python callbacks; but cells + a direct C call to a `PyObject_Vectorcall` shim removes most of the reasons to have them |
| build/toolchain | needs clang at build time, relocation-format assumptions across clang versions (parked Q2) | plain C library, no external toolchain at runtime **or** build time |
| tail calls / LCO | clang `musttail`, target-dependent (parked Q1) | see §5.4 — partial |
| debuggability | stencil bytecode + stitch plan | `MIR_output_item` textual IR + `MIR_gen_set_debug_file` pipeline dump + `_MIR_dump_code` |
| lines of vendored C to own | ~9,800 template LOC + 4,332 stitcher/harness + 2,558 generated data, all ours | 17 K lines of someone else's, unmodified |

**What is measured vs estimated.** Measured here: MIR compile latency, IR-build latency,
text-scan latency, and the inline-vs-external A/B. Measured in the parked repo: the 2.24×
geomean and the overhead split. **Not measured anywhere: what a MIR backend would score on
the engine's benchmarks.** Nobody has run one. Any number in that cell today would be
invented.

**The estimate I will commit to,** with its reasoning: a MIR backend should land in the
same 1.5–3× band the stencil backend reached, because both are bounded by the same three
things the parked ledgers identified and neither backend removes — the per-goal boundary
into the drive loop, `do_unify` (shared with the Python backend), and CLP(FD)/arithmetic
machinery. Where MIR should do *better* is on the parked backend's two named residuals
(no cross-stencil register allocation; the per-iteration bytecode scaffold), and on
predicates whose bodies are long enough for GVN and inlining to pay. Where it should do
*worse* is cold start. **And the 2026-09-05 ratio-optics warning applies unchanged: cells
speed up `do_unify` under *both* backends, so the historical stencil/default ratios are
not a valid yardstick and any gate must be re-derived on cell-native code.**

---

## 5. Vendoring plan

### 5.1 Which files

Vendor `mir/` into `third_party/mir/` and add to the `_mirjit` extension's `sources`:

```python
Extension(
    "clausal.logic.runtime._mirjit",
    sources=["clausal/logic/runtime/_mirjit.c",
             "third_party/mir/mir.c",
             "third_party/mir/mir-gen.c"],
    include_dirs=["third_party/mir", "clausal/logic/variables"],
    extra_compile_args=["-std=gnu11", "-fsigned-char", "-Wno-abi",
                        "-fvisibility=hidden"],
    libraries=["m"],
)
```

Two `.c` files only. The per-target sources (`mir-x86_64.c`, `mir-aarch64.c`,
`mir-gen-x86_64.c`, `mir-gen-aarch64.c`, …) are `#include`d by those two and must be
present in the directory but **not** listed. `c2mir/`, `mir2c/`, `llvm2mir/`,
`mir-bin-*.c`, `mir-utils/` are all droppable — that is 15.5 K of the 39 K lines gone.
Header set needed: `mir.h`, `mir-gen.h`, `mir-varr.h`, `mir-dlist.h`, `mir-htab.h`,
`mir-bitmap.h`, `mir-hash.h`, `mir-reduce.h`, `mir-alloc.h`, `mir-code-alloc.h`,
`mir-alloc-default.c`, `mir-code-alloc-default.c`, `mir-<target>.h`, `real-time.h`.

**`-fsigned-char` is mandatory, not cosmetic.** This was discovered the hard way: built
without it, `MIR_gen` **hangs in an infinite loop** in the aarch64 instruction emitter
(`out_insn` in `mir-gen-aarch64.c:2177`, reached from `generate_func_code`) on a
three-instruction function — the emitter's opcode-template scanner assigns
`hex_value()`'s `-1` sentinel to a `char`, which is unsigned by default on aarch64, so the
loop never terminates. It reproduces identically on `v1.0.0` (2024) and on HEAD, and
MIR's own `GNUmakefile:28,61` and `CMakeLists.txt:19` both pass `-fsigned-char`. Adding
the flag fixed it completely. **This flag belongs in a comment in `setup.py` with this
paragraph attached**; a future contributor who drops it will get a silent hang on ARM
and nothing on x86.

Other build facts, verified:

- Compile time for the two units: **~6 s total at `-O2`** on this host; objects ~760 KB.
- **No mutable global state** — grep for non-`const` file-scope statics across `mir.c`,
  `mir-gen.c`, `mir-interp.c`, `mir-x86_64.c` returns nothing. Everything hangs off
  `MIR_context_t`. Safe to instantiate per `Database`.
- **Symbol visibility:** MIR uses no visibility attributes, so every `MIR_*` symbol is
  extern. Build with `-fvisibility=hidden` so the extension exports only `PyInit__mirjit`;
  extension modules are `dlopen`ed `RTLD_LOCAL` anyway, but two extensions each vendoring
  MIR would otherwise be an ODR hazard.
- **Custom allocators:** `MIR_init2(alloc, code_alloc)` takes function tables
  (`mir-alloc.h`, `mir-code-alloc.h`) — a hook for routing MIR's allocations through
  `PyMem_*` and its code pages through our own mapper, if we ever want that. Documented in
  `CUSTOM-ALLOCATORS.md`.
- **Code memory reservation:** MIR reserves 128 MB of *address space* up front
  (`MIR_CODE_RESERVE_SIZE`, `mir.c:4372`) so generated code stays within aarch64 direct
  branch range. Address space only, untouched pages cost nothing, and it falls back to
  individual mappings if unavailable — but it will show up in RSS-adjacent tooling and
  should be mentioned in any memory-footprint discussion.

### 5.2 How the compiler talks to it — two front doors

**Option A — MIR text + `MIR_scan_string`.** The Python lowering pass emits MIR assembly
text; `_mirjit` calls `MIR_scan_string`, `MIR_load_module`, `MIR_load_external` for each
capsule/CPython symbol, `MIR_link`, `MIR_gen`. Measured cost 18.6 µs/clause (§4.2),
~15–25 % of the compile budget.

- *For:* the whole backend above the C boundary is Python string formatting. It is
  greppable, diffable, dumpable to a file, and trivially unit-testable — you can commit
  expected-IR fixtures. It requires **~200 lines** of C.
- *Against:* stringly-typed; errors surface as MIR scan errors with a line number, not as
  a Python traceback at the emitting site; the text format is not a stability contract.

**Option B — a Python-level IR builder mirroring `ir.py`.** `_mirjit` exposes thin
wrappers over `MIR_new_func_arr` / `MIR_new_insn` / `MIR_new_call_insn` / operands, and
the lowering pass drives them directly. Measured cost 2.5 µs/clause.

- *For:* 7.5× cheaper, typed at the boundary, no serialisation round trip, and it is the
  supported API (the text format is explicitly a convenience).
- *Against:* several hundred lines more C, and every operand constructor crossing the
  Python boundary is a call — for a 28-instruction function that is ~100 crossings, which
  is exactly what the 2.5 µs measurement already includes on the C side but not the Python
  side.

**Recommendation: A for the spike, B for the product, and design the emitter so the swap
is one class.** Emit through an abstract `MirEmitter` with `.insn(op, *args)` /
`.call(proto, callee, *args)` / `.label()`; `TextEmitter` writes strings, `ApiEmitter`
calls `_mirjit`. The 2026-09-05 finding that `compiler/ir.py` changed **19 lines across
the whole atom+cell pivot** means the *input* to this emitter is the most stable contract
in the repo — the emitter is the only piece that has to move.

### 5.3 Where it plugs in

**P3-3 already built the seam, and it is a better fit for MIR than for stencils.**
`Database.set_backend_chooser` / `Database.register_backend`
(`clausal/logic/database.py:518-628`) define exactly this contract:

- `chooser(row) -> str` is called **once per dispatch install**, with the `PredRow` about
  to receive the dispatch, so the decision can read clauses, signature, tabled-ness and
  module.
- `installer(row, python_fn) -> Callable | None` — the backend **produces**, it does not
  install; returning `None` means "not mine" and falls back to the Python dispatch with
  `row.backend` left at `"python"`. A MIR backend that only handles, say, non-tabled
  predicates with cell or atomic head args declines everything else, safely, on day one.
- **One invalidation point:** `PredRow.invalidate` and nothing else. A backend "hangs its
  cache off the row and lets `invalidate()` drive it; it must not install its own
  invalidation channel."

So the integration seam the 2026-09-05 assessment called a **complete rewrite** for the
parked stencil branch (~1,196 LOC of ad-hoc backend selection inside
`compiler/predicate.py`) is now ~30 lines: `register_backend("mir", install)` plus a
chooser. `compiler/predicate.py:2118` is the single call site.

### 5.4 Customisation points

- **Our own calling convention.** MIR functions take typed args and return typed results;
  a `(gen, value)` step protocol is expressible as `func i64, i64:frame, i64:trail` with
  the yielded pair written through `frame`. `MIR_new_global_func_reg`
  (`mir.h:532`) and `_MIR_get_module_global_var_hard_regs` (`mir.h:733`) let us tie
  module-global variables to specific hard registers — the mechanism MIR.md:513 describes
  for passing args to `JCALL`ed functions. That is our escape hatch for a threaded-code
  convention, and it is exactly the sort of "customise it to our needs" the operator asked
  about.
- **Tail calls / last-call optimisation — partial, and the honest answer is "not the way
  you want".** MIR has `MIR_JCALL` / `MIR_JRET` (`MIR_new_jcall_insn`, `mir.h:549`):
  "calls a function without setting up the return address", with `JRET` returning by
  jumping to an address operand. But MIR.md:511-513 constrains it: *"`MIR_JCALL` and
  `MIR_JRET` implement non-standard ABI for functions without args and return values …
  The argument and return values can be passed through global vars which are tied to
  specific hard regs."* It is designed for interpreter↔JIT switching, **not** as a general
  tail call. `MIR_CALL`/`MIR_INLINE` must pair with `MIR_RET`, and `JCALL` with `JRET` —
  you cannot mix. So LCO via `JCALL` means committing every JIT-compiled predicate to a
  zero-argument, globals-in-hard-registers convention. That is a real design option (it is
  how threaded-code interpreters use it) but it is a *whole-backend* decision, not a peephole.
  **There is no `MIR_TAILCALL`.** For a first cut, use `MIR_CALL` and accept native stack
  growth bounded by the drive loop, exactly as the current backend does.
- **`MIR_INLINE`** (`mir.h` insn list; MIR.md:498-501, expanded by `MIR_link`) is the
  capsule-inlining lever measured in §4.3, and also the way to inline one predicate into
  another (`inline_predicates` sits at priority 05 in the parked `nqueens`/`graph`
  opt-priority ledgers — a lever MIR gives for free that the stencil backend never got to).
- **`MIR_PRSET`/`MIR_PRBEQ`/`MIR_PRBNE`** are property instructions for lazy basic-block
  versioning — a specialisation channel (guard once, specialise the rest of the block)
  that maps onto mode/determinism inference if that ever gets revived.
- **Reusing the stencil plan's assets.** The 2026-09-05 assessment's "durable asset"
  inventory mostly survives a switch to MIR: `_dispatch_helpers.c` (2,145 LOC, the C
  iterator and Plan D-2/D-4 wins) is backend-agnostic; the bench harness, ledgers and
  calibrated A/B methodology (11,097 LOC) are unconditionally reusable and are the only
  calibrated methodology in either repo; the lowering *architecture* (op-kind registry,
  slot allocator, labels, linker, callbacks base) is reusable with the assembler swapped.
  What does **not** carry over is the 102-file stencil template library, the extractor and
  the stitcher — ~15 K lines. That is the real cost of choosing MIR over reviving stencils,
  and it should be stated plainly rather than hidden in a table.

---

## 6. Risks

### 6.1 Maturity and the author's own disclaimer

MIT licence (`LICENSE`, "Copyright (c) 2018-2024 Vladimir Makarov"). Actively maintained:
4,210 commits, HEAD `a8ab7c3` dated **2026-06-19** — i.e. three months old at time of
writing; `v1.0.0` was tagged 2024-05-17. 2.7 K stars, **137 open issues**. CI workflows for
x86-64 Linux/macOS/Windows, Apple aarch64, aarch64, ppc64le, s390x, riscv64.

The README carries an explicit disclaimer: *"There is absolutely no warranty that the code
will work for any tests except ones given here and on platforms other than x86_64
Linux/OSX, aarch64 Linux/OSX (Apple M1), and ppc64le/s390x/riscv64 Linux."* Read that as:
the platforms we care about are in scope, but the warranty is the author's test suite,
not ours.

Adoption: **Ravi** (Dibyendu Majumdar's Lua 5.3 dialect) uses MIR as its JIT backend and
archived its LLVM backend in favour of it; earlier libgccjit / dmrC / Eclipse OMR backends
were all discontinued. Ravi's README positions MIR as "compact" and states the project
"prioritizes ease of maintenance and support … over maximum performance" — a fair
characterisation of the trade. **I found no established Python bindings for MIR**, and no
confirmed PostgreSQL adoption; searches surfaced only unrelated PostgreSQL JIT projects.
We would be early.

### 6.2 aarch64 quality — one concrete scar, then clean

The `-fsigned-char` hang (§5.1) is a genuine aarch64-specific latent bug class in the
instruction emitter, present since at least `v1.0.0`, that manifests as an **infinite loop
with no diagnostic**. It is not MIR's fault in the strict sense — the project's own build
files set the flag — but it is a demonstration of how the aarch64 path fails: silently. Once
the flag was set, every probe generated correct, fast code on aarch64 with no further
trouble across four optimisation levels. Mitigation: build the extension with the flag, and
add a smoke test that generates and calls one trivial MIR function **under a timeout** at
import time or in CI, so a future toolchain change fails loudly.

### 6.3 GC and refcount correctness in generated code — the biggest correctness risk

- **Never hard-code CPython struct offsets.** Verified on this host that a GIL build has
  `ob_item@24`; a free-threaded build (`Py_GIL_DISABLED`, which the engine explicitly
  supports — see `_ft_compat.h`, "Under Py_GIL_DISABLED builds (3.13t+), these expand to
  the real atomic / critical-section operations") has a different `PyObject` header and
  therefore different tuple and `Var` offsets. Compute every offset with `offsetof` in
  `_mirjit.c` at build time and bake it as a MIR immediate. A hard-coded `16` is a
  wrong-memory read on a free-threaded interpreter, not a compile error.
- **Refcounting.** `Py_INCREF` is not `ob_refcnt++` on modern CPython: 3.12+ has immortal
  objects, and free-threaded builds use biased reference counting with a thread-id compare.
  Emitting an inline increment is a correctness bug waiting for a Python upgrade. Emit
  calls to small `_mirjit`-local `cl_incref`/`cl_decref` helpers compiled by the C compiler
  (correct by construction for whatever CPython the extension was built against) and expose
  them **as MIR functions** so `MIR_INLINE` can still fold them in where the fast path is
  version-stable. Prefer borrowed references wherever the goal tuple provably outlives the
  clause body — that is most of head matching.
- **`tp_traverse`.** Any heap frame the JIT allocates that holds `PyObject*` must be
  GC-tracked and traversable, as the parked plan already required (§7.4 of
  `COPY_AND_PATCH_BACKEND.md`). Nothing about MIR changes this.
- **Exceptions.** MIR has no exception handling. CPython errors are `NULL`/`-1` returns
  plus a thread-state error indicator, so generated code must branch on every C-API result
  and unwind by returning a failure code — the same discipline the stencil templates use.
  MIR.md suggests `setjmp`/`longjmp` for non-local exit; do **not** use it across CPython
  frames.

### 6.4 Unloading on recompile — a real gap

**MIR has no per-function code unloading API.** `MIR_gen_finish` frees generator internals;
code pages are released only in `code_finish` at `MIR_finish` (`mir.c:4521-4535`), i.e.
context teardown. There is no `MIR_gen_delete_func`.

Consequences for P3-3's "one invalidation point" (`PredRow.invalidate`):

- Recompiling a predicate **leaks its previous machine code** for the life of the context.
  Per-function code size was not measured; on the README's own figures (557 KB of MIR core
  for the whole sieve pipeline) a clause function is plausibly 0.5–2 KB, so a workload that
  `assertz`es in a loop and triggers lazy recompiles could leak steadily. **This is the
  item I would want measured before committing.**
- Two mitigations, both available: (a) `MIR_set_func_redef_permission(ctx, 1)`
  (`mir.h:543`, `mir.c:678`) allows redefining a loaded function, and `_MIR_get_thunk` /
  `_MIR_redirect_thunk` / `_MIR_get_thunk_addr` (`mir.h:719-721`) let us install a
  **stable thunk** as the predicate's call target and repoint it on recompile — call sites
  never change, old code is simply orphaned; (b) run one `MIR_context_t` per *epoch* and,
  when leaked code exceeds a threshold, build a fresh context and regenerate the live
  predicates, discarding the old context wholesale. (b) is clean but needs every JIT
  dispatch to be re-derivable from the row, which the seam contract already guarantees.
- `MIR_change_module_ctx` (`mir.h:592`) moves a module between contexts, which is the
  primitive (b) would use.

### 6.5 Threading

MIR guarantees only that *different contexts in different threads* need no
synchronisation. One context shared across threads is not safe. The engine's own contract
already makes `Trail` per-thread while sharing the clause database, so the natural mapping
is one MIR context per `Database` with compilation serialised (it happens under the
mutation gate anyway) and generated code freely callable from any thread — generated code
itself holds no MIR state. `MIR_PARALLEL_GEN` appears in `CMakeLists.txt:47` but is
**not referenced anywhere in `mir-gen.c` at HEAD**, and `mir-gen.h` exposes no
parallel-generation entry point; treat parallel codegen as unavailable.

### 6.6 Debugging generated code

Better than the stencil situation. `MIR_output_item` dumps readable textual IR (the §2.1
listing is real output); `MIR_gen_set_debug_file` + `MIR_gen_set_debug_level` dump the
optimisation pipeline; `_MIR_dump_code` dumps machine bytes. No DWARF, no perf symbol
registration, no debugger integration — a crash inside generated code is a bare address.
Budget for a "dump the IR for predicate P" developer command from day one; it costs one
function call and pays for itself the first time.

### 6.7 The strategic risk

We would be vendoring 17 K lines of C we did not write, that few projects depend on, whose
sole prominent adopter is a hobby Lua dialect, and whose author gives no warranty. Against
that: it is MIT, it is small enough to read, it has no dependencies, and if it were
abandoned tomorrow the vendored copy would keep working — the same argument that makes
vendoring the right call in the first place. The 137 open issues are worth a skim before
committing.

---

## 7. Recommendation

**Do the spike. Do not start a backend.**

The case for MIR over reviving the stencil backend rests on four things, three of which are
now measured rather than argued: compile latency is small enough to hide (§4.1); the text
front door is cheap enough that the first version is mostly Python (§4.2); capsule calls
really do inline and really do pay (§4.3, ~35 % on the micro-shape); and the integration
seam P3-3 shipped fits a "produces a dispatch, declines what it can't handle" backend
exactly (§5.3). The case against is that it discards ~15 K lines of working stencil
assets, and that nobody has ever run a MIR backend on our benchmarks.

The parked stencil backend's own history is the argument for a spike rather than a plan:
its first A/B found every committed workload falling back to the trampoline, and its
stencil-eligible predicates running **4–13× slower** than the Python backend. That failure
was cheap to discover and expensive to have not discovered earlier.

### 7.1 The smallest experiment

**One predicate, end to end, behind the existing seam. Target: two weeks.**

1. Vendor `mir.c` + `mir-gen.c` + headers; add `_mirjit` with `-fsigned-char`; expose
   `MIR_scan_string` / `MIR_load_external` / `MIR_link` / `MIR_gen` and a smoke test that
   compiles and calls `add2` under a timeout (§6.2).
2. Bake `offsetof`-derived layout constants and the capsule function pointers into the
   module at init (`import_variables_capi`), and expose them to the emitter (§6.3).
3. Write `TextEmitter` for exactly the ops `fib/2` needs: head arity + slot-0 test, arg
   load, deref, integer unwrap/box, arithmetic, one sub-call into the drive loop, trail
   mark/undo, solution yield. Do **not** build the general lowering pass.
4. Register the backend: `Database.register_backend("mir", install)` and a chooser that
   returns `"mir"` for exactly one functor/arity and `"python"` otherwise. Everything else
   in the engine is untouched by construction.
5. Run the **existing** stencil A/B harness (gc-on serial, 40-sample minimum, interleaved,
   noise %) on `bench_fib` and `bench_tabling` — the two workloads the stencil backend won
   biggest on (0.250× and 0.116×) and therefore the two where a native backend's ceiling is
   clearest. Re-derive the baseline on cell-native code; **do not** import the parked
   `bench_history.csv` ratios (the 2026-09-05 ratio-optics warning).
6. Measure, additionally: per-predicate `MIR_gen` wall on this codebase's real clause
   shapes; generated code size per function (the §6.4 leak budget); and one deliberate
   `assertz`-recompile loop to see what the leak actually costs.

### 7.2 Decision criteria — set before running

Proceed to a full plan only if **all** of these hold:

- **Correctness:** the differential test against the Python backend passes on the chosen
  predicate, including backtracking, failure and exception paths, with no refcount leak
  under `sys.gettotalrefcount` / tracemalloc across 10⁵ iterations.
- **Throughput:** ≥ **1.5×** the Python backend on `bench_fib`, measured with the existing
  harness against a freshly derived cell-native baseline. (The stencil backend got 4.0×
  there; 1.5× from a spike with no lowering pass and no specialisation is a credible
  extrapolation, and anything below it says the boundary, not the codegen, is the wall —
  which would be the *same* wall the stencil backend hit and an argument for neither.)
- **Latency:** total added compile time for a module of ~200 predicates ≤ **50 ms** at the
  chosen optimisation level, or demonstrably deferrable with `MIR_set_lazy_gen_interface`.
- **Leak:** the recompile leak is either ≤ 2 KB/predicate *and* bounded by an epoch scheme
  we have prototyped, or eliminated by the thunk-redirect route (§6.4).
- **Platform:** the smoke test passes on x86-64 and aarch64 Linux.

If throughput lands between 1.0× and 1.5×, the honest conclusion is **neither backend**,
and the effort belongs in the boundary (drive loop, callback elimination, `do_unify`)
where both the parked ledgers and the cell work already point.

### 7.3 What this does not decide

Choosing MIR for the spike does not close the stencil question. The two are not exclusive
in principle — the stencil template library is a code *generator*, MIR is a code
*generator*, and both feed the same seam. But they are exclusive in practice for the next
engineer-quarter, and the stencil revival's own scoping memo says the full plan comes
after P3-3 anyway. **The right sequencing is: land P3-3, run the MIR spike against the
criteria above, and let the measured result — not this document — pick the backend.**

---

## 8. Sources

**MIR project** (cloned and built locally; HEAD `a8ab7c3`, 2026-06-19; tag `v1.0.0`,
`477d820`, 2024-05-17):

- https://github.com/vnmakarov/mir — repo, MIT `LICENSE`, 4,210 commits, 137 open issues,
  2.7 K stars, CI badges for x86-64 Linux/macOS/Windows, Apple aarch64, aarch64, ppc64le,
  s390x, riscv64.
- https://github.com/vnmakarov/mir/blob/master/README.md — disclaimer; performance tables
  (compilation 249 µs vs GCC -O2 27.1 ms = 109×; execution 1.74 s vs 1.6 s; LOC 23.4 K vs
  2,420 K; interpreter 6–10× slower than generated code; c2m geomean 0.91 of GCC -O2 over
  15 benchmarks); optimisation pipeline; file-structure section; QBE/LIBJIT/RyuJIT
  comparison.
- https://github.com/vnmakarov/mir/blob/master/MIR.md — thread-safety statement (lines
  15-16); `MIR_JMPI`/`MIR_LADDR` (424, 437-440); `MIR_INLINE` (498-501); `MIR_JCALL`/
  `MIR_JRET` and their zero-arg/globals-in-hard-regs constraint (503-513); `MIR_link` and
  the four interfaces (701-716); `MIR_gen_init`/`MIR_gen_finish`/optimize levels (740-760).
- `mir.h` (739 lines) — full API list, `MIR_insn_code_t` enum, `MIR_type_t`,
  `MIR_new_jcall_insn:549`, `MIR_set_func_redef_permission:543`,
  `MIR_new_global_func_reg:532`, `_MIR_get_thunk`/`_MIR_redirect_thunk`:719-721,
  `MIR_change_module_ctx:592`.
- `mir-gen.h` (33 lines) — the entire generator API; note the absence of any
  parallel-generation entry point.
- `mir.c:4372` (`MIR_CODE_RESERVE_SIZE`, 128 MB address-space reservation and its
  rationale), `mir.c:4521-4535` (`code_finish` — the only place code pages are unmapped),
  `mir.c:678` (`MIR_set_func_redef_permission`), `mir.c:1960-2063` (`MIR_link`),
  `mir.c:6941-6956`, `mir-gen.c:317-332` (target files `#include`d into the two TUs).
- `mir-gen-aarch64.c:2166-2431` (`out_insn` — the `-fsigned-char` hang, §5.1/§6.2);
  `GNUmakefile:28,61` and `CMakeLists.txt:19` (`-fsigned-char -std=gnu11 -Wno-abi`);
  `CMakeLists.txt:44-48` (`MIR_PARALLEL_GEN` defined but unreferenced at HEAD).
- `CUSTOM-ALLOCATORS.md`, `HOW-TO-PORT-MIR.md`.
- https://developers.redhat.com/blog/2020/01/20/mir-a-lightweight-jit-compiler-project —
  the author's motivation post (cited by the README).

**Adopters:**

- https://github.com/dibyendumajumdar/ravi — Ravi (Lua 5.3 dialect) lists "Compact JIT
  backend MIR" as a feature; adopted 2019, LLVM backend archived 2020; earlier libgccjit /
  dmrC / Eclipse OMR backends discontinued. No Python bindings for MIR were found.

**Engine (read-only, P3-3 worktree
`/workspace/clausal-bug-fix/.claude/worktrees/p33-state-reloc`):**

- `docs/superpowers/specs/2026-09-06-atoms-as-cells-strings-design.md` §5 (term model,
  shapes, interning, `-hide` mangling, "efficient representations always"), §6.2
  (unification table), §6.3 (type checks).
- `implementation_plans/tagged-tuple-term-representation.md` §1/§1b/§3c.
- `clausal/logic/variables/_variables_capi.h` — capsule table (`deref`, `is_var`,
  `unify`/`unify_oc`, `trail_mark`/`trail_undo`, attr access) and `VarObject`/`TrailObject`
  layouts; `_ft_compat.h` — the free-threading contract.
- `clausal/logic/database.py:458-628` — **the backend seam**: `set_backend_chooser`,
  `register_backend`, `backend_dispatch`, and the three-sentence contract (one
  invalidation point; per-predicate choice at install time; installation stays in one place).
- `clausal/logic/compiler/predicate.py:770-812` (the trampoline generator protocol and
  compiled signature), `:2101-2165` (the single install choke point where
  `db.backend_dispatch` is consulted).
- `clausal/logic/compiler/ir.py` — the 16 `GoalOp` classes a backend lowers from.
- `clausal/logic/compiler/globals_env.py:437-560` — the `$disp_{fname}_{arity}` bake for
  locked predicates.
- `clausal/logic/runtime/_trampoline.c:124-136, 238-288, 562-563` — `StepGenObject`,
  `StepGen_send`, `drive_to_root_yield`.
- `implementation_plans/COPY_AND_PATCH_BACKEND.md` — the parked proposal (§4.2 calling
  convention, §7 memory/FFI, §11 Q1 tail calls / Q2 relocations / Q5 debuggability, the
  ≥3×/≥5×/≥10× targets).
- `implementation_plans/copy-patch-cells-assessment-2026-09-05.md` — the 2.24× geomean and
  per-workload table, the parking-time overhead split (ctypes thunk ~1.5 µs/fire, stencil
  bytecode + scaffold, JIT-page self-time 5.4 %, `do_unify` 37 %), the durable-asset
  inventory, and the double-counting caveat.
- `implementation_plans/stencil-v2-scoping-memo.md` — the ratio-optics warning
  ("re-derive the gate baseline post-cells") and the timing ruling.

**Local measurements** (probe sources in this session's scratchpad; not committed):
`clausebench.c` (§4.1 compile latency, §2.1 IR dump), `textbench.c` (§4.2
`MIR_scan_string`), `inlinebench.c` (§4.3 `MIR_INLINE` vs external A/B),
`minimal2.c`/`minimal3.c` (§5.1 the `-fsigned-char` hang, isolated by stack sampling to
`out_insn` ← `generate_func_code`, reproduced on both HEAD and `v1.0.0`).
