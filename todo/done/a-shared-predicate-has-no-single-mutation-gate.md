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

### Correction (fix round 1, 2026-09-05)

The first closure note above claimed more than the code did. Review found
three holes, all now fixed and pinned in `tests/test_mutation_gate.py`:

* **A refused load could still write.** The gate was consulted inside the
  write loop, so a load that legally implemented one export and then tried to
  redefine another left the first write behind on the exporter's shared class.
  The policy is pure, so the load now dry-runs it over every predicate it is
  about to write (`Database.refusal_for`, `compiler_v2` step 3d) BEFORE
  writing any — the ordering property the deleted step-3c pre-pass carried.
* **A transaction that raised skipped the gate's exit**, leaving a written
  clause with a dispatch compiled from the old list and no stamp; and change
  detection was a clause COUNT, which one remove-plus-add transaction slips
  past. Stamping and invalidation moved into the unwind, and a clause-writing
  kind now invalidates unconditionally.
* **`recompile` was never refused — and it was the write that MOVED predicate
  identity.** `compiler._install` re-bound the class on every recompile, so an
  importer's `assertz` against a shared `-dynamic` predicate moved that class
  onto the importer's row: the OWNER's own query then answered from the
  importer's clause list. `PredicateMeta._bind_row` is policed now — a class
  already reading another Database's real row is not moved by a recompile, an
  install, or an importer's `-dynamic` declaration; only the clause install
  the gate has just cleared may move it — and the runtime-assert channels
  resolve to the row the class is bound to. One shared class, one clause list,
  both modules seeing every clause: the pre-P3-3 semantics, restored.
