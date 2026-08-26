# One drive loop per language — design

**Date:** 2026-08-26
**Todos:** `todo/one-drive-loop-not-six.md`, `todo/c-and-python-trampoline-twins-have-no-parity-test.md`
**Approach approved:** corpus-first (Option A), 2026-08-26.

## Problem

The trampoline drive loop — interpret `(gen, value)` steps, decide when to
stop, route exceptions to `catch/3` — exists as independent copies that each
learn fixes separately. The `catch/3` routing broadening (`463291d6`,
`883cdf08`) had to be applied by hand to every copy and missed two of them.

Inventory as of this design (verified by reading, 2026-08-26):

| # | copy | where | TS interception | StopIteration = exhaustion | exception routing |
|---|------|-------|-----------------|---------------------------|-------------------|
| 1 | `trampoline_func` | `logic/runtime/_trampoline.c` | no | no | yes |
| 2 | `solutions_func` | `logic/runtime/_trampoline.c` | yes | no | yes |
| 3 | `drive_until_yield_func` | `logic/runtime/_trampoline.c` | yes | yes | yes |
| 4–6 | `trampoline` / `solutions` / `_drive_until_yield` | `logic/trampoline.py` (fallbacks, **never executed by the suite** in a built tree) | mirror 1–3 | mirror 1–3 | yes |
| 7 | `_tramp_call` | `logic/runtime/tramp_call.py` (always runs, even with the C extension) | **no** | no | yes |
| 8 | `_naf_has_solution` | `logic/runtime/tramp_call.py` | **no** | no | yes |
| 9 | general-ITE arm | `logic/compiler/lower_python_trampoline.py:105-181`, emitted as generated AST | yes (mid-chain only) | no | **NO** |

Copy 9 was not in the todo's table of six. Its `step_send` statements step
`g.send(v)` with no `try`/`except` at all, so a `catch/3` inside the
*condition* of a general if-then-else compiled in trampoline mode is almost
certainly inert — the same defect shape as the `Negate` bug fixed 2026-08-25.
It also treats a root-level `(None, _TABLING_SUSPEND)` as a solution (the
A04-F008 shape). The legacy emitter it once mirrored
(`_compile_general_ite_trampoline`) is already deleted; the lowering is the
only copy. **To be confirmed with a failing test before any fix is claimed.**

The C twins (1–3) and Python twins (4–6) are kept in sync by `KEEP IN SYNC`
comments only; nothing executes the fallbacks, so nothing would detect
divergence.

## Goals

1. A new exception-policy or step-protocol change touches **one site per
   language**: one C core, one Python core. (Two, not one — the C extension
   is the production path and must stay; the pure-Python twin is the
   no-build fallback and must stay.)
2. No drive loop is emitted as generated AST.
3. A parity test module runs a shared behavioural corpus against **both**
   implementations in one session; deleting a routing branch from either
   side reds it.
4. The `catch/3`-inside-ITE-condition bug is confirmed and fixed.
5. **Performance-neutral where it matters, measured, not assumed.** The
   three C entry points are the engine's innermost loops; the refactor
   must not regress them (see Performance below). The consumer re-basing
   is expected to be a win and must be shown to be one.

## Non-goals

- Converging the per-entry-point policy differences (TS interception in
  `trampoline`, `FINAL` handling outside `solutions`, exhaustion-on-
  StopIteration outside `_drive_until_yield`). The refactor **preserves
  today's per-entry-point behaviour exactly** via mode flags; deliberate
  convergence is parked as a follow-up todo.
- Any change to the step protocol itself, to `StepGenerator`, or to the
  continuation-TCO plan (`FINAL` stays a cold sentinel).
- Touching the shallow strategy or the `arg_index` dispatch loops (audited:
  they are PEP-380 delegating wrappers that forward `send`/`throw` without
  interpreting the protocol — not drive-loop copies).

## End state

### Core + wrappers, per language

The shared primitive in both languages is **advance to the next root
yield**: step the chain, intercepting `_TABLING_SUSPEND` and routing
exceptions per policy, until the current step is `(None, value)` or the
chain is exhausted / an exception propagates.

