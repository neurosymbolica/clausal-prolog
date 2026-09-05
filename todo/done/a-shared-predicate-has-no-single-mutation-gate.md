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

## Resolution (2026-09-05)

**CLOSED** by P3-3 Task 3, the mutation gate: `Database.mutate(functor, arity,
author=..., kind=...)` (`clausal/logic/database.py`) is a write transaction on
a `PredRow`; `write_refusal` beside it is the ONE policy — "may this author
write this row" — and `refusal_error` the ONE refusal.  All four channels of
the table above go through it:

| channel | routed at | surface exception |
|---|---|---|
| `_clauses[:] = …` | `compiler_v2` step 4 | `SyntaxError` (gate text appended to the redefinition diagnostic) |
| `_dispatch_fn` | `compiler_v2` step 5/6, `compiler._install`, `Database.set_dispatch` | `SyntaxError` at load; `RuntimeError` for a raw install outside a transaction |
| `_signature`, `_clauses_source` | written inside step 4's transaction | as above |
| `assertz` | `Database.assertz/asserta/retract`, `PredicateMeta._assertz/_asserta/_retract`, the `assertz/1` builtin family | `LogicException(permission_error(…))`; `RuntimeError` at the class surface |

The second row is closed structurally, not by a check: installing a dispatch
outside an open transaction RAISES, so a load cannot replace a shared
predicate's dispatch on the quiet.  The `permission_error` on `Database.assertz`
is new — that door had no lock check at all.

Provenance is per WRITE: each transaction stamps `row.writes` with its author
and kind, and a runtime assert writes as `runtime-assert:<module>` rather than
inheriting the load's authorship, which closes the attribution gap this todo
recorded.

Tests: `tests/test_mutation_gate.py` (18, including one per channel refused
from a non-owner with the same text, both dispatch doors, and the provenance
pair), plus the flipped
`tests/test_predrow.py::test_low_level_db_assertz_is_refused_on_a_locked_static_predicate`.
See `.superpowers/sdd/p33-state-relocation/task-3-report.md`.
