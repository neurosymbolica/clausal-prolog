# DECISION NEEDED: short positional construction pads -- and DCG depends on it

Companion to `todo/too-few-positional-args-pad-with-fresh-vars-2026-09-24.md`
(filed on `feat/drop-vocabulary-implements-2026-09-24`, not on main yet;
kept as a separate file so the two branches do not add/add-conflict).
Measured on main a5c4fab8, 2026-09-24, branch fix/small-todos-batch-2026-09-24.

## Reproduction (reproduces on main, no vocabulary-drop needed)

```
-module(pad5, [v(STATUS, CITATION), mk(T)])
-private([ok, cited, solo])
v(ok, cited),
mk(T) <- (T == v(solo))
```
```
v('solo')         -> ('v', 'solo', AttVar(_4))           # pads, no error
v('a', 'b', 'c')  -> ClausalTermConstructionError ...     # overflow raises
mk(T)             -> the body builds ('v', 'solo', AttVar) (seen in the
                     type_error the == raises)
```
Same for a DATA functor (`-module(pad5d, [w(A, B), ...])`, `w(solo)` ->
`('w', 'solo', AttVar)`), at compile time (`terms_to_ast._place_signature_slots`)
and at run time (`PredicateMeta.__call__`).

## Who relies on the padding (measured: made BOTH sites raise on
`0 < len(args) < len(fields)` with no keywords, then reverted)

* 26 targeted files (construction/cells/functor/reflection/specialization/
  term_expansion ...): 1088 passed -> 2 failed. Both are PINS of the padding:
  `test_functor_arity_conflict.py::TestPositionalOverflowRaises::test_partial_positional_still_fills_with_vars`
  and `test_predicate_arity_mismatch_diagnostic.py::TestTermConstructionUnaffected::test_partial_term_in_argument_position`.
* `tests/test_dcg.py` + `test_chars_carrier.py`: 141 passed -> 24 failed,
  13 errors. **DCG is load-bearing on it**: `phrase(count_leaves(T), [0], [N])`
  names a //1 nonterminal whose class is /3; the padded cell
  `('count_leaves', T, _, _)` is what `dcg._phrase_cell_goal` expects -- it
  drops the last two slots (`rule_val[1:-2]`) and supplies its own S0/S.

## Candidate behaviours

**A -- keep padding (status quo), document it as the DCG device.**
```
v('solo')  -> ('v', 'solo', _)          phrase(count_leaves(T), ...) works
```

**B -- raise like overflow.** Needs DCG to stop relying on it first (the
nonterminal-as-argument would have to be built at its WRITTEN arity -- C --
or phrase would have to accept a short term).
```
v('solo')  -> ClausalTermConstructionError: functor v/2 was constructed with 1 positional argument(s) ...
```

**C -- build the term at its WRITTEN arity (ISO; the name+arity ruling of
2026-09-24: "a predicate name is name+ARITY").**
```
v('solo')  -> ('v', 'solo')             # the compound v/1; no pad, no error
phrase(count_leaves(T), S0, S)          # phrase would call count_leaves/3 by
                                        # APPENDING S0, S (ISO call/N), not by
                                        # dropping two padded slots
```
C changes `dcg._phrase_cell_goal` (`rule_val[1:-2]` -> `rule_val[1:]`) and
un-pins the two tests above; the class-era `PredicateMeta.__call__` would
stop being the constructor for a short term.

Recommendation: C (it is what the name+arity ruling implies, and it removes
the only reason for A); B is not viable on its own. Not applied: it changes
term identity for every short construction, which is an operator call.

## Resolved (2026-09-24, operator ruling C; branch fix/small-todos-batch-2026-09-24)

A term is built at its WRITTEN arity; nothing pads.

* **Data functor** (declaration fixes the slots): too few positional args is
  refused exactly like too many -- compile time (`terms_to_ast._place_signature_slots`,
  shared by construction and `head_match` patterns) and the runtime class call
  (`PredicateMeta.__call__`, unless keywords fill the rest).
* **Predicate name** (name+arity: one name, several arities): a short
  construction is the compound at the written arity
  (`cell_signature_for_name(..., arity=n)` answers that arity's own slots;
  both construction and head-pattern sites ask again at the written arity).
  `phrase(count_leaves(T), ...)` builds `('count_leaves', T)`.
* **phrase/2,3** append S0/S to the cell's written args (`rule_val[1:]`,
  ISO call/N) instead of dropping two padded slots; a bare atom or handle
  nonterminal goes through `_resolve_named_goal` too.

Tests: `tests/test_written_arity_construction_both_eras.py` (phrase through the
class and a `mint_predicate_handle` binding). Pins flipped with notes:
`test_functor_arity_conflict` (partial positional), `test_tagged_terms`
(construction + head pattern + the partial-head indexing class, whose xfail
defect -- `todo/done/indexed-dispatch-drops-partial-head-references-2026-09-05.md`
-- can no longer be written), `test_goal_position_seam` (`pair(a, _)`),
`test_import_path_canonicalization` (`sole_verdict(ok, _)`),
`test_call_n_dangling_handle_raises` (written-arity nonterminal), `test_dcg`
(Python-side nonterminal terms built by name via `_nt`, since `cls(v)` on a
//N class now raises). test_dcg: 141 passed.

Mutations (each reverted): compile short-raise off -> 4 fail; predicate
written arity off -> 4 fail + 19 errors; runtime short-raise off -> 2 fail;
phrase back to `[1:-2]` -> 33 fail; head_match retry off -> 1 fails.

Not done (pre-existing, flipped era): a HANDLE-bound predicate name has no
construction lowering at all (`cell_signature_for_name` finds no fields on a
handle, so `tok(z)` lowers to a call of the str) -- independent of ruling C.
