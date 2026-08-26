# The drive-loop policy flags preserve historical differences — converge or bless them

**Filed:** 2026-08-26, from the one-drive-loop refactor
(docs/superpowers/specs/2026-08-26-one-drive-loop-design.md).
**Status: DONE — decided and landed, 2026-08-26.**

The refactor collapsed the drive loops to one core per language with two
flags whose values PRESERVED how each entry point historically behaved.
All four open questions are now decided; the table after convergence:

| entry point         | intercept_ts | stopiteration_is_exhaustion |
|---------------------|--------------|------------------------------|
| trampoline          | **yes**      | no (blessed, see Q2)         |
| solutions           | yes          | **yes**                      |
| _drive_until_yield  | yes          | yes                          |

## Decisions

1. **`trampoline()` intercepts mid-chain `_TABLING_SUSPEND` — converged.**
   Its only runtime call site is the Z3 propagator embedding
   (`clpz3._run_goal` / `_run_goal_simple`), which discards the returned
   value: a suspend leaking through as a value fabricated success there,
   and the parent frame receiving the raw sentinel as a resume value was
   nonsense in compiled code.  Interception (suspend → DONE send, the
   consumer stays registered in the table) is what the other two entry
   points always did.  Pinned by
   `test_mid_chain_suspend_is_intercepted_by_trampoline_too`.

2. **`solutions()` treats StopIteration/PEP-479 from a send as
   exhaustion — converged; `trampoline()`'s raise is blessed.**
   A04-F009 already established on the main query path that a PEP-479
   wrapper is a converted exhaustion; the public collector now agrees
   (returns what was collected) instead of leaking an engine
   `RuntimeError` to embedders — and the exhaustion test runs BEFORE
   routing, so no `catch/3` sees it.  `trampoline()` keeps raising
   deliberately: its contract (return the root-yield value) has no way
   to represent exhaustion, so a StopIteration there stays a loud
   protocol anomaly.  Pinned by the two
   `test_*pep479_wrapper*` corpus cases.

3. **`FINAL` at the root retires the StepGenerator for every
   pull-driver — implemented before any producer emits it.**
   `FINAL` means "here is a solution AND I am retiring"
   (CONTINUATION_TCO_PLAN Phase 4: deliver value, de-register from
   future pulls).  `StepGenerator` (both cores) gained a `retired`
   flag: `_drive_until_yield` delivers the FINAL solution (True), marks
   the root retired, and answers None to every later pull without
   resuming the retired generator; `solutions` already stopped pulling
   and now also sets/honours the flag so the two pull-drivers agree on
   one root.  Pinned by the three `*retirement*` corpus cases.

4. **The C malformed-step shape checks are now in the Python twin —
   C is canonical.**  A step that is not a 2-tuple, or whose target is
   neither `StepGenerator` nor None, raises `TypeError` from the driver
   directly, OUTSIDE exception routing — the twin used to route the
   unpack `TypeError` to an enclosing `catch/3`.  The twin's
   `_drive_to_root_yield` now performs the same explicit checks (with
   the same messages) before the routing `try`, and its KEEP-IN-SYNC
   docstring claim is accurate again.  Pinned by the
   `test_malformed_step_*` corpus cases across all three entry points.

## Verification (2026-08-26)

- Parity corpus `tests/test_trampoline_parity.py`: 52 passed (C +
  Python twin).
- Trampoline/tabling/solve/catch/source-location modules: 232 passed;
  clpz3 modules (the `trampoline()` consumer): 231 passed.
- Full suite chunked: failure set identical to baseline (remaining
  failures are environmental — ortools / python-sat not installed,
  plus a pre-existing order-dependent doc-snippet test — each verified
  present at baseline).
- Perf gate, interleaved A/B (5 rounds, medians): fib −2.4%,
  nqueens −0.9%, qsort −2.9%, naf_ite −1.1%, trampoline 1-step
  microbench −7.8% — no regression; deltas within noise, none positive.
