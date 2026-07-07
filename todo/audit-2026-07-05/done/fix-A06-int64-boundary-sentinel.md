# fix(A06-F007): exact INT64_MIN/MAX domain bounds silently become ±inf

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F007
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestInt64BoundarySentinel (2 xfail — flip to pass)

## Bug

`make_interval` (_clpfd_domain_ops.h:116-135) maps int64 sentinel values
back to Python float inf, so a USER bound of exactly 2^63-1 (or -2^63) is
indistinguishable from "unbounded":

    in_domain(X, 0, 2**63 - 1)   # domain becomes ((0, inf),)
    fd_eq(X, 2**100)             # SUCCEEDS — outside the declared domain
    label([X])                   # raises "unbounded" for a finite request

Unsound accept (wrong-not-error). Related to cross_cutting_issues.md issue 8
(int64 ceilings) but distinct: these bounds are in-range, and the bignum
fallback machinery already exists.

## Fix direction

Reserve the sentinels: in `domain_from_range` (C, _clpfd_core.c) treat
lo == INT64_MIN or hi == INT64_MAX from a PYTHON INT input as bignum-ish and
route through the Python fallback (which keeps exact int bounds), exactly as
already done for |v| > int64. I.e. shrink the C fast range to
[INT64_MIN+1, INT64_MAX-1]; the sentinel then genuinely means inf.
Audit the other domain ops for the same boundary (remove_above/below limit
of exactly INT64_MAX/MIN, expr_domain singleton at the boundary).

## Acceptance

- Both xfails pass; `test_near_boundary_bounds_exact` (2^63-2 and true
  bignum 2^64 round-trips) stays green.
