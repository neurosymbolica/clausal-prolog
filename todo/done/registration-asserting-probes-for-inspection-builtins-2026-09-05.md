# Registration-asserting probes needed for the non-`type_checks` inspection builtins

Filed at P3-2 close-out (ledger: Task 2 minor, "fold into T9 straggler sweep" —
not picked up there, filed here instead per the ledger's own close-out
convention).

## The cautionary tale that motivates this

Task 2's §12 builtin-surface sweep originally claimed `callable/1` (among
others) was "checked clean" against cell shapes. It was not checked at all:
the predicate is registered under the name `callable_` (a trailing underscore,
to avoid shadowing Python's builtin), the probe called `call("callable", ...)`
without the underscore, `call()` raised `KeyError` for the unregistered name,
and — because the probe compared the SAME `KeyError` on both the cell input
and the Compound control — the comparison read as "twins agree" when in fact
neither twin had run at all. Fixed in round 2 (`.superpowers/sdd/p32-cell-default-flip/task-2-report.md`
§20-21): `callable_/1` got its own cell branch (it DID diverge, once actually
exercised), and the fix round rebuilt `type_checks.py`'s coverage with
**registration-asserting probes** — a probe that first asserts the predicate
name resolves via `call()`/the module registry before treating any output
comparison as evidence.

## The residual gap

That registration-assertion discipline was applied to `type_checks.py`'s
predicates only. Task 2's own report (§25, concern 1) names seven
non-`type_checks` predicates from the same §12 sweep list that were
**never re-audited the same way**:

- `term_variables/2`
- `copy_term/2`
- `=../2`
- `functor/3`
- `arg/3`
- `numbervars/3`
- `dif/2`

All seven produced non-trivial, SHAPE-SPECIFIC output during the original
round-1 probe (not a matching error string like the `callable_` incident) —
which is positive evidence they actually ran against a real cell — but it is
weaker than an explicit "the name I called is the name that's registered"
assertion. The `callable_` incident shows exactly how a probe can look
healthy (produce plausible output) while silently not exercising what it
claims to.

## Why it's not fixed here

- P3-2's task briefs never scoped a second full sweep of the non-`type_checks`
  builtin surface; Task 9 (the phase's straggler sweep) was the intended
  catch-all but did not pick this specific item up.
- It is evidence-hardening, not a known bug — no divergence has been found for
  any of the seven; the concern is about probe RELIABILITY, not a known wrong
  answer.

## What to do when picked up

For each of the seven names, write (or extend an existing) test that:
1. Asserts the predicate name used in the probe is the one actually registered
   (mirroring `type_checks.py`'s fix — resolve through the same lookup path
   the probe's `call()` uses, and fail loudly if it doesn't match).
2. THEN compares cell-shaped input against its `Compound`/class-instance
   analog, as the original round-1 probes already do for output.

## Where to look

- `.superpowers/sdd/p32-cell-default-flip/task-2-report.md` §20-21 — the
  `callable_` incident and the registration-assertion fix pattern to mirror.
- `.superpowers/sdd/p32-cell-default-flip/task-2-report.md` §25 — the exact
  list of seven names still owed this treatment.
- `clausal/logic/builtins/type_checks.py` — the FIXED reference
  implementation (registration-asserting probes already in place there).
- Wherever `term_variables/2`, `copy_term/2`, `=../2`, `functor/3`, `arg/3`,
  `numbervars/3`, `dif/2` are implemented/tested — grep each name; they are
  spread across `clausal/logic/builtins/inspection.py` and related modules.

## Done

Done at P3-3 Task 8, commit 37af492f. Registration-asserting probes for all
seven names added in `tests/test_inspection_registration_probes.py`: each
resolves the name through `_BUILTINS`/`_DB_BUILTINS` first, then compares a
cell-shaped input against its `Compound` twin side by side. `=..` itself is
confirmed unregistered; the registered spelling is `unpack/2`
(`clausal/logic/builtins/inspection.py::_univ__2`) and that is the name the
probe drives.
