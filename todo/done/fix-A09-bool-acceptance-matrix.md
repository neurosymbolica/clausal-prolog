# fix(A09-F015): bool-as-int acceptance inconsistent; between/3 C vs Python diverge

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F015
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F015_* (xfail — flip to pass), ::test_F015_regression_succ_rejects_bool
**Blocked on:** A01-D001 (bool/int conflation policy) — same sequencing as A06-D005/A07-D002.

## Bug

Reject bool: succ, sign, popcount, msb, lsb, number/1, integer/1, and the C
between. Accept bool-as-int: the PYTHON between fallback (divergence:
`between(False,True,X)` = [] with C, [0,1] without), plus/3, length/2
(`length(L,True)` builds [_]), list_item/3, take/drop/split_at, arg/3,
functor/3 arity, sub_atom/5, numlist, char_code (`char_code(C,True)`→'\x1').

## Fix direction

Whatever A01-D001 decides, the C and Python paths of ONE builtin must agree —
fix the Python `_between__3_py` bool leak immediately (add
`isinstance(bool)` rejection, matching its own C path and succ). The rest
follow the A01-D001 policy in one sweep (a shared `_as_index(val)` helper).

## Acceptance

- between C/Py divergence xfail passes now; remaining xfails flip after the
  A01-D001 sweep.
