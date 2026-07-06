# fix(A06-F013): global_cardinality never propagates variable counts

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F013
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestGlobalCardinality::test_var_count_bound_when_ground (xfail — flip to pass)
**Related design Q:** A06-D003 (off-key values) — independent; this fix is wanted either way.

## Bug

`GlobalCardinalityConstraint.propagate` (clpfd.py:2350-2353) skips any pair
whose count is a Var ("can't propagate variable counts yet") — even when all
vars are ground:

    vars = [1, 1, 1], pairs = [(1, CNT)]   # CNT stays unbound; SWI: CNT = 3

## Fix direction

For a Var count: compute `definite` (ground == value) and `possible`
(domains containing value) exactly as the int-count branch does, then narrow
the count var's domain to [definite, definite + possible] via
`_narrow_if_changed` (ensure_fd on the count var at post time — today the
constructor only tracks it in vars). When definite == definite+possible the
narrow makes it a singleton and binds. This subsumes the ground case.

## Acceptance

- xfail passes; `test_ground_counts` and the off-key characterization guard
  stay green (until D003 decides otherwise).
