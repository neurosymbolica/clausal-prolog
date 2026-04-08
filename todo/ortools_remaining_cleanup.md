# OR-Tools remaining cleanup

## 1. Remove remaining single-element tuple wrapping in .clausal tests — DONE

## 2. Add first-class constraint tests (runtime tuple passing) — DONE

Tests added in `tests/fixtures/first_class_constraints.clausal` covering Z3
(integer + boolean), PySAT, CLP(Q), CLP(R), GLOP, and CP-SAT — including
arithmetic constraints. Uses `is/2` (unification) to construct constraint
tuples as data, which preserves the AST. All 14 tests pass.

## 3. Commit the deref fix, single-constraint refactor, and first-class tests

The following files have been modified but not yet committed:

- `clausal/logic/clpz3.py` — deref in z3_constraint_block
- `clausal/logic/clpsat.py` — deref in sat_constraint_block
- `clausal/logic/clportools.py` — deref in or_constraint_block
- `clausal/logic/clportools_lp.py` — deref in lp_constraint_block
- `clausal/logic/clpq.py` — deref in clpq_constraint_block
- `clausal/logic/clpr.py` — deref in clpr_constraint_block
- `tests/fixtures/z3_diagnostics.clausal` — satisfiability("sat") simplification
- `tests/fixtures/z3_bitvector.clausal` — single-constraint tuple removal
- `tests/fixtures/z3_boolean.clausal` — single-constraint tuple removal
- `tests/fixtures/ortools_cpsat.clausal` — single-constraint tuple removal
- `tests/fixtures/ortools_lp.clausal` — single-constraint tuple removal
- `tests/fixtures/ortools_mip.clausal` — single-constraint tuple removal
- `tests/fixtures/pysat_boolean.clausal` — single-constraint tuple removal
- `tests/fixtures/clpq_module.clausal` — single-constraint tuple removal
- `tests/fixtures/clpr_module.clausal` — single-constraint tuple removal
- `tests/fixtures/first_class_constraints.clausal` — NEW: first-class constraint tests
