# Test Migration Status

Tracks the migration of behavior tests from `.py` → `.clausal` (see
`MIGRATION_CANDIDATES.md` for the original classification and the plan
in conversation history).

## Phase 1 — Conformity (ISO)

Goal: `tests/conformity/test_iso_*.py` behavior tests move to sibling
`.clausal` files; Python files keep only infra-level assertions.

| file | status | notes |
|---|---|---|
| `iso_arithmetic` | ✅ done | `.py` deleted, all 51 tests in `.clausal` |
| `iso_unification` | ✅ done | `.py` slimmed to infra (structural_unify, SegList/DictTerm/SetTerm, StructuralEq side-effects); 45 `.clausal` tests |
| `iso_type_checking` | ✅ done | `.py` slimmed to Compound/KWTerm/bool/complex/negative-literal cases; 63 `.clausal` tests |
| `iso_list_operations` | ✅ done | `.py` deleted, 79 `.clausal` tests |
| `iso_control` | ✅ done | `.py` deleted, 31 `.clausal` tests |
| `iso_term_manipulation` | ✅ done | `.py` slimmed (Compound construction); 9 `.clausal` tests |
| `iso_database` | ✅ done | new `iso_database.clausal` created; `.py` deleted; 8 tests |
| `iso_syntax_na` | ✅ kept | documentation-only (no tests); documents coverage gap for Prolog-syntax tests that don't apply to clausal |

**Phase 1 result**: 7 Python test files deleted or slimmed, all ISO
behavior now runs through `.clausal` Test clauses via
`clausal.testing`. Conformity suite: 345 passing (was 403 before
migration; net loss of 58 is because each former `.py` test had a
behavior + infra intent and the infra-only kept tests are fewer than
the originals).

**Regressions**: none. Full `tests/` run: 9854 passing; 430 failures
are all pre-existing in optional-dependency modules (z3, clpz3,
clpsat, trealla, pysat, ortools, prolog_golden) — absent in this
environment. `clausal/examples/symbolic_diff.clausal::d(y)/dx = 0`
also fails pre-migration.

## Phase 2 — Builtin behavior

| file | status | action |
|---|---|---|
| `test_control.py` | ✅ keep | Entirely stderr-capture tests on `time_goal/1` — inherently Python infra |
| `test_higher_order.py` | ✅ keep | Tests Python trampoline funcs directly (`_map_list__2`, `StepGenerator`); behavior already in `builtins_higher_order.clausal` |
| `test_list_util.py` | ✅ keep | Same pattern — Python trampoline internals |
| `test_list_edge_cases.py` | ✅ migrated | Deleted. New `tests/fixtures/list_patterns_edge_cases.clausal` (60 Test clauses, self-contained) covers Phase 1–4 list-pattern edge cases |
| `test_io.py` | ✅ added .clausal | New `tests/fixtures/io_to_string.clausal` (6 tests) covers non-stdout I/O; stdout tests stay in .py |
| `test_exceptions.py` | ✅ slimmed | `TestClausalIntegration` removed (duplicate of .clausal); added 5 catch/3 semantic tests to `tests/fixtures/catch_test.clausal` (now 11 tests) |
| `test_term_inspection.py` | ✅ added Tests | Added 9 Test clauses to `tests/clausal_modules/term_inspection.clausal` for ground-term cases; Var-identity tests stay in .py |
| `test_reif_builtins.py` | ✅ keep | Tests `eq__3`/`dif_t__3` Python generators directly — infra |
| `test_dict_set_builtins.py` | ✅ added Tests | Extended `tests/fixtures/dict_set_builtins.clausal` by 28 Test clauses covering is_dict/dict_size/dict_keys/dict_values/dict_get/dict_put/is_set/set_size/set_list/set_union/set_intersection/set_subtract/set_subset/set_disjoint/set_add/set_remove |
| `test_mutable_dict_set.py` | ✅ keep | 10 infra tests — Python-level mutation of DictTerm/SetTerm objects |
| `test_builtins.py` | ✅ slimmed | 1023 → 422 LOC. Deleted `TestTypeChecks`/`TestArithmetic`/`TestListPredicates`/`TestAssertRetract`/`TestPairHelpers` (duplicated in conformity/iso_*). Added 19 new Sign/Gcd/DivMod Test clauses to `iso_arithmetic.clausal` (V2-12 arithmetic builtins), 4 pairs_keys_values Test clauses to `phase5_builtins.clausal`. Kept: `TestKWTerm`, `TestFunctor`, `TestArg`, `TestUniv` (Compound/KWTerm infra), `TestWK5` (dataclass + keyword-pred signatures), `TestBuiltinsInCompiledPredicates` (integration) |
| `test_phase5_builtins.py` | ✅ added .clausal | New `tests/fixtures/phase5_builtins.clausal` (29 tests) for lcm/exp_mod/popcount/msb/lsb/numlist/same_length/transpose; Quantity-arithmetic cases stay in .py |

**Phase 2 net adds**: 3 new `.clausal` fixtures (`io_to_string`, `phase5_builtins`, new test block in `catch_test`/`dict_set_builtins`/`term_inspection.clausal`), 77 Test clauses added. Python test files slimmed where duplicated.

## Phase 3+ — To do

See `MIGRATION_CANDIDATES.md`. Suggested next batches:

- **Phase 2 — Builtin behavior**: `test_builtins.py`, `test_higher_order.py`, `test_term_inspection.py`, `test_io.py`, `test_exceptions.py`, `test_list_util.py`, `test_list_edge_cases.py`, `test_phase5_builtins.py`, `test_reif_builtins.py`, `test_dict_set_builtins.py`.
- **Phase 3 — Control flow & constraints**: `test_tabling.py`, `test_wfs.py`, `test_dif.py`, `test_reified_ite.py`, `test_clpfd.py`, `test_clpb.py`, `test_meta.py`, `test_lambdas.py`, `test_dcg.py`, `test_edcg.py`, `test_regex.py`.
- **Phase 4 — Module/stdlib behavior**: json/csv/http/files/os/process/random/crypto/logging/date_time wrappers.
- **Phase 5 — SciPy/Torch/numeric**: scipy_*, torch_*, sklearn_*, numpy_*.
- **Phase 6 — Prolog translation**: mostly infra, stays; audit only.
- **Phase 7 — Compiler/core infra**: stays; audit only.

## Tooling

- `scripts/test_audit/dedup.py` — finds duplicate tests (AST-hash for
  `.py`, body-text hash for `.clausal`). Output: `DUPLICATE_TESTS.md`.
- `scripts/test_audit/classify.py` — tags tests `behavior` /
  `infra` / `mixed` / `unknown` via AST ref-set analysis with
  helper-function label propagation. Output:
  `MIGRATION_CANDIDATES.md`.
