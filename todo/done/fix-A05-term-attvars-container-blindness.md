# fix-A05: term_attvars/2 blind to tuples, dicts, sets, Seg* (A05-F004)

**Severity: correctness (low).** `_collect_attvars`
(`clausal/logic/builtins/attributes.py:125-146`) recurses into list /
Compound / term-instance / DictTerm only. Attributed variables inside a
**tuple** (a core Clausal structure), plain dict, set, or Seg* term are
not reported:

```python
put_attr(V, "k", 1, t)
term_attvars((V,), Out)   # Out = [] — should be [V]
```

## Fix

Add `tuple` (trivial), plain `dict` (values, mirroring the DictTerm
arm), `set`/`frozenset`/`SetTerm` (elements), and Seg* segments to the
walk. Ideally share one traversal helper with
`constraints._collect_free_vars` once fix-A05-dif-collect-free-vars-
container-blindness lands — the two walkers currently have overlapping
but different blind spots.

## Verify

Flip `TestF004TermAttvarsBlindSpots` xfails to plain asserts; the
list/Compound/DictTerm/bound-var controls must stay green.
