# Continuation-level TCO — Plan

Status: **proposal**.  Nothing implemented.  Sibling to
`LLVM_BACKEND.md` (both redesign aspects of the execution protocol);
supersedes the diagnostic notes in `todo/continuation_tco.md` and is
itself informed by `todo/commit_yield_determinism.md` and
`todo/generator_reuse_frame_chains.md`.

## 1. Motivation

A predicate whose clause body is a tail call to another predicate
pays one trampoline hop per solution just to forward it:

```
inner yields (wrap,   None)   # solution up to wrap
wrap  yields (caller, None)   # wrap forwards it
caller consumes
caller resumes wrap
wrap  yields (inner,  None)   # wrap pulls next
…
```

Two hops per solution at every wrapper level.  Wrapper chains (very
common in layered libraries, DCG expansions, meta-interpreters) pay
N hops per solution for an N-deep chain.  The work wrap actually
does between the two hops is zero — pure forwarding.

The fix is to route solutions from `inner` directly to `caller`,
skipping `wrap`.  This is a compile-time rewrite, but it requires a
protocol extension that the current tuple-yielding generator
interface cannot express.

## 2. Root cause — the protocol conflates three channels

Today every `StepGenerator` carries a single `parent` field that
steers three independent concerns:

1. **Where solutions go** — my consumer.
2. **Who resumes me on child exhaustion** — my completion point.
3. **Who handles exceptions I throw** — my handler chain.

