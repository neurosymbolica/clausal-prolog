# Bug: defining a clause for an IMPORTED functor destroys the exporter's clauses

**Reported:** 2026-07-29, found while fixing the functor import-ordering defect
(`todo/done/functor-field-name-mismatch-diagnostic.md`).
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
`todo/done/module-reexport-imported-functor-shadows.md`, which established that
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

---

## FIXED — 2026-08-25

Branch `fix/imported-functor-clause-list-2026-08-25`.

### Decision on the open design question: **option 2, refuse at load time**

Recorded here because the todo asked for it to be decided rather than assumed.

**Why not option 1 (extend).** The clause list is not what answers a goal.
`compile_module` step 5 compiles ONE dispatch function from ONE clause list
against ONE `globals_` mapping (`globals_=module_dict`). A merged clause list
would mean compiling the exporter's clause bodies — written against *its*
`-private` atoms and *its* imports — in the importer's scope. A merged clause
list with an unmerged dispatch function is the same silent-wrong-answer bug
wearing a different hat, and would be strictly harder to find.

**Why not "give the importer its own predicate" (option (c) as posed in
`todo/imported-clause-refusal-misattributes-ownership.md`).** The shared class
is load-bearing for the idiom the corpus actually uses: a clause-free export
implemented downstream, where a *third* module importing the vocabulary must
reach the implementer's clauses (live in two downstream rulebase modules). Splitting the
predicate per module breaks that, and would mean making dispatch per-module —
`_get_dispatch()` is a frozen duck-typed protocol with ~22 implementors outside
this tree.

**Why not option 3 (`-multifile`).** It would be a new directive whose only
correct implementation is option 1, which is unavailable for the reason above.
Nothing stops it being added later; refusing now is forward-compatible.

**Corpus sweep (2026-08-25, redone rather than trusted).** 767 `.clausal` files
over this repo (including `packages/`) plus the downstream rulebase corpora and
library available on this box. Live instances of "imports N and defines a clause
for N": two downstream modules, each importing a 0-arity vocabulary atom
(`dependents_count`, `query_date`) — both the 0-arity vocabulary-atom
shape, both with a **clause-free** exporter. The `packages/clausal-provenance`
fixtures that a textual sweep flags (`bottom_up_`) are false positives:
`bottom_up_` is a `_RegistrationGoal` instance, not a `PredicateMeta`, and
`bottom_up_(Edge)` is a module-level goal, not a clause head. Both live domain
modules were confirmed to still import cleanly after the fix.

So the refusal is narrowed to functors that **already have clauses**. A
clause-free export is a declaration; supplying its clauses downstream keeps
working.

### What landed

- `PredicateMeta._clauses_source` — `(module_name, source_path)` of the load
  that last wrote `_clauses`. Set at all three sites that assign the clause
  list wholesale (`compiler_v2` step 4 and the two deferred paths in
  `import_hook`) via `predicate.record_clause_source`.
- `compiler_v2` **step 3c**, `_reject_redefinition_of_imported_predicates` —
  runs BEFORE step 4 mutates anything, so a refusal never leaves a half-clobbered
  clause list.
- `import_diagnostics.describe_imported_predicate_redefinition` — names the
  module that actually supplied the clauses, which is **not** always the
  exporter. See the companion todo.
- `tests/test_imported_functor_clause_clobber.py` (11 tests) plus five
  `tests/fixtures/impclob_*.clausal`.
- `tests/audit_2026_07_05/test_10_rewriting_import.py::test_F004_local_clause_does_not_clobber_imported_predicate`
  un-`xfail`ed (same bug, found by the A10 audit).
- `docs/import.md` §"One defining module per predicate".

### The "before fixing" checklist, answered

- **Corpus sweep** — done, above. Option 2 breaks nothing.
- **Re-export idiom unaffected** — confirmed: a re-export has no local clause
  head, so `predicate_nodes` never carries the functor and step 3c never looks
  at it. `tests/test_functor_reexport.py` and
  `tests/test_functor_import_ordering.py` pass unchanged.
- **Runtime `assertz` against an imported functor** — NOT affected. It already
  raises `permission_error(modify, static_procedure, F/N)`, even when the
  exporter declares `-dynamic`. Now pinned by a test so it stays that way.

### Known limits (deliberate, not oversights)

- `Database.assertz` appends to `pred_cls._clauses` without updating
  `_clauses_source`, so a runtime-asserted clause is counted in the diagnostic
  under the *loading* module's name. Only reachable inside the owning module's
  own process; harmless, and the alternative (per-clause provenance) is a much
  larger change.
- If a module has no `__file__`, ownership cannot be compared and the refusal
  fires. Conservative on purpose: the alternative is the silent destruction
  this fixes.
