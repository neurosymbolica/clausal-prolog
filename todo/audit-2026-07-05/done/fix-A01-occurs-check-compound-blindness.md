# fix-A01: occurs-check blind to Compound / KWTerm / PredicateMeta instances (A01-F001)

**Severity: correctness.** `do_occurs_check` (`_variables.c:941-954`) traverses
tuples, lists, and anything with an `__occurs_check__` hook, then falls through
to `return 0`. `Compound`, `KWTerm`, and PredicateMeta-generated term classes
define no hook, so:

```python
X = Var()
occurs_check(X, Compound("f", (X,)))          # False — wrong
unify_with_occurs_check(X, Compound("f", (X,)), t)  # True — builds the cyclic
                                                    # term the oc exists to prevent
```

## Fix

Add `__occurs_check__(self, var)` to:
- `Compound` (`clausal/terms.py`) — recurse into `self.args` (and the functor
  slot if D004 lands on supporting Var functors);
- `KWTerm` — recurse into `self._fields.values()`;
- PredicateMeta (`clausal/logic/predicate.py`, next to `_make_unify`) — a
  generated `_make_occurs_check(fields)` recursing into field values.

Mirror the existing `DictTerm.__occurs_check__` shape (import
`occurs_check` lazily, return any()). Alternatively handle these types in C
next to the existing branches — but the Python hooks are the established
pattern and are also picked up by `do_occurs_check`'s delegation.

## Verify

Flip `TestF001OccursCheckBlindness` xfails to plain asserts in
`tests/audit_2026_07_05/test_01_term_layer.py` (run per-file).
