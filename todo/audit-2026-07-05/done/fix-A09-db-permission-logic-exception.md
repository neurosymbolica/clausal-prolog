# fix(A09-F006): locked-predicate assertz/retract RuntimeError is swallowed → silent failure

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F006
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F006_assertz_locked_raises, ::test_F006_retract_locked_raises (xfail — flip to pass)
**Gated by:** A09-D002 (error-signaling convention). Related engine bug: investigate-A09-runtimeerror-swallow.md.

## Bug

assertz/asserta/retract raise `RuntimeError("Predicate … is locked …")`
(database_ops.py:97-101, 130-134, 172-176). The trampoline drive loop treats
ANY RuntimeError from a generator as exhaustion (runtime/_trampoline.c:664-666,
719-721) → the error is silently converted to failure. Docs promise "a
permission error". This is the root cause of the known pitfall "assertz on a
non-dynamic predicate fails silently (0 sols)".

## Fix direction

A09-side (independent of the engine fix): raise
`LogicException(permission_error("modify", f"{functor}/{arity}", "assertz/1"))`
instead of RuntimeError (add permission_error to clausal/logic/exceptions.py
if missing — ISO has it). LogicException routes correctly through the drive
loop and is catchable by catch/3.

## Acceptance

- Both xfails pass (LogicException surfaces); catch/3 can intercept it;
  dynamic-predicate assertz unchanged.
