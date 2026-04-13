# Duplicate Tests Report

## Python test duplicates (identical AST bodies)

### constraints

- fingerprint `8b43092263` (2 copies):
  - `tests/test_clpb.py:319` — `test_single_var`
  - `tests/test_clpb.py:352` — `test_forced_value`
- fingerprint `b159dd45ab` (2 copies):
  - `tests/test_clpb.py:534` — `test_single_var_true`
  - `tests/test_clpb.py:1186` — `test_sat_count_constant_true`
- fingerprint `ba78202e52` (2 copies):
  - `tests/test_clpq.py:1177` — `test_float_still_rejected_in_q`
  - `tests/test_clpq.py:1190` — `test_unify_q_var_with_float_raises`
- fingerprint `898ad1278b` (2 copies):
  - `tests/test_clpz3_bool.py:147` — `test_and`
  - `tests/test_clpz3_bool.py:382` — `test_with_sat_constraint`

### constraints+misc

- fingerprint `70d862a0c7` (4 copies):
  - `tests/test_clpfd.py:354` — `test_var_eq_int`
  - `tests/test_clpfd.py:376` — `test_auto_domain`
  - `tests/test_clpz.py:144` — `test_eq_narrows_to_singleton`
  - `tests/test_resolve_and_argkey.py:81` — `test_fd_eq_var_vs_int`

### control

- fingerprint `b390a6d480` (2 copies):
  - `tests/test_lambdas.py:114` — `test_lambda_param_generates_loadname`
  - `tests/test_lambdas.py:649` — `test_arrow_lambda_param_generates_loadname`
- fingerprint `45719b9d78` (2 copies):
  - `tests/test_lambdas.py:121` — `test_lambda_captures_enclosing_var`
  - `tests/test_lambdas.py:656` — `test_arrow_lambda_captures_enclosing_var`
- fingerprint `6d3dae3c99` (2 copies):
  - `tests/test_lambdas.py:130` — `test_lambda_body_only_var_does_not_leak`
  - `tests/test_lambdas.py:665` — `test_arrow_lambda_body_var_does_not_leak`
- fingerprint `3e0cd9d274` (2 copies):
  - `tests/test_predicate_meta.py:381` — `test_fields_preserved`
  - `tests/test_predicate_meta.py:421` — `test_term_field_names_on_class`

### control+misc

- fingerprint `72278bf7c8` (2 copies):
  - `tests/test_tabling.py:325` — `test_fib_basic`
  - `tests/test_wfs.py:350` — `test_tabled_fib`

### core

- fingerprint `543fa04319` (2 copies):
  - `tests/test_terms.py:125` — `test_bool_true_is_term`
  - `tests/test_terms.py:236` — `test_true`
- fingerprint `9bc226b2ee` (2 copies):
  - `tests/test_terms.py:129` — `test_bool_false_is_term`
  - `tests/test_terms.py:240` — `test_false`
- fingerprint `fa88580dc3` (2 copies):
  - `tests/test_terms.py:133` — `test_none_is_term`
  - `tests/test_terms.py:228` — `test_none`
- fingerprint `f4d0854bfb` (2 copies):
  - `tests/test_terms.py:149` — `test_ellipsis_is_term`
  - `tests/test_terms.py:232` — `test_ellipsis`

### misc

- fingerprint `c4aab14a5b` (2 copies):
  - `tests/test_transform_nodes.py:82` — `test_middle_node_removed`
  - `tests/test_transform_nodes.py:266` — `test_node_expanded_to_empty_list_acts_like_removal`

### misc+modules+scipy_torch

- fingerprint `390169c792` (6 copies):
  - `tests/test_list_util.py:440` — `test_fixture`
  - `tests/test_logging_module.py:460` — `test_fixture`
  - `tests/test_regex.py:753` — `test_fixture`
  - `tests/test_regex.py:784` — `test_fixture`
  - `tests/test_scipy_special.py:747` — `test_fixture`
  - `tests/test_spacy_module.py:751` — `test_fixture`

### modules

- fingerprint `b0e5faf388` (3 copies):
  - `tests/test_csv_module.py:122` — `test_unbound_fails`
  - `tests/test_http_module.py:285` — `test_unbound_fails`
  - `tests/test_json_module.py:181` — `test_unbound_string_fails`
