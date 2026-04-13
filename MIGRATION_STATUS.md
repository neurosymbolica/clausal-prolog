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

## Phase 3 — Control flow & constraints

| file | status | action |
|---|---|---|
| `test_regex.py` | ✅ audit-complete | 53 migratable tests — but Python scaffolding is `_load_module`-based integration-infra. Behavior covered by `regex_basic.clausal` (34 tests) + `regex_autobind.clausal` (59 tests). No migration |
| `test_dcg.py` | ⏸ deferred | 57 tests using `_load_module` + `module_dict` introspection. Migration-worthy but requires designing many grammar fixtures. Existing `dcg_grammar.clausal` (5 tests) covers the integration path minimally |
| `test_meta.py` | ✅ slimmed | Removed `TestClausalImport` (5 tests, dup of fixture). Extended `meta_test.clausal` by 14 Test clauses covering findall/bagof/setof/forall direct behavior. Orphan imports cleaned |
| `test_coroutining.py` | ✅ extended | Added 12 Test clauses to `coroutining.clausal` (call_nth first/last/fail-goal/zero/negative, count_all bound/filter/no-side-effects, scc throw, call_cleanup fails/throws). `.py` kept for `pytest.raises(LogicException)` error-type assertions |
| `test_edcg.py` | ⏸ deferred | Same `_load_module`-per-test pattern as DCG |
| `test_clpfd.py` | ✅ audit-complete | Tests FDVar/Domain Python objects. Behavior covered by `clpfd_queens.clausal` + `clpfd_sendmore.clausal`. Stays |
| `test_clpb.py` | ✅ audit-complete | BDD internals — infra. Stays |
| `test_tabling.py` | ✅ audit-complete | TableEntry/SuspendedConsumer internals — infra. Behavior covered by `tabled_*.clausal` fixtures. Stays |
| `test_wfs.py` | ✅ audit-complete | WFS engine internals — infra. Stays |
| `test_dif.py` | ✅ audit-complete | `dif()` Python fn + attributed-var internals — infra. Behavior covered by `builtins_dif.clausal`. Stays |
| `test_reified_ite.py` | ✅ audit-complete | Reified if-then-else AST node tests — infra. Stays |
| `test_lambdas.py` | ✅ audit-complete | Lambda-compilation internals — infra. Stays |
| `test_global_constraints.py` | ✅ audit-complete | Global constraint internals — infra. Stays |
| `test_attributes.py` | ✅ audit-complete | Attributed var internals — infra. Stays |

**Phase 3 net adds**: 26 new Test clauses (`meta_test.clausal` +14, `coroutining.clausal` +12). No Python test files deleted, but `test_meta.py` slimmed. 14 files audited, 2 deferred to TODOs.

## Phase 4 — Modules / stdlib

