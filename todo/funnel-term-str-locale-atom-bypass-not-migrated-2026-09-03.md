# P3: terms.py's term_str locale-rendering branch still hand-rolls the atom check

Found by `tests/test_funnel_lint.py` (Phase 1 funnel guard, task 4 of
`docs/superpowers/plans/2026-09-03-phase1-funnel.md`) while inventorying
every `isinstance(X, PredicateMeta) and not X._fields` site in the runtime
tree to build the lint's allowlist.

`clausal/terms.py` `term_str()`, inside its `style.locale is not None`
branch (~line 2441):

```python
if isinstance(t, type) and isinstance(t, PredicateMeta) and not t._fields:
    return _c(_locale_name(t.__name__, style), 'atom', style)
```

This is the exact hand-rolled "is this a zero-arity atom class" idiom that
`clausal.logic.predicate.is_atom` exists to replace — and the same block
already does `from clausal.logic.predicate import PredicateMeta,
is_term_instance, term_field_names` two lines above, so importing `is_atom`
alongside them and funneling this one check would be a small, local change.

It was never named in the Phase 1 site inventory (not in any Task 1-3 file
list, not in the plan's Global Constraints exclusion list) — it simply falls
outside terms.py's exclusion #7 line range (~180-280, a different concern:
`KWTerm._fields` being a dict rather than `PredicateMeta._fields`). Rather
than migrate it opportunistically outside the task's scope, it's parked here
and allowlisted (with this todo cited) in `tests/test_funnel_lint.py` so the
lint stays green.

## Suggested fix

Replace the three-clause `isinstance` chain with `is_atom(t)` (after
importing it in the same `if style.locale is not None:` block), add/extend a
`term_str` locale-rendering test asserting behavior is unchanged for a
zero-arity atom class, then drop the corresponding `ALLOWLIST` entry in
`tests/test_funnel_lint.py`.