- fingerprint `225068e65d` (2 copies):
  - `tests/test_csv_module.py:200` — `test_unbound_fails`
  - `tests/test_json_module.py:235` — `test_unbound_var_fails`
- fingerprint `ef34ba900f` (2 copies):
  - `tests/test_csv_module.py:263` — `test_read_unbound_path_fails`
  - `tests/test_json_module.py:352` — `test_read_unbound_path_fails`
- fingerprint `930aeda735` (2 copies):
  - `tests/test_module_imports.py:90` — `test_use_helper_ground`
  - `tests/test_module_imports.py:445` — `test_import_from_uses_dotted_key`
- fingerprint `01e4ba3f64` (2 copies):
  - `tests/test_units.py:191` — `test_mul_compound_dims`
  - `tests/test_units.py:686` — `test_force_from_mass_times_acceleration`
- fingerprint `36fb1cc34a` (2 copies):
  - `tests/test_units.py:526` — `test_foot_unit_vector`
  - `tests/test_units.py:1482` — `test_foot`
- fingerprint `d22c566e24` (2 copies):
  - `tests/test_units.py:533` — `test_pound_unit_vector`
  - `tests/test_units.py:1519` — `test_pound_mass`
- fingerprint `68be29bc14` (2 copies):
  - `tests/test_units.py:612` — `test_kilowatt_hour_unit_vector`
  - `tests/test_units.py:1583` — `test_kilowatt_hour`

### prolog

- fingerprint `a8ae8f99ec` (3 copies):
  - `tests/test_prolog_dialect.py:125` — `test_lowercase_leading`
  - `tests/test_prolog_dialect.py:133` — `test_head_leading`
  - `tests/test_prolog_emit.py:61` — `test_var_lowercase_leading`
- fingerprint `9a2b1601a8` (2 copies):
  - `tests/test_prolog_dialect.py:49` — `test_simple`
  - `tests/test_prolog_emit.py:21` — `test_pascal_to_snake_simple`
- fingerprint `3a56fc543d` (2 copies):
  - `tests/test_prolog_dialect.py:53` — `test_allcaps`
  - `tests/test_prolog_emit.py:25` — `test_pascal_to_snake_allcaps`
- fingerprint `5aa3c771ac` (2 copies):
  - `tests/test_prolog_dialect.py:57` — `test_mixed`
  - `tests/test_prolog_emit.py:29` — `test_pascal_to_snake_mixed`
- fingerprint `20f3d1e10a` (2 copies):
  - `tests/test_prolog_dialect.py:61` — `test_dcg`
  - `tests/test_prolog_emit.py:33` — `test_pascal_to_snake_dcg`
- fingerprint `e26e44e8d7` (2 copies):
  - `tests/test_prolog_dialect.py:87` — `test_simple`
  - `tests/test_prolog_emit.py:37` — `test_snake_to_pascal_simple`
- fingerprint `650374ef87` (2 copies):
  - `tests/test_prolog_dialect.py:91` — `test_copy_term`
  - `tests/test_prolog_emit.py:41` — `test_snake_to_pascal_copy_term`
- fingerprint `28e464d546` (2 copies):
  - `tests/test_prolog_dialect.py:109` — `test_leading_underscore`
  - `tests/test_prolog_emit.py:45` — `test_var_leading_underscore`
- fingerprint `2b2b0a876f` (2 copies):
  - `tests/test_prolog_dialect.py:113` — `test_allcaps`
  - `tests/test_prolog_emit.py:49` — `test_var_allcaps`
- fingerprint `969f34a2be` (2 copies):
  - `tests/test_prolog_dialect.py:117` — `test_single_letter`
  - `tests/test_prolog_emit.py:53` — `test_var_single_letter`
- fingerprint `0bd05c0455` (2 copies):
  - `tests/test_prolog_dialect.py:121` — `test_anon`
  - `tests/test_prolog_emit.py:57` — `test_var_anon`

### scipy_torch

