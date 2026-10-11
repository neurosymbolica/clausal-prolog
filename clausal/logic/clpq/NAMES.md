# Names: clp(q,r) 1.3.3 to full words

This table is `tools/clpq_reference/rename_map.tsv` as a table: every
unquoted atom in the clp(q,r) 1.3.3 sources (and in the Scryer copy used as
the runnable oracle), with the name the reading copy and the port use for it.
`File` lists the 1.3.3 files the atom occurs in; "Scryer copy only" marks an
atom that only the merged Scryer `clpq.pl` has.

`tools/clpq_reference/rename.py` applies the map and refuses one that is not
injective or that renames onto an atom already in the sources.
`tests/clpq_port/test_rename_preserves_answers.py` shows the renamed Scryer
copy gives the same example results as the original.

## Conventions

- A `q` suffix (`addq`, `getq`) is `_rational`; `Q`/`Qn`/`R` in the compiler
  names are `rational`, `rational_normalized`, `real`.
  Exception: the port's rational arithmetic is the module
  `clausal/logic/clpq/arithmetic.py` (deviation D1), and there the module name
  carries "rational", so the functions drop the suffix: `addq`, `subq`,
  `mulq`, `divq`, `comq`, `signumq`, `getq` and `putq` are
  `arithmetic.add`, `subtract`, `multiply`, `divide`, `compare`, `sign`,
  `from_number` and `make_rational`.  Their rows below give both names.  The
  reading copy (`rename_map.tsv`) keeps the `_rational` names: it has no
  module qualification, and `compare` (the built-in), `multiply` and `sign`
  are already atoms in the 1.3.3 sources.
- A `_log` suffix (`nf_mul_log`, `log_deref`) is the balanced
  divide-and-conquer form and becomes `_balanced`; `log` alone stays the
  logarithm.
- `nf` is `normal_form`, `lin` is `linear_form`, `hom` is `homogeneous`,
  `dep`/`indep` are `dependent`/`independent`, `class` is `component`.
- `l(L)`/`u(U)` (a violated bound in `bv.pl`) become `below_lower_bound`/
  `above_upper_bound`, because `lower/2` and `upper/2` already exist.
- `order` (the attribute) is `variable_order`, because `ordering/1` is the
  exported predicate.
