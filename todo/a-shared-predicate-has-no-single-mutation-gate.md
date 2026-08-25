# A shared predicate class can be mutated through four channels; only one is guarded

**Filed:** 2026-08-26, from the aliased-import clobber (`adf95a31`).
**Status: OPEN.** Severity: high as a class — every unguarded channel is a
silent wrong answer for a module that did not consent to the change.

## What the alias bug proved

`-import_from` SHARES one `PredicateMeta` across modules — deliberately, and
load-bearing for the clause-free-vocabulary idiom. A load can then write to
that shared object through at least four channels:

| channel | where | guarded? |
|---|---|---|
| `_clauses[:] = …` | `compiler_v2` step 4, `import_hook` ×2 deferred | yes, by step 3c |
| `_dispatch_fn` | `compiler_v2` step 5 / `compile_predicate_*` | **no** |
| `_signature`, `_clauses_source` | step 4 and the deferred paths | no |
| `assertz` | `logic/database.py` | partly — `permission_error` on a static procedure |

The aliased-import bug went through the SECOND row while the first was
guarded, which is why the damage was invisible to a clause count: the owner's
`_clauses` still held its two clauses, and its own queries answered with the
importer's one. A guard on the clause list is not a guard on the predicate.

`assertz` is the related loose end already recorded when the refusal landed: it
appends to `_clauses` without updating `_clauses_source`, so a runtime-asserted
clause is attributed to the loading module in the diagnostic.

## Proposal

One gate — "this load may write to this predicate" — asked once and enforced at
every channel, rather than a check placed in front of whichever channel a bug
was last found behind. Options worth weighing: a `_writable_by(source_path)`
predicate consulted by each mutator; or making the mutators private to a small
module that owns the invariant.

Whatever the mechanism, provenance must be per-write, not per-load, so
`assertz` records its own author.

## Acceptance

- A test that mutates a shared predicate through EACH channel from a
  non-owning module and asserts the same refusal.
- The `assertz` attribution gap closed, or explicitly waived with its reason.

Related: [[predicate-identity-is-keyed-on-spelling-not-on-the-class]]