- fingerprint `3bfcb06122` (25 copies):
  - `tests/test_scipy_cluster.py:500` — `test_fixture`
  - `tests/test_scipy_constants.py:313` — `test_fixture`
  - `tests/test_scipy_differentiate.py:320` — `test_fixture`
  - `tests/test_scipy_fft.py:579` — `test_fixture`
  - `tests/test_scipy_integrate.py:526` — `test_fixture`
  - `tests/test_scipy_integrate.py:542` — `test_fixture`
  - `tests/test_scipy_interpolate.py:541` — `test_fixture`
  - `tests/test_scipy_ndimage.py:626` — `test_fixture`
  - `tests/test_scipy_optimize.py:506` — `test_fixture`
  - `tests/test_scipy_sparse.py:697` — `test_fixture`
  - `tests/test_scipy_spatial.py:731` — `test_fixture`
  - `tests/test_scipy_stats.py:997` — `test_fixture`
  - `tests/test_torch.py:112` — `test_fixture`
  - `tests/test_torch.py:141` — `test_fixture`
  - `tests/test_torch.py:179` — `test_fixture`
  - `tests/test_torch.py:201` — `test_fixture`
  - `tests/test_torch.py:257` — `test_fixture`
  - `tests/test_torch.py:298` — `test_fixture`
  - `tests/test_torch.py:348` — `test_fixture`
  - `tests/test_torch.py:411` — `test_fixture`
  - `tests/test_torch.py:465` — `test_fixture`
  - `tests/test_torch.py:513` — `test_fixture`
  - `tests/test_torch.py:575` — `test_fixture`
  - `tests/test_torch.py:604` — `test_fixture`
  - `tests/test_torch.py:727` — `test_fixture`
- fingerprint `b2ec6dcf47` (3 copies):
  - `tests/test_scipy_linalg.py:176` — `test_result_get_wrong_type`
  - `tests/test_scipy_optimize.py:441` — `test_wrong_result_type_fails`
  - `tests/test_scipy_signal.py:693` — `test_non_dict_fails`
- fingerprint `929ae41eae` (3 copies):
  - `tests/test_scipy_linalg.py:588` — `test_non_string_field_fails`
  - `tests/test_scipy_optimize.py:446` — `test_non_string_field_fails`
  - `tests/test_scipy_stats.py:927` — `test_non_string_field_fails`
- fingerprint `f64695e036` (2 copies):
  - `tests/test_scipy_linalg.py:598` — `test_bind_existing_scalar_result`
  - `tests/test_scipy_optimize.py:456` — `test_bind_existing_scalar_result`
- fingerprint `6b71b3bf06` (2 copies):
  - `tests/test_scipy_sparse.py:601` — `test_free_unknown_handle_succeeds`
  - `tests/test_scipy_spatial.py:631` — `test_free_unknown_handle_succeeds`
- fingerprint `7ae8041c00` (2 copies):
  - `tests/test_scipy_spatial.py:234` — `test_handle_in_registry`
  - `tests/test_scipy_spatial.py:624` — `test_free_removes_from_registry`

## Empty-body Python tests (suspicious)

_None._

## .clausal Test(...) duplicates (identical body text)

`prolog_golden/` and `docs/*_sig_tests.clausal` are filtered: the former is intentional Prolog round-trip mirrors, the latter is auto-generated signature-existence tests.

### constraints

- 2 copies:
  - `tests/fixtures/coroutining.clausal:4` — `Test("call_nth basic")`
  - `tests/fixtures/docs/coroutining_examples.clausal:48` — `Test("third")`
- 2 copies:
  - `tests/fixtures/coroutining.clausal:10` — `Test("call_nth too few")`
  - `tests/fixtures/docs/coroutining_examples.clausal:54` — `Test("too few")`
- 2 copies:
  - `tests/fixtures/coroutining.clausal:72` — `Test("when is_bound")`
  - `tests/fixtures/docs/coroutining_examples.clausal:5` — `Test("when isbound")`
- 2 copies:
  - `tests/fixtures/coroutining.clausal:89` — `Test("findall+callnth")`
  - `tests/fixtures/docs/coroutining_examples.clausal:81` — `Test("findall+callnth")`

### control

- 4 copies:
  - `tests/clausal_modules/higher_order.clausal:50` — `Test("HO all_positive succeeds")`
  - `tests/clausal_modules/meta.clausal:98` — `Test("all_positive succeeds")`
  - `tests/fixtures/builtins_higher_order.clausal:30` — `Test("all positive")`
  - `tests/fixtures/meta_test.clausal:33` — `Test("all positive")`
