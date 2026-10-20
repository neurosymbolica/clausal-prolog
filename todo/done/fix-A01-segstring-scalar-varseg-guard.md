# fix-A01: SegString VarSeg bound to non-str scalar fails silently (A01-F009)

**Severity: error-path.** The F024 guard in `SegString.__walk__`
(`terms.py:810-816`) raises a typed `PartialTermError` when a VarSeg is bound
to a non-char-**list**, but a VarSeg bound to any other non-str value (int,
Compound, …) falls into the else-branch (`terms.py:838-840`) which keeps
`VarSeg(v)` with a **non-Var** payload — the term is stuck non-ground
forever, every unify silently fails, and `repr` shows nonsense
(`SegString(['a', VarSeg(var=5)])`):

```python
Z = Var(); unify(Z, 5, t)           # reachable via plain unification
SegString(["a", VarSeg(Z)]).__walk__()   # no error, silent limbo
```

SegList's else-branch (`terms.py:320-322`) and SegBytes' (`terms.py:1167-1168`)
have the same shape; for SegList a scalar binding is equally a contract
violation (VarSegs bind to sequences).

## Fix

In each `__walk__` else-branch, distinguish "still an unbound Var" from
"bound to an out-of-contract value":

```python
else:
    from .logic.variables import is_var
    if not is_var(v):
        raise PartialTermError(
            f"SegString VarSeg bound to non-str value: {type(v).__name__} "
            f"({v!r}); VarSegs of a SegString must bind to str."
        )
    new_segs.append(VarSeg(v))
```

(SegList wording: "must bind to list/str"; SegBytes: "must bind to bytes".)

## Verify

Flip `TestF009SegStringScalarBinding::test_scalar_varseg_binding_raises_partial_term_error`;
the char-list-guard and construction-guard controls stay green.
