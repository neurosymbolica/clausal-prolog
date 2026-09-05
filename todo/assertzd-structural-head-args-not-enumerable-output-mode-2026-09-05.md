# Assertz'd structural head args have no output mode (pre-existing, representation-neutral)

Filed at P3-2 close-out per project convention (Task 3 report §8, item 1;
ledger: "§8.1 residual"). Pre-existing before P3-2, applies equally to
`Compound`-headed and cell-headed facts, and now that cells are the default
representation (P3-2), applies to essentially every structurally-headed
`assertz`'d fact in the system.

## The residual

`_normalize_fact_clause` — the loading path for facts, whether `.clausal`
source-declared or `assertz`'d at runtime — passes a structural head argument
through **unhoisted**. The general mechanism that gives a structural head
argument output-mode binding (a caller with an unbound Var where the fact's
structure sits) is the compile-time hoist
(`_lift_clause_at_pos`/`_normalize_structural_head_args`,
`clausal/logic/compiler/list_dispatch.py`), and that hoist only runs on the
SOURCE-COMPILATION path. A fact loaded through `_normalize_fact_clause` never
goes through it, so its structural head argument can be matched against
(equality/unify on a ground structural caller) but never bound in output mode.

This is the root cause behind
`todo/partially-ground-cell-vs-raw-cell-head-equality-gap-2026-09-05.md` (the
specific cell-vs-Compound instance Task 3/Task 4 traced); this todo is the
general statement, kept separate because the fix (if ever made) is a hoist
change in the fact-loading path, not anything specific to cell recognition.

## Why it's representation-neutral

Verified directly (Task 3, `.superpowers/sdd/p32-cell-default-flip/task-3-report.md`
§8): a `Compound`-headed fact loaded the same way has never had output mode on
this argument either. The cell flip did not introduce this gap and does not
make it worse in kind — it just means the gap now applies to the DEFAULT
representation rather than to a class-instance representation most `.clausal`
programs never used directly.

## Why it's not fixed here

- Fixing it changes answers for existing `assertz`'d/fact-loaded programs
  using structural heads TODAY, independent of this phase — it is a genuine
  feature addition (teach the fact-loading path the compiler's own hoist),
  not a representation bugfix.
- No task in P3-1/P3-2 was scoped to touch fact-loading semantics.
- Cost of leaving it: a caller cannot enumerate a structurally-headed fact's
  sub-structure via an unbound argument — it can only match a fully (or
  partially, subject to the sibling equality-gap todo) ground query against
  it. This is a capability gap, not a correctness bug — no wrong answer is
  produced, only a missing one.

## Where to look

- `clausal/logic/predicate.py` (grep for `_normalize_fact_clause` — it has
  moved between files across phases) — the fact-loading path to teach the
  hoist to.
- `clausal/logic/compiler/list_dispatch.py` — `_lift_clause_at_pos`,
  `_normalize_structural_head_args` — the hoist mechanism itself.
- `todo/partially-ground-cell-vs-raw-cell-head-equality-gap-2026-09-05.md` —
  the specific instance this general gap explains; pick up together.