- 3 copies:
  - `tests/clausal_modules/higher_order.clausal:51` — `Test("HO all_positive fails")`
  - `tests/clausal_modules/meta.clausal:99` — `Test("all_positive fails")`
  - `tests/fixtures/meta_test.clausal:34` — `Test("all positive fails: [1,-2,3]")`
- 2 copies:
  - `tests/clausal_modules/higher_order.clausal:52` — `Test("HO all_positive empty (vacuously true)")`
  - `tests/clausal_modules/meta.clausal:100` — `Test("all_positive empty (vacuously true)")`
- 2 copies:
  - `tests/conformity/iso_control.clausal:72` — `Test("not: successful unification fails")`
  - `tests/conformity/iso_control.clausal:75` — `Test("double negation: not not (1=1)")`
- 2 copies:
  - `tests/fixtures/tabled_ite.clausal:17` — `Test("path 1 to 2")`
  - `tests/fixtures/tabled_path.clausal:14` — `Test("path 1 to 2")`
- 2 copies:
  - `tests/fixtures/tabled_ite.clausal:18` — `Test("path 1 to 3")`
  - `tests/fixtures/tabled_path.clausal:15` — `Test("path 1 to 3")`

### control+misc

- 2 copies:
  - `tests/fixtures/fibonacci.clausal:24` — `Test("fib 0")`
  - `tests/fixtures/tabled_fib.clausal:15` — `Test("fib 0")`
- 2 copies:
  - `tests/fixtures/fibonacci.clausal:25` — `Test("fib 1")`
  - `tests/fixtures/tabled_fib.clausal:16` — `Test("fib 1")`
- 2 copies:
  - `tests/fixtures/fibonacci.clausal:26` — `Test("fib 5")`
  - `tests/fixtures/tabled_fib.clausal:17` — `Test("fib 5")`
- 2 copies:
  - `tests/fixtures/fibonacci.clausal:27` — `Test("fib 10")`
  - `tests/fixtures/tabled_fib.clausal:18` — `Test("fib 10")`

### control+modules

- 3 copies:
  - `tests/conformity/iso_control.clausal:73` — `Test("not: member absent")`
  - `tests/conformity/iso_control.clausal:82` — `Test("not + member: d not in list")`
  - `tests/conformity/iso_list_operations.clausal:53` — `Test("member: not found")`
- 2 copies:
  - `tests/conformity/iso_list_operations.clausal:165` — `Test("in_ enumerates [1,2,3]")`
  - `tests/fixtures/meta_test.clausal:38` — `Test("findall basic: member of [1,2,3]")`

### core

- 3 copies:
  - `tests/fixtures/builtins_db.clausal:28` — `Test("color red")`
  - `tests/fixtures/builtins_db.clausal:29` — `Test("color green")`
  - `tests/fixtures/builtins_db.clausal:30` — `Test("color blue")`
- 2 copies:
  - `tests/conformity/iso_unification.clausal:30` — `Test("atom unifies with itself")`
  - `tests/conformity/iso_unification.clausal:34` — `Test("var unifies with atom")`
- 2 copies:
  - `tests/conformity/iso_unification.clausal:70` — `Test("different atoms == fails")`
  - `tests/conformity/iso_unification.clausal:79` — `Test("different atoms !=")`
- 2 copies:
  - `tests/fixtures/expansion_importer.clausal:8` — `Test("color red")`
  - `tests/fixtures/expansion_importer.clausal:9` — `Test("color green")`

### core+misc

- 2 copies:
  - `tests/clausal_modules/thread_safe_predicates.clausal:47` — `Test("member first")`
  - `tests/fixtures/deep_index.clausal:44` — `Test("mymember first element")`
- 2 copies:
  - `tests/clausal_modules/thread_safe_predicates.clausal:48` — `Test("member last")`
  - `tests/fixtures/deep_index.clausal:45` — `Test("mymember last element")`

### misc

- 4 copies:
  - `tests/clausal_modules/thread_safe_predicates.clausal:59` — `Test("direct edge")`
  - `tests/clausal_modules/thread_safe_predicates.clausal:60` — `Test("transitive path")`
  - `tests/clausal_modules/thread_safe_predicates.clausal:61` — `Test("reachable b from a")`
  - `tests/clausal_modules/thread_safe_predicates.clausal:62` — `Test("reachable c from a")`
