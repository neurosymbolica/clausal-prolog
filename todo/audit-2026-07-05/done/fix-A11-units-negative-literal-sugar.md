# fix(A11-F047): -3(Second) silently fails in `is` goals and argument position

Works after `:=` only. Root cause (A10 seam): term_rewriting.py:1089-1095
folds USub only over bare Constants; `-3(Second)` parses as
`UnaryOp(USub, Call(3, Second))` → becomes `Negate(++thunk)`, a term
unification never evaluates. docs/units.md:42 presents `-3(s)` as a
first-class literal; tests/test_units.py::test_numeric_sugar_negation covers
only the := position.

**Fix**: in visit_UnaryOp, fold USub into the unit-sugar Call with a
numeric-constant callee (`-n(Unit)` → `(-n)(Unit)`) before the sugar
transform. Coordinate with A10 (their file — the units module is the victim).

**Tests**: test_F047_negative_unit_literal_in_is (xfail),
test_F047_guard_negative_unit_literal_in_assign (guard).
