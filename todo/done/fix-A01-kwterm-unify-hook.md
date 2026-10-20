# fix-A01: KWTerm has no __unify__ — Var fields never bind (A01-F004)

**Severity: correctness.** `KWTerm` (`terms.py:107-189`) documents
"Equality and **unification** match by keyword name", but defines no
`__unify__`, so C `do_unify` falls through to rich-compare (`_variables.c:1379`)
and Var-valued fields compare by identity instead of binding:

```python
Y = Var()
unify(KWTerm("r", a=Y, b=2), KWTerm("r", a=1, b=2), t)  # False — should be True, Y=1
```

## Fix

Add to `KWTerm`, mirroring `DictTerm.__unify__` (`terms.py:1411-1433`):

```python
def __unify__(self, other, trail):
    if not isinstance(other, KWTerm):
        return NotImplemented
    if self._functor != other._functor or self._fields.keys() != other._fields.keys():
        return False
    from .logic.variables import unify
    mark = trail.mark()
    for k in self._fields:
        if not unify(self._fields[k], other._fields[k], trail):
            trail.undo(mark)
            return False
    return True
```

Consider `__occurs_check__` and `__walk__` in the same change (see
fix-A01-occurs-check-compound-blindness.md and A01-F008) so KWTerm gets the
full protocol trio at once.

## Verify

Flip `TestF004KWTermUnify::test_kwterm_var_field_binds` xfail to a plain
assert; controls in the same class must stay green.