- 4 copies:
  - `tests/fixtures/specialize_cpd.clausal:44` — `Test("cpd path(a,b)")`
  - `tests/fixtures/specialize_cpd.clausal:46` — `Test("cpd path(a,c)")`
  - `tests/fixtures/specialize_cpd.clausal:48` — `Test("cpd path(a,d)")`
  - `tests/fixtures/specialize_cpd.clausal:50` — `Test("cpd edge(b,c)")`
- 4 copies:
  - `tests/fixtures/specialize_graph.clausal:26` — `Test("specialized edge(a,b)")`
  - `tests/fixtures/specialize_graph.clausal:30` — `Test("specialized path(a,b) direct")`
  - `tests/fixtures/specialize_graph.clausal:34` — `Test("specialized path(a,c) transitive")`
  - `tests/fixtures/specialize_graph.clausal:38` — `Test("specialized path(a,d) transitive")`
- 3 copies:
  - `tests/fixtures/expansion_passthrough.clausal:9` — `Test("foo a")`
  - `tests/fixtures/expansion_passthrough.clausal:10` — `Test("foo b")`
  - `tests/fixtures/expansion_passthrough.clausal:11` — `Test("foo c")`
- 3 copies:
  - `tests/fixtures/shallow_pred.clausal:8` — `Test("color sky")`
  - `tests/fixtures/shallow_pred.clausal:9` — `Test("color grass")`
  - `tests/fixtures/shallow_pred.clausal:10` — `Test("color sun")`
- 2 copies:
  - `tests/conformity/iso_type_checking.clausal:63` — `Test("str: plain string succeeds")`
  - `tests/conformity/iso_type_checking.clausal:64` — `Test("str: empty string succeeds")`
- 2 copies:
  - `tests/fixtures/pysat_boolean.clausal:28` — `Test("or 3 solutions")`
  - `tests/fixtures/z3_boolean.clausal:11` — `Test("boolean or has 3 solutions")`
- 2 copies:
  - `tests/fixtures/wfs_win_asym.clausal:10` — `Test("move a to b")`
  - `tests/fixtures/wfs_win_asym.clausal:11` — `Test("move b to a")`

### misc+scipy_torch

- 2 copies:
  - `tests/fixtures/pysat_boolean.clausal:127` — `Test("pigeonhole 3-into-2 unsat")`
  - `tests/fixtures/torch_linalg_tests.clausal:111` — `Test("cholesky reconstruct")`

### modules

- 5 copies:
  - `tests/fixtures/logging_basic.clausal:22` — `Test("set_level debug")`
  - `tests/fixtures/logging_basic.clausal:28` — `Test("set_level warning")`
  - `tests/fixtures/logging_basic.clausal:34` — `Test("set_level error")`
  - `tests/fixtures/logging_basic.clausal:40` — `Test("set_level critical")`
  - `tests/fixtures/logging_basic.clausal:46` — `Test("set_level info")`
- 4 copies:
  - `tests/fixtures/regex_basic.clausal:7` — `Test("match digits")`
  - `tests/fixtures/regex_basic.clausal:11` — `Test("match email")`
  - `tests/fixtures/regex_basic.clausal:69` — `Test("match empty string")`
  - `tests/fixtures/regex_basic.clausal:70` — `Test("match unicode")`
- 2 copies:
  - `tests/conformity/iso_list_operations.clausal:98` — `Test("nth0 first")`
  - `tests/conformity/iso_list_operations.clausal:100` — `Test("nth1 first")`
- 2 copies:
  - `tests/conformity/iso_list_operations.clausal:99` — `Test("nth0 last")`
  - `tests/conformity/iso_list_operations.clausal:101` — `Test("nth1 last")`
- 2 copies:
  - `tests/fixtures/logging_basic.clausal:55` — `Test("enabled_for yes")`
  - `tests/fixtures/logging_basic.clausal:65` — `Test("enabled_for same level")`
- 2 copies:
  - `tests/fixtures/logging_basic.clausal:96` — `Test("log at info")`
  - `tests/fixtures/logging_basic.clausal:100` — `Test("log at debug")`
- 2 copies:
  - `tests/fixtures/logging_basic.clausal:115` — `Test("stream_handler stdout")`
  - `tests/fixtures/logging_basic.clausal:116` — `Test("stream_handler stderr")`
