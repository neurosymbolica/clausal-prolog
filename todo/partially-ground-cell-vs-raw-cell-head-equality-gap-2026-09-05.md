# A ground cell asserted as a clause head loses output-mode binding (both routes)

Found during P3-2 Task 3 (self-review §8, item 1) and re-confirmed by the Task 4
reviewer as still open (their Observation 1) after Task 4's indexing work landed.
Predates both tasks; this is Task 3 territory (`_normalize_fact_clause` /
`_lift_clause_at_pos`), filed here per the close-out convention.

## The gap

A structural clause head asserted via `assertz/1` — cell or `Compound`, it does
not matter which — never gets an OUTPUT-MODE binding on the argument the head's
own structure occupies. Compare (from the Task 3 report's four-row table,
`.superpowers/sdd/p32-cell-default-flip/task-3-report.md` §"What I chose, and
why"):

| head arg | input mode `qq(42, K)` | matching `qq(('pt',1,2), K)` | **output mode** `qq(X, K)` |
|---|---|---|---|
| `Compound('pt', (1, 2))` | `['catchall']` | `['yes', 'catchall']` | `['catchall']` (no bind) |
| cell `('pt', 1, 2)` | `['catchall']` | `['yes', 'catchall']` | `['catchall']` (no bind) |

Both representations agree — that parity is exactly what Task 3 fixed (before
its fix, the CELL row disagreed, binding in output mode by accident; see below).
The remaining gap is that NEITHER representation supports output-mode
enumeration over a loaded, structurally-headed fact — a caller with an unbound
variable where the fact's own structure sits gets the catchall answer, not a
bound match.

## Mechanism

`_normalize_fact_clause` (loading path for `assertz`'d and `.clausal`-declared
facts alike) passes a structural head argument through UNHOISTED — it is never
lifted into a bucket-pattern clause the way a *source-compiled* head with the
SAME shape is. The general mechanism that WOULD give output mode to a
structural head argument is the hoist (`_lift_clause_at_pos` +
`_normalize_structural_head_args`), and the hoist only runs on the
source-compilation loading path, not the runtime-assert path.

This is representation-neutral: it costs `Compound`-headed facts output mode
today, for the identical reason. Task 3 did not create it and did not extend
it — it only made the cell row match the (already output-mode-less) `Compound`
row instead of diverging from it via an accident of branch ordering (see next
section).

## Why this is a *behavior change on record*, not a new bug

Before Task 3's fix, a GROUND cell head arg asserted this way rode the
`$headlit` capture-and-unify path (added for a different purpose — accepting
opaque literals wholesale) and so incidentally bound an unbound caller. Task 3
replaced that with a proper structural sequence pattern, which is correct
input-mode/matching behavior but does NOT bind in output mode — bringing the
cell row into agreement with the `Compound` row, which never had output mode on
this path. No test in the suite pinned the old (accidental) output-mode
capability; the full-suite name-diff around the change was EMPTY.

## Why it's parked here rather than fixed

- Fixing it means teaching `_normalize_fact_clause` to hoist structural head
  arguments the same way source compilation does — a real feature addition,
  not a bugfix, and it would change answers for existing `Compound`-headed
  `assertz`/fact-loaded programs today (before this phase existed).
- It affects both representations equally; there is no cell-specific reason to
  fix it as part of the cell-representation work, and P3-2's task briefs never
  scoped it.
- See also `todo/assertzd-structural-head-args-not-enumerable-output-mode-2026-09-05.md`
  for the general "output mode on assertz'd structural head args" residual this
  gap is one instance of — that todo and this one share the same root cause and
  should probably be picked up together.

## Where to look

- `clausal/logic/predicate.py` (or wherever `_normalize_fact_clause` currently
  lives — grep, it has moved before) — the loading path that skips the hoist.
- `clausal/logic/compiler/list_dispatch.py` — `_lift_clause_at_pos`,
  `_normalize_structural_head_args` — the hoist mechanism structural facts
  would need routed through.
- `tests/test_tagged_terms.py::test_the_cell_and_compound_rows_agree_in_every_argument_mode`
  (Task 3) — the four-row parity pin; a fix here would need a fifth row.
