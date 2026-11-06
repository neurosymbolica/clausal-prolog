# CLP(Q) entry points silently accept floats and CLP(R) variables; the docs promise a TypeError (A08-F007, A08-D003)

**Status: open, gated on design decision A08-D003 (unruled).** Triaged
2026-10-20, moved from the 2026-07-05 audit folder (was
`fix-A08-clpq-float-mixing-enforcement.md`). Both pinning tests still XFAIL
under the port of clp(q,r) 1.3.3, the only CLP(Q) solver since the old one
(with its `_linearize`) was retired on 2026-11-05:
tests/audit_2026_07_05/test_08_clpqr_z3.py::TestClpqSemanticsVsReference::test_q_eq_float_raises_typeerror
and ::test_in_q_after_in_real_raises. The port reads a float as 1.3.3
does, through `float_rat` (`clausal/logic/clpq/arithmetic.py`,
`arithmetic_normalize`; DEVIATIONS.md D3), so `q_eq(X, 0.1)` binds X to
1/10, and `in_q/3` does not look at `REAL_KEY`. The fix sketch below names
the old solver's functions; its two points apply to the port's float read
and to `in_q/3`.

The original audit text follows.

> **DEFERRED (2026-07-07):** intentionally not implemented — gated on the parked
> design decision A08-D003 (float literals in CLP(Q): raise TypeError vs silently
> convert to binary-exact Fraction), still open in DESIGN-DECISIONS.md. The
> recommendation (docs-conformant TypeError) is clear but the direction is a
> user policy call. Flip once D003 is answered.

**Finding:** A08-F007 (correctness/doc-drift, medium); design question A08-D003 (parked)
**Tests:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestClpqSemanticsVsReference::test_q_eq_float_raises_typeerror`,
`::test_in_q_after_in_real_raises`

## Bug
docs/clpq.md: "Mixing Fraction (CLP(Q)) and float (CLP(R)) operands in the
same constraint raises a TypeError" and the dispatch table says `in_real` then
`in_q` raises. Actually:
- `_linearize` (`clpq.py:916-917`) converts `float` to its binary-exact
  Fraction: `q_eq(X, 0.1)` binds X to 3602879701896397/36028797018963968.
- `_post_q_domain` never checks `REAL_KEY`, so `in_real(X, 0, 10); in_q(X, 0, 10)`
  succeeds silently.
The mixing guard lives only in clpfd's dispatch (`_check_no_mixed_rational_real`),
which direct calls (builtins `in_q/3`, `rational/1`, `clpq.*` module API) bypass.

## Fix sketch (pending A08-D003 decision; recommended = docs behaviour)
- In `_linearize`, replace the float branch with `raise TypeError(...)` (same
  message as `_q_hook`).
- In `_post_q_domain`, `get_attr(target, REAL_KEY)` -> TypeError.

## Acceptance
Both xfail tests flip; existing clpq tests (tests/test_clpq.py) stay green.