- `v(K, Ps)` (a monomial in a normal form) is `monomial`.
- In a bound type (`t_l`, `t_L`, ...) a capital letter marks the ACTIVE
  bound (`bv.pl`: "t_l has a lower bound (not active yet)", "t_L has an
  active lower bound"), so `t_L` is `bounds_lower_active` and `t_lU` is
  `bounds_lower_upper_active`.  Strictness is not part of the bound type;
  it is the separate `strictness` attribute (bits 0b10 lower, 0b01 upper).
  `red_t_L`/`red_t_U`, the profiling markers `redundant/3` in `redund.pl`
  reaches after dropping a redundant active bound, follow the same reading.

## Rows that keep their name

- Built-ins, library predicates and library names (`get_atts`, `put_atts`,
  `illarg`, `must_be`, `bb_put`, `ugraphs`, `assoc3`, `msb`, `gcd`, ...).
- Hooks the host calls by name: `verify_attributes`, `attribute_goal`,
  `attribute_goals`, `project_attributes`, `goal_expansion`, `portray_message`.
- The exported API: `{}`, `maximize`, `minimize`, `inf`, `sup`, `bb_inf`,
  `ordering`, `entailed`, `dump`, `projecting_assert`.
- Atoms a user writes or sees: `rat` (the SICStus rational term), `numer`,
  `denom`, the `#/1` constants `p`, `pi`, `e`, `zero`, and `clpq`/`clpr`.
- File and module names (`arith`, `arith_q`, `bv`, `bb`, `itf3`, `nfq`,
  `classq`, `geler_q`, `fourmotz`, `redund`, ...).  The reading copy keeps
  the 1.3.3 file names, so these keep theirs too.  Two file names are
  also predicate or attribute names and are renamed with them: `nf`, `class`
  (`use_module`/`ensure_loaded` of those files in the reading copy name
  `normal_form`/`component`, which are not file names there).
- `geler` (French, "freeze") and `occurences` (sic) are words, not
  abbreviations.
- `imin` is declared public in `bv.pl` but never defined; its meaning is
  unknown, so it is not renamed.

Quoted atoms (`'solve_='`, `'divq_-11'`), comments and commented-out code
are not renamed.

## Table

| Old | New | File |
|---|---|---|
| `abs` | (same) | arith.pl, nf.pl |
| `acos` | (same) | arith.pl, nf.pl |
| `acosq` | `arc_cosine_rational` | arith.pl, arith_q.pl |
| `activate_crossproduct` | (same) | fourmotz.pl |
| `add_edges` | (same) | ordering.pl |
| `add_linear_11` | `add_linear_forms` | bv.pl, fourmotz.pl, ineq.pl, nf.pl, nfq.pl, store.pl |
| `add_linear_11h` | `add_homogeneous_parts` | store.pl |
| `add_linear_f1` | `add_linear_forms_first_scaled` | fourmotz.pl, store.pl |
| `add_linear_f1h` | `add_homogeneous_parts_first_scaled` | store.pl |
| `add_linear_ff` | `add_linear_forms_scaled` | bv.pl, ineq.pl, store.pl |
| `add_linear_ffh` | `add_homogeneous_parts_scaled` | store.pl |
| `add_vertices` | (same) | ordering.pl |
| `addq` | `add_rational` (port: `arithmetic.add`) | arith.pl, arith_q.pl |
| `all_attribute_goals` | (same) | dump.pl |
| `all_nonlin` | `all_nonlinear` | geler.pl |
| `allvars` | `all_variables` | bv.pl, fourmotz.pl |
| `append` | (same) | class.pl, ordering.pl |
| `applied` | (same) | bv.pl |
| `apply` | (same) | arith.pl |
| `arg` | (same) | arith.pl |
| `arith` | (same) | arith_q.pl, compenv.pl |
| `arith_eps` | `arithmetic_epsilon` | arith_q.pl, nf.pl |
| `arith_eval` | `evaluate_arithmetic` | arith_q.pl, bb.pl, bv.pl, fourmotz.pl, ineq.pl, itf3.pl, nf.pl, redund.pl, store.pl |
| `arith_module` | `arithmetic_module` | arith_q.pl |
| `arith_normalize` | `arithmetic_normalize` | arith_q.pl, itf3.pl, nf.pl, store.pl |
| `arith_q` | (same) | arith_q.pl, compenv.pl, nfq.pl |
| `arith_r` | (same) | compenv.pl |
| `arrange` | (same) | project.pl |
| `arrange_pivot` | (same) | project.pl |
| `arrangement` | (same) | class.pl, ordering.pl, project.pl |
| `asin` | (same) | arith.pl, nf.pl |
| `asinq` | `arc_sine_rational` | arith.pl, arith_q.pl |
| `assert` | (same) | dump.pl, itf3.pl |
| `assign` | (same) | bv.pl |
| `assoc` | (same) | Scryer copy only |
| `assoc3` | (same) | dump.pl |
| `assoc_to_list` | (same) | dump.pl |
| `atan` | (same) | arith.pl, nf.pl |
| `atanq` | `arc_tangent_rational` | arith.pl, arith_q.pl |
| `attach` | (same) | geler.pl |
| `attach_class` | `attach_component` | bv.pl |
| `attribute` | (same) | class.pl, geler.pl, itf3.pl |
| `attribute_goal` | (same) | geler.pl, itf3.pl |
| `attribute_goals` | (same) | Scryer copy only |
| `atts` | (same) | class.pl, geler.pl, itf3.pl |
| `backsubst` | `back_substitute` | bv.pl, ineq.pl |
| `backsubst_delta` | `back_substitute_delta` | bv.pl, ineq.pl |
| `basis` | (same) | bv.pl |
| `basis_add` | (same) | bv.pl, fourmotz.pl, ineq.pl |
| `basis_drop` | (same) | bv.pl |
| `basis_pivot` | (same) | bv.pl |
| `bb` | (same) | compenv.pl |
| `bb_better_bound` | `branch_and_bound_better_bound` | bb.pl |
| `bb_branch` | `branch_and_bound_branch` | bb.pl |
| `bb_delete` | (same) | bb.pl, bv.pl |
| `bb_first_nonint` | `branch_and_bound_first_non_integer` | bb.pl |
| `bb_get` | (same) | bb.pl |
| `bb_inf` | (same) | bb.pl |
| `bb_inf_internal` | `branch_and_bound_infimum_internal` | bb.pl |
| `bb_intern` | `branch_and_bound_intern` | bb.pl |
| `bb_loop` | `branch_and_bound_loop` | bb.pl |
| `bb_narrow_lower` | `branch_and_bound_narrow_lower` | bb.pl |
| `bb_narrow_upper` | `branch_and_bound_narrow_upper` | bb.pl |
| `bb_put` | (same) | bb.pl, bv.pl |
| `bb_reoptimize` | `branch_and_bound_reoptimize` | bb.pl |
| `best` | (same) | fourmotz.pl |
| `between` | (same) | Scryer copy only |
| `binom` | `binomial_power` | nf.pl |
| `boolean` | (same) | arith.pl, arith_q.pl |
| `bs` | `back_substitute_variables` | bv.pl |
| `bs_collect_binding` | `back_substitute_collect_binding` | bv.pl |
| `bs_collect_bindings` | `back_substitute_collect_bindings` | bv.pl |
| `bv` | (same) | compenv.pl |
| `call` | (same) | arith_q.pl, geler.pl, nf.pl |
| `case_signum` | (same) | arith_q.pl, bv.pl, ineq.pl |
| `ceiling` | (same) | arith.pl, bb.pl |
| `ceilingq` | `ceiling_rational` | arith.pl, arith_q.pl |
| `class` | `component` | bv.pl, compenv.pl, dump.pl, itf3.pl, project.pl, redund.pl |
| `class_allvars` | `component_all_variables` | bv.pl, class.pl, dump.pl, project.pl, redund.pl |
| `class_atts` | `component_attributes` | class.pl |
| `class_basis` | `component_basis` | bv.pl, class.pl |
| `class_basis_add` | `component_basis_add` | bv.pl, class.pl |
| `class_basis_drop` | `component_basis_drop` | bv.pl, class.pl |
| `class_basis_pivot` | `component_basis_pivot` | bv.pl, class.pl |
| `class_drop` | `component_drop` | class.pl, itf3.pl |
| `class_get_prio` | `component_get_priority` | class.pl, ordering.pl |
| `class_new` | `component_new` | bv.pl, class.pl |
| `class_put_prio` | `component_put_priority` | class.pl, ordering.pl |
| `classq` | (same) | class.pl, compenv.pl |
| `classr` | (same) | compenv.pl |
| `clause` | (same) | itf3.pl |
| `clear_solver_atts` | `clear_solver_attributes` | Scryer copy only |
| `clpq` | (same) | arith_q.pl, class.pl, compenv.pl, itf3.pl, nfq.pl |
| `clpqr` | `linear_solver_module` | compenv.pl, itf3.pl |
| `clpr` | (same) | compenv.pl, itf3.pl |
| `collect_nonlin` | `collect_nonlinear` | dump.pl, geler.pl |
| `combine` | (same) | class.pl, ordering.pl |
| `combine_powers` | (same) | nf.pl |
| `compare` | (same) | arith.pl, bv.pl, itf3.pl, nf.pl, store.pl |
| `compenv` | (same) | compenv.pl |
| `compile_Q` | `compile_rational` | arith.pl |
| `compile_Qn` | `compile_rational_normalized` | arith.pl, arith_q.pl |
| `compile_R` | `compile_real` | arith.pl |
| `compile_case_signum_Qn` | `compile_case_signum_rational_normalized` | arith.pl, arith_q.pl |
| `compile_case_signum_R` | `compile_case_signum_real` | arith.pl |
| `compile_time_env` | `compile_time_environment` | compenv.pl |
| `compiler` | (same) | itf3.pl |
| `compiler_dump_nz` | `compiler_dump_disequation` | itf3.pl |
| `compiler_dump_var` | `compiler_dump_variable` | itf3.pl |
| `compound` | (same) | nf.pl |
| `comq` | `compare_rational` (port: `arithmetic.compare`) | arith.pl, arith_q.pl |
| `constraint` | (same) | nf.pl |
| `cos` | (same) | arith.pl, nf.pl |
| `cosq` | `cosine_rational` | arith.pl, arith_q.pl |
| `cp_card` | `cross_product_cardinality` | fourmotz.pl |
| `cp_card_lower` | `cross_product_cardinality_lower` | fourmotz.pl |
| `cp_card_upper` | `cross_product_cardinality_upper` | fourmotz.pl |
| `cpvars` | `copy_variables` | dump.pl |
| `cross_lower` | (same) | fourmotz.pl |
| `cross_upper` | (same) | fourmotz.pl |
| `crossproduct` | (same) | fourmotz.pl |
| `dcgs` | (same) | Scryer copy only |
| `deactivate_bound` | (same) | bv.pl |
| `dec_eval` | `decrease_evaluate` | bv.pl |
| `dec_step` | `decrease_step` | bv.pl, ineq.pl |
| `dec_step_best` | `decrease_step_best` | bv.pl |
| `decompose` | `split_linear_form` | bb.pl, bv.pl, ineq.pl, itf3.pl, project.pl, store.pl |
| `delete_factor` | (same) | bv.pl, store.pl |
| `delete_factor_hom` | `delete_factor_homogeneous` | store.pl |
| `delete_first` | (same) | class.pl |
| `denom` | (same) | arith.pl |
| `deref` | `dereference` | bb.pl, bv.pl, ineq.pl, itf3.pl |
| `deref_var` | `dereference_variable` | bb.pl, bv.pl |
| `detach_bounds` | (same) | bv.pl, fourmotz.pl, itf3.pl, redund.pl |
| `determine_active` | (same) | bv.pl |
| `determine_active_dec` | `determine_active_decrease` | bb.pl, bv.pl, ineq.pl |
| `determine_active_inc` | `determine_active_increase` | bv.pl, ineq.pl |
| `discontiguous` | (same) | Scryer copy only |
| `divq` | `divide_rational` (port: `arithmetic.divide`) | arith.pl, arith_q.pl |
| `divq_11` | `divide_rational_one_by` | arith.pl, arith_q.pl |
| `done` | (same) | geler.pl |
| `drop_dep` | `drop_dependent` | fourmotz.pl, project.pl |
| `drop_dep_one` | `drop_dependent_one` | fourmotz.pl, project.pl |
| `drop_lin_atts` | `drop_linear_attributes` | project.pl |
| `dump` | (same) | compenv.pl, dump.pl |
| `dump_ag_geler` | `dump_attribute_goals_geler` | Scryer copy only |
| `dump_ag_linear` | `dump_attribute_goals_linear` | Scryer copy only |
| `dump_ag_nonzero` | `dump_attribute_goals_nonzero` | Scryer copy only |
| `dump_linear` | (same) | dump.pl, itf3.pl |
| `dump_nonzero` | (same) | dump.pl, itf3.pl |
| `dump_nz` | `dump_disequation` | bv.pl, itf3.pl |
| `dump_strict` | (same) | bv.pl |
| `dump_v` | `dump_variable_in_context` | itf3.pl |
| `dump_var` | `dump_variable` | bv.pl, itf3.pl |
| `dynamic` | (same) | itf3.pl |
| `e` | (same) | nf.pl |
| `elim_min` | `eliminate_minimum` | fourmotz.pl |
| `empty_assoc` | (same) | dump.pl |
| `end_of_file` | (same) | compenv.pl, dump.pl |
| `ensure_loaded` | (same) | arith_q.pl, class.pl, nfq.pl |
| `entailed` | (same) | bb.pl, nf.pl, nfq.pl |
| `env_fcompile` | `environment_fcompile` | compenv.pl |
| `eps` | `epsilon` | arith.pl |
| `eq_classes` | `equate_components` | bv.pl |
| `equate` | (same) | bv.pl |
| `error` | (same) | Scryer copy only |
| `eval_q` | `evaluate_rational` | Scryer copy only |
| `exp` | (same) | arith.pl, nf.pl |
| `exp2term` | `exponent_to_term` | nf.pl |
| `exponent` | (same) | comments only |
| `export_binding` | (same) | bv.pl, ineq.pl, nf.pl, nfq.pl |
| `expq` | `exponential_rational` | arith.pl, arith_q.pl |
| `expression` | (same) | nf.pl |
| `f02t` | `first_monomial_to_term` | nf.pl |
| `factor_powers` | (same) | nf.pl |
| `fail` | (same) | bb.pl, bv.pl, fourmotz.pl, ineq.pl, nf.pl, ordering.pl, redund.pl |
| `fcompile` | (same) | compenv.pl |
| `file_mod` | `file_module` | compenv.pl |
| `findall` | (same) | dump.pl, fourmotz.pl |
| `flip` | (same) | fourmotz.pl |
| `flip_strict` | (same) | fourmotz.pl |
| `float` | (same) | arith.pl, bv.pl, itf3.pl |
| `float_rat` | `float_to_rational` | arith.pl |
| `floor` | (same) | arith.pl, bb.pl |
| `floorq` | `floor_rational` | arith.pl, arith_q.pl |
| `fm_cp_filter` | `fourier_motzkin_cross_product_filter` | fourmotz.pl |
| `fm_detach` | `fourier_motzkin_detach` | fourmotz.pl |
| `fm_elim` | `fourier_motzkin_eliminate` | fourmotz.pl, project.pl |
| `fm_elim_int` | `fourier_motzkin_eliminate_internal` | fourmotz.pl |
| `fn2t` | `next_monomial_to_term` | nf.pl |
| `format` | (same) | redund.pl |
| `forward` | (same) | itf3.pl |
| `fourmotz` | (same) | compenv.pl |
| `functor` | (same) | arith.pl |
| `fwd_deref` | `forward_dereference` | itf3.pl |
| `gcd` | (same) | arith.pl |
| `geler` | (same) | compenv.pl, geler.pl, nf.pl |
| `geler_q` | (same) | compenv.pl, geler.pl |
| `geler_r` | (same) | compenv.pl |
| `gen_edges` | `generate_edges` | ordering.pl |
| `get_atts` | (same) | bv.pl, class.pl, dump.pl, fourmotz.pl, geler.pl, ineq.pl, itf3.pl, project.pl, redund.pl, store.pl |
| `get_or_add_class` | `get_or_add_component` | bv.pl, class.pl, ineq.pl |
| `getq` | `get_rational` (port: `arithmetic.from_number`) | arith.pl, arith_q.pl |
| `goal_expansion` | (same) | arith_q.pl, itf3.pl |
| `goals` | (same) | geler.pl |
| `graph_union` | (same) | ordering.pl |
| `group` | (same) | ordering.pl |
| `hom2sum` | `homogeneous_to_sum` | store.pl |
| `illarg` | (same) | arith.pl, bb.pl, itf3.pl, nf.pl, ordering.pl |
| `imin` | (same) | bv.pl |
| `import` | (same) | compenv.pl |
| `imported_from` | (same) | itf3.pl |
| `impose_ordering` | (same) | project.pl |
| `impose_ordering_sys` | `impose_ordering_systems` | project.pl |
| `inc_step` | `increase_step` | bv.pl, ineq.pl |
| `incumbent` | (same) | bb.pl |
| `indep` | `independent` | bv.pl, fourmotz.pl, itf3.pl, project.pl, store.pl |
| `ineq` | `inequality` | bv.pl, compenv.pl, ineq.pl |
| `ineq_cases` | `inequality_cases` | ineq.pl |
| `ineq_ground` | `inequality_ground` | ineq.pl |
| `ineq_more` | `inequality_more_variables` | ineq.pl |
| `ineq_one` | `inequality_one_variable` | ineq.pl, nf.pl, nfq.pl |
| `ineq_one_n_n_0` | `inequality_one_variable_nonstrict_negative_zero` | ineq.pl, nf.pl, nfq.pl |
| `ineq_one_n_n_i` | `inequality_one_variable_nonstrict_negative_constant` | ineq.pl |
| `ineq_one_n_p_0` | `inequality_one_variable_nonstrict_positive_zero` | ineq.pl, nf.pl, nfq.pl |
| `ineq_one_n_p_i` | `inequality_one_variable_nonstrict_positive_constant` | ineq.pl |
| `ineq_one_new` | `inequality_one_new_variable` | comments only |
| `ineq_one_old` | `inequality_one_old_variable` | comments only |
| `ineq_one_old_n_n_0` | `inequality_one_old_variable_nonstrict_negative_zero` | ineq.pl |
| `ineq_one_old_n_n_i` | `inequality_one_old_variable_nonstrict_negative_constant` | ineq.pl |
| `ineq_one_old_n_p_0` | `inequality_one_old_variable_nonstrict_positive_zero` | ineq.pl |
| `ineq_one_old_n_p_i` | `inequality_one_old_variable_nonstrict_positive_constant` | ineq.pl |
| `ineq_one_old_s_n_0` | `inequality_one_old_variable_strict_negative_zero` | ineq.pl |
| `ineq_one_old_s_n_i` | `inequality_one_old_variable_strict_negative_constant` | ineq.pl |
| `ineq_one_old_s_p_0` | `inequality_one_old_variable_strict_positive_zero` | ineq.pl |
| `ineq_one_old_s_p_i` | `inequality_one_old_variable_strict_positive_constant` | ineq.pl |
| `ineq_one_s_n_0` | `inequality_one_variable_strict_negative_zero` | ineq.pl, nf.pl, nfq.pl |
| `ineq_one_s_n_i` | `inequality_one_variable_strict_negative_constant` | ineq.pl |
| `ineq_one_s_p_0` | `inequality_one_variable_strict_positive_zero` | ineq.pl, nf.pl, nfq.pl |
| `ineq_one_s_p_i` | `inequality_one_variable_strict_positive_constant` | ineq.pl |
| `inf` | (same) | bb.pl, bv.pl |
| `inf_lin` | `infimum_linear` | bv.pl |
| `instantiation_error` | (same) | Scryer copy only |
| `integer` | (same) | arith.pl, nf.pl |
| `integerp` | `rational_integer` | arith_q.pl, nf.pl |
| `intro_at` | `introduce_at` | bv.pl, redund.pl |
| `invertible` | (same) | comments only |
| `is` | (same) | arith.pl, bv.pl, fourmotz.pl, ineq.pl, nf.pl, project.pl, redund.pl, store.pl |
| `is_list` | (same) | Scryer copy only |
| `iso_ext` | (same) | Scryer copy only |
| `isolate` | (same) | bv.pl, store.pl |
| `iterate_dec` | `iterate_decrease` | bb.pl, bv.pl |
| `iterate_inc` | `iterate_increase` | bv.pl |
| `itf3` | (same) | compenv.pl |
| `join_class` | `join_component` | ordering.pl |
| `join_vars` | `join_variables` | arith.pl |
| `keep` | (same) | fourmotz.pl, itf3.pl, project.pl |
| `keep_indep` | `keep_independent` | fourmotz.pl, itf3.pl, project.pl |
| `keysort` | (same) | arith.pl, bv.pl, fourmotz.pl, ordering.pl |
| `l` | `below_lower_bound` | bv.pl, ineq.pl |
| `l2c` | `nonempty_list_to_conjunction` | dump.pl |
| `l2conj` | `list_to_conjunction` | arith.pl, arith_q.pl, geler.pl |
| `l2wrapped` | `list_to_wrapped_conjunction` | itf3.pl |
| `lb` | `lower_bound` | bv.pl, ineq.pl, itf3.pl |
| `lb_first` | `lower_bound_first` | bv.pl |
| `lb_inner` | `lower_bound_inner` | bv.pl |
| `length` | (same) | bv.pl, fourmotz.pl, nf.pl, store.pl |
| `lez` | `less_or_equal_zero` | fourmotz.pl |
| `library` | (same) | arith.pl, bb.pl, bv.pl, class.pl, dump.pl, geler.pl, itf3.pl, nf.pl, ordering.pl |
| `limit_encoding_length` | (same) | arith.pl |
| `lin` | `linear_form` | bv.pl, fourmotz.pl, ineq.pl, itf3.pl, project.pl |
| `lin_deref` | `linear_dereference` | comments only |
| `linear` | (same) | nf.pl |
| `linear_ps` | `linear_power_products` | nf.pl |
| `linearize` | (same) | arith.pl |
| `linearize_args` | `linearize_arguments` | arith.pl |
| `list` | (same) | Scryer copy only |
| `lists` | (same) | Scryer copy only |
| `llb` | `later_lower_bound` | itf3.pl |
| `load_expansions` | (same) | compenv.pl |
| `log` | (same) | arith.pl, nf.pl |
| `log_deref` | `dereference_balanced` | bv.pl, nf.pl, nfq.pl |
| `logq` | `logarithm_rational` | arith.pl, arith_q.pl |
| `lower` | (same) | fourmotz.pl |
| `lub` | `later_upper_bound` | itf3.pl |
| `make_target_indep` | `make_target_independent` | fourmotz.pl, project.pl |
| `mark_keep` | (same) | project.pl |
| `mark_target` | (same) | project.pl |
| `max` | (same) | arith.pl, nf.pl |
| `maximize` | (same) | bv.pl |
| `maxq` | `maximum_rational` | arith.pl, arith_q.pl |
| `mem` | `member_with_rest` | fourmotz.pl |
| `meta_predicate` | (same) | compenv.pl, dump.pl, geler.pl, nf.pl |
| `min` | (same) | arith.pl, bb.pl, nf.pl |
| `minimize` | (same) | bv.pl |
| `minimize_lin` | `minimize_linear` | bv.pl |
| `minq` | `minimum_rational` | arith.pl, arith_q.pl |
| `mode` | (same) | bv.pl, nf.pl |
| `module` | (same) | arith_q.pl, class.pl, geler.pl, nfq.pl |
| `monash_constant` | (same) | nf.pl |
| `msb` | (same) | arith.pl |
| `msb_val` | `most_significant_bit` | Scryer copy only |
| `msb_val_` | `most_significant_bit_loop` | Scryer copy only |
| `mulq` | `multiply_rational` (port: `arithmetic.multiply`) | arith.pl, arith_q.pl |
| `mult` | `multiply_monomials` | nf.pl |
| `mult_exp` | `multiply_exponents` | nf.pl |
| `mult_hom` | `multiply_homogeneous_part` | bv.pl, store.pl |
| `mult_linear_factor` | `multiply_linear_factor` | bv.pl, store.pl |
| `multifile` | (same) | compenv.pl |
| `must_be` | (same) | dump.pl |
| `narrow_l` | `narrow_lower` | bv.pl |
| `narrow_u` | `narrow_upper` | bv.pl |
| `negate` | (same) | nf.pl |
| `negate_l` | `negate_lower` | redund.pl |
| `negate_u` | `negate_upper` | redund.pl |
| `nf` | `normal_form` | bb.pl, compenv.pl, itf3.pl, nf.pl, nfq.pl |
| `nf2sum` | `normal_form_to_sum` | bv.pl, store.pl |
| `nf2term` | `normal_form_to_term` | nf.pl, nfq.pl |
| `nf_add` | `normal_form_add` | nf.pl |
| `nf_add_2` | `normal_form_add_two` | nf.pl |
| `nf_add_2_case` | `normal_form_add_two_case` | nf.pl |
| `nf_add_case` | `normal_form_add_case` | nf.pl |
| `nf_coeff_hom` | `normal_form_coefficient_homogeneous` | store.pl |
| `nf_coeff_of` | `normal_form_coefficient_of` | fourmotz.pl, itf3.pl, store.pl |
| `nf_constant` | `normal_form_constant` | bb.pl, nf.pl, nfq.pl |
| `nf_div` | `normal_form_divide` | nf.pl |
| `nf_length` | `normal_form_length` | nf.pl |
| `nf_mul` | `normal_form_multiply` | nf.pl |
| `nf_mul_factor` | `normal_form_multiply_factor` | nf.pl |
| `nf_mul_factor_log` | `normal_form_multiply_factor_balanced` | nf.pl |
| `nf_mul_k` | `normal_form_multiply_scalar` | nf.pl |
| `nf_mul_log` | `normal_form_multiply_balanced` | nf.pl |
| `nf_nonlin_1` | `normal_form_nonlinear_unary` | nf.pl |
| `nf_nonlin_2` | `normal_form_nonlinear_binary` | nf.pl |
| `nf_number` | `normal_form_number` | nf.pl |
| `nf_ordering` | `compare_variable_order` | itf3.pl, project.pl, store.pl |
| `nf_power` | `normal_form_power` | nf.pl |
| `nf_power_factor` | `normal_form_power_factor` | nf.pl |
| `nf_power_pos` | `normal_form_power_positive` | nf.pl |
| `nf_rhs_x` | `normal_form_right_hand_side` | bv.pl, store.pl |
| `nf_substitute` | `normal_form_substitute` | bv.pl, store.pl |
| `nfq` | (same) | arith_q.pl, compenv.pl, nfq.pl |
| `nfr` | (same) | compenv.pl |
| `nl_eval` | `evaluate_nonlinear` | nf.pl |
| `nl_invertible` | `nonlinear_invertible` | nf.pl |
| `nonexhausted` | (same) | geler.pl |
| `nonlin_1` | `nonlinear_unary` | nf.pl |
| `nonlin_2` | `nonlinear_binary` | nf.pl |
| `nonlin_crux` | `nonlinear_crux` | dump.pl |
| `nonlin_strip` | `nonlinear_strip` | dump.pl |
| `nonstrict` | (same) | bv.pl, ineq.pl, nf.pl |
| `nontarget` | (same) | project.pl |
| `nonvar` | (same) | bb.pl, bv.pl, geler.pl, itf3.pl, nf.pl, ordering.pl, store.pl |
| `nonzero` | (same) | bv.pl, itf3.pl, project.pl |
| `normalize` | (same) | ordering.pl |
| `normalize_scalar` | (same) | bv.pl, fourmotz.pl, ineq.pl, nf.pl, nfq.pl, store.pl |
| `normalize_vertex` | (same) | ordering.pl |
| `normalize_vertices` | (same) | ordering.pl |
| `not_memq` | `not_member_identical` | redund.pl |
| `number` | (same) | nf.pl |
| `numbers_only` | (same) | itf3.pl |
| `numer` | (same) | arith.pl |
| `occ_type_filter` | `occurrence_type_filter` | fourmotz.pl |
| `occurences` | (same) | fourmotz.pl |
| `occurs` | (same) | fourmotz.pl |
| `onto` | (same) | comments only |
| `op_float` | `operation_float` | arith.pl |
| `op_integer` | `operation_integer` | arith.pl |
| `op_rat` | `operation_rational` | arith.pl |
| `op_var` | `operation_variable` | arith.pl |
| `optimum` | (same) | bv.pl |
| `ord_add_element` | (same) | bv.pl |
| `order` | `variable_order` | bv.pl, itf3.pl, project.pl, store.pl |
| `ordering` | (same) | class.pl, compenv.pl, dump.pl, ordering.pl |
| `ordsets` | (same) | bv.pl |
| `p` | (same) | nf.pl |
| `p2term` | `power_product_to_term` | nf.pl |
| `pe2term` | `power_base_to_term` | nf.pl |
| `pe2term_args` | `power_base_arguments_to_terms` | nf.pl |
| `pi` | (same) | nf.pl |
| `pivot` | (same) | bv.pl, fourmotz.pl, project.pl |
| `pivot_a` | `pivot_exchange` | bv.pl, ineq.pl |
| `pivot_b` | `pivot_or_bound_swap` | bv.pl |
| `pivot_b_delta` | `bound_swap_delta` | bv.pl |
| `pmerge` | `merge_power_products` | nf.pl |
| `pmerge_case` | `merge_power_products_case` | nf.pl |
| `portray_message` | (same) | compenv.pl |
| `pow` | (same) | nf.pl |
| `powq` | `power_rational` | arith.pl |
| `predicate_property` | (same) | itf3.pl |
| `preference` | (same) | bv.pl |
| `prefilter` | (same) | fourmotz.pl |
| `presentation_context` | (same) | itf3.pl |
| `private` | (same) | compenv.pl |
| `project` | (same) | compenv.pl |
| `project_attributes` | (same) | dump.pl, project.pl |
| `project_nonlin` | `project_nonlinear` | geler.pl, project.pl |
| `projecting_assert` | (same) | dump.pl |
| `prolog` | (same) | geler.pl |
| `prolog_flag` | (same) | itf3.pl |
| `proper_list` | (same) | dump.pl |
| `public` | (same) | bv.pl, project.pl |
| `put_assoc` | (same) | dump.pl |
| `put_atts` | (same) | bv.pl, class.pl, fourmotz.pl, geler.pl, ineq.pl, itf3.pl, project.pl, redund.pl |
| `putq` | `put_rational` (port: `arithmetic.make_rational`) | arith.pl, arith_q.pl |
| `rat` | (same) | arith.pl, arith_q.pl, nf.pl |
| `rat_float` | `rational_to_float` | arith.pl, arith_q.pl |
| `rational` | (same) | itf3.pl |
| `rational_numerator_denominator` | (same) | Scryer copy only |
| `rcb` | `reconsider_basis_variable` | bv.pl |
| `rcbl` | `reconsider_basis_list` | bv.pl |
| `rcbl_app` | `reconsider_basis_list_applied` | bv.pl |
| `rcbl_opt` | `reconsider_basis_list_optimum` | bv.pl |
| `rcbl_status` | `reconsider_basis_list_status` | bv.pl, ineq.pl |
| `rcbl_unl` | `reconsider_basis_list_unlimited` | bv.pl |
| `rdiv` | (same) | Scryer copy only |
| `reconsider` | (same) | bv.pl, ineq.pl |
| `reconsider_lower` | (same) | ineq.pl |
| `reconsider_upper` | (same) | ineq.pl |
| `red_t_L` | `redundant_bounds_lower_active` | redund.pl |
| `red_t_U` | `redundant_bounds_upper_active` | redund.pl |
| `red_t_l` | `redundant_bounds_lower` | redund.pl |
| `red_t_u` | `redundant_bounds_upper` | redund.pl |
| `redund` | (same) | compenv.pl |
| `redundancy_systems` | (same) | redund.pl |
| `redundancy_vars` | `redundancy_variables` | fourmotz.pl, project.pl, redund.pl |
| `redundancy_vs` | `redundancy_variable_list` | redund.pl |
| `redundant` | (same) | redund.pl |
| `rel2sig` | `relation_to_sign` | arith.pl |
| `related_linear_sys` | `related_linear_systems` | dump.pl |
| `related_linear_vars` | `related_linear_variables` | dump.pl |
| `renorm_all` | `renormalize_all` | project.pl |
| `renormalize` | (same) | project.pl, store.pl |
| `renormalize_log` | `renormalize_balanced` | store.pl |
| `renormalize_log_one` | `renormalize_balanced_one` | store.pl |
| `repair` | (same) | bb.pl, nf.pl, nfq.pl |
| `repair_log` | `repair_balanced` | nf.pl |
| `repair_p` | `repair_power` | nf.pl |
| `repair_p_log` | `repair_power_balanced` | nf.pl |
| `repair_p_one` | `repair_power_base` | nf.pl |
| `repair_term` | (same) | nf.pl |
| `resubmit_eq` | `resubmit_equal` | nf.pl, nfq.pl |
| `resubmit_le` | `resubmit_less_or_equal` | nf.pl, nfq.pl |
| `resubmit_lt` | `resubmit_less_than` | nf.pl, nfq.pl |
| `resubmit_ne` | `resubmit_not_equal` | nf.pl, nfq.pl |
| `retractall` | (same) | itf3.pl |
| `reverse_pivot` | (same) | fourmotz.pl |
| `rhs_value` | `right_hand_side_value` | bb.pl |
| `round` | (same) | arith.pl, bb.pl |
| `round_values` | (same) | bb.pl |
| `roundq` | `round_rational` | arith.pl, arith_q.pl |
| `run` | (same) | geler.pl |
| `runtime` | (same) | redund.pl |
| `same_class` | `same_component` | bv.pl, ineq.pl |
| `scaled_eps` | `scaled_epsilon` | comments only |
| `sd` | `select_dependent` | bv.pl |
| `select_active_bound` | (same) | bv.pl |
| `select_nth` | (same) | fourmotz.pl |
| `sign` | (same) | Scryer copy only |
| `signum` | (same) | arith.pl |
| `signumq` | `signum_rational` (port: `arithmetic.sign`) | arith.pl, arith_q.pl |
| `sin` | (same) | arith.pl, nf.pl |
| `sinq` | `sine_rational` | arith.pl, arith_q.pl |
| `solve` | (same) | bv.pl, ineq.pl, itf3.pl, nf.pl, nfq.pl |
| `solve_bound` | (same) | ineq.pl |
| `solve_x` | `solve_for_variable` | bv.pl, itf3.pl |
| `solver_type` | (same) | itf3.pl |
| `sort` | (same) | geler.pl, ordering.pl, project.pl |
| `specialize_Q` | `specialize_rational` | arith.pl |
| `specialize_Q_fn` | `specialize_rational_function` | arith.pl |
| `specialize_Qn` | `specialize_rational_normalized` | arith.pl |
| `specialize_R` | `specialize_real` | arith.pl |
| `specialize_R_fn` | `specialize_real_function` | arith.pl |
| `split` | (same) | bv.pl, nf.pl, nfq.pl |
| `statistics` | (same) | redund.pl |
| `store` | (same) | compenv.pl |
| `strict` | (same) | bv.pl, ineq.pl, nf.pl |
| `strictness` | (same) | bv.pl, fourmotz.pl, ineq.pl, itf3.pl, project.pl, redund.pl |
| `strictness_parts` | (same) | redund.pl |
| `strip_nonvar` | `strip_nonvariable` | ordering.pl |
| `submit_constraint` | (same) | Scryer copy only |
| `submit_eq` | `submit_equal` | nf.pl |
| `submit_eq_b` | `submit_equal_single_term` | nf.pl |
| `submit_eq_c` | `submit_equal_several_terms` | nf.pl |
| `submit_eq_c1` | `submit_equal_constant_first` | nf.pl |
| `submit_le` | `submit_less_or_equal` | nf.pl |
| `submit_le_b` | `submit_less_or_equal_single_term` | nf.pl |
| `submit_le_c` | `submit_less_or_equal_several_terms` | nf.pl |
| `submit_lt` | `submit_less_than` | nf.pl |
| `submit_lt_b` | `submit_less_than_single_term` | nf.pl |
| `submit_lt_c` | `submit_less_than_several_terms` | nf.pl |
| `submit_ne` | `submit_not_equal` | nf.pl |
| `subq` | `subtract_rational` (port: `arithmetic.subtract`) | arith.pl, arith_q.pl |
| `sum_powers` | (same) | nf.pl |
| `sup` | (same) | bb.pl, bv.pl |
| `system` | (same) | ordering.pl |
| `system_error` | (same) | Scryer copy only |
| `systems` | (same) | project.pl, redund.pl |
| `t_L` | `bounds_lower_active` | bv.pl, fourmotz.pl, ineq.pl, itf3.pl, redund.pl |
| `t_Lu` | `bounds_lower_active_upper` | bv.pl, fourmotz.pl, ineq.pl, itf3.pl, redund.pl |
| `t_U` | `bounds_upper_active` | bv.pl, fourmotz.pl, ineq.pl, itf3.pl, redund.pl |
| `t_l` | `bounds_lower` | bv.pl, fourmotz.pl, ineq.pl, itf3.pl, redund.pl |
| `t_lU` | `bounds_lower_upper_active` | bv.pl, fourmotz.pl, ineq.pl, itf3.pl, redund.pl |
| `t_lu` | `bounds_lower_upper` | bv.pl, fourmotz.pl, ineq.pl, itf3.pl, redund.pl |
| `t_none` | `bounds_none` | bv.pl, ineq.pl, itf3.pl, project.pl, redund.pl |
| `t_u` | `bounds_upper` | bv.pl, fourmotz.pl, ineq.pl, itf3.pl, redund.pl |
| `tan` | (same) | arith.pl, nf.pl |
| `tanq` | `tangent_rational` | arith.pl, arith_q.pl |
| `target` | (same) | fourmotz.pl, itf3.pl, project.pl |
| `term_variables` | (same) | Scryer copy only |
| `term_variables_set` | (same) | dump.pl, geler.pl, nf.pl |
| `terms` | (same) | dump.pl, nf.pl |
| `the` | (same) | comments only |
| `this_linear_solver` | (same) | dump.pl, itf3.pl |
| `throw` | (same) | Scryer copy only |
| `top_sort` | (same) | ordering.pl |
| `toplevel` | (same) | dump.pl, itf3.pl |
| `trans` | `translate` | geler.pl |
| `transg` | `translate_goal` | geler.pl, nfq.pl |
| `true` | (same) | arith.pl, bb.pl, bv.pl, fourmotz.pl, ineq.pl, itf3.pl, ordering.pl, redund.pl |
| `truncate` | (same) | arith.pl |
| `truncateq` | `truncate_rational` | arith.pl, arith_q.pl |
| `type` | (same) | bv.pl, fourmotz.pl, ineq.pl, itf3.pl, nf.pl, project.pl, redund.pl |
| `type_error` | (same) | Scryer copy only |
| `typein_module` | (same) | itf3.pl |
| `types` | (same) | arith.pl, bb.pl, dump.pl, itf3.pl, nf.pl, ordering.pl |
| `u` | `above_upper_bound` | bv.pl, ineq.pl |
| `ub` | `upper_bound` | bv.pl, ineq.pl, itf3.pl |
| `ub_first` | `upper_bound_first` | bv.pl |
| `ub_inner` | `upper_bound_inner` | bv.pl |
| `udl` | `update_dependent_lower` | ineq.pl |
| `udls` | `update_dependent_lower_strict` | ineq.pl |
| `udu` | `update_dependent_upper` | ineq.pl |
| `udus` | `update_dependent_upper_strict` | ineq.pl |
| `ugraphs` | (same) | ordering.pl |
| `uil` | `update_independent_lower` | ineq.pl |
| `uils` | `update_independent_lower_strict` | ineq.pl |
| `uiu` | `update_independent_upper` | ineq.pl |
| `uius` | `update_independent_upper_strict` | ineq.pl |
| `unconstrained` | (same) | bv.pl, ineq.pl |
| `undet_active` | `undetermined_active` | bv.pl |
| `undet_active_h` | `undetermined_active_homogeneous` | bv.pl |
| `unkeep` | (same) | fourmotz.pl |
| `unlimited` | (same) | bv.pl |
| `unsatisfiable_ordering` | (same) | ordering.pl |
| `update_dep` | `update_dependent` | comments only |
| `update_indep` | `update_independent` | ineq.pl |
| `upper` | (same) | fourmotz.pl |
| `use_module` | (same) | arith.pl, bb.pl, bv.pl, class.pl, dump.pl, geler.pl, itf3.pl, nf.pl, nfq.pl, ordering.pl |
| `user` | (same) | compenv.pl |
| `user_error` | (same) | redund.pl |
| `v` | `monomial` | bb.pl, bv.pl, ineq.pl, nf.pl |
| `var` | (same) | arith.pl, bb.pl, bv.pl, class.pl, dump.pl, fourmotz.pl, geler.pl, itf3.pl, nf.pl, ordering.pl, project.pl, redund.pl, store.pl |
| `var_intern` | `variable_intern` | bv.pl, class.pl, ineq.pl, ordering.pl |
| `var_with_def_assign` | `variable_with_definition_assign` | bb.pl, bv.pl |
| `var_with_def_intern` | `variable_with_definition_intern` | bv.pl, fourmotz.pl, ineq.pl |
| `vars_constraints` | `variables_constraints` | dump.pl |
| `verify_attributes` | (same) | class.pl, geler.pl, itf3.pl |
| `verify_class` | `verify_component` | Scryer copy only |
| `verify_geler` | (same) | Scryer copy only |
| `verify_itf` | `verify_interface` | Scryer copy only |
| `verify_lin` | `verify_linear` | itf3.pl |
| `verify_nonzero` | (same) | itf3.pl |
| `verify_type` | (same) | itf3.pl |
| `verify_type_nonvar` | `verify_type_nonvariable` | itf3.pl |
| `verify_type_var` | `verify_type_variable` | itf3.pl |
| `vertex_value` | (same) | bb.pl, bv.pl |
| `wait_linear` | (same) | bb.pl, bv.pl, compenv.pl, nf.pl, nfq.pl |
| `wait_linear_retry` | (same) | nf.pl, nfq.pl |
| `warning` | (same) | compenv.pl |
| `where` | (same) | comments only |
| `wrap` | (same) | itf3.pl |
| `yfx` | `build_left_associative` | nf.pl |
| `zero` | (same) | nf.pl |
| `zero_division` | (same) | nf.pl |