- **C** (`_trampoline.c`): one `static` helper,
  `drive_to_root_yield(sg_or_step, flags, &value)` returning
  {`YIELDED`, `EXHAUSTED`, `ERROR`}. `trampoline_func`, `solutions_func`
  and `drive_until_yield_func` become thin wrappers: each calls the core
  with its flags and applies its own stop condition to the root-yield
  value (`trampoline`: return the value; `solutions`: DONE/TS/FINAL vs
  collect-and-repull; `_drive_until_yield`: DONE/TS → None, else True).
- **Python**: the fallbacks move out of the `except ImportError:` block in
  `logic/trampoline.py` into their own always-importable module
  (`logic/_trampoline_py.py`) with the same core+wrappers shape.
  `logic/trampoline.py` keeps its public surface:
  `try: from runtime._trampoline import … except ImportError: from
  _trampoline_py import …`. Making the pure module directly importable is
  what makes the parity harness trivial — no `sys.modules` blocking, no
  reload games.

Mode flags (initial values preserve today's behaviour, per the inventory
table): `intercept_tabling_suspend`, `stopiteration_is_exhaustion`. `FINAL`
is passed through as a root-yield value; only the `solutions` wrapper
interprets it, exactly as today.

### Consumers re-based on `_drive_until_yield`

`_drive_until_yield` *is* the per-solution primitive, so the remaining
Python-side copies stop being loops:

- `_tramp_call` → `sg = StepGenerator(…)` then
  `while _drive_until_yield(sg): yield None`.
- `_naf_has_solution` → `return _drive_until_yield(sg) is True`.
- The general-ITE lowering emits
  `while $drive_until_yield(_ite_sg): found = True; <then-stmts>` instead
  of an inline loop (`$drive_until_yield` injected into predicate globals
  alongside `$naf_has_solution` in `compiler/predicate.py`).

Because `_drive_until_yield` resolves to the C implementation in a built
tree, the simple-mode bridge, NAF, and ITE conditions get C-driven stepping
— a performance improvement in addition to the single-policy win.

**Accepted behaviour changes** from re-basing (all three inherit
`_drive_until_yield`'s policy, which is the policy the main query path in
`solve._drive_trampoline` already uses):

- `_tramp_call` / `_naf_has_solution` gain `_TABLING_SUSPEND` interception
  and exhaustion-on-StopIteration (today they have neither).
- The ITE loop gains exception routing (the bug fix) and stops treating a
  root-level `_TABLING_SUSPEND` as a solution.
- The ITE condition also gains exhaustion-on-StopIteration/PEP-479: the old
  emitted loop let a `StopIteration` (or its PEP-479 `RuntimeError` wrapper)
  from the condition propagate; under `_drive_until_yield` it is now treated
  as exhaustion, so the condition fails and the else-branch runs instead of
  raising. Flagged by the final whole-branch review (Minor-4) — a cold,
  anomaly-only path with no compiled-predicate test; the corpus's
  entry-send PEP-479 case (`test_entry_send_pep479_wrapper_exhausts_duy_but_raises_via_solutions`
  in `tests/test_trampoline_parity.py`) pins the underlying
  `_drive_until_yield` mechanism the ITE now inherits.

The first two are exercised directly by a compiled-predicate test; the
third is pinned only at the mechanism level (no compiled-predicate test),
per the review — not assumed, but not directly demonstrated either.

### Parity harness

`tests/test_trampoline_parity.py`, parameterised over
`clausal.logic.runtime._trampoline` (C; skipped with a loud reason if the
extension is not built) and `clausal.logic._trampoline_py`. The corpus
drives **hand-built `StepGenerator` chains** constructed with the
implementation-under-test's own `StepGenerator` type — this sidesteps the
compiled-globals obstacle (`compiler/predicate.py:746`) entirely; no
recompilation needed. Compiled-predicate behaviour stays covered by the
existing suite plus the new ITE test.

Corpus cases, run against each of `trampoline`, `solutions`,
`_drive_until_yield` where the case is expressible for that entry point:

