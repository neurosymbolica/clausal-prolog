# Task 5 inversion ledger

Format: `<full test id> | <what changed> | <ruling cited>`

Every test edited, renamed, inverted, or added in Task 5, with the reason.
Nothing here was changed to make a red test green; each row is a behaviour
this task deliberately changed (retiring the Var-functor cell per §1b), or
a mechanical artefact of one of those.

---

## Inverted assertions

`tests/test_cells.py::TestCellPrimitives::test_make_cell_var_functor` → `::test_make_cell_rejects_unbound_var_functor` | `make_cell(v, 1, 2) == (v, 1, 2)` (accepted) → `pytest.raises(TypeError)` (rejected) | §1b: the bridge's higher-order slot-0-Var functor is deprecated; `make_cell` now rejects it same as any other invalid functor.

`tests/test_cells.py::TestCellPrimitives::test_make_cell_rejects_bound_var_is_still_accepted` → `::test_make_cell_rejects_bound_var_functor_regardless_of_binding` | kept the original bound-to-int rejection assertion, ADDED a second case: a Var bound to a LEGAL slot-0 shape (a str) is *also* rejected now, because `make_cell` no longer calls `is_var`/derefs the functor at all — it inspects the functor object itself, unconditionally. The old docstring's premise ("a Var that resolves to a str is accepted") is no longer true and is corrected in the new docstring. | §1b: no deref, ever, on this recognition path.

`tests/test_cells.py::TestCellPrimitives::test_is_cell_true_for_var_functor` → `::test_is_cell_false_for_var_functor` | `is_cell((Var(), 1, 2)) is True` → `is False`; added a second case for a BOUND Var functor (also `False`) | §1b: a Var-functor tuple is not cell-shaped at all any more, unbound or bound.

`tests/test_cells.py::TestCellUnificationBoundary::test_higher_order_slot0_var_binds_to_other_cells_functor` → `::test_higher_order_slot0_var_unifies_but_is_no_longer_recognized_as_a_cell` | the "review fix finding #1" test. Kept the underlying raw-tuple-unify property (unify still binds the Var to the peer's functor string — ordinary element-wise tuple unify, untouched by §1b) but built the tuple directly (`(f, 1)`) instead of via `make_cell` (which now rejects it), and INVERTED every recognition assertion: `is_cell(c1) is True` → `False`; `cell_functor(c1) == "f"` (assertion dropped — no longer meaningful to call on a non-cell); `_functor_name(c1) == "f"` → `is None`; `_is_compound(c1) is True` → `False`; `_arity(c1) == 1` → `is None`. | §1b: recognition reads slot 0 raw everywhere now, so a bound-Var-functor tuple never becomes a cell, before or after the bind — the exact defect (finding #1) this test used to guard against no longer has a scenario to guard.

`tests/test_cells.py::TestCellUnificationBoundary::test_higher_order_slot0_var_mismatched_arity_fails` → `::test_higher_order_slot0_var_functor_no_longer_constructible` | the arity-mismatch-via-unify scenario required `make_cell(f, 1)`, which now raises before any unify happens; inverted to assert exactly that (`pytest.raises(TypeError)`) instead of the old `unify(...) is False` | §1b: `make_cell` rejects a Var functor regardless of the intended arity.

`tests/test_cells.py::TestCellPrimitives::test_known_ambiguity_plain_str_tuple_is_a_cell_by_shape` → `::test_the_discipline_plain_str_tuple_is_a_cell_by_shape` | RE-WORDED, same assertion (`is_cell(("hello", 1)) is True`) | §1b: what was an accepted "known ambiguity" is now THE DISCIPLINE per the slot-0 narrowing (there is no narrower domain left to be ambiguous with).

`tests/test_cells.py::TestInternCell::test_non_ground_functor_slot_returned_unchanged` → `::test_var_functor_tuple_is_not_a_cell_so_never_reaches_the_intern_walk` | built the tuple raw (`(F, 1, 2)`) instead of via `make_cell`; added `assert is_cell(c) is False`; kept `intern_cell(c) is c` | §1b + the tabling brief bullet: a Var-functor tuple is not a cell, so `intern_cell` short-circuits on `is_cell` before the groundness walk (`_try_intern`) ever runs, rather than reaching the walk and being disqualified there.

`tests/test_funnel_accessors.py::TestCellFunnelAwareness::test_var_functor_cell_functor_name_returns_the_var` → `::test_var_functor_tuple_functor_name_is_none` | built the tuple raw instead of via `make_cell`; `_functor_name(c) is v` → `is None` | §1b.

`tests/test_funnel_accessors.py::TestCellFunnelAwareness::test_var_functor_cell_is_compound` → `::test_var_functor_tuple_is_not_compound` | `_is_compound(c) is True` → `is False` | §1b.

`tests/test_funnel_accessors.py::TestCellFunnelAwareness::test_var_functor_cell_arity_and_args_still_resolve` → `::test_var_functor_tuple_arity_and_args_no_longer_resolve` | `_arity(c) == 2` → `is None`; `_args_list(c) == [1, 2]` → `== []`; `_nth_arg(c, 1) == 1` → `pytest.raises(IndexError)` | §1b: the tuple is no longer recognized as a cell at all, so it gets the plain-tuple answer across the board.

`tests/test_funnel_accessors.py::TestCellFunnelAwareness::test_var_functor_cell_functor_arity_is_none` → `::test_var_functor_tuple_functor_arity_is_none` | still asserts `functor_arity(c) is None` (unchanged answer) but `(_functor_name(c), _arity(c))` changes from `(v, 2)` to `(None, None)` — the documented divergence between `functor_arity` and the composed pair this test used to pin no longer exists (both now agree: None) | §1b.

`tests/test_funnel_accessors.py::TestCellFunnelAwareness::test_known_ambiguity_plain_str_tuple_pinned_by_running_assertions` → `::test_the_discipline_plain_str_tuple_pinned_by_running_assertions` | RE-WORDED, same assertions (`_functor_name`/`_arity`/`_args_list`/`_is_compound`/`functor_arity` on `("hello", 1)`, all unchanged) | §1b: "known ambiguity" → "the discipline," per the module docstring's own re-framing; brief's explicit instruction for this exact test.

`tests/test_tagged_terms.py::TestCallableAndTheTupleDataEdge::test_a_var_functor_cell_is_callable_like_its_compound_twin` → `::test_a_var_functor_tuple_is_no_longer_callable_unlike_its_compound_twin` | `nsol("callable_", (v,1,2)) == nsol("callable_", Compound(v,(1,2))) == 1` → the two now DIVERGE: `nsol("callable_", (v,1,2)) == 0` (tuple no longer compound) while `nsol("callable_", Compound(v,(1,2))) == 1` (unchanged — `Compound` is a separate representation, untouched by the cell narrowing) | §1b: higher-order metaprogramming over CELLS is retired; `Compound`'s own (pre-existing, unrelated) Var-functor story is not in scope and does not change.

## Docstring-only edits (no assertion changed)

`tests/test_cells.py` module docstring | `TestCellUnificationBoundary`'s summary line dropped "the higher-order slot-0-Var case binds the functor itself," replaced with a note that the former higher-order case is retained only as a raw-tuple-unify property, not a cell-recognition one. | §1b.

`tests/test_funnel_accessors.py::TestCellFunnelAwareness` class docstring | rewrote the "KNOWN AMBIGUITY" paragraph to "THE DISCIPLINE" (same framing shift as the module docstring in `cells.py`) and added a paragraph naming the Var-functor deprecation and pointing at the `test_var_functor_tuple_*` tests. | §1b.

`tests/test_tagged_terms.py::TestCellHeadGuardLeaks::test_a_bound_var_functor_cell_head_arg_does_not_crash` | NOT inverted (see "Not inverted" below) — docstring extended with a "WINDOW CLOSED" paragraph explaining that this test's end-to-end runtime answer is unchanged by Task 5 (`head_to_match_pattern` already read slot 0 raw pre-Task-5), and that what closes is the disagreement between the compiler (always raw) and `is_cell`/the funnel (previously deref'd, now also raw). Added one assertion, `is_cell((bound, 1, 2)) is False`, to make the closure a running check rather than prose alone. | Brief's explicit ask: "confirm behavior end-to-end with one driven test and state what the answer is" for the T3-to-T5 window.