- 2 copies:
  - `tests/fixtures/regex_basic.clausal:9` — `Test("match anchored at start")`
  - `tests/fixtures/regex_basic.clausal:10` — `Test("match full via dollar")`
- 2 copies:
  - `tests/fixtures/regex_basic.clausal:50` — `Test("replace whitespace")`
  - `tests/fixtures/regex_basic.clausal:51` — `Test("replace remove digits")`
- 2 copies:
  - `tests/fixtures/regex_basic.clausal:56` — `Test("split comma")`
  - `tests/fixtures/regex_basic.clausal:57` — `Test("split whitespace")`

### scipy_torch

- 9 copies:
  - `tests/fixtures/torch_schedulers_tests.clausal:12` — `Test("scheduler lookup StepLR")`
  - `tests/fixtures/torch_schedulers_tests.clausal:16` — `Test("scheduler lookup MultiStepLR")`
  - `tests/fixtures/torch_schedulers_tests.clausal:20` — `Test("scheduler lookup CyclicLR")`
  - `tests/fixtures/torch_schedulers_tests.clausal:24` — `Test("scheduler lookup OneCycleLR")`
  - `tests/fixtures/torch_schedulers_tests.clausal:28` — `Test("scheduler lookup ReduceLROnPlateau")`
  - `tests/fixtures/torch_schedulers_tests.clausal:32` — `Test("scheduler lookup LambdaLR")`
  - `tests/fixtures/torch_schedulers_tests.clausal:36` — `Test("scheduler lookup LinearLR")`
  - `tests/fixtures/torch_schedulers_tests.clausal:40` — `Test("scheduler lookup ConstantLR")`
  - `tests/fixtures/torch_schedulers_tests.clausal:44` — `Test("scheduler lookup PolynomialLR")`
- 4 copies:
  - `tests/fixtures/sklearn_basic.clausal:21` — `Test("load iris dataset")`
  - `tests/fixtures/sklearn_data.clausal:7` — `Test("load diabetes dataset")`
  - `tests/fixtures/sklearn_data.clausal:12` — `Test("load wine dataset")`
  - `tests/fixtures/sklearn_data.clausal:17` — `Test("load breast cancer dataset")`
- 3 copies:
  - `tests/fixtures/sklearn_basic.clausal:7` — `Test("algorithm random_forest is classifier")`
  - `tests/fixtures/sklearn_basic.clausal:11` — `Test("algorithm pca is transformer")`
  - `tests/fixtures/sklearn_basic.clausal:15` — `Test("algorithm kmeans is clusterer")`
- 3 copies:
  - `tests/fixtures/torch_registry_tests.clausal:8` — `Test("layer enumerates Linear")`
  - `tests/fixtures/torch_registry_tests.clausal:13` — `Test("layer enumerates Conv2d")`
  - `tests/fixtures/torch_registry_tests.clausal:18` — `Test("layer enumerates LSTM")`
- 2 copies:
  - `tests/fixtures/torch_distributions_tests.clausal:24` — `Test("make normal distribution")`
  - `tests/fixtures/torch_distributions_tests.clausal:32` — `Test("make uniform distribution")`
- 2 copies:
  - `tests/fixtures/scipy_sparse_tests.clausal:16` — `Test("makecsr nnz correct")`
  - `tests/fixtures/scipy_sparse_tests.clausal:127` — `Test("nonzerocount correct")`
- 2 copies:
  - `tests/fixtures/torch_registry_tests.clausal:36` — `Test("activation enumerates ReLU")`
  - `tests/fixtures/torch_registry_tests.clausal:47` — `Test("activation enumerates Softmax")`
- 2 copies:
  - `tests/fixtures/torch_registry_tests.clausal:54` — `Test("loss_fn enumerates CrossEntropyLoss")`
  - `tests/fixtures/torch_registry_tests.clausal:59` — `Test("loss_fn enumerates MSELoss")`
- 2 copies:
  - `tests/fixtures/torch_registry_tests.clausal:71` — `Test("optimizer_type enumerates Adam")`
  - `tests/fixtures/torch_registry_tests.clausal:76` — `Test("optimizer_type enumerates SGD")`
- 2 copies:
  - `tests/fixtures/torch_tensor_tests.clausal:26` — `Test("zeros default")`
  - `tests/fixtures/torch_tensor_tests.clausal:126` — `Test("shape check succeeds")`