1. single and multi-solution enumeration; exhaustion via `DONE`
2. `FINAL` at root (with and without snapshot) — `solutions` only
3. `_TABLING_SUSPEND` at root and mid-chain
4. routable exception absorbed by a catcher at depth k (k = 1, 2)
5. declining handler re-raises; next catcher up absorbs
6. no taker: exception propagates unchanged, original traceback preserved
7. unroutable: `StopIteration`, `GeneratorExit`, `KeyboardInterrupt`,
   `SystemExit` propagate unrouted
8. PEP-479 wrapper (`RuntimeError` with `StopIteration` cause):
   exhaustion for `_drive_until_yield`, propagation elsewhere
9. engine-protocol `RuntimeError` (`__clausal_engine_protocol__`): never
   offered to a catcher
10. snapshot callable invoked while bindings live (`solutions`)

Acceptance (from the todo): deleting a routing branch from **either**
implementation reds this module — to be demonstrated once by temporary
mutation of each side during development, not kept as an automated check.

## Performance

Every trampoline-mode goal resolution runs through `drive_until_yield_func`
(via `solve._drive_trampoline`) or `solutions_func`; their inner loop is
the hottest code in the engine. Two obligations follow.

**Constraint: the C core must compile to what the three loops are today.**
The core is a `static inline` helper whose `flags` argument is a
compile-time constant at each of the three call sites, so the compiler
constant-folds the flag tests and dead-branch-eliminates the unused
policies — one source specialising into effectively the same three loops.
Per-iteration costs that exist today (`PyTuple_CheckExact` unpack,
`StepGen_Check`, the `_TABLING_SUSPEND` pointer compare where enabled)
stay; no new per-iteration allocation, indirect call, or runtime flag
dispatch is acceptable in the steady-state step path. If measurement shows
the inlined-core shape regressing, the fallback is an internal macro or
an included template expanded per wrapper — uglier, but the "one site to
edit" goal survives; what is not acceptable is trading hot-loop speed for
the refactor.

**Expected wins, to be demonstrated:** `_tramp_call`, `_naf_has_solution`
and the ITE lowering currently step the chain in interpreted Python (or
emitted-AST Python) even when the C extension is built; after re-basing,
their stepping runs in C, at the cost of one `$drive_until_yield` call per
solution rather than per step. Net win expected for any goal that takes
more than ~one step per solution; the NAF/ITE benchmark below confirms it
(and would catch the pathological opposite: a helper-call-per-solution
regression on trivial one-step goals).

**Measurement protocol** (built tree, canonical practice: run from the
clone with `/workspace/clausal/venv/bin/python`):

- Baseline **before stage 3** and compare after each of stages 1 and 3:
  - `benchmarks/microbench.py` — already measures trampoline dispatch
    (1-step) and `StepGenerator` allocation at the ns level.
  - `benchmarks/workloads.py` — fib, nqueens (deep backtracking), qsort,
    graph, tabling: all drive-loop-bound macro workloads.
