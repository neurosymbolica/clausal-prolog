# findall/once/catch/forall/throw/eval_ cannot be built as terms

Parked 2026-09-25 (call-runs-body-terms, step 1 of the ISO clause/2 plan).

These are compiler special forms with no term class, so building one in term
position fails at run time, before any call:

```
g(G, X, Y) <- (G is findall(X, p(X), Y))
% NameError: Predicate 'findall/3' is not in scope as a term class.
```

Same for `once/1`, `catch/3`, `forall/2`, `throw/1` and `eval_/2`.  So
clause/2 cannot return a body that contains one: the body cannot be
represented as a term, and `call/1` never sees it.  (`call/1` itself would
run the cell `("findall", X, G, L)` only if a runtime builtin of that name
existed; none is registered -- `_BUILTINS`/`_DB_BUILTINS` have no
`("findall", 3)`, `("once", 1)`, `("catch", 3)`, `("forall", 2)`,
`("throw", 1)`, `("eval_", 2)`.)

Needed before clause/2 can reflect such clauses: a term spelling (the cell)
for each, and a runtime dispatch for the cell -- or a lowering of the cell to
the special form in `call_body._Converter.goal`.
