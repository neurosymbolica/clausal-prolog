# Test Migration Candidates

Tests classified as **behavior** exercise the Clausal language via `solve`/`once`/`query`/`call`/`run_file` and should migrate to `.clausal` fixtures. **infra** tests assert on Python-level implementation and stay in Python. **mixed** needs manual split. **unknown** needs review.

## Summary by submodule

| submodule | behavior | mixed | unknown | infra |
|---|---:|---:|---:|---:|
| conformity | 0 | 22 | 0 | 0 |
| constraints | 2 | 97 | 125 | 949 |
| control | 8 | 194 | 72 | 175 |
| core | 23 | 379 | 142 | 844 |
| docs | 1 | 0 | 4 | 0 |
| misc | 85 | 164 | 286 | 530 |
| modules | 71 | 364 | 237 | 824 |
| prolog | 4 | 11 | 188 | 268 |
| scipy_torch | 26 | 700 | 17 | 165 |

## Summary by file (files with ≥1 behavior or mixed test)

| file | behavior | mixed | unknown | infra |
|---|---:|---:|---:|---:|
| `tests/conformity/test_iso_type_checking.py` (conformity) | 0 | 22 | 0 | 0 |
| `tests/test_clpb.py` (constraints) | 1 | 3 | 26 | 83 |
| `tests/test_clpz.py` (constraints) | 1 | 0 | 33 | 20 |
| `tests/test_coroutining.py` (constraints) | 0 | 51 | 0 | 0 |
| `tests/test_reified_ite.py` (constraints) | 0 | 18 | 0 | 83 |
| `tests/test_clpfd.py` (constraints) | 0 | 14 | 17 | 45 |
| `tests/test_reif_builtins.py` (constraints) | 0 | 7 | 2 | 26 |
| `tests/test_clpq.py` (constraints) | 0 | 4 | 11 | 105 |
| `tests/test_tabling.py` (control) | 4 | 12 | 7 | 37 |
| `tests/test_meta.py` (control) | 2 | 21 | 0 | 0 |
| `tests/test_dcg.py` (control) | 1 | 56 | 0 | 0 |
| `tests/test_higher_order.py` (control) | 1 | 5 | 0 | 28 |
| `tests/test_exceptions.py` (control) | 0 | 20 | 6 | 1 |
| `tests/test_edcg.py` (control) | 0 | 19 | 9 | 0 |
| `tests/test_string_higher_order.py` (control) | 0 | 16 | 0 | 0 |
| `tests/test_dif.py` (control) | 0 | 13 | 2 | 27 |
| `tests/test_metainterpreters.py` (control) | 0 | 11 | 0 | 0 |
| `tests/test_lambdas.py` (control) | 0 | 8 | 6 | 32 |
| `tests/test_control.py` (control) | 0 | 7 | 0 | 0 |
| `tests/test_wfs.py` (control) | 0 | 6 | 5 | 20 |
| `tests/test_slg_termination.py` (core) | 9 | 10 | 1 | 0 |
| `tests/test_search.py` (core) | 6 | 70 | 6 | 7 |
| `tests/test_import.py` (core) | 5 | 4 | 5 | 18 |
| `tests/test_deep_indexing.py` (core) | 2 | 21 | 0 | 18 |
| `tests/test_directives.py` (core) | 1 | 0 | 4 | 25 |
| `tests/test_phase5_builtins.py` (core) | 0 | 78 | 8 | 39 |
| `tests/test_term_inspection.py` (core) | 0 | 50 | 0 | 2 |
| `tests/test_body_star_decon.py` (core) | 0 | 40 | 0 | 0 |
| `tests/test_builtins.py` (core) | 0 | 24 | 0 | 13 |
| `tests/test_compiler_goals.py` (core) | 0 | 22 | 0 | 34 |
| `tests/conformity/test_iso_term_manipulation.py` (core) | 0 | 18 | 0 | 0 |
| `tests/test_callsite_specialization.py` (core) | 0 | 10 | 7 | 29 |
| `tests/test_compiler.py` (core) | 0 | 8 | 2 | 70 |
| `tests/test_term_expansion.py` (core) | 0 | 7 | 2 | 16 |
| `tests/test_compiler_v2.py` (core) | 0 | 5 | 0 | 10 |
| `tests/test_builtin_classes.py` (core) | 0 | 4 | 24 | 27 |
| `tests/test_pycache.py` (core) | 0 | 3 | 5 | 2 |
| `tests/conformity/test_iso_unification.py` (core) | 0 | 2 | 2 | 15 |
| `tests/test_template_compiler.py` (core) | 0 | 2 | 2 | 70 |
| `tests/test_free_threading.py` (core) | 0 | 1 | 3 | 8 |
| `tests/test_doc_snippet_coverage.py` (docs) | 1 | 0 | 1 | 0 |
| `tests/test_specialization_pipeline.py` (misc) | 27 | 9 | 10 | 16 |
| `tests/test_scryer_backend.py` (misc) | 20 | 0 | 13 | 0 |
| `tests/test_trealla_backend.py` (misc) | 19 | 0 | 11 | 0 |
| `tests/test_io.py` (misc) | 7 | 1 | 0 | 50 |
| `tests/test_uuid_module.py` (misc) | 7 | 0 | 0 | 52 |
| `tests/test_string_head_patterns.py` (misc) | 2 | 18 | 0 | 0 |
| `tests/test_tail_recursion.py` (misc) | 1 | 9 | 5 | 26 |
| `tests/test_spacy_module.py` (misc) | 1 | 0 | 13 | 38 |
| `tests/test_translations.py` (misc) | 1 | 0 | 12 | 12 |
| `tests/test_specialization.py` (misc) | 0 | 68 | 38 | 49 |
| `tests/test_solve.py` (misc) | 0 | 31 | 1 | 6 |
| `tests/test_sympy_module.py` (misc) | 0 | 17 | 11 | 22 |
| `tests/test_trail_elision.py` (misc) | 0 | 10 | 0 | 4 |
| `tests/test_segstring.py` (misc) | 0 | 1 | 5 | 41 |
| `tests/test_units.py` (modules) | 26 | 0 | 100 | 91 |
| `tests/test_regex.py` (modules) | 17 | 36 | 0 | 0 |
| `tests/test_module_imports.py` (modules) | 12 | 5 | 13 | 5 |
| `tests/test_string_list_builtins.py` (modules) | 11 | 39 | 0 | 0 |
| `tests/test_yaml_module.py` (modules) | 1 | 34 | 10 | 0 |
| `tests/test_python_interop.py` (modules) | 1 | 12 | 0 | 0 |
| `tests/test_sqlite.py` (modules) | 1 | 5 | 0 | 31 |
| `tests/test_list_util.py` (modules) | 1 | 0 | 0 | 42 |
| `tests/test_logging_module.py` (modules) | 1 | 0 | 0 | 39 |
| `tests/test_clausal_modules.py` (modules) | 0 | 102 | 0 | 0 |
| `tests/test_dict_set_builtins.py` (modules) | 0 | 73 | 0 | 19 |
| `tests/test_chars.py` (modules) | 0 | 39 | 0 | 39 |
| `tests/test_seglist_passthrough.py` (modules) | 0 | 11 | 0 | 0 |
| `tests/test_seglist_creation.py` (modules) | 0 | 5 | 1 | 20 |
| `tests/test_dict_set_compiler.py` (modules) | 0 | 3 | 13 | 13 |
| `tests/test_prolog_import.py` (prolog) | 3 | 8 | 13 | 2 |
| `tests/test_prolog_operators.py` (prolog) | 1 | 3 | 17 | 0 |
| `tests/test_torch.py` (scipy_torch) | 13 | 3 | 3 | 0 |
| `tests/test_scipy_integrate.py` (scipy_torch) | 2 | 49 | 0 | 10 |
| `tests/test_scipy_stats.py` (scipy_torch) | 1 | 75 | 0 | 18 |
| `tests/test_scipy_special.py` (scipy_torch) | 1 | 71 | 1 | 8 |
| `tests/test_scipy_spatial.py` (scipy_torch) | 1 | 64 | 2 | 2 |
| `tests/test_scipy_sparse.py` (scipy_torch) | 1 | 55 | 3 | 4 |
| `tests/test_scipy_ndimage.py` (scipy_torch) | 1 | 51 | 0 | 14 |
| `tests/test_scipy_interpolate.py` (scipy_torch) | 1 | 50 | 1 | 1 |
| `tests/test_scipy_cluster.py` (scipy_torch) | 1 | 43 | 0 | 9 |
| `tests/test_scipy_optimize.py` (scipy_torch) | 1 | 41 | 0 | 6 |
| `tests/test_scipy_fft.py` (scipy_torch) | 1 | 36 | 0 | 15 |
| `tests/test_scipy_differentiate.py` (scipy_torch) | 1 | 28 | 0 | 6 |
| `tests/test_scipy_constants.py` (scipy_torch) | 1 | 0 | 4 | 46 |
| `tests/test_scipy_signal.py` (scipy_torch) | 0 | 77 | 0 | 20 |
| `tests/test_scipy_linalg.py` (scipy_torch) | 0 | 57 | 0 | 6 |

## Per-test classification

Entries marked **†** are also listed in `DUPLICATE_TESTS.md` — prefer deletion over migration when an equivalent `.clausal` test already covers them.

### conformity

<details><summary><code>tests/conformity/test_iso_type_checking.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 42 | **mixed** | `test_bound_var_not_var` | call | Module, Trail, Var, unify |
| 47 | **mixed** | `test_bound_var_is_nonvar` | call | Module, Trail, Var, unify |
| 57 | **mixed** | `test_var_fails_compound` | call | Compound, Module, Trail |
| 60 | **mixed** | `test_nonvar_succeeds_compound` | call | Compound, Module, Trail |
| 63 | **mixed** | `test_atom_fails_for_compound` | call | Compound, Module, Trail |
| 66 | **mixed** | `test_compound_succeeds` | call | Compound, Module, Trail |
| 69 | **mixed** | `test_compound_arity2` | call | Compound, Module, Trail |
| 72 | **mixed** | `test_compound_kwterm` | call | KWTerm, Module, Trail |
| 75 | **mixed** | `test_compound_atom_fails` | call | Module, Trail |
| 78 | **mixed** | `test_compound_int_fails` | call | Module, Trail |
| 81 | **mixed** | `test_compound_var_fails` | call | Module, Trail, Var |
| 84 | **mixed** | `test_compound_list_fails` | call | Module, Trail |
| 88 | **mixed** | `test_arity0_compound_still_compound` | call | Compound, Module, Trail |
| 92 | **mixed** | `test_callable_compound` | call | Compound, Module, Trail |
| 95 | **mixed** | `test_ground_compound_with_var` | call | Compound, Module, Trail, Var |
| 103 | **mixed** | `test_bool_not_integer` | call | Module, Trail |
| 108 | **mixed** | `test_bool_not_number` | call | Module, Trail |
| 111 | **mixed** | `test_bool_not_atom` | call | Module, Trail |
| 114 | **mixed** | `test_complex_not_number` | call | Module, Trail |
| 122 | **mixed** | `test_negative_integer` | call | Module, Trail |
| 125 | **mixed** | `test_negative_number` | call | Module, Trail |
| 128 | **mixed** | `test_negative_float` | call | Module, Trail |

</details>

### constraints

<details><summary><code>tests/test_attributes.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 38 | **infra** | `test_basic` |  | Trail, Var |
| 45 | **infra** | `test_bound_var_fails` |  | Trail |
| 51 | **infra** | `test_unbound_key_fails` |  | Trail, Var |
| 56 | **infra** | `test_non_string_key_fails` |  | Trail, Var |
| 61 | **infra** | `test_overwrite` |  | Trail, Var |
| 70 | **infra** | `test_backtrack_undoes` |  | Trail, Var |
| 85 | **infra** | `test_basic` |  | Trail, Var, deref |
| 94 | **infra** | `test_missing_key_fails` |  | Trail, Var |
| 100 | **infra** | `test_non_var_fails` |  | Trail, Var |
| 105 | **infra** | `test_unify_check` |  | Trail, Var |
| 118 | **infra** | `test_after_delete_fails` |  | Trail, Var |
| 132 | **infra** | `test_basic` |  | Trail, Var |
| 141 | **infra** | `test_nonexistent_succeeds` |  | Trail, Var |
| 148 | **infra** | `test_backtrack_undoes` |  | Trail, Var |
| 164 | **infra** | `test_multiple_attrs` |  | DictTerm, Trail, Var, deref |
| 178 | **infra** | `test_no_attrs` |  | DictTerm, Trail, Var, deref |
| 188 | **infra** | `test_non_var_fails` |  | Trail, Var |
| 198 | **infra** | `test_dict_term` |  | DictTerm, Trail, Var |
| 207 | **infra** | `test_empty_dict` |  | DictTerm, Trail, Var |
| 213 | **infra** | `test_non_dict_fails` |  | Trail, Var |
| 218 | **infra** | `test_non_var_fails` |  | DictTerm, Trail |
| 228 | **infra** | `test_var_with_attr` |  | Trail, Var |
| 236 | **infra** | `test_bare_var_fails` |  | Trail, Var |
| 241 | **infra** | `test_bound_term_fails` |  | Trail |
| 251 | **infra** | `test_single_attvar` |  | Trail, Var, deref |
| 263 | **infra** | `test_list_with_mix` |  | Trail, Var, deref |
| 280 | **infra** | `test_no_attvars` |  | Trail, Var, deref |
| 286 | **infra** | `test_compound_term` |  | Compound, Trail, Var, deref |
| 298 | **infra** | `test_duplicate_var_listed_once` |  | Trail, Var, deref |
| 314 | **infra** | `test_coexist_with_clpfd` |  | Trail, Var |
| 327 | **infra** | `test_custom_hook_rejects_unification` |  | Trail, Var, deref, unify |
| 350 | **infra** | `test_custom_hook_accepts_unification` |  | Trail, Var, deref, unify |
| 372 | **infra** | `test_round_trip_put_get_attrs` |  | DictTerm, Trail, Var, deref |

</details>

<details><summary><code>tests/test_clpb.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 36 | **infra** | `test_construction` |  | BDDNode |
| 43 | **infra** | `test_identity_equality` |  | BDDNode |
| 50 | **infra** | `test_hashable` |  | BDDNode |
| 56 | **infra** | `test_repr` |  | BDDNode |
| 68 | **infra** | `test_reduction_rule` |  | Trail, Var |
| 78 | **infra** | `test_unique_table_sharing` |  | Trail, Var |
| 88 | **infra** | `test_different_children_different_node` |  | Trail, Var |
| 104 | **unknown** | `test_and_terminals` |  |  |
| 111 | **unknown** | `test_or_terminals` |  |  |
| 118 | **unknown** | `test_xor_terminals` |  |  |
| 125 | **unknown** | `test_equiv_terminals` |  |  |
| 132 | **unknown** | `test_impl_terminals` |  |  |
| 139 | **infra** | `test_and_with_variable` |  | Var |
| 148 | **infra** | `test_or_with_variable` |  | Var |
| 157 | **infra** | `test_xor_two_variables` |  | BDDNode, Var |
| 169 | **unknown** | `test_negate` |  |  |
| 174 | **infra** | `test_negate_variable` |  | BDDNode, Var |
| 191 | **unknown** | `test_restrict_terminal` |  |  |
| 196 | **infra** | `test_restrict_identity` |  | Var |
| 204 | **infra** | `test_restrict_higher_var` |  | Var |
| 220 | **unknown** | `test_int_constants` |  |  |
| 225 | **unknown** | `test_bool_constants` |  |  |
| 230 | **unknown** | `test_invalid_int` |  |  |
| 235 | **infra** | `test_var` |  | BDDNode, Var |
| 243 | **infra** | `test_bitand` |  | Var |
| 252 | **infra** | `test_bitor` |  | Var |
| 259 | **infra** | `test_bitxor` |  | Var |
| 266 | **infra** | `test_invert` |  | BDDNode, Var |
| 275 | **infra** | `test_bool_eq` |  | BDDNode, Var |
| 282 | **infra** | `test_bool_impl` |  | BDDNode, Var |
| 289 | **infra** | `test_nested_expression` |  | BDDNode, Var |
| 297 | **unknown** | `test_unsupported_type` |  |  |
| 309 | **infra** | `test_ground_true` |  | Trail |
| 314 | **infra** | `test_ground_false` |  | Trail |
| 319 | **infra**† | `test_single_var` |  | Trail, Var, deref |
| 327 | **infra** | `test_and_forces_both` |  | Trail, Var |
| 336 | **infra** | `test_contradiction_fails` |  | Trail, Var |
| 344 | **infra** | `test_tautology_succeeds` |  | Trail, Var |
| 352 | **infra**† | `test_forced_value` |  | Trail, Var, deref |
| 368 | **infra** | `test_sat_negation_forces_zero` |  | Trail, Var, deref |
| 377 | **infra** | `test_sat_and_two_vars` |  | Trail, Var, deref |
| 387 | **infra** | `test_sat_or_no_force` |  | Trail, Var, deref |
| 402 | **infra** | `test_sequential_sat_conjunction` |  | Trail, Var, deref |
| 420 | **infra** | `test_tautology` |  | Trail, Var, deref |
| 430 | **infra** | `test_contradiction` |  | Trail, Var, deref |
| 440 | **infra** | `test_indeterminate` |  | Trail, Var |
| 448 | **infra** | `test_ground_true` |  | Trail, Var, deref |
| 455 | **infra** | `test_ground_false` |  | Trail, Var, deref |
| 462 | **infra** | `test_xor_not_tautology` |  | Trail, Var |
| 470 | **infra** | `test_equiv_tautology` |  | Trail, Var, deref |
| 487 | **infra** | `test_xor_count` |  | Trail, Var, deref |
| 496 | **infra** | `test_and_count` |  | Trail, Var, deref |
| 505 | **infra** | `test_or_count` |  | Trail, Var, deref |
| 514 | **infra** | `test_tautology_count` |  | Trail, Var, deref |
| 524 | **infra** | `test_contradiction_count` |  | Trail, Var, deref |
| 534 | **infra**† | `test_single_var_true` |  | Trail, Var, deref |
| 542 | **infra** | `test_three_vars_and` |  | Trail, Var, deref |
| 559 | **infra**† | `test_single_var` |  | Trail, Var, deref |
| 569 | **infra** | `test_two_vars` |  | Trail, Var, deref |
| 580 | **infra** | `test_constrained_xor` |  | Trail, Var, deref |
| 592 | **infra** | `test_all_bound` |  | Trail, Var, unify |
| 609 | **infra** | `test_bind_constrained_var` |  | Trail, Var, deref, unify |
| 619 | **infra** | `test_bind_to_invalid_int` |  | Trail, Var, unify |
| 640 | **infra** | `test_var_var_merge` |  | Trail, Var, unify |
| 659 | **infra** | `test_var_var_merge_incompatible` |  | Trail, Var, unify |
| 686 | **infra** | `test_backtrack_restores_state` |  | Trail, Var, deref |
| 715 | **infra** | `test_labeling_backtracks_cleanly` |  | Trail, Var, deref |
| 735 | **infra** | `test_bool_eq_construction` |  | Var |
| 742 | **infra** | `test_bool_impl_construction` |  | Var |
| 749 | **infra** | `test_bool_eq_in_sat` |  | Trail, Var, deref |
| 762 | **infra** | `test_bool_impl_in_sat` |  | Trail, Var, deref |
| 794 | **unknown** | `test_0_0` |  |  |
| 799 | **unknown** | `test_0_1` |  |  |
| 804 | **unknown** | `test_1_0` |  |  |
| 809 | **unknown** | `test_1_1` |  |  |
| 841 | **unknown** | `test_0_0_0` |  |  |
| 845 | **unknown** | `test_1_1_0` |  |  |
| 849 | **unknown** | `test_1_1_1` |  |  |
| 853 | **unknown** | `test_0_1_1` |  |  |
| 857 | **unknown** | `test_1_0_0` |  |  |
| 868 | **infra** | `test_3_pigeons_2_holes` |  | Trail, Var |
| 899 | **infra** | `test_demorgan` |  | Trail, Var, deref |
| 911 | **infra** | `test_non_equivalence` |  | Trail, Var |
| 936 | **mixed** | `test_half_adder_0_0` | call | Var, deref |
| 946 | **mixed** | `test_half_adder_1_1` | call | Var, deref |
| 956 | **mixed** | `test_full_adder_1_1_1` | call | Var, deref |
| 966 | **behavior** | `test_pigeon_hole_unsat` | call |  |
| 979 | **unknown** | `test_nand_true_true` |  |  |
| 985 | **unknown** | `test_nand_true_false` |  |  |
| 991 | **unknown** | `test_nand_false_true` |  |  |
| 997 | **unknown** | `test_nand_false_false` |  |  |
| 1003 | **infra** | `test_nand_with_variables` |  | Trail, Var |
| 1019 | **infra** | `test_nand_self` |  | Trail, Var |
| 1040 | **unknown** | `test_terminal_true` |  |  |
| 1047 | **unknown** | `test_terminal_false` |  |  |
| 1053 | **infra** | `test_single_variable` |  | Trail, Var |
| 1064 | **infra** | `test_two_variables` |  | Trail, Var |
| 1078 | **infra** | `test_complex_bdd` |  | Trail, Var |
| 1092 | **infra** | `test_adds_to_existing_set` |  | Trail, Var |
| 1111 | **infra** | `test_terminal_true` |  | Trail |
| 1117 | **infra** | `test_terminal_false` |  | Trail |
| 1124 | **infra** | `test_single_var_forced_high` |  | Trail, Var, deref |
| 1134 | **infra** | `test_single_var_forced_low` |  | Trail, Var, deref |
| 1144 | **infra** | `test_contradiction_detected` |  | BDDNode, Trail, Var |
| 1162 | **infra** | `test_20_variable_or_chain` |  | Trail, Var, deref |
| 1174 | **infra** | `test_10_variable_xor_chain` |  | Trail, Var, deref |
| 1186 | **infra**† | `test_sat_count_constant_true` |  | Trail, Var, deref |
| 1194 | **infra** | `test_sat_count_constant_false` |  | Trail, Var, deref |
| 1202 | **infra** | `test_sat_count_single_var_identity` |  | Trail, Var, deref |
| 1211 | **infra** | `test_deep_and_chain` |  | Trail, Var, deref |
| 1223 | **infra** | `test_labeling_with_many_vars` |  | Trail, Var |
| 1242 | **infra** | `test_restrict_deeper_bdd` |  | Trail, Var |
| 1269 | **infra** | `test_restrict_preserves_other_vars` |  | Trail, Var |

</details>

<details><summary><code>tests/test_clpfd.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 67 | **unknown** | `test_from_range` |  |  |
| 72 | **unknown** | `test_from_range_empty` |  |  |
| 77 | **unknown** | `test_from_range_singleton` |  |  |
| 82 | **unknown** | `test_contains` |  |  |
| 94 | **unknown** | `test_min_max` |  |  |
| 100 | **unknown** | `test_min_max_empty` |  |  |
| 107 | **unknown** | `test_size` |  |  |
| 112 | **unknown** | `test_singleton` |  |  |
| 118 | **unknown** | `test_intersection` |  |  |
| 125 | **unknown** | `test_intersection_disjoint` |  |  |
| 131 | **unknown** | `test_intersection_identical` |  |  |
| 136 | **unknown** | `test_remove` |  |  |
| 144 | **unknown** | `test_remove_above` |  |  |
| 150 | **unknown** | `test_remove_below` |  |  |
| 156 | **unknown** | `test_values` |  |  |
| 168 | **infra** | `test_post_domain` |  | Trail, Var |
| 177 | **infra** | `test_post_domain_and_unify_succeeds` |  | Trail, Var, deref, unify |
| 185 | **infra** | `test_post_domain_and_unify_fails` |  | Trail, Var, unify |
| 194 | **infra** | `test_post_domain_list` |  | Trail, Var |
| 204 | **infra** | `test_post_domain_narrows_existing` |  | Trail, Var |
| 213 | **infra** | `test_post_domain_singleton_binds` |  | Trail, Var, deref |
| 220 | **infra** | `test_post_domain_empty_fails` |  | Trail, Var |
| 229 | **infra** | `test_post_domain_ground_int` |  | Trail |
| 242 | **infra** | `test_label_single` |  | Trail, Var, deref |
| 252 | **infra** | `test_label_two_vars` |  | Trail, Var, deref |
| 266 | **infra** | `test_label_backtracking` |  | Trail, Var, deref |
| 284 | **infra** | `test_label_all_ground` |  | Trail |
| 297 | **infra** | `test_same_atoms` |  | Trail |
| 302 | **infra** | `test_different_atoms` |  | Trail |
| 307 | **infra** | `test_same_compound` |  | Compound, Trail |
| 312 | **infra** | `test_different_compound` |  | Compound, Trail |
| 317 | **infra** | `test_var_vs_var_different` |  | Trail, Var |
| 323 | **infra** | `test_var_vs_var_same` |  | Trail, Var |
| 329 | **infra** | `test_bound_vars` |  | Trail, Var, unify |
| 344 | **infra** | `test_ground_equal` |  | Trail |
| 349 | **infra** | `test_ground_unequal` |  | Trail |
| 354 | **infra**† | `test_var_eq_int` |  | Trail, Var, deref |
| 362 | **infra** | `test_var_eq_var` |  | Trail, Var |
| 376 | **infra**† | `test_auto_domain` |  | Trail, Var, deref |
| 386 | **infra** | `test_ground_different` |  | Trail |
| 391 | **infra** | `test_ground_same` |  | Trail |
| 396 | **infra** | `test_var_ne_int` |  | Trail, Var |
| 406 | **infra** | `test_ne_wipeout` |  | Trail, Var |
| 416 | **infra** | `test_ground_lt` |  | Trail |
| 423 | **infra** | `test_var_lt` |  | Trail, Var |
| 435 | **infra** | `test_ground_le` |  | Trail |
| 442 | **infra** | `test_chained_comparison` |  | Trail, Var |
| 456 | **infra** | `test_gt` |  | Trail |
| 462 | **infra** | `test_ge` |  | Trail |
| 476 | **infra** | `test_lt_chain` |  | Trail, Var, deref |
| 491 | **infra** | `test_eq_propagation` |  | Trail, Var |
| 506 | **infra** | `test_wipeout` |  | Trail, Var |
| 514 | **infra** | `test_backtracking_restores_domains` |  | Trail, Var |
| 536 | **mixed** | `test_ground_eq` | solve | Module |
| 543 | **mixed** | `test_ground_eq_fails` | solve | Module |
| 549 | **mixed** | `test_ground_ne` | solve | Module |
| 555 | **mixed** | `test_ground_lt` | solve | Module |
| 561 | **mixed** | `test_ground_le` | solve | Module |
| 567 | **mixed** | `test_ground_gt` | solve | Module |
| 573 | **mixed** | `test_ground_ge` | solve | Module |
| 579 | **mixed** | `test_var_eq_via_solve` | solve | Module, Var, deref |
| 591 | **mixed** | `test_chained_le_via_solve` | solve | And, Call, LoadName, Module, Var, deref |
| 610 | **mixed** | `test_ne_via_solve` | solve | And, Call, LoadName, Module, Var, deref |
| 627 | **mixed** | `test_evaluate_unchanged` | solve | Add, Evaluate, Module, Var, deref |
| 639 | **mixed** | `test_is_unify_unchanged` | solve | Module, Var, deref |
| 651 | **mixed** | `test_is_not_dif_unchanged` | solve | Module, Var |
| 669 | **infra** | `test_basic` |  | Trail, Var, deref |
| 680 | **infra** | `test_all_different_ground_ok` |  | Trail |
| 685 | **infra** | `test_all_different_ground_fail` |  | Trail |
| 690 | **mixed** | `test_all_different_via_solve` | solve | And, Call, LoadName, Module, Var, deref |
| 750 | **unknown** | `test_4_queens` |  |  |
| 755 | **unknown** | `test_8_queens` |  |  |
| 767 | **infra** | `test_sendmoremoney` |  | Add, Mult, Trail, Var, deref |
| 808 | **infra** | `test_independent` |  | Trail, Var, deref, unify |
| 830 | **infra** | `test_cascaded_lt` |  | Trail, Var, deref |
| 844 | **infra** | `test_ne_narrows_after_other_change` |  | Trail, Var |

</details>

<details><summary><code>tests/test_clportools.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 52 | **infra** | `test_var_mapping_bidirectional` |  | Trail, Var |
| 62 | **infra** | `test_var_mapping_idempotent` |  | Trail, Var |
| 70 | **infra** | `test_bool_var_mapping` |  | Trail, Var |
| 79 | **infra** | `test_sparse_domain` |  | Trail, Var |
| 87 | **infra** | `test_ground_var_raises` |  | Trail, Var, unify |
| 95 | **infra** | `test_state_cleanup_on_gc` |  | Trail |
| 109 | **infra** | `test_backtracking_retracts_constraints` |  | Trail, Var |
| 124 | **infra** | `test_nested_backtracking` |  | Trail, Var |
| 141 | **infra** | `test_three_nested_scopes` |  | Trail, Var |
| 165 | **infra** | `test_label_blocking_clauses_scoped` |  | Trail, Var |
| 185 | **infra** | `test_simple_no_overlap` |  | Trail, Var, deref |
| 205 | **infra** | `test_no_overlap_unsat` |  | Trail, Var |
| 222 | **infra** | `test_cumulative_allows_overlap` |  | Trail, Var |
| 238 | **infra** | `test_2d_packing` |  | Trail, Var |
| 256 | **infra** | `test_job_shop` |  | LtE, Trail, Var |
| 279 | **infra** | `test_scheduling_backtrack` |  | Trail, Var |
| 304 | **infra** | `test_tsp_3_cities` |  | Trail, Var |
| 318 | **infra** | `test_circuit_2_nodes` |  | Trail, Var |
| 330 | **infra** | `test_cpsat_registered` |  | get_builtin_predicate |
| 335 | **infra** | `test_cpsat_in_registered` |  | get_builtin_predicate |
| 340 | **infra** | `test_cpsat_solve_registered` |  | get_builtin_predicate |
| 345 | **infra** | `test_glop_registered` |  | get_builtin_predicate |
| 350 | **infra** | `test_scip_registered` |  | get_builtin_predicate |
| 355 | **infra** | `test_max_flow_registered` |  | get_builtin_predicate |
| 360 | **infra** | `test_tsp_registered` |  | get_builtin_predicate |
| 365 | **infra** | `test_knapsack_registered` |  | get_builtin_predicate |

</details>

<details><summary><code>tests/test_clportools_lp.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 29 | **infra** | `test_var_registration` |  | Trail, Var |
| 37 | **infra** | `test_solver_mismatch` |  | Trail |
| 44 | **infra** | `test_scip_available` |  | Trail |
| 50 | **infra** | `test_backtracking_retracts_constraints` |  | GtE, LtE, Trail, Var |

</details>

<details><summary><code>tests/test_clpq.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 39 | **infra** | `test_fraction_dispatches_to_q_eq` |  | Trail, Var, deref |
| 47 | **infra** | `test_fraction_dispatches_to_q_le` |  | Trail, Var |
| 55 | **infra** | `test_int_does_not_dispatch_to_q` |  | Trail, Var, deref |
| 63 | **infra** | `test_float_does_not_dispatch_to_q` |  | Trail, Var |
| 74 | **infra** | `test_basic` |  | Trail, Var, deref |
| 83 | **infra** | `test_narrows` |  | Trail, Var, deref |
| 92 | **infra** | `test_infeasible` |  | Trail, Var |
| 98 | **infra** | `test_point_binds` |  | Trail, Var, deref |
| 104 | **infra** | `test_list` |  | Trail, Var, deref |
| 112 | **infra** | `test_ground_check` |  | Trail |
| 118 | **infra** | `test_unbounded` |  | Trail, Var, deref |
| 131 | **infra** | `test_eq_ground_rationals` |  | Trail |
| 136 | **infra** | `test_eq_ground_rationals_fail` |  | Trail |
| 141 | **infra** | `test_ne_ground` |  | Trail |
| 147 | **infra** | `test_lt_ground` |  | Trail |
| 154 | **infra** | `test_le_ground` |  | Trail |
| 161 | **infra** | `test_gt_ground` |  | Trail |
| 167 | **infra** | `test_ge_ground` |  | Trail |
| 178 | **infra** | `test_eq_var_to_rational` |  | Trail, Var, deref |
| 184 | **infra** | `test_eq_var_to_int` |  | Trail, Var, deref |
| 195 | **infra** | `test_two_var_eq` |  | Add, Trail, Var, deref |
| 205 | **infra** | `test_three_var_system` |  | Add, Sub, Trail, Var, deref |
| 219 | **infra** | `test_contradictory` |  | Trail, Var |
| 227 | **infra** | `test_redundant` |  | Add, Trail, Var |
| 235 | **infra** | `test_rational_coefficients` |  | Add, Mult, Trail, Var, deref |
| 247 | **infra** | `test_single_var_scaled` |  | Mult, Trail, Var, deref |
| 256 | **infra** | `test_large_coefficients` |  | Mult, Trail, Var, deref |
| 270 | **infra** | `test_simple_le` |  | Trail, Var |
| 276 | **infra** | `test_le_infeasible` |  | Trail, Var |
| 283 | **infra** | `test_two_var_system` |  | Add, Trail, Var |
| 293 | **infra** | `test_redundant_constraint` |  | Trail, Var |
| 301 | **infra** | `test_zero_coefficients` |  | Add, Mult, Trail, Var, deref |
| 315 | **infra** | `test_undo_restores_unbound` |  | Trail, Var, deref |
| 324 | **infra** | `test_undo_restores_bounds` |  | Trail, Var, deref |
| 334 | **infra** | `test_undo_restores_tableau` |  | Add, Trail, Var, deref |
| 351 | **infra** | `test_maximize_simple` |  | Trail, Var, deref |
| 362 | **infra** | `test_minimize_simple` |  | Trail, Var, deref |
| 373 | **infra** | `test_maximize_lp` |  | Add, Mult, Trail, Var, deref |
| 393 | **infra** | `test_minimize_lp_binds_vars` |  | Add, Mult, Trail, Var, deref |
| 410 | **infra** | `test_minimize_lp` |  | Add, Mult, Trail, Var, deref |
| 434 | **infra** | `test_sup_simple` |  | Trail, Var, deref |
| 445 | **infra** | `test_inf_simple` |  | Trail, Var, deref |
| 456 | **infra** | `test_sup_does_not_bind_vars` |  | Trail, Var, deref |
| 468 | **infra** | `test_inf_does_not_bind_vars` |  | Trail, Var, deref |
| 479 | **infra** | `test_sup_lp` |  | Add, Mult, Trail, Var, deref |
| 501 | **infra** | `test_entailed_le_true` |  | Trail, Var |
| 510 | **infra** | `test_entailed_le_false` |  | Trail, Var |
| 519 | **infra** | `test_entailed_ge_true` |  | Trail, Var |
| 528 | **infra** | `test_entailed_eq_true` |  | Trail, Var |
| 537 | **infra** | `test_entailed_eq_false` |  | Trail, Var |
| 545 | **infra** | `test_entailed_ne_true` |  | Trail, Var |
| 554 | **infra** | `test_entailed_ne_false` |  | Trail, Var |
| 562 | **infra** | `test_entailed_does_not_modify_store` |  | Trail, Var, deref |
| 572 | **infra** | `test_entailed_does_not_add_q_attr` |  | Trail, Var |
| 585 | **infra** | `test_constant` |  | Trail |
| 590 | **infra** | `test_int` |  | Trail |
| 595 | **infra** | `test_var` |  | Trail, Var |
| 603 | **infra** | `test_add` |  | Add, Trail, Var |
| 611 | **infra** | `test_scalar_mult` |  | Mult, Trail, Var |
| 618 | **infra** | `test_nonlinear_rejected` |  | Mult, Trail, Var |
| 624 | **infra** | `test_negate` |  | Negate, Trail, Var |
| 638 | **infra** | `test_simple_bounds` |  | Trail, Var |
| 648 | **infra** | `test_inequality_projection` |  | Add, Mult, Trail, Var |
| 663 | **infra** | `test_equality_projection` |  | Add, Trail, Var |
| 674 | **infra** | `test_no_internal_vars` |  | Add, Mult, Trail, Var |
| 688 | **infra** | `test_empty_store` |  | Trail, Var |
| 698 | **infra** | `test_ground_var` |  | Trail, Var |
| 715 | **infra** | `test_simple_integer` |  | Trail, Var, deref |
| 726 | **infra** | `test_integer_lp` |  | Add, Trail, Var, deref |
| 740 | **infra** | `test_no_integer_constraint` |  | Trail, Var, deref |
| 751 | **infra** | `test_infeasible` |  | Trail, Var |
| 773 | **infra** | `test_already_integer` |  | Trail, Var, deref |
| 784 | **infra** | `test_mixed_integer` |  | Add, Trail, Var, deref |
| 797 | **infra** | `test_two_integer_vars` |  | Add, Trail, Var, deref |
| 811 | **infra** | `test_binds_variables` |  | Trail, Var, deref |
| 823 | **infra** | `test_binds_multiple_vars` |  | Add, Trail, Var, deref |
| 842 | **unknown** | `test_newton_sqrt2` |  |  |
| 850 | **infra** | `test_large_coefficient_constraint` |  | Trail, Var, deref |
| 866 | **infra** | `test_maximize_backtrack_restores_tableau` |  | Trail, Var, deref |
| 885 | **infra** | `test_minimize_backtrack_restores_tableau` |  | Trail, Var, deref |
| 905 | **infra** | `test_upper_bound_inequality` |  | Add, Trail, Var, deref |
| 919 | **infra** | `test_infeasible_upper_bound` |  | Add, Trail, Var |
| 932 | **infra** | `test_three_constraint_feasibility` |  | Add, Trail, Var |
| 943 | **infra** | `test_tight_system` |  | Add, Trail, Var, deref |
| 954 | **infra** | `test_contradictory_inequalities` |  | Add, Trail, Var |
| 964 | **infra** | `test_degenerate_vertex` |  | Add, Trail, Var, deref |
| 982 | **infra** | `test_ne_prevents_binding_to_excluded_value` |  | Trail, Var |
| 991 | **infra** | `test_ne_allows_other_values` |  | Trail, Var, deref |
| 1001 | **infra** | `test_strict_lt_rejects_equal` |  | Trail, Var |
| 1010 | **infra** | `test_strict_lt_allows_less` |  | Trail, Var |
| 1019 | **infra** | `test_ne_two_vars` |  | Trail, Var |
| 1029 | **infra** | `test_ne_two_vars_different_ok` |  | Trail, Var |
| 1039 | **infra** | `test_ne_ground_equal_fails` |  | Trail |
| 1045 | **infra** | `test_ne_ground_different_succeeds` |  | Trail |
| 1051 | **infra** | `test_ne_backtrack_restores` |  | Trail, Var, deref |
| 1068 | **infra** | `test_multi_constraint_single_snapshot` |  | Add, Trail, Var, deref |
| 1091 | **infra** | `test_fd_var_in_q_context_inherits_bounds` |  | Trail, Var |
| 1111 | **infra** | `test_fd_var_promoted_to_q_keeps_fd` |  | Trail, Var |
| 1122 | **infra** | `test_integer_fraction_accepted_by_fd` |  | Trail, Var, deref, unify |
| 1132 | **infra** | `test_non_integer_fraction_rejected_by_fd` |  | Trail, Var, unify |
| 1141 | **infra** | `test_integer_fraction_outside_domain_rejected` |  | Trail, Var, unify |
| 1150 | **infra** | `test_q_eq_on_fd_var_with_integer_result` |  | Add, Trail, Var, deref |
| 1167 | **infra** | `test_q_eq_on_fd_var_with_non_integer_result_fails` |  | Trail, Var, unify |
| 1177 | **infra**† | `test_float_still_rejected_in_q` |  | Trail, Var, unify |
| 1190 | **infra**† | `test_unify_q_var_with_float_raises` |  | Trail, Var, unify |
| 1198 | **infra** | `test_float_literal_does_not_reach_q` |  | Trail, Var, deref |
| 1221 | **mixed** | `test_rational_1_alias` | call, load_clausal_module | Var, deref |
| 1242 | **mixed** | `test_rational_with_bounds` | call, load_clausal_module | Var, deref |
| 1263 | **mixed** | `test_entailed_1_pythonic` | call, load_clausal_module | Var |
| 1290 | **mixed** | `test_entailed_1_fails` | call, load_clausal_module | Var |
| 1334 | **unknown** | `test_two_var` |  |  |
| 1342 | **unknown** | `test_three_var` |  |  |
| 1351 | **unknown** | `test_rational_coeffs` |  |  |
| 1359 | **unknown** | `test_feasible` |  |  |
| 1364 | **unknown** | `test_infeasible` |  |  |
| 1369 | **unknown** | `test_lp_maximize` |  |  |
| 1376 | **unknown** | `test_scheduling_minimize` |  |  |
| 1383 | **unknown** | `test_sup_inf` |  |  |
| 1391 | **unknown** | `test_bb_simple` |  |  |
| 1399 | **unknown** | `test_bb_sicstus` |  |  |

</details>

<details><summary><code>tests/test_clpq_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 17 | **infra** | `test_unsupported_node_raises` |  | Trail |
| 24 | **infra** | `test_disequality_conflict` |  | Trail, Var |
| 38 | **infra** | `test_unsupported_node_raises` |  | Trail |
| 45 | **infra** | `test_infeasible_returns_false` |  | GtE, LtE, Trail, Var |
| 58 | **infra** | `test_entailed_by_bounds` |  | LtE, Trail, Var |

</details>

<details><summary><code>tests/test_clpr.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 46 | **unknown** | `test_dn_is_less_or_equal` |  |  |
| 51 | **unknown** | `test_up_is_greater_or_equal` |  |  |
| 56 | **unknown** | `test_dn_changes_non_exact` |  |  |
| 61 | **unknown** | `test_dn_inf_is_inf` |  |  |
| 65 | **unknown** | `test_up_inf_is_inf` |  |  |
| 71 | **unknown** | `test_iadd_basic` |  |  |
| 77 | **unknown** | `test_iadd_outward_rounding` |  |  |
| 83 | **unknown** | `test_isub_basic` |  |  |
| 88 | **unknown** | `test_imul_positive` |  |  |
| 93 | **unknown** | `test_imul_mixed_sign` |  |  |
| 98 | **unknown** | `test_imul_negative` |  |  |
| 103 | **unknown** | `test_idiv_positive` |  |  |
| 108 | **unknown** | `test_idiv_zero_in_denominator` |  |  |
| 113 | **unknown** | `test_ipow_int_square_positive` |  |  |
| 118 | **unknown** | `test_ipow_int_square_mixed` |  |  |
| 123 | **unknown** | `test_ipow_int_cube` |  |  |
| 128 | **unknown** | `test_isqrt_positive` |  |  |
| 133 | **unknown** | `test_isqrt_zero_lo` |  |  |
| 138 | **unknown** | `test_iabs_positive` |  |  |
| 142 | **unknown** | `test_iabs_negative` |  |  |
| 146 | **unknown** | `test_iabs_mixed` |  |  |
| 151 | **unknown** | `test_isin_wide` |  |  |
| 156 | **unknown** | `test_icos_narrow` |  |  |
| 162 | **unknown** | `test_iexp_ilog_roundtrip` |  |  |
| 173 | **infra** | `test_float_literal` |  | Trail |
| 179 | **infra** | `test_int_literal` |  | Trail |
| 185 | **infra** | `test_real_var` |  | Trail, Var |
| 193 | **infra** | `test_unbound_var` |  | Trail, Var |
| 200 | **infra** | `test_add_expr` |  | Add, Trail, Var |
| 209 | **infra** | `test_mult_expr` |  | Mult, Trail, Var |
| 218 | **infra** | `test_negate_expr` |  | Negate, Trail, Var |
| 226 | **infra** | `test_pow_int_expr` |  | Pow, Trail, Var |
| 239 | **infra** | `test_in_real_bounds` |  | Trail, Var, deref |
| 248 | **infra** | `test_in_real_list` |  | Trail, Var, deref |
| 257 | **infra** | `test_in_real_narrows_existing` |  | Trail, Var, deref |
| 266 | **infra** | `test_in_real_empty_fails` |  | Trail, Var |
| 273 | **infra** | `test_unify_in_bounds_succeeds` |  | Trail, Var, deref, unify |
| 281 | **infra** | `test_unify_out_of_bounds_fails` |  | Trail, Var, unify |
| 290 | **infra** | `test_unify_at_lower_bound` |  | Trail, Var, unify |
| 297 | **infra** | `test_unify_at_upper_bound` |  | Trail, Var, unify |
| 304 | **infra** | `test_backtrack_restores_domain` |  | Trail, Var, deref |
| 315 | **infra** | `test_point_domain_binds_var` |  | Trail, Var, deref |
| 322 | **infra** | `test_ground_int_checks_domain` |  | Trail |
| 327 | **infra** | `test_ground_int_out_of_range_fails` |  | Trail |
| 332 | **infra** | `test_unify_two_real_vars_merges` |  | Trail, Var, deref, unify |
| 344 | **infra** | `test_unify_two_real_vars_disjoint_fails` |  | Trail, Var, unify |
| 359 | **infra** | `test_eq_pins_var` |  | Trail, Var, deref |
| 368 | **infra** | `test_eq_narrows_from_both_sides` |  | Trail, Var, deref |
| 382 | **infra** | `test_le_narrows_upper` |  | Trail, Var, deref |
| 390 | **infra** | `test_le_narrows_lower` |  | Trail, Var, deref |
| 398 | **infra** | `test_lt_narrows` |  | Trail, Var, deref |
| 406 | **infra** | `test_ge_succeeds` |  | Trail, Var |
| 413 | **infra** | `test_gt_narrows_lower` |  | Trail, Var, deref |
| 421 | **infra** | `test_eq_unsatisfiable` |  | Trail, Var |
| 428 | **infra** | `test_le_unsatisfiable` |  | Trail, Var |
| 435 | **infra** | `test_ge_unsatisfiable` |  | Trail, Var |
| 442 | **infra** | `test_ne_ground_equal_fails` |  | Trail, Var |
| 449 | **infra** | `test_ne_non_ground_passes` |  | Trail, Var |
| 456 | **infra** | `test_add_constraint_propagates` |  | Add, Trail, Var, deref |
| 468 | **infra** | `test_sub_constraint` |  | Sub, Trail, Var, deref |
| 482 | **infra** | `test_square_narrows_upper` |  | Mult, Trail, Var, deref |
| 491 | **infra** | `test_square_eq_pin` |  | Mult, Trail, Var, deref |
| 501 | **infra** | `test_square_unsatisfiable` |  | Mult, Trail, Var |
| 509 | **infra** | `test_product_constraint` |  | Mult, Trail, Var, deref |
| 520 | **infra** | `test_negate_constraint` |  | Negate, Trail, Var, deref |
| 530 | **infra** | `test_pow2_constraint` |  | Pow, Trail, Var, deref |
| 545 | **infra** | `test_ieee_termination` |  | Trail, Var, deref |
| 562 | **infra** | `test_eps_stopping` |  | Trail, Var, deref |
| 579 | **infra** | `test_already_ground_yields_once` |  | Trail, Var |
| 587 | **infra** | `test_empty_list_yields_once` |  | Trail |
| 593 | **infra** | `test_constrained_labeling` |  | Mult, Trail, Var, deref |
| 614 | **infra** | `test_unit_circle` |  | Add, Mult, Trail, Var, deref |
| 638 | **infra** | `test_backtrack_restores_state` |  | Trail, Var, deref |
| 657 | **infra** | `test_float_triggers_real_dispatch` |  | Trail, Var, deref |
| 669 | **infra** | `test_float_le_dispatch` |  | Trail, Var, deref |
| 678 | **infra** | `test_real_var_triggers_dispatch` |  | Trail, Var |
| 689 | **infra** | `test_fd_var_not_dispatched` |  | Trail, Var, deref |
| 704 | **infra** | `test_float_eq_undeclared_var` |  | Trail, Var, deref |
| 714 | **infra** | `test_float_in_expression` |  | Mult, Trail, Var, deref |
| 725 | **infra** | `test_ground_float_eq` |  | Trail |

</details>

<details><summary><code>tests/test_clpsat.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 35 | **infra** | `test_var_mapping_bidirectional` |  | Trail, Var |
| 45 | **infra** | `test_var_mapping_idempotent` |  | Trail, Var |
| 53 | **infra** | `test_multiple_vars_distinct` |  | Trail, Var |
| 62 | **infra** | `test_ground_var_raises` |  | Trail, Var, unify |
| 70 | **infra** | `test_var_attribute_stored` |  | Trail, Var |
| 81 | **infra** | `test_state_created_on_demand` |  | Trail |
| 88 | **infra** | `test_state_reused` |  | Trail |
| 95 | **infra** | `test_solver_mismatch_raises` |  | Trail |
| 102 | **infra** | `test_unknown_solver_raises` |  | Trail |
| 108 | **infra** | `test_solver_cleanup_on_gc` |  | Trail |
| 118 | **infra** | `test_solver_aliases` |  | Trail |
| 132 | **infra** | `test_unit_clause_sat` |  | Trail, Var |
| 140 | **infra** | `test_contradictory_clauses_unsat` |  | Trail, Var |
| 149 | **infra** | `test_binary_clause` |  | Trail, Var |
| 160 | **infra** | `test_backtracking_retracts_clauses` |  | Trail, Var |
| 176 | **infra** | `test_nested_backtracking` |  | Trail, Var |
| 199 | **infra** | `test_three_levels_of_nesting` |  | Trail, Var |
| 234 | **infra** | `test_var_is_simple` |  | Var |
| 238 | **infra** | `test_or_of_vars_is_simple` |  | Var |
| 243 | **infra** | `test_negated_var_is_simple` |  | Var |
| 248 | **infra** | `test_or_with_negation_is_simple` |  | Var |
| 253 | **infra** | `test_and_is_not_simple` |  | Var |
| 258 | **infra** | `test_nested_or_is_simple` |  | Var |
| 263 | **infra** | `test_not_is_literal` |  | Not, Var |
| 269 | **infra** | `test_or_node_is_simple` |  | Or, Var |
| 275 | **infra** | `test_or_with_not_is_simple` |  | Not, Or, Var |
| 284 | **infra** | `test_and` |  | Trail, Var |
| 291 | **infra** | `test_or` |  | Trail, Var |
| 298 | **infra** | `test_xor` |  | Trail, Var |
| 305 | **infra** | `test_eq` |  | Trail, Var |
| 312 | **infra** | `test_neq` |  | Trail, Var |
| 319 | **infra** | `test_not` |  | Trail, Var |
| 334 | **infra** | `test_bindings_undone_after_labeling` |  | Trail, Var, deref |
| 345 | **infra** | `test_ground_vars_skipped` |  | Trail, Var, deref |
| 356 | **infra** | `test_nested_search` |  | Trail, Var, deref |
| 388 | **infra** | `test_deep_backtracking_stress` |  | Trail, Var |
| 404 | **infra** | `test_cardinality_backtracks` |  | Trail, Var |
| 429 | **infra** | `test_sat_count_twice` |  | Trail, Var |
| 440 | **infra** | `test_label_sat_twice` |  | Trail, Var, deref |
| 457 | **infra** | `test_label_early_exit` |  | Trail, Var, deref |
| 478 | **infra** | `test_label_early_exit_then_relabel` |  | Trail, Var, deref |
| 500 | **infra** | `test_empty_constraint_block` |  | Trail |
| 507 | **infra** | `test_single_element_tuple` |  | Trail, Var, deref |
| 519 | **infra** | `test_bare_variable_forces_true` |  | Trail, Var, deref |
| 529 | **infra** | `test_negated_variable_forces_false` |  | Trail, Var, deref |
| 538 | **infra** | `test_deeply_nested_expression` |  | Trail, Var, deref |
| 560 | **infra** | `test_constraint_block_with_list` |  | Trail, Var, deref |
| 575 | **infra** | `test_or_not_nodes_fast_path` |  | Not, Or, Trail, Var, deref |
| 590 | **infra** | `test_top_level_and_flattened` |  | Trail, Var, deref |
| 603 | **infra** | `test_nested_and_flattened` |  | Trail, Var, deref |
| 616 | **infra** | `test_and_of_clauses_flattened` |  | Trail, Var, deref |
| 633 | **infra** | `test_and_node_flattened` |  | And, Trail, Var, deref |
| 647 | **infra** | `test_empty_list_at_most` |  | Trail |
| 655 | **infra** | `test_empty_list_at_least_zero` |  | Trail |
| 662 | **infra** | `test_empty_list_at_least_one` |  | Trail |
| 669 | **infra** | `test_empty_list_exactly_zero` |  | Trail |
| 676 | **infra** | `test_empty_list_exactly_one` |  | Trail |
| 683 | **infra** | `test_all_ground_true_at_most` |  | Trail |
| 690 | **infra** | `test_all_ground_false_at_least` |  | Trail |
| 697 | **infra** | `test_mixed_ground_and_vars` |  | Trail, Var, deref |
| 711 | **infra** | `test_at_most_exceeds_var_count` |  | Trail, Var |
| 725 | **infra** | `test_label_unregistered_var` |  | Trail, Var |
| 734 | **infra** | `test_label_bad_ground_value` |  | Trail, Var |
| 743 | **infra** | `test_tseitin_unsupported_node` |  | Add, Trail, Var |
| 752 | **infra** | `test_expr_to_literal_bad_int` |  | Trail |

</details>

<details><summary><code>tests/test_clpz.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 34 | **infra** | `test_default_domain_is_infinite` |  | Trail, Var |
| 41 | **unknown** | `test_domain_size_infinite` |  |  |
| 46 | **unknown** | `test_domain_size_half_bounded_above` |  |  |
| 51 | **unknown** | `test_domain_size_half_bounded_below` |  |  |
| 56 | **unknown** | `test_domain_size_finite` |  |  |
| 61 | **unknown** | `test_domain_contains_infinite` |  |  |
| 68 | **unknown** | `test_domain_min_infinite` |  |  |
| 73 | **unknown** | `test_domain_max_infinite` |  |  |
| 78 | **unknown** | `test_domain_values_infinite_raises` |  |  |
| 84 | **unknown** | `test_domain_values_half_bounded_raises` |  |  |
| 90 | **unknown** | `test_domain_values_finite_works` |  |  |
| 100 | **unknown** | `test_intersect_infinite_with_finite` |  |  |
| 107 | **unknown** | `test_intersect_infinite_with_infinite` |  |  |
| 112 | **unknown** | `test_intersect_half_bounded` |  |  |
| 119 | **unknown** | `test_remove_from_infinite` |  |  |
| 127 | **unknown** | `test_remove_above_infinite` |  |  |
| 133 | **unknown** | `test_remove_below_infinite` |  |  |
| 144 | **infra**† | `test_eq_narrows_to_singleton` |  | Trail, Var, deref |
| 151 | **infra** | `test_lt_narrows_upper` |  | Trail, Var |
| 161 | **infra** | `test_gt_narrows_lower` |  | Trail, Var |
| 171 | **infra** | `test_gt_and_lt_narrows_to_finite` |  | Trail, Var |
| 182 | **infra** | `test_ne_on_infinite` |  | Trail, Var |
| 193 | **infra** | `test_eq_chain_propagates` |  | Trail, Var, deref |
| 201 | **infra** | `test_all_different_infinite` |  | Trail, Var |
| 216 | **infra** | `test_label_bounded_from_constraints` |  | Trail, Var, deref |
| 227 | **infra** | `test_label_unbounded_raises` |  | Trail, Var |
| 236 | **infra** | `test_label_fully_unbounded_raises` |  | Trail, Var |
| 244 | **infra** | `test_label_first_fail_prefers_finite` |  | Trail, Var, deref |
| 262 | **infra** | `test_undo_restores_infinite_domain` |  | Trail, Var |
| 276 | **infra** | `test_undo_restores_after_eq` |  | Trail, Var, deref |
| 291 | **unknown** | `test_nqueens_still_finds_92` |  |  |
| 296 | **infra** | `test_in_domain_still_works` |  | Trail, Var, unify |
| 305 | **behavior** | `test_sudoku_example_loads` | collect_tests, load_clausal_module, run_test |  |
| 321 | **unknown** | `test_zero_times_pos_inf` |  |  |
| 325 | **unknown** | `test_zero_times_neg_inf` |  |  |
| 329 | **unknown** | `test_pos_inf_times_zero` |  |  |
| 333 | **unknown** | `test_neg_inf_times_zero` |  |  |
| 337 | **unknown** | `test_normal_mult` |  |  |
| 341 | **unknown** | `test_inf_times_positive` |  |  |
| 345 | **unknown** | `test_neg_inf_times_positive` |  |  |
| 353 | **unknown** | `test_nan_lo_rejected` |  |  |
| 362 | **unknown** | `test_nan_hi_rejected` |  |  |
| 370 | **unknown** | `test_both_nan_rejected` |  |  |
| 378 | **unknown** | `test_normal_still_works` |  |  |
| 382 | **unknown** | `test_inf_bounds_still_work` |  |  |
| 390 | **unknown** | `test_zero_times_infinite_domain` |  |  |
| 399 | **unknown** | `test_infinite_times_zero` |  |  |
| 408 | **unknown** | `test_zero_span_times_infinite` |  |  |
| 419 | **unknown** | `test_normal_mult` |  |  |
| 429 | **infra** | `test_zero_coeff_infinite_domain` |  | Trail, Var, deref |
| 455 | **infra** | `test_all_infinite_domains` |  | Trail, Var |
| 466 | **infra** | `test_zero_coeff_narrows_nonzero` |  | Trail, Var, deref |
| 488 | **infra** | `test_all_infinite` |  | Trail, Var |
| 499 | **infra** | `test_one_bounded_one_infinite` |  | Trail, Var |

</details>

<details><summary><code>tests/test_clpz3.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 36 | **infra** | `test_create_state` |  | Trail |
| 43 | **infra** | `test_same_state_same_trail` |  | Trail |
| 50 | **infra** | `test_different_trails_different_states` |  | Trail |
| 57 | **infra** | `test_state_has_empty_maps` |  | Trail |
| 64 | **infra** | `test_counter_starts_at_zero` |  | Trail |
| 70 | **infra** | `test_empty_solver_is_sat` |  | Trail |
| 76 | **infra** | `test_gc_cleanup` |  | Trail |
| 94 | **infra** | `test_register_int_var` |  | Trail, Var |
| 101 | **infra** | `test_register_bool_var` |  | Trail, Var |
| 108 | **infra** | `test_register_real_var` |  | Trail, Var |
| 115 | **infra** | `test_same_var_returns_same_constant` |  | Trail, Var |
| 123 | **infra** | `test_different_vars_different_constants` |  | Trail, Var |
| 132 | **infra** | `test_var_map_populated` |  | Trail, Var |
| 140 | **infra** | `test_rev_map_populated` |  | Trail, Var |
| 148 | **infra** | `test_attvar_attribute_stored` |  | Trail, Var |
| 159 | **infra** | `test_ground_var_raises` |  | Trail, Var, unify |
| 167 | **infra** | `test_sort_mismatch_raises` |  | Trail, Var |
| 175 | **infra** | `test_unique_names` |  | Trail, Var |
| 184 | **infra** | `test_counter_increments` |  | Trail, Var |
| 202 | **infra** | `test_int_literal` |  | Trail |
| 209 | **infra** | `test_zero` |  | Trail |
| 216 | **infra** | `test_negative_int` |  | Trail |
| 223 | **infra** | `test_large_int` |  | Trail |
| 231 | **infra** | `test_bool_true` |  | Trail |
| 237 | **infra** | `test_bool_false` |  | Trail |
| 243 | **infra** | `test_bool_before_int` |  | Trail |
| 250 | **infra** | `test_float_literal` |  | Trail |
| 256 | **infra** | `test_fraction_literal` |  | Trail |
| 264 | **infra** | `test_registered_var_lookup` |  | Trail, Var |
| 272 | **infra** | `test_unregistered_var_with_default_sort` |  | Trail, Var |
| 282 | **infra** | `test_unregistered_var_no_sort_raises` |  | Trail, Var |
| 289 | **infra** | `test_bound_var_translates_value` |  | Trail, Var, unify |
| 301 | **infra** | `test_addition` |  | Add, Trail, Var |
| 312 | **infra** | `test_subtraction` |  | Sub, Trail, Var |
| 322 | **infra** | `test_multiplication` |  | Mult, Trail, Var |
| 331 | **infra** | `test_negate` |  | Negate, Trail, Var |
| 340 | **infra** | `test_nested_arithmetic` |  | Add, Mult, Trail, Var |
| 353 | **infra** | `test_arith_eq_gives_bool` |  | Trail, Var |
| 362 | **infra** | `test_arith_neq` |  | Trail, Var |
| 371 | **infra** | `test_lt` |  | Lt, Trail, Var |
| 380 | **infra** | `test_lte` |  | LtE, Trail, Var |
| 389 | **infra** | `test_gt` |  | Gt, Trail, Var |
| 398 | **infra** | `test_gte` |  | GtE, Trail, Var |
| 409 | **infra** | `test_and` |  | And, Trail, Var |
| 419 | **infra** | `test_or` |  | Or, Trail, Var |
| 429 | **infra** | `test_not` |  | Not, Trail, Var |
| 438 | **infra** | `test_bitand` |  | Trail, Var |
| 448 | **infra** | `test_bitor` |  | Trail, Var |
| 458 | **infra** | `test_bitxor` |  | Trail, Var |
| 468 | **infra** | `test_invert` |  | Trail, Var |
| 477 | **infra** | `test_unknown_type_raises` |  | Trail |
| 493 | **unknown** | `test_int_value` |  |  |
| 498 | **unknown** | `test_int_zero` |  |  |
| 502 | **unknown** | `test_int_negative` |  |  |
| 506 | **unknown** | `test_large_int` |  |  |
| 511 | **unknown** | `test_bool_true` |  |  |
| 515 | **unknown** | `test_bool_false` |  |  |
| 519 | **unknown** | `test_bool_result_is_int` |  |  |
| 526 | **unknown** | `test_rational_exact` |  |  |
| 532 | **unknown** | `test_rational_whole` |  |  |
| 538 | **unknown** | `test_rational_half` |  |  |
| 543 | **unknown** | `test_model_int_value` |  |  |
| 559 | **infra** | `test_z3_push_increments_scopes` |  | Trail |
| 572 | **infra** | `test_z3_push_pop_retracts_constraint` |  | Trail |
| 589 | **infra** | `test_nested_push_pop` |  | Trail |
| 610 | **infra** | `test_push_interleaved_with_clausal_bindings` |  | Trail, Var, deref, unify |
| 630 | **infra** | `test_z3_add_lazy` |  | Trail |
| 644 | **infra** | `test_multiple_trail_pops` |  | Trail |
| 659 | **infra** | `test_push_then_constraint_then_backtrack_and_re_add` |  | Trail |
| 687 | **unknown** | `test_z3_state_requires_z3` |  |  |

</details>

<details><summary><code>tests/test_clpz3_bool.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 30 | **infra** | `test_bool_true` |  | Trail |
| 36 | **infra** | `test_bool_false` |  | Trail |
| 42 | **infra** | `test_int_one_is_true` |  | Trail |
| 49 | **infra** | `test_int_zero_is_false` |  | Trail |
| 56 | **infra** | `test_var_gets_boolsort` |  | Trail, Var |
| 63 | **infra** | `test_bitand` |  | Trail, Var |
| 70 | **infra** | `test_bitor` |  | Trail, Var |
| 77 | **infra** | `test_bitxor` |  | Trail, Var |
| 84 | **infra** | `test_invert` |  | Trail, Var |
| 91 | **infra** | `test_booleq` |  | Trail, Var |
| 98 | **infra** | `test_boolimpl` |  | Trail, Var |
| 105 | **infra** | `test_nested` |  | Trail, Var |
| 114 | **infra** | `test_bound_var_uses_value` |  | Trail, Var, unify |
| 123 | **infra** | `test_unknown_type_raises` |  | Trail |
| 135 | **infra** | `test_simple_var` |  | Trail, Var, deref |
| 147 | **infra**† | `test_and` |  | Trail, Var, deref |
| 157 | **infra** | `test_contradiction_lazy` |  | Trail, Var |
| 165 | **infra** | `test_ground_true` |  | Trail |
| 171 | **infra** | `test_ground_false_makes_unsat` |  | Trail |
| 177 | **infra** | `test_booleq` |  | Trail, Var, deref |
| 188 | **infra** | `test_boolimpl` |  | Trail, Var, deref |
| 206 | **infra** | `test_tautology` |  | Trail, Var, deref |
| 214 | **infra** | `test_contradiction` |  | Trail, Var, deref |
| 222 | **infra** | `test_indeterminate_fails` |  | Trail, Var, deref |
| 230 | **infra** | `test_forced_true_by_constraint` |  | Trail, Var, deref |
| 240 | **infra** | `test_forced_false_by_constraint` |  | Trail, Var, deref |
| 250 | **infra** | `test_does_not_modify_solver` |  | Trail, Var |
| 261 | **infra** | `test_t_already_bound_wrong` |  | Trail, Var, unify |
| 277 | **infra** | `test_or_two_vars` |  | Trail, Var, deref |
| 286 | **infra** | `test_and_two_vars` |  | Trail, Var, deref |
| 295 | **infra** | `test_tautology_count` |  | Trail, Var, deref |
| 304 | **infra** | `test_contradiction_count` |  | Trail, Var, deref |
| 313 | **infra** | `test_does_not_modify_solver` |  | Trail, Var |
| 324 | **infra** | `test_n_already_bound_correct` |  | Trail, Var, unify |
| 333 | **infra** | `test_n_already_bound_wrong` |  | Trail, Var, unify |
| 342 | **infra** | `test_counts_within_existing_constraint_context` |  | Trail, Var, deref |
| 363 | **infra** | `test_single_var_all_assignments` |  | Trail, Var, deref |
| 372 | **infra** | `test_two_vars_all_assignments` |  | Trail, Var, deref |
| 382 | **infra**† | `test_with_sat_constraint` |  | Trail, Var, deref |
| 393 | **infra** | `test_empty_list` |  | Trail |
| 398 | **infra** | `test_all_ground` |  | Trail |
| 403 | **infra** | `test_vars_unbound_after_exhaustion` |  | Trail, Var, deref |
| 411 | **infra** | `test_invalid_ground_value_raises` |  | Trail |
| 417 | **infra** | `test_unregistered_var_gets_boolsort` |  | Trail, Var, deref |
| 435 | **infra** | `test_at_most_one` |  | Trail, Var, deref |
| 446 | **infra** | `test_at_most_zero` |  | Trail, Var, deref |
| 457 | **infra** | `test_at_least_two` |  | Trail, Var, deref |
| 468 | **infra** | `test_exactly_one` |  | Trail, Var, deref |
| 479 | **infra** | `test_exactly_two` |  | Trail, Var, deref |
| 490 | **infra** | `test_at_most_with_ground` |  | Trail, Var, deref |
| 510 | **infra** | `test_sat_z3_undone_on_undo` |  | Trail, Var |
| 525 | **infra** | `test_label_bool_blocking_retracted` |  | Trail, Var, deref |

</details>

<details><summary><code>tests/test_clpz3_bv.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 30 | **infra** | `test_registers_bvsortt` |  | Trail, Var |
| 38 | **infra** | `test_width_32` |  | Trail, Var |
| 46 | **infra** | `test_list_of_vars` |  | Trail, Var |
| 55 | **infra** | `test_ground_int_passes` |  | Trail |
| 60 | **infra** | `test_wrong_type_raises` |  | Trail |
| 68 | **infra** | `test_unconstrained_8bit_all_values` |  | Trail, Var, deref |
| 80 | **infra** | `test_all_ground_yields_one` |  | Trail |
| 85 | **infra** | `test_unregistered_var_raises` |  | Trail, Var |
| 92 | **infra** | `test_vars_unbound_after` |  | Trail, Var, deref |
| 104 | **infra** | `test_add_no_overflow` |  | Trail, Var, deref |
| 117 | **infra** | `test_add_wraparound` |  | Trail, Var, deref |
| 131 | **infra** | `test_sub` |  | Trail, Var, deref |
| 143 | **infra** | `test_mul` |  | Trail, Var, deref |
| 155 | **infra** | `test_udiv` |  | Trail, Var, deref |
| 167 | **infra** | `test_urem` |  | Trail, Var, deref |
| 179 | **infra** | `test_sdiv` |  | Trail, Var, deref |
| 192 | **infra** | `test_srem` |  | Trail, Var, deref |
| 207 | **infra** | `test_and` |  | Trail, Var, deref |
| 219 | **infra** | `test_or` |  | Trail, Var, deref |
| 231 | **infra** | `test_xor` |  | Trail, Var, deref |
| 243 | **infra** | `test_not` |  | Trail, Var, deref |
| 258 | **infra** | `test_shl` |  | Trail, Var, deref |
| 270 | **infra** | `test_lshr` |  | Trail, Var, deref |
| 282 | **infra** | `test_ashr_positive` |  | Trail, Var, deref |
| 295 | **infra** | `test_ashr_negative` |  | Trail, Var, deref |
| 310 | **infra** | `test_bv_eq_constrain` |  | Trail, Var, deref |
| 322 | **infra** | `test_bv_ne` |  | Trail, Var, deref |
| 333 | **infra** | `test_bv_ult_unsigned` |  | Trail, Var |
| 345 | **infra** | `test_bv_slt_signed` |  | Trail, Var |
| 356 | **infra** | `test_bv_ult_vs_slt_differ` |  | Trail, Var |
| 375 | **infra** | `test_bv_sle` |  | Trail, Var |
| 386 | **infra** | `test_bv_sge` |  | Trail, Var |
| 397 | **infra** | `test_bv_ule` |  | Trail, Var |
| 408 | **infra** | `test_bv_ule_fails` |  | Trail, Var |
| 419 | **infra** | `test_bv_uge` |  | Trail, Var |
| 432 | **infra** | `test_extract_upper_nibble` |  | Trail, Var, deref |
| 445 | **infra** | `test_extract_lower_nibble` |  | Trail, Var, deref |
| 457 | **infra** | `test_concat_two_4bit` |  | Trail, Var, deref |
| 471 | **infra** | `test_zext` |  | Trail, Var, deref |
| 484 | **infra** | `test_sext_positive` |  | Trail, Var, deref |
| 497 | **infra** | `test_sext_negative` |  | Trail, Var, deref |
| 512 | **infra** | `test_bv_constraint_retracted_on_undo` |  | Trail, Var, deref |
| 527 | **infra** | `test_z3_try_works_for_bv_comparison` |  | Trail, Var |

</details>

<details><summary><code>tests/test_clpz3_diag.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 28 | **infra** | `test_named_post_succeeds` |  | Gt, Trail, Var |
| 35 | **infra** | `test_named_and_unsat_core` |  | Gt, Lt, Trail, Var, deref |
| 49 | **infra** | `test_satisfiable_no_core` |  | Gt, Trail, Var |
| 58 | **infra** | `test_named_backtrack` |  | Gt, Trail, Var |
| 72 | **infra** | `test_three_constraints_two_conflict` |  | Gt, GtE, Lt, Trail, Var, deref |
| 87 | **infra** | `test_no_named_unsat` |  | Trail, Var, deref |
| 100 | **infra** | `test_minimal_core_strips_redundant` |  | Gt, GtE, Lt, Trail, Var, deref |
| 116 | **infra** | `test_satisfiable_returns_false` |  | Gt, Trail, Var |
| 131 | **infra** | `test_sat` |  | Trail, Var, deref |
| 140 | **infra** | `test_unsat` |  | Trail, Var, deref |
| 156 | **infra** | `test_entailed_by_bounds` |  | GtE, LtE, Trail, Var |
| 164 | **infra** | `test_not_entailed` |  | GtE, Trail, Var |
| 171 | **infra** | `test_entailed_after_equality` |  | Trail, Var |
| 182 | **infra** | `test_disentailed` |  | Lt, Trail, Var |
| 189 | **infra** | `test_not_disentailed` |  | Lt, Trail, Var |
| 202 | **infra** | `test_model_without_binding` |  | Trail, Var, deref |
| 214 | **infra** | `test_model_constrained` |  | Trail, Var, deref |
| 224 | **infra** | `test_model_unsat_fails` |  | Trail, Var |
| 233 | **infra** | `test_model_multiple_vars` |  | Trail, Var, deref |
| 253 | **infra** | `test_simplify_constant` |  | Add, Trail, Var, deref |
| 260 | **infra** | `test_simplify_tautology` |  | Trail, Var, deref |
| 268 | **infra** | `test_simplify_with_variable` |  | Add, Trail, Var, deref |
| 287 | **infra** | `test_dump_assertions` |  | Trail, Var, deref |
| 298 | **infra** | `test_empty_assertions` |  | Trail, Var, deref |
| 312 | **infra** | `test_stats_returns_pairs` |  | Trail, Var, deref |
| 333 | **infra** | `test_set_timeout` |  | Trail |
| 338 | **infra** | `test_set_logic_qf_lia` |  | Trail, Var |
| 346 | **infra** | `test_set_logic_preserves_constraints` |  | Trail, Var, deref |
| 358 | **infra** | `test_set_logic_detects_unsat` |  | Trail, Var |
| 373 | **infra** | `test_find_conflict_with_unsat_core` |  | Gt, Lt, Trail, Var, deref |
| 390 | **infra** | `test_model_then_entailment` |  | Gt, Trail, Var, deref |

</details>

<details><summary><code>tests/test_clpz3_int.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 31 | **infra** | `test_single_var` |  | Trail, Var |
| 37 | **infra** | `test_list_of_vars` |  | Trail, Var |
| 43 | **infra** | `test_ground_in_range` |  | Trail |
| 48 | **infra** | `test_ground_out_of_range` |  | Trail |
| 53 | **infra** | `test_ground_non_int_fails` |  | Trail |
| 58 | **infra** | `test_empty_domain` |  | Trail, Var |
| 64 | **infra** | `test_singleton_domain_binds` |  | Trail, Var, deref |
| 72 | **infra** | `test_singleton_domain_backtracking` |  | Trail, Var, deref |
| 83 | **infra** | `test_narrowing_via_double_declaration` |  | Trail, Var |
| 103 | **infra** | `test_mixed_list_ground_and_var` |  | Trail, Var |
| 111 | **infra** | `test_mixed_list_ground_out_of_range_fails` |  | Trail, Var |
| 117 | **infra** | `test_non_integer_bounds_raise` |  | Trail, Var |
| 124 | **infra** | `test_var_registered_as_intsort` |  | Trail, Var |
| 133 | **infra** | `test_negative_domain` |  | Trail, Var, deref |
| 144 | **infra** | `test_all_negative_domain` |  | Trail, Var, deref |
| 155 | **infra** | `test_crossing_zero_constraint` |  | Add, Trail, Var, deref |
| 168 | **infra** | `test_singleton_already_registered_tightens_z3` |  | Trail, Var, deref |
| 191 | **infra** | `test_basic` |  | Trail, Var |
| 198 | **infra** | `test_with_ground_int` |  | Trail, Var |
| 205 | **infra** | `test_duplicate_grounds_lazy_fail` |  | Trail |
| 212 | **infra** | `test_empty_list` |  | Trail |
| 217 | **infra** | `test_single_element` |  | Trail, Var |
| 224 | **infra** | `test_non_int_non_var_raises` |  | Trail |
| 236 | **infra** | `test_single_var_all_solutions` |  | Trail, Var, deref |
| 246 | **infra** | `test_two_vars_all_different` |  | Trail, Var, deref |
| 257 | **infra** | `test_no_solution` |  | Trail, Var |
| 265 | **infra** | `test_vars_unbound_after_exhaustion` |  | Trail, Var, deref |
| 275 | **infra** | `test_early_termination` |  | Trail, Var, deref |
| 293 | **infra** | `test_all_ground_single_solution` |  | Trail |
| 299 | **infra** | `test_unregistered_var_raises` |  | Trail, Var |
| 307 | **infra** | `test_non_int_non_var_raises` |  | Trail |
| 313 | **infra** | `test_solutions_differ` |  | Trail, Var, deref |
| 330 | **infra** | `test_empty_constraints_sat` |  | Trail |
| 335 | **infra** | `test_consistent_constraints_sat` |  | Trail, Var |
| 342 | **infra** | `test_inconsistent_constraints_unsat` |  | Trail, Var |
| 356 | **infra** | `test_eq_yields_equal_pairs` |  | Trail, Var, deref |
| 366 | **infra** | `test_ne_yields_unequal_pairs` |  | Trail, Var, deref |
| 377 | **infra** | `test_lt` |  | Trail, Var, deref |
| 389 | **infra** | `test_le` |  | Trail, Var, deref |
| 400 | **infra** | `test_gt` |  | Trail, Var, deref |
| 411 | **infra** | `test_ge` |  | Trail, Var, deref |
| 422 | **infra** | `test_eq_with_ground` |  | Trail, Var, deref |
| 434 | **infra** | `test_linear_expression_add` |  | Add, Trail, Var, deref |
| 447 | **infra** | `test_linear_expression_sub` |  | Sub, Trail, Var, deref |
| 460 | **infra** | `test_linear_expression_mult` |  | Mult, Trail, Var, deref |
| 478 | **infra** | `test_trail_undo_retracts_z3_scope` |  | Trail, Var |
| 505 | **infra** | `test_label_blocking_clauses_retracted_on_undo` |  | Trail, Var, deref |
| 532 | **infra** | `test_interleaved_clausal_and_z3` |  | Trail, Var, deref, unify |
| 561 | **infra** | `test_unique_solution` |  | Add, Mult, Trail, Var, deref |

</details>

<details><summary><code>tests/test_clpz3_opt.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 23 | **infra** | `test_soft_post_succeeds` |  | Trail, Var |
| 30 | **infra** | `test_soft_with_group` |  | Trail, Var |
| 41 | **infra** | `test_soft_backtrack` |  | Trail, Var |
| 57 | **infra** | `test_multiple_soft_backtrack_partial` |  | Trail, Var |
| 80 | **infra** | `test_all_soft_satisfiable` |  | GtE, LtE, Trail, Var, deref |
| 92 | **infra** | `test_conflicting_soft` |  | Trail, Var, deref |
| 105 | **infra** | `test_infeasible_returns_false` |  | Trail, Var |
| 115 | **infra** | `test_no_soft_constraints` |  | Trail, Var, deref |
| 131 | **infra** | `test_maximize_simple` |  | Trail, Var, deref |
| 142 | **infra** | `test_minimize_simple` |  | Trail, Var, deref |
| 153 | **infra** | `test_maximize_with_constraint` |  | Add, Trail, Var, deref |
| 167 | **infra** | `test_minimize_with_soft` |  | GtE, Trail, Var, deref |
| 185 | **infra** | `test_infeasible_yields_nothing` |  | Trail, Var |
| 195 | **infra** | `test_invalid_mode_raises` |  | Trail, Var |
| 203 | **infra** | `test_bindings_undone_after_yield` |  | Trail, Var, deref |
| 221 | **infra** | `test_lex_two_objectives` |  | Add, Trail, Var, deref |
| 239 | **infra** | `test_lex_minimize_then_maximize` |  | Add, Trail, Var, deref |
| 257 | **infra** | `test_pareto_multiple_solutions` |  | Add, Trail, Var, deref |
| 277 | **infra** | `test_box_independent` |  | Add, Trail, Var, deref |
| 293 | **infra** | `test_infeasible_yields_nothing` |  | Trail, Var |
| 305 | **infra** | `test_bindings_undone` |  | Trail, Var, deref |
| 321 | **infra** | `test_maximize_z3_includes_soft` |  | LtE, Trail, Var, deref |
| 337 | **infra** | `test_minimize_z3_basic` |  | Trail, Var, deref |
| 352 | **infra** | `test_minimize_makespan` |  | Add, Trail, Var, deref |
| 376 | **infra** | `test_maxsat_scheduling_preferences` |  | GtE, LtE, Trail, Var, deref |
| 397 | **infra** | `test_real_minimize` |  | Trail, Var, deref |
| 406 | **infra** | `test_real_maximize` |  | Trail, Var, deref |

</details>

<details><summary><code>tests/test_clpz3_propagate.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 30 | **infra** | `test_push_pop_trail_sync` |  | Trail, Var, deref, unify |
| 44 | **infra** | `test_nested_push_pop` |  | Trail, Var, deref, unify |
| 66 | **infra** | `test_pop_multiple` |  | Trail, Var, deref, unify |
| 82 | **infra** | `test_pop_zero` |  | Trail, Var, deref, unify |
| 94 | **infra** | `test_push_does_not_bind` |  | Trail, Var, deref |
| 104 | **infra** | `test_scope_marks_stack` |  | Trail |
| 119 | **infra** | `test_fresh_creates_new_trail` |  | Trail |
| 127 | **infra** | `test_fresh_shares_var_map` |  | Trail |
| 137 | **infra** | `test_fresh_inherits_goals` |  | Trail |
| 150 | **infra** | `test_fresh_push_pop_independent` |  | Trail, Var, deref, unify |
| 175 | **infra** | `test_basic_table` |  | Trail, Var, deref |
| 187 | **infra** | `test_empty_table_fails` |  | Trail, Var |
| 196 | **infra** | `test_table_with_other_constraints` |  | Trail, Var, deref |
| 209 | **infra** | `test_single_row_table` |  | Trail, Var, deref |
| 221 | **infra** | `test_table_single_var` |  | Trail, Var, deref |
| 233 | **infra** | `test_table_no_match_in_domain` |  | Trail, Var |
| 242 | **infra** | `test_table_with_ground_var` |  | Trail, Var, deref |
| 255 | **infra** | `test_table_backtracking` |  | Trail, Var, deref |
| 276 | **infra** | `test_table_length_mismatch_raises` |  | Trail, Var |
| 291 | **infra** | `test_step_generator_in_propagator_context` |  | Trail, Var, deref, unify |
| 310 | **infra** | `test_inner_trampoline_bindings_undone_by_pop` |  | Trail, Var, deref, unify |
| 333 | **infra** | `test_inner_trampoline_multiple_bindings` |  | Trail, Var, deref, unify |

</details>

<details><summary><code>tests/test_clpz3_real.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 31 | **infra** | `test_unbounded_var` |  | Trail, Var |
| 39 | **infra** | `test_bounded_var` |  | Trail, Var |
| 46 | **infra** | `test_fraction_bounds` |  | Trail, Var |
| 53 | **infra** | `test_float_bounds` |  | Trail, Var |
| 60 | **infra** | `test_negative_bounds` |  | Trail, Var |
| 67 | **infra** | `test_tight_bounds_feasible` |  | Trail, Var, deref |
| 78 | **infra** | `test_tight_bounds_infeasible` |  | Trail, Var |
| 86 | **infra** | `test_ground_in_range` |  | Trail |
| 93 | **infra** | `test_ground_out_of_range` |  | Trail |
| 99 | **infra** | `test_list_of_vars` |  | Trail, Var |
| 108 | **infra** | `test_backtracking_retracts_bounds` |  | Trail, Var |
| 136 | **infra** | `test_eq` |  | Trail, Var, deref |
| 148 | **infra** | `test_ne` |  | Trail, Var |
| 157 | **infra** | `test_lt` |  | Trail, Var, deref |
| 169 | **infra** | `test_le` |  | Trail, Var, deref |
| 181 | **infra** | `test_gt` |  | Trail, Var, deref |
| 193 | **infra** | `test_ge` |  | Trail, Var, deref |
| 205 | **infra** | `test_two_var_eq` |  | Add, Trail, Var, deref |
| 219 | **infra** | `test_unsatisfiable` |  | Trail, Var |
| 227 | **infra** | `test_backtracking_retracts_constraint` |  | Trail, Var, deref |
| 251 | **infra** | `test_single_var_yields_one` |  | Trail, Var, deref |
| 264 | **infra** | `test_infeasible_yields_none` |  | Trail, Var |
| 272 | **infra** | `test_all_ground_yields_one` |  | Trail |
| 277 | **infra** | `test_vars_unbound_after` |  | Trail, Var, deref |
| 287 | **infra** | `test_unregistered_var_raises` |  | Trail, Var |
| 300 | **infra** | `test_maximize_bounded` |  | Trail, Var, deref |
| 309 | **infra** | `test_minimize_bounded` |  | Trail, Var, deref |
| 318 | **infra** | `test_maximize_lp` |  | Add, Mult, Trail, Var, deref |
| 337 | **infra** | `test_minimize_lp` |  | Add, Trail, Var, deref |
| 347 | **infra** | `test_infeasible_maximize_fails` |  | Trail, Var |
| 356 | **infra** | `test_infeasible_minimize_fails` |  | Trail, Var |
| 365 | **infra** | `test_maximize_does_not_commit` |  | Trail, Var |
| 377 | **infra** | `test_result_unifies` |  | Trail, Var, unify |
| 387 | **infra** | `test_result_wrong_value_fails` |  | Trail, Var, unify |
| 403 | **infra** | `test_entailed_upper_bound` |  | LtE, Trail, Var |
| 411 | **infra** | `test_entailed_exact` |  | LtE, Trail, Var |
| 419 | **infra** | `test_not_entailed_indeterminate` |  | Lt, Trail, Var |
| 427 | **infra** | `test_entailed_equality` |  | Trail, Var |
| 436 | **infra** | `test_not_entailed_unconstrained` |  | Lt, Trail, Var |
| 444 | **infra** | `test_entailed_does_not_modify_solver` |  | LtE, Trail, Var |
| 460 | **infra** | `test_sup` |  | Trail, Var, deref |
| 469 | **infra** | `test_inf` |  | Trail, Var, deref |
| 478 | **infra** | `test_sup_with_constraints` |  | Trail, Var, deref |
| 494 | **infra** | `test_quadratic_eq` |  | Mult, Trail, Var, deref |
| 508 | **infra** | `test_circle_constraint` |  | Add, Mult, Trail, Var, deref |
| 530 | **infra** | `test_lp_matches_clpq` |  | Add, Mult, Trail, Var, deref |
| 559 | **infra** | `test_minimize_matches_clpq` |  | Trail, Var, deref |

</details>

<details><summary><code>tests/test_clpz3_theories.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 32 | **infra** | `test_declare_array` |  | Trail, Var |
| 40 | **infra** | `test_store_then_select_same_index` |  | Trail, Var, deref |
| 57 | **infra** | `test_store_then_select_different_index` |  | Trail, Var |
| 72 | **infra** | `test_two_stores_same_index_last_wins` |  | Trail, Var, deref |
| 87 | **infra** | `test_const_array` |  | Trail, Var, deref |
| 100 | **infra** | `test_ground_non_var_raises` |  | Trail |
| 112 | **infra** | `test_declare_set` |  | Trail, Var |
| 126 | **infra** | `test_member_after_add` |  | Trail, Var |
| 135 | **infra** | `test_not_member_of_empty` |  | Trail |
| 143 | **infra** | `test_subset` |  | Trail, Var |
| 153 | **infra** | `test_not_subset` |  | Trail, Var |
| 163 | **infra** | `test_union` |  | Trail, Var |
| 177 | **infra** | `test_intersect_disjoint` |  | Trail, Var |
| 190 | **infra** | `test_set_not_member` |  | Trail |
| 203 | **infra** | `test_declare_string` |  | Trail, Var |
| 211 | **infra** | `test_length_constraint` |  | Trail, Var, deref |
| 224 | **infra** | `test_contains_hello` |  | Trail, Var, deref |
| 238 | **infra** | `test_concat_constraint` |  | Trail, Var, deref |
| 259 | **infra** | `test_regex_digits_only` |  | Trail, Var, deref |
| 276 | **infra** | `test_unsatisfiable_string` |  | Trail, Var |
| 286 | **infra** | `test_ground_var_yields_immediately` |  | Trail |
| 291 | **infra** | `test_clausal_to_z3_handles_str` |  | Trail |
| 306 | **infra** | `test_declare_function` |  | Trail, Var, deref |
| 316 | **infra** | `test_apply_function` |  | Trail, Var, deref |
| 332 | **infra** | `test_two_calls_same_arg_equal` |  | Trail, Var |
| 346 | **infra** | `test_two_calls_different_args_independent` |  | Trail, Var |
| 359 | **infra** | `test_non_function_var_raises` |  | Trail, Var |
| 372 | **infra** | `test_forall_tautology` |  | Trail |
| 379 | **infra** | `test_forall_contradiction` |  | Trail |
| 386 | **infra** | `test_exists_simple` |  | Trail |
| 393 | **infra** | `test_exists_impossible` |  | Trail |
| 400 | **infra** | `test_forall_with_function` |  | Trail |
| 408 | **infra** | `test_backtracking_retracts_quantifier` |  | Trail |
| 423 | **infra** | `test_declare_enum` |  | Trail |
| 436 | **infra** | `test_declare_pair` |  | Trail |
| 445 | **infra** | `test_enum_satisfiable` |  | Trail |
| 457 | **infra** | `test_recursive_datatype` |  | Trail |
| 475 | **infra** | `test_on_fixed_records_assignment` |  | Trail, Var |

</details>

<details><summary><code>tests/test_coroutining.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 74 | **mixed** | `test_call_nth_basic` | solve | Call, LoadName, Module, Trail, Var |
| 82 | **mixed** | `test_call_nth_first` | solve | Call, LoadName, Module, Trail, Var |
| 90 | **mixed** | `test_call_nth_last` | solve | Call, LoadName, Module, Trail, Var |
| 98 | **mixed** | `test_call_nth_too_few` | solve | Call, LoadName, Module, Trail, Var |
| 106 | **mixed** | `test_call_nth_n_is_var` | solve | And, Call, LoadName, Module, Trail, Var |
| 119 | **mixed** | `test_call_nth_zero_raises` | solve | Call, LoadName, Module, Trail, Var |
| 127 | **mixed** | `test_call_nth_negative_raises` | solve | Call, LoadName, Module, Trail, Var |
| 135 | **mixed** | `test_call_nth_non_integer_raises` | solve | Call, LoadName, Module, Trail, Var |
| 143 | **mixed** | `test_call_nth_fail_goal` | solve | Call, LoadName, Module, Trail |
| 150 | **mixed** | `test_call_nth_single_solution` | solve | Call, LoadName, Module, Trail, Var |
| 163 | **mixed** | `test_count_all_basic` | solve | Call, LoadName, Module, Trail, Var |
| 172 | **mixed** | `test_count_all_empty` | solve | Call, LoadName, Module, Trail, Var |
| 180 | **mixed** | `test_count_all_between` | solve | Call, LoadName, Module, Trail, Var |
| 189 | **mixed** | `test_count_all_already_bound_correct` | solve | Call, LoadName, Module, Trail, Var |
| 197 | **mixed** | `test_count_all_already_bound_wrong` | solve | Call, LoadName, Module, Trail, Var |
| 205 | **mixed** | `test_count_all_with_filter` | solve | And, Call, Gt, LoadName, Module, Trail, Var |
| 218 | **mixed** | `test_count_all_no_side_effects` | solve | Call, LoadName, Module, Trail, Var, deref |
| 236 | **mixed** | `test_scc_basic` | solve | Call, LoadName, Module, Trail, Var |
| 249 | **mixed** | `test_scc_call_succeeds_cleanup_runs` | solve | Call, LoadName, Module, Trail, Var, deref |
| 272 | **mixed** | `test_scc_call_fails_cleanup_runs` | solve | Call, LoadName, Module, Trail, Var |
| 284 | **mixed** | `test_scc_call_throws_cleanup_runs` | solve | Call, Compound, LoadName, Module, Trail, Var |
| 300 | **mixed** | `test_scc_setup_fails_no_cleanup` | solve | Call, LoadName, Module, Trail, Var |
| 317 | **mixed** | `test_call_cleanup_basic` | solve | Call, LoadName, Module, Trail |
| 324 | **mixed** | `test_call_cleanup_call_fails` | solve | Call, LoadName, Module, Trail |
| 331 | **mixed** | `test_call_cleanup_call_throws` | solve | Call, Compound, LoadName, Module, Trail |
| 341 | **mixed** | `test_call_cleanup_with_solutions` | solve | Call, LoadName, Module, Trail, Var |
| 363 | **mixed** | `test_freeze_already_bound` | solve | And, Call, LoadName, Module, Trail, Var |
| 376 | **mixed** | `test_freeze_then_bind` | solve | And, Call, LoadName, Module, Trail, Var |
| 389 | **mixed** | `test_freeze_goal_success` | solve | And, Call, Gt, LoadName, Module, Trail, Var |
| 401 | **mixed** | `test_freeze_goal_failure` | solve | And, Call, Gt, LoadName, Module, Trail, Var |
| 413 | **mixed** | `test_freeze_multiple_on_same_var` | solve | And, Call, LoadName, Module, Trail, Var, deref |
| 433 | **mixed** | `test_freeze_on_bound_var_immediate` | solve | And, Call, LoadName, Module, Trail, Var |
| 446 | **mixed** | `test_freeze_backtrack_removes_attr` | solve | And, Call, Gt, LoadName, Module, Or, Trail, Var |
| 484 | **mixed** | `test_when_is_bound_already` | solve | And, Call, LoadName, Module, Trail, Var |
| 496 | **mixed** | `test_when_is_bound_deferred` | solve | And, Call, LoadName, Module, Trail, Var |
| 508 | **mixed** | `test_when_conjunction` | solve | And, Call, LoadName, Module, Trail, Var |
| 526 | **mixed** | `test_when_conjunction_partial` | solve | And, Call, LoadName, Module, Trail, Var, deref |
| 548 | **mixed** | `test_when_is_ground_already` | solve | And, Call, LoadName, Module, Trail, Var |
| 560 | **mixed** | `test_when_is_ground_deferred` | solve | And, Call, LoadName, Module, Trail, Var |
| 572 | **mixed** | `test_when_is_ground_nested` | solve | And, Call, LoadName, Module, Trail, Var |
| 589 | **mixed** | `test_when_goal_failure` | solve | And, Call, Gt, LoadName, Module, Trail, Var |
| 619 | **mixed** | `test_find_all_call_nth` | solve | Call, LoadName, Module, Trail, Var |
| 632 | **mixed** | `test_find_all_count_all` | solve | Call, LoadName, Module, Trail, Var |
| 646 | **mixed** | `test_once_call_nth` | solve | Call, LoadName, Module, Trail, Var |
| 654 | **mixed** | `test_once_count_all` | solve | Call, LoadName, Module, Trail, Var |
| 663 | **mixed** | `test_catch_call_nth_type_error` | solve | Call, LoadName, Module, Trail, Var |
| 676 | **mixed** | `test_call_nth_inside_freeze` | solve | And, Call, LoadName, Module, Trail, Var |
| 688 | **mixed** | `test_scc_inside_find_all` | solve | Call, LoadName, Module, Trail, Var |
| 698 | **mixed** | `test_freeze_inside_find_all` | solve | And, Call, LoadName, Module, Trail, Var |
| 712 | **mixed** | `test_count_all_inside_count_all` | solve | Call, LoadName, Module, Trail, Var |
| 725 | **mixed** | `test_call_cleanup_inside_once` | solve | Call, LoadName, Module, Trail, Var |

</details>

<details><summary><code>tests/test_global_constraints.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 30 | **infra** | `test_no_overlap_two_tasks` |  | Trail, Var |
| 47 | **infra** | `test_overlapping_tasks_within_capacity` |  | Trail, Var |
| 62 | **infra** | `test_three_tasks_propagation` |  | Trail, Var, deref |
| 79 | **infra** | `test_infeasible` |  | Trail, Var |
| 97 | **infra** | `test_empty_task_list` |  | Trail |
| 103 | **infra** | `test_single_task` |  | Trail, Var |
| 111 | **infra** | `test_zero_duration_task` |  | Trail, Var |
| 126 | **infra** | `test_basic_cardinality` |  | Trail, Var, deref |
| 146 | **infra** | `test_cardinality_zero_count` |  | Trail, Var |
| 159 | **infra** | `test_cardinality_forced` |  | Trail, Var, deref |
| 170 | **infra** | `test_cardinality_infeasible` |  | Trail, Var |
| 186 | **infra** | `test_increasing_chain` |  | Trail, Var |
| 202 | **infra** | `test_increasing_chain_tight` |  | Trail, Var, deref |
| 213 | **infra** | `test_decreasing_chain` |  | Trail, Var, deref |
| 224 | **infra** | `test_chain_single_element` |  | Trail, Var |
| 232 | **infra** | `test_chain_le` |  | Trail, Var, deref |
| 253 | **infra** | `test_basic_table` |  | Trail, Var, deref |
| 265 | **infra** | `test_table_propagation` |  | Trail, Var, deref |
| 275 | **infra** | `test_table_no_match_fails` |  | Trail, Var |
| 284 | **infra** | `test_empty_relation_fails` |  | Trail, Var |
| 292 | **infra** | `test_domain_filtering` |  | Trail, Var |
| 315 | **infra** | `test_ground_less` |  | Trail, Var, deref |
| 323 | **infra** | `test_ground_greater` |  | Trail, Var, deref |
| 331 | **infra** | `test_ground_equal` |  | Trail, Var, deref |
| 339 | **infra** | `test_var_determined_by_domains` |  | Trail, Var, deref |
| 349 | **infra** | `test_order_ground_constrains_vars` |  | Trail, Var |
| 363 | **infra** | `test_undetermined` |  | Trail, Var, deref |
| 379 | **infra** | `test_cumulative_undo` |  | Trail, Var, deref |
| 392 | **infra** | `test_global_cardinality_undo` |  | Trail, Var, deref |
| 404 | **infra** | `test_tuples_in_undo` |  | Trail, Var |
| 418 | **infra** | `test_chain_undo` |  | Trail, Var, deref |

</details>

<details><summary><code>tests/test_reif_builtins.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 31 | **infra** | `test_ground_equal` |  | Trail, Var |
| 40 | **infra** | `test_ground_incompatible` |  | Trail, Var |
| 49 | **infra** | `test_identical_var` |  | Trail, Var |
| 59 | **infra** | `test_undetermined_explores_both` |  | Trail, Var |
| 74 | **infra** | `test_undetermined_two_vars` |  | Trail, Var |
| 88 | **infra** | `test_ground_string_equal` |  | Trail, Var |
| 97 | **infra** | `test_ground_string_different` |  | Trail, Var |
| 106 | **infra** | `test_ground_type_mismatch` |  | Trail, Var |
| 115 | **infra** | `test_t_already_bound_true_matches` |  | Trail |
| 122 | **infra** | `test_t_already_bound_true_mismatch` |  | Trail |
| 129 | **infra** | `test_t_already_bound_false_matches` |  | Trail |
| 136 | **infra** | `test_t_already_bound_false_mismatch` |  | Trail |
| 143 | **infra** | `test_no_side_effects` |  | Trail, Var, deref |
| 155 | **infra** | `test_list_equal` |  | Trail, Var |
| 164 | **infra** | `test_list_different` |  | Trail, Var |
| 173 | **infra** | `test_list_with_var` |  | Trail, Var |
| 197 | **infra** | `test_ground_different` |  | Trail, Var |
| 206 | **infra** | `test_ground_equal` |  | Trail, Var |
| 215 | **infra** | `test_identical_var` |  | Trail, Var |
| 225 | **infra** | `test_undetermined_explores_both` |  | Trail, Var |
| 239 | **infra** | `test_t_already_bound_true_matches` |  | Trail |
| 246 | **infra** | `test_t_already_bound_true_mismatch` |  | Trail |
| 253 | **infra** | `test_no_side_effects` |  | Trail, Var, deref |
| 263 | **infra** | `test_inverse_of_eq` |  | Trail, Var, deref |
| 286 | **unknown** | `test_eq_registered` |  |  |
| 291 | **unknown** | `test_dif_t_registered` |  |  |
| 296 | **infra** | `test_eq_via_get_builtin_dispatch` |  | Database |
| 305 | **infra** | `test_dif_t_via_get_builtin_dispatch` |  | Database |
| 327 | **mixed** | `test_eq_from_clausal_file` | query | Call, LoadName, Var |
| 341 | **mixed** | `test_eq_ground_false_from_clausal` | query | Call, LoadName, Var |
| 354 | **mixed** | `test_eq_undetermined_from_clausal` | query | Call, LoadName, Var |
| 385 | **mixed** | `test_ground_member_true` | query | Call, LoadName, Var |
| 399 | **mixed** | `test_ground_member_false` | query | Call, LoadName, Var |
| 413 | **mixed** | `test_empty_list` | query | Call, LoadName, Var |
| 427 | **mixed** | `test_unbound_element_explores_branches` | query | Call, LoadName, Var |

</details>

<details><summary><code>tests/test_reified_ite.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 41 | **infra** | `test_identical_var` |  | Trail, Var |
| 47 | **infra** | `test_ground_equal_int` |  | Trail |
| 52 | **infra** | `test_ground_equal_str` |  | Trail |
| 57 | **infra** | `test_ground_incompatible_int` |  | Trail |
| 62 | **infra** | `test_ground_incompatible_type` |  | Trail |
| 67 | **infra** | `test_undetermined_var_int` |  | Trail, Var |
| 73 | **infra** | `test_undetermined_int_var` |  | Trail, Var |
| 79 | **infra** | `test_undetermined_two_vars` |  | Trail, Var |
| 86 | **infra** | `test_bound_var_ground_equal` |  | Trail, Var, unify |
| 93 | **infra** | `test_bound_var_ground_inequal` |  | Trail, Var, unify |
| 100 | **infra** | `test_compound_same` |  | Compound, Trail |
| 107 | **infra** | `test_compound_different` |  | Compound, Trail |
| 114 | **infra** | `test_compound_different_functor` |  | Compound, Trail |
| 121 | **infra** | `test_compound_with_var` |  | Compound, Trail, Var |
| 129 | **infra** | `test_predicate_meta_same` |  | PredicateMeta, Trail |
| 139 | **infra** | `test_predicate_meta_different` |  | PredicateMeta, Trail |
| 149 | **infra** | `test_list_same` |  | Trail |
| 154 | **infra** | `test_list_different` |  | Trail |
| 159 | **infra** | `test_list_with_var` |  | Trail, Var |
| 165 | **infra** | `test_no_side_effects` |  | Trail, Var, deref |
| 182 | **infra** | `test_ground_eq_true` |  | Trail |
| 187 | **infra** | `test_ground_eq_false` |  | Trail |
| 192 | **infra** | `test_ground_lt_true` |  | Trail |
| 197 | **infra** | `test_ground_lt_false` |  | Trail |
| 202 | **infra**† | `test_ground_ge_true` |  | Trail |
| 207 | **infra**† | `test_ground_ge_false` |  | Trail |
| 212 | **infra** | `test_undetermined_with_var` |  | Trail, Var |
| 218 | **infra** | `test_undetermined_both_vars` |  | Trail, Var |
| 225 | **infra** | `test_ground_ne_true` |  | Trail |
| 230 | **infra** | `test_ground_ne_false` |  | Trail |
| 235 | **infra** | `test_ground_le_true` |  | Trail |
| 240 | **infra** | `test_ground_le_false` |  | Trail |
| 245 | **infra** | `test_ground_gt_true` |  | Trail |
| 250 | **infra** | `test_ground_gt_false` |  | Trail |
| 255 | **infra**† | `test_ground_ge_true` |  | Trail |
| 260 | **infra**† | `test_ground_ge_false` |  | Trail |
| 265 | **infra** | `test_undetermined_fd_var_with_domain` |  | Trail, Var |
| 273 | **infra** | `test_undetermined_both_fd_vars` |  | Trail, Var |
| 283 | **infra** | `test_bound_fd_var_becomes_ground` |  | Trail, Var, unify |
| 293 | **infra** | `test_no_side_effects` |  | Trail, Var, deref |
| 357 | **infra** | `test_ground_true_simple` |  | Compound, IfExpr, Var |
| 372 | **infra** | `test_ground_false_simple` |  | Compound, IfExpr, Var |
| 387 | **infra** | `test_undetermined_explores_both_simple` |  | Compound, IfExpr, Var |
| 406 | **infra** | `test_ground_true_trampoline` |  | Compound, IfExpr, Var |
| 420 | **infra** | `test_ground_false_trampoline` |  | Compound, IfExpr, Var |
| 434 | **infra** | `test_undetermined_explores_both_trampoline` |  | Compound, IfExpr, Var |
| 466 | **infra** | `test_ground_dif_true` |  | Compound, IfExpr, Var |
| 481 | **infra** | `test_ground_dif_false` |  | Compound, IfExpr, Var |
| 496 | **infra** | `test_undetermined_dif` |  | Compound, IfExpr, Var |
| 555 | **infra** | `test_ground_lt_true` |  | Compound, IfExpr, Lt, Var |
| 570 | **infra** | `test_ground_lt_false` |  | Compound, IfExpr, Lt, Var |
| 585 | **infra** | `test_ground_eq_true` |  | Compound, IfExpr, Var |
| 600 | **infra** | `test_ground_eq_false` |  | Compound, IfExpr, Var |
| 615 | **infra** | `test_ground_ne_true` |  | Compound, IfExpr, Var |
| 630 | **infra** | `test_ground_ne_false` |  | Compound, IfExpr, Var |
| 645 | **infra** | `test_ground_le_true` |  | Compound, IfExpr, LtE, Var |
| 660 | **infra** | `test_ground_le_false` |  | Compound, IfExpr, LtE, Var |
| 675 | **infra** | `test_ground_gt_true` |  | Compound, Gt, IfExpr, Var |
| 690 | **infra** | `test_ground_gt_false` |  | Compound, Gt, IfExpr, Var |
| 705 | **infra**† | `test_ground_ge_true` |  | Compound, GtE, IfExpr, Var |
| 720 | **infra**† | `test_ground_ge_false` |  | Compound, GtE, IfExpr, Var |
| 737 | **infra** | `test_ground_lt_true_trampoline` |  | Compound, IfExpr, Lt, Var |
| 751 | **infra** | `test_ground_lt_false_trampoline` |  | Compound, IfExpr, Lt, Var |
| 765 | **infra** | `test_ground_ge_true_trampoline` |  | Compound, GtE, IfExpr, Var |
| 779 | **infra** | `test_ground_ne_true_trampoline` |  | Compound, IfExpr, Var |
| 795 | **infra** | `test_undetermined_lt_explores_both` |  | Compound, Database, IfExpr, Lt, Trail, Var, compile_predicate, deref |
| 823 | **infra** | `test_undetermined_eq_explores_both` |  | Compound, Database, IfExpr, Trail, Var, compile_predicate, deref |
| 848 | **infra** | `test_undetermined_ge_explores_both_trampoline` |  | Compound, Database, GtE, IfExpr, Trail, Var, compile_predicate_trampoline, deref |
| 884 | **infra** | `test_fd_ite_then_label` |  | Compound, Database, IfExpr, Lt, Trail, Var, compile_predicate, deref |
| 930 | **infra** | `test_nested_fd_ite` |  | Compound, Gt, IfExpr, Lt, Var |
| 989 | **infra** | `test_succeeding_condition_simple` |  | Compound, IfExpr, Var |
| 1011 | **infra** | `test_failing_condition_simple` |  | Compound, IfExpr, Var |
| 1026 | **infra** | `test_succeeding_condition_trampoline` |  | Compound, IfExpr, Var |
| 1040 | **infra** | `test_failing_condition_trampoline` |  | Compound, IfExpr, Var |
| 1069 | **infra** | `test_nested_ite` |  | Compound, IfExpr, Var |
| 1088 | **infra** | `test_nested_ite_inner_false` |  | Compound, IfExpr, Var |
| 1107 | **infra** | `test_ite_preserves_bindings` |  | Compound, IfExpr, Var |
| 1126 | **infra** | `test_ite_with_conjunction_body` |  | And, Compound, IfExpr, Var |
| 1183 | **infra** | `test_multi_solution_runs_then_for_each` |  | Compound, IfExpr, Var |
| 1203 | **infra** | `test_multi_solution_then_for_each_trampoline` |  | Compound, IfExpr, Var |
| 1220 | **infra** | `test_general_ite_preserves_condition_bindings` |  | Compound, IfExpr, Var |
| 1256 | **infra** | `test_undetermined_ite_with_preexisting_dif` |  | Compound, IfExpr, Trail, Var |
| 1281 | **infra** | `test_undetermined_ite_with_dif_still_explores_both_when_compatible` |  | Compound, IfExpr, Trail, Var |
| 1317 | **mixed** | `test_tabled_condition_succeeds` | query | Call, LoadName, Var |
| 1330 | **mixed** | `test_tabled_condition_fails` | query | Call, LoadName, Var |
| 1358 | **mixed** | `test_classify_ground` | query | Call, LoadName, Var |
| 1378 | **mixed** | `test_memberd_ground_deterministic` | query | Call, LoadName |
| 1395 | **mixed** | `test_memberd_ground_absent` | query | Call, LoadName |
| 1407 | **mixed** | `test_memberd_unbound_enumerates` | query | Call, LoadName, Var |
| 1421 | **mixed** | `test_memberd_no_duplicates` | query | Call, LoadName, Var |
| 1481 | **mixed** | `test_once_takes_first_solution_simple` | _once | Call, Compound, LoadName, Var |
| 1492 | **mixed** | `test_once_takes_first_solution_trampoline` | _once | Call, Compound, LoadName, Var |
| 1503 | **mixed** | `test_once_failing_goal_simple` | _once | Call, Compound, LoadName, Var |
| 1517 | **mixed** | `test_once_failing_goal_trampoline` | _once | Call, Compound, LoadName, Var |
| 1531 | **mixed** | `test_once_with_continuation_simple` | _once | Call, Compound, LoadName, Var |
| 1547 | **mixed** | `test_once_with_continuation_trampoline` | _once | Call, Compound, LoadName, Var |
| 1560 | **mixed** | `test_once_preserves_bindings_simple` | _once | Call, Compound, LoadName, Var |
| 1574 | **mixed** | `test_once_preserves_bindings_trampoline` | _once | Call, Compound, LoadName, Var |
| 1587 | **mixed** | `test_once_in_if_condition_simple` | _once | Call, Compound, IfExpr, LoadName, Var |
| 1603 | **mixed** | `test_once_in_if_condition_trampoline` | _once | Call, Compound, IfExpr, LoadName, Var |
| 1622 | **mixed** | `test_once_clausal_import` | query | Call, LoadName, Var |

</details>

### control

<details><summary><code>tests/test_control.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 35 | **mixed** | `test_success_single_solution` | solve | Call, Database, LoadName, Module, Var, deref |
| 46 | **mixed** | `test_success_multiple_solutions` | solve | Call, Database, LoadName, Module, Var, deref |
| 58 | **mixed** | `test_failure_zero_solutions` | solve | Call, Database, LoadName, Module, Var |
| 68 | **mixed** | `test_timing_fields_present` | solve | Call, Database, LoadName, Module |
| 77 | **mixed** | `test_timing_format` | solve | Call, Database, LoadName, Module, Var |
| 85 | **mixed** | `test_solutions_pass_through` | solve | Call, Database, LoadName, Module, Var, deref |
| 98 | **mixed** | `test_nested_time_goal` | solve | Call, Database, LoadName, Module, Var, deref |

</details>

<details><summary><code>tests/test_dcg.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 38 | **mixed** | `test_single_terminal` | call | module_dict |
| 44 | **mixed** | `test_multi_terminal` | call | module_dict |
| 50 | **mixed** | `test_empty_terminal` | call | module_dict |
| 56 | **mixed** | `test_terminal_no_match` | call | module_dict |
| 67 | **mixed** | `test_chained_non_terminals` | call | module_dict |
| 79 | **mixed** | `test_non_terminal_with_args` | call | Var, deref, module_dict |
| 95 | **mixed** | `test_inline_goal_passthrough` | call | Var, deref, module_dict |
| 112 | **mixed** | `test_multiple_inline_goals` | call | Var, deref, module_dict |
| 134 | **mixed** | `test_tuple_conjunction` | call | module_dict |
| 145 | **mixed** | `test_and_conjunction` | call | module_dict |
| 161 | **mixed** | `test_or_branches` | call | module_dict |
| 176 | **mixed** | `test_not_terminal` | call | module_dict |
| 191 | **mixed** | `test_if_then_else_nonterminals` | call | module_dict |
| 214 | **mixed** | `test_look_ahead` | call | Var, deref, module_dict |
| 232 | **mixed** | `test_phrase_2_success` | call | module_dict |
| 239 | **mixed** | `test_phrase_2_fail` | call | module_dict |
| 247 | **mixed** | `test_phrase_3_partial` | call | Var, deref, module_dict |
| 264 | **mixed** | `test_recursive_list` | call | module_dict |
| 275 | **mixed** | `test_recursive_digits` | call | module_dict |
| 302 | **mixed** | `test_greeting` | call | module_dict |
| 308 | **mixed** | `test_noun_phrase` | call | module_dict |
| 315 | **mixed** | `test_sentence` | call | module_dict |
| 327 | **mixed** | `test_digit_with_args` | call | Var, deref, module_dict |
| 336 | **behavior** | `test_valid_sentence_regular_pred` | call |  |
| 345 | **mixed** | `test_look_ahead_pushback` | call | Var, deref, module_dict |
| 355 | **mixed** | `test_not_a` | call | module_dict |
| 375 | **mixed** | `test_state_read` | call | Var, deref, module_dict |
| 390 | **mixed** | `test_state_read_write` | call | Var, deref, module_dict |
| 407 | **mixed** | `test_increment_counter` | call | Var, deref, module_dict |
| 421 | **mixed** | `test_count_three` | call | Var, deref, module_dict |
| 436 | **mixed** | `test_counter_start_nonzero` | call | Var, deref, module_dict |
| 453 | **mixed** | `test_count_leaves_single` | call | Var, deref |
| 470 | **mixed** | `test_count_leaves_two` | call | Var, deref |
| 487 | **mixed** | `test_count_leaves_nested` | call | Var, deref |
| 506 | **mixed** | `test_accumulator_push` | call | Var, deref, module_dict |
| 525 | **mixed** | `test_accumulator_empty` | call | Var, deref, module_dict |
| 545 | **mixed** | `test_state_only_dcg` | call | Var, deref, module_dict |
| 560 | **mixed** | `test_state_chained_operations` | call | Var, deref, module_dict |
| 580 | **mixed** | `test_string_state` | call | Var, deref, module_dict |
| 596 | **mixed** | `test_phrase_with_term_arg` | call | Var, deref |
| 612 | **mixed** | `test_phrase_with_instance_arg` | call | Var, deref |
| 647 | **mixed** | `test_count3` | call | Var, deref |
| 653 | **mixed** | `test_inc_then_double` | call | Var, deref |
| 660 | **mixed** | `test_num_leaves_two` | call | Var, deref |
| 666 | **mixed** | `test_num_leaves_nested` | call | Var, deref |
| 673 | **mixed** | `test_collect_items` | call | Var, deref |
| 679 | **mixed** | `test_collect_items_empty` | call | Var, deref |
| 692 | **mixed** | `test_phrase2_string_match` | call | module_dict |
| 700 | **mixed** | `test_phrase2_string_no_match` | call | module_dict |
| 708 | **mixed** | `test_phrase2_string_empty` | call | module_dict |
| 716 | **mixed** | `test_phrase2_string_multi_terminal` | call | module_dict |
| 725 | **mixed** | `test_phrase3_string_remainder` | call | Var, deref, module_dict |
| 737 | **mixed** | `test_phrase2_chained_nonterminals_string` | call | module_dict |
| 750 | **mixed** | `test_phrase2_recursive_string` | call | module_dict |
| 763 | **mixed** | `test_phrase2_dcg_with_args_string` | call | Var, deref, module_dict |
| 775 | **mixed** | `test_phrase2_inline_goal_string` | call | Var, deref, module_dict |
| 792 | **mixed** | `test_list_input_still_works` | call | module_dict |

</details>

<details><summary><code>tests/test_dif.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 66 | **unknown** | `test_scalar` |  |  |
| 70 | **unknown** | `test_string` |  |  |
| 74 | **infra** | `test_single_var` |  | Var |
| 81 | **infra** | `test_bound_var_not_collected` |  | Trail, Var, unify |
| 88 | **infra** | `test_tuple_with_vars` |  | Var |
| 96 | **infra** | `test_list_with_vars` |  | Var |
| 103 | **infra** | `test_compound_with_vars` |  | Compound, Var |
| 110 | **infra** | `test_nested_structures` |  | Compound, Var |
| 118 | **infra** | `test_dedup_same_var` |  | Var |
| 130 | **infra** | `test_ground_equal_fails` |  | Trail |
| 135 | **infra** | `test_ground_different_succeeds` |  | Trail |
| 140 | **infra** | `test_ground_string_different` |  | Trail |
| 145 | **infra** | `test_ground_string_equal_fails` |  | Trail |
| 150 | **infra** | `test_same_var_fails` |  | Trail, Var |
| 157 | **infra** | `test_one_var_posts_constraint` |  | Trail, Var |
| 167 | **infra** | `test_both_vars_posts_constraint` |  | Trail, Var |
| 176 | **infra** | `test_compound_structurally_different` |  | Compound, Trail |
| 181 | **infra** | `test_compound_structurally_equal_fails` |  | Compound, Trail |
| 192 | **infra** | `test_var_vs_compound_containing_it` |  | Compound, Trail, Var |
| 205 | **infra** | `test_dif_then_same_value_fails` |  | Trail, Var, unify |
| 214 | **infra** | `test_dif_then_different_values_succeeds` |  | Trail, Var, unify |
| 223 | **infra** | `test_dif_var_ground_then_bind_same` |  | Trail, Var, unify |
| 231 | **infra** | `test_dif_var_ground_then_bind_different` |  | Trail, Var, unify |
| 239 | **infra** | `test_multiple_constraints_on_same_var` |  | Trail, Var, unify |
| 260 | **infra** | `test_compound_args_constraint` |  | Compound, Trail, Var, unify |
| 269 | **infra** | `test_compound_args_different_ok` |  | Compound, Trail, Var, unify |
| 278 | **infra** | `test_transitive_via_shared_var` |  | Trail, Var, unify |
| 293 | **infra** | `test_constraint_undone_on_trail_undo` |  | Trail, Var |
| 305 | **infra** | `test_binding_failure_doesnt_corrupt_trail` |  | Trail, Var, deref, unify |
| 322 | **mixed** | `test_is_not_dif_semantics_via_solve` | once | And, Module, Var, deref |
| 339 | **mixed** | `test_is_not_dif_violation_via_solve` | once | And, Module, Var |
| 354 | **mixed** | `test_is_not_ground_different` | once | Module |
| 361 | **mixed** | `test_is_not_ground_same` | once | Module |
| 368 | **mixed** | `test_is_not_same_var` | once | Module, Var |
| 376 | **mixed** | `test_not_unify_still_works_as_immediate` | once | Module, Not, Var |
| 387 | **mixed** | `test_is_not_with_multiple_constraints` | once | And, Module, Var, deref |
| 403 | **mixed** | `test_is_not_with_multiple_constraints_violation` | once | And, Module, Var |
| 424 | **mixed** | `test_dif_builtin_succeeds_different` | once | Call, LoadName, Module |
| 432 | **mixed** | `test_dif_builtin_fails_equal` | once | Call, LoadName, Module |
| 440 | **mixed** | `test_dif_builtin_with_vars` | once | And, Call, LoadName, Module, Var |
| 455 | **mixed** | `test_dif_builtin_violation` | once | And, Call, LoadName, Module, Var |
| 476 | **mixed** | `test_clausal_file_with_dif` | load_clausal_module, once | Call, LoadName, Var, deref |

</details>

<details><summary><code>tests/test_edcg.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 47 | **unknown** | `test_edcg_acc_parses` |  |  |
| 57 | **unknown** | `test_edcg_pass_parses` |  |  |
| 67 | **unknown** | `test_edcg_pred_parses` |  |  |
| 78 | **unknown** | `test_edcg_pred_with_dcg` |  |  |
| 89 | **unknown** | `test_edcg_pred_with_pass` |  |  |
| 100 | **unknown** | `test_multiple_accumulators` |  |  |
| 116 | **unknown** | `test_edcg_acc_wrong_arg_count` |  |  |
| 122 | **unknown** | `test_edcg_pred_undeclared_acc` |  |  |
| 128 | **unknown** | `test_edcg_pred_wrong_arity_type` |  |  |
| 145 | **mixed** | `test_simple_counter` | call | Var, deref |
| 162 | **mixed** | `test_counter_start_nonzero` | call | Var, deref |
| 179 | **mixed** | `test_list_accumulator` | call | Var, deref |
| 197 | **mixed** | `test_accumulator_read` | call | Var, deref |
| 214 | **mixed** | `test_custom_joiner_product` | call | Var, deref |
| 239 | **mixed** | `test_counter_and_list` | call | Var, deref |
| 260 | **mixed** | `test_partial_overlap` | call | Var, deref |
| 287 | **mixed** | `test_basic_pass` | call | Var, deref |
| 304 | **mixed** | `test_pass_with_accumulator` | call | Var, deref |
| 327 | **mixed** | `test_counted_parser` | call | Var, deref |
| 355 | **mixed** | `test_disjunction` | call | Trail, Var, deref |
| 373 | **mixed** | `test_inline_goal` | call | Var, deref |
| 395 | **mixed** | `test_len_adder` | call | Var, deref |
| 414 | **mixed** | `test_compiler_pass` | call | Var, deref |
| 454 | **mixed** | `test_counter_fixture` | call | Var, deref |
| 479 | **mixed** | `test_empty_body` | call | Var, deref |
| 494 | **mixed** | `test_recursive_accumulator` | call | Var, deref |
| 511 | **mixed** | `test_multiple_pushes_in_sequence` | call | Var, deref |
| 526 | **mixed** | `test_two_independent_accumulators` | call | Var, deref |

</details>

<details><summary><code>tests/test_exceptions.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 58 | **unknown** | `test_is_exception` |  |  |
| 63 | **infra** | `test_carries_term` |  | Compound |
| 68 | **unknown** | `test_str` |  |  |
| 78 | **mixed** | `test_throw_raises_logic_exception` | solve | Call, LoadName, Module, Trail |
| 86 | **mixed** | `test_throw_with_compound_term` | solve | Call, Compound, LoadName, Module, Trail |
| 95 | **mixed** | `test_throw_with_integer` | solve | Call, LoadName, Module, Trail |
| 103 | **mixed** | `test_throw_with_string_var` | solve | And, Call, LoadName, Module, Trail, Var |
| 126 | **mixed** | `test_catch_no_exception` | solve | Call, LoadName, Module, Trail, Var |
| 138 | **mixed** | `test_catch_catches_throw` | solve | Call, LoadName, Module, Trail, Var |
| 151 | **mixed** | `test_catch_specific_catcher` | solve | Call, LoadName, Module, Trail, Var |
| 163 | **mixed** | `test_catch_mismatch_reraises` | solve | Call, LoadName, Module, Trail, Var |
| 176 | **mixed** | `test_catch_variable_catcher` | solve | Call, LoadName, Module, Trail, Var |
| 189 | **mixed** | `test_nested_catch_inner_catches` | solve | Call, LoadName, Module, Trail, Var |
| 206 | **mixed** | `test_nested_catch_inner_misses` | solve | Call, LoadName, Module, Trail, Var |
| 224 | **mixed** | `test_trail_cleanup_on_catch` | solve | And, Call, LoadName, Module, Trail, Var, deref |
| 245 | **mixed** | `test_throw_inside_deeply_nested` | solve | Call, Compound, LoadName, Module, Trail, Var, compile_predicate_trampoline |
| 277 | **mixed** | `test_catch_goal_succeeds_multiple_solutions` | solve | And, Call, LoadName, Module, Trail, Var |
| 298 | **mixed** | `test_halt_0` | solve | Call, LoadName, Module, Trail |
| 306 | **mixed** | `test_halt_1` | solve | Call, LoadName, Module, Trail |
| 319 | **mixed** | `test_python_catches_logic_exception` | solve | Call, LoadName, Module, Trail |
| 329 | **mixed** | `test_logic_exception_is_exception_subclass` | solve | Call, LoadName, Module, Trail |
| 345 | **unknown** | `test_type_error_helper` |  |  |
| 354 | **unknown** | `test_instantiation_error_helper` |  |  |
| 362 | **unknown** | `test_existence_error_helper` |  |  |
| 369 | **unknown** | `test_permission_error_helper` |  |  |
| 388 | **mixed** | `test_throw_inside_findall_propagates` | solve | And, Call, LoadName, Module, Trail, Var |
| 402 | **mixed** | `test_catch_around_findall` | solve | And, Call, LoadName, Module, Trail, Var |

</details>

<details><summary><code>tests/test_higher_order.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 121 | **infra** | `test_all_succeed` |  | Trail, deref |
| 125 | **infra** | `test_one_fails` |  | Trail, deref |
| 129 | **infra** | `test_empty_list` |  | Trail, deref |
| 133 | **infra** | `test_non_list_fails` |  | Trail, deref |
| 137 | **infra** | `test_non_callable_fails` |  | Trail |
| 146 | **infra** | `test_double` |  | Trail, Var, deref, unify |
| 151 | **infra** | `test_empty_list` |  | Trail, Var, deref, unify |
| 156 | **infra** | `test_goal_fails_mid_list` |  | Trail, Var, deref |
| 161 | **infra** | `test_non_list_fails` |  | Trail, Var, deref, unify |
| 171 | **infra** | `test_filter_positive` |  | Trail, Var, deref |
| 176 | **infra** | `test_all_match` |  | Trail, Var, deref |
| 181 | **infra** | `test_none_match` |  | Trail, Var, deref |
| 186 | **infra** | `test_empty_input` |  | Trail, Var, deref |
| 191 | **infra** | `test_even_filter` |  | Trail, Var, deref |
| 201 | **infra** | `test_filter_non_positive` |  | Trail, Var, deref |
| 206 | **infra** | `test_all_match` |  | Trail, Var, deref |
| 211 | **infra** | `test_none_match` |  | Trail, Var, deref |
| 216 | **infra** | `test_empty_input` |  | Trail, Var, deref |
| 243 | **infra** | `test_sum` |  | Trail, Var, deref, unify |
| 247 | **infra** | `test_product` |  | Trail, Var, deref, unify |
| 251 | **infra** | `test_empty_list` |  | Trail, Var, deref, unify |
| 255 | **infra** | `test_goal_fails_mid_fold` |  | Trail, Var, deref |
| 259 | **infra** | `test_non_list_fails` |  | Trail, Var, deref, unify |
| 268 | **mixed** | `test_merge_sort` | solve | Call, LoadName, Module, Trail, Var, deref |
| 275 | **mixed** | `test_get_item` | solve | Call, LoadName, Module, Trail, Var, deref |
| 282 | **mixed** | `test_member_check` | solve | Call, LoadName, Module, Trail |
| 287 | **mixed** | `test_member_check_fail` | solve | Call, LoadName, Module, Trail |
| 292 | **mixed** | `test_unpack` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 308 | **infra** | `test_builtin_to_maplist2` |  | Trail |
| 315 | **infra** | `test_builtin_to_maplist2_fail` |  | Trail |
| 322 | **infra** | `test_builtin_to_maplist3` |  | Trail, Var, deref |
| 330 | **infra** | `test_builtin_to_filter` |  | Trail, Var, deref |
| 338 | **infra** | `test_builtin_to_exclude` |  | Trail, Var, deref |
| 346 | **behavior** | `test_builtin_clausal_fixture` | collect_tests, load_clausal_module, run_test |  |

</details>

<details><summary><code>tests/test_lambdas.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 108 | **infra** | `test_python_lambda_syntax_rejected` |  | TermTransformer, Var, ast, parse |
| 114 | **infra**† | `test_lambda_param_generates_loadname` |  | TermTransformer, Var, ast, parse |
| 121 | **infra**† | `test_lambda_captures_enclosing_var` |  | TermTransformer, Var, ast, parse |
| 130 | **infra**† | `test_lambda_body_only_var_does_not_leak` |  | TermTransformer, ast, parse |
| 140 | **infra** | `test_lambda_captures_multiple_enclosing_vars` |  | TermTransformer, Var, ast, parse |
| 148 | **infra** | `test_nested_lambda_captures_outer` |  | TermTransformer, Var, ast, parse |
| 158 | **infra** | `test_anonymous_underscore_in_lambda` |  | TermTransformer, Var, ast, parse |
| 164 | **infra** | `test_param_refs_are_loadname` |  | TermTransformer, Var, ast, parse |
| 171 | **infra** | `test_nested_lambda_outer_param_is_loadname` |  | TermTransformer, Var, ast, parse |
| 198 | **infra** | `test_compile_lambda_produces_funcdef` |  | Database, Evaluate, LoadName, ast |
| 209 | **infra** | `test_compile_lambda_param_is_func_arg` |  | Database, Evaluate, LoadName |
| 220 | **infra** | `test_compile_lambda_captured_var_not_in_params` |  | Add, Database, Evaluate, LoadName, Var |
| 236 | **infra** | `test_flatten_conjunction` |  | And, Evaluate, Var |
| 246 | **infra** | `test_flatten_single` |  | Evaluate, Var |
| 266 | **infra** | `test_call_goal_1_with_zero_arg_lambda` |  | Trail, unify |
| 282 | **infra** | `test_call_goal_2_with_one_arg_lambda` |  | Trail, Var, deref, unify |
| 300 | **infra** | `test_call_goal_3_with_two_arg_lambda` |  | Trail, Var, deref, unify |
| 318 | **infra** | `test_call_goal_with_failing_lambda` |  | Trail |
| 332 | **infra** | `test_call_goal_with_multi_solution_lambda` |  | Trail, Var, unify |
| 359 | **infra** | `test_lambda_arithmetic_body` |  | Add, Call, Compound, Database, Evaluate, LoadName, Trail, Var, compile_predicate, deref, unify |
| 386 | **infra**† | `test_lambda_captures_enclosing_var` |  | Add, Call, Compound, Database, Evaluate, LoadName, Trail, Var, compile_predicate, deref, unify |
| 413 | **infra** | `test_lambda_with_unification_body` |  | Call, Compound, Database, LoadName, Trail, Var, compile_predicate, deref |
| 436 | **infra** | `test_lambda_body_fails` |  | Call, Compound, Database, LoadName, Trail, compile_predicate |
| 457 | **infra** | `test_lambda_body_conjunction` |  | Add, And, Call, Compound, Database, Evaluate, LoadName, Trail, Var, compile_predicate, deref |
| 503 | **unknown** | `test_lambda_unify_in_clausal_file` |  |  |
| 518 | **unknown** | `test_lambda_captures_head_var_in_clausal` |  |  |
| 533 | **unknown** | `test_lambda_with_conjunction_in_clausal` |  |  |
| 548 | **mixed** | `test_lambda_zero_arg_in_clausal` | query | Call, LoadName, Var |
| 567 | **unknown** | `test_lambda_calls_user_predicate` |  |  |
| 584 | **mixed** | `test_lambda_calls_multi_solution_predicate` | query | Call, LoadName, Var |
| 607 | **unknown** | `test_python_lambda_rejected_in_clausal_file` |  |  |
| 628 | **infra** | `test_single_param_arrow_lambda` |  | TermTransformer, Var, ast, parse |
| 635 | **infra** | `test_two_param_arrow_lambda` |  | TermTransformer, Var, ast, parse |
| 643 | **infra** | `test_zero_param_arrow_lambda` |  | TermTransformer, Var, ast, parse |
| 649 | **infra**† | `test_arrow_lambda_param_generates_loadname` |  | TermTransformer, Var, ast, parse |
| 656 | **infra**† | `test_arrow_lambda_captures_enclosing_var` |  | TermTransformer, Var, ast, parse |
| 665 | **infra**† | `test_arrow_lambda_body_var_does_not_leak` |  | TermTransformer, ast, parse |
| 675 | **infra** | `test_arrow_lambda_walrus_in_body` |  | Evaluate, TermTransformer, Var, ast, parse |
| 682 | **infra** | `test_functor_head_stays_predicate` |  | TermTransformer, Var, ast, parse |
| 700 | **unknown** | `test_arrow_lambda_unify` |  |  |
| 710 | **mixed** | `test_arrow_lambda_arithmetic_in_clausal` | query | Call, LoadName, Var |
| 729 | **mixed** | `test_arrow_lambda_two_params_in_clausal` | query | Call, LoadName, Var |
| 748 | **mixed** | `test_arrow_lambda_zero_arg_in_clausal` | query | Call, LoadName, Var |
| 767 | **mixed** | `test_arrow_lambda_captures_head_var` | query | Call, LoadName, Var |
| 786 | **mixed** | `test_arrow_lambda_conjunction_in_clausal` | query | Call, LoadName, Var |
| 805 | **mixed** | `test_arrow_lambda_calls_user_predicate` | query | Call, LoadName, Var |

</details>

<details><summary><code>tests/test_meta.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 51 | **mixed** | `test_find_all_basic` | solve | Call, LoadName, Module, Trail, Var |
| 64 | **mixed** | `test_find_all_with_filter` | solve | And, Call, Gt, LoadName, Module, Trail, Var |
| 77 | **mixed** | `test_find_all_fail_empty_list` | solve | Call, LoadName, Module, Trail, Var |
| 86 | **mixed** | `test_find_all_template_expression` | solve | And, Call, LoadName, Module, Trail, Var |
| 100 | **mixed** | `test_find_all_no_side_effects` | solve | Call, LoadName, Module, Trail, Var |
| 113 | **mixed** | `test_find_all_nested` | solve | And, Call, LoadName, Module, Trail, Var |
| 142 | **mixed** | `test_bag_of_basic` | solve | Call, LoadName, Module, Trail, Var |
| 155 | **mixed** | `test_bag_of_fails_on_empty` | solve | Call, LoadName, Module, Trail, Var |
| 169 | **mixed** | `test_set_of_dedup` | solve | Call, LoadName, Module, Trail, Var |
| 182 | **mixed** | `test_set_of_fails_on_empty` | solve | Call, LoadName, Module, Trail, Var |
| 191 | **mixed** | `test_set_of_preserves_order` | solve | Call, LoadName, Module, Trail, Var |
| 209 | **mixed** | `test_for_all_succeeds` | solve | Call, Gt, LoadName, Module, Trail, Var |
| 219 | **mixed** | `test_for_all_fails` | solve | Call, Gt, LoadName, Module, Trail, Var |
| 229 | **mixed** | `test_for_all_vacuously_true` | solve | Call, Gt, LoadName, Module, Trail, Var |
| 245 | **mixed** | `test_call_1` | call | Module, Var, deref |
| 254 | **mixed** | `test_call_goal_4` | call | Module |
| 268 | **mixed** | `test_call_alias` | call | Module |
| 281 | **mixed** | `test_call_5` | call | Module |
| 302 | **mixed** | `test_squares` | call | Var |
| 310 | **mixed** | `test_positives` | call | Var |
| 318 | **mixed** | `test_unique_members` | call | Var |
| 326 | **behavior** | `test_all_positive_pass` | call |  |
| 333 | **behavior** | `test_all_positive_fail` | call |  |

</details>

<details><summary><code>tests/test_metainterpreters.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 59 | **mixed** | `test_natnum_binds_variable` | call, load_clausal_module | Var, deref |
| 81 | **mixed** | `test_edge_binds_destination` | call, load_clausal_module | Var, deref |
| 96 | **mixed** | `test_path_binds_destination` | call, load_clausal_module | Var, deref |
| 121 | **mixed** | `test_count_single_fact` | call, load_clausal_module | Var, deref |
| 134 | **mixed** | `test_count_path_transitive` | call, load_clausal_module | Var, deref |
| 153 | **mixed** | `test_depth_0_fails_on_any_goal` | call, load_clausal_module | Var, deref |
| 165 | **mixed** | `test_exact_depth_succeeds` | call, load_clausal_module | Var, deref |
| 187 | **mixed** | `test_finds_path_in_cyclic_graph` | call, load_clausal_module | Var, deref |
| 209 | **mixed** | `test_fact_tree` | call, load_clausal_module | Var, deref |
| 223 | **mixed** | `test_recursive_tree_structure` | call, load_clausal_module | Var, deref |
| 242 | **mixed** | `test_transitive_path_tree` | call, load_clausal_module | Var, deref |

</details>

<details><summary><code>tests/test_predicate_meta.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 29 | **unknown** | `test_functor` |  |  |
| 33 | **unknown** | `test_arity` |  |  |
| 37 | **unknown** | `test_arity_zero` |  |  |
| 41 | **unknown** | `test_arity_three` |  |  |
| 50 | **unknown** | `test_full_kwargs` |  |  |
| 56 | **unknown** | `test_partial_kwargs_fills_var` |  |  |
| 62 | **unknown** | `test_no_args_all_vars` |  |  |
| 68 | **unknown** | `test_each_call_fresh_vars` |  |  |
| 75 | **unknown** | `test_positional_args` |  |  |
| 81 | **unknown** | `test_isinstance_works` |  |  |
| 87 | **unknown** | `test_three_fields_partial` |  |  |
| 94 | **unknown** | `test_none_is_not_missing` |  |  |
| 101 | **unknown** | `test_zero_arity_returns_class` |  |  |
| 111 | **unknown** | `test_eq_same_values` |  |  |
| 115 | **unknown** | `test_eq_different_values` |  |  |
| 119 | **unknown** | `test_eq_different_types` |  |  |
| 123 | **unknown** | `test_repr` |  |  |
| 128 | **unknown** | `test_repr_zero_arity` |  |  |
| 138 | **infra** | `test_match_args_set` |  | __match_args__ |
| 142 | **unknown** | `test_match_case` |  |  |
| 166 | **infra** | `test_assertz_appends` |  | _clauses |
| 174 | **infra** | `test_asserta_prepends` |  | _clauses |
| 182 | **infra** | `test_assertz_clears_dispatch` |  | _dispatch_fn |
| 188 | **infra** | `test_retract_removes_first_match` |  | _clauses |
| 198 | **unknown** | `test_retract_nonexistent_returns_false` |  |  |
| 203 | **infra** | `test_retract_clears_dispatch` |  | _dispatch_fn |
| 226 | **infra** | `test_get_dispatch_returns_fn` |  | _dispatch_fn, _get_dispatch |
| 232 | **infra** | `test_get_dispatch_lazy_recompile` |  | _dispatch_fn, _get_dispatch, _lazy_recompile |
| 240 | **infra** | `test_get_dispatch_no_fn_raises` |  | _get_dispatch |
| 245 | **infra** | `test_assertz_triggers_lazy_recompile` |  | _dispatch_fn, _get_dispatch, _lazy_recompile |
| 275 | **infra** | `test_starts_unlocked` |  | _locked |
| 279 | **infra** | `test_lock` |  | _locked |
| 284 | **infra** | `test_unlock` |  | _locked |
| 290 | **unknown** | `test_locked_assertz_raises` |  |  |
| 296 | **unknown** | `test_locked_asserta_raises` |  |  |
| 302 | **unknown** | `test_locked_retract_raises` |  |  |
| 308 | **infra** | `test_unlocked_after_lock_allows_assertz` |  | _clauses |
| 334 | **infra** | `test_clauses_are_per_class` |  | _clauses |
| 340 | **infra** | `test_locking_is_per_class` |  | _locked |
| 351 | **unknown** | `test_repr_uncompiled` |  |  |
| 357 | **infra** | `test_repr_compiled` |  | _dispatch_fn |
| 364 | **unknown** | `test_repr_locked` |  |  |
| 376 | **infra** | `test_predicate_is_a_class` |  | PredicateMeta |
| 381 | **infra**† | `test_fields_preserved` |  | _fields |
| 385 | **infra** | `test_slots` |  | __slots__ |
| 389 | **unknown** | `test_missing_sentinel_identity` |  |  |
| 393 | **unknown** | `test_hash_disabled` |  |  |
| 406 | **infra** | `test_is_term_instance_true` |  | is_term_instance |
| 411 | **infra** | `test_is_term_instance_class_false` |  | is_term_instance |
| 416 | **infra** | `test_term_field_names` |  | term_field_names |
| 421 | **infra**† | `test_term_field_names_on_class` |  | _fields |
| 425 | **infra** | `test_zero_arity_fields` |  | _fields |
| 431 | **unknown** | `test_not_dataclass` |  |  |
| 451 | **unknown** | `test_call_returns_class` |  |  |
| 455 | **unknown** | `test_different_atoms_not_identical` |  |  |
| 459 | **unknown** | `test_atom_is_hashable` |  |  |
| 464 | **unknown** | `test_atom_in_set` |  |  |
| 470 | **infra** | `test_unify_same_atom` |  | Trail, unify |
| 476 | **infra** | `test_unify_different_atoms_fails` |  | Trail, unify |
| 482 | **infra** | `test_unify_var_with_atom` |  | Trail, Var, deref, unify |
| 490 | **unknown** | `test_is_atom_helper` |  |  |
| 499 | **unknown** | `test_non_zero_arity_unchanged` |  |  |
| 512 | **infra** | `test_returns_predicate_meta` |  | PredicateMeta, _fields |
| 520 | **unknown** | `test_call_returns_self` |  |  |
| 526 | **unknown** | `test_different_calls_different_identity` |  |  |
| 533 | **unknown** | `test_hashable` |  |  |
| 540 | **infra** | `test_unify` |  | Trail, Var, deref, unify |

</details>

<details><summary><code>tests/test_string_higher_order.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 46 | **mixed** | `test_filter_vowels` | call | Var, deref, module_dict |
| 52 | **mixed** | `test_filter_empty` | call | Var, deref, module_dict |
| 58 | **mixed** | `test_filter_none_match` | call | Var, deref, module_dict |
| 64 | **mixed** | `test_filter_all_match` | call | Var, deref, module_dict |
| 70 | **mixed** | `test_filter_list_still_works` | call | Var, deref, module_dict |
| 83 | **mixed** | `test_exclude_vowels` | call | Var, deref, module_dict |
| 94 | **mixed** | `test_maplist2_all_succeed` | call | module_dict |
| 98 | **mixed** | `test_maplist2_some_fail` | call | module_dict |
| 102 | **mixed** | `test_maplist2_empty` | call | module_dict |
| 111 | **mixed** | `test_maplist3_char_to_code` | call | Var, deref, module_dict |
| 122 | **mixed** | `test_foldleft_concat_chars` | call | Var, deref, module_dict |
| 135 | **mixed** | `test_partition_vowels` | call | Var, deref, module_dict |
| 147 | **mixed** | `test_take_while_vowels` | call | Var, deref, module_dict |
| 153 | **mixed** | `test_take_while_none` | call | Var, deref, module_dict |
| 164 | **mixed** | `test_drop_while_vowels` | call | Var, deref, module_dict |
| 175 | **mixed** | `test_span_vowels` | call | Var, deref, module_dict |

</details>

<details><summary><code>tests/test_tabling.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 46 | **infra** | `test_initial_state` |  | TableEntry |
| 54 | **infra** | `test_add_answer_new` |  | TableEntry |
| 61 | **infra** | `test_add_answer_duplicate` |  | TableEntry |
| 68 | **infra** | `test_add_answer_preserves_order` |  | TableEntry |
| 81 | **unknown** | `test_ground_scalar` |  |  |
| 88 | **infra** | `test_unbound_var` |  | Var |
| 93 | **infra** | `test_bound_var` |  | Trail, Var, unify |
| 100 | **unknown** | `test_list` |  |  |
| 105 | **infra** | `test_compound` |  | Compound |
| 111 | **infra** | `test_make_subgoal_key_ground` |  | Trail |
| 117 | **infra** | `test_make_subgoal_key_with_vars` |  | Trail, Var |
| 124 | **infra** | `test_variant_keys_match` |  | Trail |
| 131 | **infra** | `test_variant_keys_vars_match` |  | Trail, Var |
| 143 | **infra** | `test_freeze_ground` |  | Trail |
| 149 | **infra** | `test_freeze_bound_var` |  | Trail, Var, unify |
| 157 | **infra** | `test_unify_answer_success` |  | Trail, Var, deref |
| 165 | **infra** | `test_unify_answer_failure` |  | Trail |
| 193 | **unknown** | `test_normalize_dataclass_ground` |  |  |
| 199 | **infra** | `test_normalize_dataclass_with_var` |  | Var |
| 206 | **infra** | `test_normalize_dataclass_with_bound_var` |  | Trail, Var, unify |
| 215 | **unknown** | `test_normalize_nested_dataclass` |  |  |
| 222 | **infra** | `test_make_subgoal_key_dataclass` |  | Trail |
| 229 | **infra** | `test_make_subgoal_key_dataclass_with_var` |  | Trail, Var |
| 237 | **infra** | `test_freeze_dataclass_ground` |  | Trail |
| 247 | **infra** | `test_freeze_dataclass_with_bound_var` |  | Trail, Var, unify |
| 259 | **unknown** | `test_deref_walk_dataclass_ground` |  |  |
| 267 | **infra** | `test_deref_walk_dataclass_with_bound_var` |  | Trail, Var, unify |
| 278 | **infra** | `test_deref_walk_nested_dataclass` |  | Trail, Var, unify |
| 292 | **infra** | `test_unify_answer_dataclass` |  | Trail, Var, deref |
| 303 | **infra** | `test_variant_keys_dataclass_match` |  | Trail, Var |
| 312 | **infra** | `test_variant_keys_dataclass_differ` |  | Trail |
| 325 | **mixed**† | `test_fib_basic` | call | Var, deref |
| 334 | **mixed** | `test_fib_zero` | call | Var, deref |
| 343 | **mixed** | `test_fib_one` | call | Var, deref |
| 352 | **mixed** | `test_fib_cache_hit` | call | Var, deref |
| 370 | **behavior** | `test_fib_ground_query_success` | call |  |
| 377 | **behavior** | `test_fib_ground_query_failure` | call |  |
| 389 | **mixed** | `test_cyclic_path_terminates` | call | Var, deref |
| 400 | **mixed** | `test_path_all_pairs` | call | Var, deref |
| 411 | **mixed** | `test_path_from_node_2` | call | Var, deref |
| 420 | **mixed** | `test_path_from_node_3` | call | Var, deref |
| 429 | **behavior** | `test_path_ground_true` | call |  |
| 435 | **behavior** | `test_path_ground_self` | call |  |
| 442 | **mixed** | `test_table_entry_complete_after_query` | call | Var |
| 457 | **infra** | `test_table_store_property` |  | Database |
| 463 | **infra** | `test_abolish_table` |  | Database, TableEntry |
| 473 | **infra** | `test_abolish_all_tables` |  | Database, TableEntry |
| 481 | **infra** | `test_assertz_auto_invalidates_tabled` |  | Compound, Database, TableEntry |
| 489 | **infra** | `test_retract_auto_invalidates_tabled` |  | Compound, Database, TableEntry |
| 499 | **infra** | `test_assertz_non_tabled_no_invalidation` |  | Compound, Database, TableEntry |
| 511 | **unknown** | `test_tabled_directive_sets_metadata` |  |  |
| 517 | **unknown** | `test_tabled_predicate_wrapped` |  |  |
| 524 | **mixed** | `test_non_tabled_predicate_still_works` | call | Var, deref |
| 538 | **mixed** | `test_abolish_recomputes` | call | Var, deref |
| 563 | **mixed** | `test_two_tabled_predicates` | call | Var, deref |
| 615 | **infra** | `test_simple_wrapper_basic` |  | Trail, Var, deref, unify |
| 643 | **infra** | `test_simple_wrapper_cache_hit` |  | Trail, Var, deref, unify |
| 671 | **infra** | `test_trampoline_wrapper_basic` |  | Trail, Var, deref, unify |
| 695 | **infra** | `test_trampoline_wrapper_multiple_answers` |  | Trail, Var, deref, unify |
| 718 | **infra** | `test_trampoline_to_simple_adapter` |  | Trail, Var, deref, unify |

</details>

<details><summary><code>tests/test_wfs.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 45 | **unknown** | `test_equality` |  |  |
| 51 | **unknown** | `test_inequality` |  |  |
| 57 | **unknown** | `test_hashable` |  |  |
| 65 | **unknown** | `test_repr` |  |  |
| 75 | **infra** | `test_add_answer_default_unconditional` |  | TableEntry |
| 81 | **infra** | `test_add_answer_with_delays` |  | TableEntry |
| 88 | **infra** | `test_truth_value_unconditional` |  | TableEntry |
| 94 | **infra** | `test_truth_value_conditional` |  | TableEntry |
| 101 | **infra** | `test_truth_value_failed` |  | TableEntry |
| 108 | **infra** | `test_current_delays_initially_empty` |  | TableEntry |
| 118 | **unknown** | `test_empty_stack` |  |  |
| 129 | **infra** | `test_push_pop` |  | TableEntry |
| 144 | **infra** | `test_nested_leaders` |  | TableEntry |
| 166 | **infra** | `test_complete_table_no_match` |  | TableEntry, Trail |
| 178 | **infra** | `test_complete_table_with_match` |  | TableEntry, Trail |
| 190 | **infra** | `test_complete_table_skips_failed` |  | TableEntry, Trail |
| 203 | **infra** | `test_evaluating_table_delays` |  | TableEntry, Trail |
| 229 | **infra** | `test_no_entry_returns_true` |  | Trail |
| 236 | **infra** | `test_complete_table_var_arg` |  | TableEntry, Trail, Var |
| 256 | **infra** | `test_unconditional_passthrough` |  | TableEntry |
| 268 | **infra** | `test_resolve_to_true` |  | TableEntry |
| 288 | **infra** | `test_resolve_to_false` |  | TableEntry |
| 308 | **infra** | `test_unfounded_stays_conditional` |  | TableEntry |
| 323 | **infra** | `test_multiple_delays_partial_resolution` |  | TableEntry |
| 350 | **mixed**† | `test_tabled_fib` | call | Var, deref |
| 360 | **mixed** | `test_tabled_path_cyclic` | call | Var, deref |
| 375 | **infra** | `test_naf_on_complete_table` |  | TableEntry, Trail |
| 396 | **mixed** | `test_symmetric_win_both_undefined` | call | Var, deref |
| 433 | **mixed** | `test_asymmetric_win` | call | Var, deref |
| 460 | **mixed** | `test_tabled_with_naf_no_cycle` | call | Var, deref |
| 486 | **mixed** | `test_query_wfs_returns_list` | query_wfs | LoadName, Trail, Var, unify |

</details>

### core

<details><summary><code>tests/conformity/test_iso_term_manipulation.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 50 | **mixed** | `test_decompose_compound` | call | Compound, Module, Var, deref |
| 58 | **mixed** | `test_decompose_atom` | call | Module, Var, deref |
| 67 | **mixed** | `test_decompose_arity1` | call | Compound, Module, Var, deref |
| 75 | **mixed** | `test_construct_compound` | call | Compound, Module, Var, deref |
| 86 | **mixed** | `test_construct_atom` | call | Module, Var, deref |
| 96 | **mixed** | `test_decompose_large_compound` | call | Compound, Module, Var, deref |
| 115 | **mixed** | `test_first_arg` | call | Compound, Module, Var, deref |
| 123 | **mixed** | `test_second_arg` | call | Compound, Module, Var, deref |
| 131 | **mixed** | `test_third_arg` | call | Compound, Module, Var, deref |
| 138 | **mixed** | `test_out_of_range` | call | Compound, Module, Var, deref |
| 145 | **mixed** | `test_zero_fails` | call | Compound, Module, Var, deref |
| 152 | **mixed** | `test_negative_fails` | call | Compound, Module, Var, deref |
| 158 | **mixed** | `test_nested_compound` | call | Compound, Module, Var, deref |
| 174 | **mixed** | `test_decompose_compound` | call | Compound, Module, Var, deref |
| 182 | **mixed** | `test_decompose_atom` | call | Module, Var, deref |
| 190 | **mixed** | `test_decompose_arity1` | call | Compound, Module, Var, deref |
| 198 | **mixed** | `test_construct_from_list` | call | Compound, Module, Var, deref |
| 209 | **mixed** | `test_construct_atom_from_list` | call | Module, Var, deref |

</details>

<details><summary><code>tests/conformity/test_iso_unification.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 39 | **infra** | `test_compound_var_args` |  | Compound, Trail, Var, deref, structural_unify |
| 48 | **infra** | `test_nested_compound` |  | Compound, Trail, Var, deref, structural_unify |
| 56 | **infra** | `test_different_functors_fail` |  | Compound, Trail, structural_unify |
| 60 | **infra** | `test_different_arity_fail` |  | Compound, Trail, structural_unify |
| 64 | **infra** | `test_var_aliases` |  | Compound, Trail, Var, deref, structural_unify |
| 70 | **infra** | `test_var_aliases_fail` |  | Compound, Trail, Var, structural_unify |
| 86 | **unknown** | `test_seglist_same` |  |  |
| 90 | **unknown** | `test_seglist_different` |  |  |
| 94 | **infra** | `test_seglist_with_same_var` |  | Var |
| 102 | **infra** | `test_seglist_with_different_vars` |  | Var |
| 109 | **infra** | `test_dictterm_same` |  | DictTerm |
| 113 | **infra** | `test_dictterm_different_values` |  | DictTerm |
| 117 | **infra** | `test_dictterm_different_keys` |  | DictTerm |
| 121 | **infra** | `test_dictterm_var_value_same_var` |  | DictTerm, Var |
| 126 | **infra** | `test_dictterm_var_value_different_vars` |  | DictTerm, Var |
| 130 | **infra** | `test_setterm_same` |  | SetTerm |
| 134 | **infra** | `test_setterm_different` |  | SetTerm |
| 146 | **mixed** | `test_no_binding` | _goal_fails, _goal_succeeds, once | Module, Var, deref |
| 153 | **mixed** | `test_bound_var_equals_value` | _goal_succeeds, once | Module, Trail, Var, unify |

</details>

<details><summary><code>tests/test_body_star_decon.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 68 | **mixed** | `test_head_tail_basic` | solve | And, Module, Var, deref |
| 80 | **mixed** | `test_head_tail_singleton` | solve | And, Module, Var, deref |
| 92 | **mixed** | `test_head_tail_empty_fails` | solve | And, Module, Var |
| 103 | **mixed** | `test_two_fixed_plus_star` | solve | And, Module, Var, deref |
| 115 | **mixed** | `test_two_fixed_exact_match` | solve | And, Module, Var, deref |
| 127 | **mixed** | `test_two_fixed_too_short_fails` | solve | And, Module, Var |
| 138 | **mixed** | `test_star_only` | solve | And, Module, Var, deref |
| 150 | **mixed** | `test_star_only_empty` | solve | And, Module, Var, deref |
| 162 | **mixed** | `test_sandwich_pattern` | solve | And, Module, Var, deref |
| 174 | **mixed** | `test_sandwich_minimum` | solve | And, Module, Var, deref |
| 186 | **mixed** | `test_sandwich_too_short_fails` | solve | And, Module, Var |
| 197 | **mixed** | `test_trailing_star` | solve | And, Module, Var, deref |
| 209 | **mixed** | `test_nested_list_elements` | solve | And, Module, Var, deref |
| 235 | **mixed** | `test_construct_from_bound_vars` | solve | And, Module, Var, deref |
| 250 | **mixed** | `test_construct_empty_tail` | solve | And, Module, Var, deref |
| 265 | **mixed** | `test_construct_star_only` | solve | And, Module, Var, deref |
| 277 | **mixed** | `test_construct_sandwich` | solve | And, Module, Var, deref |
| 308 | **mixed** | `test_append_forward` | call | Module, Var, deref |
| 316 | **mixed** | `test_append_reverse` | call | Module, Var, deref |
| 332 | **mixed** | `test_length` | call | Module, Var, deref |
| 340 | **mixed** | `test_length_empty` | call | Module, Var, deref |
| 357 | **mixed** | `test_head_tail_body_decon` | call | Module, Var, deref |
| 371 | **mixed** | `test_head_tail_singleton` | call | Module, Var, deref |
| 382 | **mixed** | `test_head_tail_empty_fails` | call | Module, Var |
| 390 | **mixed** | `test_init_last_body_decon` | call | Module, Var, deref |
| 404 | **mixed** | `test_init_last_singleton` | call | Module, Var, deref |
| 415 | **mixed** | `test_init_last_empty_fails` | call | Module, Var |
| 423 | **mixed** | `test_sandwich_body_decon` | call | Module, Var, deref |
| 437 | **mixed** | `test_sandwich_minimum` | call | Module, Var, deref |
| 448 | **mixed** | `test_capture_all_body` | call | Module, Var, deref |
| 459 | **mixed** | `test_capture_all_body_empty` | call | Module, Var, deref |
| 467 | **mixed** | `test_body_decon_then_use` | call | Module, Var, deref |
| 478 | **mixed** | `test_body_decon_chain` | call | Module, Var, deref |
| 489 | **mixed** | `test_body_construct_and_decon` | call | Module, Var, deref |
| 510 | **mixed** | `test_body_split` | call | Module, Var, deref |
| 529 | **mixed** | `test_body_split_empty` | call | Module, Var, deref |
| 540 | **mixed** | `test_body_split_singleton` | call | Module, Var, deref |
| 560 | **mixed** | `test_decon_then_construct_roundtrip` | solve | And, Module, Var, deref |
| 575 | **mixed** | `test_lhs_ground_rhs_pattern` | solve | Module, Var, deref |
| 584 | **mixed** | `test_rhs_ground_lhs_pattern` | solve | Module, Var, deref |

</details>

<details><summary><code>tests/test_builtin_classes.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 29 | **unknown** | `test_all_builtins_have_fields` |  |  |
| 36 | **unknown** | `test_all_builtins_have_classes` |  |  |
| 42 | **unknown** | `test_class_count` |  |  |
| 46 | **unknown** | `test_get_builtin_class_found` |  |  |
| 51 | **unknown** | `test_get_builtin_class_not_found` |  |  |
| 62 | **infra** | `test_append_positional` |  | is_term_instance |
| 71 | **infra** | `test_append_keyword` |  | Var, deref |
| 80 | **infra** | `test_between_partial` |  | Var, deref |
| 88 | **unknown** | `test_length_positional` |  |  |
| 95 | **infra** | `test_zero_arity` |  | PredicateMeta |
| 101 | **infra** | `test_no_args_all_vars` |  | Var, deref |
| 115 | **unknown** | `test_append_fields` |  |  |
| 119 | **unknown** | `test_between_fields` |  |  |
| 123 | **unknown** | `test_length_fields` |  |  |
| 127 | **unknown** | `test_functor_fields` |  |  |
| 131 | **unknown** | `test_in_fields` |  |  |
| 135 | **unknown** | `test_db_builtin_fields` |  |  |
| 141 | **infra** | `test_term_field_names_on_instance` |  | term_field_names |
| 154 | **infra** | `test_is_predicate_meta` |  | PredicateMeta |
| 159 | **unknown** | `test_functor_property` |  |  |
| 164 | **unknown** | `test_arity_property` |  |  |
| 169 | **infra** | `test_locked` |  | _locked |
| 174 | **unknown** | `test_assertz_raises_on_locked` |  |  |
| 180 | **infra** | `test_dispatch_fn_set` |  | _dispatch_fn |
| 185 | **infra** | `test_get_dispatch` |  | _get_dispatch |
| 191 | **infra** | `test_db_builtin_no_dispatch` |  | _dispatch_fn |
| 202 | **unknown** | `test_eq` |  |  |
| 207 | **unknown** | `test_neq` |  |  |
| 212 | **unknown** | `test_repr` |  |  |
| 222 | **unknown** | `test_match_args` |  |  |
| 239 | **unknown** | `test_maplist_is_multi` |  |  |
| 244 | **infra** | `test_maplist_2_construction` |  | is_term_instance |
| 251 | **infra** | `test_maplist_3_construction` |  | is_term_instance |
| 258 | **infra** | `test_maplist_dispatch` |  | _get_dispatch |
| 264 | **unknown** | `test_phrase_is_multi` |  |  |
| 269 | **unknown** | `test_phrase_2_construction` |  |  |
| 275 | **unknown** | `test_phrase_3_construction` |  |  |
| 281 | **unknown** | `test_multi_repr` |  |  |
| 292 | **infra** | `test_is_term_instance_true` |  | is_term_instance |
| 298 | **infra** | `test_is_term_instance_false_on_class` |  | is_term_instance |
| 303 | **infra** | `test_term_field_names` |  | term_field_names |
| 345 | **infra** | `test_append_concat` |  | Var |
| 353 | **infra** | `test_append_split` |  | Var |
| 364 | **infra** | `test_between_enumerate` |  | Var |
| 372 | **infra** | `test_length_check` |  | Var |
| 380 | **infra** | `test_in_member` |  | Var |
| 388 | **infra** | `test_reverse` |  | Var |
| 396 | **infra** | `test_sort` |  | Var |
| 404 | **infra** | `test_plus_relational` |  | Var |
| 412 | **infra** | `test_succ_forward` |  | Var |
| 420 | **infra** | `test_succ_backward` |  | Var |
| 439 | **mixed** | `test_call_append` | call | Var, deref |
| 451 | **mixed** | `test_call_between` | call | Var, deref |
| 462 | **mixed** | `test_call_length` | call | Var, deref |
| 472 | **mixed** | `test_construct_then_unpack_for_call` | call | Var, _fields, deref |

</details>

<details><summary><code>tests/test_builtins.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 49 | **infra** | `test_construction_and_access` |  | KWTerm |
| 56 | **infra** | `test_equality_order_independent` |  | KWTerm |
| 60 | **infra** | `test_equality_different_functor` |  | KWTerm |
| 64 | **infra** | `test_equality_different_fields` |  | KWTerm |
| 68 | **infra** | `test_len` |  | KWTerm |
| 72 | **infra** | `test_keys_values_items` |  | KWTerm |
| 79 | **infra** | `test_with_overrides` |  | KWTerm |
| 86 | **infra** | `test_with_overrides_unknown_key` |  | KWTerm |
| 92 | **infra** | `test_with_extensions` |  | KWTerm |
| 98 | **infra** | `test_with_extensions_existing_key` |  | KWTerm |
| 104 | **infra** | `test_repr` |  | KWTerm |
| 109 | **infra** | `test_hash_consistent` |  | KWTerm |
| 115 | **infra** | `test_missing_attr` |  | KWTerm |
| 134 | **mixed** | `test_decompose_compound` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 144 | **mixed** | `test_decompose_atom` | solve | Call, LoadName, Module, Trail, Var, deref |
| 152 | **mixed** | `test_decompose_integer` | solve | Call, LoadName, Module, Trail, Var, deref |
| 160 | **mixed** | `test_compose_compound` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 172 | **mixed** | `test_compose_atom` | solve | Call, LoadName, Module, Trail, Var, deref |
| 179 | **mixed** | `test_fails_both_unbound` | solve | Call, LoadName, Module, Trail, Var, deref |
| 186 | **mixed** | `test_decompose_dataclass` | solve | Call, Database, LoadName, Module, Trail, Var, deref |
| 206 | **mixed** | `test_first_arg` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 213 | **mixed** | `test_second_arg` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 220 | **mixed** | `test_out_of_range` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 227 | **mixed** | `test_list_arg` | solve | Call, LoadName, Module, Trail, Var, deref |
| 239 | **mixed** | `test_decompose` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 247 | **mixed** | `test_construct` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 259 | **mixed** | `test_decompose_atom` | solve | Call, LoadName, Module, Trail, Var, deref |
| 277 | **mixed** | `test_vary_dataclass` | solve | Call, LoadName, Module, Trail, Var, deref |
| 296 | **mixed** | `test_vary_kwterm` | solve | Call, KWTerm, LoadName, Module, Trail, Var, deref |
| 308 | **mixed** | `test_vary_unknown_key` | solve | Call, KWTerm, LoadName, Module, Trail, Var, deref |
| 318 | **mixed** | `test_extend_kwterm` | solve | Call, KWTerm, LoadName, Module, Trail, Var, deref |
| 330 | **mixed** | `test_unbound_keys_dataclass` | solve | Call, LoadName, Module, Trail, Var, deref |
| 345 | **mixed** | `test_unbound_keys_kwterm` | solve | Call, KWTerm, LoadName, Module, Trail, Var, deref |
| 355 | **mixed** | `test_signature` | solve | Call, LoadName, Module, Trail, Var, deref |
| 369 | **mixed** | `test_signature_unknown` | solve | Call, LoadName, Module, Trail, Var, deref |
| 386 | **mixed** | `test_between_in_compiled_body` | solve | Call, Compound, LoadName, Module, Trail, Var, compile_predicate_trampoline, deref, get_dispatch |
| 409 | **mixed** | `test_member_in_compiled_body` | solve | Call, Compound, LoadName, Module, Trail, Var, compile_predicate_trampoline, deref, get_dispatch |

</details>

<details><summary><code>tests/test_callsite_specialization.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 58 | **infra** | `test_index_plans_set_for_indexed_predicate` |  | Compound, PredicateMeta, compile_predicate |
| 69 | **infra** | `test_index_plans_keys_are_positions` |  | Compound, PredicateMeta, compile_predicate |
| 80 | **infra** | `test_index_plans_values_are_dicts_of_callables` |  | Compound, PredicateMeta, compile_predicate |
| 93 | **infra** | `test_index_plans_contains_expected_keys` |  | Compound, PredicateMeta, compile_predicate |
| 103 | **infra** | `test_index_plans_contains_integer_keys` |  | Compound, PredicateMeta, compile_predicate |
| 114 | **infra** | `test_index_plans_empty_when_below_threshold` |  | Compound, PredicateMeta, compile_predicate |
| 125 | **infra** | `test_index_plans_not_set_when_no_pred_cls` |  | Compound, compile_predicate |
| 134 | **infra** | `test_dispatch_routes_through_bucket` |  | Compound, PredicateMeta, Trail, compile_predicate, deref |
| 148 | **infra** | `test_dispatch_no_solutions_for_unknown_value` |  | Compound, PredicateMeta, Trail, compile_predicate, deref |
| 162 | **infra** | `test_index_plans_empty_when_compiled_with_few_clauses` |  | Compound, PredicateMeta, compile_predicate |
| 176 | **infra** | `test_two_arg_predicate_indexes_first_arg` |  | Compound, PredicateMeta, compile_predicate |
| 188 | **infra** | `test_second_position_indexed_when_more_selective` |  | Compound, PredicateMeta, compile_predicate |
| 206 | **infra** | `test_index_plans_joint_set_for_high_coverage` |  | Compound, PredicateMeta, compile_predicate |
| 228 | **infra** | `test_index_plans_joint_keys_are_tuples` |  | Compound, PredicateMeta, compile_predicate |
| 246 | **infra** | `test_integer_constant` |  | ast |
| 250 | **infra** | `test_string_constant` |  | ast |
| 254 | **infra** | `test_float_constant` |  | ast |
| 258 | **infra** | `test_none_constant` |  | ast |
| 262 | **infra** | `test_bool_constant` |  | ast |
| 266 | **infra** | `test_variable_name_returns_none` |  | ast |
| 271 | **infra** | `test_compound_call_name` |  | ast |
| 281 | **infra** | `test_compound_call_qualified` |  | ast |
| 296 | **infra** | `test_compound_call_no_args` |  | ast |
| 304 | **infra** | `test_list_literal_returns_none` |  | ast |
| 310 | **infra** | `test_zero_integer` |  | ast |
| 314 | **infra** | `test_empty_string` |  | ast |
| 323 | **unknown** | `test_bucket_key_atom` |  |  |
| 328 | **unknown** | `test_bucket_key_integer` |  |  |
| 333 | **unknown** | `test_bucket_key_second_position` |  |  |
| 338 | **unknown** | `test_bucket_key_compound` |  |  |
| 343 | **unknown** | `test_joint_bucket_key` |  |  |
| 351 | **unknown** | `test_joint_bucket_key_symmetric` |  |  |
| 373 | **mixed** | `test_bucket_injected_for_literal_arg` | call_goal | Call, Compound, LoadName, PredicateMeta, Var, _locked, compile_predicate |
| 403 | **mixed** | `test_bucket_ref_map_populated` | call_goal | Call, Compound, LoadName, PredicateMeta, Var, _locked, compile_predicate |
| 425 | **mixed** | `test_no_injection_for_variable_arg` | call_goal | Call, Compound, LoadName, PredicateMeta, Var, _locked, compile_predicate |
| 449 | **mixed** | `test_no_injection_for_unlocked_predicate` | call_goal | Call, Compound, LoadName, PredicateMeta, Var, _locked, compile_predicate |
| 473 | **mixed** | `test_no_injection_for_unknown_key` | call_goal | Call, Compound, LoadName, PredicateMeta, Var, _locked, compile_predicate |
| 519 | **unknown** | `test_callsite_bucket_injected_into_base_globals` |  |  |
| 529 | **infra** | `test_locked_callee_returns_correct_results` |  | Compound, PredicateMeta, Trail, _dispatch_fn, _locked, compile_predicate, deref |
| 541 | **infra** | `test_locked_callee_variable_arg_returns_all` |  | Compound, PredicateMeta, Trail, Var, _dispatch_fn, _locked, compile_predicate, deref |
| 554 | **mixed** | `test_compile_caller_with_literal_uses_bucket_ref` | call_goal | Call, Compound, LoadName, PredicateMeta, Var, _locked, compile_predicate |
| 580 | **mixed** | `test_dynamic_predicate_not_specialised` | call_goal | Call, Compound, LoadName, PredicateMeta, Var, _locked, compile_predicate |
| 606 | **mixed** | `test_self_recursive_predicate_not_specialised` | call_goal | Call, Compound, LoadName, PredicateMeta, Var, _locked |
| 632 | **infra** | `test_multiple_literal_calls_different_buckets` |  | Call, Compound, LoadName, PredicateMeta, Var, _locked, compile_predicate |
| 657 | **mixed** | `test_bucket_ref_is_correct_callable` | call_goal | Call, Compound, LoadName, PredicateMeta, Var, _locked, compile_predicate |
| 684 | **mixed** | `test_inject_idempotent_for_same_key` | call_goal | Call, Compound, LoadName, PredicateMeta, Var, _locked, compile_predicate |

</details>

<details><summary><code>tests/test_codegen.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 26 | **infra** | `test_load_only_is_param` |  | ast, parse |
| 30 | **infra** | `test_assigned_before_load_is_local` |  | ast, parse |
| 34 | **infra** | `test_load_before_assign_is_param` |  | ast, parse |
| 39 | **infra** | `test_multiple_params_in_load_order` |  | ast, parse |
| 43 | **infra** | `test_same_name_used_twice_appears_once` |  | ast, parse |
| 47 | **infra** | `test_param_then_reassigned` |  | ast, parse |
| 55 | **infra** | `test_augassign_makes_param` |  | ast, parse |
| 60 | **infra** | `test_augassign_on_subscript_object_is_param` |  | ast, parse |
| 65 | **infra** | `test_augassign_on_attribute_object_is_param` |  | ast, parse |
| 72 | **infra** | `test_for_iterable_is_param` |  | ast, parse |
| 76 | **infra** | `test_for_target_is_local` |  | ast, parse |
| 80 | **infra** | `test_for_body_load_is_param` |  | ast, parse |
| 84 | **infra** | `test_for_target_used_after_loop_is_not_param` |  | ast, parse |
| 92 | **infra** | `test_listcomp_outermost_iter_is_param` |  | ast, parse |
| 97 | **infra** | `test_listcomp_element_name_not_param` |  | ast, parse |
| 102 | **infra** | `test_listcomp_inner_iter_not_param` |  | ast, parse |
| 108 | **infra** | `test_setcomp_outermost_iter_is_param` |  | ast, parse |
| 112 | **infra** | `test_dictcomp_outermost_iter_is_param` |  | ast, parse |
| 116 | **infra** | `test_genexpr_outermost_iter_is_param` |  | ast, parse |
| 123 | **infra** | `test_nested_function_names_not_params` |  | ast, parse |
| 128 | **infra** | `test_nested_function_name_is_local` |  | ast, parse |
| 134 | **infra** | `test_nested_class_body_names_not_params` |  | ast, parse |
| 139 | **infra** | `test_lambda_body_not_scanned` |  | ast, parse |
| 147 | **infra** | `test_builtin_not_a_param` |  | ast, parse |
| 153 | **infra** | `test_only_non_builtin_becomes_param` |  | ast, parse |
| 160 | **infra** | `test_global_name_not_a_param` |  | ast, parse |
| 164 | **infra** | `test_all_globals_excluded` |  | ast, parse |
| 168 | **infra** | `test_global_name_still_accessible_at_runtime` |  | ast, parse |
| 178 | **infra** | `test_global_stmt_excludes_name` |  | ast, parse |
| 183 | **infra** | `test_global_stmt_load_not_param` |  | ast, parse |
| 191 | **infra** | `test_param_order_matches_first_load` |  | ast, parse |
| 195 | **infra** | `test_param_order_across_statements` |  | ast, parse |
| 202 | **infra** | `test_inferred_function_works` |  | ast, parse |
| 207 | **infra** | `test_inferred_function_signature` |  | ast, parse |
| 212 | **infra** | `test_no_params_when_all_assigned` |  | ast, parse |
| 218 | **infra** | `test_explicit_args_not_overridden` |  | ast, parse |

</details>

<details><summary><code>tests/test_compiled_programs.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 139 | **infra** | `test_direct_edge` |  | Trail, Var, deref, get_dispatch |
| 149 | **infra** | `test_transitive_reachability` |  | Trail, Var, deref, get_dispatch |
| 159 | **infra** | `test_no_path_backwards` |  | Trail, Var, deref, get_dispatch |
| 169 | **infra** | `test_path_to_specific_dest` |  | Trail, Var, deref, get_dispatch |
| 186 | **unknown** | `test_edge_count` |  |  |
| 232 | **infra** | `test_dog_is_mammal` |  | Trail, Var, deref, get_dispatch |
| 241 | **infra** | `test_eagle_is_bird` |  | Trail, Var, deref, get_dispatch |
| 250 | **infra** | `test_salmon_is_fish` |  | Trail, Var, deref, get_dispatch |
| 259 | **infra** | `test_name_is_irrelevant` |  | Trail, Var, deref, get_dispatch |
| 270 | **infra** | `test_unknown_matches_nothing` |  | Trail, Var, deref, get_dispatch |
| 280 | **infra** | `test_ground_category_check` |  | Trail, get_dispatch |
| 344 | **infra** | `test_fib_values` |  | Trail, Var, deref, get_dispatch |
| 353 | **infra** | `test_fib_deterministic` |  | Trail, Var, get_dispatch |
| 440 | **infra** | `test_perm4_has_24_solutions` |  | Trail, Var, deref, get_dispatch |
| 454 | **infra** | `test_no_attack_passes_safe_queens` |  | Trail, get_dispatch |
| 463 | **infra** | `test_no_attack_fails_diagonal` |  | Trail, get_dispatch |
| 472 | **infra** | `test_exactly_two_solutions` |  | Trail, Var, deref, get_dispatch |
| 485 | **infra** | `test_known_solutions` |  | Trail, Var, deref, get_dispatch |
| 541 | **infra** | `test_nine_combinations_simple` |  | Trail, Var, deref, get_dispatch |
| 553 | **infra** | `test_nine_combinations_trampoline` |  | Trail, Var, deref, get_dispatch |
| 566 | **infra** | `test_colour_filter` |  | Trail, get_dispatch |
| 575 | **infra** | `test_size_enumeration` |  | Trail, Var, deref, get_dispatch |
| 620 | **infra** | `test_or_val_three_solutions` |  | Trail, Var, deref, get_dispatch |
| 629 | **infra** | `test_or_pair_nine_solutions` |  | Trail, Var, deref, get_dispatch |
| 641 | **infra** | `test_filter_by_first` |  | Trail, get_dispatch |
| 650 | **infra** | `test_nonexistent_value` |  | Trail, get_dispatch |
| 698 | **infra** | `test_not_red_with_green` |  | Trail, get_dispatch |
| 707 | **infra** | `test_not_red_with_red_fails` |  | Trail, get_dispatch |
| 716 | **infra** | `test_not_red_enumerates_two` |  | Trail, Var, deref, get_dispatch |
| 734 | **infra** | `test_show_simple_produces_output` |  | Compound, Database, Var |
| 746 | **infra** | `test_show_trampoline_produces_output` |  | Compound, Database, Var |
| 758 | **infra** | `test_source_is_valid_python` |  | Add, Compound, Database, Evaluate, Var, parse, predicate_to_source |
| 774 | **infra** | `test_ast_str_non_empty` |  | Compound, Database, Var |
| 784 | **infra** | `test_visualize_fib_simple` |  | Add, Call, Compound, Database, Evaluate, Gt, LoadName, Sub, Var |

</details>

<details><summary><code>tests/test_compiler.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 76 | **infra** | `test_unbound_var_gives_match_as` |  | Var, ast |
| 85 | **infra** | `test_var_registers_in_context` |  | Var |
| 93 | **infra** | `test_two_different_vars_different_names` |  | Var |
| 104 | **infra** | `test_none_gives_match_singleton` |  | ast |
| 110 | **infra** | `test_true_gives_match_singleton` |  | ast |
| 116 | **infra** | `test_false_gives_match_singleton` |  | ast |
| 124 | **infra** | `test_int_gives_match_value` |  | ast |
| 131 | **infra** | `test_float_gives_match_value` |  | ast |
| 137 | **infra** | `test_str_gives_match_value` |  | ast |
| 143 | **infra** | `test_bytes_gives_match_value` |  | ast |
| 151 | **infra** | `test_empty_list_gives_wildcard_capture` |  | ast |
| 160 | **infra** | `test_list_registers_vars_in_context` |  | Var, ast |
| 173 | **infra** | `test_compound_gives_match_class_on_compound` |  | Compound, Var, ast |
| 196 | **infra** | `test_compound_with_var_functor_gives_wildcard` |  | Compound, Var, ast |
| 206 | **infra** | `test_dataclass_gives_match_class_on_its_type` |  | Var, ast |
| 221 | **infra** | `test_dataclass_all_literals` |  | ast |
| 230 | **infra** | `test_nested_dataclass` |  | Var, ast |
| 249 | **infra** | `test_unknown_term_gives_wildcard` |  | ast |
| 262 | **infra** | `test_returns_match_case` |  | ast |
| 273 | **infra** | `test_outer_pattern_is_match_sequence` |  | ast |
| 285 | **infra** | `test_ground_fact_skips_trail_mark` |  | ast |
| 299 | **infra** | `test_body_starts_with_trail_mark` |  | Var, ast |
| 315 | **mixed** | `test_body_has_try_finally_with_undo` | call | Var, ast |
| 336 | **infra** | `test_var_context_populated_from_head` |  | Var, ast |
| 349 | **infra** | `test_body_stmts_in_try_block` |  | Var, ast |
| 382 | **infra** | `test_no_clauses_always_fails` |  | Database, Trail, compile_predicate |
| 388 | **infra** | `test_no_clauses_is_generator` |  | Database, Trail, compile_predicate |
| 396 | **infra** | `test_no_clauses_installs_dispatch_fn` |  | Database, compile_predicate, get_dispatch |
| 404 | **infra** | `test_function_name_includes_functor_and_arity` |  | Database, compile_predicate |
| 411 | **infra** | `test_arity_zero_function_name` |  | Compound, Database, compile_predicate |
| 420 | **infra** | `test_literal_head_matches_exact_args` |  | Database, Trail, compile_predicate |
| 428 | **infra** | `test_literal_head_fails_wrong_arg` |  | Database, Trail, compile_predicate |
| 436 | **infra** | `test_singleton_head_none` |  | Compound, Database, Trail, compile_predicate |
| 446 | **infra** | `test_var_head_matches_any_value` |  | Database, Trail, Var, compile_predicate |
| 456 | **infra** | `test_var_head_fails_wrong_literal` |  | Database, Trail, Var, compile_predicate |
| 467 | **infra** | `test_compound_head_matches_compound_term` |  | Compound, Database, Trail, Var, compile_predicate |
| 476 | **infra** | `test_compound_head_fails_wrong_second_arg` |  | Compound, Database, Trail, Var, compile_predicate |
| 487 | **infra** | `test_nested_dataclass_head_matches` |  | Database, Trail, Var, compile_predicate |
| 499 | **infra** | `test_nested_dataclass_fails_wrong_inner` |  | Database, Trail, Var, compile_predicate |
| 514 | **infra** | `test_multi_clause_each_can_match` |  | Compound, Database, Trail, compile_predicate |
| 528 | **infra** | `test_multi_clause_no_double_yield` |  | Compound, Database, Trail, compile_predicate |
| 540 | **infra** | `test_installs_dispatch_fn_on_table` |  | Database, compile_predicate, get_dispatch |
| 548 | **infra** | `test_get_dispatch_works_after_compile` |  | Database, compile_predicate, get_dispatch |
| 559 | **infra** | `test_custom_body_compiler_called_per_clause` |  | Compound, Database, ast, compile_predicate |
| 581 | **infra** | `test_custom_body_compiler_can_yield_multiple` |  | Compound, Database, Trail, ast, compile_predicate |
| 602 | **infra** | `test_trail_mark_and_undo_called_around_body` |  | Compound, Database, Var, compile_predicate |
| 628 | **infra** | `test_trail_undo_called_after_solutions_exhausted` |  | Compound, Database, Var, compile_predicate |
| 657 | **infra** | `test_star_list_produces_wildcard_capture` |  | Var, ast |
| 666 | **infra** | `test_star_list_registers_both_vars` |  | Var |
| 675 | **infra** | `test_star_list_records_list_guard` |  | Var |
| 689 | **infra** | `test_star_middle_pattern` |  | Var |
| 704 | **infra** | `test_no_star_list_still_records_guard` |  | Var |
| 719 | **infra** | `test_repeated_var_produces_dup_guard` |  | Var, ast |
| 736 | **infra** | `test_repeated_var_across_list_patterns` |  | Var |
| 754 | **infra** | `test_nested_star_flattens_to_proxy_var` |  | Var, ast |
| 786 | **infra** | `test_nested_star_registers_all_vars` |  | Var |
| 801 | **infra** | `test_double_nested_star` |  | Var |
| 822 | **infra** | `test_nested_star_no_star_in_inner` |  | Var |
| 891 | **mixed** | `test_extract_head_tail_rows` | call | Var, deref |
| 901 | **mixed** | `test_extract_single_element_inner` | call | Var, deref |
| 911 | **mixed** | `test_extract_single_row` | call | Var, deref |
| 921 | **mixed** | `test_first` | call | Var, deref |
| 929 | **mixed** | `test_deep_triple_nesting` | call | Var, deref |
| 940 | **mixed** | `test_transpose_2x3` | call | Var, deref |
| 948 | **mixed** | `test_transpose_3x2` | call | Var, deref |
| 956 | **unknown** | `test_transpose_empty_rows` |  |  |
| 960 | **unknown** | `test_transpose_empty_matrix` |  |  |
| 973 | **infra** | `test_input_simple_list` |  | Trail, Var, deref |
| 982 | **infra** | `test_input_star_list` |  | Trail, Var, deref |
| 991 | **infra** | `test_input_star_middle` |  | Trail, Var, deref |
| 1001 | **infra** | `test_input_empty_star` |  | Trail, Var, deref |
| 1010 | **infra** | `test_input_too_short_fails` |  | Trail, Var |
| 1017 | **infra** | `test_input_no_star_wrong_length_fails` |  | Trail, Var |
| 1024 | **infra** | `test_input_non_list_fails` |  | Trail, Var |
| 1033 | **infra** | `test_input_var_defers` |  | Trail, Var |
| 1043 | **infra** | `test_output_constructs_list` |  | Trail, Var, deref, unify |
| 1054 | **infra** | `test_output_with_after` |  | Trail, Var, deref, unify |
| 1066 | **infra** | `test_output_empty_star` |  | Trail, Var, deref, unify |
| 1078 | **infra** | `test_output_unbound_star_builds_seglist` |  | Trail, Var, deref, unify |
| 1098 | **infra** | `test_output_already_bound_switches_to_input` |  | Trail, Var, deref, unify |

</details>

<details><summary><code>tests/test_compiler_goals.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 64 | **infra** | `test_known_var_gives_name` |  | Var, ast, term_to_ast_expr |
| 72 | **infra** | `test_body_only_var_gives_walrus` |  | Var, ast, term_to_ast_expr |
| 87 | **infra** | `test_body_only_var_same_name_on_second_call` |  | Var, ast, term_to_ast_expr |
| 96 | **infra** | `test_none_constant` |  | ast, term_to_ast_expr |
| 102 | **infra** | `test_true_constant` |  | ast, term_to_ast_expr |
| 108 | **infra** | `test_false_constant` |  | ast, term_to_ast_expr |
| 114 | **infra** | `test_int_constant` |  | ast, term_to_ast_expr |
| 120 | **infra** | `test_str_constant` |  | ast, term_to_ast_expr |
| 126 | **infra** | `test_float_constant` |  | ast, term_to_ast_expr |
| 132 | **infra** | `test_list_gives_ast_list` |  | ast, term_to_ast_expr |
| 138 | **infra** | `test_list_recurses_into_elements` |  | Var, ast, term_to_ast_expr |
| 147 | **infra** | `test_compound_gives_call_to_compound` |  | Compound, ast, term_to_ast_expr |
| 160 | **infra** | `test_dataclass_gives_call_to_cls` |  | Var, ast, term_to_ast_expr |
| 173 | **infra** | `test_unknown_type_raises` |  | term_to_ast_expr |
| 185 | **infra** | `test_int_gives_constant` |  | ast |
| 191 | **infra** | `test_float_gives_constant` |  | ast |
| 196 | **infra** | `test_var_gives_deref_call` |  | Var, ast |
| 205 | **infra** | `test_add_gives_binop_add` |  | Add, ast |
| 213 | **infra** | `test_sub` |  | Sub, ast |
| 219 | **infra** | `test_mult` |  | Mult, ast |
| 225 | **infra** | `test_negate` |  | Negate, ast |
| 231 | **infra** | `test_nested_add` |  | Add, ast |
| 247 | **infra** | `test_true_returns_k_stmts` |  | ast, compile_goal |
| 253 | **infra** | `test_false_returns_empty` |  | ast, compile_goal |
| 258 | **infra** | `test_is_gives_mark_if_undo` |  | Var, ast, compile_goal |
| 269 | **infra** | `test_and_chains_goals` |  | And, Var, ast, compile_goal |
| 284 | **infra** | `test_or_gives_two_branches` |  | Or, Var, ast, compile_goal |
| 296 | **infra** | `test_not_generates_nested_function` |  | Not, Var, ast, compile_goal |
| 307 | **infra** | `test_in_generates_for_loop` |  | Var, ast, compile_goal |
| 316 | **infra** | `test_not_in_generates_flag_and_for_loop` |  | Var, ast, compile_goal |
| 328 | **infra** | `test_unknown_goal_raises` |  | ast, compile_goal |
| 343 | **infra** | `test_empty_body_yields_none` |  | ast |
| 351 | **infra** | `test_single_goal_wraps_yield` |  | Var, ast |
| 364 | **infra** | `test_two_goals_chains_correctly` |  | Var, ast |
| 410 | **mixed** | `test_fact_matches_and_yields` | _drive, _run | Compound, Database, Trail, compile_predicate |
| 423 | **mixed** | `test_unify_var_with_literal` | _drive | Compound, Database, Trail, Var, compile_predicate, deref |
| 435 | **mixed** | `test_unify_both_vars` | _drive | Compound, Database, Trail, Var, compile_predicate, deref |
| 452 | **mixed** | `test_unify_fails_mismatch` | _drive, _run | Compound, Database, Trail, Var, compile_predicate |
| 463 | **mixed** | `test_bindings_undone_after_exhaustion` | _drive | Compound, Database, Trail, Var, compile_predicate, deref |
| 478 | **mixed** | `test_conjunction_two_is_goals` | _drive | Compound, Database, Trail, Var, compile_predicate, deref |
| 514 | **mixed** | `test_gt_succeeds` | _drive, _run | Trail |
| 520 | **mixed** | `test_gt_fails` | _drive, _run | Trail |
| 526 | **mixed** | `test_lt_succeeds` | _drive, _run | Compound, Database, Lt, Trail, Var, compile_predicate |
| 537 | **mixed** | `test_eq_structural` | _drive | Compound, Database, Trail, Var, compile_predicate |
| 555 | **mixed** | `test_lte_boundary` | _drive, _run | Compound, Database, LtE, Trail, Var, compile_predicate |
| 569 | **mixed** | `test_or_both_branches_explored` | _drive | Compound, Database, Or, Trail, Var, compile_predicate, deref |
| 587 | **mixed** | `test_or_left_fails_right_succeeds` | _drive | Compound, Database, Or, Trail, Var, compile_predicate, deref |
| 612 | **mixed** | `test_naf_succeeds_when_goal_fails` | _drive, _run | Call, Compound, Database, LoadName, Not, Trail, Var, compile_predicate |
| 632 | **mixed** | `test_naf_fails_when_goal_succeeds` | _drive, _run | Call, Compound, Database, LoadName, Not, Trail, Var, compile_predicate |
| 652 | **mixed** | `test_in_finds_all_members` | _drive | Compound, Database, Trail, Var, compile_predicate, deref |
| 670 | **mixed** | `test_in_with_ground_checks_membership` | _drive, _run | Compound, Database, Trail, Var, compile_predicate |
| 685 | **mixed** | `test_not_in_succeeds_when_absent` | _drive, _run | Compound, Database, Trail, Var, compile_predicate |
| 703 | **mixed** | `test_call_chain` | _drive | Call, Compound, Database, LoadName, Trail, Var, compile_predicate, deref |
| 723 | **mixed** | `test_multi_clause_predicate` | _drive, _run | Compound, Database, Trail, compile_predicate |
| 735 | **mixed** | `test_recursive_predicate` | _drive, _run | Call, Compound, Database, LoadName, Trail, Var, compile_predicate |
| 764 | **mixed** | `test_add_in_gt` | _drive, _run | Add, Compound, Database, Gt, Trail, Var, compile_predicate |

</details>

<details><summary><code>tests/test_compiler_optimizations.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 183 | **infra** | `test_single_clause_one_deref_per_arg` |  | Compound, Database, ast |
| 188 | **infra** | `test_two_clauses_still_one_deref_per_arg` |  | Compound, Database, ast |
| 194 | **infra** | `test_three_clauses_still_one_deref_per_arg` |  | Compound, Database, ast |
| 200 | **infra** | `test_five_clauses_arity3_one_deref_per_arg` |  | Compound, Database, ast |
| 206 | **infra** | `test_match_subjects_use_deref_locals` |  | Compound, Database, ast |
| 215 | **infra** | `test_deref_locals_assigned_before_first_match` |  | Compound, Database, ast |
| 237 | **infra** | `test_arity_zero_no_deref_assigns` |  | Compound, Database, ast |
| 248 | **infra** | `test_deref_count_scales_with_arity_not_clauses` |  | Compound, Database, ast |
| 318 | **infra** | `test_reified_eq_true_branch_is_unify_branch` |  | Var, ast |
| 336 | **infra** | `test_reified_eq_false_branch_is_dif_branch` |  | Var, ast |
| 354 | **infra** | `test_reified_eq_only_two_compilations` |  | Var, ast |
| 380 | **infra** | `test_reified_fd_true_branch_is_fd_then_stmts` |  | Gt, Var, ast |
| 397 | **infra** | `test_reified_fd_false_branch_is_fd_else_stmts` |  | Gt, Var, ast |
| 413 | **infra** | `test_reified_fd_only_one_reify_call` |  | Gt, Var, ast |
| 452 | **infra** | `test_or_has_exactly_one_mark_call` |  | ast |
| 462 | **infra** | `test_or_has_exactly_two_undo_calls` |  | ast |
| 472 | **infra** | `test_or_mark_is_first_statement` |  | ast |
| 486 | **infra** | `test_or_mark_variable_not_reassigned` |  | ast |
| 497 | **infra** | `test_nested_or_has_two_marks` |  | ast |
| 507 | **infra** | `test_or_correctness_still_holds` |  | Compound, Database, Or, Trail, Var, compile_predicate_trampoline, deref |
| 558 | **unknown** | `test_call_targets_collected` |  |  |
| 568 | **infra** | `test_head_types_collected` |  | make_predicate |
| 584 | **infra** | `test_py_thunks_collected` |  | Compound, Var |
| 603 | **unknown** | `test_single_pass_same_result_as_three_passes` |  |  |
| 638 | **infra** | `test_disp_key_in_globals_for_locked_callee` |  | Call, Compound, Database, LoadName, Var, compile_predicate_trampoline |
| 656 | **infra** | `test_no_get_dispatch_call_in_bytecode_for_locked` |  | Call, Compound, Database, LoadName, Var, compile_predicate_trampoline |
| 679 | **infra** | `test_unlocked_predicate_still_uses_get_dispatch` |  | Call, Compound, Database, LoadName, Var, _locked, compile_predicate_trampoline, make_predicate |
| 706 | **infra** | `test_locked_dispatch_correctness` |  | Call, Compound, Database, LoadName, Trail, Var, compile_predicate_trampoline |
| 797 | **infra** | `test_compound_keys_extracted_at_compile_time` |  | Compound, Var |
| 811 | **infra** | `test_compound_arg_builds_arg_index` |  | Compound, Var |
| 830 | **infra** | `test_compound_key_dispatch_circle` |  | Compound, Trail, Var, deref |
| 838 | **infra** | `test_compound_key_dispatch_rect` |  | Compound, Trail, Var, deref |
| 846 | **infra** | `test_compound_key_dispatch_wrong_functor` |  | Compound, Trail, Var, deref |
| 854 | **infra** | `test_compound_key_distinct_from_scalar_keys` |  | Compound, Var |
| 873 | **infra** | `test_predicate_meta_compound_key` |  | Compound, Var, make_predicate |
| 931 | **infra** | `test_secondary_index_builds_correctly` |  | Compound |
| 958 | **infra** | `test_all_ground_exact_match` |  | Trail, Var, deref |
| 965 | **infra** | `test_all_ground_no_match` |  | Trail, Var, deref |
| 972 | **infra** | `test_partial_ground_first_arg` |  | Trail, Var, deref |
| 981 | **infra** | `test_partial_ground_third_arg` |  | Trail, Var, deref |
| 990 | **infra** | `test_fully_unbound_returns_all` |  | Trail, Var, deref |
| 1043 | **infra** | `test_joint_index_built_for_high_coverage` |  | Compound |
| 1063 | **infra** | `test_analyze_joint_finds_improvement` |  | Compound |
| 1090 | **infra** | `test_both_args_ground_exact_match` |  | Trail, Var, deref |
| 1098 | **infra** | `test_both_args_ground_opposite` |  | Trail, Var, deref |
| 1106 | **infra** | `test_both_args_ground_no_match` |  | Trail, Var, deref |
| 1114 | **infra** | `test_first_arg_only_ground` |  | Trail, Var, deref |
| 1124 | **infra** | `test_second_arg_only_ground` |  | Trail, Var, deref |
| 1134 | **infra** | `test_fully_unbound_returns_all` |  | Trail, Var, deref |

</details>

<details><summary><code>tests/test_compiler_trampoline.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 131 | **infra** | `test_empty_body_yields_step_parent` |  | Database, ast |
| 143 | **infra** | `test_single_is_goal_wraps_step_parent` |  | Database, Var |
| 153 | **infra** | `test_two_is_goals_nest_correctly` |  | Database, Var |
| 167 | **infra** | `test_call_generates_three_stmts` |  | Call, Compound, Database, LoadName, Var, ast |
| 183 | **infra** | `test_while_body_ends_with_step_assign` |  | Call, Compound, Database, LoadName, Var, ast |
| 204 | **infra** | `test_no_clauses_zero_solutions` |  | Database, Trail, compile_predicate_trampoline |
| 211 | **infra** | `test_single_fact_matches` |  | Compound, Database, Trail, compile_predicate_trampoline |
| 217 | **infra** | `test_single_fact_no_match` |  | Compound, Database, Trail, compile_predicate_trampoline |
| 223 | **infra** | `test_two_facts_one_solution_each` |  | Compound, Database, Trail, compile_predicate_trampoline |
| 233 | **infra** | `test_unbound_arg_yields_solutions_in_order` |  | Compound, Database, Trail, Var, compile_predicate_trampoline, deref |
| 253 | **infra** | `test_fact_binds_var` |  | Compound, Database, Trail, Var, compile_predicate_trampoline, deref |
| 265 | **infra** | `test_bindings_undone_after_exhaustion` |  | Compound, Database, Trail, Var, compile_predicate_trampoline, deref |
| 283 | **infra** | `test_is_goal_binds_var` |  | Compound, Database, Trail, Var, compile_predicate_trampoline, deref |
| 294 | **infra** | `test_failed_is_goal_zero_solutions` |  | Compound, Database, Trail, compile_predicate_trampoline |
| 302 | **infra** | `test_conjunction_body_both_bound` |  | Compound, Database, Trail, Var, compile_predicate_trampoline, deref |
| 322 | **infra** | `test_chain_two_predicates` |  | Call, Compound, Database, LoadName, Trail, Var, compile_predicate_trampoline, deref |
| 345 | **infra** | `test_chain_multiplies_solutions` |  | Call, Compound, Database, LoadName, Trail, Var, compile_predicate_trampoline, deref |
| 379 | **infra** | `test_many_facts_no_stack_overflow` |  | Compound, Database, Trail, Var, compile_predicate_trampoline |
| 398 | **infra** | `test_wrap_many_facts_via_call` |  | Call, Compound, Database, LoadName, Trail, Var, compile_predicate_trampoline |
| 424 | **infra** | `test_or_two_branches` |  | Compound, Database, Or, Trail, Var, compile_predicate_trampoline, deref |
| 438 | **infra** | `test_or_left_fails_right_succeeds` |  | Compound, Database, Or, Trail, Var, compile_predicate_trampoline, deref |
| 459 | **infra** | `test_naf_succeeds_when_inner_fails` |  | Call, Compound, Database, LoadName, Not, Trail, Var, compile_predicate_trampoline |
| 473 | **infra** | `test_naf_fails_when_inner_succeeds` |  | Call, Compound, Database, LoadName, Not, Trail, Var, compile_predicate_trampoline |
| 496 | **infra** | `test_in_enumerates_list` |  | Compound, Database, Trail, Var, compile_predicate_trampoline, deref |
| 510 | **infra** | `test_not_in_succeeds_when_absent` |  | Compound, Database, Trail, Var, compile_predicate_trampoline |
| 522 | **infra** | `test_not_in_fails_when_present` |  | Compound, Database, Trail, Var, compile_predicate_trampoline |
| 540 | **infra** | `test_gt_succeeds` |  | Compound, Database, Gt, Trail, Var, compile_predicate_trampoline |
| 549 | **infra** | `test_gt_fails` |  | Compound, Database, Gt, Trail, Var, compile_predicate_trampoline |
| 558 | **infra** | `test_eq_structural_match` |  | Compound, Database, Trail, Var, compile_predicate_trampoline |
| 574 | **infra** | `test_arith_add_one` |  | Add, Compound, Database, Evaluate, Trail, Var, compile_predicate_trampoline, deref |
| 595 | **infra** | `test_always_fail_zero_solutions` |  | Database, Trail, compile_predicate_trampoline |
| 602 | **infra** | `test_always_fail_yields_tuple_none_done` |  | Database, Trail, compile_predicate_trampoline |
| 616 | **unknown** | `test_done_is_singleton` |  |  |
| 621 | **unknown** | `test_done_is_not_none` |  |  |
| 625 | **unknown** | `test_done_distinct_from_false` |  |  |
| 636 | **infra** | `test_lazy_recompile_fires_after_assertz` |  | Compound, Database, Trail, Var, compile_predicate_trampoline, deref, get_dispatch |
| 657 | **infra** | `test_lazy_recompile_via_db_dispatch` |  | Compound, Database, Trail, Var, compile_predicate_trampoline, deref, get_dispatch |

</details>

<details><summary><code>tests/test_compiler_v2.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 74 | **infra** | `test_empty_module` |  | EmbedTransformer, ast, parse |
| 82 | **infra** | `test_directive_items` |  | EmbedTransformer, ast, parse |
| 99 | **infra** | `test_import_from_item` |  | EmbedTransformer, ast, parse |
| 114 | **infra** | `test_import_module_item` |  | EmbedTransformer, ast, parse |
| 128 | **infra** | `test_module_declaration_item` |  | EmbedTransformer, ast, parse |
| 157 | **mixed** | `test_edge_graph` | call | EmbedTransformer, LogicModule, Var, ast, compile_module, deref, parse |
| 168 | **mixed** | `test_fibonacci` | call | EmbedTransformer, LogicModule, Var, ast, compile_module, deref, parse |
| 180 | **infra** | `test_dynamic_pred` |  | EmbedTransformer, LogicModule, ast, compile_module, parse |
| 188 | **mixed** | `test_facts_only` | call | EmbedTransformer, LogicModule, Var, ast, compile_module, parse |
| 198 | **mixed** | `test_tabled_fib` | call | EmbedTransformer, LogicModule, Var, ast, compile_module, deref, parse |
| 211 | **infra** | `test_shallow_pred` |  | EmbedTransformer, LogicModule, ast, compile_module, parse |
| 219 | **mixed** | `test_dcg_grammar` | call | EmbedTransformer, LogicModule, ast, compile_module, parse |
| 234 | **infra** | `test_empty_module` |  | LogicModule, compile_module |
| 241 | **infra** | `test_predicate_locking` |  | EmbedTransformer, LogicModule, PredicateMeta, _fields, _locked, ast, compile_module, parse |
| 253 | **infra** | `test_dynamic_not_locked` |  | EmbedTransformer, LogicModule, PredicateMeta, _locked, ast, compile_module, parse |

</details>

<details><summary><code>tests/test_continuation_search.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 8 | **unknown** | `test_empty` |  |  |
| 17 | **unknown** | `test_single_value` |  |  |
| 25 | **unknown** | `test_multiple_values` |  |  |
| 35 | **unknown** | `test_emission_order` |  |  |
| 45 | **unknown** | `test_non_integer_values` |  |  |
| 57 | **unknown** | `test_for_loop` |  |  |
| 71 | **unknown** | `test_iterable_once` |  |  |
| 85 | **unknown** | `test_emit_during_computation` |  |  |
| 97 | **unknown** | `test_function_stored` |  |  |
| 109 | **unknown** | `test_finished_not_visible` |  |  |
| 123 | **unknown** | `test_large_number_of_values` |  |  |
| 134 | **unknown** | `test_emit_callable_is_first_arg` |  |  |

</details>

<details><summary><code>tests/test_database.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 41 | **infra** | `test_compound_ground` |  | Compound |
| 46 | **infra** | `test_compound_arity_zero` |  | Compound |
| 51 | **infra** | `test_call_loadname` |  | Call, LoadName, Var |
| 56 | **infra** | `test_call_arity_zero` |  | Call, LoadName |
| 61 | **unknown** | `test_functor_dataclass` |  |  |
| 66 | **unknown** | `test_functor_dataclass_arity_one` |  |  |
| 71 | **unknown** | `test_bad_type_raises` |  |  |
| 76 | **infra** | `test_compound_var_functor_raises` |  | Compound, Var |
| 87 | **unknown** | `test_none_body` |  |  |
| 91 | **infra** | `test_single_goal` |  | Var |
| 96 | **infra** | `test_and_chain` |  | And, Var |
| 105 | **infra** | `test_right_nested_and` |  | And, Var |
| 113 | **unknown** | `test_true_literal` |  |  |
| 117 | **unknown** | `test_false_literal` |  |  |
| 126 | **infra** | `test_fact_has_empty_body` |  | Compound |
| 132 | **infra** | `test_rule_is_not_fact` |  | Compound, Var |
| 151 | **infra** | `test_assertz_and_clauses_for` |  | Database |
| 158 | **infra** | `test_asserta_prepends` |  | Database |
| 166 | **infra** | `test_is_defined_false_before_assert` |  | Database |
| 171 | **infra** | `test_is_defined_true_after_assert` |  | Database |
| 177 | **infra** | `test_clauses_for_undefined` |  | Database |
| 182 | **infra** | `test_get_dispatch_returns_none_when_absent` |  | Database, get_dispatch |
| 187 | **infra** | `test_retract_removes_clause` |  | Compound, Database |
| 195 | **infra** | `test_retract_undefined_predicate` |  | Compound, Database |
| 200 | **infra** | `test_multiple_functors_independent` |  | Database |
| 210 | **infra** | `test_multiple_clauses_same_predicate` |  | Database |
| 219 | **infra** | `test_repr` |  | Database |
| 233 | **infra** | `test_default_database_created` |  | Database, Module |
| 238 | **infra** | `test_assert_fact_compound` |  | Compound, Module |
| 246 | **infra** | `test_assert_fact_call` |  | Call, LoadName, Module |
| 255 | **infra** | `test_define_predicate_fact` |  | Compound, Module |
| 270 | **infra** | `test_define_predicate_with_body` |  | And, Compound, Module, Var |
| 287 | **infra** | `test_solve_returns_iterator` |  | Module |
| 296 | **infra** | `test_repr` |  | Module |
| 301 | **infra** | `test_functor_dataclass_head_in_define` |  | Module, Var |
| 320 | **unknown** | `test_functor_dataclass_returns_field_names` |  |  |
| 325 | **unknown** | `test_single_field_dataclass` |  |  |
| 330 | **infra** | `test_compound_returns_none` |  | Compound |
| 335 | **infra** | `test_call_returns_none` |  | Call, LoadName |
| 340 | **unknown** | `test_non_term_returns_none` |  |  |
| 349 | **infra** | `test_register_and_retrieve` |  | Database |
| 355 | **infra** | `test_unknown_predicate_returns_none` |  | Database |
| 360 | **infra** | `test_duplicate_identical_is_noop` |  | Database |
| 367 | **infra** | `test_conflicting_signature_warns` |  | Database |
| 376 | **infra** | `test_register_creates_signature_if_absent` |  | Database |
| 397 | **infra** | `test_dataclass_head_registers_signature` |  | Module, Var |
| 403 | **infra** | `test_compound_head_no_signature` |  | Compound, Module |
| 409 | **infra** | `test_call_head_no_signature` |  | Call, LoadName, Module |
| 415 | **infra** | `test_consistent_clauses_same_signature` |  | Module, Var |

</details>

<details><summary><code>tests/test_deep_indexing.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 233 | **mixed** | `test_mylen_empty` | call, load_clausal_module | Var, deref |
| 240 | **mixed** | `test_mylen_three` | call, load_clausal_module | Var, deref |
| 247 | **mixed** | `test_mylen_five` | call, load_clausal_module | Var, deref |
| 254 | **mixed** | `test_mylen_deterministic` | call, load_clausal_module | Var |
| 263 | **mixed** | `test_myappend_nil_left` | call, load_clausal_module | Var, deref |
| 270 | **mixed** | `test_myappend_two_plus_two` | call, load_clausal_module | Var, deref |
| 277 | **mixed** | `test_myappend_nil_right` | call, load_clausal_module | Var, deref |
| 284 | **mixed** | `test_myappend_split_enumerates_all` | call, load_clausal_module | Var, deref |
| 300 | **behavior** | `test_mymember_present` | call, load_clausal_module |  |
| 305 | **behavior** | `test_mymember_absent` | call, load_clausal_module |  |
| 310 | **mixed** | `test_mymember_enumerate` | call, load_clausal_module | Var, deref |
| 317 | **mixed** | `test_mymember_duplicates` | call, load_clausal_module | Var, deref |
| 326 | **mixed** | `test_mylast_singleton` | call, load_clausal_module | Var, deref |
| 333 | **mixed** | `test_mylast_three` | call, load_clausal_module | Var, deref |
| 340 | **mixed** | `test_mylast_deterministic` | call, load_clausal_module | Var |
| 348 | **mixed** | `test_mysumlist_empty` | call, load_clausal_module | Var, deref |
| 355 | **mixed** | `test_mysumlist_ten` | call, load_clausal_module | Var, deref |
| 364 | **mixed** | `test_mymax_singleton` | call, load_clausal_module | Var, deref |
| 371 | **mixed** | `test_mymax_three` | call, load_clausal_module | Var, deref |
| 380 | **mixed** | `test_myproduct_empty` | call, load_clausal_module | Var, deref |
| 387 | **mixed** | `test_myproduct_five` | call, load_clausal_module | Var, deref |
| 396 | **mixed** | `test_myprefix_enumerate` | call, load_clausal_module | Var, deref |
| 403 | **mixed** | `test_myprefix_no_extra_solutions` | call, load_clausal_module | Var |
| 425 | **infra** | `test_nil_and_cons_pred_has_isinstance_list_guard` |  | Compound, Database, Var, ast |
| 434 | **infra** | `test_three_list_clauses_has_isinstance_guard` |  | Compound, Database, Var, ast |
| 440 | **infra** | `test_single_clause_no_isinstance_guard` |  | Compound, Database, Var, ast |
| 448 | **infra** | `test_scalar_only_pred_has_no_isinstance_list_guard` |  | Compound, Database, Var, ast |
| 460 | **infra** | `test_isinstance_check_is_on_deref_local` |  | Compound, Database, Var, ast |
| 484 | **infra** | `test_list_pred_has_is_var_guard` |  | Compound, Database, Var, ast |
| 493 | **infra** | `test_is_var_guard_is_on_deref_local` |  | Compound, Database, Var, ast |
| 518 | **infra** | `test_top_level_match_count_less_than_clause_count` |  | Compound, Database, Var, ast |
| 534 | **infra** | `test_nil_and_cons_have_separate_match_blocks` |  | Compound, Database, Var, ast |
| 548 | **infra** | `test_isinstance_appears_exactly_once_for_one_list_position` |  | Compound, Database, Var, ast |
| 565 | **infra** | `test_arity_zero_unaffected` |  | Compound, Database, ast |
| 576 | **infra** | `test_arity_one_single_nil_clause` |  | Compound, Database, ast |
| 585 | **infra** | `test_all_var_heads_no_list_guard` |  | Compound, Database, Var, ast |
| 597 | **infra** | `test_list_pred_correctness_ground_nil` |  | Compound, Database, Trail, Var, compile_predicate_trampoline |
| 616 | **infra** | `test_list_pred_correctness_ground_cons` |  | Compound, Database, Trail, Var, compile_predicate_trampoline |
| 634 | **infra** | `test_list_pred_correctness_non_list_arg` |  | Compound, Database, Trail, Var, compile_predicate_trampoline |
| 652 | **infra** | `test_list_pred_correctness_var_arg` |  | Compound, Database, Trail, Var, compile_predicate_trampoline |
| 673 | **infra** | `test_structural_dispatch_does_not_suppress_backtracking` |  | Compound, Database, Trail, Var, compile_predicate_trampoline |

</details>

<details><summary><code>tests/test_destructive_reuse.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 99 | **infra** | `test_eligible_with_evaluate` |  | Compound, Evaluate, Var |
| 112 | **infra** | `test_alias_through_unify_not_eligible` |  | Compound, Var |
| 126 | **infra** | `test_transitive_alias_not_eligible` |  | Compound, Var |
| 140 | **infra** | `test_head_var_not_eligible` |  | Compound, Var |
| 150 | **infra** | `test_live_var_not_eligible` |  | Compound, Var |
| 166 | **infra** | `test_nondeterministic_prefix_not_eligible` |  | Call, Compound, Evaluate, LoadName, Var |
| 180 | **infra** | `test_deterministic_builtin_prefix_eligible` |  | Call, Compound, Evaluate, LoadName, Var |
| 202 | **infra** | `test_once_wrapped_prefix_eligible` |  | Call, Compound, Evaluate, LoadName, Var |
| 219 | **infra** | `test_eligible_dict_put_with_evaluate` |  | Compound, DictTerm, Evaluate, Var |
| 232 | **infra** | `test_dict_put_alias_not_eligible` |  | Compound, Var |
| 245 | **infra** | `test_eligible_set_union_with_evaluate` |  | Compound, Evaluate, SetTerm, Var |
| 258 | **infra** | `test_set_union_alias_not_eligible` |  | Compound, Var |
| 271 | **infra** | `test_source_literal_not_eligible` |  | Compound, Var |
| 281 | **infra** | `test_empty_body` |  | Compound |
| 289 | **infra** | `test_single_eligible_among_multiple` |  | Compound, Evaluate, Var |
| 304 | **infra** | `test_unify_body_only_vars_eligible` |  | Compound, Evaluate, Var |
| 319 | **infra** | `test_and_conjunction_alias_detected` |  | And, Call, Compound, Evaluate, Var, deref |
| 338 | **infra** | `test_and_flattening_exposes_eligible_call` |  | And, Compound, Evaluate, Var |
| 376 | **infra** | `test_unique_list_mutated_in_place` |  | Trail, Var, unify |
| 394 | **infra** | `test_shared_list_not_mutated` |  | Trail, Var, unify |
| 412 | **infra** | `test_fallback_for_string` |  | Trail, Var |
| 421 | **infra** | `test_nondeterministic_mode_falls_back` |  | Trail, Var, deref |
| 442 | **infra** | `test_unique_dict_mutated_in_place` |  | DictTerm, Trail, Var, deref, unify |
| 465 | **infra** | `test_shared_dict_not_mutated` |  | DictTerm, Trail, Var, deref, unify |
| 490 | **infra** | `test_unique_set_mutated_in_place` |  | SetTerm, Trail, Var, deref, unify |
| 513 | **infra** | `test_shared_set_not_mutated` |  | SetTerm, Trail, Var, deref, unify |
| 541 | **infra** | `test_append_with_evaluate` |  | Call, Compound, Database, Evaluate, LoadName, Trail, Var, compile_predicate_trampoline, deref |
| 561 | **infra** | `test_dict_put_with_evaluate` |  | Call, Compound, Database, DictTerm, Evaluate, LoadName, Trail, Var, compile_predicate_trampoline, deref |
| 582 | **infra** | `test_set_union_with_evaluate` |  | Call, Compound, Database, Evaluate, LoadName, SetTerm, Trail, Var, compile_predicate_trampoline, deref |
| 603 | **infra** | `test_alias_to_head_var_correct` |  | Call, Compound, Database, LoadName, Trail, Var, compile_predicate_trampoline, deref |
| 626 | **infra** | `test_head_var_not_optimized_correctness` |  | Call, Compound, Database, LoadName, Trail, Var, compile_predicate_trampoline, deref |
| 647 | **infra** | `test_chained_appends` |  | Call, Compound, Database, Evaluate, LoadName, Trail, Var, compile_predicate_trampoline, deref |
| 672 | **infra** | `test_multiple_clauses` |  | Call, Compound, Database, LoadName, Trail, Var, compile_predicate_trampoline, deref |

</details>

<details><summary><code>tests/test_directives.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 40 | **infra** | `test_mark_dynamic` |  | Database |
| 46 | **infra** | `test_not_dynamic_by_default` |  | Database |
| 51 | **infra** | `test_mark_discontiguous` |  | Database |
| 57 | **infra** | `test_not_discontiguous_by_default` |  | Database |
| 62 | **infra** | `test_mark_tabled` |  | Database |
| 68 | **infra** | `test_not_tabled_by_default` |  | Database |
| 73 | **infra** | `test_multiple_dynamic` |  | Database |
| 96 | **infra** | `test_dynamic_directive_generates_mark_dynamic_call` |  | EmbedTransformer, ast, parse |
| 103 | **infra** | `test_discontiguous_directive_generates_mark_call` |  | EmbedTransformer, ast, parse |
| 109 | **infra** | `test_table_directive_generates_mark_call` |  | EmbedTransformer, ast, parse |
| 115 | **infra** | `test_multiple_pred_arity_args` |  | EmbedTransformer, ast, parse |
| 122 | **infra** | `test_unknown_directive_raises` |  | EmbedTransformer, ast, parse |
| 127 | **infra** | `test_malformed_arg_no_arity_raises` |  | EmbedTransformer, ast, parse |
| 132 | **infra** | `test_malformed_arg_string_arity_raises` |  | EmbedTransformer, ast, parse |
| 137 | **infra** | `test_empty_args_raises` |  | EmbedTransformer, ast, parse |
| 147 | **infra** | `test_dynamic_predicate_is_unlocked` |  | PredicateMeta, _locked |
| 154 | **infra** | `test_dynamic_predicate_allows_runtime_assertz` |  | _clauses |
| 163 | **infra** | `test_static_predicate_is_locked` |  | PredicateMeta, _locked |
| 170 | **unknown** | `test_static_predicate_rejects_runtime_assertz` |  |  |
| 177 | **unknown** | `test_dynamic_flag_recorded_on_db` |  |  |
| 183 | **unknown** | `test_static_not_dynamic_on_db` |  |  |
| 194 | **infra** | `test_mark_shallow` |  | Database |
| 200 | **infra** | `test_not_shallow_by_default` |  | Database |
| 205 | **infra** | `test_multiple_shallow` |  | Database |
| 219 | **infra** | `test_shallow_directive_positional_form` |  | EmbedTransformer, ast, parse |
| 225 | **infra** | `test_shallow_directive_list_form` |  | EmbedTransformer, ast, parse |
| 231 | **infra** | `test_shallow_directive_list_multiple` |  | EmbedTransformer, ast, parse |
| 237 | **infra** | `test_shallow_directive_positional_multiple` |  | EmbedTransformer, ast, parse |
| 243 | **unknown** | `test_shallow_flag_recorded_on_db` |  |  |
| 249 | **behavior** | `test_shallow_predicate_is_queryable` | call |  |

</details>

<details><summary><code>tests/test_first_arg_index.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 49 | **infra** | `test_compound_literal` |  | Compound |
| 54 | **infra** | `test_compound_string` |  | Compound |
| 59 | **infra** | `test_compound_var` |  | Compound, Var |
| 65 | **infra** | `test_compound_var_with_unify` |  | Compound, Var |
| 72 | **infra** | `test_compound_var_with_unify_reversed` |  | Compound, Var |
| 79 | **infra** | `test_zero_arity` |  | Compound |
| 84 | **infra** | `test_predicate_meta_head` |  | PredicateMeta, Var |
| 94 | **infra** | `test_non_indexable_first_arg` |  | Compound |
| 100 | **infra** | `test_bool_key` |  | Compound |
| 105 | **infra** | `test_none_key` |  | Compound, Var |
| 112 | **infra** | `test_none_key_direct` |  | Compound |
| 123 | **infra** | `test_too_few_clauses` |  | Compound |
| 128 | **infra** | `test_zero_arity` |  | Compound |
| 133 | **infra** | `test_all_defaults` |  | Compound, Var |
| 142 | **infra** | `test_basic_partition` |  | Compound |
| 158 | **infra** | `test_mixed_with_defaults` |  | Compound, Var |
| 190 | **infra** | `test_ground_lookup` |  | Trail, Var, compile_predicate, deref |
| 203 | **infra** | `test_var_first_arg_enumerates_all` |  | Trail, Var, compile_predicate, deref |
| 216 | **infra** | `test_no_match_returns_empty` |  | Trail, Var, compile_predicate, deref |
| 229 | **infra** | `test_mixed_var_and_specific` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 260 | **infra** | `test_integer_keys` |  | Trail, Var, compile_predicate, deref |
| 279 | **infra** | `test_string_keys` |  | Trail, Var, compile_predicate, deref |
| 292 | **infra** | `test_below_threshold_no_index` |  | Trail, Var, compile_predicate, deref |
| 314 | **infra** | `test_ground_lookup` |  | Trail, Var, compile_predicate_trampoline, deref |
| 328 | **infra** | `test_var_first_arg_enumerates_all` |  | Trail, Var, compile_predicate_trampoline, deref |
| 342 | **infra** | `test_no_match_returns_empty` |  | Trail, Var, compile_predicate_trampoline, deref |
| 356 | **infra** | `test_mixed_var_and_specific` |  | Compound, Database, Trail, Var, compile_predicate_trampoline, deref |
| 384 | **infra** | `test_large_fact_table` |  | Trail, Var, compile_predicate_trampoline, deref |
| 406 | **infra** | `test_assertz_rebuilds_index_simple` |  | Compound, Database, Trail, Var, compile_predicate, deref, get_dispatch |
| 431 | **infra** | `test_assertz_rebuilds_index_trampoline` |  | Compound, Database, Trail, Var, compile_predicate_trampoline, deref, get_dispatch |
| 458 | **infra** | `test_predicate_meta_facts` |  | Database, PredicateMeta, Trail, Var, compile_predicate, deref |
| 497 | **infra** | `test_single_arity` |  | Compound, Database, Trail, compile_predicate, deref |
| 508 | **infra** | `test_duplicate_keys` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 520 | **infra** | `test_none_as_key` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 532 | **infra** | `test_bool_vs_int` |  | Compound, Database, Trail, compile_predicate, deref |

</details>

<details><summary><code>tests/test_free_threading.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 28 | **infra** | `test_unique_ids_under_contention` |  | Trail, Var, unify |
| 66 | **infra** | `test_independent_unify_threads` |  | Trail, Var, deref, unify |
| 97 | **infra** | `test_unify_shared_ground_terms` |  | Trail, Var, deref, unify |
| 128 | **infra** | `test_concurrent_register_unregister` |  | Trail, Var, unify |
| 148 | **infra** | `test_hook_fires_under_contention` |  | Trail, Var, unify |
| 190 | **mixed** | `test_concurrent_call` | call | Compound, Module, Trail, Var, compile_predicate_trampoline, deref, unify |
| 240 | **infra** | `test_two_trails_independent` |  | Trail, Var, deref, unify |
| 257 | **infra** | `test_cross_thread_trail_raises` |  | Trail, Var, unify |
| 281 | **infra** | `test_cross_thread_trail_undo_raises` |  | Trail, Var, unify |
| 312 | **unknown** | `test_variables_is_c_extension` |  |  |
| 323 | **unknown** | `test_trampoline_is_c_extension` |  |  |
| 333 | **unknown** | `test_trampoline_stepgen_has_parent` |  |  |

</details>

<details><summary><code>tests/test_groundness_dispatch.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 51 | **infra** | `test_position_zero` |  | Compound |
| 56 | **infra** | `test_position_one` |  | Compound |
| 61 | **infra** | `test_var_at_position` |  | Compound, Var |
| 67 | **infra** | `test_var_with_unify_at_position` |  | Compound, Var |
| 78 | **infra** | `test_out_of_range` |  | Compound |
| 84 | **infra** | `test_predicate_meta_second_field` |  | PredicateMeta, Var |
| 103 | **infra** | `test_position_zero_matches_first_arg` |  | Compound |
| 114 | **infra** | `test_position_one_index` |  | Compound, Var |
| 127 | **infra** | `test_no_index_all_vars` |  | Compound, Var |
| 136 | **infra** | `test_n_distinct` |  | Compound |
| 153 | **infra** | `test_both_positions_indexable` |  | Compound, Database |
| 165 | **infra** | `test_only_second_arg_indexable` |  | Compound, Var |
| 176 | **infra** | `test_sorted_by_selectivity` |  | Compound |
| 192 | **infra** | `test_empty_for_few_clauses` |  | Compound |
| 197 | **infra** | `test_three_arg_predicate` |  | Compound, Database |
| 211 | **infra** | `test_lookup_by_second_arg` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 227 | **infra** | `test_lookup_by_first_arg_still_works` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 242 | **infra** | `test_all_vars_enumerate` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 257 | **infra** | `test_both_args_ground` |  | Compound, Database, Trail, compile_predicate, deref |
| 275 | **infra** | `test_no_match_second_arg` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 290 | **infra** | `test_three_arg_middle_ground` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 305 | **infra** | `test_three_arg_last_ground` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 327 | **infra** | `test_color_all_modes` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 364 | **infra** | `test_var_headed_clauses_in_all_buckets` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 389 | **infra** | `test_true_catch_all_clauses` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 417 | **infra** | `test_assertz_rebuilds_multi_index` |  | Compound, Database, Trail, Var, compile_predicate, deref, get_dispatch |
| 445 | **infra** | `test_single_position_matches_v2_1_behavior` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 464 | **infra** | `test_below_threshold_no_dispatch` |  | Compound, Database, Trail, Var, compile_predicate, deref |
| 479 | **infra** | `test_second_field_lookup` |  | Database, PredicateMeta, Trail, Var, compile_predicate, deref |

</details>

<details><summary><code>tests/test_import.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 62 | **infra** | `test_module_is_logic_module` |  | LogicModule |
| 70 | **unknown** | `test_module_name_matches_import_name` |  |  |
| 82 | **unknown** | `test_edge_predicate_is_defined` |  |  |
| 89 | **unknown** | `test_reach_predicate_is_defined` |  |  |
| 96 | **infra** | `test_edge_dispatch_fn_is_compiled` |  | get_dispatch |
| 104 | **infra** | `test_reach_dispatch_fn_is_compiled` |  | get_dispatch |
| 112 | **unknown** | `test_edge_has_three_clauses` |  |  |
| 120 | **unknown** | `test_reach_has_two_clauses` |  |  |
| 131 | **infra** | `test_var_injected` |  | Var |
| 138 | **infra** | `test_compound_injected` |  | Compound |
| 145 | **infra** | `test_trail_injected` |  | Trail |
| 152 | **infra** | `test_unify_injected` |  | unify |
| 159 | **infra** | `test_deref_injected` |  | deref |
| 169 | **infra** | `test_edge_matches_1_2` |  | Trail, get_dispatch |
| 178 | **infra** | `test_edge_matches_2_3` |  | Trail, get_dispatch |
| 187 | **infra** | `test_edge_matches_1_3` |  | Trail, get_dispatch |
| 196 | **infra** | `test_edge_no_match_2_1` |  | Trail, get_dispatch |
| 205 | **infra** | `test_edge_no_match_9_9` |  | Trail, get_dispatch |
| 217 | **infra** | `test_reach_direct_edge` |  | Trail, get_dispatch |
| 227 | **infra** | `test_reach_transitive` |  | Trail, get_dispatch |
| 237 | **infra** | `test_reach_no_path_3_1` |  | Trail, get_dispatch |
| 250 | **infra** | `test_runtime_assertz_adds_clause` |  | Trail, get_dispatch |
| 277 | **behavior** | `test_call_edge_ground_success` | call |  |
| 293 | **behavior** | `test_call_edge_ground_failure` | call |  |
| 305 | **behavior** | `test_call_reach_ground_success` | call |  |
| 322 | **behavior** | `test_call_reach_no_solution` | call |  |
| 334 | **mixed** | `test_query_reach_ground_via_api` | query | Call, LoadName |
| 348 | **mixed** | `test_once_reach_ground_success` | once | Call, LoadName |
| 362 | **mixed** | `test_once_reach_failure_returns_none` | once | Call, LoadName |
| 376 | **infra** | `test_module_solve_method_on_imported` |  | Call, LoadName |
| 389 | **mixed** | `test_solve_ground_edge_goal` | solve | Call, LoadName |
| 403 | **behavior** | `test_call_unknown_predicate_raises` | call |  |

</details>

<details><summary><code>tests/test_listing.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 72 | **infra** | `test_no_clauses` |  | Trail |
| 78 | **infra** | `test_single_fact` |  | Trail |
| 86 | **infra** | `test_multiple_facts` |  | Trail |
| 94 | **infra** | `test_fact_with_ground_head` |  | Trail |
| 101 | **infra** | `test_instance_resolves_to_class` |  | Trail |
| 109 | **infra** | `test_non_predicate_error` |  | Trail |
| 116 | **infra** | `test_fact_format_ends_with_dot` |  | Trail |
| 123 | **infra** | `test_clause_count_in_header` |  | Trail |
| 134 | **infra** | `test_simple_string` |  | Trail |
| 139 | **infra** | `test_integer` |  | Trail |
| 144 | **infra** | `test_list` |  | Trail |
| 151 | **infra** | `test_nested_list` |  | Trail |
| 157 | **infra** | `test_unbound_var` |  | Trail, Var |

</details>

<details><summary><code>tests/test_phase5_builtins.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 53 | **mixed** | `test_basic` | solve | Call, LoadName, Module, Trail, Var, deref |
| 59 | **mixed** | `test_coprime` | solve | Call, LoadName, Module, Trail, Var, deref |
| 65 | **mixed** | `test_with_zero` | solve | Call, LoadName, Module, Trail, Var, deref |
| 71 | **mixed** | `test_negative` | solve | Call, LoadName, Module, Trail, Var, deref |
| 77 | **mixed** | `test_unbound_fails` | solve | Call, LoadName, Module, Trail, Var |
| 84 | **mixed** | `test_basic` | solve | Call, LoadName, Module, Trail, Var, deref |
| 90 | **mixed** | `test_zero_exp` | solve | Call, LoadName, Module, Trail, Var, deref |
| 96 | **mixed** | `test_mod_zero_fails` | solve | Call, LoadName, Module, Trail, Var |
| 101 | **mixed** | `test_unbound_fails` | solve | Call, LoadName, Module, Trail, Var |
| 108 | **mixed** | `test_zero` | solve | Call, LoadName, Module, Trail, Var, deref |
| 114 | **mixed** | `test_255` | solve | Call, LoadName, Module, Trail, Var, deref |
| 120 | **mixed** | `test_power_of_two` | solve | Call, LoadName, Module, Trail, Var, deref |
| 126 | **mixed** | `test_negative_fails` | solve | Call, LoadName, Module, Trail, Var |
| 133 | **mixed** | `test_one` | solve | Call, LoadName, Module, Trail, Var, deref |
| 139 | **mixed** | `test_eight` | solve | Call, LoadName, Module, Trail, Var, deref |
| 145 | **mixed** | `test_255` | solve | Call, LoadName, Module, Trail, Var, deref |
| 151 | **mixed** | `test_zero_fails` | solve | Call, LoadName, Module, Trail, Var |
| 158 | **mixed** | `test_one` | solve | Call, LoadName, Module, Trail, Var, deref |
| 164 | **mixed** | `test_twelve` | solve | Call, LoadName, Module, Trail, Var, deref |
| 170 | **mixed** | `test_eight` | solve | Call, LoadName, Module, Trail, Var, deref |
| 176 | **mixed** | `test_zero_fails` | solve | Call, LoadName, Module, Trail, Var |
| 214 | **infra** | `test_abs_quantity` |  | Quantity, Var |
| 226 | **infra** | `test_sign_quantity_positive` |  | Var |
| 234 | **infra** | `test_sign_quantity_negative` |  | Var |
| 244 | **infra** | `test_max_quantity` |  | Var |
| 253 | **infra** | `test_min_quantity` |  | Var |
| 262 | **infra** | `test_max_mismatched_dims_raises` |  | Var |
| 273 | **infra** | `test_plus_quantity` |  | Var |
| 282 | **infra** | `test_plus_mismatched_dims_raises` |  | Var |
| 292 | **infra** | `test_gcd_quantity` |  | Quantity, Var |
| 302 | **infra** | `test_gcd_mismatched_dims_raises` |  | Var |
| 312 | **infra** | `test_gcd_mixed_quantity_plain_raises` |  | Var |
| 321 | **infra** | `test_lcm_mixed_quantity_plain_raises` |  | Var |
| 331 | **infra** | `test_lcm_quantity` |  | Quantity, Var |
| 343 | **infra** | `test_divmod_quantity` |  | Quantity, Trail, Var, deref |
| 365 | **mixed** | `test_basic_partition` | solve | Call, LoadName, Module, Trail, Var, deref |
| 377 | **mixed** | `test_all_match` | solve | Call, LoadName, Module, Trail, Var, deref |
| 387 | **mixed** | `test_none_match` | solve | Call, LoadName, Module, Trail, Var, deref |
| 397 | **mixed** | `test_empty_list` | solve | Call, LoadName, Module, Trail, Var, deref |
| 437 | **unknown** | `test_with_reified_eq` |  |  |
| 443 | **unknown** | `test_empty_list` |  |  |
| 449 | **unknown** | `test_none_match` |  |  |
| 455 | **unknown** | `test_all_match` |  |  |
| 487 | **unknown** | `test_with_reified_eq` |  |  |
| 493 | **unknown** | `test_empty_list` |  |  |
| 499 | **unknown** | `test_all_true` |  |  |
| 505 | **unknown** | `test_all_false` |  |  |
| 516 | **mixed** | `test_range` | solve | Call, LoadName, Module, Trail, Var, deref |
| 522 | **mixed** | `test_single` | solve | Call, LoadName, Module, Trail, Var, deref |
| 528 | **mixed** | `test_empty_fails` | solve | Call, LoadName, Module, Trail, Var |
| 533 | **mixed** | `test_shorthand` | solve | Call, LoadName, Module, Trail, Var, deref |
| 539 | **mixed** | `test_shorthand_one` | solve | Call, LoadName, Module, Trail, Var, deref |
| 545 | **mixed** | `test_unbound_fails` | solve | Call, LoadName, Module, Trail, Var |
| 552 | **mixed** | `test_both_ground_equal` | solve | Call, LoadName, Module, Trail |
| 557 | **mixed** | `test_both_ground_unequal` | solve | Call, LoadName, Module, Trail |
| 562 | **mixed** | `test_generate_from_first` | solve | Call, LoadName, Module, Trail, Var, deref |
| 573 | **mixed** | `test_generate_from_second` | solve | Call, LoadName, Module, Trail, Var, deref |
| 584 | **mixed** | `test_empty_lists` | solve | Call, LoadName, Module, Trail |
| 591 | **mixed** | `test_2x2` | solve | Call, LoadName, Module, Trail, Var, deref |
| 597 | **mixed** | `test_2x3` | solve | Call, LoadName, Module, Trail, Var, deref |
| 603 | **mixed** | `test_empty` | solve | Call, LoadName, Module, Trail, Var, deref |
| 609 | **mixed** | `test_non_rectangular_fails` | solve | Call, LoadName, Module, Trail, Var |
| 619 | **mixed** | `test_basic` | solve | Call, LoadName, Module, Trail, Var, deref |
| 629 | **mixed** | `test_all_unique` | solve | Call, LoadName, Module, Trail, Var, deref |
| 637 | **mixed** | `test_empty` | solve | Call, LoadName, Module, Trail, Var, deref |
| 643 | **mixed** | `test_single_pair` | solve | Call, LoadName, Module, Trail, Var, deref |
| 650 | **mixed** | `test_order_preserved` | solve | Call, LoadName, Module, Trail, Var, deref |
| 664 | **mixed** | `test_integer_succeeds` | solve | Call, LoadName, Module, Trail |
| 669 | **mixed** | `test_integer_string_throws` | solve | Call, LoadName, Module, Trail |
| 676 | **mixed** | `test_unbound_throws_instantiation` | solve | Call, LoadName, Module, Trail, Var |
| 683 | **mixed** | `test_list_succeeds` | solve | Call, LoadName, Module, Trail |
| 688 | **mixed** | `test_number_float_succeeds` | solve | Call, LoadName, Module, Trail |
| 693 | **mixed** | `test_atom_int_throws` | solve | Call, LoadName, Module, Trail |
| 702 | **mixed** | `test_integer_succeeds` | solve | Call, LoadName, Module, Trail |
| 707 | **mixed** | `test_unbound_succeeds` | solve | Call, LoadName, Module, Trail, Var |
| 712 | **mixed** | `test_wrong_type_throws` | solve | Call, LoadName, Module, Trail |
| 719 | **mixed** | `test_dict_succeeds` | solve | Call, DictTerm, LoadName, Module, Trail |
| 730 | **mixed** | `test_returns_float` | solve | Call, LoadName, Module, Trail, Var, deref |
| 739 | **mixed** | `test_monotonic` | solve | Call, LoadName, Module, Trail, Var, deref |
| 752 | **mixed** | `test_cpu_time` | solve | Call, LoadName, Module, Trail, Var, deref |
| 761 | **mixed** | `test_wall_time` | solve | Call, LoadName, Module, Trail, Var, deref |
| 770 | **mixed** | `test_enumerate` | solve | Call, LoadName, Module, Trail, Var |
| 782 | **mixed** | `test_unknown_key_fails` | solve | Call, LoadName, Module, Trail, Var |
| 792 | **mixed** | `test_ground_eq` | solve | Call, LoadName, Module, Trail |
| 798 | **mixed** | `test_ground_eq_fails` | solve | Call, LoadName, Module, Trail |
| 804 | **mixed** | `test_ground_lt` | solve | Call, LoadName, Module, Trail |
| 810 | **mixed** | `test_ground_lt_fails` | solve | Call, LoadName, Module, Trail |
| 816 | **mixed** | `test_empty_list` | solve | Call, LoadName, Module, Trail |
| 822 | **mixed** | `test_unify_value` | solve | Call, LoadName, Module, Trail, Var, deref |
| 832 | **mixed** | `test_ground` | solve | Call, LoadName, Module, Trail |
| 839 | **mixed** | `test_ground_fails` | solve | Call, LoadName, Module, Trail |
| 845 | **mixed** | `test_mismatched_lengths_fails` | solve | Call, LoadName, Module, Trail |
| 853 | **mixed** | `test_ground_index` | solve | Call, LoadName, Module, Trail, Var, deref |
| 861 | **mixed** | `test_ground_index_first` | solve | Call, LoadName, Module, Trail, Var, deref |
| 867 | **mixed** | `test_index_out_of_range_fails` | solve | Call, LoadName, Module, Trail, Var |
| 872 | **mixed** | `test_index_zero_fails` | solve | Call, LoadName, Module, Trail, Var |
| 879 | **mixed** | `test_valid_circuit` | solve | Call, LoadName, Module, Trail |
| 885 | **mixed** | `test_self_loop_fails` | solve | Call, LoadName, Module, Trail |
| 891 | **mixed** | `test_sub_tour_fails` | solve | Call, LoadName, Module, Trail |
| 897 | **mixed** | `test_valid_4_node` | solve | Call, LoadName, Module, Trail |
| 908 | **infra** | `test_match_exact` |  | Trail |
| 922 | **infra** | `test_match_with_rest` |  | Trail, Var, deref |
| 938 | **infra** | `test_no_match_fails` |  | Trail |
| 952 | **infra** | `test_empty_sequence` |  | Trail |
| 966 | **infra** | `test_too_short_fails` |  | Trail |
| 996 | **infra** | `test_sum_narrows_total` |  | Trail, Var |
| 1008 | **infra** | `test_sum_narrows_vars_from_total` |  | Trail, Var, deref |
| 1020 | **infra** | `test_sum_wipeout` |  | Trail, Var |
| 1029 | **infra** | `test_sum_lt_narrows` |  | Trail, Var |
| 1042 | **infra** | `test_sum_propagates_on_label` |  | Trail, Var, deref |
| 1056 | **infra** | `test_sum_ground_vars_unbound_value_eq` |  | Trail, Var, deref |
| 1064 | **infra** | `test_sum_ground_vars_unbound_value_lt` |  | Trail, Var |
| 1076 | **infra** | `test_sp_narrows_total` |  | Trail, Var |
| 1088 | **infra** | `test_sp_backward_narrows_vars` |  | Trail, Var, deref |
| 1101 | **infra** | `test_sp_negative_coeff` |  | Trail, Var |
| 1112 | **infra** | `test_sp_wipeout` |  | Trail, Var |
| 1123 | **infra** | `test_element_narrows_value_from_index_domain` |  | Trail, Var |
| 1135 | **infra** | `test_element_narrows_index_from_value` |  | Trail, Var, deref |
| 1145 | **infra** | `test_element_wipeout` |  | Trail, Var |
| 1153 | **infra** | `test_element_var_value_var_index` |  | Trail, Var |
| 1166 | **infra** | `test_element_narrows_bidirectionally` |  | FDVar, Trail, Var |
| 1183 | **infra** | `test_circuit_prunes_self_loops` |  | Trail, Var |
| 1200 | **infra** | `test_circuit_detects_forced_subtour` |  | Trail, Var |
| 1214 | **infra** | `test_circuit_forces_completion` |  | Trail, Var, deref |
| 1229 | **infra** | `test_circuit_all_solutions` |  | Trail, Var, deref |

</details>

<details><summary><code>tests/test_pycache.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 60 | **unknown** | `test_pyc_created` |  |  |
| 74 | **unknown** | `test_pyc_path_matches_source` |  |  |
| 86 | **unknown** | `test_source_to_code_skipped_on_cache_hit` |  |  |
| 104 | **unknown** | `test_modified_source_recompiles` |  |  |
| 130 | **mixed** | `test_query_from_cache` | call | Var, deref |
| 145 | **mixed** | `test_rules_from_cache` | call | Var, deref |
| 177 | **mixed** | `test_dynamic_assertz_after_cache` | call | Var, _locked, deref |
| 209 | **unknown** | `test_no_pyc_when_dont_write` |  |  |
| 232 | **infra** | `test_compile_called_once_per_predicate` |  | compile_predicate_trampoline |
| 263 | **infra** | `test_multiple_predicates_compiled_once_each` |  | compile_predicate_trampoline |

</details>

<details><summary><code>tests/test_search.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 79 | **mixed** | `test_member_enumerates_all` | call | Module, Var, deref |
| 86 | **mixed** | `test_member_check_present` | call | Module |
| 92 | **mixed** | `test_member_check_absent` | call | Module |
| 98 | **mixed** | `test_member_empty_list_fails` | call | Module, Var |
| 105 | **mixed** | `test_member_with_duplicates` | call | Module, Var, deref |
| 112 | **mixed** | `test_member_string_elements` | call | Module, Var, deref |
| 124 | **mixed** | `test_append_ground_check` | call | Module |
| 130 | **mixed** | `test_append_ground_check_fail` | call | Module |
| 136 | **mixed** | `test_append_compute_result` | call | Module, Var, deref |
| 143 | **mixed** | `test_append_empty_left` | call | Module, Var, deref |
| 150 | **mixed** | `test_append_empty_right` | call | Module, Var, deref |
| 157 | **mixed** | `test_append_both_empty` | call | Module, Var, deref |
| 164 | **mixed** | `test_append_split_mode` | call | Module, Var, deref |
| 176 | **mixed** | `test_append_left_unknown` | call | Module, Var, deref |
| 188 | **mixed** | `test_last_singleton` | call | Module, Var, deref |
| 195 | **mixed** | `test_last_multiple` | call | Module, Var, deref |
| 202 | **mixed** | `test_last_check_correct` | call | Module |
| 208 | **mixed** | `test_last_check_wrong` | call | Module |
| 214 | **mixed** | `test_last_strings` | call | Module, Var, deref |
| 226 | **mixed** | `test_reverse_empty` | call | Module, Var, deref |
| 233 | **mixed** | `test_reverse_singleton` | call | Module, Var, deref |
| 240 | **mixed** | `test_reverse_multiple` | call | Module, Var, deref |
| 247 | **mixed** | `test_reverse_check` | call | Module |
| 258 | **mixed** | `test_permutation_empty` | call | Module, Var, deref |
| 265 | **mixed** | `test_permutation_singleton` | call | Module, Var, deref |
| 272 | **mixed** | `test_permutation_two_elements` | call | Module, Var, deref |
| 279 | **mixed** | `test_permutation_three_elements_count` | call | Module, Var, deref |
| 286 | **mixed** | `test_permutation_three_all_distinct` | call | Module, Var, deref |
| 293 | **mixed** | `test_permutation_check_valid` | call | Module |
| 299 | **mixed** | `test_permutation_check_invalid` | call | Module |
| 310 | **mixed** | `test_between_enumerates` | call | Module, Var, deref |
| 317 | **mixed** | `test_between_single_value` | call | Module, Var, deref |
| 324 | **mixed** | `test_between_empty_range` | call | Module, Var |
| 331 | **mixed** | `test_between_check_in_range` | call | Module |
| 337 | **mixed** | `test_between_check_out_of_range` | call | Module |
| 343 | **mixed** | `test_between_negative` | call | Module, Var, deref |
| 375 | **infra** | `test_fib_0` |  | Module |
| 380 | **infra** | `test_fib_1` |  | Module |
| 385 | **infra** | `test_fib_2` |  | Module |
| 390 | **infra** | `test_fib_3` |  | Module |
| 395 | **infra** | `test_fib_5` |  | Module |
| 400 | **infra** | `test_fib_7` |  | Module |
| 405 | **infra** | `test_fib_10` |  | Module |
| 410 | **mixed** | `test_fib_no_solution_negative` | call | Module, Var |
| 544 | **unknown** | `test_queens_1` |  |  |
| 549 | **unknown** | `test_queens_2_no_solution` |  |  |
| 554 | **unknown** | `test_queens_3_no_solution` |  |  |
| 559 | **unknown** | `test_queens_4_count` |  |  |
| 564 | **unknown** | `test_queens_4_solutions_valid` |  |  |
| 575 | **unknown** | `test_queens_5_count` |  |  |
| 585 | **mixed** | `test_conjunction` | solve | And, Module, Trail, Var, deref |
| 598 | **mixed** | `test_disjunction` | solve | Module, Or, Trail, Var, deref |
| 611 | **mixed** | `test_naf_success` | solve | Module, Not, Trail |
| 618 | **mixed** | `test_naf_failure` | solve | Module, Not, Trail |
| 625 | **mixed** | `test_naf_with_unification` | solve | Module, Not, Trail, Var |
| 635 | **mixed** | `test_in_goal` | solve | Module, Trail, Var, deref |
| 644 | **mixed** | `test_not_in_goal_succeeds` | solve | Module, Trail, Var, unify |
| 657 | **mixed** | `test_arithmetic_comparison` | solve | Lt, Module, Trail |
| 663 | **mixed** | `test_arithmetic_comparison_fail` | solve | Lt, Module, Trail |
| 674 | **mixed** | `test_query_append` | query | Call, LoadName, Module, Var |
| 682 | **mixed** | `test_query_member_multiple` | query | Call, LoadName, Module, Var |
| 690 | **mixed** | `test_once_member` | once | Call, LoadName, Module, Var |
| 720 | **mixed** | `test_append_empty_left` | call | Var, deref |
| 727 | **mixed** | `test_append_nonempty` | call | Var, deref |
| 734 | **mixed** | `test_append_both_empty` | call | Var, deref |
| 741 | **mixed** | `test_append_base_clause_repeated_var` | call | Var, deref |
| 751 | **mixed** | `test_last_singleton` | call | Var, deref |
| 758 | **mixed** | `test_last_multi` | call | Var, deref |
| 767 | **mixed** | `test_append_split` | call | Var, deref |
| 784 | **mixed** | `test_length` | call | Var, deref |
| 801 | **mixed** | `test_first_extracts_head` | call | Var, deref |
| 809 | **behavior** | `test_has_pair_succeeds` | call |  |
| 815 | **behavior** | `test_has_pair_fails_singleton` | call |  |
| 821 | **behavior** | `test_has_pair_fails_empty` | call |  |
| 826 | **mixed** | `test_second_extracts_second` | call | Var, deref |
| 834 | **mixed** | `test_const_ignores_input` | call | Var, deref |
| 842 | **mixed** | `test_const_ignores_input_var` | call | Var, deref |
| 850 | **behavior** | `test_member_of_pair_first` | call |  |
| 857 | **behavior** | `test_member_of_pair_second` | call |  |
| 864 | **behavior** | `test_member_of_pair_neither_fails` | call |  |
| 871 | **mixed** | `test_last_anon_head_still_works` | call | Module, Var, deref |
| 886 | **mixed** | `test_split_empty` | call | Var, deref |
| 894 | **mixed** | `test_split_singleton` | call | Var, deref |
| 902 | **mixed** | `test_split_three` | call | Var, deref |
| 915 | **mixed** | `test_split3_fixed_head` | call | Var, deref |
| 930 | **mixed** | `test_around` | call | Var, deref |
| 945 | **mixed** | `test_split3way` | call | Var, deref |
| 963 | **mixed** | `test_split3way_empty` | call | Var, deref |
| 974 | **mixed** | `test_unbound_builds_seglist` | call | Var, deref |

</details>

<details><summary><code>tests/test_slg_termination.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 44 | **mixed** | `test_terminates_and_finds_all` | call | Var, deref |
| 53 | **behavior** | `test_single_hop` | call |  |
| 58 | **behavior** | `test_multi_hop` | call |  |
| 63 | **behavior** | `test_no_path` | call |  |
| 69 | **mixed** | `test_all_pairs` | call | Var, deref |
| 83 | **mixed** | `test_table_entries_complete` | call | Var |
| 117 | **behavior** | `test_reflexive` | call |  |
| 124 | **behavior** | `test_same_gen_siblings` | call |  |
| 130 | **behavior** | `test_same_gen_cousins` | call |  |
| 136 | **behavior** | `test_same_gen_shared_child` | call |  |
| 142 | **behavior** | `test_not_same_gen_different_levels` | call |  |
| 148 | **behavior** | `test_not_same_gen_parent_child` | call |  |
| 154 | **mixed** | `test_enumerate_cross_gen_pairs` | call | Var, deref |
| 174 | **mixed** | `test_table_entries_complete` | call | Var |
| 199 | **mixed** | `test_reach_a_from_1` | call | Var, deref |
| 208 | **mixed** | `test_reach_b_from_2` | call | Var, deref |
| 217 | **mixed** | `test_reach_a_from_3` | call | Var, deref |
| 226 | **mixed** | `test_mutual_cycle_terminates` | call | Var, deref |
| 235 | **unknown** | `test_both_tabled` |  |  |
| 240 | **mixed** | `test_table_entries_complete` | call | Var |

</details>

<details><summary><code>tests/test_template_compiler.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 54 | **infra** | `test_empty_dict_decorator_detected` |  | ast, parse |
| 59 | **infra** | `test_no_decorator_not_detected` |  | ast, parse |
| 64 | **infra** | `test_non_empty_dict_not_detected` |  | ast, parse |
| 69 | **infra** | `test_multiple_decorators_not_detected` |  | ast, parse |
| 74 | **infra** | `test_class_not_detected` |  | ast, parse |
| 85 | **infra** | `test_function_name` |  | ast, parse |
| 91 | **infra** | `test_argument_name` |  | ast, parse |
| 97 | **infra** | `test_name_in_expression` |  | ast, parse |
| 103 | **infra** | `test_multiple_substitutions` |  | ast, parse |
| 116 | **infra** | `test_default_parameter_values` |  | ast, parse |
| 126 | **infra** | `test_class_name_substitution` |  | ast, parse |
| 132 | **infra** | `test_attribute_name_not_substituted` |  | ast, parse |
| 146 | **infra** | `test_single_escape` |  | ast, parse |
| 163 | **infra** | `test_multi_escape` |  | ast, parse |
| 173 | **infra** | `test_star_escape` |  | ast, parse |
| 190 | **infra** | `test_comprehension_escape` |  | ast, parse |
| 209 | **infra** | `test_comprehension_with_filter` |  | ast, parse |
| 228 | **infra** | `test_escape_returns_list` |  | ast, parse |
| 237 | **infra** | `test_nested_if_else_escapes` |  | ast, parse |
| 261 | **infra** | `test_args_from_arguments` |  | ast, parse |
| 270 | **infra** | `test_args_from_single_arg` |  | ast, parse |
| 277 | **infra** | `test_args_from_tuple` |  | ast, parse |
| 285 | **infra** | `test_args_from_expression` |  | ast, parse |
| 299 | **infra** | `test_args_with_body_escape` |  | ast, parse |
| 329 | **infra** | `test_args_not_sole_param_raises` |  | ast, parse |
| 337 | **infra** | `test_args_no_default_raises` |  | ast, parse |
| 349 | **infra** | `test_simple_class` |  | ast, parse |
| 360 | **infra** | `test_class_with_base` |  | ast, parse |
| 371 | **infra** | `test_class_with_magic_bases` |  | ast, parse |
| 385 | **infra** | `test_class_with_magic_bases_single_expr` |  | ast, parse |
| 397 | **infra** | `test_class_with_magic_bases_tuple` |  | ast, parse |
| 410 | **infra** | `test_class_with_body_escapes` |  | ast, parse |
| 429 | **infra** | `test_class_with_methods_and_bases` |  | ast, parse |
| 457 | **infra** | `test_full_dataclass_expansion` |  | ast, parse |
| 494 | **infra** | `test_function_keeps_original_line` |  | ast, parse |
| 501 | **infra** | `test_escape_gets_original_line` |  | ast, parse |
| 523 | **unknown** | `test_non_template_function_unchanged` |  |  |
| 528 | **infra** | `test_template_with_no_subs` |  | ast, parse |
| 534 | **infra** | `test_compile_non_template_raises` |  | ast, parse |
| 540 | **unknown** | `test_multiple_templates_in_module` |  |  |
| 554 | **infra** | `test_escape_with_single_stmt_node` |  | ast, parse |
| 569 | **mixed** | `test_string_callable_becomes_name` | call | ast, parse |
| 582 | **mixed** | `test_string_callable_with_substitution` | call | ast, parse |
| 595 | **infra** | `test_identifier_string_callable_in_comp_escape` |  | ast, parse |
| 612 | **infra** | `test_nonidentifier_string_callable_in_comp_escape` |  | ast, parse |
| 629 | **infra** | `test_identifier_string_callable_in_single_escape` |  | ast, parse |
| 641 | **infra** | `test_nonidentifier_string_callable_in_single_escape` |  | ast, parse |
| 677 | **infra** | `test_basic_return_value` |  | ast, parse |
| 682 | **infra** | `test_name_from_node` |  | ast, parse |
| 687 | **infra** | `test_single_parameter` |  | ast, parse |
| 692 | **infra** | `test_multiple_parameters` |  | ast, parse |
| 697 | **infra** | `test_default_parameter` |  | ast, parse |
| 704 | **infra** | `test_globals_accessible` |  | ast, parse |
| 712 | **infra** | `test_globals_used_in_expression` |  | ast, parse |
| 720 | **infra** | `test_filename_in_code_object` |  | ast, parse |
| 726 | **infra** | `test_default_filename` |  | ast, parse |
| 731 | **infra** | `test_multiline_body` |  | ast, parse |
| 737 | **infra** | `test_varargs` |  | ast, parse |
| 743 | **infra** | `test_kwargs` |  | ast, parse |
| 748 | **infra** | `test_exception_propagates` |  | ast, parse |
| 755 | **infra** | `test_globals_dict_not_mutated` |  | ast, parse |
| 761 | **infra** | `test_async_functiondef` |  | ast, parse |
| 774 | **infra** | `test_basic_body_no_args` |  | ast, parse |
| 779 | **infra** | `test_name_assigned` |  | ast, parse |
| 784 | **infra** | `test_explicit_args` |  | ast, parse |
| 789 | **infra** | `test_default_args_means_no_parameters` |  | ast, parse |
| 795 | **infra** | `test_globals_accessible_in_body` |  | ast, parse |
| 803 | **infra** | `test_multiple_statements` |  | ast, parse |
| 809 | **infra** | `test_filename_in_code_object` |  | ast, parse |
| 814 | **infra** | `test_default_filename` |  | ast, parse |
| 819 | **infra** | `test_returns_annotation` |  | ast, parse |
| 825 | **infra** | `test_decorator_applied` |  | ast, parse |
| 832 | **infra** | `test_same_body_reused_for_two_functions` |  | ast, parse |
| 841 | **infra** | `test_integration_with_template` |  | ast, parse |

</details>

<details><summary><code>tests/test_term_expansion.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 71 | **infra** | `test_no_expansion_returns_same` |  | EmbedTransformer, LogicModule, ast, parse, run_term_expansion |
| 79 | **infra** | `test_empty_input` |  | run_term_expansion |
| 89 | **infra** | `test_detects_te_clause` |  | EmbedTransformer, LogicModule, ast, parse |
| 102 | **infra** | `test_non_te_not_detected` |  | EmbedTransformer, LogicModule, ast, parse |
| 114 | **infra** | `test_identity_expansion` |  | EmbedTransformer, LogicModule, ast, parse, run_term_expansion |
| 129 | **mixed** | `test_identity_via_fixture` | call | Var, deref |
| 146 | **infra** | `test_suppress_all` |  | EmbedTransformer, LogicModule, ast, parse, run_term_expansion |
| 158 | **unknown** | `test_suppress_via_fixture` |  |  |
| 171 | **infra** | `test_te_clauses_removed_from_output` |  | EmbedTransformer, LogicModule, ast, parse, run_term_expansion |
| 189 | **infra** | `test_duplicate_items` |  | EmbedTransformer, LogicModule, ast, parse, run_term_expansion |
| 202 | **mixed** | `test_duplicate_full_pipeline` | call | EmbedTransformer, LogicModule, Var, ast, compile_module, deref, parse |
| 225 | **infra** | `test_state_unmatched_passes_through` |  | EmbedTransformer, LogicModule, ast, parse, run_term_expansion |
| 243 | **infra** | `test_q_produces_call_node` |  | TermTransformer, ast, parse |
| 259 | **infra** | `test_q_shares_vars` |  | TermTransformer, ast, parse |
| 272 | **infra** | `test_directives_preserved` |  | EmbedTransformer, LogicModule, ast, parse |
| 286 | **mixed** | `test_no_expansion_full_pipeline` | call | EmbedTransformer, LogicModule, Var, ast, compile_module, deref, parse |
| 300 | **mixed** | `test_identity_expansion_full_pipeline` | call | EmbedTransformer, LogicModule, Var, ast, compile_module, deref, parse |
| 318 | **infra** | `test_suppression_full_pipeline` |  | EmbedTransformer, LogicModule, ast, compile_module, parse |
| 333 | **mixed** | `test_imported_te_via_fixture` | call | Var, deref |
| 363 | **unknown** | `test_imported_te_predicate_nodes_stored` |  |  |
| 379 | **infra** | `test_expansion_creates_new_functor` |  | EmbedTransformer, LogicModule, ast, parse, run_term_expansion |
| 400 | **mixed** | `test_new_functor_full_pipeline` | call | EmbedTransformer, LogicModule, Var, ast, compile_module, deref, parse |
| 427 | **infra** | `test_init_list_injection` |  | EmbedTransformer, LogicModule, ast, parse, run_term_expansion |
| 444 | **infra** | `test_final_list_injection` |  | EmbedTransformer, LogicModule, ast, parse, run_term_expansion |
| 457 | **mixed** | `test_init_final_full_pipeline` | call | EmbedTransformer, LogicModule, Var, ast, compile_module, deref, parse |

</details>

<details><summary><code>tests/test_term_html.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 10 | **unknown** | `test_term_html_int` |  |  |
| 17 | **unknown** | `test_term_html_float` |  |  |
| 24 | **unknown** | `test_term_html_str` |  |  |
| 31 | **infra** | `test_term_html_var` |  | Var |
| 38 | **unknown** | `test_term_html_list` |  |  |
| 47 | **unknown** | `test_term_html_nested_list` |  |  |
| 54 | **unknown** | `test_term_html_empty_list` |  |  |
| 60 | **unknown** | `test_term_html_bool` |  |  |
| 66 | **unknown** | `test_term_html_none` |  |  |
| 71 | **unknown** | `test_term_html_special_chars` |  |  |
| 79 | **unknown** | `test_term_html_ampersand_in_string` |  |  |
| 87 | **infra** | `test_term_html_compound` |  | Compound |
| 99 | **unknown** | `test_term_pformat_html_short` |  |  |
| 107 | **unknown** | `test_term_pformat_html_long` |  |  |
| 117 | **unknown** | `test_jupyter_css_has_required_classes` |  |  |
| 125 | **unknown** | `test_jupyter_css_has_style_tag` |  |  |

</details>

<details><summary><code>tests/test_term_inspection.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 48 | **mixed** | `test_copy_atom` | solve | Call, LoadName, Module, Trail, Var, deref |
| 54 | **mixed** | `test_copy_integer` | solve | Call, LoadName, Module, Trail, Var, deref |
| 60 | **mixed** | `test_copy_none` | solve | Call, LoadName, Module, Trail, Var, deref |
| 66 | **mixed** | `test_copy_list_ground` | solve | Call, LoadName, Module, Trail, Var, deref |
| 72 | **mixed** | `test_copy_compound_ground` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 83 | **mixed** | `test_copy_var_gets_fresh_var` | solve | Call, LoadName, Module, Trail, Var, deref |
| 94 | **mixed** | `test_copy_preserves_sharing` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 109 | **mixed** | `test_copy_fresh_var_distinct_from_original` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 121 | **mixed** | `test_copy_nested_compound` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 134 | **mixed** | `test_copy_list_with_vars` | solve | Call, LoadName, Module, Trail, Var, deref |
| 148 | **mixed** | `test_copy_bound_var` | solve | Call, LoadName, Module, Trail, Var, deref, unify |
| 159 | **mixed** | `test_copy_exactly_one_solution` | solve | Call, Compound, LoadName, Module, Trail, Var |
| 165 | **mixed** | `test_copy_no_side_effects_on_original` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 180 | **mixed** | `test_ground_term_empty` | solve | Call, LoadName, Module, Trail, Var, deref |
| 186 | **mixed** | `test_ground_compound_empty` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 192 | **mixed** | `test_single_var` | solve | Call, LoadName, Module, Trail, Var, deref |
| 204 | **mixed** | `test_compound_with_vars` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 217 | **mixed** | `test_repeated_var_only_once` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 229 | **mixed** | `test_left_to_right_order` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 240 | **mixed** | `test_list_term` | solve | Call, LoadName, Module, Trail, Var, deref |
| 253 | **mixed** | `test_bound_var_not_collected` | solve | Call, Compound, LoadName, Module, Trail, Var, deref, unify |
| 268 | **mixed** | `test_nested_vars` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 280 | **mixed** | `test_exactly_one_solution` | solve | Call, LoadName, Module, Trail, Var |
| 292 | **mixed** | `test_ground_term_no_vars` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 299 | **mixed** | `test_single_var` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 311 | **mixed** | `test_two_vars` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 323 | **mixed** | `test_start_offset` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 334 | **mixed** | `test_repeated_var_numbered_once` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 345 | **mixed** | `test_unbound_start_fails` | solve | Call, LoadName, Module, Trail, Var |
| 352 | **mixed** | `test_list_term` | solve | Call, Compound, LoadName, Module, Trail, Var, deref |
| 364 | **mixed** | `test_exactly_one_solution` | solve | Call, LoadName, Module, Trail, Var |
| 370 | **mixed** | `test_end_wrong_value_fails` | solve | Call, Compound, LoadName, Module, Trail, Var, unify |
| 383 | **mixed** | `test_bindings_undone_after_backtrack` | solve | Call, Compound, LoadName, Module, Trail, Var |
| 410 | **mixed** | `test_basic` | solve | Call, LoadName, Module, Trail, Var, deref |
| 417 | **mixed** | `test_sequential` | solve | Call, LoadName, Module, Trail, Var, deref |
| 426 | **mixed** | `test_different_prefixes` | solve | Call, LoadName, Module, Trail, Var, deref |
| 435 | **mixed** | `test_unbound_prefix_fails` | solve | Call, LoadName, Module, Trail, Var |
| 442 | **mixed** | `test_non_string_prefix_fails` | solve | Call, LoadName, Module, Trail, Var |
| 449 | **mixed** | `test_counter_survives_backtracking` | solve | Call, LoadName, Module, Trail, Var, deref |
| 459 | **mixed** | `test_atom_already_bound_unification` | solve | Call, LoadName, Module, Trail |
| 465 | **mixed** | `test_atom_already_bound_mismatch` | solve | Call, LoadName, Module, Trail |
| 471 | **mixed** | `test_thread_safety` | solve | Call, LoadName, Module, Trail, Var, deref |
| 499 | **mixed** | `test_copy_kwterm_ground` | solve | Call, KWTerm, LoadName, Module, Trail, Var, _fields, deref |
| 510 | **mixed** | `test_copy_kwterm_preserves_functor` | solve | Call, KWTerm, LoadName, Module, Trail, Var, deref |
| 518 | **mixed** | `test_copy_kwterm_var_field_gets_fresh_var` | solve | Call, KWTerm, LoadName, Module, Trail, Var, _fields, deref |
| 534 | **mixed** | `test_copy_kwterm_sharing_preserved` | solve | Call, KWTerm, LoadName, Module, Trail, Var, _fields, deref |
| 550 | **mixed** | `test_copy_kwterm_no_side_effects_on_original` | solve | Call, KWTerm, LoadName, Module, Trail, Var, deref |
| 571 | **mixed** | `test_copy_dictterm_ground` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 579 | **mixed** | `test_copy_dictterm_var_not_freshened` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 596 | **mixed** | `test_dictterm_vars_not_collected` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 617 | **infra** | `test_copy_seglist_var_not_freshened` |  | Var |
| 632 | **infra** | `test_seglist_vars_not_collected` |  | Var |

</details>

<details><summary><code>tests/test_term_rewriting.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 59 | **infra** | `test_integer` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 64 | **infra** | `test_float` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 69 | **infra** | `test_complex` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 74 | **infra** | `test_string` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 79 | **infra** | `test_bytes` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 84 | **infra** | `test_bool_true` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 90 | **infra** | `test_bool_false` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 96 | **infra** | `test_none` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 105 | **infra** | `test_ellipsis` |  | TermTransformer, ast, parse |
| 116 | **infra** | `test_bare_name_becomes_load_name` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 122 | **infra** | `test_logic_variable_first_use` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 129 | **infra** | `test_logic_variable_reuse` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 154 | **infra** | `test_binop` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 169 | **infra** | `test_unaryop` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 177 | **infra** | `test_bool_and` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 184 | **infra** | `test_bool_or` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 191 | **infra** | `test_bool_and_folded` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 216 | **infra** | `test_cmpop` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 223 | **infra** | `test_compare_chain` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 232 | **infra** | `test_walrus_is_simple` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 240 | **infra** | `test_walrus_is_arithmetic` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 248 | **infra** | `test_plain_eq_not_arith_constraint` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 258 | **infra** | `test_arrow_assign` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 268 | **infra** | `test_arrow_assign_with_spaces` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 278 | **infra** | `test_spaced_lt_negate_not_arrow` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 285 | **infra** | `test_arrow_body_requires_parens` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 302 | **infra** | `test_arrow_body_binop_with_parens` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 321 | **infra** | `test_arrow_body_pow_still_works` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 331 | **unknown** | `test_arrow_detection_no_positions` |  |  |
| 363 | **infra** | `test_arrow_detection_extra_whitespace` |  | parse |
| 392 | **infra** | `test_negative_literal_folding` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 406 | **infra** | `test_list_literal` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 414 | **infra** | `test_empty_list` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 420 | **infra** | `test_tuple_literal` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 426 | **infra** | `test_set_literal` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 432 | **infra** | `test_dict_literal` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 442 | **infra** | `test_call_positional` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 451 | **infra** | `test_call_keyword` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 461 | **infra** | `test_call_string_callable` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 471 | **infra** | `test_call_string_callable_keyword` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 480 | **infra** | `test_if_expr` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 488 | **infra** | `test_if_expr_rejects_two_args` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 494 | **infra** | `test_if_expr_ternary_rejected` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 500 | **infra** | `test_subscript` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 507 | **infra** | `test_starred` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 514 | **infra** | `test_list_comp` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 524 | **infra** | `test_lambda_syntax_rejected` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 532 | **infra** | `test_position_set` |  | DictTerm, SetTerm, TermTransformer, ast, parse |
| 542 | **infra** | `test_embed_double_dash` |  | DictTerm, EmbedTransformer, SetTerm, ast, parse |
| 551 | **infra** | `test_embed_double_dash_nested` |  | DictTerm, EmbedTransformer, SetTerm, ast, parse |
| 557 | **infra** | `test_embed_spaced_double_dash_not_escaped` |  | DictTerm, EmbedTransformer, SetTerm, ast, parse |
| 565 | **infra** | `test_embed_normal_code_unchanged` |  | DictTerm, EmbedTransformer, SetTerm, ast, parse |
| 573 | **infra** | `test_embed_trailing_comma_defines_fact` |  | DictTerm, EmbedTransformer, PredicateMeta, SetTerm, ast, parse |
| 598 | **infra** | `test_embed_dash_block_produces_simple_ast_terms` |  | DictTerm, EmbedTransformer, SetTerm, ast, parse |
| 613 | **infra** | `test_embed_tilde_block_expr_stmts` |  | DictTerm, EmbedTransformer, SetTerm, ast, parse |
| 628 | **infra** | `test_embed_tilde_block_return_stmt` |  | DictTerm, EmbedTransformer, SetTerm, ast, parse |
| 642 | **infra** | `test_embed_tilde_block_mixed` |  | DictTerm, EmbedTransformer, SetTerm, ast, parse |
| 673 | **infra** | `test_partial_term_unspecified_field_is_var` |  | PredicateMeta, ast, parse |
| 681 | **infra** | `test_partial_term_explicit_none_preserved` |  | PredicateMeta, ast, parse |
| 688 | **infra** | `test_partial_term_no_args_all_vars` |  | PredicateMeta, ast, parse |
| 696 | **infra** | `test_partial_term_fresh_vars_each_call` |  | PredicateMeta, ast, parse |
| 707 | **infra** | `test_anon_var_is_var` |  | TermTransformer, ast, parse |
| 719 | **infra** | `test_anon_var_fresh_each_occurrence` |  | TermTransformer, ast, parse |
| 736 | **infra** | `test_anon_var_not_reused_like_named_var` |  | TermTransformer, ast, parse |

</details>

<details><summary><code>tests/test_terms.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 47 | **infra** | `test_construction` |  | Compound |
| 53 | **infra** | `test_arity_zero` |  | Compound |
| 59 | **infra** | `test_var_functor` |  | Compound, Var |
| 65 | **infra** | `test_equality_same` |  | Compound |
| 69 | **infra** | `test_equality_different_functor` |  | Compound |
| 73 | **infra** | `test_equality_different_args` |  | Compound |
| 77 | **infra** | `test_equality_different_arity` |  | Compound |
| 81 | **infra** | `test_str_no_args` |  | Compound |
| 85 | **infra** | `test_str_with_args` |  | Compound |
| 89 | **infra** | `test_nested_str` |  | Compound |
| 95 | **infra** | `test_repr_is_dataclass_repr` |  | Compound |
| 109 | **unknown** | `test_int_is_term` |  |  |
| 115 | **unknown** | `test_float_is_term` |  |  |
| 120 | **unknown** | `test_str_is_term` |  |  |
| 125 | **unknown**† | `test_bool_true_is_term` |  |  |
| 129 | **unknown**† | `test_bool_false_is_term` |  |  |
| 133 | **unknown**† | `test_none_is_term` |  |  |
| 137 | **unknown** | `test_list_is_term` |  |  |
| 141 | **unknown** | `test_empty_list_is_term` |  |  |
| 145 | **unknown** | `test_bytes_is_term` |  |  |
| 149 | **unknown**† | `test_ellipsis_is_term` |  |  |
| 159 | **infra** | `test_empty_list_to_cons` |  | Compound |
| 166 | **infra** | `test_single_element` |  | Compound |
| 174 | **unknown** | `test_three_elements` |  |  |
| 185 | **infra** | `test_cons_to_list_empty` |  | Compound |
| 190 | **unknown** | `test_cons_to_list_single` |  |  |
| 195 | **unknown** | `test_roundtrip` |  |  |
| 200 | **unknown** | `test_roundtrip_empty` |  |  |
| 204 | **infra** | `test_cons_to_list_improper_raises` |  | Compound |
| 210 | **infra** | `test_cons_to_list_non_cons_raises` |  | Compound |
| 215 | **infra** | `test_non_nil_tail_raises` |  | Compound |
| 228 | **unknown**† | `test_none` |  |  |
| 232 | **unknown**† | `test_ellipsis` |  |  |
| 236 | **unknown**† | `test_true` |  |  |
| 240 | **unknown**† | `test_false` |  |  |
| 244 | **unknown** | `test_int` |  |  |
| 249 | **unknown** | `test_float` |  |  |
| 253 | **unknown** | `test_complex` |  |  |
| 258 | **unknown** | `test_str` |  |  |
| 262 | **unknown** | `test_bytes` |  |  |
| 266 | **unknown** | `test_list` |  |  |
| 270 | **unknown** | `test_nested_list` |  |  |
| 274 | **infra** | `test_var_unbound` |  | Var |
| 280 | **infra** | `test_compound` |  | Compound |
| 285 | **infra** | `test_kwterm` |  | KWTerm |
| 293 | **infra** | `test_is_node` |  | Var |
| 299 | **infra** | `test_and_node` |  | And |
| 304 | **infra** | `test_or_node` |  | Or |
| 309 | **infra** | `test_not_node` |  | Not |
| 314 | **infra** | `test_add_node` |  | Add |
| 319 | **infra** | `test_lt_node` |  | Lt |
| 324 | **unknown** | `test_eq_node` |  |  |
| 329 | **infra** | `test_call_node` |  | Call, LoadName |
| 334 | **infra** | `test_loadname_node` |  | LoadName |
| 338 | **infra** | `test_predicate_node` |  | Call, LoadName |
| 344 | **unknown** | `test_dataclass_fallback` |  |  |
| 352 | **infra** | `test_negate_node` |  | Negate |
| 357 | **unknown** | `test_invert_node` |  |  |
| 362 | **infra** | `test_arithmetic_ops` |  | FloorDiv, Mod, Mult, Pow, Sub |
| 371 | **unknown** | `test_bitwise_ops` |  |  |
| 380 | **infra** | `test_comparison_ops` |  | Gt, GtE, LtE |

</details>

<details><summary><code>tests/test_unify.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 59 | **infra** | `test_same_ground_succeeds` |  | Compound, Trail, structural_unify |
| 64 | **infra** | `test_different_functor_fails` |  | Compound, Trail, structural_unify |
| 69 | **infra** | `test_different_arity_fails` |  | Compound, Trail, structural_unify |
| 74 | **infra** | `test_unify_with_var_arg` |  | Compound, Trail, Var, deref, structural_unify |
| 81 | **infra** | `test_var_on_right_side` |  | Compound, Trail, Var, deref, structural_unify |
| 88 | **infra** | `test_var_var_in_compound` |  | Compound, Trail, Var, deref, structural_unify |
| 95 | **infra** | `test_nested_compound` |  | Compound, Trail, Var, deref, structural_unify |
| 104 | **infra** | `test_nested_mismatch_fails` |  | Compound, Trail, structural_unify |
| 111 | **infra** | `test_arity_zero` |  | Compound, Trail, structural_unify |
| 117 | **infra** | `test_trail_undo_on_failure` |  | Compound, Trail, Var, structural_unify |
| 138 | **infra** | `test_empty_lists` |  | Trail, structural_unify |
| 142 | **infra** | `test_same_ground_lists` |  | Trail, structural_unify |
| 146 | **infra** | `test_different_lengths_fail` |  | Trail, structural_unify |
| 150 | **infra** | `test_list_with_var` |  | Trail, Var, deref, structural_unify |
| 157 | **infra** | `test_list_partial_fail_undoes` |  | Trail, Var, structural_unify |
| 166 | **infra** | `test_nested_lists` |  | Trail, Var, deref, structural_unify |
| 178 | **infra** | `test_same_ground_succeeds` |  | Trail, structural_unify |
| 183 | **infra** | `test_field_mismatch_fails` |  | Trail, structural_unify |
| 188 | **infra** | `test_with_var_field` |  | Trail, Var, deref, structural_unify |
| 195 | **infra** | `test_var_on_both_sides` |  | Trail, Var, deref, structural_unify |
| 203 | **infra** | `test_different_types_fail` |  | Trail, structural_unify |
| 212 | **infra** | `test_nested_dataclass` |  | Trail, Var, deref, structural_unify |
| 221 | **infra** | `test_trail_undo_on_failure` |  | Trail, Var, structural_unify |
| 230 | **infra** | `test_three_field_dataclass` |  | Trail, Var, deref, structural_unify |
| 246 | **infra** | `test_same_ground_succeeds` |  | KWTerm, Trail, structural_unify |
| 253 | **infra** | `test_order_independent` |  | KWTerm, Trail, structural_unify |
| 261 | **infra** | `test_different_functor_fails` |  | KWTerm, Trail, structural_unify |
| 266 | **infra** | `test_different_keys_fail` |  | KWTerm, Trail, structural_unify |
| 271 | **infra** | `test_value_mismatch_fails` |  | KWTerm, Trail, structural_unify |
| 276 | **infra** | `test_with_var_field` |  | KWTerm, Trail, Var, deref, structural_unify |
| 283 | **infra** | `test_trail_undo_on_failure` |  | KWTerm, Trail, Var, structural_unify |
| 294 | **infra** | `test_extra_keys_in_one_fails` |  | KWTerm, Trail, structural_unify |
| 306 | **infra** | `test_top_level_var_binds` |  | Compound, Trail, Var, deref, structural_unify |
| 313 | **infra** | `test_var_var_binds` |  | Trail, Var, deref, structural_unify |
| 320 | **infra** | `test_var_on_right_binds` |  | Trail, Var, deref, structural_unify |
| 327 | **infra** | `test_bound_var_left` |  | Trail, Var, structural_unify, unify |
| 335 | **infra** | `test_bound_var_mismatch` |  | Trail, Var, structural_unify, unify |
| 349 | **infra** | `test_int_equal` |  | Trail, structural_unify |
| 353 | **infra** | `test_int_unequal` |  | Trail, structural_unify |
| 357 | **infra** | `test_str_equal` |  | Trail, structural_unify |
| 361 | **infra** | `test_str_unequal` |  | Trail, structural_unify |
| 365 | **infra** | `test_none_equal` |  | Trail, structural_unify |
| 369 | **infra** | `test_bool_equal` |  | Trail, structural_unify |
| 373 | **infra** | `test_mixed_types_fail` |  | Trail, structural_unify |

</details>

### docs

<details><summary><code>tests/test_doc_snippet_coverage.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 38 | **unknown** | `test_no_skip_blocks` |  |  |
| 55 | **behavior** | `test_no_raw_untested_blocks` | load_clausal_module |  |

</details>

<details><summary><code>tests/test_doc_snippet_integrity.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 54 | **unknown** | `test_all_snippet_files_exist` |  |  |
| 67 | **unknown** | `test_all_snippet_sections_exist` |  |  |
| 88 | **unknown** | `test_clausal_fixtures_have_tests` |  |  |

</details>

### misc

<details><summary><code>tests/test_io.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 47 | **infra** | `test_str_unbound` |  | Var |
| 54 | **infra** | `test_str_bound_int` |  | Trail, Var, unify |
| 61 | **infra** | `test_str_bound_string` |  | Trail, Var, unify |
| 69 | **infra** | `test_format_unbound` |  | Var |
| 75 | **infra** | `test_format_bound_int` |  | Trail, Var, unify |
| 82 | **infra** | `test_format_bound_string` |  | Trail, Var, unify |
| 89 | **infra** | `test_format_spec_float` |  | Trail, Var, unify |
| 96 | **infra** | `test_format_spec_int_padding` |  | Trail, Var, unify |
| 103 | **infra** | `test_fstring_interpolation` |  | Trail, Var, unify |
| 112 | **infra** | `test_fstring_with_unbound` |  | Trail, Var, unify |
| 121 | **infra** | `test_format_spec_unbound_ignores_spec` |  | Var |
| 128 | **infra** | `test_format_bound_none` |  | Trail, Var, unify |
| 135 | **infra** | `test_str_bound_list` |  | Trail, Var, unify |
| 142 | **infra** | `test_str_chain_deref` |  | Trail, Var, unify |
| 158 | **infra** | `test_write_string` |  | Trail |
| 164 | **infra** | `test_write_int` |  | Trail |
| 170 | **infra** | `test_write_var_bound` |  | Trail, Var, unify |
| 178 | **infra** | `test_write_fstring` |  | Trail, Var, unify |
| 186 | **infra** | `test_write_unbound_var` |  | Trail, Var |
| 193 | **infra** | `test_write_compound` |  | Compound, Trail |
| 199 | **infra** | `test_write_no_newline` |  | Trail |
| 205 | **infra** | `test_write_succeeds` |  | Trail |
| 216 | **infra** | `test_writeln_string` |  | Trail |
| 222 | **infra** | `test_writeln_int` |  | Trail |
| 228 | **infra** | `test_writeln_var_bound` |  | Trail, Var, unify |
| 236 | **infra** | `test_writeln_fstring` |  | Trail, Var, unify |
| 246 | **infra** | `test_writeln_succeeds` |  | Trail |
| 257 | **infra** | `test_print_term_int` |  | Trail |
| 263 | **infra** | `test_print_term_string` |  | Trail |
| 270 | **infra** | `test_print_term_list` |  | Trail |
| 276 | **infra** | `test_print_term_compound` |  | Compound, Trail |
| 283 | **infra** | `test_print_term_var_bound` |  | Trail, Var, unify |
| 291 | **infra** | `test_print_term_succeeds` |  | Trail |
| 302 | **infra** | `test_nl_outputs_newline` |  | Trail |
| 308 | **infra** | `test_nl_succeeds` |  | Trail |
| 319 | **infra** | `test_tab_spaces` |  | Trail |
| 325 | **infra** | `test_tab_zero` |  | Trail |
| 331 | **infra** | `test_tab_var_fails` |  | Trail, Var |
| 338 | **infra** | `test_tab_negative_no_output` |  | Trail |
| 350 | **infra** | `test_print_term_unbound_var` |  | Trail, Var |
| 362 | **infra** | `test_string_passthrough` |  | Trail, Var, deref |
| 371 | **infra** | `test_int_to_string` |  | Trail, Var, deref |
| 380 | **infra** | `test_var_bound` |  | Trail, Var, deref, unify |
| 391 | **infra** | `test_fstring` |  | Trail, Var, deref, unify |
| 402 | **infra** | `test_unbound_var` |  | Trail, Var, deref |
| 418 | **infra** | `test_int` |  | Trail, Var, deref |
| 427 | **infra** | `test_string_quoted` |  | Trail, Var, deref |
| 436 | **infra** | `test_list` |  | Trail, Var, deref |
| 445 | **infra** | `test_unbound_var` |  | Trail, Var, deref |
| 456 | **infra** | `test_compound` |  | Compound, Trail, Var, deref |
| 471 | **behavior** | `test_writeln_from_clausal` | call |  |
| 492 | **behavior** | `test_write_fstring_from_clausal` | call |  |
| 513 | **behavior** | `test_fstring_len_expression` | call |  |
| 534 | **behavior** | `test_fstring_arithmetic_expression` | call |  |
| 555 | **behavior** | `test_fstring_str_upper` | call |  |
| 576 | **mixed** | `test_writeln_with_backtracking` | call | Var |
| 600 | **behavior** | `test_fstring_format_spec_in_clausal` | call |  |
| 621 | **behavior** | `test_fstring_no_vars` | call |  |

</details>

<details><summary><code>tests/test_repl.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 33 | **unknown** | `test_format_bindings_empty` |  |  |
| 38 | **unknown** | `test_format_bindings_single` |  |  |
| 43 | **unknown** | `test_format_bindings_multiple` |  |  |
| 52 | **unknown** | `test_no_solutions` |  |  |
| 60 | **unknown** | `test_one_solution_enter_stops` |  |  |
| 70 | **unknown** | `test_two_solutions_enter_after_first` |  |  |
| 80 | **unknown** | `test_two_solutions_dot_after_first` |  |  |
| 89 | **unknown** | `test_two_solutions_space_advances` |  |  |
| 100 | **unknown** | `test_two_solutions_n_advances` |  |  |
| 119 | **unknown** | `test_esc_aborts` |  |  |
| 128 | **unknown** | `test_q_aborts` |  |  |
| 137 | **unknown** | `test_a_shows_all` |  |  |
| 146 | **unknown** | `test_three_solutions_next_then_stop` |  |  |
| 156 | **unknown** | `test_or_separator_between_solutions` |  |  |

</details>

<details><summary><code>tests/test_repl_integration.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 156 | **unknown** | `test_no_solutions_prints_false` |  |  |
| 161 | **unknown** | `test_single_solution_shows_binding` |  |  |
| 166 | **unknown** | `test_single_solution_exhausts_with_no_more_message` |  |  |
| 171 | **unknown** | `test_stop_after_first_with_enter` |  |  |
| 178 | **unknown** | `test_advance_with_space` |  |  |
| 185 | **unknown** | `test_show_all_with_a` |  |  |
| 193 | **unknown** | `test_abort_with_esc_shows_only_first` |  |  |
| 200 | **unknown** | `test_conjunction_two_goals` |  |  |
| 210 | **unknown** | `test_variables_auto_declared_uppercase` |  |  |
| 216 | **unknown** | `test_true_binding_shows_true` |  |  |
| 226 | **unknown** | `test_assignment_executes` |  |  |
| 235 | **unknown** | `test_import_then_query` |  |  |
| 246 | **infra** | `test_embed_name_produces_LoadName` |  | LoadName |
| 261 | **unknown** | `test_or_separator_between_solutions` |  |  |
| 266 | **unknown** | `test_no_blank_line_after_output` |  |  |
| 291 | **unknown** | `test_normal_exec_unchanged` |  |  |
| 299 | **unknown** | `test_single_expr_promoted_to_single_mode` |  |  |
| 315 | **unknown** | `test_multistatement_stays_exec` |  |  |
| 324 | **unknown** | `test_star_query_compiles` |  |  |
| 335 | **unknown** | `test_real_syntax_error_propagates` |  |  |
| 341 | **infra** | `test_embed_syntax_transforms` |  | LoadName |

</details>

<details><summary><code>tests/test_resolve_and_argkey.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 35 | **infra** | `test_fd_ne_var_vs_int` |  | Trail, Var |
| 48 | **infra** | `test_fd_ne_int_vs_var` |  | Trail, Var |
| 59 | **infra** | `test_fd_lt_var_vs_int` |  | Trail, Var |
| 70 | **infra** | `test_fd_le_var_vs_int` |  | Trail, Var |
| 81 | **infra**† | `test_fd_eq_var_vs_int` |  | Trail, Var, deref |
| 89 | **infra** | `test_fd_eq_var_vs_var` |  | Trail, Var |
| 105 | **infra** | `test_fd_gt_delegates_to_fd_lt` |  | Trail, Var |
| 116 | **infra** | `test_fd_ge_delegates_to_fd_le` |  | Trail, Var |
| 136 | **unknown** | `test_int_returns_self` |  |  |
| 140 | **unknown** | `test_str_returns_self` |  |  |
| 144 | **unknown** | `test_bool_true_returns_self` |  |  |
| 150 | **unknown** | `test_bool_false_returns_self` |  |  |
| 155 | **unknown** | `test_bool_not_equal_to_int` |  |  |
| 163 | **unknown** | `test_float_returns_self` |  |  |
| 167 | **unknown** | `test_none_returns_self` |  |  |
| 171 | **unknown** | `test_bytes_returns_self` |  |  |
| 175 | **infra** | `test_compound_returns_functor_arity` |  | Compound |
| 180 | **unknown** | `test_empty_string` |  |  |
| 184 | **unknown** | `test_large_int` |  |  |
| 201 | **infra** | `test_normal_unify_succeeds` |  | Trail, Var, deref, unify |
| 209 | **infra** | `test_normal_unify_oc_succeeds` |  | Trail, Var, deref |
| 216 | **infra** | `test_circular_unify_succeeds` |  | Trail, Var, deref, unify |
| 226 | **infra** | `test_circular_unify_oc_fails` |  | Trail, Var, deref |
| 236 | **infra** | `test_nested_circular_unify_succeeds` |  | Trail, Var, unify |
| 244 | **infra** | `test_nested_circular_unify_oc_fails` |  | Trail, Var, deref |
| 253 | **infra** | `test_var_var_unify` |  | Trail, Var, deref, unify |
| 263 | **infra** | `test_var_var_unify_oc` |  | Trail, Var, deref |
| 271 | **infra** | `test_list_unify` |  | Trail, Var, deref, unify |
| 279 | **infra** | `test_list_unify_oc` |  | Trail, Var, deref |
| 286 | **infra** | `test_list_circular_unify_succeeds` |  | Trail, Var, unify |
| 294 | **infra** | `test_list_circular_unify_oc_fails` |  | Trail, Var, deref |
| 303 | **infra** | `test_failure_rolls_back` |  | Trail, Var, deref, unify |
| 313 | **infra** | `test_failure_rolls_back_oc` |  | Trail, Var, deref |

</details>

<details><summary><code>tests/test_scryer_backend.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 135 | **behavior** | `test_conformity_parses` | query |  |
| 153 | **behavior** | `test_golden_pl_parses` | query |  |
| 175 | **behavior** | `test_simple_fact_query` | query |  |
| 186 | **behavior** | `test_simple_rule_query` | query |  |
| 200 | **behavior** | `test_recursive_rule` | query |  |
| 218 | **behavior** | `test_list_operations` | query |  |
| 233 | **behavior** | `test_arithmetic_evaluation` | query |  |
| 257 | **behavior** | `test_negation` | query |  |
| 273 | **behavior** | `test_unification` | query |  |
| 285 | **behavior** | `test_disjunction` | query |  |
| 301 | **behavior** | `test_findall` | query |  |
| 346 | **unknown** | `test_iso_arithmetic` |  |  |
| 353 | **unknown** | `test_iso_control` |  |  |
| 360 | **unknown** | `test_iso_unification` |  |  |
| 367 | **unknown** | `test_iso_list_operations` |  |  |
| 374 | **unknown** | `test_iso_type_checking` |  |  |
| 381 | **unknown** | `test_iso_term_manipulation` |  |  |
| 439 | **behavior** | `test_roundtrip_parses` | query |  |
| 455 | **unknown** | `test_roundtrip_execution` |  |  |
| 474 | **unknown** | `test_clpz_constraints` |  |  |
| 488 | **unknown** | `test_scryer_leq_operator` |  |  |
| 495 | **unknown** | `test_scryer_tabling` |  |  |
| 503 | **unknown** | `test_scryer_dif` |  |  |
| 510 | **unknown** | `test_scryer_member` |  |  |
| 517 | **unknown** | `test_scryer_cut` |  |  |
| 536 | **behavior** | `test_operator_precedence_iso` | query |  |
| 546 | **behavior** | `test_atom_quoting` | query |  |
| 555 | **behavior** | `test_string_handling` | query |  |
| 566 | **behavior** | `test_empty_list` | query |  |
| 575 | **behavior** | `test_list_cons_pattern` | query |  |
| 586 | **behavior** | `test_nested_compound` | query |  |
| 598 | **behavior** | `test_multiple_solutions` | query |  |
| 615 | **behavior** | `test_comparison_operators` | query |  |

</details>

<details><summary><code>tests/test_scryer_embedding.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 28 | **unknown** | `test_true` |  |  |
| 34 | **unknown** | `test_fail` |  |  |
| 41 | **unknown** | `test_fact_and_query` |  |  |
| 48 | **unknown** | `test_multiple_solutions` |  |  |
| 56 | **unknown** | `test_arithmetic` |  |  |
| 63 | **unknown** | `test_list_unification` |  |  |
| 70 | **infra** | `test_compound_term` |  | Compound |
| 79 | **unknown** | `test_no_bindings_goal` |  |  |
| 86 | **unknown** | `test_iterator_protocol` |  |  |
| 99 | **unknown** | `test_early_break` |  |  |
| 111 | **unknown** | `test_machine_busy_during_iteration` |  |  |
| 136 | **unknown** | `test_consult_clausal_facts` |  |  |
| 144 | **unknown** | `test_consult_clausal_rules` |  |  |
| 160 | **unknown** | `test_consult_clausal_arithmetic` |  |  |
| 167 | **unknown** | `test_consult_clausal_list_patterns` |  |  |
| 178 | **unknown** | `test_consult_file_clausal` |  |  |
| 189 | **unknown** | `test_consult_file_prolog` |  |  |
| 210 | **unknown** | `test_fibonacci` |  |  |
| 219 | **unknown** | `test_graph_reachable` |  |  |
| 237 | **unknown** | `test_separate_predicates_persist` |  |  |
| 249 | **unknown** | `test_dynamic_assertz_accumulates` |  |  |
| 260 | **unknown** | `test_multiple_queries_same_session` |  |  |
| 269 | **unknown** | `test_context_manager_cleanup` |  |  |
| 278 | **unknown** | `test_use_after_close_raises` |  |  |
| 295 | **unknown** | `test_large_integer` |  |  |
| 302 | **unknown** | `test_float_result` |  |  |
| 309 | **unknown** | `test_nested_list` |  |  |
| 316 | **unknown** | `test_empty_list` |  |  |
| 323 | **unknown** | `test_prolog_error_raises` |  |  |
| 340 | **unknown** | `test_basic_types` |  |  |
| 349 | **unknown** | `test_string_quoting` |  |  |
| 355 | **unknown** | `test_list` |  |  |
| 361 | **infra** | `test_compound` |  | Compound |
| 367 | **unknown** | `test_unsupported_type_raises` |  |  |

</details>

<details><summary><code>tests/test_scryer_raw.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 17 | **unknown** | `test_raw_machine_creates` |  |  |
| 24 | **unknown** | `test_raw_query_iteration` |  |  |
| 34 | **unknown** | `test_raw_arithmetic` |  |  |
| 42 | **unknown** | `test_raw_no_solutions` |  |  |
| 50 | **unknown** | `test_raw_multiple_solutions` |  |  |
| 59 | **unknown** | `test_raw_lazy_iteration` |  |  |
| 75 | **unknown** | `test_raw_machine_busy_while_iterating` |  |  |
| 91 | **unknown** | `test_raw_list` |  |  |
| 99 | **infra** | `test_raw_compound` |  | Compound |
| 109 | **unknown** | `test_raw_large_integer` |  |  |
| 117 | **unknown** | `test_raw_exception` |  |  |
| 127 | **unknown** | `test_raw_true_no_bindings` |  |  |
| 136 | **unknown** | `test_raw_nested_list` |  |  |
| 144 | **unknown** | `test_raw_empty_list` |  |  |
| 152 | **unknown** | `test_raw_float` |  |  |
| 160 | **unknown** | `test_raw_load_then_query_multiple_times` |  |  |

</details>

<details><summary><code>tests/test_segstring.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 23 | **infra** | `test_create` |  | Var |
| 31 | **unknown** | `test_repr` |  |  |
| 40 | **unknown** | `test_ground_returns_str` |  |  |
| 46 | **infra** | `test_bound_varseg_collapses` |  | Trail, Var, unify |
| 55 | **infra** | `test_unbound_returns_segstring` |  | Var |
| 63 | **unknown** | `test_empty_segments` |  |  |
| 69 | **unknown** | `test_adjacent_strings_merge` |  |  |
| 75 | **infra** | `test_varseg_bound_to_list_joins` |  | Trail, Var, unify |
| 84 | **infra** | `test_nested_segstring` |  | Trail, Var, unify |
| 94 | **infra** | `test_is_ground` |  | Var |
| 102 | **unknown** | `test_to_str` |  |  |
| 107 | **infra** | `test_to_str_raises_when_not_ground` |  | Var |
| 119 | **infra** | `test_ground_match` |  | Trail, unify |
| 124 | **infra** | `test_ground_mismatch` |  | Trail, unify |
| 129 | **infra** | `test_varseg_binds_to_substring` |  | Trail, Var, deref, unify |
| 137 | **infra** | `test_two_varseg` |  | Trail, Var, deref, unify |
| 146 | **infra** | `test_empty_match` |  | Trail, unify |
| 151 | **infra** | `test_varseg_empty_binding` |  | Trail, Var, deref, unify |
| 159 | **infra** | `test_string_vs_segstring_symmetric` |  | Trail, Var, deref, unify |
| 168 | **infra** | `test_segstring_vs_char_list` |  | Trail, unify |
| 175 | **infra** | `test_segstring_vs_char_list_with_var` |  | Trail, Var, unify |
| 184 | **infra** | `test_segstring_vs_wrong_list_fails` |  | Trail, unify |
| 193 | **infra** | `test_var_in_varseg` |  | Var |
| 199 | **infra** | `test_var_not_in_segstring` |  | Var |
| 209 | **infra** | `test_multiple_splits` |  | Trail, Var, deref |
| 223 | **infra** | `test_no_match` |  | Trail, Var |
| 232 | **infra** | `test_single_varseg` |  | Trail, Var, deref |
| 250 | **infra** | `test_single_star_binds_substring` |  | Trail, Var, deref, unify |
| 259 | **infra** | `test_multi_star_binds_substrings` |  | Trail, Var, deref, unify |
| 268 | **infra** | `test_star_binds_empty_substring` |  | Trail, Var, deref, unify |
| 276 | **infra** | `test_walk_handles_string_bound_varseg` |  | Trail, Var, unify |
| 287 | **infra** | `test_seglist_still_works_with_lists` |  | Trail, Var, deref, unify |
| 297 | **infra** | `test_multi_star_string_generator` |  | Trail, Var, deref |
| 318 | **infra** | `test_star_vars_bind_to_substrings` |  | Trail, Var, deref |
| 329 | **infra** | `test_fixed_elements_match_chars` |  | Trail, Var, deref |
| 342 | **infra** | `test_empty_string_target` |  | Trail, Var, deref |
| 353 | **infra** | `test_no_match` |  | Trail, Var |
| 369 | **infra** | `test_star_str_returns_str` |  | Trail, Var, unify |
| 379 | **infra** | `test_star_str_with_after` |  | Trail, Var, unify |
| 389 | **infra** | `test_star_list_returns_list` |  | Trail, Var, unify |
| 400 | **infra** | `test_star_ground_segstring_mixed` |  | Trail, Var, unify |
| 413 | **infra** | `test_star_nonground_segstring_mixed` |  | Var |
| 423 | **infra** | `test_star_nonground_segstring_all_str` |  | Var |
| 436 | **infra** | `test_all_str_returns_str` |  | Trail, Var, unify |
| 450 | **infra** | `test_single_char_fixed_returns_str` |  | Trail, Var, unify |
| 471 | **mixed** | `test_head_tail_string` | call | Var, deref |
| 487 | **infra** | `test_body_multi_star_string_direct` |  | Trail, Var, deref |

</details>

<details><summary><code>tests/test_simple_ast.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 27 | **infra** | `test_literals` |  | ast, parse |
| 41 | **infra** | `test_collections` |  | ast, parse |
| 53 | **infra** | `test_fstring` |  | ast, parse |
| 63 | **infra** | `test_no_expr_stmt` |  | ast, parse |
| 79 | **infra** | `test_name_context` |  | ast, parse |
| 89 | **infra** | `test_attr_context` |  | ast, parse |
| 99 | **infra** | `test_subscript_context` |  | ast, parse |
| 109 | **infra** | `test_starred` |  | ast, parse |
| 120 | **infra** | `test_destructuring` |  | ast, parse |
| 131 | **infra** | `test_binops` |  | ast, parse |
| 147 | **infra** | `test_boolops` |  | ast, parse |
| 159 | **infra** | `test_unaryops` |  | ast, parse |
| 168 | **infra** | `test_comparisons` |  | ast, parse |
| 187 | **infra** | `test_augmented_assign` |  | ast, parse |
| 205 | **infra** | `test_call` |  | ast, parse |
| 217 | **infra** | `test_ifexpr` |  | ast, parse |
| 222 | **infra** | `test_lambda` |  | ast, parse |
| 233 | **infra** | `test_yield` |  | ast, parse |
| 240 | **infra** | `test_walrus` |  | ast, parse |
| 245 | **infra** | `test_slice` |  | ast, parse |
| 256 | **infra** | `test_comprehensions` |  | ast, parse |
| 271 | **infra** | `test_parameters` |  | ast, parse |
| 290 | **infra** | `test_import_flattening` |  | ast, parse |
| 306 | **infra** | `test_delete_flattening` |  | ast, parse |
| 316 | **infra** | `test_compound_stmts` |  | ast, parse |
| 331 | **infra** | `test_async` |  | ast, parse |
| 342 | **infra** | `test_class` |  | ast, parse |
| 351 | **infra** | `test_decorators` |  | ast, parse |
| 358 | **infra** | `test_ann_assign` |  | ast, parse |
| 364 | **infra** | `test_raise` |  | ast, parse |
| 370 | **infra** | `test_assert` |  | ast, parse |
| 376 | **infra** | `test_global_nonlocal` |  | ast, parse |
| 382 | **infra** | `test_multi_assign` |  | ast, parse |
| 391 | **infra** | `test_match` |  | ast, parse |
| 424 | **infra** | `test_loc_preserved` |  | ast, parse |
| 431 | **infra** | `test_dump` |  | ast, parse |
| 437 | **unknown** | `test_children` |  |  |
| 464 | **unknown** | `test_call_copy` |  |  |
| 481 | **unknown** | `test_call_copy_list_field` |  |  |
| 492 | **infra** | `test_visit_children_list_field` |  | ast, parse |
| 504 | **unknown** | `test_visit_children_node_fields` |  |  |
| 516 | **infra** | `test_visit_children_optional_node` |  | ast, parse |
| 533 | **infra** | `test_transform_children_replaces_nodes` |  | ast, parse |
| 551 | **unknown** | `test_transform_children_identity` |  |  |
| 560 | **infra** | `test_transform_children_list_field` |  | ast, parse |
| 578 | **unknown** | `test_transform_fields` |  |  |
| 595 | **infra** | `test_yield_from` |  | ast, parse |
| 604 | **infra** | `test_await` |  | ast, parse |
| 613 | **infra** | `test_try_star` |  | ast, parse |
| 624 | **infra** | `test_type_alias` |  | ast, parse |
| 635 | **infra** | `test_type_params` |  | ast, parse |
| 649 | **infra** | `test_fstring_conversion_and_format_spec` |  | ast, parse |
| 660 | **infra** | `test_slice_partial` |  | ast, parse |
| 671 | **infra** | `test_compare_chain_shared_operand` |  | ast, parse |
| 684 | **infra** | `test_multi_for_comprehension` |  | ast, parse |
| 696 | **infra** | `test_for_clause_children` |  | ast, parse |
| 713 | **infra** | `test_match_star_and_as` |  | ast, parse |
| 736 | **infra** | `test_yield_bare` |  | ast, parse |
| 745 | **infra** | `test_exception_tuple` |  | ast, parse |
| 756 | **unknown** | `test_visit_dispatch` |  |  |
| 767 | **infra** | `test_big_real_code` |  | ast, parse |
| 852 | **infra** | `test_str_literals` |  | ast, parse |
| 870 | **infra** | `test_str_collections` |  | ast, parse |
| 884 | **infra** | `test_str_names_attrs` |  | ast, parse |
| 894 | **infra** | `test_str_star` |  | ast, parse |
| 905 | **infra** | `test_str_binops` |  | ast, parse |
| 922 | **infra** | `test_str_boolops` |  | ast, parse |
| 929 | **infra** | `test_str_unaryops` |  | ast, parse |
| 945 | **infra** | `test_str_comparisons` |  | ast, parse |
| 961 | **infra** | `test_str_call` |  | ast, parse |
| 970 | **infra** | `test_str_ifexpr` |  | ast, parse |
| 976 | **infra** | `test_str_walrus` |  | ast, parse |
| 982 | **infra** | `test_str_lambda` |  | ast, parse |
| 990 | **infra** | `test_str_params` |  | ast, parse |
| 1001 | **infra** | `test_str_yield` |  | ast, parse |
| 1012 | **infra** | `test_str_await` |  | ast, parse |
| 1019 | **infra** | `test_str_slice` |  | ast, parse |
| 1029 | **infra** | `test_str_comprehensions` |  | ast, parse |
| 1040 | **infra** | `test_str_fstring` |  | ast, parse |
| 1050 | **infra** | `test_str_combined` |  | ast, parse |

</details>

<details><summary><code>tests/test_solve.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 108 | **mixed** | `test_call_edge_direct` | call | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline, deref |
| 115 | **mixed** | `test_call_edge_multiple_sources` | call | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline, deref |
| 122 | **mixed** | `test_call_path_reachable_from_a` | call | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline, deref |
| 129 | **mixed** | `test_call_path_ground_success` | call | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 135 | **mixed** | `test_call_path_ground_failure` | call | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 141 | **mixed** | `test_call_unknown_predicate_raises` | call | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 147 | **mixed** | `test_call_yields_trail` | call | Call, Compound, LoadName, Module, Trail, Var, compile_predicate_trampoline |
| 155 | **mixed** | `test_call_uses_provided_trail` | call | Call, Compound, LoadName, Module, Trail, Var, compile_predicate_trampoline, deref |
| 166 | **mixed** | `test_call_member2_via_in` | call | Compound, Module, Var, compile_predicate_trampoline, deref |
| 173 | **mixed** | `test_call_lt_check_pass` | call | Compound, Lt, Module, Var, compile_predicate_trampoline |
| 179 | **mixed** | `test_call_lt_check_fail` | call | Compound, Lt, Module, Var, compile_predicate_trampoline |
| 190 | **mixed** | `test_solve_call_goal` | solve | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline, deref |
| 198 | **mixed** | `test_solve_and_goal` | solve | And, Call, Compound, LoadName, Module, Var, compile_predicate_trampoline, deref |
| 210 | **mixed** | `test_solve_true_goal` | solve | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 216 | **mixed** | `test_solve_false_goal` | solve | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 222 | **mixed** | `test_solve_is_goal` | solve | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline, deref |
| 230 | **mixed** | `test_solve_or_goal` | solve | Call, Compound, LoadName, Module, Or, Var, compile_predicate_trampoline, deref |
| 241 | **mixed** | `test_solve_not_goal_success` | solve | Call, Compound, LoadName, Module, Not, Var, compile_predicate_trampoline |
| 248 | **mixed** | `test_solve_not_goal_failure` | solve | Call, Compound, LoadName, Module, Not, Var, compile_predicate_trampoline |
| 255 | **mixed** | `test_solve_yields_trail` | solve | Call, Compound, LoadName, Module, Trail, Var, compile_predicate_trampoline |
| 264 | **mixed** | `test_solve_multiple_solutions_backtrack` | solve | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline, deref |
| 272 | **infra** | `test_module_solve_method` |  | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline, deref |
| 286 | **mixed** | `test_query_single_var` | query | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 294 | **mixed** | `test_query_multiple_solutions` | query | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 302 | **mixed** | `test_query_two_vars` | query | And, Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 314 | **mixed** | `test_query_failure_yields_nothing` | query | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 322 | **mixed** | `test_query_unbound_var_stays_var` | query | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 340 | **mixed** | `test_once_success` | once | Call, Compound, LoadName, Module, Trail, Var, compile_predicate_trampoline |
| 351 | **mixed** | `test_once_failure_returns_none` | once | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 359 | **mixed** | `test_once_only_first_solution` | once | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 370 | **mixed** | `test_once_true_succeeds` | once | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 376 | **mixed** | `test_once_false_fails` | once | Call, Compound, LoadName, Module, Var, compile_predicate_trampoline |
| 387 | **unknown** | `test_scalar` |  |  |
| 394 | **infra** | `test_unbound_var` |  | Var |
| 401 | **infra** | `test_bound_var` |  | Trail, Var, unify |
| 409 | **infra** | `test_list` |  | Trail, Var, unify |
| 417 | **infra** | `test_compound` |  | Compound, Trail, Var, unify |
| 427 | **infra** | `test_nested` |  | Trail, Var, unify |

</details>

<details><summary><code>tests/test_spacy_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 131 | **unknown** | `test_keys` |  |  |
| 137 | **unknown** | `test_apple_text` |  |  |
| 142 | **unknown** | `test_index` |  |  |
| 147 | **unknown** | `test_is_alpha_true` |  |  |
| 152 | **unknown** | `test_pos_propn` |  |  |
| 159 | **unknown** | `test_keys` |  |  |
| 166 | **unknown** | `test_apple_org` |  |  |
| 173 | **unknown** | `test_keys` |  |  |
| 180 | **unknown** | `test_apple_chunk` |  |  |
| 192 | **unknown** | `test_get_known_model` |  |  |
| 197 | **unknown** | `test_get_unknown_raises` |  |  |
| 202 | **infra** | `test_load_model_1` |  | Trail |
| 214 | **infra** | `test_load_model_2` |  | Trail |
| 226 | **infra** | `test_load_model_2_idempotent` |  | Trail |
| 238 | **infra** | `test_unload_model` |  | Trail |
| 250 | **infra** | `test_unload_nonexistent_fails` |  | Trail |
| 256 | **infra** | `test_current_model_enumerate` |  | Trail, Var, deref |
| 269 | **infra** | `test_current_model_check_known` |  | Trail |
| 281 | **infra** | `test_current_model_check_unknown` |  | Trail |
| 306 | **infra** | `test_process_returns_doc` |  | Trail, Var, deref |
| 315 | **infra** | `test_process_unknown_alias` |  | Trail, Var |
| 329 | **infra** | `test_token_2_yields_multiple` |  | Trail, Var |
| 342 | **infra** | `test_token_2_first_is_apple` |  | Trail, Var, deref |
| 357 | **infra** | `test_token_3_by_index` |  | Trail, Var, deref |
| 372 | **infra** | `test_token_3_out_of_range` |  | Trail, Var |
| 385 | **infra** | `test_token_3_iterate_with_index` |  | Trail, Var, deref |
| 401 | **infra** | `test_token_text` |  | Trail, Var, deref |
| 410 | **infra** | `test_token_list` |  | Trail, Var, deref |
| 436 | **infra** | `test_pos` |  | Trail, Var, deref |
| 444 | **infra** | `test_lemma` |  | Trail, Var, deref |
| 452 | **infra** | `test_dep` |  | Trail, Var, deref |
| 460 | **infra** | `test_head` |  | Trail, Var, deref |
| 468 | **infra** | `test_shape` |  | Trail, Var, deref |
| 476 | **infra** | `test_is_alpha_true` |  | Trail |
| 482 | **infra** | `test_is_alpha_false_for_punctuation` |  | Trail |
| 495 | **infra** | `test_is_stop` |  | Trail |
| 514 | **infra** | `test_entity_2_yields_entities` |  | Trail, Var, deref |
| 528 | **infra** | `test_entity_3_filter_by_label` |  | Trail, Var, deref |
| 542 | **infra** | `test_entity_3_unknown_label_empty` |  | Trail, Var |
| 555 | **infra** | `test_entity_list` |  | Trail, Var, deref |
| 572 | **infra** | `test_sentence_2_yields_sentences` |  | Trail, Var, deref |
| 586 | **infra** | `test_sentence_list` |  | Trail, Var, deref |
| 603 | **infra** | `test_identical_texts` |  | Trail, Var, deref |
| 613 | **infra** | `test_score_is_float` |  | Trail, Var, deref |
| 630 | **infra** | `test_noun_chunk_2_yields_chunks` |  | Trail, Var, deref |
| 644 | **infra** | `test_noun_chunk_has_keys` |  | Trail, Var, deref |
| 664 | **infra** | `test_single_arity_dispatch_direct` |  | _get_dispatch |
| 670 | **infra** | `test_multi_arity_dispatch_is_multi` |  | _get_dispatch |
| 676 | **unknown** | `test_repr` |  |  |
| 680 | **infra** | `test_multi_dispatch_wrong_arity_fails` |  | Trail |
| 697 | **unknown** | `test_re_exports` |  |  |
| 751 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_specialization.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 41 | **unknown** | `test_pattern_fields` |  |  |
| 51 | **unknown** | `test_has_base_and_recursive` |  |  |
| 57 | **unknown** | `test_no_pre_match_goals` |  |  |
| 62 | **unknown** | `test_no_post_match_goals` |  |  |
| 67 | **unknown** | `test_match_clause_found` |  |  |
| 72 | **unknown** | `test_append_found` |  |  |
| 77 | **unknown** | `test_one_recursive_call` |  |  |
| 82 | **unknown** | `test_variables_extracted` |  |  |
| 95 | **unknown** | `test_pattern_fields` |  |  |
| 105 | **infra** | `test_post_match_goals` |  | Evaluate |
| 117 | **unknown** | `test_pattern_fields` |  |  |
| 127 | **infra** | `test_pre_match_goals` |  | Evaluate, Gt |
| 140 | **unknown** | `test_pattern_fields` |  |  |
| 150 | **unknown** | `test_no_append` |  |  |
| 155 | **unknown** | `test_two_recursive_calls` |  |  |
| 160 | **unknown** | `test_no_pre_post_match_goals` |  |  |
| 174 | **unknown** | `test_cannot_specialize` |  |  |
| 183 | **unknown** | `test_explicit_program_arg` |  |  |
| 188 | **unknown** | `test_invalid_program_arg` |  |  |
| 222 | **infra** | `test_clause_count` |  | Var, _clauses |
| 229 | **infra** | `test_field_count` |  | Var, _fields |
| 237 | **mixed** | `test_solve_natnum_0` | _query, call | Var |
| 248 | **mixed** | `test_solve_natnum_s0` | _query, call | Var |
| 259 | **mixed** | `test_solve_natnum_ss0` | _query, call | Var |
| 274 | **infra** | `test_clause_count` |  | Var, _clauses |
| 281 | **mixed** | `test_solve_edge` | _query, call | Var |
| 291 | **mixed** | `test_solve_path_direct` | _query, call | Var |
| 301 | **mixed** | `test_solve_path_transitive` | _query, call | Var |
| 311 | **mixed** | `test_solve_no_path` | _query, call | Var |
| 325 | **infra** | `test_clause_count` |  | Var, _clauses |
| 332 | **infra** | `test_fields` |  | Var, _fields |
| 338 | **mixed** | `test_count_natnum_0` | call | Var, deref |
| 349 | **mixed** | `test_count_natnum_s0` | call | Var, deref |
| 362 | **mixed** | `test_count_natnum_ss0` | call | Var, deref |
| 379 | **mixed** | `test_count_edge` | call | Var, deref |
| 391 | **mixed** | `test_count_path_direct` | call | Var, deref |
| 403 | **mixed** | `test_count_path_transitive` | call | Var, deref |
| 419 | **infra** | `test_clause_count` |  | Var, _clauses |
| 425 | **infra** | `test_fields` |  | Var, _fields |
| 431 | **mixed** | `test_limit_natnum_s0_depth1_fails` | call | Var |
| 444 | **mixed** | `test_limit_natnum_s0_depth2_succeeds` | call | Var |
| 457 | **mixed** | `test_limit_natnum_ss0_depth2_fails` | call | Var |
| 469 | **mixed** | `test_limit_natnum_ss0_depth3_succeeds` | call | Var |
| 485 | **infra** | `test_clause_count` |  | Var, _clauses |
| 491 | **infra** | `test_fields` |  | Var, _fields |
| 497 | **mixed** | `test_tree_natnum_0` | call | Var, deref |
| 511 | **mixed** | `test_tree_natnum_s0` | call | Var, deref |
| 533 | **mixed** | `test_solve_natnum_equivalence` | _query, call | Var |
| 554 | **mixed** | `test_solve_count_equivalence` | call | Var, deref |
| 631 | **infra** | `test_natnum` |  | Var |
| 635 | **infra** | `test_graph` |  | Var |
| 639 | **infra** | `test_factorial` |  | Var |
| 643 | **infra** | `test_mixed` |  | Var |
| 651 | **infra** | `test_natnum_no_residual` |  | Var |
| 656 | **infra** | `test_graph_no_residual` |  | Var |
| 661 | **infra** | `test_factorial_has_residual` |  | Var |
| 666 | **infra** | `test_mixed_has_residual` |  | Var |
| 675 | **infra** | `test_clause_count` |  | Var, _clauses |
| 682 | **infra** | `test_fields` |  | Var, _fields |
| 689 | **mixed** | `test_factorial_0` | _query, call | Var |
| 700 | **mixed** | `test_factorial_1` | _query, call | Var |
| 711 | **mixed** | `test_factorial_3` | _query, call | Var |
| 722 | **mixed** | `test_factorial_5` | _query, call | Var |
| 733 | **mixed** | `test_factorial_wrong_result_fails` | _query, call | Var |
| 748 | **infra** | `test_clause_count` |  | Var, _clauses |
| 757 | **mixed** | `test_count_factorial_0` | call | Var, deref |
| 771 | **mixed** | `test_count_factorial_3` | call | Var, deref |
| 797 | **mixed** | `test_even_0` | _query, call | Var |
| 807 | **mixed** | `test_even_2` | _query, call | Var |
| 817 | **mixed** | `test_even_4` | _query, call | Var |
| 827 | **mixed** | `test_odd_1_fails` | _query, call | Var |
| 837 | **mixed** | `test_odd_3_fails` | _query, call | Var |
| 851 | **mixed** | `test_double_3` | _query, call | Var |
| 862 | **mixed** | `test_quadruple_3` | _query, call | Var |
| 873 | **mixed** | `test_quadruple_wrong_fails` | _query, call | Var |
| 888 | **infra** | `test_natnum_no_catchall` |  | Var, _clauses |
| 895 | **infra** | `test_graph_no_catchall` |  | Var, _clauses |
| 906 | **mixed** | `test_custom_handler` | _query, call | Var, deref |
| 943 | **mixed** | `test_factorial_known_results` | _query, call | Var |
| 960 | **mixed** | `test_factorial_query_result` | call | Var, deref |
| 986 | **mixed** | `test_limit_factorial_0_depth1` | call | Var |
| 1000 | **mixed** | `test_limit_factorial_1_depth2_fails` | call | Var |
| 1014 | **mixed** | `test_limit_factorial_1_high_depth` | call | Var |
| 1035 | **infra** | `test_var_embeds_var` |  | Var |
| 1041 | **infra** | `test_var_does_not_embed_constant` |  | Var |
| 1047 | **infra** | `test_constant_does_not_embed_var` |  | Var |
| 1053 | **unknown** | `test_equal_constants` |  |  |
| 1059 | **unknown** | `test_different_constants` |  |  |
| 1065 | **infra** | `test_same_functor_coupling` |  | Var |
| 1072 | **unknown** | `test_same_functor_args` |  |  |
| 1080 | **unknown** | `test_diving` |  |  |
| 1086 | **unknown** | `test_diving_nested` |  |  |
| 1092 | **infra** | `test_growth_detection` |  | Var |
| 1116 | **unknown** | `test_no_embed_different_arity` |  |  |
| 1122 | **infra** | `test_transitive_growth` |  | Var |
| 1134 | **unknown** | `test_constant_does_not_embed_compound` |  |  |
| 1141 | **unknown** | `test_compound_does_not_embed_constant` |  |  |
| 1150 | **unknown** | `test_empty_lookup` |  |  |
| 1156 | **unknown** | `test_register_and_lookup` |  |  |
| 1163 | **infra** | `test_register_var_pattern` |  | Var |
| 1172 | **unknown** | `test_different_functor_no_match` |  |  |
| 1179 | **unknown** | `test_multiple_registrations` |  |  |
| 1188 | **unknown** | `test_non_list_lookup` |  |  |
| 1195 | **unknown** | `test_entries_property` |  |  |
| 1208 | **infra** | `test_depth_0_same_as_shallow` |  | Var, _clauses |
| 1227 | **mixed** | `test_deep_natnum_produces_results` | _query, call | Var |
| 1241 | **mixed** | `test_deep_natnum_s0` | _query, call | Var |
| 1255 | **mixed** | `test_deep_factorial_base` | _query, call | Var |
| 1269 | **mixed** | `test_deep_factorial_1` | call | Var, deref |
| 1289 | **mixed** | `test_deep_count_natnum` | call | Var, deref |
| 1306 | **mixed** | `test_deep_graph_path` | _query, call | Var |
| 1323 | **infra** | `test_max_depth_respected` |  | Var, _clauses |
| 1337 | **mixed** | `test_equivalence_natnum` | _query, call | Var |
| 1365 | **mixed** | `test_equivalence_factorial` | call | Var, deref |
| 1400 | **infra** | `test_self_recursive_natnum_terminates` |  | Var |
| 1412 | **infra** | `test_recursive_factorial_terminates` |  | Var |
| 1423 | **infra** | `test_mutual_recursion_graph_terminates` |  | Var |
| 1434 | **infra** | `test_even_recursive_terminates` |  | Var |
| 1499 | **unknown** | `test_ground_match` |  |  |
| 1503 | **unknown** | `test_ground_mismatch` |  |  |
| 1507 | **infra** | `test_var_binds` |  | Var |
| 1515 | **infra** | `test_var_in_second` |  | Var |
| 1523 | **infra** | `test_nested_unify` |  | Var |
| 1531 | **infra** | `test_both_vars` |  | Var |
| 1540 | **unknown** | `test_arity_mismatch` |  |  |
| 1544 | **infra** | `test_same_var` |  | Var |
| 1551 | **infra** | `test_var_to_compound` |  | Var |
| 1563 | **unknown** | `test_empty` |  |  |
| 1568 | **unknown** | `test_register_and_lookup` |  |  |
| 1574 | **unknown** | `test_different_pattern` |  |  |
| 1580 | **unknown** | `test_entries` |  |  |
| 1590 | **infra** | `test_more_clauses_than_shallow` |  | Var, _clauses |
| 1597 | **mixed** | `test_natnum_0` | call | Var |
| 1604 | **mixed** | `test_natnum_s_0` | call | Var |
| 1611 | **mixed** | `test_natnum_s_s_s_0` | call | Var |
| 1618 | **mixed** | `test_equivalence_natnum` | call | Var |
| 1638 | **infra** | `test_more_clauses_than_shallow` |  | Var, _clauses |
| 1645 | **mixed** | `test_path_a_b` | call | Var |
| 1652 | **mixed** | `test_path_a_c` | call | Var |
| 1659 | **mixed** | `test_path_a_d` | call | Var |
| 1666 | **mixed** | `test_edge_a_b` | call | Var |
| 1673 | **mixed** | `test_equivalence_graph` | call | Var |
| 1694 | **mixed** | `test_count_natnum_0` | call | Var, deref |
| 1704 | **mixed** | `test_count_natnum_s_0` | call | Var, deref |
| 1714 | **mixed** | `test_count_equivalence` | call | Var, deref |
| 1739 | **mixed** | `test_limit_passes` | call | Var |
| 1746 | **mixed** | `test_limit_fails` | call | Var |
| 1753 | **mixed** | `test_limit_equivalence` | call | Var |
| 1773 | **mixed** | `test_factorial_results` | call | Var, deref |
| 1784 | **mixed** | `test_factorial_equivalence` | call | Var, deref |
| 1805 | **mixed** | `test_even_equivalence` | call | Var |
| 1820 | **infra** | `test_natnum_terminates` |  | Var, _clauses |
| 1828 | **infra** | `test_graph_terminates` |  | Var, _clauses |
| 1836 | **infra** | `test_factorial_terminates` |  | Var, _clauses |
| 1844 | **infra** | `test_even_terminates` |  | Var, _clauses |

</details>

<details><summary><code>tests/test_specialization_pipeline.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 43 | **unknown** | `test_specialized_predicate_exists` |  |  |
| 48 | **infra** | `test_specialized_predicate_is_predicate_meta` |  | PredicateMeta |
| 53 | **infra** | `test_specialized_fields_no_program` |  | _fields |
| 61 | **infra** | `test_specialized_has_clauses` |  | _clauses |
| 66 | **infra** | `test_specialized_has_dispatch` |  | _dispatch_fn |
| 78 | **mixed** | `test_count_natnum_0` | call | Var, deref |
| 89 | **mixed** | `test_count_natnum_s0` | call | Var, deref |
| 100 | **mixed** | `test_count_natnum_ss0` | call | Var, deref |
| 111 | **unknown** | `test_clausal_inline_tests` |  |  |
| 123 | **unknown** | `test_specialized_exists` |  |  |
| 127 | **behavior** | `test_edge_ab` | call |  |
| 133 | **behavior** | `test_path_ab` | call |  |
| 139 | **behavior** | `test_path_ac_transitive` | call |  |
| 145 | **behavior** | `test_path_ad_transitive` | call |  |
| 151 | **behavior** | `test_no_path_ca` | call |  |
| 157 | **infra** | `test_solve_graph_fields` |  | _fields |
| 170 | **unknown** | `test_specialized_exists` |  |  |
| 174 | **infra** | `test_fields` |  | _fields |
| 181 | **behavior** | `test_limit_natnum_0_depth_1` | call |  |
| 189 | **behavior** | `test_limit_natnum_s0_depth_1_fails` | call |  |
| 197 | **behavior** | `test_limit_natnum_s0_depth_2` | call |  |
| 205 | **behavior** | `test_limit_natnum_ss0_depth_3` | call |  |
| 220 | **mixed** | `test_count_equivalence` | call | Var, deref |
| 242 | **behavior** | `test_graph_solve_equivalence` | call |  |
| 281 | **unknown** | `test_specialized_exists` |  |  |
| 285 | **infra** | `test_has_catch_all` |  | _clauses |
| 291 | **behavior** | `test_factorial_0` | call |  |
| 297 | **behavior** | `test_factorial_3` | call |  |
| 303 | **behavior** | `test_factorial_5` | call |  |
| 309 | **mixed** | `test_factorial_query_var` | call | Var, deref |
| 321 | **behavior** | `test_factorial_wrong_fails` | call |  |
| 331 | **unknown** | `test_specialized_exists` |  |  |
| 335 | **mixed** | `test_count_factorial_0` | call | Var, deref |
| 350 | **unknown** | `test_specialized_exists` |  |  |
| 354 | **behavior** | `test_limit_factorial_0_depth_1` | call |  |
| 360 | **behavior** | `test_limit_factorial_3_depth_30` | call |  |
| 370 | **behavior** | `test_even_0` | call |  |
| 376 | **behavior** | `test_even_4` | call |  |
| 382 | **behavior** | `test_odd_1_fails` | call |  |
| 402 | **unknown** | `test_deep_predicate_exists` |  |  |
| 406 | **unknown** | `test_deep_count_predicate_exists` |  |  |
| 410 | **unknown** | `test_shallow_predicate_exists` |  |  |
| 414 | **infra** | `test_deep_predicate_is_predicate_meta` |  | PredicateMeta |
| 419 | **behavior** | `test_deep_natnum_0` | call |  |
| 425 | **behavior** | `test_deep_natnum_s0` | call |  |
| 431 | **behavior** | `test_deep_natnum_ss0` | call |  |
| 440 | **mixed** | `test_deep_count_natnum_0` | call | Var, deref |
| 450 | **mixed** | `test_deep_count_natnum_s0` | call | Var, deref |
| 462 | **behavior** | `test_equivalence_shallow_deep` | call |  |
| 478 | **infra** | `test_depth_directive_parsed` |  | _clauses |
| 491 | **infra** | `test_specialize_missing_args` |  | EmbedTransformer, ast, parse |
| 517 | **infra** | `test_cpd_natnum_exists` |  | PredicateMeta |
| 523 | **infra** | `test_cpd_graph_exists` |  | PredicateMeta |
| 528 | **infra** | `test_cpd_count_exists` |  | PredicateMeta |
| 533 | **infra** | `test_cpd_limit_exists` |  | PredicateMeta |
| 538 | **behavior** | `test_cpd_natnum_query` | call |  |
| 543 | **behavior** | `test_cpd_graph_path` | call |  |
| 548 | **mixed** | `test_cpd_count_value` | call | Var, deref |
| 558 | **behavior** | `test_cpd_limit_succeeds` | call |  |
| 565 | **behavior** | `test_cpd_inline_tests` | call |  |
| 572 | **infra** | `test_cpd_directive_parsing` |  | EmbedTransformer, ast, parse |
| 589 | **infra** | `test_cpd_directive_default_false` |  | EmbedTransformer, ast, parse |

</details>

<details><summary><code>tests/test_string_head_patterns.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 35 | **mixed** | `test_head_tail` | call | Var, deref |
| 43 | **mixed** | `test_head_tail_single_char` | call | Var, deref |
| 51 | **mixed** | `test_head_tail_empty_fails` | call | Var |
| 59 | **mixed** | `test_capture_all` | call | Var, deref |
| 65 | **mixed** | `test_capture_all_empty` | call | Var, deref |
| 73 | **mixed** | `test_three_and_rest` | call | Var, deref |
| 82 | **mixed** | `test_three_exact` | call | Var, deref |
| 88 | **mixed** | `test_too_short_fails` | call | Var |
| 95 | **mixed** | `test_exactly_two` | call | Var, deref |
| 102 | **mixed** | `test_wrong_length_fails` | call | Var |
| 110 | **behavior** | `test_empty_string` | call |  |
| 114 | **behavior** | `test_nonempty_string_fails` | call |  |
| 123 | **mixed** | `test_length` | call | Var, deref |
| 129 | **mixed** | `test_length_empty` | call | Var, deref |
| 135 | **mixed** | `test_last` | call | Var, deref |
| 141 | **mixed** | `test_last_single` | call | Var, deref |
| 154 | **mixed** | `test_tail_is_string` | call | Var, deref |
| 160 | **mixed** | `test_star_capture_is_string` | call | Var, deref |
| 166 | **mixed** | `test_rest_is_string` | call | Var, deref |
| 172 | **mixed** | `test_list_input_still_gives_list` | call | Var, deref |

</details>

<details><summary><code>tests/test_sympy_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 53 | **unknown** | `test_int` |  |  |
| 57 | **unknown** | `test_float` |  |  |
| 61 | **infra** | `test_free_var` |  | Var |
| 68 | **infra** | `test_bound_var_derefs` |  | Trail, Var, unify |
| 75 | **infra** | `test_add` |  | Add, Var |
| 85 | **infra** | `test_sub` |  | Sub, Var |
| 95 | **infra** | `test_mult` |  | Mult |
| 100 | **infra** | `test_pow` |  | Pow, Var |
| 110 | **infra** | `test_negate` |  | Negate |
| 115 | **infra** | `test_compound_sin` |  | Compound, Var |
| 125 | **infra** | `test_compound_unknown` |  | Compound |
| 130 | **infra** | `test_nested` |  | Add, Mult, Pow, Var |
| 145 | **unknown** | `test_string_becomes_symbol` |  |  |
| 150 | **unknown** | `test_sympy_passthrough` |  |  |
| 155 | **unknown** | `test_div` |  |  |
| 162 | **unknown** | `test_integer` |  |  |
| 166 | **unknown** | `test_symbol_passthrough` |  |  |
| 174 | **infra** | `test_symbol_roundtrip` |  | Var |
| 182 | **infra** | `test_add` |  | Add |
| 189 | **infra** | `test_mul` |  | Mult |
| 196 | **infra** | `test_pow` |  | Pow |
| 203 | **infra** | `test_negation` |  | Negate |
| 210 | **unknown** | `test_rational` |  |  |
| 217 | **unknown** | `test_rational_integer` |  |  |
| 222 | **infra** | `test_sin` |  | Compound |
| 230 | **unknown** | `test_float` |  |  |
| 235 | **unknown** | `test_inverse_to_div` |  |  |
| 247 | **infra** | `test_var_preserved` |  | Add, Compound, Var |
| 259 | **infra** | `test_simplify_roundtrip` |  | Add, Compound, Pow, Var |
| 295 | **mixed** | `test_create_symbol` | _first_solution | Trail, Var, _get_dispatch, deref |
| 305 | **mixed** | `test_simplify_polynomial` | _first_solution | Add, Mult, Pow, Sub, Trail, Var, _get_dispatch, deref, unify |
| 323 | **mixed** | `test_simplify_trig` | _first_solution | Add, Compound, Pow, Trail, Var, _get_dispatch, deref |
| 338 | **mixed** | `test_expand_square` | _first_solution | Add, Pow, Trail, Var, _get_dispatch, deref |
| 353 | **mixed** | `test_factor_diff_of_squares` | _first_solution | Pow, Sub, Trail, Var, _get_dispatch, deref |
| 365 | **infra** | `test_solve_linear` |  | Mult, Sub, Trail, Var, _get_dispatch, deref |
| 376 | **infra** | `test_solve_quadratic` |  | Pow, Sub, Trail, Var, _get_dispatch, deref |
| 386 | **infra** | `test_solve_no_solution` |  | Add, Pow, Trail, Var, _get_dispatch, deref |
| 398 | **mixed** | `test_solve_all_quadratic` | _first_solution | Pow, Sub, Trail, Var, _get_dispatch, deref |
| 410 | **mixed** | `test_diff_auto_var` | _first_solution | Pow, Trail, Var, _get_dispatch, deref |
| 421 | **mixed** | `test_diff_explicit_var` | _first_solution | Compound, Trail, Var, _get_dispatch, deref |
| 431 | **mixed** | `test_diff_multivar` | _first_solution | Add, Mult, Pow, Trail, Var, _get_dispatch, deref |
| 444 | **mixed** | `test_integrate_poly` | _first_solution | Pow, Trail, Var, _get_dispatch, deref |
| 455 | **mixed** | `test_integrate_explicit_var` | _first_solution | Compound, Trail, Var, _get_dispatch, deref |
| 466 | **mixed** | `test_limit_sinx_over_x` | _first_solution | Compound, Trail, Var, _get_dispatch, deref |
| 478 | **mixed** | `test_series_exp` | _first_solution | Compound, Trail, Var, _get_dispatch, deref |
| 492 | **mixed** | `test_subs_dict` | _first_solution | Add, Pow, Trail, Var, _get_dispatch, deref |
| 501 | **mixed** | `test_subs_list` | _first_solution | Add, Trail, Var, _get_dispatch, deref |
| 512 | **mixed** | `test_free_vars` | _first_solution | Add, Mult, Trail, Var, _get_dispatch, deref |
| 528 | **infra** | `test_solve_and_verify` |  | Pow, Sub, Trail, Var, _get_dispatch, deref |
| 540 | **mixed** | `test_differentiate_then_integrate` | _first_solution | Pow, Trail, Var, _get_dispatch, deref |

</details>

<details><summary><code>tests/test_tail_recursion.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 38 | **infra** | `test_unify` |  | Var |
| 42 | **infra** | `test_evaluate` |  | Add, Evaluate, Var |
| 46 | **infra** | `test_does_not_unify` |  | Var |
| 50 | **unknown** | `test_structural_eq` |  |  |
| 54 | **unknown** | `test_structural_neq` |  |  |
| 58 | **infra** | `test_comparisons` |  | Gt, GtE, Lt, LtE, Var |
| 65 | **unknown** | `test_in_notin` |  |  |
| 70 | **infra** | `test_not` |  | Gt, Not |
| 74 | **unknown** | `test_true_false` |  |  |
| 79 | **infra** | `test_and_deterministic` |  | And, Evaluate, Gt, Sub, Var |
| 85 | **infra** | `test_and_nondeterministic` |  | And, Call, Gt, LoadName, Var |
| 91 | **infra** | `test_predicate_call` |  | Call, LoadName, Var |
| 97 | **infra** | `test_or_nondeterministic` |  | Gt, Lt, Or, Var |
| 103 | **infra** | `test_once_deterministic` |  | Call, LoadName, Var |
| 110 | **infra** | `test_findall_deterministic` |  | Call, LoadName, Var |
| 127 | **unknown** | `test_no_body` |  |  |
| 133 | **infra** | `test_last_goal_is_self_call` |  | Call, LoadName, PredicateMeta, Var |
| 149 | **infra** | `test_deterministic_prefix_with_self_call` |  | Call, Evaluate, Gt, LoadName, PredicateMeta, Sub, Var |
| 169 | **infra** | `test_nondeterministic_prefix_rejected` |  | Call, LoadName, PredicateMeta, Var |
| 186 | **infra** | `test_different_functor_rejected` |  | Call, LoadName, PredicateMeta, Var |
| 200 | **infra** | `test_no_prefix_body_only_vars_rejected` |  | Call, LoadName, PredicateMeta, Var |
| 222 | **infra** | `test_star_unpack_with_prefix_allowed` |  | Call, LoadName, PredicateMeta, Var |
| 245 | **infra** | `test_nested_var_in_list_arg_no_prefix_rejected` |  | Call, LoadName, PredicateMeta, Var |
| 267 | **infra** | `test_compound_arg_with_head_var_allowed_with_prefix` |  | Call, Compound, Evaluate, Gt, LoadName, PredicateMeta, Sub, Var |
| 291 | **infra** | `test_compound_arg_with_head_var_rejected_no_prefix` |  | Call, Compound, LoadName, PredicateMeta, Var |
| 339 | **infra** | `test_simple_countdown` |  | Call, Evaluate, Gt, LoadName, PredicateMeta, Sub, Var |
| 361 | **infra** | `test_accumulator_sum` |  | PredicateMeta, Var |
| 381 | **infra** | `test_passthrough_variable` |  | Call, Evaluate, Gt, LoadName, PredicateMeta, Sub, Var |
| 409 | **infra** | `test_deep_recursion` |  | Call, Evaluate, Gt, LoadName, PredicateMeta, Sub, Var |
| 505 | **mixed** | `test_tro_constant_allocations` | call | Call, Database, Evaluate, Gt, LoadName, PredicateMeta, Sub, Trail, Var, _get_dispatch |
| 553 | **mixed** | `test_non_tro_linear_allocations` | call | Call, Evaluate, Gt, LoadName, PredicateMeta, Sub, Trail, Var, _get_dispatch, compile_predicate_trampoline |
| 604 | **mixed** | `test_tro_with_passthrough_output` | call | Add, Call, Evaluate, Gt, LoadName, PredicateMeta, Sub, Trail, Var, _get_dispatch, compile_predicate_trampoline, deref |
| 658 | **behavior** | `test_fixture_loaded_with_tro` | load_clausal_module |  |
| 667 | **mixed** | `test_fixture_accsum_correct` | call, load_clausal_module | Trail, Var, deref |
| 681 | **mixed** | `test_fixture_factorial_correct` | call, load_clausal_module | Trail, Var, deref |
| 695 | **mixed** | `test_fixture_tro_allocations` | call, load_clausal_module | Trail, Var, _get_dispatch |
| 723 | **mixed** | `test_mynthof_tro_across_buckets` | call, load_clausal_module | Trail, Var, deref |
| 739 | **mixed** | `test_mynthof_tro_allocations` | call, load_clausal_module | Trail, Var, _get_dispatch |
| 763 | **mixed** | `test_acclength_with_unbound_list` | call, load_clausal_module | Trail, Var |
| 780 | **infra** | `test_check_indices_computed` |  | Add, Call, Evaluate, LoadName, PredicateMeta, Var |
| 808 | **infra** | `test_get_tro_check_indices_with_head_decomposition` |  | Add, Call, Evaluate, LoadName, PredicateMeta, Var |

</details>

<details><summary><code>tests/test_tcp_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 118 | **infra** | `test_connect_to_echo_server` |  | Trail, Var, deref |
| 128 | **infra** | `test_connection_refused_fails` |  | Trail, Var |
| 135 | **infra** | `test_unbound_host_fails` |  | Trail, Var |
| 141 | **infra** | `test_unbound_port_fails` |  | Trail, Var |
| 153 | **infra** | `test_listen_and_accept` |  | Trail, Var, deref |
| 176 | **infra** | `test_ephemeral_port` |  | Trail, Var, deref |
| 192 | **infra** | `test_echo_round_trip` |  | Trail, Var, deref |
| 212 | **infra** | `test_receive_custom_buffer_size` |  | Trail, Var, deref |
| 226 | **infra** | `test_send_unbound_data_fails` |  | Trail, Var, deref |
| 236 | **infra** | `test_send_bytes` |  | Trail, Var, deref |
| 255 | **infra** | `test_close_succeeds` |  | Trail, Var, deref |
| 264 | **infra** | `test_double_close_harmless` |  | Trail, Var, deref |
| 275 | **infra** | `test_close_unbound_fails` |  | Trail, Var |
| 286 | **infra** | `test_set_timeout` |  | Trail, Var, deref |
| 297 | **infra** | `test_unbound_seconds_fails` |  | Trail, Var, deref |
| 313 | **infra** | `test_full_echo_trampoline` |  | Trail, Var, _get_dispatch, deref |

</details>

<details><summary><code>tests/test_trail_elision.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 98 | **infra** | `test_single_clause_bucket_no_mark_undo` |  | Compound, Database, Var, ast |
| 139 | **infra** | `test_skip_trail_false_has_mark_undo` |  | Compound, Var, ast |
| 156 | **infra** | `test_skip_trail_with_dup_guards` |  | Compound, Var, ast |
| 174 | **infra** | `test_ground_head_still_elided_without_skip_trail` |  | Compound, ast |
| 201 | **mixed** | `test_single_clause_bucket_returns_correct_results` | call, load_clausal_module | Var, deref |
| 217 | **mixed** | `test_each_bucket_returns_exactly_one_solution` | call, load_clausal_module | Var, deref |
| 231 | **mixed** | `test_backtracking_past_elided_clause_undoes_bindings` | call, load_clausal_module | Var, deref |
| 255 | **mixed** | `test_var_binding_undone_between_calls` | call, load_clausal_module | Trail, Var, deref |
| 281 | **mixed** | `test_dup_guard_clause_in_single_bucket` | call, load_clausal_module | Var, deref |
| 300 | **mixed** | `test_dup_guard_failure_in_single_bucket` | call, load_clausal_module | Var, deref |
| 323 | **mixed** | `test_nested_calls_through_elided_predicates` | call, load_clausal_module | Var, deref |
| 343 | **mixed** | `test_single_clause_predicate_no_index` | call, load_clausal_module | Var, deref |
| 354 | **mixed** | `test_mixed_ground_and_var_heads_no_elision` | call, load_clausal_module | Var, deref |
| 373 | **mixed** | `test_multiple_solutions_non_elided_predicate` | call, load_clausal_module | Var, deref |

</details>

<details><summary><code>tests/test_transform_nodes.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 25 | **unknown** | `test_empty_list_returns_empty_list` |  |  |
| 31 | **unknown** | `test_single_node_unchanged` |  |  |
| 38 | **unknown** | `test_single_node_removed` |  |  |
| 44 | **unknown** | `test_single_node_transformed` |  |  |
| 55 | **unknown** | `test_all_unchanged_returns_list_equal_to_original` |  |  |
| 62 | **unknown** | `test_all_unchanged_returns_same_object_as_input` |  |  |
| 75 | **unknown** | `test_first_node_removed` |  |  |
| 82 | **unknown**† | `test_middle_node_removed` |  |  |
| 89 | **unknown** | `test_last_node_removed` |  |  |
| 96 | **unknown** | `test_all_nodes_removed` |  |  |
| 103 | **unknown** | `test_multiple_adjacent_nodes_removed` |  |  |
| 111 | **unknown** | `test_multiple_non_adjacent_nodes_removed` |  |  |
| 123 | **unknown** | `test_first_node_transformed` |  |  |
| 130 | **unknown** | `test_middle_node_transformed` |  |  |
| 137 | **unknown** | `test_last_node_transformed` |  |  |
| 144 | **unknown** | `test_all_nodes_transformed` |  |  |
| 151 | **unknown** | `test_transformation_uses_identity_comparison_not_equality` |  |  |
| 172 | **unknown** | `test_remove_and_transform_different_nodes` |  |  |
| 187 | **unknown** | `test_transform_first_then_remove_later` |  |  |
| 202 | **unknown** | `test_remove_first_then_transform_later` |  |  |
| 221 | **unknown** | `test_always_returns_a_list` |  |  |
| 229 | **unknown** | `test_unchanged_result_is_same_object_so_mutations_are_shared` |  |  |
| 245 | **unknown** | `test_first_node_expanded_to_multiple` |  |  |
| 252 | **unknown** | `test_middle_node_expanded_to_multiple` |  |  |
| 259 | **unknown** | `test_last_node_expanded_to_multiple` |  |  |
| 266 | **unknown**† | `test_node_expanded_to_empty_list_acts_like_removal` |  |  |
| 273 | **unknown** | `test_node_expanded_to_single_item_list` |  |  |
| 280 | **unknown** | `test_all_nodes_expanded` |  |  |
| 287 | **unknown** | `test_multiple_nodes_expanded` |  |  |
| 295 | **unknown** | `test_expansion_and_removal_mixed` |  |  |
| 310 | **unknown** | `test_expansion_and_single_replacement_mixed` |  |  |
| 325 | **unknown** | `test_expansion_triggers_changed_flag` |  |  |
| 339 | **unknown** | `test_transform_called_once_per_node` |  |  |
| 352 | **unknown** | `test_transform_called_once_per_node_when_first_removed` |  |  |
| 365 | **unknown** | `test_transform_called_once_per_node_when_first_transformed` |  |  |

</details>

<details><summary><code>tests/test_translations.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 50 | **unknown** | `test_register_predicate` |  |  |
| 58 | **unknown** | `test_reverse_predicate` |  |  |
| 66 | **unknown** | `test_register_atom` |  |  |
| 72 | **unknown** | `test_missing_lookup_returns_none` |  |  |
| 79 | **unknown** | `test_multiple_languages` |  |  |
| 86 | **unknown** | `test_additive_merge` |  |  |
| 93 | **unknown** | `test_get_all_predicates` |  |  |
| 103 | **unknown** | `test_get_all_atoms` |  |  |
| 110 | **unknown** | `test_get_languages` |  |  |
| 116 | **unknown** | `test_arity_discrimination` |  |  |
| 134 | **infra** | `test_compound_with_locale` |  | Compound |
| 141 | **infra** | `test_compound_without_locale` |  | Compound |
| 147 | **infra** | `test_nested_with_locale` |  | Compound |
| 154 | **infra** | `test_predicate_meta_with_locale` |  | make_predicate |
| 162 | **infra** | `test_no_translation_passthrough` |  | Compound |
| 168 | **infra** | `test_atom_in_compound_arg` |  | Compound |
| 176 | **infra** | `test_zero_arity_atom_with_locale` |  | make_predicate |
| 194 | **infra** | `test_forward_produces_string` |  | Compound, Trail, Var, deref |
| 207 | **infra** | `test_result_is_string_not_term` |  | Compound, Trail, Var, deref |
| 220 | **infra** | `test_unbound_lang_fails` |  | Compound, Trail, Var |
| 228 | **infra** | `test_atom_lang_accepted` |  | Compound, Trail, Var, deref, make_predicate |
| 243 | **infra** | `test_nested_translation` |  | Compound, Trail, Var, deref |
| 278 | **unknown** | `test_predicate_translations_loaded` |  |  |
| 293 | **unknown** | `test_atom_translations_loaded` |  |  |
| 303 | **behavior** | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_trealla_backend.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 135 | **behavior** | `test_conformity_parses` | query |  |
| 150 | **behavior** | `test_golden_pl_parses` | query |  |
| 172 | **behavior** | `test_simple_fact_query` | query |  |
| 183 | **behavior** | `test_simple_rule_query` | query |  |
| 197 | **behavior** | `test_recursive_rule` | query |  |
| 215 | **behavior** | `test_list_operations` | query |  |
| 230 | **behavior** | `test_arithmetic_evaluation` | query |  |
| 254 | **behavior** | `test_negation` | query |  |
| 270 | **behavior** | `test_unification` | query |  |
| 282 | **behavior** | `test_disjunction` | query |  |
| 298 | **behavior** | `test_findall` | query |  |
| 334 | **unknown** | `test_iso_arithmetic` |  |  |
| 345 | **unknown** | `test_iso_control` |  |  |
| 355 | **unknown** | `test_iso_unification` |  |  |
| 365 | **unknown** | `test_iso_list_operations` |  |  |
| 375 | **unknown** | `test_iso_type_checking` |  |  |
| 385 | **unknown** | `test_iso_term_manipulation` |  |  |
| 404 | **unknown** | `test_clpz_constraints` |  |  |
| 418 | **unknown** | `test_trealla_leq_operator` |  |  |
| 425 | **unknown** | `test_trealla_dif` |  |  |
| 432 | **unknown** | `test_trealla_member` |  |  |
| 439 | **unknown** | `test_trealla_cut` |  |  |
| 458 | **behavior** | `test_operator_precedence_iso` | query |  |
| 467 | **behavior** | `test_atom_quoting` | query |  |
| 476 | **behavior** | `test_string_handling` | query |  |
| 486 | **behavior** | `test_empty_list` | query |  |
| 495 | **behavior** | `test_list_cons_pattern` | query |  |
| 506 | **behavior** | `test_nested_compound` | query |  |
| 518 | **behavior** | `test_multiple_solutions` | query |  |
| 535 | **behavior** | `test_comparison_operators` | query |  |

</details>

<details><summary><code>tests/test_trealla_embedding.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 28 | **unknown** | `test_true` |  |  |
| 34 | **unknown** | `test_fail` |  |  |
| 41 | **unknown** | `test_fact_and_query` |  |  |
| 48 | **unknown** | `test_multiple_solutions` |  |  |
| 56 | **unknown** | `test_arithmetic` |  |  |
| 63 | **unknown** | `test_list_unification` |  |  |
| 70 | **infra** | `test_compound_term` |  | Compound |
| 79 | **unknown** | `test_no_bindings_goal` |  |  |
| 86 | **unknown** | `test_iterator_protocol` |  |  |
| 103 | **unknown** | `test_consult_clausal_facts` |  |  |
| 111 | **unknown** | `test_consult_clausal_rules` |  |  |
| 127 | **unknown** | `test_consult_clausal_arithmetic` |  |  |
| 134 | **unknown** | `test_consult_clausal_list_patterns` |  |  |
| 145 | **unknown** | `test_consult_file_clausal` |  |  |
| 156 | **unknown** | `test_consult_file_prolog` |  |  |
| 177 | **unknown** | `test_fibonacci` |  |  |
| 186 | **unknown** | `test_graph_reachable` |  |  |
| 203 | **unknown** | `test_separate_predicates_persist` |  |  |
| 214 | **unknown** | `test_dynamic_assertz_accumulates` |  |  |
| 225 | **unknown** | `test_multiple_queries_same_session` |  |  |
| 234 | **unknown** | `test_context_manager_cleanup` |  |  |
| 243 | **unknown** | `test_use_after_close_raises` |  |  |
| 260 | **unknown** | `test_prolog_error_raises` |  |  |
| 268 | **unknown** | `test_early_break_is_lazy` |  |  |
| 291 | **unknown** | `test_large_integer` |  |  |
| 298 | **unknown** | `test_float_result` |  |  |
| 305 | **unknown** | `test_nested_list` |  |  |
| 312 | **unknown** | `test_empty_list` |  |  |
| 327 | **unknown** | `test_basic_types` |  |  |
| 336 | **unknown** | `test_string_quoting` |  |  |
| 342 | **unknown** | `test_list` |  |  |
| 348 | **infra** | `test_compound` |  | Compound |
| 354 | **unknown** | `test_unsupported_type_raises` |  |  |

</details>

<details><summary><code>tests/test_uuid_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 71 | **infra** | `test_uuid4_generates` |  | Trail, Var, deref |
| 80 | **infra** | `test_uuid4_unique` |  | Trail, Var, deref |
| 87 | **infra** | `test_uuid4_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 99 | **infra** | `test_uuid1_generates` |  | Trail, Var, deref |
| 108 | **infra** | `test_uuid1_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 120 | **infra** | `test_uuid3_deterministic` |  | Trail, Var, deref |
| 127 | **infra** | `test_uuid3_version` |  | Trail, Var, deref |
| 133 | **infra** | `test_uuid3_all_namespaces` |  | Trail, Var |
| 140 | **infra** | `test_uuid3_raw_namespace` |  | Trail, Var |
| 146 | **infra** | `test_uuid3_bad_namespace_fails` |  | Trail, Var |
| 152 | **infra** | `test_uuid3_unbound_name_fails` |  | Trail, Var |
| 158 | **infra** | `test_uuid3_trampoline` |  | Trail, Var, _get_dispatch |
| 169 | **infra** | `test_uuid5_deterministic` |  | Trail, Var, deref |
| 176 | **infra** | `test_uuid5_version` |  | Trail, Var, deref |
| 182 | **infra** | `test_uuid5_trampoline` |  | Trail, Var, _get_dispatch |
| 193 | **infra** | `test_decompose` |  | Trail, Var, deref |
| 201 | **infra** | `test_construct` |  | Trail, Var, deref |
| 210 | **infra** | `test_roundtrip` |  | Trail, Var, deref |
| 218 | **infra** | `test_both_ground_match` |  | Trail |
| 224 | **infra** | `test_both_ground_mismatch` |  | Trail |
| 230 | **infra** | `test_bad_string_fails` |  | Trail, Var |
| 241 | **infra** | `test_decompose` |  | Trail, Var, deref |
| 249 | **infra** | `test_construct` |  | Trail, Var, deref |
| 257 | **infra** | `test_roundtrip` |  | Trail, Var, deref |
| 265 | **infra** | `test_bad_hex_fails` |  | Trail, Var |
| 276 | **infra** | `test_decompose` |  | Trail, Var, deref |
| 284 | **infra** | `test_construct` |  | Trail, Var, deref |
| 292 | **infra** | `test_roundtrip` |  | Trail, Var, deref |
| 305 | **infra** | `test_decompose` |  | Trail, Var, deref |
| 313 | **infra** | `test_construct` |  | Trail, Var, deref |
| 321 | **infra** | `test_roundtrip` |  | Trail, Var, deref |
| 329 | **infra** | `test_wrong_length_fails` |  | Trail, Var |
| 340 | **infra** | `test_decompose` |  | Trail, Var, deref |
| 348 | **infra** | `test_construct` |  | Trail, Var, deref |
| 356 | **infra** | `test_roundtrip` |  | Trail, Var, deref |
| 364 | **infra** | `test_negative_fails` |  | Trail, Var |
| 375 | **infra** | `test_version_v4` |  | Trail, Var, deref |
| 383 | **infra** | `test_version_v1` |  | Trail, Var, deref |
| 391 | **infra** | `test_version_v3` |  | Trail, Var, deref |
| 399 | **infra** | `test_version_v5` |  | Trail, Var, deref |
| 407 | **infra** | `test_non_uuid_fails` |  | Trail, Var |
| 418 | **infra** | `test_decompose` |  | Trail, Var, deref |
| 432 | **infra** | `test_non_uuid_fails` |  | Trail, Var |
| 443 | **infra** | `test_uuid_passes` |  | Trail |
| 449 | **infra** | `test_string_fails` |  | Trail |
| 454 | **infra** | `test_int_fails` |  | Trail |
| 459 | **infra** | `test_var_fails` |  | Trail, Var |
| 469 | **infra** | `test_nil_uuid` |  | Trail, Var, deref |
| 477 | **infra** | `test_max_uuid` |  | Trail, Var, deref |
| 485 | **infra** | `test_nil_uuid_version` |  | Trail, Var |
| 492 | **infra** | `test_both_unbound_str_fails` |  | Trail, Var |
| 498 | **infra** | `test_both_unbound_hex_fails` |  | Trail, Var |
| 509 | **behavior** | `test_uuid4_in_clausal` | call |  |
| 514 | **behavior** | `test_uuid_str_roundtrip_clausal` | call |  |
| 519 | **behavior** | `test_uuid3_clausal` | call |  |
| 524 | **behavior** | `test_uuid5_clausal` | call |  |
| 529 | **behavior** | `test_uuid_int_clausal` | call |  |
| 534 | **behavior** | `test_uuid_hex_clausal` | call |  |
| 567 | **behavior** | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_variables.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 28 | **infra** | `test_new_var_is_unbound` |  | Var |
| 33 | **infra** | `test_unbound_value_is_self` |  | Var |
| 38 | **infra** | `test_is_var_on_unbound` |  | Var |
| 42 | **unknown** | `test_is_var_on_int` |  |  |
| 46 | **unknown** | `test_is_var_on_string` |  |  |
| 50 | **infra** | `test_var_has_id` |  | Var |
| 57 | **infra** | `test_repr_unbound` |  | Var |
| 64 | **infra** | `test_repr_bound` |  | Trail, Var, unify |
| 72 | **infra** | `test_distinct_vars` |  | Var |
| 78 | **infra** | `test_var_hashable` |  | Var |
| 89 | **infra** | `test_new_trail_length_zero` |  | Trail |
| 94 | **infra** | `test_mark_on_empty` |  | Trail |
| 99 | **infra** | `test_repr` |  | Trail |
| 104 | **infra** | `test_mark_advances_after_bind` |  | Trail, Var, unify |
| 112 | **infra** | `test_undo_empty_is_noop` |  | Trail |
| 117 | **infra** | `test_undo_bad_mark_raises` |  | Trail |
| 127 | **infra** | `test_reset` |  | Trail, Var, unify |
| 143 | **infra** | `test_var_int` |  | Var, deref, unify |
| 150 | **infra** | `test_var_string` |  | Var, deref, unify |
| 156 | **infra** | `test_var_float` |  | Var, deref, unify |
| 162 | **infra** | `test_var_none` |  | Var, deref, unify |
| 168 | **infra** | `test_reversed_order_works` |  | Var, deref, unify |
| 174 | **infra** | `test_var_already_bound_same_value` |  | Var, unify |
| 180 | **infra** | `test_var_already_bound_different_value_fails` |  | Var, unify |
| 186 | **infra** | `test_var_is_bound_after_unify` |  | Var, unify |
| 198 | **infra** | `test_same_var_trivially_unifies` |  | Var, unify |
| 204 | **infra** | `test_two_vars_bind` |  | Var, deref, unify |
| 212 | **infra** | `test_binding_direction` |  | Var, deref, unify |
| 225 | **infra** | `test_var_var_then_bind_one` |  | Var, deref, unify |
| 235 | **infra** | `test_three_vars` |  | Var, deref, unify |
| 252 | **infra** | `test_int_int_equal` |  | unify |
| 256 | **infra** | `test_int_int_unequal` |  | unify |
| 260 | **infra** | `test_string_string_equal` |  | unify |
| 264 | **infra** | `test_string_string_unequal` |  | unify |
| 268 | **infra** | `test_int_string_fails` |  | unify |
| 272 | **infra** | `test_none_none` |  | unify |
| 276 | **infra** | `test_bool_int` |  | unify |
| 287 | **infra** | `test_tuples_equal` |  | unify |
| 291 | **infra** | `test_tuples_unequal_functor` |  | unify |
| 295 | **infra** | `test_tuples_unequal_arity` |  | unify |
| 299 | **infra** | `test_tuples_with_var` |  | Var, deref, unify |
| 305 | **infra** | `test_tuples_nested` |  | Var, deref, unify |
| 311 | **infra** | `test_empty_tuples` |  | unify |
| 315 | **infra** | `test_tuple_vs_list_fails` |  | unify |
| 319 | **infra** | `test_lists_equal` |  | unify |
| 323 | **infra** | `test_lists_with_var` |  | Var, deref, unify |
| 329 | **infra** | `test_lists_unequal_length` |  | unify |
| 336 | **infra** | `test_undo_single_binding` |  | Trail, Var, deref, unify |
| 347 | **infra** | `test_undo_multiple_bindings` |  | Trail, Var, unify |
| 360 | **infra** | `test_partial_undo` |  | Trail, Var, unify |
| 371 | **infra** | `test_failure_auto_rollback` |  | Trail, Var, deref, unify |
| 387 | **infra** | `test_nested_choice_points` |  | Trail, Var, deref, unify |
| 405 | **infra** | `test_var_var_undo` |  | Trail, Var, deref, unify |
| 419 | **infra** | `test_reuse_var_after_undo` |  | Trail, Var, deref, unify |
| 435 | **infra** | `test_deref_unbound` |  | Var, deref |
| 440 | **infra** | `test_deref_int` |  | deref |
| 444 | **infra** | `test_deref_bound_var` |  | Trail, Var, deref, unify |
| 451 | **infra** | `test_deref_chain` |  | Trail, Var, deref, unify |
| 464 | **unknown** | `test_walk_atomic` |  |  |
| 469 | **infra** | `test_walk_unbound` |  | Var |
| 474 | **infra** | `test_walk_bound` |  | Trail, Var, unify |
| 481 | **infra** | `test_walk_tuple` |  | Trail, Var, unify |
| 489 | **infra** | `test_walk_nested` |  | Trail, Var, unify |
| 498 | **infra** | `test_walk_list` |  | Trail, Var, unify |
| 506 | **infra** | `test_walk_unbound_in_compound` |  | Var |
| 514 | **infra** | `test_walk_returns_new_object` |  | Trail, Var, unify |
| 526 | **infra** | `test_var_not_in_atomic` |  | Var |
| 531 | **infra** | `test_var_in_itself` |  | Var |
| 536 | **infra** | `test_var_in_tuple` |  | Var |
| 541 | **infra** | `test_var_not_in_tuple` |  | Var |
| 547 | **infra** | `test_var_in_nested` |  | Var |
| 552 | **infra** | `test_var_in_list` |  | Var |
| 557 | **infra** | `test_bound_var_not_treated_as_var` |  | Trail, Var, unify |
| 565 | **infra** | `test_var_found_through_binding` |  | Trail, Var, unify |
| 578 | **infra** | `test_simple_success` |  | Trail, Var, deref |
| 585 | **infra** | `test_circular_fails` |  | Trail, Var |
| 594 | **infra** | `test_non_circular_succeeds` |  | Trail, Var |
| 601 | **infra** | `test_nested_circular_fails` |  | Trail, Var |
| 609 | **infra** | `test_without_occurs_check_allows_cycle` |  | Trail, Var, unify |
| 620 | **infra** | `test_wrong_trail_type_raises` |  | unify |
| 625 | **unknown** | `test_wrong_trail_type_occ` |  |  |
| 630 | **infra** | `test_unify_many_vars` |  | Trail, Var, deref, unify |
| 640 | **infra** | `test_mark_undo_repeated` |  | Trail, Var, deref, unify |
| 651 | **infra** | `test_gc_collects_trail` |  | Trail, Var, unify |
| 663 | **infra** | `test_walk_deeply_nested` |  | Trail, Var, unify |
| 679 | **infra** | `test_trail_undo_type_error` |  | Trail |
| 685 | **infra** | `test_deref_non_var` |  | deref |
| 690 | **infra** | `test_is_var_on_var` |  | Trail, Var, unify |

</details>

<details><summary><code>tests/test_z3_docs.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 26 | **infra** | `test_store_select` |  | Trail, Var, deref |
| 41 | **infra** | `test_set_member_after_add` |  | Trail, Var |
| 52 | **infra** | `test_string_length_entailed` |  | GtE, Trail, Var |
| 64 | **infra** | `test_functional_consistency` |  | Trail, Var |

</details>

<details><summary><code>tests/test_z3_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 25 | **infra** | `test_single_comparison_chain` |  | LtE, Trail, Var |
| 36 | **infra** | `test_integer_sort_registered` |  | LtE, Trail, Var |
| 48 | **infra** | `test_real_sort_registered` |  | LtE, Trail, Var |
| 61 | **infra** | `test_ground_vars_ignored` |  | Trail, Var, deref |
| 75 | **infra** | `test_unregistered_raises` |  | Trail, Var |
| 82 | **infra** | `test_bindings_undone_after_label` |  | LtE, Trail, Var, deref |
| 96 | **infra** | `test_constraint_block_retracted_on_undo` |  | LtE, Trail, Var, deref |

</details>

### modules

<details><summary><code>tests/test_chars.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 38 | **mixed** | `test_both_bound_match` | _run | Trail |
| 42 | **mixed** | `test_both_bound_mismatch` | _run | Trail |
| 46 | **mixed** | `test_digit_match` | _run | Trail |
| 50 | **mixed** | `test_upper_match` | _run | Trail |
| 54 | **mixed** | `test_space_match` | _run | Trail |
| 58 | **mixed** | `test_punct_match` | _run | Trail |
| 62 | **mixed** | `test_not_single_char_fails` | _run | Trail |
| 66 | **infra** | `test_enum_types_for_char` |  | Trail, Var, deref |
| 79 | **infra** | `test_enum_chars_for_digit` |  | Trail, Var, deref |
| 87 | **mixed** | `test_both_unbound_error` | _run | Trail, Var |
| 92 | **mixed** | `test_control_char` | _run | Trail |
| 96 | **mixed** | `test_ascii_char` | _run | Trail |
| 104 | **infra** | `test_char_to_code` |  | Trail, Var, deref |
| 110 | **infra** | `test_code_to_char` |  | Trail, Var, deref |
| 116 | **mixed** | `test_both_bound_match` | _run | Trail |
| 120 | **mixed** | `test_both_bound_mismatch` | _run | Trail |
| 124 | **mixed** | `test_both_unbound_error` | _run | Trail, Var |
| 129 | **mixed** | `test_non_char_error` | _run | Trail, Var |
| 138 | **infra** | `test_upcase` |  | Trail, Var, deref |
| 145 | **infra** | `test_upcase_mixed` |  | Trail, Var, deref |
| 152 | **infra** | `test_downcase` |  | Trail, Var, deref |
| 159 | **infra** | `test_upcase_empty` |  | Trail, Var, deref |
| 165 | **mixed** | `test_upcase_unbound_error` | _run | Trail, Var |
| 170 | **mixed** | `test_upcase_non_string_error` | _run | Trail, Var |
| 179 | **infra** | `test_length` |  | Trail, Var, deref |
| 186 | **infra** | `test_empty` |  | Trail, Var, deref |
| 192 | **mixed** | `test_both_bound_match` | _run | Trail |
| 196 | **mixed** | `test_both_bound_mismatch` | _run | Trail |
| 200 | **mixed** | `test_unbound_error` | _run | Trail, Var |
| 209 | **infra** | `test_atom_to_chars` |  | Trail, Var, deref |
| 215 | **infra** | `test_chars_to_atom` |  | Trail, Var, deref |
| 222 | **mixed** | `test_both_bound_match` | _run | Trail |
| 226 | **infra** | `test_empty` |  | Trail, Var, deref |
| 232 | **mixed** | `test_both_unbound_error` | _run | Trail, Var |
| 241 | **infra** | `test_atom_to_codes` |  | Trail, Var, deref |
| 247 | **infra** | `test_codes_to_atom` |  | Trail, Var, deref |
| 254 | **mixed** | `test_both_bound_match` | _run | Trail |
| 258 | **mixed** | `test_both_unbound_error` | _run | Trail, Var |
| 267 | **infra** | `test_forward` |  | Trail, Var, deref |
| 274 | **infra** | `test_forward_empty_left` |  | Trail, Var, deref |
| 281 | **infra** | `test_forward_empty_right` |  | Trail, Var, deref |
| 288 | **infra** | `test_reverse_enumerate_splits` |  | Trail, Var, deref |
| 297 | **infra** | `test_prefix_bound` |  | Trail, Var, deref |
| 304 | **infra** | `test_suffix_bound` |  | Trail, Var, deref |
| 311 | **mixed** | `test_all_bound_match` | _run | Trail |
| 315 | **mixed** | `test_all_bound_mismatch` | _run | Trail |
| 319 | **mixed** | `test_all_unbound_error` | _run | Trail, Var |
| 324 | **mixed** | `test_c_unbound_a_bound_error` | _run | Trail, Var |
| 333 | **infra** | `test_all_bound_extract` |  | Trail, Var, deref |
| 340 | **infra** | `test_whole_string` |  | Trail, Var, deref |
| 347 | **infra** | `test_empty_prefix` |  | Trail, Var, deref |
| 354 | **infra** | `test_sub_bound_find` |  | Trail, Var, deref |
| 361 | **infra** | `test_sub_bound_multiple_occurrences` |  | Trail, Var, deref |
| 369 | **infra** | `test_length_bound_enumerate` |  | Trail, Var, deref |
| 379 | **mixed** | `test_all_unbound_enumerate` | _run | Trail, Var |
| 384 | **mixed** | `test_inconsistent_fails` | _run | Trail |
| 389 | **mixed** | `test_consistent_succeeds` | _run | Trail |
| 393 | **mixed** | `test_unbound_atom_error` | _run | Trail, Var |
| 398 | **infra** | `test_empty_string` |  | Trail, Var, deref |
| 410 | **infra** | `test_before_bound_enumerate` |  | Trail, Var, deref |
| 426 | **infra** | `test_int_forward` |  | Trail, Var, deref |
| 434 | **infra** | `test_int_reverse` |  | Trail, Var, deref |
| 442 | **infra** | `test_float_forward` |  | Trail, Var, deref |
| 450 | **infra** | `test_float_reverse` |  | Trail, Var, deref |
| 458 | **infra** | `test_negative` |  | Trail, Var, deref |
| 466 | **mixed** | `test_invalid_chars_fails` | _run | Trail, Var |
| 472 | **mixed** | `test_both_bound_consistent` | _run | Trail |
| 477 | **mixed** | `test_both_bound_inconsistent` | _run | Trail |
| 482 | **mixed** | `test_both_unbound_raises` | _run | Trail, Var |
| 488 | **mixed** | `test_bool_raises` | _run | Trail, Var |
| 500 | **infra** | `test_int_forward` |  | Trail, Var, deref |
| 508 | **infra** | `test_int_reverse` |  | Trail, Var, deref |
| 516 | **infra** | `test_float_forward` |  | Trail, Var, deref |
| 524 | **infra** | `test_float_reverse` |  | Trail, Var, deref |
| 533 | **infra** | `test_negative` |  | Trail, Var, deref |
| 541 | **mixed** | `test_invalid_codes_fails` | _run | Trail, Var |
| 547 | **mixed** | `test_both_unbound_raises` | _run | Trail, Var |
| 553 | **mixed** | `test_non_int_code_raises` | _run | Trail, Var |

</details>

<details><summary><code>tests/test_clausal_modules.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 55 | **mixed** | `test_squares_basic` | call | Module, Var |
| 60 | **mixed** | `test_squares_empty` | call | Module, Var |
| 65 | **mixed** | `test_squares_single` | call | Module, Var |
| 70 | **mixed** | `test_squares_negative` | call | Module, Var |
| 80 | **mixed** | `test_positives_mixed` | call | Module, Var |
| 85 | **mixed** | `test_positives_all_negative` | call | Module, Var |
| 90 | **mixed** | `test_positives_all_positive` | call | Module, Var |
| 95 | **mixed** | `test_positives_with_zero` | call | Module, Var |
| 105 | **mixed** | `test_unique_dedup` | call | Module, Var |
| 110 | **mixed** | `test_unique_already_unique` | call | Module, Var |
| 115 | **mixed** | `test_unique_single` | call | Module, Var |
| 125 | **mixed**† | `test_all_positive_succeeds` | call | Module |
| 129 | **mixed**† | `test_all_positive_fails` | call | Module |
| 133 | **mixed**† | `test_all_positive_empty` | call | Module |
| 143 | **mixed** | `test_sum_squares` | call | Module, Var |
| 148 | **mixed** | `test_sum_squares_empty` | call | Module, Var |
| 158 | **mixed** | `test_evens` | call | Module, Var |
| 163 | **mixed** | `test_evens_none` | call | Module, Var |
| 173 | **mixed** | `test_count` | call | Module, Var |
| 178 | **mixed** | `test_count_empty` | call | Module, Var |
| 188 | **mixed** | `test_pairs_cartesian` | call | Module, Var |
| 194 | **mixed** | `test_pairs_empty_first` | call | Module, Var |
| 199 | **mixed** | `test_pairs_empty_second` | call | Module, Var |
| 209 | **mixed** | `test_all_members_subset` | call | Module |
| 213 | **mixed** | `test_all_members_not_subset` | call | Module |
| 217 | **mixed** | `test_all_members_empty_sub` | call | Module |
| 226 | **mixed** | `test_bag_positives` | call | Module, Var |
| 231 | **mixed** | `test_bag_positives_fails_on_none` | call | Module, Var |
| 247 | **mixed** | `test_doubles` | call | Module, Var |
| 252 | **mixed** | `test_doubles_empty` | call | Module, Var |
| 257 | **mixed** | `test_doubles_negative` | call | Module, Var |
| 267 | **mixed**† | `test_all_positive_pass` | call | Module |
| 271 | **mixed**† | `test_all_positive_fail` | call | Module |
| 275 | **mixed**† | `test_all_positive_empty` | call | Module |
| 284 | **mixed** | `test_keep_positive` | call | Module, Var |
| 289 | **mixed** | `test_keep_positive_none` | call | Module, Var |
| 294 | **mixed** | `test_keep_positive_all` | call | Module, Var |
| 304 | **mixed** | `test_remove_negative` | call | Module, Var |
| 309 | **mixed** | `test_remove_negative_none` | call | Module, Var |
| 319 | **mixed** | `test_sum` | call | Module, Var |
| 324 | **mixed** | `test_sum_empty` | call | Module, Var |
| 329 | **mixed** | `test_sum_single` | call | Module, Var |
| 339 | **mixed** | `test_product` | call | Module, Var |
| 344 | **mixed** | `test_product_empty` | call | Module, Var |
| 349 | **mixed** | `test_product_with_zero` | call | Module, Var |
| 359 | **mixed** | `test_squares` | call | Module, Var |
| 369 | **mixed** | `test_keep_even` | call | Module, Var |
| 374 | **mixed** | `test_keep_even_none` | call | Module, Var |
| 384 | **mixed** | `test_remove_even` | call | Module, Var |
| 394 | **mixed** | `test_negate` | call | Module, Var |
| 399 | **mixed** | `test_negate_empty` | call | Module, Var |
| 409 | **mixed** | `test_count` | call | Module, Var |
| 414 | **mixed** | `test_count_empty` | call | Module, Var |
| 424 | **mixed** | `test_max_fold` | call | Module, Var |
| 429 | **mixed** | `test_max_fold_single` | call | Module, Var |
| 434 | **mixed** | `test_max_fold_init_wins` | call | Module, Var |
| 449 | **mixed** | `test_apply_val` | call | Module, Var |
| 454 | **mixed** | `test_apply_val_string` | call | Module, Var |
| 464 | **mixed** | `test_add_one` | call | Module, Var |
| 469 | **mixed** | `test_add_one_negative` | call | Module, Var |
| 479 | **mixed** | `test_add_z` | call | Module, Var |
| 484 | **mixed** | `test_add_z_zero` | call | Module, Var |
| 494 | **mixed** | `test_double_val` | call | Module, Var |
| 504 | **mixed** | `test_zero_arg` | call | Module, Var |
| 514 | **mixed** | `test_transform` | call | Module, Var |
| 520 | **mixed** | `test_transform_zero` | call | Module, Var |
| 531 | **mixed** | `test_capture_two` | call | Module, Var |
| 542 | **mixed** | `test_apply_pred` | call | Module, Var |
| 553 | **mixed** | `test_all_colors` | call | Module, Var |
| 569 | **mixed** | `test_copy_ground_term` | call | Compound, Module, Var |
| 578 | **mixed** | `test_copy_returns_fresh_copy` | call | Compound, Module, Var |
| 592 | **mixed** | `test_copy_atom` | call | Module, Var |
| 598 | **mixed** | `test_copy_integer` | call | Module, Var |
| 604 | **mixed** | `test_copy_list` | call | Module, Var |
| 615 | **mixed** | `test_ground_term_no_vars` | call | Compound, Module |
| 620 | **mixed** | `test_ground_atom` | call | Module |
| 624 | **mixed** | `test_term_with_var_fails` | call | Compound, Module, Var |
| 630 | **mixed** | `test_ground_list` | call | Module |
| 634 | **mixed** | `test_list_with_var_fails` | call | Module, Var |
| 643 | **mixed** | `test_no_vars` | call | Compound, Module, Var |
| 650 | **mixed** | `test_one_var` | call | Compound, Module, Var |
| 657 | **mixed** | `test_two_vars` | call | Compound, Module, Var |
| 664 | **mixed** | `test_repeated_var_counts_once` | call | Compound, Module, Var |
| 672 | **mixed** | `test_list_vars` | call | Module, Var |
| 683 | **mixed** | `test_no_vars` | call | Compound, Module, Var |
| 690 | **mixed** | `test_one_var` | call | Compound, Module, Var |
| 697 | **mixed** | `test_start_offset` | call | Compound, Module, Var |
| 704 | **mixed** | `test_two_vars_consecutive` | call | Module, Var |
| 715 | **mixed** | `test_sharing_preserved` | call | Compound, Var, deref |
| 731 | **mixed** | `test_sharing_independent_from_original` | call | Compound, Var, deref |
| 750 | **mixed** | `test_empty_list` | call | Module, Var |
| 756 | **mixed** | `test_list_no_vars` | call | Module, Var |
| 762 | **mixed** | `test_list_with_vars` | call | Var |
| 785 | **mixed** | `test_catch_integer` | call | Module, Var |
| 790 | **mixed** | `test_catch_string` | call | Module, Var |
| 800 | **mixed** | `test_safe_recip_nonzero` | call | Module, Var |
| 805 | **mixed** | `test_safe_recip_zero` | call | Module, Var |
| 815 | **mixed** | `test_inner_miss` | call | Module, Var |
| 820 | **mixed** | `test_inner_hit` | call | Module, Var |
| 834 | **mixed** | `test_parent_backtracks` | call | Module, Var |
| 844 | **mixed** | `test_no_throw` | call | Module, Var |
| 849 | **mixed** | `test_multiple_solutions` | call | Module, Var |

</details>

<details><summary><code>tests/test_crypto_modules.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 49 | **infra** | `test_sha256_known_vector` |  | Trail, Var, deref |
| 57 | **infra** | `test_sha512` |  | Trail, Var, deref |
| 64 | **infra** | `test_md5` |  | Trail, Var, deref |
| 72 | **infra** | `test_sha1` |  | Trail, Var, deref |
| 80 | **infra** | `test_bytes_input` |  | Trail, Var, deref |
| 88 | **infra** | `test_unknown_algorithm_fails` |  | Trail, Var |
| 94 | **infra** | `test_unbound_data_fails` |  | Trail, Var |
| 100 | **infra** | `test_unbound_algorithm_fails` |  | Trail, Var |
| 106 | **infra** | `test_trampoline_protocol` |  | Trail, Var, _get_dispatch, deref |
| 119 | **infra** | `test_returns_bytes` |  | Trail, Var, deref |
| 126 | **infra** | `test_length_matches_algorithm` |  | Trail, Var, deref |
| 143 | **infra** | `test_sha256_known_vector` |  | Trail, Var, deref |
| 153 | **infra** | `test_default_sha256` |  | Trail, Var, deref |
| 162 | **infra** | `test_different_key_different_result` |  | Trail, Var, deref |
| 170 | **infra** | `test_unbound_key_fails` |  | Trail, Var |
| 176 | **infra** | `test_custom_algorithm` |  | Trail, Var, deref |
| 184 | **infra** | `test_trampoline_protocol` |  | Trail, Var, _get_dispatch |
| 196 | **infra** | `test_correct_hmac_succeeds` |  | Trail, Var, deref |
| 204 | **infra** | `test_incorrect_hmac_fails` |  | Trail |
| 209 | **infra** | `test_custom_algorithm` |  | Trail, Var, deref |
| 223 | **infra** | `test_known_derivation` |  | Trail, Var, deref |
| 232 | **infra** | `test_different_iterations_different_result` |  | Trail, Var, deref |
| 240 | **infra** | `test_default_key_length` |  | Trail, Var, deref |
| 249 | **infra** | `test_unbound_password_fails` |  | Trail, Var |
| 255 | **infra** | `test_zero_iterations_fails` |  | Trail, Var |
| 261 | **infra** | `test_trampoline_protocol` |  | Trail, Var, _get_dispatch |

</details>

<details><summary><code>tests/test_csv_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 48 | **infra** | `test_simple` |  | Trail, Var, deref |
| 55 | **infra** | `test_quoted_fields` |  | Trail, Var, deref |
| 62 | **infra** | `test_empty_string` |  | Trail, Var, deref |
| 69 | **infra** | `test_single_field` |  | Trail, Var, deref |
| 76 | **infra** | `test_unbound_string_fails` |  | Trail, Var |
| 81 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 93 | **infra** | `test_multi_line` |  | Trail, Var, deref |
| 105 | **infra** | `test_empty_input` |  | Trail, Var, deref |
| 112 | **infra** | `test_mixed_quoted` |  | Trail, Var, deref |
| 122 | **infra**† | `test_unbound_fails` |  | Trail, Var |
| 132 | **infra** | `test_basic` |  | DictTerm, Trail, Var, deref |
| 146 | **infra** | `test_headers_only` |  | Trail, Var, deref |
| 155 | **infra** | `test_empty_fails` |  | Trail, Var |
| 161 | **infra**† | `test_unbound_fails` |  | Trail, Var |
| 171 | **infra** | `test_basic` |  | Trail, Var, deref |
| 181 | **infra** | `test_quoting` |  | Trail, Var, deref |
| 190 | **infra** | `test_round_trip` |  | Trail, Var, deref |
| 200 | **infra**† | `test_unbound_fails` |  | Trail, Var |
| 205 | **infra** | `test_non_list_row_fails` |  | Trail, Var |
| 215 | **infra** | `test_basic` |  | DictTerm, Trail, Var, deref |
| 226 | **infra** | `test_unbound_headers_fails` |  | Trail, Var |
| 231 | **infra** | `test_non_dict_term_record_fails` |  | Trail, Var |
| 243 | **infra** | `test_round_trip` |  | Trail, Var, deref |
| 258 | **infra** | `test_read_nonexistent_fails` |  | Trail, Var |
| 263 | **infra**† | `test_read_unbound_path_fails` |  | Trail, Var |
| 268 | **infra** | `test_write_unbound_rows_fails` |  | Trail, Var |
| 278 | **infra** | `test_basic` |  | DictTerm, Trail, Var, deref |
| 293 | **infra** | `test_nonexistent_fails` |  | Trail, Var |

</details>

<details><summary><code>tests/test_date_time.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 52 | **infra** | `test_now_binds_datetime` |  | Trail, Var, deref |
| 60 | **infra** | `test_now_utc_binds_datetime` |  | Trail, Var, deref |
| 69 | **infra** | `test_today_binds_date` |  | Trail, Var, deref |
| 84 | **infra** | `test_construct` |  | Trail, Var, deref |
| 94 | **infra** | `test_decompose` |  | Trail, Var, deref |
| 104 | **infra** | `test_decompose_datetime_object` |  | Trail, Var, deref |
| 116 | **infra** | `test_construct_invalid_date_fails` |  | Trail, Var |
| 123 | **infra** | `test_construct_and_check` |  | Trail |
| 132 | **infra** | `test_construct_and_check_mismatch` |  | Trail |
| 141 | **infra** | `test_leap_year` |  | Trail, Var, deref |
| 149 | **infra** | `test_non_leap_year_feb29_fails` |  | Trail, Var |
| 161 | **infra** | `test_construct` |  | Trail, Var, deref |
| 168 | **infra** | `test_decompose` |  | Trail, Var, deref |
| 177 | **infra** | `test_construct_invalid_fails` |  | Trail, Var |
| 183 | **infra** | `test_midnight` |  | Trail, Var, deref |
| 195 | **infra** | `test_construct` |  | Trail, Var, deref |
| 205 | **infra** | `test_decompose` |  | Trail, Var, deref |
| 220 | **infra** | `test_construct_invalid_fails` |  | Trail, Var |
| 231 | **infra** | `test_construct` |  | Trail, Var, deref |
| 238 | **infra** | `test_construct_days_only` |  | Trail, Var, deref |
| 247 | **infra** | `test_decompose` |  | Trail, Var, deref |
| 261 | **infra** | `test_add_days_to_date` |  | Trail, Var, deref |
| 270 | **infra** | `test_add_to_datetime` |  | Trail, Var, deref |
| 282 | **infra** | `test_add_non_date_fails` |  | Trail, Var |
| 288 | **infra** | `test_add_non_timedelta_fails` |  | Trail, Var |
| 299 | **infra** | `test_sub_days_from_date` |  | Trail, Var, deref |
| 308 | **infra** | `test_sub_from_datetime` |  | Trail, Var, deref |
| 325 | **infra** | `test_diff_dates` |  | Trail, Var, deref |
| 334 | **infra** | `test_diff_datetimes` |  | Trail, Var, deref |
| 346 | **infra** | `test_negative_diff` |  | Trail, Var, deref |
| 355 | **infra** | `test_diff_non_dates_fails` |  | Trail, Var |
| 366 | **infra** | `test_format_date` |  | Trail, Var, deref |
| 375 | **infra** | `test_format_datetime` |  | Trail, Var, deref |
| 387 | **infra** | `test_format_time` |  | Trail, Var, deref |
| 401 | **infra** | `test_parse_date_string` |  | Trail, Var, deref |
| 414 | **infra** | `test_parse_datetime_string` |  | Trail, Var, deref |
| 424 | **infra** | `test_parse_invalid_fails` |  | Trail, Var |
| 432 | **infra** | `test_parse_format_roundtrip` |  | Trail, Var, deref |
| 448 | **infra** | `test_weekday` |  | Trail, Var, deref |
| 457 | **infra** | `test_sunday` |  | Trail, Var, deref |
| 466 | **infra** | `test_non_date_fails` |  | Trail, Var |
| 477 | **infra** | `test_range_three_days` |  | Trail, Var, _get_dispatch |
| 489 | **infra** | `test_single_day` |  | Trail, Var, _get_dispatch |
| 500 | **infra** | `test_empty_range` |  | Trail, Var, _get_dispatch |
| 511 | **infra** | `test_week_range` |  | Trail, Var, _get_dispatch |
| 522 | **infra** | `test_non_date_fails` |  | Trail, Var, _get_dispatch |
| 535 | **infra** | `test_same_date_unifies` |  | Trail, Var, deref, unify |
| 542 | **infra** | `test_different_dates_fail` |  | Trail, Var, unify |
| 550 | **infra** | `test_datetime_unifies` |  | Trail, Var, deref, unify |
| 558 | **infra** | `test_timedelta_unifies` |  | Trail, Var, deref, unify |
| 571 | **infra** | `test_now_has_dispatch` |  | _get_dispatch |
| 575 | **infra** | `test_today_has_dispatch` |  | _get_dispatch |
| 579 | **infra** | `test_date_has_dispatch` |  | _get_dispatch |
| 583 | **infra** | `test_time_has_dispatch` |  | _get_dispatch |
| 587 | **infra** | `test_datetime_has_dispatch` |  | _get_dispatch |
| 591 | **infra** | `test_timedelta_has_dispatch` |  | _get_dispatch |
| 595 | **infra** | `test_date_add_has_dispatch` |  | _get_dispatch |
| 599 | **infra** | `test_date_sub_has_dispatch` |  | _get_dispatch |
| 603 | **infra** | `test_date_diff_has_dispatch` |  | _get_dispatch |
| 607 | **infra** | `test_format_date_has_dispatch` |  | _get_dispatch |
| 611 | **infra** | `test_parse_date_has_dispatch` |  | _get_dispatch |
| 615 | **infra** | `test_day_of_week_has_dispatch` |  | _get_dispatch |
| 619 | **infra** | `test_date_between_has_dispatch` |  | _get_dispatch |
| 623 | **unknown** | `test_repr` |  |  |

</details>

<details><summary><code>tests/test_dict_set_builtins.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 65 | **mixed** | `test_is_dict_succeeds` | solve | Call, DictTerm, LoadName, Module |
| 69 | **mixed** | `test_is_dict_fails_on_atom` | solve | Call, LoadName, Module |
| 73 | **mixed** | `test_is_dict_fails_on_set` | solve | Call, LoadName, Module, SetTerm |
| 77 | **mixed** | `test_is_dict_fails_on_atom` | solve | Call, LoadName, Module |
| 81 | **mixed** | `test_is_dict_fails_on_var` | solve | Call, LoadName, Module, Var |
| 90 | **mixed** | `test_size_empty` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 96 | **mixed** | `test_size_three` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 103 | **mixed** | `test_size_fails_on_non_dict` | solve | Call, LoadName, Module, Var |
| 112 | **mixed** | `test_keys_sorted` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 119 | **mixed** | `test_keys_unify_succeeds` | solve | Call, DictTerm, LoadName, Module |
| 124 | **mixed** | `test_keys_wrong_order_fails` | solve | Call, DictTerm, LoadName, Module |
| 134 | **mixed** | `test_values_in_key_order` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 146 | **mixed** | `test_dict_to_pairs` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 153 | **mixed** | `test_pairs_to_dict` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 160 | **mixed** | `test_pairs_to_dict_unordered` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 172 | **mixed** | `test_get_existing_key` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 179 | **mixed** | `test_get_missing_key_fails` | solve | Call, DictTerm, LoadName, Module, Var |
| 184 | **mixed** | `test_get_value_unify_succeeds` | solve | Call, DictTerm, LoadName, Module |
| 189 | **mixed** | `test_get_value_unify_fails` | solve | Call, DictTerm, LoadName, Module |
| 194 | **mixed** | `test_get_fails_unbound_key` | solve | Call, DictTerm, LoadName, Module, Var |
| 204 | **mixed** | `test_put_new_key` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 211 | **mixed** | `test_put_overwrite_key` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 218 | **mixed** | `test_put_fails_unbound_key` | solve | Call, DictTerm, LoadName, Module, Var |
| 228 | **mixed** | `test_put_pairs_bulk` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 236 | **mixed** | `test_put_pairs_overwrite` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 248 | **mixed** | `test_remove_existing_key` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 255 | **mixed** | `test_remove_missing_key_fails` | solve | Call, DictTerm, LoadName, Module, Var |
| 265 | **mixed** | `test_merge_disjoint` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 273 | **mixed** | `test_merge_d2_overrides` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 281 | **mixed** | `test_merge_empty_d1` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 293 | **mixed** | `test_gen_dict_all_pairs` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 303 | **mixed** | `test_gen_dict_count` | solve | Call, DictTerm, LoadName, Module, Var |
| 309 | **mixed** | `test_gen_dict_filter_by_key` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 317 | **mixed** | `test_gen_dict_empty` | solve | Call, DictTerm, LoadName, Module, Var |
| 327 | **mixed** | `test_subdict_exact_match` | solve | Call, DictTerm, LoadName, Module |
| 333 | **mixed** | `test_subdict_with_var_binds_value` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 344 | **mixed** | `test_subdict_fails_missing_key` | solve | Call, DictTerm, LoadName, Module |
| 350 | **mixed** | `test_subdict_fails_value_mismatch` | solve | Call, DictTerm, LoadName, Module |
| 356 | **mixed** | `test_subdict_empty_pattern_always_succeeds` | solve | Call, DictTerm, LoadName, Module |
| 361 | **mixed** | `test_subdict_fails_non_dict_pattern` | solve | Call, DictTerm, LoadName, Module |
| 365 | **mixed** | `test_subdict_fails_non_dict_full` | solve | Call, DictTerm, LoadName, Module |
| 369 | **mixed** | `test_subdict_backtracking_undo` | solve | Call, DictTerm, LoadName, Module, Trail, Var, deref |
| 386 | **mixed** | `test_is_set_succeeds` | solve | Call, LoadName, Module, SetTerm |
| 390 | **mixed** | `test_is_set_fails_on_list` | solve | Call, LoadName, Module |
| 394 | **mixed** | `test_is_set_fails_on_dict` | solve | Call, DictTerm, LoadName, Module |
| 398 | **mixed** | `test_is_set_fails_on_var` | solve | Call, LoadName, Module, Var |
| 407 | **mixed** | `test_size` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 414 | **mixed** | `test_size_empty` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 425 | **mixed** | `test_set_to_list` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 433 | **mixed** | `test_list_to_set` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 439 | **mixed** | `test_list_to_set_deduplicates` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 450 | **mixed** | `test_union` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 458 | **mixed** | `test_union_disjoint` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 469 | **mixed** | `test_intersection` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 477 | **mixed** | `test_intersection_empty` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 488 | **mixed** | `test_subtract` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 496 | **mixed** | `test_subtract_all` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 507 | **mixed** | `test_symdiff` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 515 | **mixed** | `test_symdiff_disjoint` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 526 | **mixed** | `test_subset_true` | solve | Call, LoadName, Module, SetTerm |
| 530 | **mixed** | `test_subset_false` | solve | Call, LoadName, Module, SetTerm |
| 534 | **mixed** | `test_subset_equal` | solve | Call, LoadName, Module, SetTerm |
| 538 | **mixed** | `test_empty_is_subset_of_anything` | solve | Call, LoadName, Module, SetTerm |
| 542 | **mixed** | `test_disjoint_true` | solve | Call, LoadName, Module, SetTerm |
| 546 | **mixed** | `test_disjoint_false` | solve | Call, LoadName, Module, SetTerm |
| 550 | **mixed** | `test_disjoint_empty` | solve | Call, LoadName, Module, SetTerm |
| 559 | **mixed** | `test_add` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 566 | **mixed** | `test_add_existing_is_noop` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 573 | **mixed** | `test_remove` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 580 | **mixed** | `test_remove_absent_is_noop` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 592 | **mixed** | `test_gen_set_all` | solve | Call, LoadName, Module, SetTerm, Trail, Var, deref |
| 602 | **mixed** | `test_gen_set_count` | solve | Call, LoadName, Module, SetTerm, Var |
| 608 | **mixed** | `test_gen_set_empty` | solve | Call, LoadName, Module, SetTerm, Var |
| 635 | **infra** | `test_get_name` |  | DictTerm, Var |
| 643 | **infra** | `test_is_admin` |  | DictTerm |
| 651 | **infra** | `test_update_field` |  | DictTerm, Var |
| 658 | **infra** | `test_dict_member` |  | DictTerm, Var |
| 666 | **infra** | `test_set_common` |  | SetTerm, Var |
| 674 | **infra** | `test_set_member` |  | SetTerm, Var |
| 682 | **infra** | `test_dict_key` |  | DictTerm, Var |
| 691 | **infra** | `test_splat_update` |  | DictTerm, Var |
| 738 | **infra** | `test_key_in_dict_enumerates_keys` |  | DictTerm, Var |
| 746 | **infra** | `test_key_in_dict_filters` |  | DictTerm |
| 752 | **infra** | `test_key_in_dict_empty` |  | DictTerm, Var |
| 758 | **infra** | `test_pair_in_dict_enumerates_pairs` |  | DictTerm, Var |
| 766 | **infra** | `test_pair_in_dict_filter_by_key` |  | DictTerm, Var |
| 774 | **infra** | `test_pair_in_dict_unifies_value` |  | DictTerm, Var |
| 783 | **infra** | `test_pair_in_dict_empty` |  | DictTerm, Var |
| 789 | **infra** | `test_key_not_in_dict` |  | DictTerm |
| 795 | **infra** | `test_key_not_in_dict_fails` |  | DictTerm |
| 801 | **infra** | `test_pair_not_in_dict` |  | DictTerm |
| 807 | **infra** | `test_pair_not_in_dict_wrong_value` |  | DictTerm |

</details>

<details><summary><code>tests/test_dict_set_compiler.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 33 | **infra** | `test_dictterm_unify_with_vars` |  | DictTerm, Trail, Var, deref, unify |
| 43 | **infra** | `test_dictterm_unify_fails_different_keys` |  | DictTerm, Trail, unify |
| 48 | **infra** | `test_dictterm_unify_fails_value_mismatch` |  | DictTerm, Trail, unify |
| 53 | **infra** | `test_dictterm_unify_trail_undo` |  | DictTerm, Trail, Var, deref, unify |
| 63 | **infra** | `test_setterm_unify_same` |  | SetTerm, Trail, unify |
| 68 | **infra** | `test_setterm_unify_different` |  | SetTerm, Trail, unify |
| 73 | **infra** | `test_var_unifies_with_dictterm` |  | DictTerm, Trail, Var, deref, unify |
| 81 | **infra** | `test_var_unifies_with_setterm` |  | SetTerm, Trail, Var, deref, unify |
| 89 | **infra** | `test_dictterm_not_implemented_for_non_dict` |  | DictTerm, Trail, unify |
| 94 | **infra** | `test_empty_dictterms_unify` |  | DictTerm, Trail, unify |
| 99 | **infra** | `test_nested_dictterm_unify` |  | DictTerm, Trail, Var, deref, unify |
| 108 | **infra** | `test_setterm_not_implemented_for_non_set` |  | SetTerm, Trail, unify |
| 113 | **infra** | `test_empty_setterms_unify` |  | SetTerm, Trail, unify |
| 137 | **unknown** | `test_origin` |  |  |
| 141 | **unknown** | `test_x_axis` |  |  |
| 145 | **unknown** | `test_get_x` |  |  |
| 149 | **unknown** | `test_get_y` |  |  |
| 153 | **unknown** | `test_nested_city` |  |  |
| 157 | **unknown** | `test_make_point` |  |  |
| 161 | **unknown** | `test_dict_unify` |  |  |
| 165 | **unknown** | `test_dict_key_mismatch` |  |  |
| 169 | **unknown** | `test_set_match` |  |  |
| 173 | **unknown** | `test_set_primary` |  |  |
| 177 | **unknown** | `test_set_mismatch` |  |  |
| 181 | **unknown** | `test_var_binds_dict` |  |  |
| 185 | **unknown** | `test_empty_dict` |  |  |
| 203 | **mixed** | `test_multiple_dict_clauses` | call | Var |
| 209 | **mixed** | `test_get_x_different_inputs` | call | DictTerm, Var, deref |
| 217 | **mixed** | `test_get_x_another_input` | call | DictTerm, Var, deref |

</details>

<details><summary><code>tests/test_dict_set_terms.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 30 | **infra** | `test_construction` |  | DictTerm |
| 37 | **infra** | `test_defensive_copy` |  | DictTerm |
| 44 | **infra** | `test_keys_values_items` |  | DictTerm |
| 51 | **infra** | `test_contains` |  | DictTerm |
| 57 | **infra** | `test_equality` |  | DictTerm |
| 63 | **infra** | `test_inequality_different_keys` |  | DictTerm |
| 69 | **infra** | `test_inequality_different_values` |  | DictTerm |
| 75 | **infra** | `test_not_equal_to_plain_dict` |  | DictTerm |
| 80 | **infra** | `test_hash` |  | DictTerm |
| 86 | **infra** | `test_repr` |  | DictTerm |
| 92 | **infra** | `test_term_str` |  | DictTerm |
| 103 | **infra** | `test_same_ground_succeeds` |  | DictTerm, Trail, structural_unify |
| 110 | **infra** | `test_different_keys_fails` |  | DictTerm, Trail, structural_unify |
| 117 | **infra** | `test_different_key_count_fails` |  | DictTerm, Trail, structural_unify |
| 124 | **infra** | `test_different_values_fails` |  | DictTerm, Trail, structural_unify |
| 131 | **infra** | `test_var_in_value_binds` |  | DictTerm, Trail, Var, deref, structural_unify |
| 140 | **infra** | `test_var_on_both_sides` |  | DictTerm, Trail, Var, deref, structural_unify |
| 151 | **infra** | `test_nested_dict_with_vars` |  | DictTerm, Trail, Var, deref, structural_unify |
| 160 | **infra** | `test_trail_undo_on_failure` |  | DictTerm, Trail, Var, structural_unify |
| 172 | **infra** | `test_empty_dicts_unify` |  | DictTerm, Trail, structural_unify |
| 177 | **infra** | `test_dict_does_not_unify_with_non_dict` |  | DictTerm, Trail, structural_unify |
| 184 | **infra** | `test_var_unifies_with_dict` |  | DictTerm, Trail, Var, deref, structural_unify |
| 197 | **infra** | `test_walk_substitutes_vars` |  | DictTerm, Trail, Var, unify |
| 208 | **infra** | `test_walk_nested` |  | DictTerm, Trail, Var, unify |
| 218 | **infra** | `test_walk_no_vars_returns_equivalent` |  | DictTerm |
| 229 | **infra** | `test_occurs_check_detects_var_in_value` |  | DictTerm, Trail, Var |
| 238 | **infra** | `test_occurs_check_allows_non_circular` |  | DictTerm, Trail, Var, deref |
| 252 | **infra** | `test_construction` |  | SetTerm |
| 259 | **infra** | `test_from_set` |  | SetTerm |
| 264 | **infra** | `test_equality_order_independent` |  | SetTerm |
| 270 | **infra** | `test_inequality` |  | SetTerm |
| 276 | **infra** | `test_not_equal_to_plain_set` |  | SetTerm |
| 281 | **infra** | `test_hash` |  | SetTerm |
| 287 | **infra** | `test_iter` |  | SetTerm |
| 292 | **infra** | `test_repr` |  | SetTerm |
| 297 | **infra** | `test_term_str` |  | SetTerm |
| 308 | **infra** | `test_same_sets_unify` |  | SetTerm, Trail, structural_unify |
| 315 | **infra** | `test_different_sets_fail` |  | SetTerm, Trail, structural_unify |
| 322 | **infra** | `test_different_size_fails` |  | SetTerm, Trail, structural_unify |
| 329 | **infra** | `test_empty_sets_unify` |  | SetTerm, Trail, structural_unify |
| 334 | **infra** | `test_var_unifies_with_set` |  | SetTerm, Trail, Var, deref, structural_unify |
| 342 | **infra** | `test_set_does_not_unify_with_non_set` |  | SetTerm, Trail, structural_unify |
| 353 | **infra** | `test_collect_vars_from_dictterm` |  | DictTerm, Var |
| 364 | **infra** | `test_collect_vars_from_setterm_empty` |  | SetTerm |

</details>

<details><summary><code>tests/test_files_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 59 | **infra** | `test_existing_file` |  | Trail |
| 66 | **infra** | `test_nonexistent_fails` |  | Trail |
| 71 | **infra** | `test_directory_fails` |  | Trail |
| 76 | **infra** | `test_unbound_fails` |  | Trail, Var |
| 81 | **infra** | `test_trampoline` |  | Trail, _get_dispatch |
| 93 | **infra** | `test_existing_dir` |  | Trail |
| 98 | **infra** | `test_file_fails` |  | Trail |
| 105 | **infra** | `test_nonexistent_fails` |  | Trail |
| 115 | **infra** | `test_file_exists` |  | Trail |
| 122 | **infra** | `test_dir_exists` |  | Trail |
| 127 | **infra** | `test_nonexistent_fails` |  | Trail |
| 137 | **infra** | `test_lists_files` |  | Trail, Var, deref |
| 149 | **infra** | `test_nonexistent_dir_fails` |  | Trail, Var |
| 154 | **infra** | `test_unbound_dir_fails` |  | Trail, Var |
| 159 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 172 | **infra** | `test_enumerates_entries` |  | Trail, Var |
| 183 | **infra** | `test_matches_directory_files` |  | Trail, Var, deref |
| 204 | **infra** | `test_returns_size` |  | Trail, Var, deref |
| 215 | **infra** | `test_nonexistent_fails` |  | Trail, Var |
| 225 | **infra** | `test_returns_float` |  | Trail, Var, deref |
| 236 | **infra** | `test_nonexistent_fails` |  | Trail, Var |
| 248 | **infra** | `test_deletes_file` |  | Trail |
| 257 | **infra** | `test_nonexistent_fails` |  | Trail |
| 262 | **infra** | `test_unbound_fails` |  | Trail, Var |
| 272 | **infra** | `test_deletes_empty_dir` |  | Trail |
| 281 | **infra** | `test_nonempty_fails` |  | Trail |
| 294 | **infra** | `test_renames` |  | Trail |
| 305 | **infra** | `test_nonexistent_fails` |  | Trail |
| 317 | **infra** | `test_copies` |  | Trail |
| 328 | **infra** | `test_nonexistent_source_fails` |  | Trail |
| 340 | **infra** | `test_creates_dir` |  | Trail |
| 348 | **infra** | `test_already_exists_fails` |  | Trail |
| 358 | **infra** | `test_creates_nested` |  | Trail |
| 366 | **infra** | `test_already_exists_succeeds` |  | Trail |
| 376 | **infra** | `test_reads_file` |  | Trail, Var, deref |
| 385 | **infra** | `test_nonexistent_fails` |  | Trail, Var |
| 392 | **infra** | `test_unbound_path_fails` |  | Trail, Var |
| 397 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 411 | **infra** | `test_writes_file` |  | Trail |
| 418 | **infra** | `test_overwrites` |  | Trail |
| 425 | **infra** | `test_unbound_contents_fails` |  | Trail, Var |
| 437 | **infra** | `test_appends` |  | Trail |
| 445 | **infra** | `test_creates_if_missing` |  | Trail |
| 457 | **infra** | `test_resolves` |  | Trail, Var, deref |
| 465 | **infra** | `test_unbound_fails` |  | Trail, Var |
| 475 | **infra** | `test_joins` |  | Trail, Var, deref |
| 482 | **infra** | `test_unbound_base_fails` |  | Trail, Var |
| 487 | **infra** | `test_unbound_relative_fails` |  | Trail, Var |
| 492 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 504 | **infra** | `test_splits` |  | Trail, Var, deref |
| 514 | **infra** | `test_unbound_fails` |  | Trail, Var |
| 524 | **infra** | `test_extension` |  | Trail, Var, deref |
| 531 | **infra** | `test_no_extension` |  | Trail, Var, deref |
| 538 | **infra** | `test_double_extension` |  | Trail, Var, deref |
| 550 | **infra** | `test_creates_temp_file` |  | Trail, Var, deref |
| 561 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 575 | **infra** | `test_creates_temp_dir` |  | Trail, Var, deref |
| 586 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |

</details>

<details><summary><code>tests/test_http_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 62 | **infra** | `test_get_200` |  | Trail, Var, deref |
| 71 | **infra** | `test_get_404_fails` |  | Trail, Var |
| 79 | **infra** | `test_unbound_url_fails` |  | Trail, Var |
| 86 | **infra** | `test_get_with_headers` |  | DictTerm, Trail, Var, deref |
| 102 | **infra** | `test_post_200` |  | Trail, Var, deref |
| 111 | **infra** | `test_post_data_sent` |  | Trail, Var |
| 122 | **infra** | `test_post_with_headers` |  | DictTerm, Trail, Var |
| 130 | **infra** | `test_post_unbound_data_fails` |  | Trail, Var |
| 143 | **infra** | `test_returns_status_code` |  | DictTerm, Trail, Var, deref |
| 154 | **infra** | `test_non_200_still_succeeds` |  | DictTerm, Trail, Var, deref |
| 175 | **infra** | `test_json_get_parses_dict` |  | DictTerm, Trail, Var, deref |
| 186 | **infra** | `test_json_get_parses_list` |  | Trail, Var, deref |
| 195 | **infra** | `test_json_post_serializes_and_parses` |  | DictTerm, Trail, Var, deref |
| 207 | **infra** | `test_invalid_json_fails` |  | Trail, Var |
| 220 | **infra** | `test_encode_special_chars` |  | Trail, Var, deref |
| 228 | **infra** | `test_encode_preserves_safe` |  | Trail, Var, deref |
| 235 | **infra** | `test_decode` |  | Trail, Var, deref |
| 242 | **infra** | `test_round_trip` |  | Trail, Var, deref |
| 250 | **infra**† | `test_unbound_fails` |  | Trail, Var |
| 261 | **infra** | `test_parse_full_url` |  | DictTerm, Trail, Var, deref |
| 276 | **infra** | `test_parse_simple_url` |  | Trail, Var, deref |
| 285 | **infra**† | `test_unbound_fails` |  | Trail, Var |
| 293 | **infra** | `test_join_basic` |  | DictTerm, Trail, Var, deref |
| 308 | **infra** | `test_join_no_port` |  | DictTerm, Trail, Var, deref |
| 323 | **infra**† | `test_unbound_fails` |  | Trail, Var |

</details>

<details><summary><code>tests/test_ipython_integration.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 32 | **infra** | `test_embed_name_produces_LoadName` |  | LoadName, ast, parse |
| 39 | **infra** | `test_embed_integer_is_native_int` |  | ast, parse |
| 46 | **infra** | `test_embed_float_is_native_float` |  | ast, parse |
| 53 | **infra** | `test_embed_string_is_native_str` |  | ast, parse |
| 60 | **infra** | `test_embed_bool_is_native_bool` |  | ast, parse |
| 66 | **infra** | `test_embed_none_is_native_none` |  | ast, parse |
| 74 | **infra** | `test_embed_call_no_args` |  | Call, LoadName, ast, parse |
| 85 | **infra** | `test_embed_call_with_int_args` |  | Call, ast, parse |
| 96 | **infra** | `test_embed_nested_call` |  | Call, ast, parse |
| 109 | **infra** | `test_embed_addition` |  | Add, ast, parse |
| 120 | **infra** | `test_each_visit_gets_fresh_transformer` |  | ast, parse |
| 134 | **infra** | `test_plain_python_unchanged` |  | ast, parse |
| 140 | **unknown** | `test_simple_ast_names_in_scope` |  |  |
| 150 | **unknown** | `test_star_query_input_transformer_single_goal` |  |  |
| 157 | **unknown** | `test_star_query_input_transformer_multi_goal` |  |  |
| 164 | **unknown** | `test_star_query_input_transformer_preserves_indent` |  |  |
| 171 | **unknown** | `test_star_query_input_transformer_ignores_non_star` |  |  |
| 178 | **unknown** | `test_star_query_input_transformer_ignores_star_not_paren` |  |  |
| 200 | **infra** | `test_sentinel_single_goal_compiles` |  | ast, parse |
| 214 | **infra** | `test_sentinel_multi_goal_compiles` |  | ast, parse |

</details>

<details><summary><code>tests/test_json_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 47 | **infra** | `test_python_to_clausal_dict` |  | DictTerm |
| 53 | **infra** | `test_python_to_clausal_nested` |  | DictTerm |
| 61 | **infra** | `test_python_to_clausal_list` |  | DictTerm |
| 68 | **unknown** | `test_python_to_clausal_scalars` |  |  |
| 76 | **infra** | `test_clausal_to_python_dict_term` |  | DictTerm |
| 82 | **infra** | `test_clausal_to_python_nested` |  | DictTerm |
| 88 | **infra** | `test_clausal_to_python_list` |  | DictTerm |
| 93 | **infra** | `test_clausal_to_python_unbound_var_raises` |  | Var |
| 103 | **infra** | `test_simple_object` |  | DictTerm, Trail, Var, deref |
| 113 | **infra** | `test_nested_object` |  | DictTerm, Trail, Var, deref |
| 123 | **infra** | `test_array` |  | Trail, Var, deref |
| 130 | **infra** | `test_string_scalar` |  | Trail, Var, deref |
| 137 | **infra** | `test_number_int` |  | Trail, Var, deref |
| 144 | **infra** | `test_number_float` |  | Trail, Var, deref |
| 151 | **infra** | `test_bool` |  | Trail, Var, deref |
| 158 | **infra** | `test_null` |  | Trail, Var, deref |
| 165 | **infra** | `test_empty_object` |  | DictTerm, Trail, Var, deref |
| 174 | **infra** | `test_empty_array` |  | Trail, Var, deref |
| 181 | **infra**† | `test_unbound_string_fails` |  | Trail, Var |
| 186 | **infra** | `test_invalid_json_fails` |  | Trail, Var |
| 191 | **infra** | `test_trampoline` |  | DictTerm, Trail, Var, _get_dispatch, deref |
| 203 | **infra** | `test_dict_term` |  | DictTerm, Trail, Var, deref |
| 212 | **infra** | `test_nested` |  | DictTerm, Trail, Var, deref |
| 221 | **infra** | `test_list` |  | Trail, Var, deref |
| 228 | **infra** | `test_scalars` |  | Trail, Var, deref |
| 235 | **infra**† | `test_unbound_var_fails` |  | Trail, Var |
| 241 | **infra** | `test_round_trip` |  | Trail, Var, deref |
| 257 | **infra** | `test_indented` |  | DictTerm, Trail, Var, deref |
| 272 | **infra** | `test_key_bound` |  | DictTerm, Trail, Var, deref |
| 280 | **infra** | `test_key_not_found_fails` |  | DictTerm, Trail, Var |
| 285 | **infra** | `test_key_unbound_enumerates` |  | DictTerm, Trail, Var |
| 309 | **infra** | `test_not_dict_term_fails` |  | Trail, Var |
| 314 | **infra** | `test_trampoline` |  | DictTerm, Trail, Var, _get_dispatch, deref |
| 327 | **infra** | `test_round_trip` |  | DictTerm, Trail, Var, deref |
| 342 | **infra** | `test_read_nonexistent_fails` |  | Trail, Var |
| 347 | **infra** | `test_write_unbound_term_fails` |  | Trail, Var |
| 352 | **infra**† | `test_read_unbound_path_fails` |  | Trail, Var |

</details>

<details><summary><code>tests/test_jupyter_integration.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 10 | **unknown** | `test_in_jupyter_kernel_false_in_test_env` |  |  |
| 16 | **unknown** | `test_in_jupyter_kernel_false_when_import_fails` |  |  |
| 28 | **unknown** | `test_format_bindings_html_empty` |  |  |
| 35 | **unknown** | `test_format_bindings_html_single` |  |  |
| 43 | **unknown** | `test_format_bindings_html_multiple` |  |  |
| 52 | **unknown** | `test_format_bindings_html_escapes_key` |  |  |
| 61 | **unknown** | `test_repr_html_no_solutions` |  |  |
| 68 | **unknown** | `test_repr_html_single_solution` |  |  |
| 76 | **unknown** | `test_repr_html_multiple_solutions` |  |  |
| 86 | **unknown** | `test_repr_html_or_separator` |  |  |
| 92 | **unknown** | `test_repr_html_limit_default` |  |  |
| 102 | **unknown** | `test_repr_html_limit_custom` |  |  |
| 109 | **unknown** | `test_repr_html_limit_not_hit` |  |  |
| 118 | **unknown** | `test_repr_html_true_for_ground_query` |  |  |
| 125 | **unknown** | `test_repr_html_html_escaping` |  |  |
| 133 | **unknown** | `test_repr_html_contains_css` |  |  |
| 143 | **unknown** | `test_ipython_display_calls_run_in_terminal` |  |  |
| 154 | **unknown** | `test_ipython_display_uses_html_in_jupyter` |  |  |

</details>

<details><summary><code>tests/test_list_util.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 124 | **infra** | `test_basic` |  | Trail, Var, deref |
| 128 | **infra** | `test_take_zero` |  | Trail, Var, deref |
| 132 | **infra** | `test_take_more_than_length` |  | Trail, Var, deref |
| 136 | **infra** | `test_take_from_empty` |  | Trail, Var, deref |
| 142 | **infra** | `test_basic` |  | Trail, Var, deref |
| 146 | **infra** | `test_drop_zero` |  | Trail, Var, deref |
| 150 | **infra** | `test_drop_all` |  | Trail, Var, deref |
| 154 | **infra** | `test_drop_more_than_length` |  | Trail, Var, deref |
| 160 | **infra** | `test_middle` |  | Trail, Var, deref |
| 164 | **infra** | `test_at_zero` |  | Trail, Var, deref |
| 168 | **infra** | `test_at_end` |  | Trail, Var, deref |
| 172 | **infra** | `test_beyond_length` |  | Trail, Var, deref |
| 178 | **infra** | `test_equal_length` |  | Trail, Var, deref |
| 184 | **infra** | `test_unequal_length` |  | Trail, Var, deref |
| 190 | **infra** | `test_empty` |  | Trail, Var, deref |
| 196 | **infra** | `test_basic` |  | Trail, Var, deref |
| 200 | **infra** | `test_zero` |  | Trail, Var, deref |
| 204 | **infra** | `test_one` |  | Trail, Var, deref |
| 210 | **infra** | `test_split_by_element` |  | Trail, Var, deref |
| 216 | **infra** | `test_no_separator` |  | Trail, Var, deref |
| 220 | **infra** | `test_consecutive_separators` |  | Trail, Var, deref |
| 226 | **infra** | `test_join_mode` |  | Trail, Var, deref |
| 250 | **infra** | `test_basic` |  | Trail, Var, deref |
| 254 | **infra** | `test_none_match` |  | Trail, Var, deref |
| 258 | **infra** | `test_all_match` |  | Trail, Var, deref |
| 264 | **infra** | `test_basic` |  | Trail, Var, deref |
| 268 | **infra** | `test_none_match` |  | Trail, Var, deref |
| 272 | **infra** | `test_all_match` |  | Trail, Var, deref |
| 278 | **infra** | `test_basic` |  | Trail, Var, deref |
| 286 | **infra** | `test_consecutive_equal` |  | Trail, Var, deref, unify |
| 292 | **infra** | `test_by_computed_key` |  | Trail, Var, deref, unify |
| 302 | **infra** | `test_sort_by_key` |  | Trail, Var, deref, unify |
| 306 | **infra** | `test_already_sorted` |  | Trail, Var, deref, unify |
| 310 | **infra** | `test_empty` |  | Trail, Var, deref, unify |
| 316 | **infra** | `test_basic` |  | Trail, Var, deref, unify |
| 321 | **infra** | `test_single_element` |  | Trail, Var, deref, unify |
| 325 | **infra** | `test_tie_breaking` |  | Trail, Var, deref, unify |
| 332 | **infra** | `test_basic` |  | Trail, Var, deref, unify |
| 337 | **infra** | `test_single_element` |  | Trail, Var, deref, unify |
| 343 | **infra** | `test_basic` |  | Trail, Var, deref, unify |
| 349 | **infra** | `test_all_pass` |  | Trail, Var, deref, unify |
| 355 | **infra** | `test_none_pass` |  | Trail, Var, deref |
| 440 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_logging_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 73 | **infra** | `test_get_logger_default` |  | Trail, Var, deref |
| 79 | **infra** | `test_get_logger_named` |  | Trail, Var, deref |
| 85 | **infra** | `test_get_logger_same_name_same_object` |  | Trail, Var, deref |
| 91 | **infra** | `test_get_logger_different_names` |  | Trail, Var, deref |
| 99 | **infra** | `test_set_debug` |  | Trail, Var, deref |
| 107 | **infra** | `test_set_warning` |  | Trail, Var, deref |
| 115 | **infra** | `test_set_error` |  | Trail, Var, deref |
| 122 | **infra** | `test_set_critical` |  | Trail, Var, deref |
| 129 | **infra** | `test_set_info` |  | Trail, Var, deref |
| 136 | **infra** | `test_fatal_alias` |  | Trail, Var, deref |
| 143 | **infra** | `test_warn_alias` |  | Trail, Var, deref |
| 152 | **infra** | `test_enabled` |  | Trail |
| 158 | **infra** | `test_disabled` |  | Trail |
| 164 | **infra** | `test_same_level` |  | Trail |
| 174 | **infra** | `test_debug_output` |  | Trail |
| 180 | **infra** | `test_info_output` |  | Trail |
| 186 | **infra** | `test_warning_output` |  | Trail |
| 192 | **infra** | `test_error_output` |  | Trail |
| 198 | **infra** | `test_critical_output` |  | Trail |
| 204 | **infra** | `test_log3_output` |  | Trail |
| 214 | **infra** | `test_debug_suppressed_at_warning` |  | Trail |
| 221 | **infra** | `test_error_passes_at_warning` |  | Trail |
| 228 | **infra** | `test_info_suppressed_at_error` |  | Trail |
| 239 | **infra** | `test_two_handlers` |  | Trail |
| 261 | **infra** | `test_stream_handler_stdout` |  | Trail, Var, deref |
| 266 | **infra** | `test_stream_handler_stderr` |  | Trail, Var, deref |
| 271 | **infra** | `test_set_formatter` |  | Trail |
| 281 | **infra** | `test_file_handler_creates_file` |  | Trail, Var, deref |
| 288 | **infra** | `test_file_handler_writes` |  | Trail |
| 309 | **infra** | `test_add_and_remove` |  | Trail |
| 325 | **infra** | `test_basic_config_level` |  | Trail |
| 336 | **infra** | `test_debug_1` |  | Trail |
| 340 | **infra** | `test_info_1` |  | Trail |
| 344 | **infra** | `test_warning_1` |  | Trail |
| 348 | **infra** | `test_error_1` |  | Trail |
| 352 | **infra** | `test_critical_1` |  | Trail |
| 360 | **infra** | `test_custom_format` |  | Trail |
| 370 | **infra** | `test_name_in_format` |  | Trail |
| 383 | **infra** | `test_bound_var_in_message` |  | Trail, Var, unify |
| 460 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_module_imports.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 42 | **unknown** | `test_base_module_has_predicates` |  |  |
| 49 | **behavior** | `test_base_double_ground` | call |  |
| 57 | **behavior** | `test_base_helper_calls_double` | call |  |
| 65 | **mixed** | `test_base_double_with_var` | call | Var, deref |
| 81 | **unknown** | `test_imported_predicates_in_namespace` |  |  |
| 90 | **behavior**† | `test_use_helper_ground` | call |  |
| 98 | **behavior** | `test_use_double_ground` | call |  |
| 106 | **behavior** | `test_use_helper_failure` | call |  |
| 114 | **mixed** | `test_use_helper_with_var` | call | Var, deref |
| 123 | **behavior** | `test_imported_predicate_directly_callable` | call |  |
| 132 | **mixed** | `test_multiple_solutions` | call | Var |
| 152 | **unknown** | `test_alias_in_namespace` |  |  |
| 159 | **behavior** | `test_use_alias_ground` | call |  |
| 167 | **mixed** | `test_use_alias_with_var` | call | Var, deref |
| 188 | **infra** | `test_inject_dotted_call_target` |  | LoadAttr, LoadName, Var |
| 222 | **infra** | `test_dotted_name_dispatch` |  | _get_dispatch |
| 240 | **behavior** | `test_import_module_fixture_loads` | call |  |
| 250 | **mixed** | `test_import_module_fixture_with_var` | call | Var, deref |
| 266 | **behavior** | `test_python_import_existing_fixture` | call |  |
| 280 | **unknown** | `test_unknown_module_raises_import_error` |  |  |
| 292 | **unknown** | `test_unknown_predicate_raises_import_error` |  |  |
| 306 | **unknown** | `test_bad_directive_syntax_non_dotted` |  |  |
| 318 | **unknown** | `test_bad_directive_missing_list` |  |  |
| 337 | **unknown** | `test_dotted_name_simple` |  |  |
| 344 | **unknown** | `test_dotted_name_two_parts` |  |  |
| 354 | **unknown** | `test_dotted_name_three_parts` |  |  |
| 367 | **unknown** | `test_dotted_name_invalid` |  |  |
| 381 | **infra** | `test_loadname` |  | LoadName |
| 386 | **infra** | `test_loadattr_simple` |  | LoadAttr, LoadName |
| 391 | **infra** | `test_loadattr_nested` |  | LoadAttr, LoadName |
| 406 | **unknown** | `test_logic_var_in_attr_raises_syntax_error` |  |  |
| 422 | **unknown** | `test_logic_var_as_attr_name_raises_syntax_error` |  |  |
| 445 | **behavior**† | `test_import_from_uses_dotted_key` | call |  |
| 456 | **behavior** | `test_alias_import_uses_dotted_key` | call |  |
| 465 | **behavior** | `test_local_name_does_not_shadow_import` | call |  |

</details>

<details><summary><code>tests/test_mutable_dict_set.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 15 | **infra** | `test_record_called_on_undo` |  | Trail |
| 24 | **infra** | `test_record_not_called_if_not_undone` |  | Trail |
| 31 | **infra** | `test_multiple_callbacks_reversed` |  | Trail |
| 43 | **infra** | `test_callback_exception_cleared` |  | Trail |
| 58 | **infra** | `test_non_callable_raises` |  | Trail |
| 64 | **infra** | `test_callbacks_mixed_with_var_bindings` |  | Trail, Var, deref, unify |
| 77 | **infra** | `test_partial_undo_respects_mark` |  | Trail |
| 90 | **infra** | `test_reset_fires_all_callbacks` |  | Trail |
| 99 | **infra** | `test_plain_dict_with_trail_record` |  | Trail |
| 123 | **infra** | `test_plain_set_with_trail_record` |  | Trail |

</details>

<details><summary><code>tests/test_os_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 48 | **infra** | `test_get_home` |  | Trail, Var, deref |
| 55 | **infra** | `test_get_path` |  | Trail, Var, deref |
| 62 | **infra** | `test_missing_var_fails` |  | Trail, Var |
| 70 | **infra** | `test_enumerate_all` |  | Trail, Var |
| 80 | **infra** | `test_unify_value_check` |  | Trail |
| 89 | **infra** | `test_unify_value_wrong_fails` |  | Trail |
| 97 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 109 | **infra** | `test_set_and_get` |  | Trail |
| 119 | **infra** | `test_unbound_name_fails` |  | Trail, Var |
| 124 | **infra** | `test_unbound_value_fails` |  | Trail, Var |
| 129 | **infra** | `test_non_string_name_fails` |  | Trail |
| 139 | **infra** | `test_set_then_unset` |  | Trail |
| 147 | **infra** | `test_nonexistent_fails` |  | Trail |
| 154 | **infra** | `test_unbound_fails` |  | Trail, Var |
| 164 | **infra** | `test_returns_string` |  | Trail, Var, deref |
| 173 | **infra** | `test_matches_os_getcwd` |  | Trail, Var, deref |
| 179 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 191 | **infra** | `test_change_and_verify` |  | Trail |
| 201 | **infra** | `test_nonexistent_fails` |  | Trail |
| 206 | **infra** | `test_unbound_fails` |  | Trail, Var |
| 216 | **infra** | `test_returns_int` |  | Trail, Var, deref |
| 225 | **infra** | `test_matches_os_getpid` |  | Trail, Var, deref |
| 231 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 243 | **infra** | `test_returns_list` |  | Trail, Var, deref |
| 251 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 263 | **infra** | `test_returns_known_platform` |  | Trail, Var, deref |
| 271 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 283 | **infra** | `test_returns_positive_int` |  | Trail, Var, deref |
| 292 | **infra** | `test_matches_os_cpu_count` |  | Trail, Var, deref |
| 298 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |

</details>

<details><summary><code>tests/test_process_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 46 | **infra** | `test_true_succeeds` |  | Trail |
| 51 | **infra** | `test_false_fails` |  | Trail |
| 56 | **infra** | `test_unbound_fails` |  | Trail, Var |
| 61 | **infra** | `test_non_string_fails` |  | Trail |
| 66 | **infra** | `test_trampoline_multi_arity` |  | Trail, _get_dispatch |
| 77 | **infra** | `test_true_exit_zero` |  | Trail, Var, deref |
| 84 | **infra** | `test_false_exit_one` |  | Trail, Var, deref |
| 91 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 103 | **infra** | `test_captures_stdout` |  | Trail, Var, deref |
| 110 | **infra** | `test_nonzero_exit_fails` |  | Trail, Var |
| 115 | **infra** | `test_unbound_fails` |  | Trail, Var |
| 120 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 132 | **infra** | `test_captures_stdout_and_stderr` |  | Trail, Var, deref |
| 142 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 157 | **infra** | `test_runs_program` |  | DictTerm, Trail, Var, deref |
| 169 | **infra** | `test_nonexistent_program_fails` |  | Trail, Var |
| 176 | **infra** | `test_unbound_program_fails` |  | Trail, Var |
| 181 | **infra** | `test_unbound_args_fails` |  | Trail, Var |
| 186 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 201 | **infra** | `test_with_cwd` |  | DictTerm, Trail, Var, deref |
| 212 | **infra** | `test_with_timeout` |  | DictTerm, Trail, Var |
| 222 | **infra** | `test_with_input` |  | DictTerm, Trail, Var, deref |
| 233 | **infra** | `test_trampoline` |  | DictTerm, Trail, Var, _get_dispatch, deref |
| 249 | **infra** | `test_sleeps` |  | Trail |
| 257 | **infra** | `test_unbound_fails` |  | Trail, Var |
| 262 | **infra** | `test_non_numeric_fails` |  | Trail |
| 267 | **infra** | `test_trampoline` |  | Trail, _get_dispatch |

</details>

<details><summary><code>tests/test_python_fallbacks.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 39 | **infra** | `test_predicate_instance` |  | is_term_instance |
| 44 | **infra** | `test_class_not_instance` |  | is_term_instance |
| 48 | **infra** | `test_int_not_instance` |  | is_term_instance |
| 52 | **infra** | `test_compound_is_dataclass` |  | Compound, is_term_instance |
| 57 | **infra** | `test_var_not_instance` |  | Var, is_term_instance |
| 64 | **unknown** | `test_zero_arity` |  |  |
| 68 | **unknown** | `test_non_zero_arity` |  |  |
| 72 | **unknown** | `test_not_predicate_meta` |  |  |
| 79 | **infra** | `test_predicate_instance` |  | term_field_names |
| 84 | **infra** | `test_compound_dataclass` |  | Compound, term_field_names |
| 91 | **unknown** | `test_non_term_raises` |  |  |
| 109 | **infra** | `test_compound` |  | Compound |
| 114 | **infra** | `test_kwterm` |  | KWTerm |
| 119 | **unknown** | `test_predicate_instance` |  |  |
| 124 | **unknown** | `test_list_empty` |  |  |
| 128 | **unknown** | `test_list_nonempty` |  |  |
| 132 | **unknown** | `test_int` |  |  |
| 136 | **unknown** | `test_string` |  |  |
| 143 | **infra** | `test_compound` |  | Compound |
| 148 | **unknown** | `test_predicate_instance` |  |  |
| 153 | **unknown** | `test_int` |  |  |
| 157 | **unknown** | `test_atom` |  |  |
| 164 | **infra** | `test_compound_first` |  | Compound |
| 169 | **infra** | `test_compound_second` |  | Compound |
| 174 | **infra** | `test_out_of_range` |  | Compound |
| 185 | **infra** | `test_compound` |  | Compound |
| 190 | **unknown** | `test_predicate_instance` |  |  |
| 195 | **unknown** | `test_non_compound` |  |  |
| 202 | **infra** | `test_compound` |  | Compound |
| 207 | **infra** | `test_kwterm` |  | KWTerm |
| 212 | **unknown** | `test_int` |  |  |
| 219 | **unknown** | `test_ground_int` |  |  |
| 223 | **unknown** | `test_ground_list` |  |  |
| 227 | **infra** | `test_unbound_var` |  | Var |
| 232 | **infra** | `test_list_with_var` |  | Var |
| 237 | **infra** | `test_compound_with_var` |  | Compound, Var |
| 243 | **infra** | `test_compound_ground` |  | Compound |
| 248 | **infra** | `test_kwterm_with_var` |  | KWTerm, Var |
| 254 | **infra** | `test_kwterm_ground` |  | KWTerm |
| 259 | **infra** | `test_predicate_instance_with_var` |  | Var |
| 265 | **unknown** | `test_predicate_instance_ground` |  |  |
| 270 | **infra** | `test_bound_var_ground` |  | Trail, Var, unify |
| 277 | **unknown** | `test_atom_ground` |  |  |
| 292 | **unknown** | `test_ground_unchanged` |  |  |
| 296 | **unknown** | `test_list_copied` |  |  |
| 302 | **infra** | `test_var_freshened` |  | Var |
| 310 | **infra** | `test_compound_copied` |  | Compound, Var |
| 319 | **infra** | `test_kwterm_functor_preserved` |  | KWTerm |
| 328 | **infra** | `test_kwterm_var_freshened` |  | KWTerm, Var, _fields |
| 336 | **infra** | `test_sharing_preserved` |  | Var |
| 346 | **unknown** | `test_ground_no_vars` |  |  |
| 354 | **infra** | `test_single_var` |  | Var |
| 363 | **infra** | `test_dedup` |  | Var |
| 372 | **infra** | `test_compound_vars` |  | Compound, Var |

</details>

<details><summary><code>tests/test_python_interop.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 39 | **mixed** | `test_len` | call | Var, deref |
| 49 | **mixed** | `test_upper` | call | Var, deref |
| 59 | **mixed** | `test_arithmetic` | call | Var, deref |
| 69 | **mixed** | `test_multi_var` | call | Var, deref |
| 79 | **mixed** | `test_no_vars` | call | Var, deref |
| 90 | **mixed** | `test_subscript` | call | Var, deref |
| 100 | **mixed** | `test_dict_access` | call | Var, deref |
| 110 | **mixed** | `test_string_format` | call | Var, deref |
| 124 | **behavior** | `test_print_side_effect` | call |  |
| 141 | **mixed** | `test_goal_with_continuation` | call | Var, deref |
| 167 | **mixed** | `test_thunk_per_choice_point` | call | Var, deref |
| 182 | **mixed** | `test_thunk_no_vars` | call | Var, deref |
| 192 | **mixed** | `test_thunk_list_comprehension` | call | Var, deref |

</details>

<details><summary><code>tests/test_python_repl.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 37 | **unknown** | `test_base_namespace_has_var` |  |  |
| 42 | **unknown** | `test_base_namespace_has_solutions` |  |  |
| 47 | **unknown** | `test_base_namespace_has_set_style` |  |  |
| 52 | **unknown** | `test_base_namespace_has_compound` |  |  |
| 60 | **unknown** | `test_incomplete_returns_true` |  |  |
| 66 | **unknown** | `test_complete_returns_false` |  |  |
| 72 | **unknown** | `test_syntax_error_returns_false` |  |  |
| 88 | **unknown** | `test_var_in_scope` |  |  |
| 93 | **unknown** | `test_solutions_in_scope` |  |  |
| 98 | **unknown** | `test_trail_in_scope` |  |  |
| 106 | **unknown** | `test_normal_assignment_executes` |  |  |
| 113 | **unknown** | `test_normal_expression_executes` |  |  |
| 121 | **infra** | `test_embed_double_minus_produces_term` |  | LoadName |
| 142 | **unknown** | `test_star_query_no_solutions` |  |  |
| 156 | **unknown** | `test_star_query_single_solution` |  |  |
| 170 | **unknown** | `test_star_query_conjunction` |  |  |
| 187 | **unknown** | `test_star_query_import_then_use` |  |  |
| 206 | **unknown** | `test_enable_injects_var` |  |  |
| 213 | **unknown** | `test_enable_injects_solutions` |  |  |
| 220 | **unknown** | `test_enable_injects_set_style` |  |  |
| 227 | **unknown** | `test_enable_installs_displayhook` |  |  |
| 278 | **unknown** | `test_configure_installs_compile_hook` |  |  |
| 284 | **unknown** | `test_configure_injects_var` |  |  |
| 290 | **unknown** | `test_configure_injects_solutions` |  |  |
| 296 | **unknown** | `test_configure_enables_fuzzy_completion` |  |  |
| 302 | **unknown** | `test_configure_enables_signature` |  |  |
| 308 | **unknown** | `test_compile_hook_normal_python` |  |  |
| 318 | **unknown** | `test_compile_hook_star_query_transforms` |  |  |
| 337 | **infra** | `test_compile_hook_embed_syntax` |  | LoadName |
| 349 | **unknown** | `test_compile_hook_syntax_error_propagates` |  |  |

</details>

<details><summary><code>tests/test_random_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 45 | **infra** | `test_binds_float` |  | Trail, Var, deref |
| 54 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 68 | **infra** | `test_in_range` |  | Trail, Var, deref |
| 76 | **infra** | `test_low_equals_high_fails` |  | Trail, Var |
| 82 | **infra** | `test_low_greater_than_high_fails` |  | Trail, Var |
| 88 | **infra** | `test_unbound_low_fails` |  | Trail, Var |
| 93 | **infra** | `test_unbound_high_fails` |  | Trail, Var |
| 103 | **infra** | `test_in_range` |  | Trail, Var, deref |
| 112 | **infra** | `test_boundaries_inclusive` |  | Trail, Var, deref |
| 125 | **infra** | `test_low_greater_than_high_fails` |  | Trail, Var |
| 130 | **infra** | `test_unbound_args_fail` |  | Trail, Var |
| 140 | **infra** | `test_picks_element` |  | Trail, Var, deref |
| 148 | **infra** | `test_empty_list_fails` |  | Trail, Var |
| 153 | **infra** | `test_unbound_list_fails` |  | Trail, Var |
| 158 | **infra** | `test_trampoline` |  | Trail, Var, _get_dispatch, deref |
| 170 | **infra** | `test_is_permutation` |  | Trail, Var, deref |
| 179 | **infra** | `test_empty_list` |  | Trail, Var, deref |
| 186 | **infra** | `test_unbound_list_fails` |  | Trail, Var |
| 196 | **infra** | `test_correct_length` |  | Trail, Var, deref |
| 205 | **infra** | `test_k_zero` |  | Trail, Var, deref |
| 212 | **infra** | `test_k_greater_than_length_fails` |  | Trail, Var |
| 217 | **infra** | `test_unbound_k_fails` |  | Trail, Var |
| 227 | **infra** | `test_reproducible` |  | Trail, Var, deref |
| 244 | **infra** | `test_via_predicate` |  | Trail, Var, deref |
| 260 | **infra** | `test_unbound_seed_fails` |  | Trail, Var |
| 270 | **infra** | `test_maybe_0_roughly_half` |  | Trail |
| 284 | **infra** | `test_maybe_1_always_succeeds` |  | Trail |
| 291 | **infra** | `test_maybe_1_always_fails` |  | Trail |
| 298 | **infra** | `test_maybe_1_unbound_fails` |  | Trail, Var |
| 303 | **infra** | `test_maybe_trampoline_multi_arity` |  | Trail, _get_dispatch |

</details>

<details><summary><code>tests/test_regex.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 111 | **behavior** | `test_digits_match` | call |  |
| 118 | **behavior** | `test_digits_no_match` | call |  |
| 125 | **behavior** | `test_anchored_at_start` | call |  |
| 134 | **behavior** | `test_fullmatch_via_dollar` | call |  |
| 142 | **behavior** | `test_email_validation` | call |  |
| 161 | **mixed** | `test_named_groups` | call | Var, deref |
| 175 | **mixed** | `test_positional_groups` | call | Var, deref |
| 189 | **mixed** | `test_no_match_fails` | call | Var, deref |
| 196 | **mixed** | `test_mixed_named_positional` | call | Var, deref |
| 227 | **mixed** | `test_basic_auto_bind` | call | Var, deref |
| 237 | **mixed** | `test_auto_bind_no_match_fails` | call | Var |
| 246 | **mixed** | `test_auto_bind_constrains_input` | call | Var, deref |
| 259 | **mixed** | `test_auto_bind_search` | call | Var, deref |
| 267 | **mixed** | `test_auto_bind_single_group` | call | Var, deref |
| 274 | **mixed** | `test_auto_bind_many_groups` | call | Var, deref |
| 285 | **mixed** | `test_leading_underscore_group` | call | Var, deref |
| 301 | **mixed** | `test_selective_binding` | call | Var, deref |
| 311 | **behavior** | `test_lowercase_groups_still_work_in_regex` | call |  |
| 321 | **mixed** | `test_explicit_extraction_of_lowercase_group` | call | Var, deref |
| 343 | **mixed** | `test_search_finds_in_middle` | call | Var, deref |
| 350 | **mixed** | `test_search_with_explicit_groups` | call | Var, deref |
| 369 | **mixed** | `test_findall_strings` | call | Var, deref |
| 377 | **mixed** | `test_findall_no_matches` | call | Var, deref |
| 384 | **mixed** | `test_findall_with_groups` | call | Var, deref |
| 393 | **mixed** | `test_findall_backtracking` | call | Var, deref |
| 417 | **mixed** | `test_simple_replace` | call | Var, deref |
| 424 | **mixed** | `test_replace_remove` | call | Var, deref |
| 431 | **mixed** | `test_replace_backreference` | call | Var, deref |
| 439 | **mixed** | `test_replace_chain` | call | Var, deref |
| 453 | **mixed** | `test_split_comma` | call | Var, deref |
| 460 | **mixed** | `test_split_whitespace` | call | Var, deref |
| 476 | **behavior** | `test_dynamic_match` | call |  |
| 484 | **mixed** | `test_dynamic_with_explicit_groups` | call | Var, deref |
| 494 | **behavior** | `test_dynamic_pattern_variable` | call |  |
| 512 | **behavior** | `test_static_precompiled` | call |  |
| 520 | **behavior** | `test_multiple_patterns_in_module` | call |  |
| 531 | **mixed** | `test_same_pattern_deduplicated` | call | Var, deref |
| 548 | **mixed** | `test_log_parser_compact` | call | Var, deref |
| 558 | **mixed** | `test_tokenizer` | call | Var, deref |
| 566 | **mixed** | `test_backtracking_regex` | call | Var, deref |
| 581 | **mixed** | `test_url_parser` | call | Var, deref |
| 592 | **mixed** | `test_csv_parse_and_validate` | call | Var, deref |
| 613 | **mixed** | `test_typo_in_group_name` | call | Var, deref |
| 625 | **mixed** | `test_optional_group_binds_none` | call | Var, deref |
| 640 | **mixed** | `test_lowercase_groups_not_auto_bound` | call | Var, deref |
| 651 | **behavior** | `test_no_named_groups_boolean_only` | call |  |
| 663 | **behavior** | `test_empty_string` | call |  |
| 671 | **behavior** | `test_unicode` | call |  |
| 678 | **behavior** | `test_special_chars` | call |  |
| 686 | **mixed** | `test_findall_nonoverlapping` | call | Var, deref |
| 693 | **behavior** | `test_search_vs_match` | call |  |
| 753 | **behavior**† | `test_fixture` | call |  |
| 784 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_seglist_core.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 12 | **unknown** | `test_zero_stars_zero_remainder` |  |  |
| 16 | **unknown** | `test_zero_stars_nonzero_fails` |  |  |
| 20 | **unknown** | `test_one_star` |  |  |
| 24 | **unknown** | `test_two_stars_remainder_2` |  |  |
| 29 | **unknown** | `test_three_stars_remainder_1` |  |  |
| 34 | **unknown** | `test_total_count` |  |  |
| 43 | **unknown** | `test_empty_seglist` |  |  |
| 48 | **unknown** | `test_single_concrete` |  |  |
| 53 | **infra** | `test_single_var` |  | Var |
| 59 | **infra** | `test_mixed_segments` |  | Var |
| 65 | **unknown** | `test_segments_property_returns_copy_list` |  |  |
| 77 | **unknown** | `test_fully_ground_returns_plain_list` |  |  |
| 84 | **infra** | `test_unbound_var_stays_seglist` |  | Var |
| 91 | **infra** | `test_bound_var_inlined` |  | Trail, Var, unify |
| 100 | **unknown** | `test_adjacent_concrete_segs_merged` |  |  |
| 106 | **infra** | `test_empty_var_bound_to_empty_list_inlined` |  | Trail, Var, unify |
| 115 | **infra** | `test_nested_seglist_inlined_when_ground` |  | Trail, Var, unify |
| 127 | **infra** | `test_nested_seglist_partially_unbound_inlined_structurally` |  | Trail, Var, unify |
| 143 | **unknown** | `test_empty_seglist_returns_empty_list` |  |  |
| 149 | **infra** | `test_all_vars_bound_multi_star` |  | Trail, Var, unify |
| 163 | **unknown** | `test_ground_concrete_only` |  |  |
| 168 | **infra** | `test_not_ground_with_unbound_var` |  | Var |
| 173 | **infra** | `test_ground_after_binding` |  | Trail, Var, unify |
| 182 | **unknown** | `test_to_list_ground` |  |  |
| 187 | **infra** | `test_to_list_raises_if_not_ground` |  | Var |
| 193 | **infra** | `test_to_list_after_binding` |  | Trail, Var, unify |
| 205 | **infra** | `test_var_in_varseg` |  | Var |
| 211 | **infra** | `test_var_not_present` |  | Var |
| 217 | **infra** | `test_var_in_concrete_elem` |  | Var |
| 223 | **infra** | `test_var_absent_all_concrete` |  | Var |
| 233 | **infra** | `test_unify_against_matching_list_single_star` |  | Trail, Var |
| 242 | **infra** | `test_unify_against_too_short_list` |  | Trail, Var |
| 250 | **infra** | `test_unify_against_non_sequence_returns_not_implemented` |  | Trail |
| 256 | **infra** | `test_unify_against_string_treats_as_char_list` |  | Trail |
| 263 | **infra** | `test_unify_against_seglist_returns_not_implemented` |  | Trail |
| 270 | **infra** | `test_unify_fully_ground_seglist_against_equal_list` |  | Trail |
| 276 | **infra** | `test_unify_fully_ground_seglist_against_unequal_list` |  | Trail |
| 286 | **infra** | `test_single_var_tail` |  | Trail, Var |
| 297 | **infra** | `test_two_vars_all_splits` |  | Trail, Var |
| 313 | **infra** | `test_sandwich_pattern` |  | Trail, Var |
| 329 | **infra** | `test_too_short_yields_nothing` |  | Trail, Var |
| 336 | **infra** | `test_empty_var_match` |  | Trail, Var |
| 354 | **unknown** | `test_len_ground` |  |  |
| 358 | **infra** | `test_len_unground_raises` |  | Var |
| 364 | **unknown** | `test_iter_ground` |  |  |
| 368 | **infra** | `test_iter_unground_raises` |  | Var |
| 374 | **unknown** | `test_contains_ground` |  |  |
| 379 | **infra** | `test_contains_in_concrete_seg_unground` |  | Var |
| 385 | **infra** | `test_contains_not_found_unground` |  | Var |
| 391 | **unknown** | `test_getitem_ground` |  |  |
| 396 | **infra** | `test_getitem_unground_raises` |  | Var |
| 406 | **infra** | `test_add_plain_list` |  | Trail, Var, unify |
| 417 | **infra** | `test_add_seglist` |  | Trail, Var, unify |
| 429 | **infra** | `test_radd_plain_list` |  | Trail, Var, unify |
| 439 | **unknown** | `test_add_non_list_returns_not_implemented` |  |  |
| 448 | **infra** | `test_seglist_eq_seglist_structural` |  | Var |
| 455 | **unknown** | `test_seglist_eq_list_when_ground` |  |  |
| 460 | **infra** | `test_seglist_neq_list_when_unground` |  | Var |
| 465 | **unknown** | `test_seglist_neq_non_list` |  |  |
| 470 | **unknown** | `test_not_hashable` |  |  |
| 480 | **unknown** | `test_concrete_only` |  |  |
| 485 | **infra** | `test_single_var` |  | Var |
| 493 | **infra** | `test_mixed` |  | Var |
| 501 | **unknown** | `test_empty` |  |  |

</details>

<details><summary><code>tests/test_seglist_creation.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 50 | **infra** | `test_star_only` |  | Trail, Var, deref |
| 63 | **infra** | `test_before_and_unbound_star` |  | Trail, Var, deref, unify |
| 78 | **infra** | `test_before_unbound_star_after` |  | Trail, Var, deref, unify |
| 97 | **infra** | `test_seglist_later_unified` |  | Trail, Var, unify |
| 111 | **infra** | `test_target_already_bound_uses_input_mode` |  | Trail, Var, deref, unify |
| 131 | **infra** | `test_unbound_target_unbound_star` |  | Trail, Var, deref, unify |
| 144 | **infra** | `test_unbound_target_bound_star` |  | Trail, Var, deref, unify |
| 157 | **infra** | `test_then_unify_against_ground` |  | Trail, Var, deref, unify |
| 180 | **infra** | `test_two_stars_unbound_target` |  | Trail, Var, deref |
| 197 | **infra** | `test_star_fixed_star_unbound_target` |  | Trail, Var, deref, unify |
| 217 | **infra** | `test_seglist_then_unified_against_ground` |  | Trail, Var, deref |
| 249 | **infra** | `test_star_only_unbound` |  | Var |
| 259 | **infra** | `test_before_and_unbound_star` |  | Var |
| 268 | **infra** | `test_before_unbound_star_after` |  | Var |
| 279 | **unknown** | `test_bound_star_returns_plain_list` |  |  |
| 285 | **infra** | `test_seglist_becomes_ground_on_bind` |  | Trail, Var, unify |
| 303 | **infra** | `test_two_unbound_stars` |  | Var |
| 314 | **infra** | `test_fixed_star_unbound` |  | Var |
| 323 | **infra** | `test_star_fixed_star_unbound` |  | Var |
| 334 | **infra** | `test_all_bound_returns_plain_list` |  | Trail, Var, unify |
| 344 | **infra** | `test_fixed_and_bound_star` |  | Trail, Var, unify |
| 364 | **mixed** | `test_append_unbound_rhs` | call | Var, deref |
| 374 | **mixed** | `test_append_unbound_rhs_then_unified` | call | Var, deref, unify |
| 389 | **mixed** | `test_last_forward_still_works` | call | Var, deref |
| 399 | **mixed** | `test_split_unbound_list` | call | Var, deref |
| 408 | **mixed** | `test_split_unbound_list_then_ground` | call | Var, deref |

</details>

<details><summary><code>tests/test_seglist_passthrough.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 42 | **mixed** | `test_append_first_arg_ground_seglist` | call | Trail, Var, deref, unify |
| 55 | **mixed** | `test_append_third_arg_ground_seglist` | call | Trail, Var, deref, unify |
| 72 | **mixed** | `test_last_ground_seglist` | call | Trail, Var, deref, unify |
| 103 | **mixed** | `test_split_ground_seglist` | call | Var, deref |
| 116 | **mixed** | `test_split3_ground_seglist` | call | Var, deref |
| 129 | **mixed** | `test_around_ground_seglist` | call | Var, deref |
| 142 | **mixed** | `test_split_concrete_seglist` | call | Var, deref |
| 156 | **mixed** | `test_non_ground_seglist_produces_no_solutions` | call | Var |
| 175 | **mixed** | `test_head_tail_ground_seglist` | call | Trail, Var, deref, unify |
| 189 | **mixed** | `test_init_last_ground_seglist` | call | Trail, Var, deref, unify |
| 212 | **mixed** | `test_append_result_via_add` | call | Trail, Var, deref, unify |

</details>

<details><summary><code>tests/test_sqlite.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 131 | **infra** | `test_connect_memory` |  | Trail |
| 137 | **infra** | `test_connect_file` |  | Trail |
| 144 | **infra** | `test_connect_duplicate_alias_idempotent` |  | Trail |
| 150 | **infra** | `test_connect_multiple_aliases` |  | Trail |
| 161 | **infra** | `test_disconnect` |  | Trail |
| 168 | **infra** | `test_disconnect_nonexistent_fails` |  | Trail |
| 177 | **infra** | `test_enumerate_all` |  | Trail, Var, deref |
| 192 | **infra** | `test_check_specific` |  | Trail |
| 205 | **infra** | `test_check_missing` |  | Trail |
| 236 | **infra** | `test_query_all_rows` |  | Trail, Var, deref |
| 250 | **infra** | `test_query_single_column` |  | Trail, Var, deref |
| 265 | **infra** | `test_query_no_results` |  | Trail, Var, deref |
| 279 | **infra** | `test_query_parameterized` |  | Trail, Var, deref |
| 296 | **infra** | `test_query_multiple_params` |  | Trail, Var, deref |
| 313 | **infra** | `test_query_types_preserved` |  | Trail, Var, deref |
| 332 | **infra** | `test_query_join` |  | Trail, Var, deref |
| 355 | **infra** | `test_query_aggregate` |  | Trail, Var, deref |
| 369 | **infra** | `test_query_bad_alias_raises` |  | Trail, Var |
| 381 | **infra** | `test_exec_create_table` |  | Trail |
| 387 | **infra** | `test_exec_insert` |  | Trail |
| 399 | **infra** | `test_exec_parameterized_insert` |  | Trail |
| 411 | **infra** | `test_exec_update` |  | Trail |
| 420 | **infra** | `test_exec_delete` |  | Trail |
| 434 | **infra** | `test_row_count_insert` |  | Trail, Var, deref |
| 448 | **infra** | `test_row_count_update` |  | Trail, Var, deref |
| 459 | **infra** | `test_row_count_delete` |  | Trail, Var, deref |
| 479 | **infra** | `test_table_enumerate` |  | Trail, Var, deref |
| 496 | **infra** | `test_table_specific_exists` |  | Trail |
| 509 | **infra** | `test_table_specific_not_exists` |  | Trail |
| 526 | **infra** | `test_column_enumerate` |  | Trail, Var, deref |
| 543 | **infra** | `test_column_specific_name` |  | Trail, Var, deref |
| 569 | **mixed** | `test_connect_exec_query` | call | Var, deref |
| 579 | **mixed** | `test_parameterized_query` | call | Var, deref |
| 589 | **mixed** | `test_table_introspection` | call | Var, deref |
| 599 | **mixed** | `test_column_introspection` | call | Var, deref |
| 615 | **behavior** | `test_disconnect` | call |  |
| 623 | **mixed** | `test_exec_with_params` | call | Var, deref |

</details>

<details><summary><code>tests/test_string_list_builtins.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 46 | **mixed** | `test_enumerate_chars` | call | Var, deref |
| 51 | **behavior** | `test_member_check` | call |  |
| 55 | **behavior** | `test_member_miss` | call |  |
| 59 | **mixed** | `test_empty_string` | call | Var, deref |
| 64 | **mixed** | `test_list_still_works` | call | Var, deref |
| 71 | **behavior** | `test_memberchk_hit` | call |  |
| 75 | **behavior** | `test_memberchk_miss` | call |  |
| 84 | **mixed** | `test_concat_two_strings` | call | Var, deref |
| 90 | **mixed** | `test_prefix_match` | call | Var, deref |
| 96 | **mixed** | `test_suffix_match` | call | Var, deref |
| 102 | **mixed** | `test_enumerate_splits` | call | Var, deref |
| 115 | **mixed** | `test_concat_string_with_list` | call | Var, deref |
| 122 | **mixed** | `test_empty_strings` | call | Var, deref |
| 128 | **mixed** | `test_list_still_works` | call | Var, deref |
| 139 | **mixed** | `test_length` | call | Var, deref |
| 144 | **mixed** | `test_empty` | call | Var, deref |
| 154 | **mixed** | `test_reverse` | call | Var, deref |
| 159 | **mixed** | `test_reverse_empty` | call | Var, deref |
| 164 | **mixed** | `test_reverse_single` | call | Var, deref |
| 174 | **mixed** | `test_last_char` | call | Var, deref |
| 179 | **mixed** | `test_empty_fails` | call | Var, deref |
| 189 | **mixed** | `test_index` | call | Var, deref |
| 194 | **mixed** | `test_enumerate` | call | Var, deref |
| 207 | **mixed** | `test_take` | call | Var, deref |
| 212 | **mixed** | `test_drop` | call | Var, deref |
| 217 | **mixed** | `test_split_at` | call | Var, deref |
| 224 | **mixed** | `test_take_zero` | call | Var, deref |
| 229 | **mixed** | `test_drop_all` | call | Var, deref |
| 239 | **mixed** | `test_msort` | call | Var, deref |
| 245 | **mixed** | `test_msort_duplicates` | call | Var, deref |
| 251 | **mixed** | `test_sort_dedup` | call | Var, deref |
| 262 | **mixed** | `test_to_set` | call | Var, deref |
| 273 | **mixed** | `test_select` | call | Var, deref |
| 290 | **mixed** | `test_subtract` | call | Var, deref |
| 296 | **mixed** | `test_intersection` | call | Var, deref |
| 302 | **mixed** | `test_union` | call | Var, deref |
| 313 | **mixed** | `test_max` | call | Var, deref |
| 319 | **mixed** | `test_min` | call | Var, deref |
| 330 | **mixed** | `test_permutations` | call | Var, deref |
| 342 | **mixed** | `test_zip_strings` | call | Var, deref |
| 348 | **mixed** | `test_zip_string_list` | call | Var, deref |
| 359 | **mixed** | `test_split_by_comma` | call | Var, deref |
| 365 | **mixed** | `test_split_no_sep` | call | Var, deref |
| 376 | **behavior** | `test_same_length` | call |  |
| 380 | **behavior** | `test_different_length` | call |  |
| 384 | **behavior** | `test_string_list_same_length` | call |  |
| 393 | **behavior** | `test_string` | call |  |
| 397 | **behavior** | `test_list` | call |  |
| 401 | **behavior** | `test_int_fails` | call |  |
| 405 | **behavior** | `test_is_list_string_still_fails` | call |  |

</details>

<details><summary><code>tests/test_string_list_unification.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 14 | **infra** | `test_basic` |  | Trail, unify |
| 18 | **infra** | `test_symmetric` |  | Trail, unify |
| 22 | **infra** | `test_empty` |  | Trail, unify |
| 26 | **infra** | `test_single_char` |  | Trail, unify |
| 30 | **infra** | `test_unicode` |  | Trail, unify |
| 34 | **infra** | `test_emoji` |  | Trail, unify |
| 42 | **infra** | `test_length_str_longer` |  | Trail, unify |
| 46 | **infra** | `test_length_list_longer` |  | Trail, unify |
| 50 | **infra** | `test_content_mismatch` |  | Trail, unify |
| 54 | **infra** | `test_str_vs_int_list` |  | Trail, unify |
| 58 | **infra** | `test_str_vs_multi_char_elements` |  | Trail, unify |
| 63 | **infra** | `test_str_vs_mixed_type_list` |  | Trail, unify |
| 67 | **infra** | `test_str_vs_none_in_list` |  | Trail, unify |
| 75 | **infra** | `test_all_vars` |  | Trail, Var, deref, unify |
| 84 | **infra** | `test_partial_vars` |  | Trail, Var, deref, unify |
| 91 | **infra** | `test_var_at_start` |  | Trail, Var, deref, unify |
| 98 | **infra** | `test_var_at_end` |  | Trail, Var, deref, unify |
| 105 | **infra** | `test_var_mismatch_other_position` |  | Trail, Var, unify |
| 112 | **infra** | `test_symmetric_var_binding` |  | Trail, Var, deref, unify |
| 120 | **infra** | `test_unicode_var_binding` |  | Trail, Var, deref, unify |
| 132 | **infra** | `test_equal` |  | Trail, unify |
| 136 | **infra** | `test_not_equal` |  | Trail, unify |
| 140 | **infra** | `test_empty_strings` |  | Trail, unify |
| 144 | **infra** | `test_unicode_equal` |  | Trail, unify |
| 148 | **infra** | `test_unicode_not_equal` |  | Trail, unify |
| 156 | **infra** | `test_undo_restores_var` |  | Trail, Var, deref, unify |
| 166 | **infra** | `test_undo_after_failed_unify` |  | Trail, Var, unify |
| 183 | **infra** | `test_nested_string` |  | Trail, unify |
| 187 | **infra** | `test_list_of_strings` |  | Trail, unify |
| 191 | **infra** | `test_deeply_nested` |  | Trail, unify |
| 198 | **infra** | `test_string_in_tuple` |  | Trail, unify |
| 203 | **infra** | `test_mixed_nesting` |  | Trail, Var, deref, unify |
| 214 | **infra** | `test_very_long_string` |  | Trail, unify |
| 220 | **infra** | `test_very_long_string_mismatch_at_end` |  | Trail, unify |
| 226 | **infra** | `test_string_vs_empty_list` |  | Trail, unify |
| 230 | **infra** | `test_empty_string_vs_nonempty_list` |  | Trail, unify |
| 234 | **infra** | `test_newline_char` |  | Trail, unify |
| 238 | **infra** | `test_null_char` |  | Trail, unify |
| 242 | **infra** | `test_surrogate_pair` |  | Trail, unify |
| 247 | **infra** | `test_string_does_not_unify_with_tuple` |  | Trail, unify |
| 252 | **infra** | `test_pre_bound_var_match` |  | Trail, Var, unify |
| 260 | **infra** | `test_pre_bound_var_mismatch` |  | Trail, Var, unify |
| 268 | **infra** | `test_same_var_repeated` |  | Trail, Var, deref, unify |
| 276 | **infra** | `test_same_var_repeated_conflict` |  | Trail, Var, unify |
| 292 | **infra** | `test_head_tail` |  | Trail, Var, deref, unify |
| 302 | **infra** | `test_prefix_suffix` |  | Trail, Var, deref, unify |
| 312 | **infra** | `test_multi_star_multiple_solutions` |  | Trail, Var, deref |
| 328 | **infra** | `test_empty_string` |  | Trail, Var, deref, unify |
| 337 | **infra** | `test_full_concrete_match` |  | Trail, unify |
| 343 | **infra** | `test_full_concrete_mismatch` |  | Trail, unify |
| 349 | **infra** | `test_concrete_length_mismatch` |  | Trail, unify |
| 355 | **infra** | `test_only_star` |  | Trail, Var, deref, unify |
| 364 | **infra** | `test_two_stars` |  | Trail, Var, deref |
| 378 | **infra** | `test_var_in_concrete_binds` |  | Trail, Var, deref |
| 393 | **infra** | `test_unicode_string` |  | Trail, Var, deref, unify |
| 403 | **infra** | `test_symmetric_string_seglist` |  | Trail, Var, deref, unify |
| 418 | **infra** | `test_split_at_comma` |  | Trail, Var, deref |
| 430 | **infra** | `test_multiple_commas` |  | Trail, Var, deref |
| 441 | **infra** | `test_no_match` |  | Trail, Var |
| 450 | **infra** | `test_empty_string` |  | Trail, Var |

</details>

<details><summary><code>tests/test_units.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 79 | **infra** | `test_zero_exponents_removed` |  | Quantity |
| 84 | **infra** | `test_empty_dims_is_dimensionless` |  | Quantity |
| 90 | **infra** | `test_repr` |  | Quantity |
| 96 | **infra** | `test_str` |  | Quantity |
| 104 | **infra** | `test_equality` |  | Quantity |
| 110 | **infra** | `test_hash_consistent_with_eq` |  | Quantity |
| 125 | **infra** | `test_add_same_dims` |  | Quantity |
| 130 | **infra** | `test_add_mismatch_raises` |  | Quantity |
| 135 | **infra** | `test_add_dimensioned_with_plain_raises` |  | Quantity |
| 140 | **infra** | `test_add_dimensionless_with_plain` |  | Quantity |
| 145 | **infra** | `test_radd_dimensionless` |  | Quantity |
| 152 | **infra** | `test_sub_same_dims` |  | Quantity |
| 157 | **infra** | `test_sub_mismatch_raises` |  | Quantity |
| 164 | **infra** | `test_mul_dimensioned_dimensioned` |  | Quantity |
| 172 | **infra** | `test_mul_dimensioned_scalar` |  | Quantity |
| 177 | **infra** | `test_rmul_scalar` |  | Quantity |
| 182 | **infra** | `test_mul_cancels_dims` |  | Quantity |
| 191 | **infra**† | `test_mul_compound_dims` |  | Quantity |
| 202 | **infra** | `test_div_dimensioned_dimensioned` |  | Quantity |
| 209 | **infra** | `test_div_by_scalar` |  | Quantity |
| 214 | **infra** | `test_rdiv_scalar` |  | Quantity |
| 220 | **infra** | `test_div_same_dims_gives_dimensionless` |  | Quantity |
| 228 | **infra** | `test_pow_integer_exponent` |  | Quantity |
| 234 | **infra** | `test_pow_cubed` |  | Quantity |
| 240 | **infra** | `test_pow_minus_one` |  | Quantity |
| 246 | **infra** | `test_pow_zero_gives_dimensionless` |  | Quantity |
| 252 | **infra** | `test_pow_non_integer_raises` |  | Quantity |
| 257 | **infra** | `test_pow_dimensioned_exponent_raises` |  | Quantity |
| 262 | **infra** | `test_pow_dimensionless_exponent_integer_value` |  | Quantity |
| 271 | **infra** | `test_neg` |  | Quantity |
| 276 | **infra** | `test_abs` |  | Quantity |
| 288 | **infra** | `test_lt_same_dims` |  | Quantity |
| 292 | **infra** | `test_gt_same_dims` |  | Quantity |
| 296 | **infra** | `test_le_equal` |  | Quantity |
| 300 | **infra** | `test_ge_equal` |  | Quantity |
| 304 | **infra** | `test_comparison_mismatch_raises` |  | Quantity |
| 309 | **infra** | `test_comparison_with_plain_on_dimensionless` |  | Quantity |
| 313 | **infra** | `test_comparison_dimensioned_with_plain_raises` |  | Quantity |
| 325 | **infra** | `test_unify_same_value_same_dims` |  | Quantity, Trail, unify |
| 330 | **infra** | `test_unify_different_value_fails` |  | Quantity, Trail, unify |
| 335 | **infra** | `test_unify_different_dims_fails` |  | Quantity, Trail, unify |
| 340 | **infra** | `test_unify_var_with_dimensioned` |  | Quantity, Trail, Var, deref, unify |
| 347 | **infra** | `test_unify_not_dimensioned_returns_not_implemented` |  | Quantity, Trail |
| 356 | **infra** | `test_attvar_unit_constraint_fires_on_bind` |  | Quantity, Trail, Var, deref, unify |
| 365 | **infra** | `test_attvar_unit_constraint_fails_wrong_dims` |  | Quantity, Trail, Var, unify |
| 373 | **infra** | `test_attvar_unit_constraint_fails_plain_number` |  | Trail, Var, unify |
| 381 | **infra** | `test_attvar_dimensionless_constraint_accepts_plain_number` |  | Trail, Var, unify |
| 389 | **infra** | `test_two_attvar_unit_constraints_merge_compatible` |  | Trail, Var, deref, unify |
| 401 | **infra** | `test_two_attvar_unit_constraints_fail_incompatible` |  | Trail, Var, unify |
| 411 | **infra** | `test_attvar_constraint_transfers_to_unconstrained_var` |  | Trail, Var, deref, unify |
| 421 | **infra** | `test_attvar_unit_constraint_backtracks` |  | Trail, Var |
| 442 | **infra** | `test_meter` |  | Quantity |
| 447 | **infra** | `test_kilogram` |  | Quantity |
| 452 | **infra** | `test_second` |  | Quantity |
| 457 | **infra** | `test_ampere` |  | Quantity |
| 462 | **infra** | `test_kelvin` |  | Quantity |
| 467 | **infra** | `test_mole` |  | Quantity |
| 472 | **infra** | `test_candela` |  | Quantity |
| 486 | **unknown** | `test_kilometer` |  |  |
| 493 | **unknown** | `test_centimeter` |  |  |
| 500 | **unknown** | `test_gram` |  |  |
| 507 | **unknown** | `test_tonne` |  |  |
| 513 | **unknown** | `test_minute` |  |  |
| 520 | **unknown** | `test_hour` |  |  |
| 526 | **unknown**† | `test_foot_unit_vector` |  |  |
| 533 | **unknown**† | `test_pound_unit_vector` |  |  |
| 550 | **unknown** | `test_newton` |  |  |
| 557 | **unknown** | `test_joule` |  |  |
| 563 | **unknown** | `test_watt` |  |  |
| 569 | **unknown** | `test_pascal` |  |  |
| 575 | **unknown** | `test_hertz` |  |  |
| 581 | **unknown** | `test_volt` |  |  |
| 587 | **unknown** | `test_coulomb` |  |  |
| 593 | **unknown** | `test_farad` |  |  |
| 599 | **unknown** | `test_ohm` |  |  |
| 605 | **unknown** | `test_bar` |  |  |
| 612 | **unknown**† | `test_kilowatt_hour_unit_vector` |  |  |
| 627 | **infra** | `test_dimension_of` |  | DictTerm, Quantity, Trail, _get_dispatch, deref |
| 638 | **infra** | `test_value_of` |  | Quantity, Trail, _get_dispatch, deref |
| 646 | **infra** | `test_strip_dimensions` |  | Quantity, Trail, _get_dispatch, deref |
| 654 | **infra** | `test_make_dimensioned` |  | DictTerm, Quantity, Trail, _get_dispatch, deref |
| 665 | **infra** | `test_dimension_of_plain_number_fails` |  | Trail, _get_dispatch, deref |
| 671 | **infra** | `test_value_of_plain_number_fails` |  | Trail, _get_dispatch, deref |
| 686 | **infra**† | `test_force_from_mass_times_acceleration` |  | Quantity |
| 695 | **infra** | `test_kinetic_energy` |  | Quantity |
| 704 | **infra** | `test_power_from_energy_over_time` |  | Quantity |
| 713 | **infra** | `test_speed_from_distance_over_time` |  | Quantity |
| 719 | **infra** | `test_ohms_law_voltage` |  | Quantity |
| 728 | **infra** | `test_area_from_side_squared` |  | Quantity |
| 734 | **unknown** | `test_chain_unit_predicates_and_arithmetic` |  |  |
| 754 | **infra** | `test_dimensionless_times_dimensioned` |  | Quantity |
| 763 | **infra** | `test_add_two_dimensionless` |  | Quantity |
| 768 | **infra** | `test_sub_two_dimensionless` |  | Quantity |
| 773 | **infra** | `test_pow_with_dimensionless_dimensioned_int_value` |  | Quantity |
| 781 | **infra** | `test_attvar_vars_merge_then_bind` |  | Quantity, Trail, Var, deref, unify |
| 795 | **infra** | `test_format_dunder` |  | Quantity |
| 801 | **infra** | `test_dimensioned_zero_value` |  | Quantity |
| 806 | **infra** | `test_negative_exponents_in_display` |  | Quantity |
| 812 | **infra** | `test_multiply_complex_dims` |  | Quantity |
| 821 | **infra** | `test_pow_half_dimensionless` |  | Quantity |
| 828 | **infra** | `test_pow_half_dimensional_raises` |  | Quantity |
| 838 | **infra** | `test_kilogram_call` |  | Quantity |
| 843 | **infra** | `test_meter_call` |  | Quantity |
| 848 | **infra** | `test_newton_call` |  | Quantity |
| 853 | **infra** | `test_kilometer_multiply` |  | Quantity |
| 858 | **unknown** | `test_expression_e_mc2` |  |  |
| 866 | **unknown** | `test_expression_weight` |  |  |
| 873 | **unknown** | `test_expression_ohms_law` |  |  |
| 889 | **unknown** | `test_pow_produces_correct_dims` |  |  |
| 895 | **unknown** | `test_div_produces_correct_dims` |  |  |
| 901 | **unknown** | `test_mul_produces_correct_dims` |  |  |
| 907 | **unknown** | `test_compound_force_dims` |  |  |
| 913 | **unknown** | `test_acceleration_dims` |  |  |
| 919 | **unknown** | `test_pow_fractional_not_useful_but_legal` |  |  |
| 926 | **unknown** | `test_descriptor_matches_quantity_dims` |  |  |
| 933 | **unknown** | `test_area_descriptor_matches_quantity_dims` |  |  |
| 940 | **unknown** | `test_compound_desc_mismatch` |  |  |
| 949 | **unknown** | `test_speed_of_light_dims` |  |  |
| 954 | **unknown** | `test_planck_constant_dims` |  |  |
| 959 | **unknown** | `test_boltzmann_constant_dims` |  |  |
| 964 | **unknown** | `test_standard_gravity_dims` |  |  |
| 969 | **unknown** | `test_elementary_charge_dims` |  |  |
| 974 | **unknown** | `test_gravitational_constant_dims` |  |  |
| 994 | **infra** | `test_has_units_ground_match` |  | Trail, _get_dispatch, deref |
| 1000 | **infra** | `test_has_units_ground_mismatch` |  | Trail, _get_dispatch, deref |
| 1006 | **infra** | `test_has_units_unbound_var_posts_constraint` |  | Trail, Var, _get_dispatch |
| 1026 | **infra** | `test_has_units_unbound_var_backtracks` |  | Trail, Var, _get_dispatch |
| 1043 | **infra** | `test_has_units_already_constrained_match` |  | Trail, Var, _get_dispatch, deref |
| 1054 | **infra** | `test_has_units_already_constrained_conflict` |  | Trail, Var, _get_dispatch, deref |
| 1067 | **behavior** | `test_numeric_sugar_basic` | call |  |
| 1082 | **behavior** | `test_numeric_sugar_float` | call |  |
| 1096 | **behavior** | `test_numeric_sugar_negation` | call |  |
| 1110 | **behavior** | `test_numeric_sugar_addition` | call |  |
| 1126 | **behavior** | `test_var_sugar_constructs_quantity` | call |  |
| 1140 | **behavior** | `test_var_sugar_compound_constructs` | call |  |
| 1154 | **behavior** | `test_has_units_check_passes` | call |  |
| 1168 | **behavior** | `test_has_units_check_fails` | call |  |
| 1182 | **behavior** | `test_has_units_posts_constraint` | call |  |
| 1196 | **behavior** | `test_has_units_constraint_rejects_wrong_unit` | call |  |
| 1225 | **behavior** | `test_add_metre_plus_second_raises` | call |  |
| 1235 | **behavior** | `test_sub_metre_minus_kilogram_raises` | call |  |
| 1245 | **behavior** | `test_compare_metre_with_second_raises` | call |  |
| 1255 | **behavior** | `test_add_dimensioned_with_plain_raises` | call |  |
| 1265 | **behavior** | `test_matching_units_no_error` | call |  |
| 1289 | **behavior** | `test_integer_dimensionless` | call |  |
| 1297 | **behavior** | `test_float_dimensionless` | call |  |
| 1305 | **behavior** | `test_dimensionless_equals_dimensionless_pred` | call |  |
| 1314 | **behavior** | `test_dimensionless_arithmetic` | call |  |
| 1322 | **behavior** | `test_dimensionless_is_dimensionless` | call |  |
| 1331 | **behavior** | `test_dimensionless_is_dimensionless_not_length` | call |  |
| 1355 | **behavior** | `test_catch_add_mismatch` | call |  |
| 1364 | **behavior** | `test_catch_sub_mismatch` | call |  |
| 1373 | **behavior** | `test_catch_message_bound` | call |  |
| 1383 | **behavior** | `test_no_exception_recovery_skipped` | call |  |
| 1393 | **behavior** | `test_unmatched_exception_reraises` | call |  |
| 1412 | **unknown** | `test_kilo_is_number` |  |  |
| 1418 | **unknown** | `test_milli_is_number` |  |  |
| 1423 | **unknown** | `test_mega_is_number` |  |  |
| 1428 | **unknown** | `test_nano_is_number` |  |  |
| 1433 | **unknown** | `test_kilo_times_unit_vector` |  |  |
| 1440 | **unknown** | `test_nano_times_unit_vector` |  |  |
| 1447 | **unknown** | `test_mega_times_unit_vector` |  |  |
| 1454 | **unknown** | `test_prefix_abbreviation_k` |  |  |
| 1459 | **unknown** | `test_prefix_abbreviation_n` |  |  |
| 1475 | **unknown** | `test_inch` |  |  |
| 1482 | **unknown**† | `test_foot` |  |  |
| 1489 | **unknown** | `test_yard` |  |  |
| 1496 | **unknown** | `test_mile` |  |  |
| 1503 | **unknown** | `test_nautical_mile` |  |  |
| 1510 | **unknown** | `test_light_year` |  |  |
| 1519 | **unknown**† | `test_pound_mass` |  |  |
| 1526 | **unknown** | `test_ounce_mass` |  |  |
| 1535 | **unknown** | `test_pound_force` |  |  |
| 1544 | **unknown** | `test_litre` |  |  |
| 1551 | **unknown** | `test_gallon_us` |  |  |
| 1560 | **unknown** | `test_psi` |  |  |
| 1569 | **unknown** | `test_calorie` |  |  |
| 1576 | **unknown** | `test_btu` |  |  |
| 1583 | **unknown**† | `test_kilowatt_hour` |  |  |
| 1592 | **unknown** | `test_horsepower` |  |  |
| 1601 | **unknown** | `test_mph` |  |  |
| 1608 | **unknown** | `test_knot` |  |  |
| 1617 | **unknown** | `test_ft_alias` |  |  |
| 1622 | **unknown** | `test_lb_alias` |  |  |
| 1627 | **unknown** | `test_lbf_alias` |  |  |
| 1632 | **unknown** | `test_nmi_alias` |  |  |
| 1639 | **unknown** | `test_five_feet_twelve_inches_equals_six_feet` |  |  |
| 1644 | **unknown** | `test_mph_to_ms` |  |  |
| 1661 | **unknown** | `test_bit_is_base_unit` |  |  |
| 1668 | **unknown** | `test_bit_dim_key_is_predicate` |  |  |
| 1676 | **unknown** | `test_byte_is_8_bits` |  |  |
| 1683 | **unknown** | `test_byte_10_is_80_bits` |  |  |
| 1690 | **unknown** | `test_kilobyte` |  |  |
| 1697 | **unknown** | `test_megabyte` |  |  |
| 1704 | **unknown** | `test_gigabyte` |  |  |
| 1711 | **unknown** | `test_terabyte` |  |  |
| 1720 | **unknown** | `test_kilobit` |  |  |
| 1727 | **unknown** | `test_megabit` |  |  |
| 1734 | **unknown** | `test_gigabit` |  |  |
| 1743 | **unknown** | `test_kibibyte` |  |  |
| 1750 | **unknown** | `test_mebibyte` |  |  |
| 1757 | **unknown** | `test_gibibyte` |  |  |
| 1764 | **unknown** | `test_tebibyte` |  |  |
| 1773 | **unknown** | `test_kibibit` |  |  |
| 1780 | **unknown** | `test_mebibit` |  |  |
| 1787 | **unknown** | `test_gibibit` |  |  |
| 1796 | **unknown** | `test_kibi_value` |  |  |
| 1801 | **unknown** | `test_mebi_value` |  |  |
| 1806 | **unknown** | `test_gibi_value` |  |  |
| 1811 | **unknown** | `test_tebi_value` |  |  |
| 1816 | **unknown** | `test_pebi_value` |  |  |
| 1821 | **unknown** | `test_exbi_value` |  |  |
| 1828 | **unknown** | `test_gibi_times_byte` |  |  |
| 1835 | **unknown** | `test_mebi_times_byte` |  |  |
| 1844 | **unknown** | `test_add_bytes_and_bits` |  |  |
| 1852 | **unknown** | `test_kibibyte_minus_byte` |  |  |
| 1859 | **unknown** | `test_information_mismatch_with_length` |  |  |

</details>

<details><summary><code>tests/test_yaml_module.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 55 | **mixed** | `test_parse_scalar_int` | call | Var, deref |
| 62 | **mixed** | `test_parse_scalar_float` | call | Var, deref |
| 69 | **mixed** | `test_parse_scalar_string` | call | Var, deref |
| 76 | **mixed** | `test_parse_mapping` | call | Var, deref |
| 84 | **mixed** | `test_parse_sequence` | call | Var, deref |
| 92 | **mixed** | `test_parse_nested_mapping` | call | Var, deref |
| 101 | **mixed** | `test_parse_bool_true` | call | Var, deref |
| 109 | **mixed** | `test_parse_bool_false` | call | Var, deref |
| 117 | **mixed** | `test_parse_null` | call | Var, deref |
| 125 | **mixed** | `test_parse_empty_doc` | call | Var, deref |
| 133 | **mixed** | `test_parse_flow_style_mapping` | call | Var, deref |
| 141 | **mixed** | `test_parse_multiline_literal_block` | call | Var, deref |
| 150 | **mixed** | `test_parse_list_of_mappings` | call | Var, deref |
| 162 | **mixed** | `test_invalid_yaml_fails` | call | Var, deref |
| 179 | **mixed** | `test_write_mapping` | call | Var, deref |
| 187 | **mixed** | `test_write_list` | call | Var, deref |
| 197 | **mixed** | `test_write_scalar` | call | Var, deref |
| 205 | **mixed** | `test_write_nested` | call | Var, deref |
| 215 | **mixed** | `test_write_bool_null` | call | Var, deref |
| 224 | **mixed** | `test_round_trip` | call | Var, deref |
| 243 | **mixed** | `test_multi_doc` | call | Var, deref |
| 252 | **mixed** | `test_single_doc` | call | Var, deref |
| 260 | **mixed** | `test_empty_stream` | call | Var, deref |
| 276 | **mixed** | `test_multi_doc_write` | call | Var, deref |
| 287 | **mixed** | `test_round_trip_multi_doc` | call | Var, deref |
| 305 | **mixed** | `test_read_file` | call | Var, deref |
| 315 | **mixed** | `test_read_nonexistent_file_fails` | call | Var, deref |
| 323 | **mixed** | `test_write_and_read_back` | call | Var, deref |
| 336 | **behavior** | `test_write_file` | call |  |
| 358 | **mixed** | `test_single_key` | call | Var, deref |
| 365 | **mixed** | `test_nested_keys` | call | Var, deref |
| 373 | **mixed** | `test_list_index` | call | Var, deref |
| 380 | **mixed** | `test_mixed_keys_and_indices` | call | Var, deref |
| 388 | **mixed** | `test_missing_key_fails` | call | Var, deref |
| 395 | **mixed** | `test_index_out_of_range_fails` | call | Var, deref |
| 424 | **unknown** | `test_parse_scalar_int` |  |  |
| 428 | **unknown** | `test_parse_scalar_string` |  |  |
| 432 | **unknown** | `test_parse_mapping` |  |  |
| 436 | **unknown** | `test_parse_sequence` |  |  |
| 440 | **unknown** | `test_parse_bool_and_null` |  |  |
| 444 | **unknown** | `test_parse_nested_mapping` |  |  |
| 448 | **unknown** | `test_list_of_maps` |  |  |
| 452 | **unknown** | `test_config_pattern` |  |  |
| 456 | **unknown** | `test_round_trip_mapping` |  |  |
| 460 | **unknown** | `test_write_and_read_back` |  |  |

</details>

### prolog

<details><summary><code>tests/test_gprolog_embedding.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 40 | **unknown** | `test_true` |  |  |
| 44 | **unknown** | `test_fail` |  |  |
| 49 | **unknown** | `test_fact_and_query` |  |  |
| 54 | **unknown** | `test_multiple_solutions` |  |  |
| 60 | **unknown** | `test_arithmetic` |  |  |
| 65 | **unknown** | `test_list_unification` |  |  |
| 70 | **infra** | `test_compound_term` |  | Compound |
| 77 | **unknown** | `test_no_bindings_goal` |  |  |
| 82 | **unknown** | `test_iterator_protocol` |  |  |
| 93 | **unknown** | `test_early_break` |  |  |
| 111 | **unknown** | `test_simple_rule` |  |  |
| 120 | **unknown** | `test_recursive_rule` |  |  |
| 130 | **unknown** | `test_append` |  |  |
| 135 | **unknown** | `test_member` |  |  |
| 140 | **unknown** | `test_length` |  |  |
| 153 | **unknown** | `test_fd_domain_and_labeling` |  |  |
| 161 | **unknown** | `test_fd_constraint_operators` |  |  |
| 172 | **unknown** | `test_fd_equality_constraint` |  |  |
| 184 | **unknown** | `test_fd_all_different` |  |  |
| 204 | **unknown** | `test_consult_clausal_fact` |  |  |
| 209 | **unknown** | `test_consult_clausal_rule` |  |  |
| 226 | **unknown** | `test_to_prolog_int` |  |  |
| 231 | **unknown** | `test_to_prolog_str` |  |  |
| 236 | **unknown** | `test_to_prolog_list` |  |  |
| 241 | **unknown** | `test_to_prolog_bool` |  |  |
| 247 | **unknown** | `test_to_prolog_none` |  |  |
| 252 | **unknown** | `test_to_prolog_in_query` |  |  |

</details>

<details><summary><code>tests/test_gprolog_raw.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 33 | **unknown** | `test_raw_machine_creates` |  |  |
| 39 | **unknown** | `test_raw_singleton_enforcement` |  |  |
| 47 | **unknown** | `test_raw_consult_string` |  |  |
| 56 | **unknown** | `test_raw_arithmetic` |  |  |
| 63 | **unknown** | `test_raw_no_solutions` |  |  |
| 70 | **unknown** | `test_raw_multiple_solutions` |  |  |
| 78 | **unknown** | `test_raw_lazy_iteration` |  |  |
| 93 | **unknown** | `test_raw_machine_busy_while_iterating` |  |  |
| 108 | **unknown** | `test_raw_list_term` |  |  |
| 115 | **infra** | `test_raw_compound_term` |  | Compound |
| 124 | **unknown** | `test_raw_float_term` |  |  |
| 131 | **unknown** | `test_raw_fd_constraint` |  |  |
| 143 | **unknown** | `test_raw_no_bindings` |  |  |

</details>

<details><summary><code>tests/test_prolog_ast.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 14 | **infra** | `test_atom` |  | PAtom |
| 20 | **infra** | `test_atom_quoted` |  | PAtom |
| 25 | **infra** | `test_var` |  | PVar |
| 30 | **infra** | `test_number_int` |  | PNumber |
| 35 | **infra** | `test_number_float` |  | PNumber |
| 40 | **infra** | `test_compound` |  | PAtom, PCompound, PVar |
| 46 | **infra** | `test_list_proper` |  | PList, PNumber |
| 51 | **infra** | `test_list_partial` |  | PList, PVar |
| 56 | **infra** | `test_clause_fact` |  | PClause, PCompound, PNumber |
| 61 | **infra** | `test_clause_rule` |  | PClause, PCompound, PVar |
| 69 | **infra** | `test_dcg_rule` |  | PAtom, PDCGRule, PList |
| 77 | **infra** | `test_directive` |  | PAtom, PCompound, PDirective |
| 82 | **infra** | `test_query` |  | PCompound, PList, PNumber, PQuery, PVar |
| 87 | **infra** | `test_module` |  | PClause, PCompound, PModule, PNumber |
| 95 | **infra** | `test_string` |  | PString |
| 100 | **infra** | `test_curly` |  | PCompound, PCurly, PNumber, PVar |
| 105 | **infra** | `test_frozen` |  | PAtom |
| 111 | **infra** | `test_compound_frozen` |  | PAtom, PCompound |
| 119 | **infra** | `test_atom_builder` |  | PAtom |
| 123 | **infra** | `test_var_builder` |  | PVar |
| 127 | **infra** | `test_anon_builder` |  | PVar |
| 131 | **infra** | `test_compound_builder` |  | PAtom, PCompound, PVar |
| 136 | **infra** | `test_op_builder` |  | PAtom, PCompound |
| 141 | **infra** | `test_prefix_builder` |  | PAtom, PCompound |
| 146 | **infra** | `test_plist_builder` |  | PList, PNumber |
| 151 | **infra** | `test_plist_with_tail` |  | PList, PVar |
| 156 | **infra** | `test_cons_builder` |  | PList, PVar |
| 161 | **infra** | `test_fact_builder` |  | PClause, PNumber |
| 167 | **infra** | `test_rule_builder` |  | PClause |
| 174 | **infra** | `test_dcg_rule_builder` |  | PDCGRule |
| 179 | **infra** | `test_directive_builder` |  | PDirective |
| 184 | **infra** | `test_module_builder` |  | PModule |
| 193 | **infra** | `test_variables_simple` |  | PAtom, PCompound, PVar |
| 198 | **infra** | `test_variables_excludes_anon` |  | PCompound, PVar |
| 203 | **infra** | `test_variables_nested` |  | PCompound, PVar |
| 211 | **infra** | `test_variables_in_list` |  | PList, PVar |
| 216 | **infra** | `test_functors` |  | PCompound, PVar |
| 226 | **infra** | `test_functors_no_compounds` |  | PVar |
| 231 | **infra** | `test_is_ground_true` |  | PAtom, PCompound, PNumber |
| 235 | **infra** | `test_is_ground_false` |  | PCompound, PVar |
| 239 | **infra** | `test_is_ground_anon_false` |  | PCompound, PVar |
| 243 | **infra** | `test_is_ground_atom` |  | PAtom |
| 247 | **infra** | `test_is_ground_number` |  | PNumber |
| 251 | **infra** | `test_is_ground_list` |  | PList, PNumber |
| 255 | **infra** | `test_is_ground_list_with_tail_var` |  | PList, PNumber, PVar |
| 259 | **infra** | `test_term_size` |  | PAtom, PCompound, PNumber |
| 264 | **infra** | `test_term_size_atom` |  | PAtom |
| 268 | **infra** | `test_term_size_list` |  | PList, PNumber |
| 273 | **infra** | `test_subterms` |  | PAtom, PCompound, PNumber |
| 279 | **infra** | `test_subterms_nested` |  | PAtom, PCompound, PNumber |
| 288 | **infra** | `test_collects_atoms` |  | PAtom, PCompound |
| 301 | **infra** | `test_collects_vars` |  | PCompound, PVar |
| 317 | **infra** | `test_visits_list_elements` |  | PList, PNumber |
| 330 | **infra** | `test_visits_curly` |  | PAtom, PCurly |
| 343 | **infra** | `test_visits_clause` |  | PClause, PCompound, PVar |
| 359 | **infra** | `test_visits_module` |  | PAtom, PClause, PModule |
| 378 | **infra** | `test_rename_vars` |  | PAtom, PCompound, PVar |
| 388 | **infra** | `test_identity` |  | PAtom, PCompound, PNumber |
| 394 | **infra** | `test_transform_nested` |  | PCompound, PNumber |
| 404 | **infra** | `test_transform_list` |  | PList, PNumber |
| 414 | **infra** | `test_transform_clause` |  | PClause, PCompound, PVar |
| 430 | **infra** | `test_transform_module_delete_item` |  | PAtom, PClause, PModule |
| 447 | **infra** | `test_transform_curly` |  | PCurly, PVar |
| 457 | **infra** | `test_transform_dcg_rule` |  | PCompound, PDCGRule, PList, PVar |
| 473 | **infra** | `test_transform_directive` |  | PAtom, PCompound, PDirective |

</details>

<details><summary><code>tests/test_prolog_dialect.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 12 | **infra** | `test_iso` |  | Dialect |
| 18 | **infra** | `test_swi` |  | Dialect |
| 27 | **infra** | `test_scryer` |  | Dialect |
| 36 | **infra** | `test_swi_library_map` |  | Dialect |
| 42 | **infra** | `test_scryer_library_map` |  | Dialect |
| 49 | **unknown**† | `test_simple` |  |  |
| 53 | **unknown**† | `test_allcaps` |  |  |
| 57 | **unknown**† | `test_mixed` |  |  |
| 61 | **unknown**† | `test_dcg` |  |  |
| 65 | **unknown**† | `test_copy_term` |  |  |
| 69 | **unknown** | `test_io_stream` |  |  |
| 73 | **unknown** | `test_single_word` |  |  |
| 77 | **unknown** | `test_already_lower` |  |  |
| 81 | **unknown** | `test_f_string_thunk` |  |  |
| 87 | **unknown**† | `test_simple` |  |  |
| 91 | **unknown**† | `test_copy_term` |  |  |
| 95 | **unknown** | `test_all_different` |  |  |
| 99 | **unknown** | `test_single_word` |  |  |
| 103 | **unknown** | `test_already_pascal` |  |  |
| 109 | **unknown**† | `test_leading_underscore` |  |  |
| 113 | **unknown**† | `test_allcaps` |  |  |
| 117 | **unknown**† | `test_single_letter` |  |  |
| 121 | **unknown**† | `test_anon` |  |  |
| 125 | **unknown**† | `test_lowercase_leading` |  |  |
| 129 | **unknown** | `test_mixed_leading` |  |  |
| 133 | **unknown**† | `test_head_leading` |  |  |
| 138 | **unknown** | `test_single_upper` |  |  |
| 144 | **unknown** | `test_single_upper` |  |  |
| 148 | **unknown** | `test_titlecase` |  |  |
| 152 | **unknown** | `test_head` |  |  |
| 156 | **unknown**† | `test_leading_underscore` |  |  |
| 160 | **unknown**† | `test_anon` |  |  |
| 164 | **unknown** | `test_result` |  |  |
| 170 | **infra** | `test_iso_builtin` |  | Dialect |
| 175 | **infra** | `test_iso_copy_term` |  | Dialect |
| 180 | **infra** | `test_swi_all_different` |  | Dialect |
| 185 | **infra** | `test_scryer_all_different` |  | Dialect |
| 190 | **infra** | `test_fallback_pascal_to_snake` |  | Dialect |
| 195 | **infra** | `test_time_goal_swi` |  | Dialect |
| 200 | **infra** | `test_time_goal_scryer` |  | Dialect |
| 205 | **infra** | `test_member_iso` |  | Dialect |
| 210 | **infra** | `test_filter_swi` |  | Dialect |
| 215 | **infra** | `test_filter_scryer` |  | Dialect |

</details>

<details><summary><code>tests/test_prolog_emit.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 21 | **unknown**† | `test_pascal_to_snake_simple` |  |  |
| 25 | **unknown**† | `test_pascal_to_snake_allcaps` |  |  |
| 29 | **unknown**† | `test_pascal_to_snake_mixed` |  |  |
| 33 | **unknown**† | `test_pascal_to_snake_dcg` |  |  |
| 37 | **unknown**† | `test_snake_to_pascal_simple` |  |  |
| 41 | **unknown**† | `test_snake_to_pascal_copy_term` |  |  |
| 45 | **unknown**† | `test_var_leading_underscore` |  |  |
| 49 | **unknown**† | `test_var_allcaps` |  |  |
| 53 | **unknown**† | `test_var_single_letter` |  |  |
| 57 | **unknown**† | `test_var_anon` |  |  |
| 61 | **unknown**† | `test_var_lowercase_leading` |  |  |
| 69 | **infra** | `test_atom` |  | OperatorTable, PAtom |
| 73 | **infra** | `test_atom_needs_quoting` |  | OperatorTable, PAtom |
| 78 | **infra** | `test_var` |  | OperatorTable, PVar |
| 82 | **infra** | `test_anon_var` |  | OperatorTable, PVar |
| 86 | **infra** | `test_integer` |  | OperatorTable, PNumber |
| 90 | **infra** | `test_float` |  | OperatorTable, PNumber |
| 94 | **infra** | `test_string` |  | OperatorTable, PString |
| 98 | **infra** | `test_compound_simple` |  | OperatorTable, PAtom, PCompound, PVar |
| 103 | **infra** | `test_compound_binary_op` |  | OperatorTable, PCompound, PNumber |
| 108 | **infra** | `test_compound_op_precedence` |  | OperatorTable, PCompound, PNumber |
| 114 | **infra** | `test_compound_op_needs_parens` |  | OperatorTable, PCompound, PNumber |
| 120 | **infra** | `test_conjunction` |  | OperatorTable, PCompound |
| 126 | **infra** | `test_disjunction` |  | OperatorTable, PCompound |
| 133 | **infra** | `test_negation` |  | OperatorTable, PCompound |
| 139 | **infra** | `test_list_proper` |  | OperatorTable, PList, PNumber |
| 144 | **infra** | `test_list_partial` |  | OperatorTable, PList, PVar |
| 149 | **infra** | `test_list_empty` |  | OperatorTable, PList |
| 154 | **infra** | `test_curly` |  | OperatorTable, PCompound, PCurly, PNumber, PVar |
| 159 | **infra** | `test_unify` |  | OperatorTable, PCompound, PNumber, PVar |
| 164 | **infra** | `test_is_eval` |  | OperatorTable, PCompound, PNumber, PVar |
| 169 | **infra** | `test_negative_number` |  | OperatorTable, PNumber |
| 173 | **infra** | `test_zero_arity_compound` |  | OperatorTable, PCompound |
| 178 | **infra** | `test_nested_compound` |  | OperatorTable, PAtom, PCompound, PVar |
| 183 | **infra** | `test_slash_indicator` |  | OperatorTable, PAtom, PCompound, PNumber |
| 188 | **infra** | `test_mod_operator` |  | OperatorTable, PCompound, PNumber |
| 193 | **infra** | `test_list_with_multiple_elements_and_tail` |  | OperatorTable, PList, PNumber, PVar |
| 202 | **infra** | `test_fact` |  | OperatorTable, PClause, PCompound, PNumber |
| 207 | **infra** | `test_rule` |  | OperatorTable, PClause, PCompound, PVar |
| 218 | **infra** | `test_rule_with_conjunction` |  | OperatorTable, PClause, PCompound, PVar |
| 232 | **infra** | `test_dcg_rule` |  | OperatorTable, PAtom, PDCGRule, PList |
| 242 | **infra** | `test_directive` |  | OperatorTable, PAtom, PCompound, PDirective, PNumber |
| 251 | **infra** | `test_fact_atom_head` |  | OperatorTable, PAtom, PClause |
| 260 | **infra** | `test_empty_module` |  | OperatorTable, PModule |
| 266 | **infra** | `test_simple_module` |  | OperatorTable, PClause, PCompound, PModule, PNumber |
| 282 | **unknown** | `test_edge_graph` |  |  |
| 298 | **unknown** | `test_arithmetic` |  |  |
| 305 | **unknown** | `test_negation` |  |  |
| 311 | **unknown** | `test_list_spread` |  |  |
| 318 | **unknown** | `test_module_directive` |  |  |
| 324 | **unknown** | `test_unification` |  |  |
| 330 | **unknown** | `test_disequality` |  |  |
| 336 | **unknown** | `test_simple_fact_no_args` |  |  |
| 342 | **unknown** | `test_or_becomes_semicolon` |  |  |
| 348 | **unknown** | `test_comparison_operators` |  |  |
| 354 | **unknown** | `test_lte_becomes_prolog_lte` |  |  |
| 360 | **unknown** | `test_structural_eq` |  |  |
| 366 | **unknown** | `test_structural_neq` |  |  |
| 372 | **unknown** | `test_variable_naming` |  |  |
| 380 | **unknown** | `test_string_literals` |  |  |
| 386 | **unknown** | `test_integer_literals` |  |  |
| 392 | **unknown** | `test_empty_list` |  |  |
| 398 | **unknown** | `test_list_literal` |  |  |
| 404 | **unknown** | `test_builtin_name_mapping` |  |  |
| 412 | **unknown** | `test_import_from_directive` |  |  |
| 419 | **unknown** | `test_dynamic_directive` |  |  |
| 430 | **infra** | `test_simple_fact` |  | PClause, PCompound |
| 441 | **infra** | `test_rule_has_body` |  | PClause |
| 450 | **infra** | `test_directive` |  | PDirective |
| 458 | **infra** | `test_variables_converted` |  | PClause, PCompound, PVar |
| 470 | **infra** | `test_list_with_star_unpack` |  | PList |
| 480 | **infra** | `test_negation_becomes_naf` |  | PCompound |
| 489 | **infra** | `test_named_expr_becomes_is` |  | PCompound |
| 498 | **infra** | `test_and_becomes_conjunction` |  | PCompound |
| 507 | **infra** | `test_or_becomes_disjunction` |  | PCompound |
| 516 | **unknown** | `test_private_directive_omitted` |  |  |

</details>

<details><summary><code>tests/test_prolog_golden.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 53 | **unknown** | `test_golden_snapshot` |  |  |
| 69 | **unknown** | `test_every_clause_ends_with_dot` |  |  |
| 82 | **unknown** | `test_no_trailing_whitespace` |  |  |
| 91 | **unknown** | `test_no_python_syntax_leaks` |  |  |
| 106 | **unknown** | `test_in_translates_to_member` |  |  |
| 111 | **unknown** | `test_not_in_translates_to_negated_member` |  |  |
| 120 | **unknown** | `test_keyword_fact` |  |  |
| 125 | **unknown** | `test_keyword_mixed` |  |  |
| 134 | **unknown** | `test_double_uadd_warning` |  |  |
| 142 | **infra** | `test_fstring_swi_format` |  | Dialect |
| 153 | **unknown** | `test_fstring_iso_warning` |  |  |
| 160 | **unknown** | `test_set_single_element_is_curly` |  |  |
| 167 | **unknown** | `test_set_multi_element_warning` |  |  |
| 174 | **infra** | `test_dict_swi` |  | Dialect |
| 184 | **unknown** | `test_dict_iso_warning` |  |  |
| 195 | **infra** | `test_import_known_library_swi` |  | Dialect |
| 205 | **infra** | `test_import_known_library_scryer` |  | Dialect |
| 215 | **unknown** | `test_import_python_only_warning` |  |  |
| 224 | **infra** | `test_table_scryer_adds_use_module` |  | Dialect |
| 239 | **unknown** | `test_cli_help` |  |  |
| 249 | **unknown** | `test_cli_pipe` |  |  |
| 260 | **unknown** | `test_cli_file` |  |  |
| 307 | **unknown** | `test_reverse_golden_snapshot` |  |  |
| 329 | **unknown** | `test_no_trailing_whitespace` |  |  |
| 341 | **unknown** | `test_no_prolog_syntax_leaks` |  |  |
| 359 | **unknown** | `test_uses_clausal_conventions` |  |  |
| 381 | **unknown** | `test_help` |  |  |
| 391 | **unknown** | `test_roundtrip_flag` |  |  |

</details>

<details><summary><code>tests/test_prolog_import.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 65 | **unknown** | `test_facts` |  |  |
| 77 | **mixed** | `test_facts_queryable` | call | Var |
| 89 | **mixed** | `test_rule_with_body` | call | Var, deref |
| 113 | **mixed** | `test_is_operator` | call | Var, deref |
| 124 | **behavior** | `test_comparison` | call |  |
| 134 | **behavior** | `test_unification` | call |  |
| 151 | **unknown** | `test_pyc_created` |  |  |
| 166 | **unknown** | `test_pyc_path_matches_source` |  |  |
| 183 | **unknown** | `test_source_to_code_skipped_on_cache_hit` |  |  |
| 199 | **mixed** | `test_cached_predicates_work` | call | Var |
| 221 | **unknown** | `test_modified_source_recompiles` |  |  |
| 252 | **mixed** | `test_chained_import` | call | Var |
| 270 | **mixed** | `test_imported_facts_accessible` | call | Var, deref |
| 294 | **infra** | `test_clpfd_library_translates_to_import` |  | Dialect |
| 304 | **infra** | `test_lists_library_no_import_generated` |  | Dialect |
| 323 | **unknown** | `test_clausal_wins_over_pl` |  |  |
| 349 | **unknown** | `test_cut_loads_successfully` |  |  |
| 358 | **unknown** | `test_if_then_else_raises_syntax_error` |  |  |
| 374 | **mixed** | `test_dcg_rule` | call | Var |
| 392 | **mixed** | `test_assertz_after_import` | call | Var |
| 415 | **unknown** | `test_empty_pl_file` |  |  |
| 421 | **unknown** | `test_comments_only` |  |  |
| 430 | **unknown** | `test_non_utf8_raises_syntax_error` |  |  |
| 444 | **unknown** | `test_import_finds_pl_file` |  |  |
| 476 | **unknown** | `test_golden_imports` |  |  |
| 486 | **behavior** | `test_golden_tests_pass` | collect_tests, run_test |  |

</details>

<details><summary><code>tests/test_prolog_operators.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 31 | **unknown** | `test_trunc_div_positive` |  |  |
| 36 | **unknown** | `test_trunc_div_negative_dividend` |  |  |
| 42 | **unknown** | `test_trunc_div_negative_divisor` |  |  |
| 47 | **unknown** | `test_trunc_mod_positive` |  |  |
| 52 | **unknown** | `test_trunc_mod_negative_dividend` |  |  |
| 58 | **unknown** | `test_rem_positive` |  |  |
| 63 | **unknown** | `test_rem_negative` |  |  |
| 75 | **unknown** | `test_integer_division_emits_prolog_qualified` |  |  |
| 81 | **unknown** | `test_mod_emits_prolog_qualified` |  |  |
| 87 | **unknown** | `test_rem_emits_prolog_qualified` |  |  |
| 93 | **unknown** | `test_auto_imports_prolog_module` |  |  |
| 99 | **unknown** | `test_no_prolog_import_when_not_needed` |  |  |
| 112 | **unknown** | `test_atom_declared_via_private` |  |  |
| 121 | **unknown** | `test_atom_used_as_bare_name` |  |  |
| 129 | **unknown** | `test_true_false_not_in_private` |  |  |
| 137 | **unknown** | `test_numbers_not_in_private` |  |  |
| 143 | **unknown** | `test_functor_names_not_affected` |  |  |
| 174 | **mixed** | `test_atoms_as_data` | call | Var, deref |
| 190 | **mixed** | `test_iso_truncate_div` | call | Var, deref |
| 204 | **mixed** | `test_iso_mod` | call | Var, deref |
| 218 | **behavior** | `test_mixed_atoms_and_arithmetic` | call |  |

</details>

<details><summary><code>tests/test_prolog_parse.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 22 | **infra** | `test_word_atom` |  | Token, TokenType, tokenize |
| 27 | **infra** | `test_quoted_atom` |  | Token, TokenType, tokenize |
| 32 | **infra** | `test_quoted_atom_doubled_quote` |  | tokenize |
| 37 | **infra** | `test_graphic_atom` |  | Token, TokenType, tokenize |
| 42 | **infra** | `test_graphic_op` |  | Token, TokenType, tokenize |
| 47 | **infra** | `test_semicolon` |  | Token, TokenType, tokenize |
| 52 | **infra** | `test_cut` |  | Token, TokenType, tokenize |
| 57 | **infra** | `test_arrow` |  | Token, TokenType, tokenize |
| 62 | **infra** | `test_dcg_arrow` |  | Token, TokenType, tokenize |
| 69 | **infra** | `test_uppercase` |  | Token, TokenType, tokenize |
| 74 | **infra** | `test_longer_var` |  | Token, TokenType, tokenize |
| 79 | **infra** | `test_anonymous` |  | Token, TokenType, tokenize |
| 84 | **infra** | `test_named_underscore` |  | Token, TokenType, tokenize |
| 91 | **infra** | `test_integer` |  | Token, TokenType, tokenize |
| 96 | **infra** | `test_float` |  | Token, TokenType, tokenize |
| 101 | **infra** | `test_float_exponent` |  | TokenType, tokenize |
| 107 | **infra** | `test_hex` |  | Token, TokenType, tokenize |
| 112 | **infra** | `test_binary` |  | Token, TokenType, tokenize |
| 117 | **infra** | `test_octal` |  | Token, TokenType, tokenize |
| 122 | **infra** | `test_char_code` |  | Token, TokenType, tokenize |
| 127 | **infra** | `test_char_code_space` |  | Token, TokenType, tokenize |
| 134 | **infra** | `test_simple` |  | Token, TokenType, tokenize |
| 139 | **infra** | `test_escape` |  | tokenize |
| 144 | **infra** | `test_doubled_quote` |  | tokenize |
| 151 | **infra** | `test_parens` |  | TokenType, tokenize |
| 157 | **infra** | `test_brackets` |  | TokenType, tokenize |
| 166 | **infra** | `test_curly` |  | TokenType, tokenize |
| 172 | **infra** | `test_bar` |  | TokenType, tokenize |
| 183 | **infra** | `test_clause_terminator` |  | Token, TokenType, tokenize |
| 188 | **infra** | `test_dot_eof` |  | TokenType, tokenize |
| 194 | **infra** | `test_dot_whitespace` |  | TokenType, tokenize |
| 200 | **infra** | `test_dot_in_float_not_terminator` |  | TokenType, tokenize |
| 207 | **infra** | `test_line_comment` |  | TokenType, tokenize |
| 213 | **infra** | `test_block_comment` |  | TokenType, tokenize |
| 219 | **infra** | `test_nested_block_comment` |  | TokenType, tokenize |
| 227 | **infra** | `test_unterminated_quoted_atom` |  | TokenizeError, tokenize |
| 232 | **infra** | `test_unterminated_string` |  | TokenizeError, tokenize |
| 239 | **infra** | `test_fact` |  | TokenType, tokenize |
| 249 | **infra** | `test_rule` |  | TokenType, tokenize |
| 257 | **infra** | `test_negative_number_in_expr` |  | TokenType, tokenize |
| 272 | **infra** | `test_atom` |  | PAtom, parse_term |
| 277 | **infra** | `test_variable` |  | PVar, parse_term |
| 282 | **infra** | `test_integer` |  | PNumber, parse_term |
| 287 | **infra** | `test_float` |  | PNumber, parse_term |
| 292 | **infra** | `test_string` |  | PString, parse_term |
| 297 | **infra** | `test_compound` |  | PAtom, PCompound, parse_term |
| 304 | **infra** | `test_nested_compound` |  | PCompound, parse_term |
| 312 | **infra** | `test_empty_list` |  | PList, parse_term |
| 317 | **infra** | `test_proper_list` |  | PList, PNumber, parse_term |
| 324 | **infra** | `test_partial_list` |  | PList, PVar, parse_term |
| 331 | **infra** | `test_multi_head_list` |  | PList, PVar, parse_term |
| 338 | **infra** | `test_curly` |  | PAtom, PCurly, parse_term |
| 344 | **infra** | `test_empty_curly` |  | PAtom, parse_term |
| 349 | **infra** | `test_parenthesized` |  | PAtom, parse_term |
| 354 | **infra** | `test_negative_number` |  | PNumber, parse_term |
| 359 | **infra** | `test_quoted_atom` |  | PAtom, parse_term |
| 366 | **infra** | `test_infix_plus` |  | PCompound, PNumber, parse_term |
| 373 | **infra** | `test_precedence` |  | PCompound, parse_term |
| 380 | **infra** | `test_left_assoc` |  | PCompound, parse_term |
| 387 | **infra** | `test_right_assoc` |  | PCompound, parse_term |
| 394 | **infra** | `test_negation_prefix` |  | PAtom, PCompound, parse_term |
| 401 | **infra** | `test_unification` |  | PAtom, PCompound, PVar, parse_term |
| 408 | **infra** | `test_is_expr` |  | PCompound, parse_term |
| 414 | **infra** | `test_conjunction` |  | PAtom, PCompound, parse_term |
| 424 | **infra** | `test_clause_arrow` |  | PAtom, PCompound, parse_term |
| 430 | **infra** | `test_comparison` |  | PCompound, parse_term |
| 435 | **infra** | `test_mod_operator` |  | PCompound, parse_term |
| 440 | **infra** | `test_power` |  | PCompound, parse_term |
| 447 | **infra** | `test_simple_fact` |  | PClause, PCompound, parse |
| 457 | **infra** | `test_simple_rule` |  | PClause, parse |
| 465 | **infra** | `test_multiple_clauses` |  | parse |
| 470 | **infra** | `test_directive` |  | PDirective, parse |
| 476 | **infra** | `test_dcg_rule` |  | PDCGRule, parse |
| 482 | **infra** | `test_atom_fact` |  | PAtom, PClause, parse |
| 489 | **infra** | `test_multiline_rule` |  | PClause, parse |
| 502 | **infra** | `test_list_head` |  | parse |
| 507 | **infra** | `test_list_pattern` |  | PCompound, parse |
| 514 | **infra** | `test_query` |  | PQuery, parse |
| 520 | **infra** | `test_cut_in_body` |  | PClause, parse |
| 528 | **infra** | `test_op_directive_affects_parsing` |  | PClause, PCompound, PDirective, parse |
| 545 | **infra** | `test_edge_graph` |  | parse |
| 562 | **infra** | `test_fibonacci` |  | PClause, parse |
| 580 | **infra** | `test_dcg_grammar` |  | PDCGRule, PDirective, parse |
| 597 | **infra** | `test_if_then_else` |  | parse |
| 603 | **infra** | `test_nested_negation` |  | PClause, parse |
| 612 | **infra** | `test_zero_arity_compound` |  | PCompound, parse_term |
| 619 | **infra** | `test_operator_as_atom_in_compound` |  | PCompound, parse_term |
| 625 | **infra** | `test_nested_list` |  | PList, parse_term |
| 631 | **infra** | `test_string_in_compound` |  | PCompound, PString, parse_term |
| 637 | **infra** | `test_predicate_indicator` |  | PAtom, PCompound, PNumber, parse_term |

</details>

<details><summary><code>tests/test_prolog_roundtrip.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 86 | **infra** | `test_roundtrip_ok` |  | Dialect |
| 92 | **infra** | `test_fact_preserves_arity` |  | PAtom, PClause, PCompound, parse |
| 103 | **infra** | `test_rule_preserves_clause_count` |  | PClause, parse |
| 124 | **infra** | `test_roundtrip_produces_valid_prolog` |  | parse |
| 132 | **infra** | `test_fact_arity_preserved` |  | PAtom, PClause, PCompound, parse |
| 148 | **unknown** | `test_arithmetic_precedence_clausal_roundtrip` |  |  |
| 161 | **infra** | `test_arithmetic_precedence_prolog_roundtrip` |  | parse |
| 172 | **infra** | `test_comparison_chain` |  | PClause, PCompound, parse |
| 195 | **infra** | `test_shared_variables_clausal_roundtrip` |  | PClause, PCompound, PVar, parse |
| 207 | **infra** | `test_shared_variables_prolog_roundtrip` |  | PClause, PCompound, PVar, parse |
| 217 | **infra** | `test_anonymous_variables` |  | PClause, PCompound, PVar, parse |
| 246 | **infra** | `test_clause_order_clausal_roundtrip` |  | PAtom, PClause, PCompound, parse |
| 262 | **infra** | `test_clause_order_prolog_roundtrip` |  | PClause, parse |
| 275 | **infra** | `test_multi_predicate_order` |  | PAtom, PClause, PCompound, parse |
| 317 | **infra** | `test_clause_count_preserved` |  | PClause, parse |
| 332 | **infra** | `test_head_functors_preserved` |  | PAtom, PClause, PCompound, parse |
| 341 | **infra** | `test_variable_count_preserved` |  | PClause, PCompound, PVar, parse |
| 354 | **infra** | `test_prolog_output_parses` |  | parse |
| 382 | **infra** | `test_clause_count_preserved` |  | PClause, parse |
| 393 | **infra** | `test_head_functors_preserved` |  | PAtom, PClause, PCompound, parse |
| 400 | **infra** | `test_prolog_output_parses` |  | parse |
| 417 | **unknown** | `test_roundtrip_exit_code_simple_fact` |  |  |
| 428 | **unknown** | `test_roundtrip_file_based` |  |  |
| 436 | **unknown** | `test_translate_clausal_to_prolog_autodetect` |  |  |
| 446 | **unknown** | `test_translate_prolog_to_clausal_autodetect` |  |  |
| 456 | **unknown** | `test_translate_explicit_to_flag` |  |  |
| 476 | **unknown** | `test_clausal_dynamic_to_prolog` |  |  |
| 483 | **unknown** | `test_prolog_dynamic_to_clausal` |  |  |
| 490 | **unknown** | `test_prolog_module_to_clausal` |  |  |

</details>

<details><summary><code>tests/test_prolog_to_clausal.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 27 | **infra** | `test_atom` |  | PAtom |
| 31 | **infra** | `test_variable_single_letter` |  | PVar |
| 35 | **infra** | `test_variable_titlecase` |  | PVar |
| 39 | **infra** | `test_variable_anonymous` |  | PVar |
| 43 | **infra** | `test_variable_named_underscore` |  | PVar |
| 47 | **infra** | `test_integer` |  | PNumber |
| 51 | **infra** | `test_float` |  | PNumber |
| 55 | **infra** | `test_string` |  | PString |
| 59 | **infra** | `test_empty_list` |  | PList |
| 63 | **infra** | `test_proper_list` |  | PList, PNumber |
| 68 | **infra** | `test_partial_list` |  | PList, PVar |
| 73 | **infra** | `test_compound` |  | PCompound, PVar |
| 78 | **infra** | `test_negation` |  | PAtom, PCompound |
| 83 | **infra** | `test_unification` |  | PCompound, PNumber, PVar |
| 88 | **infra** | `test_arithmetic_is` |  | PCompound, PNumber, PVar |
| 100 | **infra** | `test_fact` |  | PClause, PCompound, PNumber |
| 105 | **infra** | `test_rule` |  | PClause, PCompound, PVar |
| 113 | **infra** | `test_rule_with_conjunction` |  | PClause, PCompound, PVar |
| 125 | **infra** | `test_dcg_rule` |  | PAtom, PDCGRule, PList, PString |
| 133 | **infra** | `test_directive_module` |  | PAtom, PCompound, PDirective, PList |
| 140 | **infra** | `test_directive_dynamic` |  | PAtom, PCompound, PDirective, PNumber |
| 154 | **unknown** | `test_edge_graph` |  |  |
| 168 | **unknown** | `test_arithmetic` |  |  |
| 174 | **unknown** | `test_negation` |  |  |
| 180 | **unknown** | `test_list_cons` |  |  |
| 186 | **unknown** | `test_unification` |  |  |
| 192 | **unknown** | `test_disunification` |  |  |
| 198 | **unknown** | `test_comparison_leq` |  |  |
| 204 | **unknown** | `test_structural_equality` |  |  |
| 210 | **unknown** | `test_structural_inequality` |  |  |
| 216 | **unknown** | `test_disjunction` |  |  |
| 222 | **unknown** | `test_if_then_else_rejected` |  |  |
| 228 | **unknown** | `test_bare_if_then_rejected` |  |  |
| 234 | **unknown** | `test_member_to_in` |  |  |
| 240 | **unknown** | `test_builtin_name_mapping` |  |  |
| 246 | **unknown** | `test_module_directive` |  |  |
| 252 | **unknown** | `test_dynamic_directive` |  |  |
| 258 | **infra** | `test_use_module` |  | Dialect |
| 264 | **unknown** | `test_dcg_rule` |  |  |
| 272 | **unknown** | `test_cut_translated` |  |  |
| 278 | **unknown** | `test_cut_fact_translated` |  |  |
| 285 | **unknown** | `test_op_directive_as_comment` |  |  |
| 293 | **unknown** | `test_snake_to_pascal` |  |  |
| 299 | **unknown** | `test_variable_conversion` |  |  |
| 306 | **unknown** | `test_single_letter_var` |  |  |
| 313 | **unknown** | `test_anonymous_var` |  |  |
| 321 | **infra** | `test_swi_default` |  | Dialect |
| 327 | **infra** | `test_iso_default` |  | Dialect |
| 351 | **infra** | `test_parses_without_error` |  | parse |
| 361 | **unknown** | `test_emits_clausal_output` |  |  |
| 374 | **unknown** | `test_no_prolog_syntax_leaks` |  |  |
| 399 | **infra** | `test_golden_pl_parses` |  | parse |
| 408 | **unknown** | `test_golden_pl_translates` |  |  |

</details>

### scipy_torch

<details><summary><code>tests/test_scipy_cluster.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 78 | **mixed** | `test_returns_matrix` | _drive | Trail, Var, _get_dispatch, deref |
| 84 | **mixed** | `test_with_method` | _drive | Trail, Var, _get_dispatch, deref |
| 90 | **mixed** | `test_with_method_and_metric` | _drive | Trail, Var, _get_dispatch, deref |
| 96 | **mixed** | `test_with_optimal_ordering` | _drive | Trail, Var, _get_dispatch, deref |
| 102 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 106 | **mixed** | `test_distances_are_non_negative` | _drive | Trail, Var, _get_dispatch, deref, np |
| 120 | **mixed** | `test_returns_labels` | _drive | Trail, Var, _get_dispatch, deref |
| 126 | **mixed** | `test_two_clusters_split_correctly` | _drive | Trail, Var, _get_dispatch, deref |
| 135 | **mixed** | `test_with_depth` | _drive | Trail, Var, _get_dispatch, deref |
| 141 | **mixed** | `test_default_criterion` | _drive | Trail, Var, _get_dispatch, deref |
| 148 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 161 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 167 | **mixed** | `test_has_required_keys` | _drive | Trail, Var, _get_dispatch, deref |
| 176 | **mixed** | `test_leaves_count` | _drive | Trail, Var, _get_dispatch, deref |
| 182 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 186 | **mixed** | `test_result_get_leaves` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 202 | **mixed** | `test_returns_distance_array` | _drive | Trail, Var, _get_dispatch, deref, np |
| 212 | **mixed** | `test_distances_non_negative` | _drive | Trail, Var, _get_dispatch, deref, np |
| 217 | **mixed** | `test_with_y_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 227 | **mixed** | `test_with_y_high_correlation` | _drive | Trail, Var, _get_dispatch, deref |
| 235 | **mixed** | `test_with_y_d_matches_no_y` | _drive | Trail, Var, _get_dispatch, deref, np |
| 243 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 256 | **mixed** | `test_returns_array` | _drive | Trail, Var, _get_dispatch, deref |
| 262 | **mixed** | `test_with_depth` | _drive | Trail, Var, _get_dispatch, deref |
| 268 | **mixed** | `test_values_are_numeric` | _drive | Trail, Var, _get_dispatch, deref, np |
| 273 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 281 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 289 | **mixed** | `test_correct_cluster_count` | _drive | Trail, Var, _get_dispatch, deref |
| 295 | **mixed** | `test_with_iterations` | _drive | Trail, Var, _get_dispatch, deref |
| 300 | **mixed** | `test_with_seed` | _drive | Trail, Var, _get_dispatch, deref |
| 306 | **mixed** | `test_result_get_centroid` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 313 | **mixed** | `test_result_get_label` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 320 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 328 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 336 | **mixed** | `test_correct_codebook_shape` | _drive | Trail, Var, _get_dispatch, deref |
| 341 | **mixed** | `test_distortion_is_float` | _drive | Trail, Var, _get_dispatch, deref |
| 347 | **mixed** | `test_with_iterations` | _drive | Trail, Var, _get_dispatch, deref |
| 352 | **mixed** | `test_result_get_codebook` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 359 | **mixed** | `test_result_get_distortion` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 366 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 379 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 387 | **mixed** | `test_code_shape` | _drive | Trail, Var, _get_dispatch, deref |
| 392 | **mixed** | `test_dist_shape` | _drive | Trail, Var, _get_dispatch, deref |
| 397 | **mixed** | `test_dist_non_negative` | _drive | Trail, Var, _get_dispatch, deref, np |
| 402 | **mixed** | `test_result_get_code` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 409 | **mixed** | `test_wrong_result_fails` | _drive | Trail, Var, _get_dispatch, deref |
| 417 | **mixed** | `test_returns_array` | _drive | Trail, Var, _get_dispatch, deref |
| 423 | **mixed** | `test_unit_variance_columns` | _drive | Trail, Var, _get_dispatch, deref, np |
| 430 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 438 | **mixed** | `test_extracts_known_key` | _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 445 | **mixed** | `test_missing_key_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 451 | **infra** | `test_non_string_field_fails` |  | Trail, Var, _get_dispatch, np |
| 500 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_scipy_constants.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 57 | **infra** | `test_is_quantity` |  | Quantity |
| 59 | **infra** | `test_value` |  | Quantity |
| 60 | **infra** | `test_dims` |  | Quantity |
| 67 | **infra** | `test_is_quantity` |  | Quantity |
| 69 | **infra** | `test_value` |  | Quantity |
| 70 | **infra** | `test_dims` |  | Quantity |
| 77 | **infra** | `test_is_quantity` |  | Quantity |
| 78 | **infra** | `test_value` |  | Quantity |
| 81 | **infra** | `test_dims` |  | Quantity |
| 88 | **infra** | `test_is_quantity` |  | Quantity |
| 90 | **infra** | `test_value` |  | Quantity |
| 91 | **infra** | `test_dims` |  | Quantity |
| 98 | **infra** | `test_is_quantity` |  | Quantity |
| 100 | **infra** | `test_value` |  | Quantity |
| 101 | **infra** | `test_dims` |  | Quantity |
| 108 | **infra** | `test_is_quantity` |  | Quantity |
| 110 | **infra** | `test_value` |  | Quantity |
| 111 | **infra** | `test_dims` |  | Quantity |
| 119 | **infra** | `test_is_quantity` |  | Quantity |
| 121 | **infra** | `test_value` |  | Quantity |
| 122 | **infra** | `test_dims` |  | Quantity |
| 129 | **infra** | `test_is_quantity` |  | Quantity |
| 131 | **infra** | `test_value` |  | Quantity |
| 132 | **infra** | `test_dims` |  | Quantity |
| 139 | **infra** | `test_is_quantity` |  | Quantity |
| 141 | **infra** | `test_value` |  | Quantity |
| 142 | **infra** | `test_dims` |  | Quantity |
| 145 | **infra** | `test_heavier_than_electron` |  | Quantity |
| 152 | **infra** | `test_is_quantity` |  | Quantity |
| 154 | **infra** | `test_value` |  | Quantity |
| 155 | **infra** | `test_dims_are_energy` |  | Quantity |
| 158 | **infra** | `test_matches_elementary_charge_value` |  | Quantity |
| 165 | **infra** | `test_is_quantity` |  | Quantity |
| 167 | **infra** | `test_value` |  | Quantity |
| 168 | **infra** | `test_dims_are_pressure` |  | Quantity |
| 177 | **unknown** | `test_kilo` |  |  |
| 179 | **unknown** | `test_mega` |  |  |
| 181 | **unknown** | `test_giga` |  |  |
| 182 | **unknown** | `test_are_floats` |  |  |
| 192 | **infra** | `test_speed_of_light` |  | Trail, Var, _get_dispatch, deref |
| 195 | **infra** | `test_unknown_fails` |  | Trail, Var, _get_dispatch, deref |
| 201 | **infra** | `test_speed_of_light_unit` |  | Trail, Unit, Var, _get_dispatch, deref |
| 208 | **infra** | `test_c_is_exact` |  | Trail, Var, _get_dispatch, deref |
| 211 | **infra** | `test_G_has_uncertainty` |  | Trail, Var, _get_dispatch, deref |
| 217 | **infra** | `test_returns_all_three` |  | Trail, Var, _get_dispatch, deref |
| 230 | **infra** | `test_unknown_fails` |  | Trail, Var, _get_dispatch |
| 241 | **infra** | `test_finds_electron_mass` |  | Trail, Var, _get_dispatch, deref |
| 246 | **infra** | `test_no_match_is_empty` |  | Trail, Var, _get_dispatch, deref |
| 253 | **infra** | `test_returns_many` |  | Trail, Var, _get_dispatch, deref |
| 257 | **infra** | `test_contains_known` |  | Trail, Var, _get_dispatch, deref |
| 313 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_scipy_differentiate.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 72 | **mixed** | `test_quadratic_at_3` | _drive | Trail, Var, _get_dispatch, deref |
| 79 | **mixed** | `test_sin_at_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 87 | **mixed** | `test_exp_at_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 94 | **mixed** | `test_result_dict_has_required_fields` | _drive | Trail, Var, _get_dispatch, deref |
| 101 | **mixed** | `test_success_flag` | _drive | Trail, Var, _get_dispatch, deref |
| 106 | **mixed** | `test_with_extra_args` | _drive | Trail, Var, _get_dispatch, deref |
| 113 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 117 | **mixed** | `test_x_field_echoes_input` | _drive | Trail, Var, _get_dispatch, deref |
| 126 | **mixed** | `test_linear_function` | _drive | Trail, Var, _get_dispatch, deref, np |
| 141 | **mixed** | `test_result_dict_has_required_fields` | _drive | Trail, Var, _get_dispatch, deref, np |
| 149 | **mixed** | `test_quadratic_jacobian` | _drive | Trail, Var, _get_dispatch, deref, np |
| 162 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 174 | **mixed** | `test_quadratic_hessian_is_identity_scaled` | _drive | Trail, Var, _get_dispatch, deref, np |
| 187 | **mixed** | `test_result_dict_has_required_fields` | _drive | Trail, Var, _get_dispatch, deref, np |
| 198 | **mixed** | `test_mixed_partial` | _drive | Trail, Var, _get_dispatch, deref, np |
| 212 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 227 | **mixed** | `test_get_df` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 233 | **mixed** | `test_get_x` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 239 | **mixed** | `test_get_success` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 245 | **mixed** | `test_get_error` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 251 | **infra** | `test_missing_field_fails` |  | Trail, Var, _get_dispatch |
| 261 | **infra** | `test_bound_value_unifies` |  | Trail, _get_dispatch |
| 272 | **infra** | `test_bound_wrong_value_fails` |  | Trail, _get_dispatch |
| 281 | **mixed** | `test_hessian_result_get` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 320 | **behavior**† | `test_fixture` | call |  |
| 339 | **mixed** | `test_derivative_linear_newton_per_metre` | _drive | Quantity, Trail, Var, _get_dispatch, deref |
| 353 | **mixed** | `test_derivative_x_has_input_units` | _drive | Quantity, Trail, Var, _get_dispatch, deref |
| 365 | **mixed** | `test_derivative_error_has_df_units` | _drive | Quantity, Trail, Var, _get_dispatch, deref |
| 377 | **mixed** | `test_derivative_plain_function_returns_plain_df` | _drive | Quantity, Trail, Var, _get_dispatch, deref |
| 388 | **mixed** | `test_derivative_plain_fast_path` | _drive | Quantity, Trail, Var, _get_dispatch, deref |
| 397 | **mixed** | `test_derivative_dimensionless_quantity` | _drive | Quantity, Trail, Var, _get_dispatch, deref |
| 410 | **mixed** | `test_jacobian_linear_map` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 424 | **mixed** | `test_jacobian_plain_fast_path` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 435 | **mixed** | `test_hessian_with_quantity_x` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 449 | **mixed** | `test_hessian_plain_fast_path` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |

</details>

<details><summary><code>tests/test_scipy_fft.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 95 | **mixed** | `test_constant_signal_dc_only` | _drive | Trail, Var, _get_dispatch, deref, np |
| 104 | **mixed** | `test_impulse_spectrum_flat` | _drive | Trail, Var, _get_dispatch, deref, np |
| 112 | **mixed** | `test_with_output_length` | _drive | Trail, Var, _get_dispatch, deref, np |
| 120 | **mixed** | `test_complex_input` | _drive | Trail, Var, _get_dispatch, deref, np |
| 127 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 136 | **mixed** | `test_round_trip` | _drive | Trail, Var, _get_dispatch, deref, np |
| 145 | **infra** | `test_dc_only_to_constant` |  | Trail, Var, _get_dispatch, deref, np |
| 153 | **infra** | `test_with_output_length` |  | Trail, Var, _get_dispatch, deref, np |
| 161 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 176 | **mixed** | `test_identity_matrix` | _drive | Trail, Var, _get_dispatch, deref, np |
| 183 | **mixed** | `test_constant_matrix_dc_only` | _drive | Trail, Var, _get_dispatch, deref, np |
| 192 | **mixed** | `test_with_output_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 199 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 208 | **mixed** | `test_round_trip` | _drive | Trail, Var, _get_dispatch, deref, np |
| 217 | **mixed** | `test_wrong_result_fails` | _drive | Trail, Var, _get_dispatch, deref, np |
| 233 | **mixed** | `test_1d_matches_fft` | _drive | Trail, Var, _get_dispatch, deref, np |
| 241 | **mixed** | `test_2d_round_trip` | _drive | Trail, Var, _get_dispatch, deref, np |
| 250 | **mixed** | `test_with_output_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 257 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 266 | **mixed** | `test_output_length` | _drive | Trail, Var, _get_dispatch, deref, np |
| 274 | **mixed** | `test_impulse_flat_spectrum` | _drive | Trail, Var, _get_dispatch, deref, np |
| 281 | **mixed** | `test_constant_signal` | _drive | Trail, Var, _get_dispatch, deref, np |
| 290 | **mixed** | `test_with_output_length` | _drive | Trail, Var, _get_dispatch, deref, np |
| 297 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 306 | **mixed** | `test_round_trip` | _drive | Trail, Var, _get_dispatch, deref, np |
| 315 | **mixed** | `test_output_is_real` | _drive | Trail, Var, _get_dispatch, deref, np |
| 323 | **infra** | `test_with_output_length` |  | Trail, Var, _get_dispatch, deref, np |
| 331 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 346 | **mixed** | `test_constant_signal` | _drive | Trail, Var, _get_dispatch, deref, np |
| 357 | **mixed** | `test_type_2_is_default` | _drive | Trail, Var, _get_dispatch, deref, np |
| 365 | **mixed** | `test_type_1` | _drive | Trail, Var, _get_dispatch, deref, np |
| 372 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 381 | **mixed** | `test_round_trip` | _drive | Trail, Var, _get_dispatch, deref, np |
| 390 | **mixed** | `test_type_2_round_trip` | _drive | Trail, Var, _get_dispatch, deref, np |
| 399 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 414 | **mixed** | `test_length_4` | _drive | Trail, Var, _get_dispatch, deref, np |
| 422 | **mixed** | `test_with_sample_spacing` | _drive | Trail, Var, _get_dispatch, deref, np |
| 430 | **mixed** | `test_length_equals_n` | _drive | Trail, Var, _get_dispatch, deref |
| 436 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 444 | **mixed** | `test_length_4` | _drive | Trail, Var, _get_dispatch, deref, np |
| 452 | **mixed** | `test_length_is_n_half_plus_one` | _drive | Trail, Var, _get_dispatch, deref |
| 458 | **mixed** | `test_with_sample_spacing` | _drive | Trail, Var, _get_dispatch, deref, np |
| 465 | **mixed** | `test_all_non_negative` | _drive | Trail, Var, _get_dispatch, deref |
| 471 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 479 | **mixed** | `test_1d_shift` | _drive | Trail, Var, _get_dispatch, deref, np |
| 488 | **mixed** | `test_moves_dc_to_centre` | _drive | Trail, Var, _get_dispatch, deref |
| 497 | **mixed** | `test_2d_shift` | _drive | Trail, Var, _get_dispatch, deref, np |
| 504 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 513 | **mixed** | `test_round_trip_1d` | _drive | Trail, Var, _get_dispatch, deref, np |
| 522 | **mixed** | `test_round_trip_2d` | _drive | Trail, Var, _get_dispatch, deref, np |
| 530 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 579 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_scipy_integrate.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 72 | **mixed** | `test_sin_0_to_pi` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 79 | **mixed** | `test_result_has_error` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 87 | **mixed** | `test_with_args` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 95 | **mixed** | `test_constant_function` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 102 | **mixed** | `test_result_get_value` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 109 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 117 | **mixed** | `test_unit_square` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 125 | **mixed** | `test_result_has_error` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 132 | **mixed** | `test_xy_product` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 140 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 148 | **mixed** | `test_unit_cube` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 156 | **mixed** | `test_result_has_error` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 167 | **mixed** | `test_unit_square` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 175 | **mixed** | `test_result_has_error` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 182 | **mixed** | `test_1d` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 190 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 198 | **mixed** | `test_sin_0_to_pi` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 206 | **mixed** | `test_result_has_success` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 213 | **mixed** | `test_result_has_err` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 220 | **mixed** | `test_result_has_neval` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 232 | **mixed** | `test_exponential_decay` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 247 | **mixed** | `test_result_success` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 257 | **mixed** | `test_with_method_rk45` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 268 | **mixed** | `test_with_method_rk23` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 280 | **mixed** | `test_with_t_eval` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 294 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 301 | **mixed** | `test_result_has_nfev` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 316 | **mixed** | `test_exponential_decay` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 327 | **mixed** | `test_result_has_y` | _drive | Trail, Var, _get_dispatch, deref, np |
| 334 | **mixed** | `test_with_args` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 344 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 353 | **mixed** | `test_uniform_1_2_3` | _drive | Trail, Var, _get_dispatch, deref |
| 361 | **mixed** | `test_with_x` | _drive | Trail, Var, _get_dispatch, deref |
| 369 | **mixed** | `test_constant_function` | _drive | Trail, Var, _get_dispatch, deref |
| 377 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 385 | **mixed** | `test_uniform_1_2_3` | _drive | Trail, Var, _get_dispatch, deref |
| 392 | **mixed** | `test_with_x` | _drive | Trail, Var, _get_dispatch, deref |
| 398 | **mixed** | `test_constant` | _drive | Trail, Var, _get_dispatch, deref |
| 405 | **mixed** | `test_single_interval` | _drive | Trail, Var, _get_dispatch, deref |
| 412 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 420 | **mixed** | `test_three_points_1_4_1` | _drive | Trail, Var, _get_dispatch, deref |
| 427 | **mixed** | `test_with_x` | _drive | Trail, Var, _get_dispatch, deref |
| 433 | **mixed** | `test_constant` | _drive | Trail, Var, _get_dispatch, deref |
| 440 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 448 | **mixed** | `test_get_existing_field` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 454 | **mixed** | `test_get_error_field` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 460 | **mixed** | `test_missing_field_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 466 | **mixed** | `test_wrong_result_type_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 471 | **infra** | `test_non_string_field_fails` |  | Trail, Var, _get_dispatch |
| 481 | **infra** | `test_bind_scalar_value` |  | Trail, _get_dispatch |
| 526 | **behavior**† | `test_fixture` | call |  |
| 542 | **behavior**† | `test_fixture` | call |  |
| 556 | **mixed** | `test_trapezoid_velocity_times_time` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 567 | **mixed** | `test_trapezoid_plain_fast_path` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 575 | **mixed** | `test_simpson_with_units` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 585 | **mixed** | `test_cumulative_trapezoid_with_units` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 596 | **mixed** | `test_trapezoid_y_only_with_units` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 609 | **mixed** | `test_quad_units_propagated` | _drive | Quantity, Trail, Var, _get_dispatch, deref |
| 625 | **mixed** | `test_quad_plain_function` | _drive | Quantity, Trail, Var, _get_dispatch, deref |
| 635 | **mixed** | `test_quad_no_units_fast_path` | _drive | Quantity, Trail, Var, _get_dispatch, deref |
| 644 | **mixed** | `test_quad_error_has_same_units` | _drive | Quantity, Trail, Var, _get_dispatch, deref |

</details>

<details><summary><code>tests/test_scipy_interpolate.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 83 | **mixed** | `test_returns_int_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 89 | **mixed** | `test_handle_in_registry` | _drive | Trail, Var, _get_dispatch, deref |
| 95 | **mixed** | `test_with_k` | _drive | Trail, Var, _get_dispatch, deref |
| 101 | **mixed** | `test_with_k_and_bc_type` | _drive | Trail, Var, _get_dispatch, deref |
| 107 | **mixed** | `test_wrong_result_fails` | _drive | Trail, Var, _get_dispatch, deref |
| 113 | **mixed** | `test_unique_handles` | _drive | Trail, Var, _get_dispatch, deref |
| 125 | **mixed** | `test_returns_int_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 131 | **mixed** | `test_with_bc_type` | _drive | Trail, Var, _get_dispatch, deref |
| 137 | **mixed** | `test_handle_in_registry` | _drive | Trail, Var, _get_dispatch, deref |
| 147 | **mixed** | `test_returns_int_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 153 | **mixed** | `test_with_extrapolate` | _drive | Trail, Var, _get_dispatch, deref |
| 163 | **mixed** | `test_returns_int_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 169 | **mixed** | `test_handle_in_registry` | _drive | Trail, Var, _get_dispatch, deref |
| 179 | **mixed** | `test_returns_int_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 187 | **mixed** | `test_with_kind` | _drive | Trail, Var, _get_dispatch, deref |
| 195 | **mixed** | `test_nearest_kind` | _drive | Trail, Var, _get_dispatch, deref |
| 210 | **mixed** | `test_returns_int_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 216 | **mixed** | `test_with_method` | _drive | Trail, Var, _get_dispatch, deref |
| 229 | **mixed** | `test_returns_int_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 235 | **mixed** | `test_with_kernel` | _drive | Trail, Var, _get_dispatch, deref |
| 241 | **mixed** | `test_with_kernel_and_smooth` | _drive | Trail, Var, _get_dispatch, deref |
| 251 | **mixed** | `test_eval_at_knots` | _drive | Trail, Var, _get_dispatch, deref, np |
| 259 | **mixed** | `test_eval_at_midpoint` | _drive | Trail, Var, _get_dispatch, deref, np |
| 268 | **mixed** | `test_eval_with_nu` | _drive | Trail, Var, _get_dispatch, deref, np |
| 277 | **mixed** | `test_pchip_eval_at_knots` | _drive | Trail, Var, _get_dispatch, deref, np |
| 285 | **mixed** | `test_akima_eval_at_knots` | _drive | Trail, Var, _get_dispatch, deref, np |
| 293 | **mixed** | `test_wrong_result_fails` | _drive | Trail, Var, _get_dispatch, deref |
| 299 | **mixed** | `test_invalid_handle_fails` | _drive | Trail, Var, _get_dispatch, deref |
| 311 | **mixed** | `test_eval_at_grid_points` | _drive | Trail, Var, _get_dispatch, deref, np |
| 320 | **mixed** | `test_eval_with_method` | _drive | Trail, Var, _get_dispatch, deref, np |
| 336 | **mixed** | `test_eval_at_known_points` | _drive | Trail, Var, _get_dispatch, deref, np |
| 344 | **mixed** | `test_invalid_handle_fails` | _drive | Trail, Var, _get_dispatch, deref |
| 353 | **mixed** | `test_integral_of_x_squared` | _drive | Trail, Var, _get_dispatch, deref, np |
| 364 | **mixed** | `test_integral_of_constant` | _drive | Trail, Var, _get_dispatch, deref, np |
| 375 | **mixed** | `test_invalid_handle_fails` | _drive | Trail, Var, _get_dispatch, deref |
| 384 | **mixed** | `test_returns_new_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 393 | **mixed** | `test_derivative_with_order` | _drive | Trail, Var, _get_dispatch, deref |
| 401 | **mixed** | `test_derivative_evaluates` | _drive | Trail, Var, _get_dispatch, deref, np |
| 414 | **mixed** | `test_invalid_handle_fails` | _drive | Trail, Var, _get_dispatch, deref |
| 423 | **mixed** | `test_linear_root_at_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 436 | **mixed** | `test_multiple_roots` | _drive | Trail, Var, _get_dispatch, deref, np |
| 451 | **mixed** | `test_invalid_handle_fails` | _drive | Trail, Var, _get_dispatch, deref |
| 460 | **mixed** | `test_removes_handle_from_registry` | _drive | Trail, Var, _get_dispatch, deref |
| 467 | **infra** | `test_free_nonexistent_succeeds` |  | Trail, _get_dispatch |
| 475 | **mixed** | `test_free_prevents_eval` | _drive | Trail, Var, _get_dispatch, deref |
| 486 | **unknown** | `test_alias_module_exports_all` |  |  |
| 541 | **behavior**† | `test_fixture` | call |  |
| 555 | **mixed** | `test_make_eval_spline_propagates_y_dims` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 569 | **mixed** | `test_make_eval_spline_plain_fast_path` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 580 | **mixed** | `test_spline_integral_has_y_times_x_dims` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 595 | **mixed** | `test_spline_derivative_handle_has_adjusted_dims` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 611 | **mixed** | `test_eval_spline_nu_dims` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |
| 623 | **mixed** | `test_make_cubic_with_units` | _drive | Quantity, Trail, Var, _get_dispatch, deref, np |

</details>

<details><summary><code>tests/test_scipy_linalg.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 121 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 126 | **mixed** | `test_known_solution` | _drive | Trail, Var, _get_dispatch, deref, np |
| 133 | **mixed** | `test_with_assume_a` | _drive | Trail, Var, _get_dispatch, deref, np |
| 139 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 147 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref, np |
| 154 | **mixed** | `test_x_field` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 162 | **mixed** | `test_rank_field` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 169 | **mixed** | `test_result_get_missing_field` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 176 | **mixed**† | `test_result_get_wrong_type` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 185 | **mixed** | `test_upper` | _drive | Trail, Var, _get_dispatch, deref, np |
| 192 | **mixed** | `test_lower` | _drive | Trail, Var, _get_dispatch, deref, np |
| 199 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 209 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref, np |
| 215 | **mixed** | `test_plu_reconstruct` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 223 | **mixed** | `test_result_get_p` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 233 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref, np |
| 239 | **mixed** | `test_qr_reconstruct` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 246 | **mixed** | `test_q_orthogonal` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 256 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref, np |
| 262 | **mixed** | `test_reconstruct` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 270 | **mixed** | `test_singular_values_positive` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 280 | **mixed** | `test_upper_default` | _drive | Trail, Var, _get_dispatch, deref, np |
| 286 | **mixed** | `test_lower_explicit` | _drive | Trail, Var, _get_dispatch, deref, np |
| 292 | **mixed** | `test_reconstruct_upper` | _drive | Trail, Var, _get_dispatch, deref, np |
| 301 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref, np |
| 307 | **mixed** | `test_eigenvalue_count` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 313 | **mixed** | `test_eigenvector_shape` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 319 | **mixed** | `test_av_equals_lv` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 334 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref, np |
| 340 | **mixed** | `test_eigenvalues_real_positive` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 346 | **mixed** | `test_eigenvectors_orthonormal` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 356 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref, np |
| 362 | **mixed** | `test_schur_reconstruct` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 369 | **mixed** | `test_complex_output` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 379 | **mixed** | `test_inverse` | _drive | Trail, Var, _get_dispatch, deref, np |
| 384 | **mixed** | `test_identity_inverse` | _drive | Trail, Var, _get_dispatch, deref, np |
| 390 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 398 | **mixed** | `test_square` | _drive | Trail, Var, _get_dispatch, deref, np |
| 404 | **mixed** | `test_rect` | _drive | Trail, Var, _get_dispatch, deref, np |
| 414 | **mixed** | `test_identity` | _drive | Trail, Var, _get_dispatch, deref, np |
| 419 | **mixed** | `test_known_det` | _drive | Trail, Var, _get_dispatch, deref, np |
| 425 | **mixed** | `test_singular_det` | _drive | Trail, Var, _get_dispatch, deref, np |
| 435 | **mixed** | `test_vector_norm` | _drive | Trail, Var, _get_dispatch, deref, np |
| 441 | **mixed** | `test_frobenius_norm` | _drive | Trail, Var, _get_dispatch, deref, np |
| 447 | **mixed** | `test_norm_with_ord` | _drive | Trail, Var, _get_dispatch, deref, np |
| 453 | **mixed** | `test_inf_norm` | _drive | Trail, Var, _get_dispatch, deref, np |
| 463 | **mixed** | `test_zero_matrix` | _drive | Trail, Var, _get_dispatch, deref, np |
| 470 | **mixed** | `test_diagonal` | _drive | Trail, Var, _get_dispatch, deref, np |
| 481 | **infra** | `test_identity` |  | Trail, Var, _get_dispatch, deref, np |
| 487 | **mixed** | `test_expm_logm_roundtrip` | _drive | Trail, Var, _get_dispatch, deref, np |
| 497 | **mixed** | `test_identity` | _drive | Trail, Var, _get_dispatch, deref, np |
| 502 | **mixed** | `test_sqrtm_squared` | _drive | Trail, Var, _get_dispatch, deref, np |
| 511 | **mixed** | `test_exp_via_matrix_function` | _drive | Trail, Var, _get_dispatch, deref, np |
| 517 | **mixed** | `test_identity_fn` | _drive | Trail, Var, _get_dispatch, deref, np |
| 527 | **mixed** | `test_factor_then_solve` | _drive | Trail, Var, _get_dispatch, deref, np |
| 535 | **mixed** | `test_reuse_factorisation` | _drive | Trail, Var, _get_dispatch, deref, np |
| 549 | **mixed** | `test_factor_then_solve` | _drive | Trail, Var, _get_dispatch, deref, np |
| 557 | **mixed** | `test_reuse_factorisation` | _drive | Trail, Var, _get_dispatch, deref, np |
| 571 | **mixed** | `test_basic_extraction` | _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 577 | **mixed** | `test_missing_field_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 583 | **mixed** | `test_not_a_dict_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 588 | **infra**† | `test_non_string_field_fails` |  | Trail, Var, _get_dispatch |
| 598 | **infra**† | `test_bind_existing_scalar_result` |  | Trail, _get_dispatch |

</details>

<details><summary><code>tests/test_scipy_ndimage.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 66 | **mixed** | `test_constant_array_unchanged` | _drive | Trail, Var, _get_dispatch, deref, np |
| 74 | **mixed** | `test_output_same_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 81 | **mixed** | `test_smoothing_reduces_peak` | _drive | Trail, Var, _get_dispatch, deref, np |
| 90 | **mixed** | `test_2d_constant_array` | _drive | Trail, Var, _get_dispatch, deref, np |
| 99 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 108 | **mixed** | `test_constant_array_unchanged` | _drive | Trail, Var, _get_dispatch, deref, np |
| 115 | **mixed** | `test_default_size_three` | _drive | Trail, Var, _get_dispatch, deref, np |
| 125 | **mixed** | `test_with_explicit_size` | _drive | Trail, Var, _get_dispatch, deref, np |
| 132 | **mixed** | `test_output_same_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 139 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 148 | **mixed** | `test_constant_array_unchanged` | _drive | Trail, Var, _get_dispatch, deref, np |
| 155 | **mixed** | `test_removes_spike` | _drive | Trail, Var, _get_dispatch, deref, np |
| 163 | **mixed** | `test_output_same_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 170 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 179 | **mixed** | `test_identity_kernel` | _drive | Trail, Var, _get_dispatch, deref, np |
| 188 | **mixed** | `test_box_kernel_averages` | _drive | Trail, Var, _get_dispatch, deref, np |
| 197 | **mixed** | `test_2d_identity_kernel` | _drive | Trail, Var, _get_dispatch, deref, np |
| 207 | **mixed** | `test_output_same_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 215 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 225 | **mixed** | `test_single_region` | _drive | Trail, Var, _get_dispatch, deref, np |
| 232 | **mixed** | `test_two_regions` | _drive | Trail, Var, _get_dispatch, deref, np |
| 239 | **mixed** | `test_label_array_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 246 | **mixed** | `test_label_array_background_is_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 253 | **mixed** | `test_no_features_when_all_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 260 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 269 | **mixed** | `test_solid_block_erodes` | _drive | Trail, Var, _get_dispatch, deref, np |
| 278 | **mixed** | `test_isolated_pixel_eroded_away` | _drive | Trail, Var, _get_dispatch, deref, np |
| 286 | **mixed** | `test_output_same_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 293 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 302 | **mixed** | `test_single_pixel_dilates` | _drive | Trail, Var, _get_dispatch, deref, np |
| 311 | **mixed** | `test_all_false_stays_false` | _drive | Trail, Var, _get_dispatch, deref, np |
| 318 | **mixed** | `test_output_same_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 325 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 334 | **mixed** | `test_removes_isolated_pixel` | _drive | Trail, Var, _get_dispatch, deref, np |
| 342 | **mixed** | `test_preserves_solid_region` | _drive | Trail, Var, _get_dispatch, deref, np |
| 350 | **mixed** | `test_output_same_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 357 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 366 | **mixed** | `test_fills_single_gap` | _drive | Trail, Var, _get_dispatch, deref, np |
| 374 | **mixed** | `test_solid_interior_preserved` | _drive | Trail, Var, _get_dispatch, deref, np |
| 382 | **mixed** | `test_output_same_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 389 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 398 | **mixed** | `test_zoom_doubles_length` | _drive | Trail, Var, _get_dispatch, deref, np |
| 405 | **mixed** | `test_zoom_halves_length` | _drive | Trail, Var, _get_dispatch, deref, np |
| 412 | **mixed** | `test_zoom_1_returns_same_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 419 | **mixed** | `test_zoom_2d_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 426 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 435 | **mixed** | `test_zero_rotation_preserves_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 442 | **mixed** | `test_360_rotation_round_trip` | _drive | Trail, Var, _get_dispatch, deref, np |
| 449 | **mixed** | `test_90_rotation_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 457 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 466 | **mixed** | `test_zero_shift_identity` | _drive | Trail, Var, _get_dispatch, deref, np |
| 473 | **mixed** | `test_shift_right_by_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 482 | **mixed** | `test_2d_zero_shift` | _drive | Trail, Var, _get_dispatch, deref, np |
| 489 | **mixed** | `test_output_same_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 496 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 505 | **mixed** | `test_two_regions_two_entries` | _drive | Trail, Var, _get_dispatch, deref, np |
| 513 | **mixed** | `test_single_region` | _drive | Trail, Var, _get_dispatch, deref, np |
| 520 | **mixed** | `test_empty_returns_empty_list` | _drive | Trail, Var, _get_dispatch, deref, np |
| 527 | **mixed** | `test_each_entry_is_tuple_of_slices` | _drive | Trail, Var, _get_dispatch, deref, np |
| 536 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 545 | **mixed** | `test_uniform_1d_centre` | _drive | Trail, Var, _get_dispatch, deref, np |
| 553 | **mixed** | `test_uniform_2d_centre` | _drive | Trail, Var, _get_dispatch, deref, np |
| 561 | **mixed** | `test_asymmetric_1d` | _drive | Trail, Var, _get_dispatch, deref, np |
| 569 | **mixed** | `test_single_peak` | _drive | Trail, Var, _get_dispatch, deref, np |
| 576 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 626 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_scipy_optimize.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 74 | **mixed** | `test_brent_quadratic` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 81 | **mixed** | `test_with_method` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 88 | **mixed** | `test_bounded` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 95 | **mixed** | `test_result_has_success` | _drive | Trail, Var, _get_dispatch, deref |
| 101 | **mixed** | `test_result_get_x` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 108 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 116 | **mixed** | `test_bfgs_quadratic` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 123 | **mixed** | `test_with_method_nelder_mead` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 130 | **mixed** | `test_result_success` | _drive | Trail, Var, _get_dispatch, deref, np |
| 136 | **mixed** | `test_result_get_x` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 143 | **mixed** | `test_result_get_fun` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 150 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 158 | **mixed** | `test_simple` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 165 | **mixed** | `test_with_seed` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 176 | **mixed** | `test_simple` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 183 | **mixed** | `test_with_niter` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 194 | **mixed** | `test_simple` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 201 | **mixed** | `test_with_seed` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 212 | **mixed** | `test_simple` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 223 | **mixed** | `test_simple` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 230 | **mixed** | `test_with_bounds` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 244 | **mixed** | `test_linear_fit` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 253 | **mixed** | `test_with_p0` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 262 | **mixed** | `test_result_has_popt_pcov` | _drive | Trail, Var, _get_dispatch, deref, np |
| 275 | **mixed** | `test_bisect` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 282 | **mixed** | `test_brentq` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 289 | **mixed** | `test_secant` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 296 | **mixed** | `test_result_converged` | _drive | Trail, Var, _get_dispatch, deref |
| 302 | **mixed** | `test_result_get_root` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 313 | **mixed** | `test_simple_system` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 320 | **mixed** | `test_with_method` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 327 | **mixed** | `test_result_success` | _drive | Trail, Var, _get_dispatch, deref, np |
| 333 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 341 | **mixed** | `test_simple_1d` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 349 | **mixed** | `test_2d` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 360 | **mixed** | `test_with_equality` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 373 | **mixed** | `test_result_success` | _drive | Trail, Var, _get_dispatch, deref, np |
| 379 | **mixed** | `test_result_get_x` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 385 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch, np |
| 393 | **mixed** | `test_simple` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 409 | **mixed** | `test_creates_object` | _drive | Trail, Var, _get_dispatch, deref, np |
| 419 | **mixed** | `test_creates_object` | _drive | Trail, Var, _get_dispatch, deref, np |
| 429 | **mixed** | `test_get_existing_field` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 435 | **mixed** | `test_missing_field_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 441 | **mixed**† | `test_wrong_result_type_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 446 | **infra**† | `test_non_string_field_fails` |  | Trail, Var, _get_dispatch |
| 456 | **infra**† | `test_bind_existing_scalar_result` |  | Trail, _get_dispatch |
| 506 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_scipy_signal.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 92 | **mixed** | `test_default_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 98 | **mixed** | `test_ba_coefficients_are_arrays` | _drive | Trail, Var, _get_dispatch, deref |
| 104 | **mixed** | `test_with_btype_high` | _drive | Trail, Var, _get_dispatch, deref |
| 110 | **mixed** | `test_with_output_sos` | _drive | Trail, Var, _get_dispatch, deref |
| 117 | **mixed** | `test_with_output_zpk` | _drive | Trail, Var, _get_dispatch, deref |
| 123 | **mixed** | `test_with_fs` | _drive | Trail, Var, _get_dispatch, deref |
| 129 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 133 | **mixed** | `test_result_get_b` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 139 | **mixed** | `test_result_get_sos` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 150 | **mixed** | `test_default_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 156 | **mixed** | `test_with_btype` | _drive | Trail, Var, _get_dispatch, deref |
| 161 | **mixed** | `test_with_output_sos` | _drive | Trail, Var, _get_dispatch, deref |
| 167 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 175 | **mixed** | `test_default_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 181 | **mixed** | `test_with_btype` | _drive | Trail, Var, _get_dispatch, deref |
| 186 | **mixed** | `test_with_output_sos` | _drive | Trail, Var, _get_dispatch, deref |
| 192 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 200 | **mixed** | `test_default_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 206 | **mixed** | `test_with_btype` | _drive | Trail, Var, _get_dispatch, deref |
| 211 | **mixed** | `test_with_output_sos` | _drive | Trail, Var, _get_dispatch, deref |
| 217 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 225 | **mixed** | `test_default_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 231 | **mixed** | `test_with_btype` | _drive | Trail, Var, _get_dispatch, deref |
| 236 | **mixed** | `test_with_output_sos` | _drive | Trail, Var, _get_dispatch, deref |
| 242 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 254 | **mixed** | `test_returns_w_h` | _drive | Trail, Var, _get_dispatch, deref |
| 261 | **mixed** | `test_w_length_default` | _drive | Trail, Var, _get_dispatch, deref |
| 267 | **mixed** | `test_with_nfreqs` | _drive | Trail, Var, _get_dispatch, deref |
| 273 | **mixed** | `test_h_is_complex` | _drive | Trail, Var, _get_dispatch, deref, np |
| 279 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 292 | **mixed** | `test_filters_signal` | _drive | Trail, Var, _get_dispatch, deref, np |
| 299 | **mixed** | `test_with_axis` | _drive | Trail, Var, _get_dispatch, deref, np |
| 305 | **mixed** | `test_with_zi_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 314 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 327 | **mixed** | `test_filters_signal` | _drive | Trail, Var, _get_dispatch, deref, np |
| 334 | **mixed** | `test_with_axis` | _drive | Trail, Var, _get_dispatch, deref, np |
| 340 | **mixed** | `test_with_zi_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 349 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 362 | **mixed** | `test_zero_phase_filtering` | _drive | Trail, Var, _get_dispatch, deref, np |
| 369 | **mixed** | `test_with_axis` | _drive | Trail, Var, _get_dispatch, deref, np |
| 375 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 380 | **mixed** | `test_differs_from_linear_filter` | _drive | Trail, Var, _get_dispatch, deref, np |
| 396 | **mixed** | `test_zero_phase_filtering` | _drive | Trail, Var, _get_dispatch, deref, np |
| 403 | **mixed** | `test_with_axis` | _drive | Trail, Var, _get_dispatch, deref, np |
| 409 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 414 | **mixed** | `test_pipeline_design_and_filter` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 428 | **mixed** | `test_decimates_signal` | _drive | Trail, Var, _get_dispatch, deref, np |
| 434 | **mixed** | `test_with_axis` | _drive | Trail, Var, _get_dispatch, deref, np |
| 439 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 447 | **mixed** | `test_resamples_signal` | _drive | Trail, Var, _get_dispatch, deref, np |
| 454 | **mixed** | `test_with_axis` | _drive | Trail, Var, _get_dispatch, deref, np |
| 461 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 472 | **mixed** | `test_full_convolution` | _drive | Trail, Var, _get_dispatch, deref, np |
| 478 | **mixed** | `test_with_mode_same` | _drive | Trail, Var, _get_dispatch, deref, np |
| 484 | **mixed** | `test_with_mode_valid` | _drive | Trail, Var, _get_dispatch, deref, np |
| 489 | **mixed** | `test_with_method_direct` | _drive | Trail, Var, _get_dispatch, deref, np |
| 494 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 498 | **mixed** | `test_known_result` | _drive | Trail, Var, _get_dispatch, deref, np |
| 512 | **mixed** | `test_full_correlation` | _drive | Trail, Var, _get_dispatch, deref, np |
| 518 | **mixed** | `test_with_mode` | _drive | Trail, Var, _get_dispatch, deref, np |
| 523 | **mixed** | `test_with_method` | _drive | Trail, Var, _get_dispatch, deref, np |
| 528 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 539 | **mixed** | `test_full_convolution` | _drive | Trail, Var, _get_dispatch, deref, np |
| 545 | **mixed** | `test_with_mode` | _drive | Trail, Var, _get_dispatch, deref, np |
| 550 | **mixed** | `test_matches_direct_convolve` | _drive | Trail, Var, _get_dispatch, deref, np |
| 557 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 565 | **mixed** | `test_returns_f_pxx` | _drive | Trail, Var, _get_dispatch, deref |
| 571 | **mixed** | `test_default_fs` | _drive | Trail, Var, _get_dispatch, deref |
| 577 | **mixed** | `test_with_fs` | _drive | Trail, Var, _get_dispatch, deref |
| 582 | **mixed** | `test_pxx_nonnegative` | _drive | Trail, Var, _get_dispatch, deref, np |
| 587 | **mixed** | `test_result_get_f` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 593 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 597 | **mixed** | `test_peak_at_50hz` | _drive | Trail, Var, _get_dispatch, deref, np |
| 609 | **mixed** | `test_returns_f_pxx` | _drive | Trail, Var, _get_dispatch, deref |
| 615 | **mixed** | `test_with_fs` | _drive | Trail, Var, _get_dispatch, deref |
| 620 | **mixed** | `test_pxx_nonnegative` | _drive | Trail, Var, _get_dispatch, deref, np |
| 625 | **mixed** | `test_result_get_pxx` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 631 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 635 | **mixed** | `test_smoother_than_periodogram` | _drive | Trail, Var, _get_dispatch, deref |
| 646 | **mixed** | `test_returns_f_t_sxx` | _drive | Trail, Var, _get_dispatch, deref |
| 652 | **mixed** | `test_with_fs` | _drive | Trail, Var, _get_dispatch, deref |
| 657 | **mixed** | `test_sxx_is_2d` | _drive | Trail, Var, _get_dispatch, deref |
| 662 | **mixed** | `test_sxx_nonnegative` | _drive | Trail, Var, _get_dispatch, deref, np |
| 667 | **mixed** | `test_result_get_sxx` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 673 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 681 | **mixed** | `test_extracts_field` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 687 | **mixed** | `test_missing_field_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 693 | **mixed**† | `test_non_dict_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 698 | **mixed** | `test_non_string_field_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 704 | **infra** | `test_unify_with_bound_correct` |  | Trail, _get_dispatch, np |
| 715 | **infra** | `test_unify_with_bound_wrong_fails` |  | Trail, _get_dispatch |
| 731 | **mixed** | `test_butterworth_ba_linear_filter` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 739 | **mixed** | `test_butterworth_sos_forward_backward` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 746 | **mixed** | `test_chebyshev_type1_sos_second_order_sections_filter` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 753 | **mixed** | `test_butterworth_highpass_attenuates_low_frequency` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref, np |
| 761 | **mixed** | `test_frequency_response_after_design` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 771 | **mixed** | `test_convolve_correlate_symmetry` | _drive | Trail, Var, _get_dispatch, deref, np |

</details>

<details><summary><code>tests/test_scipy_sparse.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 101 | **mixed** | `test_arity4_returns_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 107 | **mixed** | `test_arity5_with_shape` | _drive | Trail, Var, _get_dispatch, deref |
| 113 | **mixed** | `test_arity6_with_shape_dtype` | _drive | Trail, Var, _get_dispatch, deref |
| 119 | **mixed** | `test_handle_in_registry` | _drive | Trail, Var, _get_dispatch, deref |
| 126 | **mixed** | `test_registry_object_is_sparse` | _drive | Trail, Var, _get_dispatch, deref |
| 132 | **mixed** | `test_correct_nnz` | _drive | Trail, Var, _get_dispatch, deref |
| 144 | **mixed** | `test_arity4_returns_handle` | _drive | Trail, Var, _get_dispatch, deref, np |
| 154 | **mixed** | `test_arity5_with_shape` | _drive | Trail, Var, _get_dispatch, deref, np |
| 163 | **mixed** | `test_arity6_with_dtype` | _drive | Trail, Var, _get_dispatch, deref, np |
| 174 | **mixed** | `test_registry_object_is_sparse` | _drive | Trail, Var, _get_dispatch, deref, np |
| 189 | **mixed** | `test_arity4_returns_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 195 | **mixed** | `test_arity5_with_shape` | _drive | Trail, Var, _get_dispatch, deref |
| 201 | **mixed** | `test_registry_object_is_sparse` | _drive | Trail, Var, _get_dispatch, deref |
| 207 | **mixed** | `test_correct_nnz` | _drive | Trail, Var, _get_dispatch, deref |
| 213 | **mixed** | `test_todense_matches_expected` | _drive | Trail, Var, _get_dispatch, deref, np |
| 226 | **mixed** | `test_arity2_main_diagonal` | _drive | Trail, Var, _get_dispatch, deref |
| 234 | **mixed** | `test_arity3_with_offset` | _drive | Trail, Var, _get_dispatch, deref |
| 240 | **mixed** | `test_arity4_with_shape` | _drive | Trail, Var, _get_dispatch, deref |
| 246 | **mixed** | `test_diagonal_values_correct` | _drive | Trail, Var, _get_dispatch, deref, np |
| 253 | **mixed** | `test_superdiagonal` | _drive | Trail, Var, _get_dispatch, deref, np |
| 269 | **mixed** | `test_arity2_returns_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 275 | **mixed** | `test_arity3_rectangular` | _drive | Trail, Var, _get_dispatch, deref |
| 283 | **mixed** | `test_arity4_with_offset` | _drive | Trail, Var, _get_dispatch, deref |
| 289 | **mixed** | `test_identity_values` | _drive | Trail, Var, _get_dispatch, deref, np |
| 296 | **mixed** | `test_nnz_identity` | _drive | Trail, Var, _get_dispatch, deref |
| 315 | **mixed** | `test_arity2_returns_array` | _drive | Trail, Var, _get_dispatch, deref, np |
| 320 | **mixed** | `test_correct_shape` | _drive | Trail, Var, _get_dispatch, deref |
| 325 | **mixed** | `test_values_match` | _drive | Trail, Var, _get_dispatch, deref, np |
| 330 | **mixed** | `test_arity3_order_c` | _drive | Trail, Var, _get_dispatch, deref, np |
| 336 | **mixed** | `test_arity3_order_f` | _drive | Trail, Var, _get_dispatch, deref, np |
| 348 | **mixed** | `test_arity2_returns_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 354 | **mixed** | `test_registry_object_is_sparse` | _drive | Trail, Var, _get_dispatch, deref |
| 360 | **mixed** | `test_round_trip_todense` | _drive | Trail, Var, _get_dispatch, deref, np |
| 367 | **mixed** | `test_arity3_csc_format` | _drive | Trail, Var, _get_dispatch, deref |
| 375 | **mixed** | `test_arity3_csr_format` | _drive | Trail, Var, _get_dispatch, deref |
| 389 | **mixed** | `test_shape_3x3` | _drive | Trail, Var, _get_dispatch, deref |
| 396 | **mixed** | `test_shape_eye_4x4` | _drive | Trail, Var, _get_dispatch, deref |
| 403 | **mixed** | `test_shape_rectangular` | _drive | Trail, Var, _get_dispatch, deref |
| 416 | **mixed** | `test_nnz_csr_5_elements` | _drive | Trail, Var, _get_dispatch, deref |
| 423 | **mixed** | `test_nnz_eye_3` | _drive | Trail, Var, _get_dispatch, deref |
| 430 | **mixed** | `test_nnz_coo_matches` | _drive | Trail, Var, _get_dispatch, deref |
| 460 | **mixed** | `test_arity3_returns_array` | _drive | Trail, Var, _get_dispatch, deref, np |
| 465 | **mixed** | `test_arity3_correct_solution` | _drive | Trail, Var, _get_dispatch, deref, np |
| 470 | **mixed** | `test_arity4_with_permc_spec` | _drive | Trail, Var, _get_dispatch, deref, np |
| 475 | **mixed** | `test_arity5_with_use_umfpack` | _drive | Trail, Var, _get_dispatch, deref, np |
| 480 | **infra** | `test_invalid_handle_fails` |  | Trail, Var, _get_dispatch |
| 506 | **mixed** | `test_arity2_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 513 | **mixed** | `test_arity2_eigenvalues_count` | _drive | Trail, Var, _get_dispatch, deref |
| 519 | **mixed** | `test_arity3_k2` | _drive | Trail, Var, _get_dispatch, deref |
| 525 | **mixed** | `test_arity3_eigenvalues_are_real` | _drive | Trail, Var, _get_dispatch, deref, np |
| 531 | **infra** | `test_invalid_handle_fails` |  | Trail, Var, _get_dispatch |
| 556 | **mixed** | `test_arity2_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 564 | **mixed** | `test_arity3_k2` | _drive | Trail, Var, _get_dispatch, deref |
| 571 | **mixed** | `test_singular_values_positive` | _drive | Trail, Var, _get_dispatch, deref, np |
| 576 | **mixed** | `test_reconstruction` | _drive | Trail, Var, _get_dispatch, deref, np |
| 584 | **infra** | `test_invalid_handle_fails` |  | Trail, Var, _get_dispatch |
| 594 | **mixed** | `test_free_removes_from_registry` | _drive | Trail, Var, _get_dispatch, deref |
| 601 | **infra**† | `test_free_unknown_handle_succeeds` |  | Trail, _get_dispatch |
| 608 | **mixed** | `test_free_twice_succeeds` | _drive | Trail, Var, _get_dispatch, deref |
| 620 | **unknown** | `test_all_exports_present` |  |  |
| 632 | **unknown** | `test_shim_exports_match` |  |  |
| 641 | **unknown** | `test_registry_exported` |  |  |
| 697 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_scipy_spatial.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 94 | **mixed** | `test_shape_default_metric` | _drive | Trail, Var, _get_dispatch, deref, np |
| 101 | **mixed** | `test_euclidean_3_4_5` | _drive | Trail, Var, _get_dispatch, deref, np |
| 108 | **mixed** | `test_cityblock` | _drive | Trail, Var, _get_dispatch, deref, np |
| 115 | **mixed** | `test_with_kwargs` | _drive | Trail, Var, _get_dispatch, deref, np |
| 123 | **infra** | `test_unification_fails_wrong_value` |  | Trail, Var, _get_dispatch, np |
| 129 | **mixed** | `test_multiple_rows` | _drive | Trail, Var, _get_dispatch, deref, np |
| 142 | **mixed** | `test_length_3_points` | _drive | Trail, Var, _get_dispatch, deref |
| 147 | **mixed** | `test_euclidean_3_4_5` | _drive | Trail, Var, _get_dispatch, deref, np |
| 153 | **mixed** | `test_with_kwargs` | _drive | Trail, Var, _get_dispatch, deref |
| 158 | **mixed** | `test_single_pair` | _drive | Trail, Var, _get_dispatch, deref, np |
| 171 | **mixed** | `test_condensed_to_square` | _drive | Trail, Var, _get_dispatch, deref |
| 177 | **mixed** | `test_diagonal_is_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 183 | **mixed** | `test_symmetric` | _drive | Trail, Var, _get_dispatch, deref, np |
| 189 | **mixed** | `test_square_to_condensed` | _drive | Trail, Var, _get_dispatch, deref |
| 202 | **mixed** | `test_euclidean_3_4_5` | _drive | Trail, Var, _get_dispatch, deref |
| 207 | **mixed** | `test_cityblock` | _drive | Trail, Var, _get_dispatch, deref |
| 212 | **mixed** | `test_cosine_identical` | _drive | Trail, Var, _get_dispatch, deref |
| 217 | **mixed** | `test_returns_float` | _drive | Trail, Var, _get_dispatch, deref |
| 228 | **mixed** | `test_returns_int_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 234 | **mixed**† | `test_handle_in_registry` | _drive | Trail, Var, _get_dispatch, deref |
| 241 | **mixed** | `test_with_leafsize` | _drive | Trail, Var, _get_dispatch, deref |
| 247 | **mixed** | `test_registry_object_is_kdtree` | _drive | Trail, Var, _get_dispatch, deref |
| 265 | **mixed** | `test_nearest_returns_dict` | _drive | Trail, Var, _get_dispatch, deref, np |
| 273 | **mixed** | `test_nearest_index_correct` | _drive | Trail, Var, _get_dispatch, deref, np |
| 279 | **mixed** | `test_query_k_2` | _drive | Trail, Var, _get_dispatch, deref, np |
| 286 | **mixed** | `test_nearest_distance_zero_for_exact` | _drive | Trail, Var, _get_dispatch, deref, np |
| 304 | **mixed** | `test_returns_list` | _drive | Trail, Var, _get_dispatch, deref |
| 309 | **mixed** | `test_small_radius_finds_origin` | _drive | Trail, Var, _get_dispatch, deref |
| 315 | **mixed** | `test_large_radius_finds_all` | _drive | Trail, Var, _get_dispatch, deref |
| 332 | **mixed** | `test_returns_set` | _drive | Trail, Var, _get_dispatch, deref |
| 337 | **mixed** | `test_large_radius_all_pairs` | _drive | Trail, Var, _get_dispatch, deref |
| 342 | **mixed** | `test_small_radius_no_pairs` | _drive | Trail, Var, _get_dispatch, deref |
| 353 | **mixed** | `test_returns_int_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 359 | **mixed** | `test_registry_object_is_convex_hull` | _drive | Trail, Var, _get_dispatch, deref |
| 377 | **mixed** | `test_vertices_is_array` | _drive | Trail, Var, _get_dispatch, deref |
| 382 | **mixed** | `test_area_unit_square` | _drive | Trail, Var, _get_dispatch, deref |
| 388 | **mixed** | `test_volume_unit_square` | _drive | Trail, Var, _get_dispatch, deref |
| 394 | **mixed** | `test_simplices_shape` | _drive | Trail, Var, _get_dispatch, deref |
| 399 | **mixed** | `test_equations_shape` | _drive | Trail, Var, _get_dispatch, deref |
| 411 | **mixed** | `test_returns_int_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 417 | **mixed** | `test_registry_object_is_delaunay` | _drive | Trail, Var, _get_dispatch, deref |
| 435 | **mixed** | `test_interior_point_nonnegative` | _drive | Trail, Var, _get_dispatch, deref, np |
| 441 | **mixed** | `test_exterior_point_minus_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 447 | **mixed** | `test_with_bruteforce` | _drive | Trail, Var, _get_dispatch, deref, np |
| 459 | **mixed** | `test_from_rotvec_identity` | _drive | Trail, Var, _get_dispatch, deref |
| 465 | **mixed** | `test_from_quat` | _drive | Trail, Var, _get_dispatch, deref |
| 471 | **mixed** | `test_from_matrix` | _drive | Trail, Var, _get_dispatch, deref, np |
| 477 | **mixed** | `test_from_euler` | _drive | Trail, Var, _get_dispatch, deref |
| 483 | **mixed** | `test_registry_object_is_rotation` | _drive | Trail, Var, _get_dispatch, deref |
| 489 | **mixed** | `test_unknown_method_fails` | _drive | Trail, Var, _get_dispatch, deref |
| 500 | **mixed** | `test_identity_preserves_vector` | _drive | Trail, Var, _get_dispatch, deref, np |
| 508 | **mixed** | `test_90_degree_z_rotation` | _drive | Trail, Var, _get_dispatch, deref, np |
| 516 | **mixed** | `test_with_inverse` | _drive | Trail, Var, _get_dispatch, deref, np |
| 536 | **mixed** | `test_as_quat_length` | _drive | Trail, Var, _get_dispatch, deref |
| 541 | **mixed** | `test_as_matrix_shape` | _drive | Trail, Var, _get_dispatch, deref |
| 546 | **mixed** | `test_as_rotvec_length` | _drive | Trail, Var, _get_dispatch, deref |
| 551 | **mixed** | `test_as_euler_xyz` | _drive | Trail, Var, _get_dispatch, deref |
| 558 | **mixed** | `test_as_euler_wrong_form_fails` | _drive | Trail, Var, _get_dispatch, deref |
| 569 | **mixed** | `test_compose_two_90_degrees` | _drive | Trail, Var, _get_dispatch, deref, np |
| 579 | **mixed** | `test_returns_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 593 | **mixed** | `test_inverse_of_identity_is_identity` | _drive | Trail, Var, _get_dispatch, deref, np |
| 602 | **mixed** | `test_inverse_undoes_rotation` | _drive | Trail, Var, _get_dispatch, deref, np |
| 611 | **mixed** | `test_returns_handle` | _drive | Trail, Var, _get_dispatch, deref |
| 624 | **mixed**† | `test_free_removes_from_registry` | _drive | Trail, Var, _get_dispatch, deref |
| 631 | **infra**† | `test_free_unknown_handle_succeeds` |  | Trail, _get_dispatch |
| 639 | **mixed** | `test_free_twice_succeeds` | _drive | Trail, Var, _get_dispatch, deref |
| 651 | **unknown** | `test_all_exports_present` |  |  |
| 665 | **unknown** | `test_shim_exports_match` |  |  |
| 731 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_scipy_special.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 80 | **mixed** | `test_positive_integer` | _drive | Trail, Var, _get_dispatch, deref, np |
| 85 | **mixed** | `test_half` | _drive | Trail, Var, _get_dispatch, deref, np |
| 90 | **infra** | `test_unification_fails_wrong_value` |  | Trail, _get_dispatch |
| 100 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 107 | **mixed** | `test_positive` | _drive | Trail, Var, _get_dispatch, deref |
| 112 | **mixed** | `test_negative` | _drive | Trail, Var, _get_dispatch, deref |
| 119 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 126 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 133 | **mixed** | `test_order_0_is_digamma` | _drive | Trail, Var, _get_dispatch, deref, np |
| 138 | **mixed** | `test_order_1` | _drive | Trail, Var, _get_dispatch, deref, np |
| 145 | **mixed** | `test_arity2_exact_false` | _drive | Trail, Var, _get_dispatch, deref, np |
| 150 | **mixed** | `test_arity3_exact_true` | _drive | Trail, Var, _get_dispatch, deref |
| 155 | **mixed** | `test_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 162 | **mixed** | `test_arity3` | _drive | Trail, Var, _get_dispatch, deref, np |
| 167 | **mixed** | `test_arity4_exact` | _drive | Trail, Var, _get_dispatch, deref |
| 172 | **mixed** | `test_arity5_repetition` | _drive | Trail, Var, _get_dispatch, deref, np |
| 179 | **mixed** | `test_arity3` | _drive | Trail, Var, _get_dispatch, deref, np |
| 184 | **mixed** | `test_arity4_exact` | _drive | Trail, Var, _get_dispatch, deref |
| 193 | **mixed** | `test_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 198 | **mixed** | `test_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 205 | **mixed** | `test_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 210 | **mixed** | `test_sums_to_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 218 | **mixed** | `test_round_trip` | _drive | Trail, Var, _get_dispatch, deref, np |
| 228 | **infra** | `test_basic` |  | Trail, Var, _get_dispatch, deref, np |
| 236 | **mixed** | `test_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 241 | **mixed** | `test_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 248 | **infra** | `test_half` |  | Trail, Var, _get_dispatch, deref, np |
| 254 | **mixed** | `test_round_trip` | _drive | Trail, Var, _get_dispatch, deref, np |
| 265 | **mixed** | `test_order0` | _drive | Trail, Var, _get_dispatch, deref, np |
| 270 | **mixed** | `test_order1` | _drive | Trail, Var, _get_dispatch, deref, np |
| 277 | **mixed** | `test_order0` | _drive | Trail, Var, _get_dispatch, deref, np |
| 284 | **mixed** | `test_half_order` | _drive | Trail, Var, _get_dispatch, deref, np |
| 291 | **mixed** | `test_half_order` | _drive | Trail, Var, _get_dispatch, deref, np |
| 298 | **mixed** | `test_order0` | _drive | Trail, Var, _get_dispatch, deref, np |
| 305 | **mixed** | `test_order0` | _drive | Trail, Var, _get_dispatch, deref, np |
| 312 | **mixed** | `test_first_five_zeros_of_j0` | _drive | Trail, Var, _get_dispatch, deref, np |
| 320 | **mixed** | `test_arity3_no_derivative` | _drive | Trail, Var, _get_dispatch, deref, np |
| 325 | **mixed** | `test_arity4_with_derivative` | _drive | Trail, Var, _get_dispatch, deref, np |
| 334 | **mixed** | `test_zero_modulus` | _drive | Trail, Var, _get_dispatch, deref, np |
| 341 | **mixed** | `test_zero_modulus` | _drive | Trail, Var, _get_dispatch, deref, np |
| 348 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 355 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 364 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 371 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 378 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 387 | **mixed** | `test_half` | _drive | Trail, Var, _get_dispatch, deref, np |
| 392 | **mixed** | `test_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 399 | **mixed** | `test_equal_inputs` | _drive | Trail, Var, _get_dispatch, deref, np |
| 404 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 411 | **mixed** | `test_arity2` | _drive | Trail, Var, _get_dispatch, deref, np |
| 417 | **mixed** | `test_arity5_with_axis` | _drive | Trail, Var, _get_dispatch, deref, np |
| 428 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 435 | **mixed** | `test_p0_is_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 440 | **mixed** | `test_p1_is_x` | _drive | Trail, Var, _get_dispatch, deref, np |
| 445 | **mixed** | `test_p2` | _drive | Trail, Var, _get_dispatch, deref, np |
| 452 | **mixed** | `test_t0_is_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 457 | **mixed** | `test_t1_is_x` | _drive | Trail, Var, _get_dispatch, deref, np |
| 464 | **mixed** | `test_u0_is_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 471 | **mixed** | `test_h0_is_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 476 | **mixed** | `test_h1_is_2x` | _drive | Trail, Var, _get_dispatch, deref, np |
| 483 | **mixed** | `test_l0_is_one` | _drive | Trail, Var, _get_dispatch, deref, np |
| 492 | **mixed** | `test_eight` | _drive | Trail, Var, _get_dispatch, deref, np |
| 497 | **mixed** | `test_negative` | _drive | Trail, Var, _get_dispatch, deref, np |
| 504 | **mixed** | `test_two` | _drive | Trail, Var, _get_dispatch, deref, np |
| 511 | **mixed** | `test_three` | _drive | Trail, Var, _get_dispatch, deref, np |
| 518 | **infra** | `test_zero_input` |  | Trail, Var, _get_dispatch, deref, np |
| 524 | **infra** | `test_large_input` |  | Trail, Var, _get_dispatch, deref, np |
| 530 | **mixed** | `test_round_trip_with_logit` | _drive | Trail, Var, _get_dispatch, deref, np |
| 540 | **mixed** | `test_half` | _drive | Trail, Var, _get_dispatch, deref, np |
| 547 | **mixed** | `test_arity2` | _drive | Trail, Var, _get_dispatch, deref, np |
| 553 | **mixed** | `test_arity4_k0` | _drive | Trail, Var, _get_dispatch, deref, np |
| 559 | **mixed** | `test_arity4_k_minus1` | _drive | Trail, Var, _get_dispatch, deref, np |
| 567 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 572 | **mixed** | `test_zero_x_gives_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 579 | **mixed** | `test_basic` | _drive | Trail, Var, _get_dispatch, deref, np |
| 584 | **mixed** | `test_zero_x_gives_zero` | _drive | Trail, Var, _get_dispatch, deref, np |
| 593 | **unknown** | `test_repr` |  |  |
| 597 | **infra** | `test_get_dispatch_callable` |  | _get_dispatch |
| 601 | **infra** | `test_multi_arity_dispatch_is_callable` |  | _get_dispatch |
| 605 | **infra** | `test_unknown_arity_fails` |  | Trail, Var, _get_dispatch |
| 747 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_scipy_stats.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 87 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 92 | **mixed** | `test_nobs` | _drive | Trail, Var, _get_dispatch, deref |
| 97 | **mixed** | `test_mean_approx` | _drive | Trail, Var, _get_dispatch, deref, np |
| 102 | **mixed** | `test_minmax` | _drive | Trail, Var, _get_dispatch, deref |
| 108 | **mixed** | `test_has_all_keys` | _drive | Trail, Var, _get_dispatch, deref |
| 118 | **mixed** | `test_simple` | _drive | Trail, Var, _get_dispatch, deref |
| 123 | **mixed** | `test_float_result` | _drive | Trail, Var, _get_dispatch, deref |
| 128 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 136 | **mixed** | `test_simple` | _drive | Trail, Var, _get_dispatch, deref |
| 142 | **mixed** | `test_float_result` | _drive | Trail, Var, _get_dispatch, deref |
| 151 | **mixed** | `test_simple` | _drive | Trail, Var, _get_dispatch, deref |
| 157 | **mixed** | `test_harmonic_two` | _drive | Trail, Var, _get_dispatch, deref |
| 167 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 174 | **mixed** | `test_mode_value` | _drive | Trail, Var, _get_dispatch, deref |
| 179 | **mixed** | `test_count_value` | _drive | Trail, Var, _get_dispatch, deref |
| 188 | **mixed** | `test_symmetric_near_zero` | _drive | Trail, Var, _get_dispatch, deref |
| 193 | **mixed** | `test_float_result` | _drive | Trail, Var, _get_dispatch, deref |
| 202 | **mixed** | `test_returns_float` | _drive | Trail, Var, _get_dispatch, deref |
| 211 | **mixed** | `test_simple` | _drive | Trail, Var, _get_dispatch, deref |
| 217 | **mixed** | `test_float_result` | _drive | Trail, Var, _get_dispatch, deref |
| 226 | **mixed** | `test_returns_list` | _drive | Trail, Var, _get_dispatch, deref |
| 232 | **mixed** | `test_mean_zero` | _drive | Trail, Var, _get_dispatch, deref |
| 241 | **mixed** | `test_returns_float` | _drive | Trail, Var, _get_dispatch, deref |
| 246 | **mixed** | `test_value` | _drive | Trail, Var, _get_dispatch, deref |
| 256 | **mixed** | `test_perfect_correlation` | _drive | Trail, Var, _get_dispatch, deref |
| 263 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 270 | **mixed** | `test_result_get_statistic` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 276 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 284 | **mixed** | `test_one_array` | _drive | Trail, Var, _get_dispatch, deref, np |
| 290 | **mixed** | `test_two_arrays` | _drive | Trail, Var, _get_dispatch, deref |
| 296 | **mixed** | `test_perfect_rank_correlation` | _drive | Trail, Var, _get_dispatch, deref |
| 306 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 313 | **mixed** | `test_perfect_agreement` | _drive | Trail, Var, _get_dispatch, deref |
| 323 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 328 | **mixed** | `test_slope_intercept` | _drive | Trail, Var, _get_dispatch, deref |
| 334 | **mixed** | `test_has_all_fields` | _drive | Trail, Var, _get_dispatch, deref |
| 340 | **mixed** | `test_result_get_slope` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 350 | **mixed** | `test_two_arg` | _drive | Trail, Var, _get_dispatch, deref |
| 355 | **mixed** | `test_three_arg` | _drive | Trail, Var, _get_dispatch, deref |
| 360 | **mixed** | `test_has_all_fields` | _drive | Trail, Var, _get_dispatch, deref |
| 370 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 377 | **mixed** | `test_same_mean_low_t` | _drive | Trail, Var, _get_dispatch, deref |
| 383 | **mixed** | `test_result_get_pvalue` | _drive, _drive_result_get | Trail, Var, _get_dispatch, deref |
| 393 | **mixed** | `test_two_arg` | _drive | Trail, Var, _get_dispatch, deref |
| 398 | **mixed** | `test_three_arg_equal_var` | _drive | Trail, Var, _get_dispatch, deref |
| 403 | **mixed** | `test_three_arg_unequal_var` | _drive | Trail, Var, _get_dispatch, deref |
| 412 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 422 | **mixed** | `test_one_arg` | _drive | Trail, Var, _get_dispatch, deref |
| 428 | **mixed** | `test_two_arg_with_expected` | _drive | Trail, Var, _get_dispatch, deref |
| 433 | **mixed** | `test_uniform_distribution` | _drive | Trail, Var, _get_dispatch, deref |
| 443 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 449 | **mixed** | `test_has_dof` | _drive | Trail, Var, _get_dispatch, deref |
| 456 | **mixed** | `test_has_expected_freq` | _drive | Trail, Var, _get_dispatch, deref |
| 466 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 474 | **mixed** | `test_pvalue_range` | _drive | Trail, Var, _get_dispatch, deref |
| 484 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 490 | **mixed** | `test_pvalue_range` | _drive | Trail, Var, _get_dispatch, deref |
| 499 | **mixed** | `test_one_sample` | _drive | Trail, Var, _get_dispatch, deref |
| 505 | **mixed** | `test_two_sample` | _drive | Trail, Var, _get_dispatch, deref |
| 514 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 520 | **mixed** | `test_three_groups` | _drive | Trail, Var, _get_dispatch, deref |
| 525 | **infra** | `test_wrong_result_fails` |  | Trail, _get_dispatch |
| 533 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 539 | **mixed** | `test_identical_samples_zero_stat` | _drive | Trail, Var, _get_dispatch, deref |
| 548 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref, np |
| 560 | **mixed** | `test_returns_dict` | _drive | Trail, Var, _get_dispatch, deref |
| 566 | **mixed** | `test_pvalue_range` | _drive | Trail, Var, _get_dispatch, deref |
| 575 | **infra** | `test_norm_pdf_at_zero` |  | Trail, Var, _get_dispatch, deref |
| 591 | **infra** | `test_norm_cdf_at_zero` |  | Trail, Var, _get_dispatch, deref |
| 605 | **infra** | `test_norm_entropy_no_x` |  | Trail, Var, _get_dispatch, deref |
| 626 | **mixed** | `test_at_zero` | _drive | Trail, Var, _get_dispatch, deref |
| 632 | **mixed** | `test_with_loc_scale` | _drive | Trail, Var, _get_dispatch, deref |
| 638 | **mixed** | `test_wrong_arity_returns_none` | _drive | Trail, Var, _get_dispatch, deref |
| 648 | **mixed** | `test_at_zero` | _drive | Trail, Var, _get_dispatch, deref |
| 653 | **mixed** | `test_with_loc_scale` | _drive | Trail, Var, _get_dispatch, deref |
| 663 | **mixed** | `test_median` | _drive | Trail, Var, _get_dispatch, deref |
| 668 | **mixed** | `test_with_loc_scale` | _drive | Trail, Var, _get_dispatch, deref |
| 678 | **infra** | `test_scalar_result` |  | Trail, Var, _get_dispatch, deref |
| 692 | **mixed** | `test_with_loc_scale` | _drive | Trail, Var, _get_dispatch, deref |
| 697 | **mixed** | `test_with_size` | _drive | Trail, Var, _get_dispatch, deref |
| 707 | **infra** | `test_returns_int_handle` |  | Trail, Var, _get_dispatch, deref |
| 723 | **infra** | `test_pdf_via_handle` |  | Trail, Var, _get_dispatch, deref |
| 753 | **infra** | `test_frozen_stats` |  | Trail, Var, _get_dispatch, deref |
| 780 | **infra** | `test_frozen_free_removes_handle` |  | Trail, Var, _get_dispatch, deref |
| 804 | **infra** | `test_frozen_cdf` |  | Trail, Var, _get_dispatch, deref |
| 830 | **infra** | `test_frozen_ppf` |  | Trail, Var, _get_dispatch, deref |
| 858 | **infra** | `test_frozen_rvs_scalar` |  | Trail, Var, _get_dispatch, deref |
| 884 | **infra** | `test_frozen_rvs_with_size` |  | Trail, Var, _get_dispatch, deref |
| 915 | **mixed** | `test_get_from_dict` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 921 | **mixed** | `test_missing_field_fails` | _drive_result_get | Trail, Var, _get_dispatch, deref |
| 927 | **infra**† | `test_non_string_field_fails` |  | Trail, Var, _get_dispatch |
| 937 | **infra** | `test_bind_existing_value` |  | Trail, _get_dispatch |
| 947 | **infra** | `test_wrong_value_fails` |  | Trail, _get_dispatch |
| 997 | **behavior**† | `test_fixture` | call |  |

</details>

<details><summary><code>tests/test_torch.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 112 | **behavior**† | `test_fixture` | call |  |
| 141 | **behavior**† | `test_fixture` | call |  |
| 179 | **behavior**† | `test_fixture` | call |  |
| 201 | **behavior**† | `test_fixture` | call |  |
| 257 | **behavior**† | `test_fixture` | call |  |
| 298 | **behavior**† | `test_fixture` | call |  |
| 348 | **behavior**† | `test_fixture` | call |  |
| 411 | **behavior**† | `test_fixture` | call |  |
| 465 | **behavior**† | `test_fixture` | call |  |
| 513 | **behavior**† | `test_fixture` | call |  |
| 575 | **behavior**† | `test_fixture` | call |  |
| 604 | **behavior**† | `test_fixture` | call |  |
| 627 | **mixed** | `test_current_lr` | call | Var, deref, torch |
| 640 | **mixed** | `test_clip_grad_norm` | call | Var, deref, torch |
| 655 | **mixed** | `test_clip_grad_value` | call | torch |
| 727 | **behavior**† | `test_fixture` | call |  |
| 740 | **unknown** | `test_lazy_import_loads_torch` |  |  |
| 746 | **unknown** | `test_exports_exist` |  |  |
| 753 | **unknown** | `test_pred_arities` |  |  |

</details>

<details><summary><code>tests/test_torch_coverage.py</code></summary>

| line | label | test | behavior-hits | infra-hits |
|---:|---|---|---|---|
| 190 | **unknown** | `test_category_coverage` |  |  |
| 199 | **unknown** | `test_report_full_coverage` |  |  |
| 215 | **unknown** | `test_no_unexpected_exports` |  |  |

</details>
