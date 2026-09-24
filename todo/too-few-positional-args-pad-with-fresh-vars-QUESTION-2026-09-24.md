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
