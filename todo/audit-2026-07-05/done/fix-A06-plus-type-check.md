# fix(A06-F015): arith_plus accepts strings (concat) and raises in inverse mode

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F015
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestTypeHoles::test_plus_strings_rejected, ::test_plus_string_inverse_no_crash (xfail — flip to pass)

## Bug

`py_arith_plus` (_arithmetic_core.c:207-255) checks Quantity but never
numeric-ness; `PyNumber_Add("a", "b")` concatenates:

    plus("a", "b", Z)      # Z = "ab" at the Clausal level (probe-confirmed)
    arith_plus("a", Y, "ab")  # TypeError from PyNumber_Subtract escapes

`py_arith_max`/`py_arith_min` (:285-333) similarly compare any orderable
type. The Python twins (`_plus__3_py`, `_max__3_py` in
builtins/arithmetic.py) have the same holes, so fix both layers.

## Fix direction

Add `is_numeric()` guards (already defined in the file, used by abs/sign) on
every known operand in plus/max/min before computing; return Py_None (fail)
on non-numeric. Mirror in the Python fallbacks. Decide whether float is
allowed (abs_/sign accept float; SWI plus/3 is integer-only — follow
docs/arithmetic.md's documented signature).

## Acceptance

- Both xfails pass (clean failure, no TypeError); numeric-mode guards in
  TestArithmeticCore stay green.
