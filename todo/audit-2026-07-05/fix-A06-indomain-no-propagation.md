# fix(A06-F008): in_domain narrowing does not re-propagate existing constraints

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F008
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestInDomainPropagation::test_in_domain_propagates_through_eq (xfail — flip to pass)

## Bug

`_post_domain` (clpfd.py:1834-1864) writes the narrowed domain with a bare
`put_attr` — no propagation queue, no constraint re-fire (only the singleton
case propagates, via the unify hook):

    X == Y, in_domain(X, 1, 5)    # Y stays (-inf, inf)
    label([Y])                    # ValueError "unbounded"

SWI: X #= Y, X in 1..5 → Y in 1..5. Constraint-then-domain is a completely
normal posting order.

## Fix direction

Route the narrow through `_narrow_if_changed` + `propagate(queue, trail)`
(the C `_narrow` is already exported and used by fd_*). Keep the
real-interval intersection logic that _post_domain adds. Watch the
list-of-vars form: collect one queue across all targets, then run one
fixpoint.

## Acceptance

- xfail passes (label([Y]) yields 1..5);
  `test_in_domain_before_constraint_propagates` stays green; queens/sendmore
  counts unchanged.
