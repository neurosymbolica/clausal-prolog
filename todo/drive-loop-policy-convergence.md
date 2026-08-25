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
4. **Pre-existing, anomaly-only C/py divergence on a malformed step.**
   A frame that yields something other than a 2-tuple (or a non-`None`,
   non-`StepGenerator` target) is a protocol violation, and the two cores
   disagree on where the resulting `TypeError` goes:
   - C: `drive_to_root_yield`'s explicit shape checks
     (`clausal/logic/runtime/_trampoline.c:541` — not a 2-tuple —
     and `:558` — target not `StepGenerator`/`None`) raise `TypeError`
     directly as `DRIVE_ERROR`, outside any routing; it is never offered
     to a `catch/3`.
   - Python twin: there are no shape checks. `gen, value = gen.send(value)`
     (`clausal/logic/_trampoline_py.py:225`) sits *inside* the same
     `try` (`:221-237`) that routes ordinary exceptions, so a malformed
     step's unpack `TypeError` is caught by `except Exception as exc:`
     (`:230`), passes `_is_routable` (TypeError isn't excluded), and is
     offered to an enclosing `catch/3` — the twin's own docstring claim
     ("KEEP IN SYNC ... the parity test enforces the agreement",
     `_trampoline_py.py:1-10`) overstates coverage here.
   - This predates the one-drive-loop refactor (the old per-entry-point
     fallbacks had the same shape) and only manifests on a compiler bug
     or hand-built protocol violation — no compiled predicate can
     produce a malformed step. The parity corpus does not currently pin
     either side of this. Flagged by the final whole-branch review of
     `refactor/one-drive-loop-2026-08-26` (Minor-2); not fixed there —
     recorded here as a decision to make (add shape checks to the twin,
     C is canonical; or formally document the exclusion in the twin's
     module docstring and the corpus).

Converging any of these is a behaviour change: decide, test, then flip
the flag in BOTH cores (the parity corpus keeps them agreeing).
