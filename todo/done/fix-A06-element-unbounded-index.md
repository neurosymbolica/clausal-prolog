# fix(A06-F005): element/3 with unconstrained index raises ValueError

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F005
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestElement::test_element_unconstrained_index (xfail — flip to pass)

## Bug

`fd_element` (clpfd.py:2152) calls bare `_ensure_fd(index, trail)`, which
creates the DEFAULT (-inf, inf) domain. That defeats ElementConstraint's own
lazy [1, n] initialisation (clpfd.py:1048-1053, which only fires when the
index has NO fd attr), so propagate() calls `domain_values(idx_domain)` on
an unbounded domain → ValueError escapes to the caller:

    element(I, [10, 20, 30, 20], V)   # I fresh → ValueError (crash, not fail)

## Fix direction

In `fd_element`, post the finite domain instead of the bare ensure:
`_post_domain(index, domain_from_range(1, n), trail)` (or `_narrow` with a
queue so existing constraints re-fire). Also defensive: in
ElementConstraint.propagate, intersect the index domain with [1, n] before
enumerating so a hand-posted wide domain can't re-trigger the crash.

## Acceptance

- xfail passes (enumerates (1,10),(2,20),(3,30),(4,20)); the four bounded
  guards stay green.
