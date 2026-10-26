# Unifying two frozen variables runs one side's goal

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