| file | status | action |
|---|---|---|
| `test_clausal_modules.py` | ✅ slimmed | 102 → 33 tests. 69 behavior tests migrated to Test clauses in `tests/clausal_modules/{meta,higher_order,lambdas}.clausal` (28+28+13 = 69). What remains in .py: TermInspection tests (need Compound/Var construction) + Exceptions tests (already covered by `exceptions.clausal`'s 12 Test clauses but kept for explicit assertions on result values). Orphan imports cleaned |
| `test_json_module.py` | ✅ keep | Imports `_parse_2`/`_generate_2` etc. directly — adapter-implementation infra. Behavior in `tests/fixtures/docs/sig_tests` |
| `test_csv_module.py` | ✅ keep | Same pattern |
| `test_http_module.py` | ✅ keep | Same |
| `test_files_module.py` | ✅ keep | Same |
| `test_os_module.py` | ✅ keep | Same |
| `test_process_module.py` | ✅ keep | Same |
| `test_random_module.py` | ✅ keep | Same |
| `test_crypto_modules.py` | ✅ keep | Same |
| `test_logging_module.py` | ✅ keep | Tests Python `logging` integration — infra |
| `test_date_time.py` | ✅ keep | Same adapter pattern |
| `test_uuid_module.py` | ✅ keep | Same |
| `test_chars.py` | ✅ keep | Tests via `get_builtin_dispatch` + `StepGenerator` — infra |
| `test_sqlite.py` | ✅ keep | Same |
| `test_tcp_module.py` | ✅ keep | Same |
| `test_yaml_module.py` | ⏸ deferred | `_load_module`-per-test pattern (regex/dcg/edcg cohort) |
| `test_module_imports.py` | ✅ keep | V3-1 module system mechanics (directive parsing, dispatch, errors). Behavior of imported predicates covered by `imports_*.clausal` + `importable_utils.clausal` |

**Phase 4 net adds**: 69 Test clauses (`meta.clausal` +28, `higher_order.clausal` +28, `lambdas.clausal` +13). 1 file slimmed (test_clausal_modules.py 102 → 33 tests). 14 stdlib wrappers audit-confirmed-as-infra. 1 deferred (yaml).

## Phase 5 — SciPy / Torch / numeric

All files in this phase fall into one of two patterns, both of which are
correctly classified as Python-level infrastructure:

1. **Direct adapter import** — `from clausal.modules.py.scipy_X import
   Predicate, ...` + `_drive(pred, args)` helper that calls `_get_dispatch`
   directly to verify the adapter's Var-binding / exception / arity
   handling. Test the adapter implementation, not language behavior.

2. **Fixture-runner** — parametrized `test_fixture(name)` methods that
   `_load_module` a .clausal fixture and run its Test clauses. The runner
   itself is integration-infra; the *behavior* is in the fixture.

Behavior coverage at the .clausal surface is comprehensive:

| .clausal fixture group | Test clause count |
|---|---:|
| scipy_*.clausal (cluster, constants, differentiate, fft, integrate, interpolate, linalg, ndimage, optimize, sparse, spatial, special, stats — incl. `_bidir` variants) | ~440 |
| torch_*.clausal (comparison, creation2, data, distributions, fft, functional, io, linalg, math, nn, registry, schedulers, shape2, tensor) | ~230 |
| sklearn_*.clausal (basic, data, metrics, pipeline, search) | ~50 |
| spacy / sympy / units fixtures | ~80 |

| file | status | reason |
|---|---|---|
| `test_scipy_cluster.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_constants.py` | ✅ keep | Adapter import |
| `test_scipy_differentiate.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_fft.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_integrate.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_interpolate.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_linalg.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_ndimage.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_optimize.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_signal.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_sparse.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_spatial.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_special.py` | ✅ keep | Adapter import + `_drive` |
| `test_scipy_stats.py` | ✅ keep | Adapter import + `_drive` |
| `test_torch.py` | ✅ keep | Parametrized fixture runner + lazy-import / opts unit tests |
| `test_torch_coverage.py` | ✅ keep | Coverage matrix runner |
| `test_units.py` | ✅ keep | Quantity protocol (`__unify__` / `__walk__` / `__occurs_check__` / UnitsMismatch / attributed-var) — infra |
| `test_spacy_module.py` | ✅ keep | Adapter import |
| `test_sympy_module.py` | ✅ keep | Adapter import |

**Phase 5 net adds**: zero. All 19 files audit-confirmed-stay-as-infra.
The behavior layer is already comprehensively covered by .clausal
fixtures (~800 Test clauses across scipy/torch/sklearn/spacy/sympy/units).

## Phase 6 — Prolog translation

Per the original plan, this phase was expected to be mostly infra. That
prediction held: all 16 files are Prolog→Clausal compile-pipeline
infrastructure or external-backend integration. No migrations.

| file | status | reason |
|---|---|---|
| `test_prolog_ast.py` | ✅ keep | PAtom/PVar/PCompound etc. AST class tests |
| `test_prolog_dialect.py` | ✅ keep | Dialect config (ISO/SWI/Scryer) |
| `test_prolog_emit.py` | ✅ keep | Term-to-Prolog-text emission |
| `test_prolog_golden.py` | ✅ keep | Golden-file round-trip checks |
| `test_prolog_import.py` | ✅ keep | PrologLoader/PrologFinder + `__pycache__` integration; `_load_module`-per-test pattern |
| `test_prolog_operators.py` | ✅ keep | Operator-table tests |
| `test_prolog_parse.py` | ✅ keep | Tokenizer + Pratt parser |
| `test_prolog_roundtrip.py` | ✅ keep | parse→emit→parse identity |
| `test_prolog_to_clausal.py` | ✅ keep | Translation pipeline |
| `test_gprolog_embedding.py` | ✅ keep | External GNU-Prolog backend integration |
| `test_gprolog_raw.py` | ✅ keep | Same |
| `test_scryer_backend.py` | ✅ keep | External Scryer backend integration (20 "behavior" tests are backend probes) |
| `test_scryer_embedding.py` | ✅ keep | Same |
| `test_scryer_raw.py` | ✅ keep | Same |
| `test_trealla_backend.py` | ✅ keep | External Trealla backend integration (19 backend probes) |
| `test_trealla_embedding.py` | ✅ keep | Same |

**Phase 6 net adds**: zero. All 16 files audit-confirmed-stay-as-infra.

## Phase 7+ — To do

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
