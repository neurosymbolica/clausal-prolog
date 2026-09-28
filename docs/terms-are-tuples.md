# A compound term is a tuple

**P2, 2026-09. What a downstream reader of a term needs to know.**

A compound data term is a **cell**: the functor-first tuple `(name, *args)`.

```python
point(1, 2)        # -> ('point', 1, 2)
BoolEq(X, Y)       # -> ('BoolEq', X, Y)
```

It used to be an instance of a `PredicateMeta` class, and anything that read
`term.x` or `type(term)` is reading the old shape.

## Reading one

**Positions, not attributes.**

```python
from clausal.logic.cells import compound_cell_shape, cell_args

is_cell, functor = compound_cell_shape(term)
if is_cell:
    args = cell_args(term)          # or term[1:]
```

**Field NAMES come from the declaration, not the term** — a tuple has no field
names. Ask the database:

```python
fields = db.signature_for(functor, len(args))
```

## Three things that bite

1. **A cell is a tuple, so anything that treats a tuple structurally now
   catches terms.** `isinstance(x, tuple)`, `len(x) == 2`, `a, b = x` — a
   generic tuple branch placed ahead of a specific one will swallow a term.
   Put the specific branch first.
2. **`getattr(term, "field", default)` answers the DEFAULT.** It does not
   raise. The caller proceeds with a wrong-but-plausible value and nothing
   reports it. Read positions, or fail loudly.
3. **A type test must ANSWER, not raise.** `compound_cell_shape` refuses the
   reserved 1-tuple `('x',)`. A predicate that sits in a dispatch chain has to
   handle that and answer False rather than propagate.

## What has NOT changed

* **`m.pred(X)` still works.** The class is still the predicate handle, and a
  module attribute still resolves to it. That goes in P4, not here.
  **Update 2026-09-25: it has gone.** P4's flip (main `e107929e`) binds every
  module attribute for a predicate to the owner's handle, a `str`, so
  `m.pred(X)` is now `TypeError: 'str' object is not callable`. From Python,
  run a plain cell against the module: `solve(("pred", X), module=m)` — see
  [Querying from Python](python_integration.md#querying-from-python).
* **A clause HEAD is still an instance** on the one internal channel that
  builds it (`PredicateMeta._clausal_head`). Also P4.
* **Atoms are unchanged**: an atom is the interned `str`, a string is the
  `('$chars', s)` carrier. See the atoms announcement.
* `KWTerm` still exists and is still read the old way (the `Compound` class
  was removed, 2026-09-27).

## Measured

Loading the 37 `tests/fixtures/docs/*.clausal` fixtures:

| | live term INSTANCES | `PredicateMeta` classes |
|---|---|---|
| before P2 | 534 | 574 |
| after P2  | **0** | 574 |

Classes are unchanged **by design** — they are the predicate handle until P4.
What P2 removed is the instance.
