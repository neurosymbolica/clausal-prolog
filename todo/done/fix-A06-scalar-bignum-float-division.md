# fix(A06-F004): "bignum-safe" scalar helpers use float division — over-prune

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F004
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestDoublePrecisionRounding::test_scalar_bignum_exact_division (xfail — flip to pass)

## Bug

`_scalar_propagate_bignum` (clpfd.py:592-596) and
`ScalarProductConstraint.propagate` (clpfd.py:696-700, second copy
:968-972) compute

    new_v_lo = math.ceil((total_lo - other_max) / c)

with Python TRUE division — the int operands are converted to float, losing
precision past 2^53. These are precisely the code paths the C extension
tail-calls FOR big values ("Slice 4 of clpz_bignum.md"), so the designated
bignum-safe path is itself unsound:

    X in 0..2^62,  3*X == 3*(2^60+1)   # FAILS; valid X = 2^60+1

Also corrects cross_cutting_issues.md issue 8's claim that "Python fallback
handles correctly".

## Fix direction

Integer ceil/floor division on int operands:

    ceil(a/c)  ->  -((-a) // c)      floor(a/c) -> a // c     (c > 0; mirror for c < 0)

keeping the existing ±inf guards (only divide when both operands finite).
Apply to both duplicated ScalarProductConstraint class bodies (note:
clpfd.py defines the class TWICE, :643 and :915 — the second shadows the
first; consider deleting the dead first copy while here).

## Acceptance

- xfail passes; Fibonacci-style bignum workloads (clpz_bignum.md repro) give
  exact bounds; differential tests stay green.
