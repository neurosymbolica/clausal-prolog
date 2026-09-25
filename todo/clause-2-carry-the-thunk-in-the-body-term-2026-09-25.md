# clause/2: carry a variable-reading PyThunk in the Body term? (parked)

Parked 2026-09-25 (feat/clause-2-2026-09-25).  The operator is undecided, so
the shipped behaviour stays.

## Today

A clause whose body holds a `PyThunk` that reads clause variables (`++(X+1)`,
`f"v{Y}"`, the goals regex auto-binding generates) has no term form.  Building
it would evaluate the closure with its variables unbound (`f"v{Y}"` builds
`'v_0'`), so `clause/2` refuses the clause when its head matches:

```
fs(1, Y) <- (Y is f"v{Y}")
?- clause(fs(1, Y), B).
error(permission_error(access, private_procedure, fs/2),
      'clause/2: fs/2 has a clause whose body has no term form -- ...')
```

(`clausal/logic/builtins/clause_ops.py`: `_capturing_thunk`, `_full_built`.)

## The alternative

Put the thunk object itself in the Body, with its variables renamed like the
rest of the answer, and teach call/1's converter to run it as code rather than
lift it into a parameter:

```python
# clause_ops: during construction, leave the thunk unevaluated -- replace it
# with a parameter Var bound (on the private trail) to the PyThunk OBJECT --
# then, after _copy_term(..., var_map), re-point the copy's thunks:
def _rename_thunks(t, var_map):
    if isinstance(t, PyThunk):
        return PyThunk(t.fn, [var_map.get(id(v), v) for v in t.var_objects])
    ...                                   # walk lists/tuples/node fields

# call_body._Converter.arg: a thunk is code, like a Call or a Lambda
        if isinstance(t, PyThunk):
            return t          # term_to_ast_expr's PyThunk arm evaluates it
```

What that buys: f-string, `++` and regex clauses round-trip through
`clause/2` + `call/1`.  What it costs: the Body holds a Clausal-only object
that is not a Prolog term.  It does not unify with anything a program can
write, it prints as `PyThunk(<lambda>, ...)`, and `copy_term` does not rename
inside it (that is why `_rename_thunks` is needed).  It also changes step 1
(`call_body`).

Decide: keep permission_error, or carry the thunk.
