# Bug: defining a clause for an IMPORTED functor destroys the exporter's clauses

**Reported:** 2026-07-29, found while fixing the functor import-ordering defect
(`todo/functor-field-name-mismatch-diagnostic.md`).
**Severity: high — silent wrong answers, at a distance.**
**Pre-existing.** Confirmed on `/workspace/clausal` @ `b1af4889`, i.e. before the
positional-heads fix. That fix did not cause this; it *exposed* it, because the
shape was previously unreachable whenever field spellings differed (the keyword
head raised first).

## Symptom

A module that `-import_from`s a functor and then defines its own clause for it
**replaces** the shared class's clause list instead of extending it. The
exporter's own facts are gone — from the exporter's point of view, for queries
the exporter itself makes.

Merely *loading* an unrelated module silently changes another module's answers.

## Reproduction (verified, 2026-07-29)

`/tmp/clrepl/exp.clausal`:
```clausal
-module(exp, [colour(NAME)])
-private([red, green])
colour(red),
colour(green),
```

`/tmp/clrepl/ext.clausal`:
```clausal
-module(ext, [colour(NAME)])
-import_from(exp, [colour])
-private([blue])
colour(blue),
```

```python
from clausal.import_hook import _load_module
from clausal.logic.solve import solve
from clausal.logic.variables import Var

e = _load_module('exp', '/tmp/clrepl/exp.clausal')

def names(mod):
    out = []; X = Var()
    for _ in solve(mod.colour(X)):
        out.append(str(X.value))
    return sorted(out)

print(names(e))                                        # ['green', 'red']
x = _load_module('ext', '/tmp/clrepl/ext.clausal')
print(names(e))                                        # ['blue']   <-- red, green DESTROYED
print(x.colour is e.colour)                            # True
```

Observed:

| | result |
|---|---|
| exporter alone | `['green', 'red']` |
| after importer loads | `['blue']` |
| shared class identity | `True` |

Note the class identity is *correct* and intended — see
`todo/module-reexport-imported-functor-shadows.md`, which established that
sharing identity is the right behaviour. The bug is that the clause list on that
shared class is **assigned** rather than **appended to**.

## Why this is high severity

- **Silent.** No error, no warning. The exporter keeps working, with fewer
  clauses.
- **Wrong answers, not failures.** A missing clause is a lost solution. In this
  codebase that surfaces as `0 solutions` or a wrong verdict — historically the
  hardest failure mode to trace here (see the query-template atom-key bug,
  `todo/done/query-template-rebinds-atom-dict-keys.md`).
- **Action at a distance, load-order dependent.** The damage is done by whichever
  module happens to be imported, in whatever order. A domain can be correct in
  isolation and wrong in a package.
- **It contradicts a reasonable reading of `-discontiguous`** — authors
  legitimately expect to add clauses to a functor they imported.

## Open design question — extend, or refuse?

Not obvious, and it should be decided rather than assumed:

1. **Extend** (append to the exporter's clause list). Matches the Prolog
   intuition and probably what an author writing this means. But it mutates
   another module's predicate from outside — spooky, and cross-module
   `-discontiguous` is not currently a thing (the engine has no `-multifile`).
2. **Refuse at load time** — "you imported `colour/1`; define it in the module
   that owns it, or declare your own rather than importing." Safe, explicit, and
   consistent with the strict-atoms philosophy of making the surface checkable.
   Would need a check that this shape is not already relied on in the corpus.
3. Extend only under an explicit opt-in directive (a `-multifile` equivalent).

Given the engine has no `-multifile`, and given the *silent* nature is the actual
harm, option 2 is the cheapest correct answer and option 3 is the principled one.
**Whichever is chosen, the current silent-destruction behaviour is not
defensible.**

## Before fixing

- **Sweep the corpus for this shape** — a module that imports a functor and also
  defines a clause for it. If domains rely on it, option 2 breaks them and the
  answer must be 1 or 3. The positional-heads work found 7 modules using the
  declare-and-import re-export idiom, but a re-export has *no local clause head*,
  so those are a different shape and are probably not affected. Confirm that.
- Check whether `assertz` at runtime has the same behaviour against an imported
  functor.
- Note `tests/test_functor_reexport.py` is a deliberate tripwire for re-export
  class identity; a fix here must not disturb it.
