# The drive-loop policy flags preserve historical differences — converge or bless them

**Filed:** 2026-08-26, from the one-drive-loop refactor
(docs/superpowers/specs/2026-08-26-one-drive-loop-design.md).
**Status: OPEN — design question, deliberately parked.**

The refactor collapsed the drive loops to one core per language with two
flags whose values PRESERVE how each entry point historically behaved:

| entry point         | intercept_ts | stopiteration_is_exhaustion |
|---------------------|--------------|------------------------------|
| trampoline          | no           | no                           |
| solutions           | yes          | no                           |
| _drive_until_yield  | yes          | yes                          |

`tests/test_trampoline_parity.py::test_mid_chain_suspend_is_NOT_intercepted_by_trampoline`
pins the first difference on purpose.

Open questions, each a deliberate decision rather than a refactor
side-effect:

1. Should `trampoline()` intercept mid-chain `_TABLING_SUSPEND`?  Today a
   suspend reaching a `trampoline()`-driven chain passes through as a
   value.  Is any `trampoline()` call site reachable from tabled code?
2. Should `solutions()` treat StopIteration/PEP-479 from a send as
   exhaustion the way `_drive_until_yield` does, instead of raising?
3. `FINAL` is only interpreted by `solutions`; when producers start
   emitting it (CONTINUATION_TCO_PLAN Phase 4b+), `_drive_until_yield`
   will deliver it as a truthy solution and then re-pull a retired root —
   decide its semantics there BEFORE any producer emits it.

Converging any of these is a behaviour change: decide, test, then flip
the flag in BOTH cores (the parity corpus keeps them agreeing).
