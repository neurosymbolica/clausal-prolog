# Unifying two frozen variables runs one side's goal

**Status: FIXED 2026-10-27 (fix/freeze-alias-merge-2026-10-26).** `_freeze_hook` merges the goals onto the surviving variable when bound to an unbound one. Pinned by `tests/iso/test_freeze_alias_merge_scryer.py` and `tests/test_coroutining.py::TestFreeze::test_bare_unify_of_two_frozen_vars_merges`. Remaining differences from Scryer (by design or cosmetic, recorded in that test): a when/2 waiting on both aliased variables runs once (Scryer runs and prints it twice); three aliased freezes print left-nested (Scryer nests by alias order); freeze vs when goals on one variable run in posting order (Scryer runs freeze goals first).

Found 2026-10-26 while making `-g` print pending `freeze/2` goals.

When both variables of a variable-variable unification carry a `freeze`
attribute, one variable is bound to the other and its hook queues its
goals: they RUN, where Scryer merges the two delays and runs nothing
(`freeze/2`'s `verify_attributes` rescues the conjunction onto the other
variable):

```prolog
?- freeze(X, write(a)), freeze(Y, write(b)), X = Y.
% Scryer:  X = Y, freeze:freeze(X,(write(a),write(b))).
% Clausal: prints b, then  Y = X, freeze(X,write(a)).
```

With only one side frozen the attribute survives (`freeze(X,g), X = Y`
gives `Y = X, freeze(X,g)`). The fix belongs in `_freeze_hook`
(`clausal/logic/coroutining.py`): when `bound_to` is an unbound variable,
append the goals to its `freeze` attribute (trailed) instead of queueing
them. A wake-semantics change, so it was left out of the residual-printing
work; the printed residual would then come out right by itself.
