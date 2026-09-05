# Task 2 inversion ledger

Format: `<full test id> | <what changed> | <ruling cited>`

STATUS: PARTIAL. Task 2 is reported BLOCKED (see `task-2-report.md`) on an
unresolved design question — declaration-only predicate exports under R6 — so
this ledger covers only the inversions that were actually made. The full-suite
name-diff is NOT empty (89 new names, listed in `task2-new-failures.txt`); the
remaining inversions were deliberately NOT made because the blocking ruling can
change the binding rule that decides them.

## tests/test_tagged_terms.py

tests/test_tagged_terms.py::TestDefaultPathGolden::test_unflagged_codegen_unchanged | RENAMED to `test_codegen_unchanged`; class + method docstrings drop the "flag off => byte-identical" framing (there is one path now); goldens regenerated | R9
tests/test_tagged_terms.py::TestDirective::test_bare_directive_sets_module_flag | INVERTED to `TestRetiredDirective::test_bare_form_is_an_unknown_directive` — the directive is deleted, so the bare marker form raises `SyntaxError: Unknown directive: -tagged_terms` | R9
tests/test_tagged_terms.py::TestDirective::test_parenthesised_directive_sets_module_flag | INVERTED to `TestRetiredDirective::test_parenthesised_form_is_an_unknown_directive` | R9
tests/test_tagged_terms.py::TestDirective::test_directive_rejects_arguments | INVERTED to `TestRetiredDirective::test_argument_form_is_an_unknown_directive_too` — no longer a "takes no arguments" complaint; the name itself is unknown | R9
tests/test_tagged_terms.py::TestDirective::test_unflagged_module_has_no_flag | DELETED — `TAGGED_TERMS_FLAG` no longer exists, so there is no key to assert the absence of | R9
tests/test_tagged_terms.py::TestDirective::test_unknown_directive_message_lists_tagged_terms | INVERTED to `TestRetiredDirective::test_unknown_directive_message_no_longer_lists_tagged_terms` — the known-directive list must not advertise a deleted directive | R9
tests/test_tagged_terms.py::TestCellEmission::test_flagged_module_constructs_cells | RENAMED `test_a_module_constructs_cells` (no flag to name) | R9
tests/test_tagged_terms.py::TestCellEmission::test_unflagged_sibling_constructs_class_terms | INVERTED to `test_the_sibling_module_constructs_cells_too` — asserts cells, not class calls | R5 (flip)
tests/test_tagged_terms.py::TestCellEmission::test_atoms_lower_to_str_constants_even_in_a_flagged_module | RENAMED `test_atoms_lower_to_str_constants_not_to_cells`; docstring drops the flag | §1b
tests/test_tagged_terms.py::TestSignatureConstruction (`_MODULE_TEMPLATE`) and every `_load_inline` source in the file | the `-tagged_terms\n` line removed from all inline fixtures | R9
tests/test_tagged_terms.py::TestSignatureConstruction::test_unflagged_twin_builds_class_instances_slot_for_slot | RENAMED `test_the_runtime_constructor_places_slots_the_same_way`; still pins `PredicateMeta.__call__`'s backfill (untouched by the flip) | R6
tests/test_tagged_terms.py::TestHeadSignaturePlacement (helper `_flagged_globals`/`_pattern_for`) | scope manager dropped — `head_match` resolves against the `globals_` it is handed, so no compile scope is needed | R9
tests/test_tagged_terms.py::TestHeadPatterns (helper `_pattern(term, flagged=...)`) | the `flagged` parameter deleted; all call sites updated | R9
tests/test_tagged_terms.py::TestHeadPatterns::test_source_compound_unflagged_stays_a_class_pattern | DELETED — there is no unflagged path to assert | R5 (flip)
tests/test_tagged_terms.py::TestHeadPatterns::test_live_instance_unflagged_stays_a_class_pattern | DELETED — same | R5 (flip)
tests/test_tagged_terms.py::TestHeadPatterns::test_another_modules_functor_keeps_the_class_pattern | INVERTED to `test_another_modules_functor_matches_as_a_cell_too` — the own-module gate is deleted, so a functor owned elsewhere matches as a cell | R5
tests/test_tagged_terms.py::TestCellHeadDispatch::test_functor_and_arity_discrimination | parametrize collapsed from two shape columns (cell for the tagged half, CLASS INSTANCE for the plain half) to one — both halves build cells now | R6
tests/test_tagged_terms.py::TestCellHeadDispatch::test_the_flagged_modules_own_class_constructor_matches_nothing | REWRITTEN as `test_a_declared_data_functors_class_constructor_matches_nothing` | R6
tests/test_tagged_terms.py::TestBucketPatternIntegration::test_a_class_instance_caller_finds_nothing | docstring rewritten (representation limit, not flag boundary); assertions unchanged | R6
tests/test_tagged_terms.py::TestHeadPatternReachability::test_source_written_compounds_never_reach_a_head_pattern | docstring rewritten; assertions unchanged (Task 3 named as the closer) | R9
tests/test_tagged_terms.py::TestHeadPatternReachability::test_index_dispatch_routes_every_cell_to_the_all_clauses_fallback | docstring rewritten (Task 4 named as the inverter); the class-term half re-justified — no compiled clause builds one now, but the constructor is still minted | §4
tests/test_tagged_terms.py::TestGateSymmetry::test_position_field_functor_matches_as_a_class | scope manager dropped from the helper; assertion unchanged | R9
tests/test_tagged_terms.py::TestGateSymmetry::test_the_cell_branch_resolves_names_where_its_fallback_does | REWRITTEN — the old premise (another MODULE's data functor -> class pattern) died with the own-module gate, so the globals_-vs-scope discriminator is re-cast on the data/predicate split; also fixes the stale docstring naming `cell_functor_for_name` (Task 1 deferred minor) | R5
tests/test_tagged_terms.py::TestGateSymmetry::test_an_unflagged_compile_inside_a_flagged_scope_emits_no_cells | DELETED and REPLACED by `test_a_nested_compile_scope_resolves_against_its_own_namespace`, which pins the surviving structural property (top-of-stack wins; a scope with no namespace resolves nothing) | R9
tests/test_tagged_terms.py (module docstring, `_GOLDEN_MODULES` comment, `_PLAIN`/`_TAGGED` header, `TestNormalizer` docstring) | prose updated: no flag, one path, the fixture pair is now the class-era answer anchor | R9

## tests/test_tagged_terms_parity.py

tests/test_tagged_terms_parity.py (module docstring) | rewritten: the two halves are the same program under two module names now; the RECORDED VALUES are the old-golden-vs-new-default anchor | R9
tests/test_tagged_terms_parity.py::TestStructTablingParity::test_nats_ground_query_success_parity | the plain half's caller-supplied chain built as CELLS instead of via `mod.cons(...)` | R6
tests/test_tagged_terms_parity.py::TestStructTablingParity::test_nats_ground_query_failure_parity | same | R6
tests/test_tagged_terms_parity.py::TestHeadListCompoundParity::test_ev_deep_output_mode_answer_parity | the plain half's `[mod.c(mod.d(S))]` built as `[("c", ("d", S))]` | R6
tests/test_tagged_terms_parity.py::TestHeadListCompoundParity::test_must_fail_ev_deep_input_mismatch_fails_both_halves | same | R6

## Fixtures

tests/fixtures/tagged_shapes_tagged.clausal, struct_tabling_tagged.clausal, head_list_compound_tagged.clausal | `-tagged_terms` line removed (the directive no longer parses) | R9

## Goldens

tests/golden/{tagged_shapes,struct_tabling,head_list_compound}.codegen.txt | regenerated: 29 lines, every one a class constructor call replaced by a cell literal in a body position. `deep_index` and `edge_graph` unchanged (no declared data functors). Diff read in full before committing — see the report's 5-line summary | R5/R6

## NOT made (blocked)

The ~89 remaining new failures are listed in `task2-new-failures.txt`. Roughly 80
are the same mechanical shape (a Python caller builds a data term via
`mod.functor(...)`, or asserts `.Field` on an answer, or compares an answer to a
class term) and would be straightforward R6 inversions. They were NOT made
because ~9 of them (`tests/test_imported_functor_clause_clobber.py`,
`tests/test_functor_import_ordering.py`,
`tests/test_import_path_canonicalization.py`,
`tests/fixtures/impord_declare_then_import_fact.clausal`) expose a design
question R6 does not answer — see the report — whose resolution can change the
binding rule and therefore invalidate the other 80 inversions.

---

# Round 2 — after the controller's rulings (R6b, instance-side removal)

The "STATUS: PARTIAL" note above is superseded: the full-suite name diff vs
`baseline-failed-names.txt` is now EMPTY (145 == 145, 0 new, 0 fixed).

## R6b — ISO `name/arity` predicate exports

tests/fixtures/impclob_decl_vocab.clausal | `-module(..., [impclob_verdict(OUTCOME, CITES)])` → `[impclob_verdict/2]`: a declaration-only PREDICATE export, said explicitly | Ruling R6b
tests/fixtures/impord_fact_vocab.clausal | `-module(..., [impord_fverdict(OUTCOME, CITES)])` → `[impord_fverdict/2]`: same idiom, same migration | Ruling R6b
tests/test_import_path_canonicalization.py::test_two_paths_one_module (`real.sole_verdict is via_link.sole_verdict`) | the compilation-identity witness moved from the data functor `sole_verdict` to the PREDICATE `decide_sole` — a data functor's binding is the interned spelling, identical across compilations by construction, so it cannot witness anything apart | R6
tests/test_import_path_canonicalization.py::test_load_module_helper_does_not_claim_the_path | same witness move (`is not` half) | R6

## Instance-side cell emission removed

tests/test_tagged_terms.py::TestHeadPatterns::test_live_instance_becomes_a_sequence_pattern | INVERTED to `test_live_instance_stays_a_class_pattern`; the instance is Python-minted (`_python_minted`, a new module-level helper) since a `.clausal` declaration mints none | controller ruling (instance-side removal)
tests/test_tagged_terms.py::TestHeadPatterns::test_another_modules_functor_matches_as_a_cell_too | re-asked on the NAME side (`_source_compound` resolved against the other module's `globals_`) — the cross-module question moved there when instances stopped answering it | R5 + the same ruling
tests/test_tagged_terms.py::TestGateSymmetry::test_position_field_functor_constructs_as_a_class | INVERTED to `test_position_field_functor_constructs_as_a_cell`: the exclusion dissolves, a cell keeps every declared slot | controller ruling + R6
tests/test_tagged_terms.py::TestGateSymmetry::test_position_field_functor_matches_as_a_class | REPLACED by `test_position_field_functor_has_no_instance_half_any_more`: the declaration mints no reachable class, so there is no instance to match | controller ruling + R6
tests/test_tagged_terms.py::TestGateSymmetry::test_the_cell_branch_resolves_names_where_its_fallback_does | premise re-expressed on BINDINGS (`tagged.point == "point"` / `isinstance(tagged.kind, PredicateMeta)`) — `is_data_functor` is deleted | R6
tests/test_tagged_terms.py::TestNormalizer (4 tests) | the class half of every comparison is Python-minted now — the only class terms left | R6
tests/test_tagged_terms.py::TestHeadPatternReachability::test_index_dispatch_routes_every_cell_to_the_all_clauses_fallback | the class-term half reads a Python-minted instance; wording says why that branch is still live code | R6
tests/test_tagged_terms.py::TestBucketPatternIntegration (`_compile_instance_headed_kind` → `_compile_cell_headed_kind`, 8 tests) | the probe clauses are built from CELLS, since instances now yield class patterns; `test_buckets_match_cells_by_functor_and_arity` becomes `test_the_lift_does_not_yet_reach_a_cell_pattern`, a recorded finding (`_lift_clause_at_pos` does not lift a tuple, so dispatch is correct via the `$headlit` capture but unindexed — Task 3 closes it) | controller ruling + §4
tests/test_tagged_terms.py::TestCellHeadDispatch::test_a_declared_data_functors_class_constructor_matches_nothing | INVERTED to `test_a_declared_data_functor_binds_its_spelling_not_a_constructor`: the trap is CLOSED — `m.point == "point"` and calling it is a loud TypeError, where the bridge era had a callable constructor that silently matched nothing | R6
tests/test_tagged_terms.py::TestSignatureConstruction::test_the_runtime_constructor_places_slots_the_same_way | reads through a `make_predicate` class — `PredicateMeta.__call__` is untouched and is still every Python producer's placer | controller ruling (test_fast_construction direction, applied here too)

## Mechanical R6 inversions (a Python caller built a data term, or read a field off one)

tests/test_head_match_imported_compound.py (15 tests; `Wrap(...)`/`Item(...)`/`Met(...)` → cell literals, `type(x).__name__` → slot 0, `item.STATUS` → `item[2]`) | R6
tests/test_metainterpreters.py (11 tests; `_terms(mod)` returns cell BUILDERS instead of classes, so every call site reads unchanged) | R6
tests/test_structural_head_output_mode.py (6 tests; `_ctor` returns a cell builder) | R6
tests/test_tabling.py::TestStructTabling (4 tests; `node.H`/`node.T` → `node[1]`/`node[2]`, caller chains built as cells) | R6
tests/test_dcg.py::TestAtomHeadDispatch (2 tests; `ve` is a cell builder — `r` stays a predicate class and `foo`/`bar` stay atoms) | R6
tests/test_constants.py (2 tests; `result.X` → `result == ("Point", …)`) | R6
tests/test_standard_order.py::test_msort_of_domain_local_compounds_end_to_end | expected sort ORDER unchanged, the terms are cells | R6
tests/test_comma_separated_rules.py::test_compound_list_heads_with_commas_between_rules | caller list built from cells | R6
tests/test_exceptions.py::TestRaisingGuardThroughFindAll::test_guard_raise_propagates_out_of_findall | a `-private` functor throws as a CELL — slot 0 the functor, declared fields after it | R6
tests/audit_2026_07_05/test_02_compiler_heads.py::TestCompoundAtomIndexGuards::test_compound_key_input_and_partial | `fc` is a cell builder | R6
tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF005UnhashableAnswers::test_term_instance_answer | answer shape read from slot 0 | R6
tests/audit_2026_07_05/test_09_builtins.py::test_F002_filter_map_inner_bindings | `out[0].B` → `out[0][2]` | R6
tests/audit_2026_07_05/test_09_builtins.py::test_regression_dr_alias_guard | `deref(P).A` → `deref(P)[1]` | R6
tests/audit_2026_07_05/test_03_compiler_goals.py::TestF004CatchFunctorCatcher::test_instance_catcher_via_variable_arg_catches | RENAMED `test_prebuilt_catcher_via_variable_arg_catches`; the pre-built catcher is the cell the throw site builds | R6
tests/audit_2026_07_05/test_03_compiler_goals.py::TestF004CatchFunctorCatcher::test_compound_vs_instance_unify_is_the_root_cause | RENAMED `test_compound_vs_cell_unify_is_the_root_cause`; same mismatch, one representation later | R6

## Behaviour the flip IMPROVES (tests inverted from "fails" to "succeeds")

tests/test_predicate_class_as_term_value.py::TestClausalSourceRepro::test_bare_functor_name_compared_to_a_string_just_fails | INVERTED to `test_bare_functor_name_now_IS_the_string`: `functor/3` names a functor with a string and a bare data-functor reference IS that string, so `NAME is cite` SUCCEEDS. The todo's asymmetry is resolved, not merely diagnosed | R6
tests/test_predicate_class_as_term_value.py::TestClausalSourceRepro::test_the_field_body_verbatim_fails_instead_of_raising | INVERTED to `test_the_field_body_verbatim_now_succeeds`: the whole body succeeds, which is what its author wrote it expecting | R6

## Line-number pins shifted by the source edits

tests/test_funnel_lint.py::test_testing_py_allowlist_entry_is_load_bearing, ::test_dotted_receiver_is_caught, and the `clausal/testing.py` ALLOWLIST range | 2260 → 2286 and (2215, 2329) → (2241, 2355); mechanical shift from the two cell-aware diagnostic additions earlier in `clausal/testing.py`, no semantic change | §4 (housekeeping)

---

# Fix round 1 — test edits

None of these are inversions of a flip-era pin; they are new regression tests
plus two mechanical pin shifts. Listed here so the ledger stays the single
place a reviewer can see every test-side edit.

tests/test_funnel_accessors.py::TestCellGroundnessRegression (5 NEW tests) | `_is_ground` on a cell, on a cell nested in a list/Compound, agreeing with the class twin, `_findall_copy_row`'s ISO copy, and `compound/1` through the funnel | fix-round CRITICAL 1
tests/test_tagged_terms.py::TestCellsAtTheBuiltinSurface (5 NEW tests) | `ground/1`, `compound/1`, `write/1` and `term_str` at the user-visible surface, each against the class twin | fix-round CRITICAL 1
tests/test_constants.py (4 NEW tests + 2 NEW fixtures) | a `-constants` RHS constructing an IMPORTED data functor (incl. nested), and the three placement errors | fix-round IMPORTANT 4
tests/test_exceptions.py::TestAssertzAgainstADataFunctor (4 NEW tests) | the ISO `permission_error` for a cell head reaching assertz — error class, term shape, message, and that `-dynamic` really is the remedy | fix-round IMPORTANT 5
tests/test_funnel_lint.py (`clausal/terms.py` ALLOWLIST range) | 2355-2457 → 2373-2475: mechanical shift for the `term_str` cell branch added above it | §4 (housekeeping)
tests/test_var_classifier_conformance.py::test_corpus_has_no_constant_shaped_variables | grew the explicit declared-constant allowlist its own docstring anticipated, for the new `-constants` fixture, plus a check that each allowlisted token really is declared by a `-constants` line in that file | §4 (housekeeping)
tests/fixtures/docs/directives_sigs.txt (3 NEW snippets) | the data-functor and `name/arity` examples the rewritten `docs/directives.md` references, so the doc-snippet coverage test does not flag them as raw blocks | fix-round IMPORTANT 6

---

# Fix round 2 — test edits

tests/test_tagged_terms.py::TestCallableAndTheTupleDataEdge (5 NEW tests) | `callable_/1` on a str-functor cell, a var-functor cell and a 0-arity cell, each against its Compound (and class) twin side by side; the tuple-DATA tag against BOTH candidate analogs, pinning which one it tracks; and `compound/1`'s pre-existing 0-arity Compound wart, pinned rather than copied. The helper asserts the predicate is REGISTERED before probing — the guard against the false negative that let `callable_/1` through round 1 | fix-round-2 Finding 1 follow-up
