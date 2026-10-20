# fix(A06-F014): sum_/scalar_product silently accept non-integer elements

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F014
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestTypeHoles::test_sum_over_strings_rejected (xfail — flip to pass)

## Bug

`fd_sum`/`fd_scalar_product` (clpfd.py:2040-2043, :2101-2104) never check
element types; a string element reaches `_expr_domain`'s fallback
(clpfd.py:1208-1215) which returns the FULL domain for any unknown object —
so `sum_(["a","b"], "#=", 5)` posts happily and yields, treating "a" as an
unconstrained integer.

## Fix direction

At posting time, require every deref'd element to satisfy
`_is_fd_candidate` (clpfd.py:1455 — currently dead code) or be an
arithmetic-expression node; otherwise fail the builtin (yield nothing) or
raise TypeError, consistent with `in_domain`'s bounds check. Same check in
SumConstraint/ScalarProduct propagate for elements that get BOUND to
non-integers later (today the hook rejects most, but expression leaves
bypass it).

## Acceptance

- xfail passes; `all_different` type-edge guard unchanged; numeric guards
  green.
