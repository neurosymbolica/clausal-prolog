# fix(A09-F008): retract/1 undoes the head-unification bindings

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F008
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F008_retract_binds_pattern (xfail — flip to pass)
**Gated by:** A09-D003 — recommendation: ISO binding semantics.

## Bug

`retract__1` (database_ops.py:181-218) unifies the argument with each clause
head on a THROWAWAY `Trail()` and undoes it before yielding —
`assertz(seen2(5)), retract(seen2(X))` succeeds with X unbound. ISO/SWI bind
X=5 (that is what makes "retract by pattern" and retract-loops usable).
Also not re-satisfiable on backtracking (documented; ISO retract is).

## Fix direction

Perform the matching head-unification (head + normalization Unify body goals)
on the REAL trail for the clause actually removed, so bindings escape with
the solution and are undone by normal backtracking. Re-satisfiability
(retry next matching clause on redo) is a natural extension — implement if
cheap, else note in docs.

## Acceptance

- xfail passes (X=5); ground retract unchanged; failed retract leaves no
  bindings.
