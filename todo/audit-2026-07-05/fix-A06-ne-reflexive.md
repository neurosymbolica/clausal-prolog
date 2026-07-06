# fix(A06-F010): fd_ne(X, X) accepted at post time

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F010
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestNeReflexivity::test_ne_same_var_fails_at_post (xfail — flip to pass)

## Bug

`X != X` posts successfully (True) — NeConstraint's both-var branch
(clpfd.py:744-759; C _clpfd_propagate.c:1124-1219) never checks operand
identity, and neither singleton exists on an unbounded domain. SWI
`X #\= X` fails immediately. Labeling later yields 0 solutions (guard), but
an unlabelled query answers "true" with an unsatisfiable pending constraint.
Also inconsistent with dif/2: `dif(X, X)` fails immediately (A05 seam).

## Fix direction

In fd_ne (both impls) after deref: `if lhs is rhs: return False`. Same check
at the top of NeConstraint.propagate / ne_propagate for the aliasing-later
case (unify(X, Y) merges two vars that share a NeConstraint — verify the
merge path detects it; today it fails only via eventual singleton removal).

## Acceptance

- xfail passes; `test_ne_same_var_yields_no_labelled_solutions` stays green;
  differential suite unchanged.