## New tests (not inversions — net-new coverage the brief's checklist requires)

`tests/test_tabling.py::TestAddAnswerCellInterning::test_a_ground_cell_answer_still_tables` | proves the §1b narrowing does not touch str/TUPLE_TAG cells: a ground str-functor cell answer still dedups/interns exactly as before Task 5. | Brief checkbox 4 ("a ground cell answer still tables").

`tests/test_tabling.py::TestAddAnswerCellInterning::test_a_var_functor_tuple_answer_no_longer_reaches_intern_cell` | proves a Var-functor tuple answer is passed through `TableEntry.add_answer`'s `intern_cell(a) if is_cell(a) else a` gate UNTOUCHED — `is_cell` now answers `False` for it, so `intern_cell` is never even called on it. | Brief checkbox 4 ("a Var-functor tuple no longer reaches `intern_cell`").

---

## Not inverted, though a reader might expect it

`tests/test_tagged_terms.py::TestCellHeadGuardLeaks::test_an_unbound_var_functor_cell_head_arg_does_not_crash` | UNCHANGED and still passing — an UNBOUND Var-functor cell head arg was already, and remains, a pure wildcard (`head_to_match_pattern` returns `case _:` for it, per `test_a_var_functor_cell_head_arg_stays_a_wildcard`); `head_match` never called `is_cell`/the funnel here, so the §1b narrowing changes nothing observable for this shape.

`tests/test_tagged_terms.py::TestCellHeadGuardLeaks::test_a_bound_var_functor_cell_head_arg_does_not_crash` | UNCHANGED assertions (see "Docstring-only edits" above for the added closure note and one new assertion) — this is the "T3-to-T5 window" test named in the task brief. `head_to_match_pattern` already read slot 0 RAW pre-Task-5 (a documented, deliberate choice — a bound-Var functor is "not a shape this can decide" at compile time), so this test's END-TO-END RUNTIME ANSWER was already what Task 5 leaves it as. What Task 5 closes is that `is_cell`/the funnel accessors PREVIOUSLY disagreed with the compiler (answering `True`, via a deref, for the exact same tuple the compiler could not decide) — now both read raw and agree: `False`, uniformly. See the extended docstring for the full trace.

`tests/test_tagged_terms.py::TestCellHeadGuardLeaks::test_a_var_functor_cell_head_arg_stays_a_wildcard` (in `TestTaggedShapesHeadPatternGeneration` or wherever it lives) and the rest of `head_match`/`globals_env`/`list_dispatch`'s existing cell-pattern tests | UNCHANGED — these all exercise `head_match`'s live-cell branch, `globals_env._walk_head`'s cell branch, and `list_dispatch`'s gate helpers, all three of which ALREADY read slot 0 raw before this task (per the pre-flight scan cited in the task prompt). Task 5's consolidation of these three sites onto `cells._cell_shape` (the carry-forward ruling) is argued to be behavior-PRESERVING in the report; the full-suite gate (144 failed / 11982 passed, name-diff empty modulo the C17-perf flake) is the evidence that held.
