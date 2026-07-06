# fix(A06-F003): C sum/scalar propagate rounds in double — over-prunes near 2^53

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F003
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestDoublePrecisionRounding::test_sum_near_2_53 (xfail — flip to pass)

## Bug

`sum_propagate` / `scalar_propagate` (_clpfd_propagate.c:1571-1894)
accumulate bounds in `double`. The bignum-fallback guard
(DOUBLE_PRECISE_INT_LIMIT, :1601-1606) only checks the AGGREGATE sums; a
computation whose intermediate `total - other` needs >53 bits slips through
and rounds (ties-to-even), producing a wrong bound by ±1 → over-pruning:

    Y in 2^53..2^53+2,  -(2^53) + Y == 1     # FAILS; valid Y = 2^53+1
    (min_sum=0, max_sum=2 pass the guard; new_hi = 1+2^53 rounds to 2^53)

Unsound reject, values well inside int64.

## Fix direction

Do the bounds arithmetic in int64 with __builtin_add/sub/mul_overflow
(falling back to the Python helper on overflow), OR tighten the fallback
trigger to fire when ANY per-var contribution magnitude exceeds 2^53 (cheap:
already have per-var lo/hi as int64). The int64 route also fixes the
division: use C integer ceil/floor division instead of ceil()/floor() on
doubles in scalar_propagate (:1857-1864).

## Acceptance

- xfail passes; `test_scalar_small_values_exact` and both differential
  tests stay green; no perf regression on sendmore (ScalarProduct hot path).
