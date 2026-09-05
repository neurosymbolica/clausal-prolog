# Task 3 inversions ledger

Format: `<test id> | <what changed> | <ruling/task citation>`

Every test edited, renamed, inverted or regenerated in Task 3, with the
reason.  Nothing here was changed to make a red test green; each row is a
behaviour the task deliberately changed, or a mechanical artefact of it.

---

## Inverted assertions

`tests/test_tagged_terms.py::TestHeadPatternReachability::test_source_written_compounds_never_reach_a_head_pattern` → `::test_source_written_compounds_reach_a_head_pattern` | assertion flipped from `assert not [case lines mentioning 'point'/'seg']` to `assert [...]`; docstring rewritten to record what changed and why the old refusal dissolved. The trailing assertion (cell literals still present in bodies) is KEPT and re-justified: it is now the evidence that the unlifted all-clauses fallback still carries the body `Unify`, which is what preserves output mode. | Task 3 brief checkbox 5 ("Invert `TestHeadPatternReachability::test_source_written_compounds_never_reach_a_head_pattern` → now asserts `case ('point', ...)`/`('seg', ...)` arms DO appear in bucket functions"). The task's own crux.

`tests/test_tagged_terms.py::TestBucketPatternIntegration::test_the_lift_does_not_yet_reach_a_cell_pattern` → `::test_a_cell_head_arg_reaches_a_sequence_pattern` | three assertions flipped: `"case [['point', _ncap0, _ncap1]," not in src` → `in src`; `"$headlit_" in src` → `not in src`; added `"case [['seg', " in src`. `"case [point(" not in src` is unchanged (a cell must never match as a class). | Task 2 carry-forward, recorded by its own implementer as an executable finding for Task 3 to close ("TestBucketPatternIntegration is now an executable finding (bucket dispatch correct but unindexed for cells — lift doesn't recognize cells yet)", progress.md). Closed by the live-cell branch, not by the lift — see the report's note on this class, which asserts clauses straight into a `Database` with a `Compound` head, the one route that runs no hoist at all.

`tests/test_tagged_terms.py::TestHeadPatterns::test_no_tuple_data_tag_is_emitted_in_this_stage` → `::test_the_tuple_data_tag_is_now_emitted_as_a_dotted_value_pattern` | dropped `assert not hasattr(head_match, "TUPLE_TAG")` (head_match imports it now) and added a positive assertion that a tuple-DATA cell emits `case [$cells.TUPLE_TAG, _ncap0]:`. The str-functor half of the old test is kept verbatim. | Task 3 brief checkbox 3, which specifies the tuple-DATA arm and its constraint ("NEVER a bare `tuple` name (capture) or `__builtins__`"). The old test recorded the arm's absence as deliberate and named exactly the constraint any future one would have to meet; this is that future one. Deviation from the brief's spelling (`$cells.TUPLE_TAG`, not `builtins.tuple`) is argued in the report §4.

## Docstring-only edits (no assertion changed)

`tests/test_tagged_terms.py::TestBucketPatternIntegration` (class docstring) | rewrote the paragraph that recorded the Task-2 gap; added the fact that this class asserts through `Database.assertz` with a `Compound` head — the one route that runs neither `Module.define_predicate`'s hoist nor `database_ops`' fact normalisation — so the cell is in the head from the start and there is nothing for the bucket lift to lift. Points at `TestCellHeadReachability` for the lift's own coverage. | Accuracy: the old text said Task 3 would close this via the lift, and it did not — the live-cell branch closed it. Leaving the claim would mis-attribute the mechanism.

## Regenerated

`tests/golden/tagged_shapes.codegen.txt` | regenerated with `CLAUSAL_REGEN_GOLDEN=1`; diff READ before committing (49 insertions / 65 deletions, one file). Shape: `kind__p0_b0/b1/b2` each gain a `case [['<functor>', …], _vN]` arm and lose two/three `Var()` allocations plus one `trail.mark()`/`$unify`/`trail.undo()` triple; every other hunk in the file is the monotonic fresh-name counter renumbering by three (`_m21`→`_m18`, …). `kind__p1_*` and `kind__all__2` keep their cell literals in body `Unify` goals. The other four goldens (struct_tabling, deep_index, head_list_compound, edge_graph) are BYTE-IDENTICAL — their compound-head predicates are all under `_INDEX_THRESHOLD` (4). | Task 3 brief checkbox 5 ("Regenerate goldens again; read the diff -- expected: cell sequence arms in bucket functions, body Unify goals for those positions gone"). Observed shape matches the expectation exactly.

## Mechanical (line-number bookkeeping, no semantics)

`tests/test_funnel_lint.py` ALLOWLIST entry for `clausal/logic/database.py` | range `(524, 556)` → `(541, 573)`, with a comment recording the cause. The lint allowlists `head_key`'s `atom_bypass` idiom by LINE RANGE; the cell branch added to `_is_structural_head_value` earlier in the same file pushed `head_key` down 17 lines. No allowlist entry added, none widened in kind — the same single site, at its new address. | Same mechanism, same remedy, and the same comment convention as the two existing shift notes in that file (P3-2 Task 2 shifted `clausal/terms.py` 2355-2457 → 2373-2475 and `clausal/testing.py` for the same reason).

---

## Not inverted, though a reader might expect it

`tests/test_tagged_terms.py::TestHeadPatternReachability::test_index_dispatch_routes_every_cell_to_the_all_clauses_fallback` | UNCHANGED and still passing. `arg_index._runtime_arg_key` still keys a cell as `_INDEX_VAR`; Task 3 makes the bucket's CODEGEN reach a cell pattern, and Task 4 is what makes runtime dispatch select that bucket. The test's own docstring already says it is expected to be inverted there.

`tests/test_tagged_terms.py::TestBucketPatternIntegration::test_cell_callers_select_the_right_clause` | UNCHANGED and still passing — the answers were correct before Task 3 and are correct after. What changed underneath is the route (sequence pattern instead of `$headlit` capture-and-unify), which is exactly what the inverted sibling above now asserts.
