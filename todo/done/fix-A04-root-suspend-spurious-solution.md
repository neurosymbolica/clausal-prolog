**DONE — commit a3408b08 (F007+F008 shipped together).** Both tabled wrappers drop a poisoned entry on abnormal exit; _drive_trampoline closes the StepGenerator chain in a finally so cleanup is synchronous (not GC-timed). All five root drivers treat (None, _TABLING_SUSPEND) as exhaustion. Flips the F007 (once/exception/mechanism) + F008 tests. Full suite: 8818 passed, 0 failures.

---

# fix(A04-F008): root-level (None, _TABLING_SUSPEND) misread as a solution — spurious unbound answers

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F008
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF008RootSuspendSpuriousSolution` (xfail — flip to pass)

## Bug

All root drivers handle the `gen is None` case BEFORE the
tabling-suspend interception, and treat any value ≠ DONE as "solution":

- Py fallback: `trampoline.py:238-241` (`_drive_until_yield`),
  `:191-204` (`solutions`)
- C: `runtime/_trampoline.c:684-691` (`drive_until_yield_func`),
  `:536-559` (`solutions_func`)

A consumer whose `_proceed` is the root (None) — the orphaned-consumer
state left by A04-F007 — yields `(None, _TABLING_SUSPEND)` and the driver
reports a solution while the output vars are UNBOUND: post-`once()`
re-query of `path(1,Y)` yields `(2,)` then `(AttVar(_n),)`.

## Fix direction

In each driver's `gen is None` arm, treat `_TABLING_SUSPEND` explicitly:
it is a control sentinel, never a solution — convert to exhaustion
(return None / stop collecting), mirroring what the non-root interception
already does. Four sites (2 Py, 2 C) + `_trampoline_to_simple_adapter`
(`tabling.py:566-593`) which has the same `gen is None → yield` shape.

With `fix-A04-poisoned-evaluating-tables.md` applied the state becomes
unreachable in normal use; fix it anyway (defense in depth — any future
consumer-at-root path would silently fabricate solutions).

## Acceptance

- F008 xfail flips: no unbound answers after a poisoned once().
- A raw StepGenerator whose generator yields `(None, _TABLING_SUSPEND)`
  produces zero solutions via both `_drive_until_yield` and `solutions`
  (unit-level, C and Py).
