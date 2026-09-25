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

## Resolved 2026-09-25 (fix/call-runs-special-form-cells-2026-09-25)

Both halves:

- Term position: `G is findall(X, p(X), L)` (and every other special form,
  `call_body.SPECIAL_FORMS`) builds the cell `("findall", X, ("p", X), L)`
  (`terms_to_ast._goal_cell_functor`).  So does a name bound to a
  non-callable `_get_dispatch` goal object such as py.re's `match`.
- Runtime: `call/N` of such a cell (after the fold) is compiled back to the
  same `Call` node the clause body holds and run through the query compiler
  (`call_body.special_form_dispatch`); the goal arguments are `call/1` of
  their term, as ISO defines these forms.  A ModulePredicate cell resolves
  through the binding's `_get_dispatch` (`higher_order._goal_object_dispatch`).
- On the way: `throw/1` now raises a COPY of the ball, and
  `instantiation_error` for an unbound one (ISO 7.8.10), and `halt(X)` exits
  with X's value rather than the Var.

Tests: `tests/test_call_runs_special_form_cells.py`.
