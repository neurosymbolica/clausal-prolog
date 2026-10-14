# unify_with_occurs_check through DictTerm and other __unify__ hooks builds cycles

Since e9ff13e7 the C unifier sets `trail.unify_oc` while a term's `__unify__`
hook runs for an occurs-checked unification, and the SegList hook binds its
parts with `_seg_unifier(trail)` (clausal/terms.py). The other hooks still
bind their parts with plain `unify`, so `unify_with_occurs_check` builds the
cycle it exists to refuse:

```python
from clausal.logic.variables import Var, Trail, unify_with_occurs_check, deref
from clausal.terms import DictTerm
x = Var(); t = Trail()
unify_with_occurs_check(DictTerm({"k": x}), DictTerm({"k": ("g", x)}), t)
# -> True, and deref(x)[1] is x   (control: [x] vs [("g", x)] -> False)
```

Scryer has no dict term; the ISO rule (8.2.2) is that the unifier fails
rather than bind a variable to a term containing it.

Hooks that bind parts with plain unify (clausal/terms.py unless noted):
- `DictTerm.__unify__`: each value pair.
- `SegListView.__unify__`: `unify(self.elements(), ...)`.
- `quantity.__unify__`: `unify(self._value, other._value)`. A value is usually
  a number, so this is low risk.
- `clausal/pythonic_ast/nodes.py`: two hooks, at lines 189 and 233.
- `SetTerm.__unify__` compares ground elements with `==`, so it needs nothing.
- SegString and SegBytes bind holes to ground text or bytes, so they need nothing either.

Fix direction: replace `from .logic.variables import unify` in each hook with
`unify = _seg_unifier(trail)`, perhaps renamed to something like
`_hook_unifier`, since it is no longer only about segments. Add one bare test
per hook, mutation-checked, as tests/test_value_pattern_keeps_every_split.py
does for the SegList sites.