- Add one workload exercising the re-based consumers: a NAF-heavy and
  general-ITE-heavy predicate (negation in an inner loop, if-then-else
  with a multi-solution condition), since no existing workload isolates
  `$naf_has_solution` / the ITE path. Added in stage 1 (it also serves as
  the perf check for the bug fix's change of emission).
- Compare medians of repeated runs; ns-level microbenches are noisy, so
  regressions are called on the median, not single runs.
- Acceptance for stage 3: no macro-workload regression beyond run-to-run
  noise; microbench trampoline dispatch within noise of baseline; the
  NAF/ITE workload at least as fast as baseline.

The Python twin (`_trampoline_py.py`) is the no-build fallback; its
wrapper-over-core call per root yield is accepted and not benchmarked.

## Sequencing (each stage lands green)

1. **ITE bug, test-first.** Failing test in `tests/test_catch_trampolined.py`
   (`catch/3` inside a general-ITE condition, trampoline mode) plus a
   root-TS case if expressible; fix by emitting `$drive_until_yield`.
   Smallest user-visible win; lands independently of everything else.
   Includes the NAF/ITE workload benchmark, measured before and after the
   emission change.
2. **Extract + harness.** Move the Python fallbacks to
   `logic/_trampoline_py.py` (mechanical move, no logic change); land
   `tests/test_trampoline_parity.py` green against both implementations
   as they are today.
3. **Core+wrappers refactor.** C `drive_to_root_yield` + thin wrappers;
   Python twin to the same shape; re-base `_tramp_call` /
   `_naf_has_solution` on `_drive_until_yield`. Corpus and suite green;
   benchmark comparison against the stage-2 baseline passes the
   acceptance thresholds in the Performance section.
4. **Bookkeeping.** Record the audit (below) in the todos, archive both,
   file the policy-convergence follow-up todo.

Verification throughout per project practice: run the suite chunked with
`/workspace/clausal/venv/bin/python` from the clone; in worktrees run
`build_ext` before diffing failure **sets** (not counts) against baseline.

## Audit record (goal 2 / todo's audit ask)

Searched `logic/compiler/` for engine control flow emitted as AST or
open-coded stepping of the `(gen, value)` protocol, 2026-08-26:

- `lower_python_trampoline.py` — `Negate`: already lifted to
  `$naf_has_solution`. **General ITE: inline loop found** (copy 9 above);
  fixed by stage 1.
- `goal_shallow.py` — calls the `$tramp_call` runtime helper; no emitted
  loop.
- `arg_index.py` — `_drive_tro_bucket` and the TRO `dispatch` closures
  forward `send`/`throw`/`close` (PEP-380 delegation) without interpreting
  steps or owning exception policy; not copies. Left untouched.
- `goal_trampoline.py`, `control_constructs.py`, `tro.py` — no protocol
  stepping emitted.

Addendum (2026-08-26, later the same day): the parked policy-convergence
follow-up was decided and landed — all three entry points now intercept
mid-chain `_TABLING_SUSPEND`; `solutions` treats StopIteration/PEP-479
as exhaustion (`trampoline`'s raise is blessed — its contract cannot
represent exhaustion); a root-level `FINAL` retires the StepGenerator
for every pull-driver; and the Python twin gained the C core's
malformed-step shape checks.  Decision record:
`todo/done/drive-loop-policy-convergence.md`.

Addendum (post-implementation): a repo-wide search for AST-emitted
protocol stepping (`attr="send"` over `clausal/logic/compiler/`,
including `optimisations/`) confirmed the general-ITE arm held the only
emitted drive loop; it now emits `$drive_until_yield`.  The parity
corpus found one pre-existing C/Python divergence on landing (a
returning inner generator: C raised the marked engine-protocol
RuntimeError, the Python twin surfaced bare StopIteration which
`_drive_until_yield` swallowed as silent exhaustion) — fixed in the
twin, pinned by
`test_generator_that_returns_is_a_protocol_error_not_a_catchable`.

## Risks

- **Hot-loop regression from the C core extraction.** Covered by the
  Performance section: `static inline` + constant flags, benchmarked
  against a pre-refactor baseline, with the macro/template fallback if
  inlining doesn't deliver.
- **Per-solution helper-call overhead in the re-based consumers** on
  trivial one-step goals (NAF over a fact, ITE with a deterministic
  condition). The NAF/ITE workload includes exactly these shapes so the
  trade is visible, not assumed away.
- **C refactor of exception paths / refcounting.** Mitigated by
  corpus-first ordering (stage 2 before stage 3) and by the traceback-
  identity corpus case (pins the `PyException_SetTraceback` behaviour that
  `tests/test_source_locations.py::TestSourceLocationsG6` also pins).
- **Behaviour drift from re-basing consumers.** The three accepted changes
  are listed above and each gets a test; anything else showing up in the
  failure-set diff is a defect in the refactor, not an accepted change.
- **`_trampoline_py` import cycle** (`solutions` lazily imports
  `logic.tabling`): the move keeps the lazy import inside the function
  bodies, as today.
