# fix(A06): all_different ground-value propagation shares the INT64 sentinel bug

**Findings:** A06-F007 sibling (medium — C-only unsound; latent)
**Tests:** none yet — add to `tests/audit_2026_07_05/test_06_clpfd.py` next to `TestInt64SentinelValueArgs`

## Problem
A06-F007 (commit 7fad78d6, extended in `eba8b8d5`) reserved the int64
sentinels `INT64_MIN`/`INT64_MAX` for ±infinity and routed every finite user
integer landing exactly on a sentinel through the exact-int / bignum path — but
only at the domain-construction and remove/ne/lt/le/expr-singleton entry points.

`alldiff_propagate` (`clausal/logic/_clpfd_propagate.c:1543`) was not audited: it
does an ungated `PyLong_AsLongLong` on a ground member and then
`domain_remove_c` on its peers. Consequences (same class as F007, C path only —
the pure-Python propagator is correct):

- a ground `all_different` member equal to exactly `2**63-1` or `-(2**63)`
  truncates/mis-removes the peer domains (the sentinel is read back as ±inf);
- a true bignum ground member (e.g. `2**64`) raises `OverflowError` out of
  `PyLong_AsLongLong` instead of being handled by the exact path.

## Direction
Mirror the established F007 pattern at this site: before the fast
`PyLong_AsLongLong` + `domain_remove_c`, test the ground value with
`is_bignum_int()` (now flags finite PyLongs at the sentinels too) and route a
sentinel-valued or bignum ground member through the exact-int Python
`domain_remove` fallback, exactly as the ne propagator's int-operand path now
does. Grep `_clpfd_propagate.c` for the other ground-value `PyLong_AsLongLong`
call sites (scalar/sum coefficient handling was already covered — confirm) and
apply the same guard to any that compare a user integer against a domain bound.

## Verify
RED before / GREEN after against the rebuilt `.so`, plus a C-vs-Python
agreement assertion at the ±sentinel boundary (import-block `_USE_C_PROPAGATE`
for the pure-Python leg). Regression-guard `2**63-2` (fast path) and `2**64`
(bignum round-trip). Found by the A06-F007 fix-review session (2026-07-10).