The naive TCO rewrite (pass `caller` as `inner`'s parent) collapses
all three onto `caller`, losing (2) and (3) in the process:

- **Loses (2)**: when `inner` signals DONE, the signal goes to
  `caller` instead of `wrap`.  `caller` thinks we've exhausted.
  `wrap`'s `finally: trail.undo(_mark)` never runs; multi-clause
  predicates never try their next clause; enclosing `for`-loops
  never iterate.  The 2026-04-15 investigation caught this on two
  real tests (`exceptions.clausal::parent backtracks after catch
  failure`, `thread_safe_predicates.clausal::transitive path`).
- **Loses (3)**: exceptions from `inner` walk `parent` chains;
  bypassing `wrap` breaks `catch/3` placement invariants.

No compile-time rewrite alone fixes this.  The protocol itself has
to express the three channels separately.

## 3. Design — split-continuation protocol

Each call site's continuation becomes a record rather than a scalar:

- `proceed` — where to deliver a solution.
- `fail` — where to resume when the callee has no (more) solutions.
- `catcher` — where thrown exceptions propagate.

Names chosen for Prolog-native fit and active voice (the callee
*invokes* `proceed` / `fail` / `catcher`).  `fail` in particular is
preferred over `backtrack` because the caller's response on `fail`
is not always backtracking — it may be loop iteration, next-clause
fall-through, or propagating its own exhaustion.  Backtracking is a
*consequence* of receiving `fail` combined with the trail and the
caller's compiled control flow; it is not a separate signal.

### 3.1 Normal (non-TCO) call site

All three continuations point at the caller's frame:

```
proceed, fail, catcher = caller, caller, caller
```

### 3.2 Tail-call site

Solutions bypass us; completion and exception routing stay:

```
proceed = caller.proceed          # solutions skip our frame
fail    = this_frame              # we still wake on child DONE
catcher = this_frame              # we still handle thrown exceptions
```

After `inner`'s DONE wakes us, we run our `try: ... finally:
trail.undo(_mark)`, try any remaining clauses, and finally invoke
our own `fail` continuation.

### 3.3 Composition

Nested TCO chains compose naturally.  Each site picks its own three
values; there is no global routing table.  An LLVM backend
materialises the three as three pointer slots in the coroutine
frame.

### 3.4 The `commit` variant

Orthogonal to the protocol split but built from the same pieces (see
`todo/commit_yield_determinism.md`): the callee's `proceed` action
has a determinism-aware variant `commit(value)` meaning "deliver
this solution, and I guarantee there will be no more — retire me."
The caller's subsequent `fail` path walks straight past the retired
callee.  Saves one hop per semi-deterministic sub-call.

`commit` is a *variant of `proceed`*, not a fourth continuation slot.
The protocol carries three slots; the callee chooses between
`proceed` and `commit` at yield time based on its own control flow.

## 4. Execution-protocol encodings

### 4.1 Pure-Python trampoline

`StepGenerator`'s single `parent` becomes three explicit parameters
(**hard break**, no compatibility shim — a shim at a protocol-level
primitive lingers indefinitely):

```python
StepGenerator(dispatch, proceed, fail, catcher, *args, trail)
```

Three parameters passed separately, **not** bundled in a tuple or
record.  Rationale: in a right-to-left Sequence, `fail` changes per
goal (points at the previous goal's resume), `proceed` changes per
goal (points at the next goal or the leaf), while `catcher` is
usually invariant across the whole clause body (same try/catch
scope).  A bundle would be rewritten on every call site — no saving.
The LLVM backend stores the three into frame slots directly; the
Python signature mirrors that layout without inventing a Python-only
container.

Normal call sites pass `(this_generator, this_generator,
this_generator)` for the three.  TCO sites pass `(caller_proceed,
this_generator, this_generator)` — `proceed` is hoisted to the
caller; `fail` and `catcher` stay pointing at the current frame so
the frame still wakes on child exhaustion and still handles
exceptions.

Leaf yields split by action:

- solution:   `yield (proceed, None)`
- commit:     `yield (proceed, FINAL)`
- exhaustion: `yield (fail, _DONE)`
- throw: `LogicException` propagation driven by the trampoline's
  handler walk along the `catcher` chain (not `parent.parent…`).

The exception walk in `trampoline.py` is updated as part of Phase 1
— the old `parent` field is replaced by three distinct fields
(`proceed` / `fail` / `catcher`) from the start, and the walk
follows `catcher` chains.  No interim "parent == fail" aliasing.

A "no-fail" variant of `StepGenerator` is tempting for predicates
that cannot fail, but everything can fail on `MemoryError` in a
Python host — skip this micro-optimisation.

### 4.2 C extension

The existing `_trampoline.c` StepGenerator gains two extra slots.
Driver loop reads `(target, value)` unchanged; routing remains
literal (target IS the generator to resume).  `FINAL` is a new
sentinel handled like `DONE` but also de-registering the callee
from future pulls (wake the consumer's loop-exit path immediately
after value delivery).

### 4.3 LLVM backend

The three continuations are three function-pointer + frame-pointer
pairs in the coroutine frame:

```
{ resume_pc:   i32
, proceed:     (Frame*, Term*) -> void     ; solution handler
, fail:        (Frame*) -> void            ; exhaustion handler
, catcher:     (Frame*, Exn*) -> void      ; throw handler
, trail_mark:  i64
, saved_vars:  …
}
```

`commit(value)` = pop self from CP stack, then invoke `proceed`.
`fail` = pop self from CP stack, then invoke parent's `fail`.
`proceed(value)` = leave CP in place, invoke parent's `proceed`.

Three clean CP-stack actions.  This is the shape the protocol
design is optimised for; the pure-Python trampoline encoding is a
faithful projection of the same primitives onto Python generators.

## 5. Analysis pass — eligibility

Under the split-continuation protocol the eligibility rule broadens
dramatically from the failed 2026-04-15 attempts.  A `SubCall` is a
TCO candidate when:

1. It is in tail position — `Sequence`'s last op, or any arm of
   `Alternate` / `Branch` whose outer position is tail, etc.
2. It is not marked `tail_recursive`.  **TRO wins over TCO** — TRO
   is effectively a special case of TCO that rewrites the tail as
   an arg-reassignment loop with no StepGenerator at all, and the
   two treatments are mutually exclusive.  The analysis runs after
   TRO so any `SubCall` already carrying `tail_recursive=True` is
   skipped.
3. It is not inside a `MetaCall` that observes solutions (`once`,
   `findall`, `bagof`, `setof`, `call_nth`, `count_all`).

Enclosing `for`-loops (`MemberIn`), multi-clause predicates, and
surrounding `try/finally` trail undo are **all safe** because the
caller's frame still wakes on `fail` and runs to completion — only
the solution path is redirected.

The pass lives at `clausal/logic/compiler/optimisations/
continuation_tco.py` as `analyse → apply`, matching the contract
shape of `tro.py` / `destructive_reuse.py` / `call_site.py`.
`SubCall` gains a `tail_position: bool = False` hint; `apply`
writes `True` on eligible call sites.

### 5.1 Precise eligibility recursion

The analysis treats the clause body IR as its input, with the root
implicitly at tail position (since its continuation is the leaf
yield).  For each node type, `walk` either recurses into
tail-positioned children, marks a `SubCall`, or stops:

```
walk(node, marks):
    match node:
        Sequence(ops):          # only the last op inherits tail
            if ops: walk(ops[-1], marks)

        Alternate(ops):          # every arm is at tail
            for op in ops: walk(op, marks)

        Branch(test, then, else_, reified_test, tabled_naf):
            # test is NOT tail — its solutions are committed-choice
            # (general ITE: `_found` flag discards after first;
            #  reified: evaluated as a constraint, not enumerated;
            #  tabled_naf: routed through `_naf_tabled`).
            walk(then, marks)
            walk(else_, marks)

        SubCall(...):            # the thing we mark
            if not node.tail_recursive:
                marks.add(id(node))
            # TRO already owns self-recursive tails; the
            # mutual-exclusion is enforced at the hint level.

        Negate(op):              # op's success is observed
            stop

        MetaCall(kind, args):    # ALL kinds observe inner solutions
            stop
            # (once, call_nth, count_all, findall, bagof, setof,
            #  forall, setup_call_cleanup, call_cleanup, freeze,
            #  when, catch, catch_error, catch_recover, naf_tabled,
            #  throw, halt — none pass the caller's tail through)

        Unify | Dif | StructuralEq | ArithEval | FDCompare
          | MemberIn | ListPatternUnify | Fail | PyThunkOp:
            stop                 # leaf ops, no GoalOp children

        default: stop
```

Points worth spelling out:

- **`Sequence([MemberIn, SubCall])`** — the tail SubCall *is*
  eligible under this rule even though emitted code wraps it in
  MemberIn's `for`-loop.  The naive-protocol attempt failed here
  because the single-parent TCO routed DONE past the MemberIn
  frame; under split continuations, `fail` still points at the
  caller's frame so the loop's next iteration runs correctly.
- **Reified Branch** (`reified_test is not None`) — test operands
  are plain terms (`Unify.l`/`.r`, `FDCompare.l`/`.r`) lowered via
  `_reify_eq` / `_reify_fd`; no SubCall lives inside `test`, so the
  "don't recurse into test" rule is vacuous but stated for
  clarity.
- **`tabled_naf=True` Branch** — test *is* a SubCall but it's
  lowered via `_naf_tabled` as a one-shot observation, not as a
  tail call.  Same "don't recurse into test" treatment.
- **Nested `Sequence`** — composes correctly: the outer rule
  recurses into `ops[-1]`, which may itself be a `Sequence` whose
  last op gets the recursion next, etc.
- **`MetaCall.args` inners** — meta-constructs hold `GoalOp`-typed
  args (e.g. `once.inner`, `findall.inner`) that are themselves
  lowered goals.  Those inners are **not** in the caller's tail
  position; they are under the meta-construct's observation.  The
  `MetaCall: stop` rule is therefore complete — no need to walk
  into `args`.

### 5.2 `commit` detection (Phase 4, separate pass)

`commit` eligibility is a distinct analysis added later —
structural for a first cut (detect the final yield of the final
clause with no pending non-determinism), dynamic discovery
deferred.  Decide during Phase 3 whether to merge with the TCO
pass or keep separate; the answer likely depends on how much of
the recursion structure above is reusable for the commit rule.

## 6. Phased delivery

**Phase 1 — protocol hard-break.**

- `clausal/logic/trampoline.py`: `StepGenerator.__init__(func,
  proceed, fail, catcher, *args)`.  `parent` field retired entirely
  — replaced by `proceed` / `fail` / `catcher` attributes.  No
  compatibility shim.
- Trampoline driver exception walk updated: exceptions follow the
  `catcher` chain instead of `parent`.
- C extension `_trampoline.c`: struct layout mirrors Python —
  three distinct fields, ABI-bumped.
- Every external StepGenerator construction site updated in the
  same commit (`solve.py`, `builtins/_registry.py`,
  `modules/units.py`, `modules/spacy_module.py`,
  `modules/py/__init__.py`, trampoline test stubs).  `git grep
  StepGenerator(` is the punch list.
- Validation: full test suite green under both Python and C.  No
  behaviour change expected — the three fields all carry the same
  value in every caller until Phase 3.

**Phase 2 — codegen split for compiled predicates.**

- `TrampolineStrategy.function_params` emits
  `[self_name, proceed_name, fail_name, catcher_name]` instead of
  `[self_name, parent_name]`.
- `CompilationContext` gains `proceed_name` / `fail_name` /
  `catcher_name` fields (retire `parent_name`).
- Leaf yield splits: `emit_leaf_yield` → `yield (_proceed, None)`;
  `emit_exhaustion_yield` → `yield (_fail, _DONE)`.  (The current
  single `_tramp_parent` is replaced in both emission sites.)
- Every `StepGenerator(...)` emission passes three parents.  For
  all non-TCO call sites they are all `this_generator` — pure
  mechanical refactor, no behaviour change.
- Validation: byte-identical *solution output* (AST will differ —
  three params instead of one — but execution results identical).
  Full suite green.

**Phase 3 — TCO emission at eligible sites.**

- New `optimisations/continuation_tco.py` analysis pass (runs
  after TRO so the `tail_recursive` skip in §5 rule 2 applies).
- `SubCall` IR gains `tail_position` hint.
- Lowering reads the hint and emits the split-parent variant for
  marked call sites.
- Validation: full suite green.  Benchmarks under `benchmarks/`
  (see `microbench.py` / `workloads.py` patterns) — add at least:
  - list-processing over varying lengths (e.g. `length/2`,
    `append/3`, `last/2`, `msort/2`) at N ∈ {10, 100, 1k, 10k}.
  - a wrapper-chain microbench (N-deep pass-through predicates)
    at N ∈ {1, 4, 16, 64}.
  - a DFS / graph-traversal workload over the existing
    `benchmarks/workloads.py` graph.
  - type-error recovery: body that throws on wrong-type input
    inside `catch/3` — verifies the `catcher` slot handling under
    TCO.
  Many of these shapes already exist in the `.clausal` examples /
  fixtures; reuse existing workloads rather than invent new ones.
  "Measurable improvement" means ≥ 10% solution-time reduction
  on wrapper-chain N≥16; smaller but nonzero on the list ops.

**Phase 4 — `commit` variant.**

- New `FINAL` sentinel; structural analysis pass.
- Lowering emits `yield (_proceed, FINAL)` at detected sites.
- Trampoline driver handles `FINAL` (deliver value, de-register
  callee from future pulls).
- Validation: green suite; further measurable wins on
  semi-deterministic code.

**Phase 5 — LLVM alignment.**

- Update `LLVM_BACKEND.md` coroutine-frame layout to include the
  three continuation slots from the start.  The Python-backend
  protocol and the LLVM coroutine frames share one semantic model.

## 7. Risks and reversibility

- **Phase 1 / 2 signature change.**  Every compiled predicate
  changes arity (two extra params).  External callers (`solve.py`,
  tests, embedders) need a sweep.  Mitigation: Phase 2 is a pure
  mechanical refactor with byte-equality validation against Phase 1
  output; any drift is a bug in the refactor, not in semantics.

- **C-extension compatibility.**  The ABI changes.  Mitigation:
  bump a trampoline ABI version; re-build on `pip install -e .`.

- **Reversibility.**  Phases 1–2 are invertible if we discover a
  design flaw — the split is mechanical.  Phase 3 onward introduces
  a real optimisation; reverts remove the gain but not soundness.

- **Overlap with generator-reuse** (`todo/generator_reuse_frame_
  chains.md`).  Orthogonal on paper; design Phase 3 with an eye on
  the reuse idiom so continuation records are the same shape
  whether frames are fresh or reused.

## 8. Decision points to resolve before implementation

- **C-first or Python-first?**  The reference pure-Python
  trampoline is the usual place to prove the design; the C
  extension follows.  Default to Python-first unless performance
  testing requires the C change up-front.

- **`commit` in Phase 3 or Phase 4?**  The plan above separates
  them.  If the analysis for `commit` structural detection is cheap
  to fold into the tail-position analysis, merging saves a pass.
  Decide during Phase 3.

- **Exception channel split timing.**  *Resolved*: three distinct
  fields from Phase 1, exception walk uses the `catcher` chain.
  No interim aliasing — a rename-half-now-finish-later shape would
  leave a misnamed `parent` slot behind until some future cleanup.

## 9. Relationship to other proposals

- **TRO** (self-recursive tail calls, shipped) — orthogonal; same
  hint-on-`SubCall` shape.  Mutual exclusion at the hint level.
- **LLVM backend** — this plan's protocol is designed to map 1:1
  onto LLVM coroutine frames; landing it in the Python backend
  first de-risks the LLVM design.
- **Generator reuse** — orthogonal; composes cleanly because
  continuation records are per-call-site values, not per-frame
  state.
- **`commit` variant** — captured at `todo/commit_yield_
  determinism.md`; folded into this plan as Phase 4.

## 10. Status

Proposal.  Not scheduled.  Revisit when LLVM-backend design
resumes, or when a wrapper-heavy workload surfaces in benchmarking.
