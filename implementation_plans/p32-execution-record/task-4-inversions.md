# Task 4 inversion ledger

Format: `<full test id> | <what changed> | <ruling cited>`

Every test edited, renamed, inverted, or regenerated in Task 4, with the
reason. Nothing here was changed to make a red test green; each row is a
behaviour the task deliberately changed (the cell key landing; R8's
coalesce retirement; the list-lift-skip fix the todo's trace required), or
a mechanical artefact of one of those.

---

## Inverted assertions

`tests/audit_2026_05_25/test_class_C15_first_arg_indexing.py::test_F095_first_arg_index_coalesces_str_and_charlist` | rewritten in full: module + method docstrings reframed from "F095 (bug)" to "F095 (historical bug, RETIRED)"; assertions changed from `n_str_caller == 2` / `n_list_caller == 1` (documenting the residual asymmetry) to `n_str_caller == 1` / `n_list_caller == 1` (§1b symmetric); comment block explains the traced mechanism (arg-index default-merge + `_lift_clause_at_pos` list lift + `_head_list_unify_input_py`'s residual str-as-list head-pattern contract) and cites the fixed todo | §1b, R8; todo/done/first-arg-indexing-str-caller-still-reaches-list-fact-2026-09-04.md

`tests/test_tagged_terms.py::TestHeadPatternReachability::test_index_dispatch_routes_every_cell_to_the_all_clauses_fallback` → `::test_index_dispatch_routes_a_cell_to_its_bucket` | inverted per the brief: `arg_index._runtime_arg_key(("point", 3, 4)) is arg_index._INDEX_VAR` → `== ("point", 2)`; kept the class-instance assertion (unchanged, still live code); ADDED an end-to-end demonstration that a real >threshold cell-headed predicate (`kind/2`, `tests/fixtures/tagged_shapes_tagged.clausal`, 6 clauses) SELECTS its bucket function (instrumented call counters: `{"bucket": 1, "fallback": 0}`) rather than falling through to `kind__all__2` | P3-2 Task 4 (the brief's own sketch); the old test's docstring named this test as its expected replacement

`tests/audit_2026_07_05/test_02_compiler_heads.py::TestIndexedDispatchGuards::test_str_charlist_heads_no_longer_coalesce_for_list_caller` | a SEPARATE, independent occurrence of the exact same bug the todo tracked (`coll/2`'s str-literal fact `coll("abc","s")` vs list-literal fact `coll(["a","b","c"],"l")`), found while running the full targeted suite (not the C15 file). `collect(mod, "coll", "abc", R, outv=[R])` expected `[("s",), ("l",)]` → `[("s",)]`; docstring rewritten to record the traced mechanism and point at the fixed todo instead of citing it as still-parked | §1b, R8; same fix as above

---

## New tests (not inversions — net-new coverage the brief's checklist requires)

`tests/test_first_arg_index.py::TestCellIndexKey` (new class) | `test_compound_cell_keys_functor_arity`, `test_tuple_data_cell_keys_by_length`, `test_slot_0_var_tuple_is_unindexable`, `test_bytelist_coalescing_regression`, `test_charlist_no_longer_coalesces_with_str`, `test_bucket_sharing_across_producers` | brief checkbox 4 (new tests); brief's key-branch sketch

`tests/test_first_arg_index.py::TestLiftClauseAtPos` (extended) | added `test_str_literal_is_now_lifted` (positive inversion of the retired F095 str skip), `test_bytes_literal_is_still_not_lifted` (regression for the KEPT half), `test_ground_str_content_list_literal_is_not_lifted` (the todo's fix, unit-level), `test_ground_int_list_literal_is_still_lifted` (regression proving the list-skip is narrowed correctly, not blanket) | R8; the todo's traced mechanism

`tests/test_tagged_terms.py::TestBucketPatternIntegration::test_asserted_cell_and_compile_time_compound_share_a_bucket` (new) | end-to-end bucket-sharing proof: five `assertz`-style live-cell clauses + one `Call(LoadName('point'), (7,8))`-shaped clause (the REAL `.clausal`-source representation of a compound reference, hoisted to Var + body `Unify` — not a bare `Compound` object, which no reachable clause head carries directly) on one predicate; instrumented call counters show all three `("point", ...)` callers route through the single `kind_probe__p0_b0*` bucket, never the fallback | brief checkbox 4 ("bucket-sharing across producers")

---

## Regenerated

`tests/golden/tagged_shapes.codegen.txt` | regenerated with `CLAUSAL_REGEN_GOLDEN=1`; diff READ before committing (49 insertions / 65 deletions in one file — `git diff --stat`). Shape: every str-literal head-arg bucket/position (`kind__p0_b3`, `kind__p0_b5`, `kind__p1_b0..b5`) loses its `trail.mark()`/`$unify(...)`/`trail.undo()` wrapper around the literal and instead gets a lifted `MatchValue`-style guard (`_scap0 == 'nil' or $unify(_scap0, 'nil', trail)`), with the fresh-name counter renumbering monotonically (`_m18`→`_m18` at new positions, etc.) — the exact shape the R8 str-lift-skip retirement produces, now that str literals in `kind/2`'s indexed buckets are lift-eligible. The other four goldens (struct_tabling, deep_index, head_list_compound, edge_graph) are BYTE-IDENTICAL — none has a str-literal head arg inside an `_INDEX_THRESHOLD`-crossing predicate | R8 (F095 str lift-skip retirement)

---

## Regression found and fixed by the FULL-SUITE gate (not anticipated by the brief)

`tests/test_head_match_imported_compound.py::test_indexed_imported_compound_at_second_position_enumerates_all_rows` | went red running the full `tests/` suite (not touched by hand): the cell key branch made dispatch select an already-broken second-position bucket for the first time. Root cause 1 — `head_to_match_pattern` (head_match.py) had no branch for a bare `LoadName`/`LoadAttr` reference reached anywhere OTHER than as a `Call`'s functor (e.g. `direct` nested inside `Wrap(direct)`'s lifted pattern); it fell through to `is_term_instance` and built a dead `MatchClass(LoadName, ...)` that no runtime cell slot (a plain resolved atom string) ever matches. Fixed: a new branch resolves the reference at compile time and bakes the resolved atom in as an `ast.MatchValue(ast.Constant(...))` (a bare dotted `ast.Name` — the trick `term_to_ast_expr` uses in plain expression position — is REJECTED by `compile()` inside a match pattern: "patterns may only match literals and attribute lookups"). Root cause 2 (found immediately after, re-running the test with only root cause 1 fixed) — a caller passing a PARTIALLY-ground cell (`("Wrap", Var())`) reached the newly-correct bucket and STILL got zero solutions, because the bucket's fact (`Wrap(direct)`, fully ground) compiles its nested slot to a plain `MatchValue` with no `== or $unify` hybrid fallback (unlike a top-level indexed argument), so an unbound Var there can never structurally match. Fixed: `_runtime_arg_key` (arg_index.py) gates its cell AND `is_term_instance` branches on a new `_is_deeply_ground` recursive check — a cell/instance with an unbound Var anywhere inside now keys `_INDEX_VAR` (full scan, correct via `unify()`) instead of routing to a bucket some of its clauses can structurally never satisfy. | Both are pre-existing defects (Task 3's cell-lift branch for root cause 1; the general indexed-bucket architecture for root cause 2, which ALSO affects the pre-existing `is_term_instance` branch) that Task 4's cell key branch is what makes reachable for the first time — squarely the "raw-cell lift route goes live" risk the hand-off called out. Not a test edit/inversion; a genuine code fix, TDD'd against this one red test (see task-4-report.md §TDD evidence).

## Not inverted, though a reader might expect it

`tests/test_tagged_terms.py::TestBucketPatternIntegration::test_cell_callers_select_the_right_clause` and `::test_a_class_instance_caller_finds_nothing` | UNCHANGED and still passing — the answers were correct before Task 4 (via the fallback scan) and are correct after (now via the selected bucket, for the cell case); nothing about the OBSERVABLE behaviour of these two tests depends on which route dispatch takes internally.

`tests/test_first_arg_index.py`'s existing `TestExtractFirstArgKey`/`TestBuildFirstArgIndex`/etc. classes | UNCHANGED — none of them exercised a str/char-list head arg or a cell, so R8 and the cell-key addition are both no-ops for their fixtures.
