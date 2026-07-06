# fix(A06-F017): cross_cutting_issues.md issue 1 stale for _arithmetic_core.c

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F017
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestArithmeticCore::test_trail_type_checked (green guard)

## Drift

`todo/cross_cutting_issues.md` issue 1 ("Trail cast without type check")
lists `_arithmetic_core.c` and `_clpfd_propagate.c` as affected. As of this
audit:

- `_arithmetic_core.c`: every one of the 14 exported functions calls
  `Trail_Check(trail_obj)` before `Trail_CAST` (guard test green).
- `_clpfd_propagate.c`: never casts a trail at all — the trail is passed
  through to the Python variables API (`unify`/`put_attr`), which validates.

## Fix

Update issue 1's affected-files list (remove or annotate these two) so
future audits don't re-chase it. Verify the remaining listed files
(`_constraints_dif.c`, `_tabling_core.c`, `_list_unify.c`, `_lists_core.c`)
before editing — they belong to other subsystems (A05/A04/A01/A09).
