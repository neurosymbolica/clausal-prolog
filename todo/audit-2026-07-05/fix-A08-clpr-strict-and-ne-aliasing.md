# fix(A08): CLP(R) strict-< non-termination and != aliasing blindness

**Findings:** A08-F010 (correctness, critical — hang), A08-F011 (correctness, high)
**Tests:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestClprAliasing` (3 xfails; two run the repro in a subprocess because the current code HANGS)

## Bugs
1. `RealLtConstraint.propagate` (`clpr.py:556-568`) narrows by one ULP per
   pass and re-queues itself. With `lhs` and `rhs` aliased to the same var
   (`{X<Y}, X is Y`) or a cycle (`{X<Y, Y<X}`), propagation walks the interval
   ULP-by-ULP (~1e17 steps over [0,10]) — an effective hang instead of failure.
2. `RealNeConstraint.propagate` (`clpr.py:571-583`) fails only when both sides
   are equal point intervals; after `X is Y` both sides deref to the same var
   and the unsat store `{X != Y, X = Y}` is accepted.

## Fix sketch
In both propagate methods, first check `deref(lhs) is deref(rhs)` (after
deref): for `!=` and `<` on structurally identical terms, fail immediately.
That fixes the aliasing/unify cases. For the two-constraint cycle
`{X<Y, Y<X}` consider also a propagation budget or narrowing-progress
threshold that converts ULP-creep into failure (the intervals provably shrink
to empty; detect `hi - lo` no longer decreasing meaningfully and force the
fixpoint via interval emptiness on `llo >= rhi` with outward-rounded slack).

## Acceptance
All three xfail tests flip to pass (and can then be inlined instead of
subprocess-guarded); `tests/test_clpr.py` stays green.
