# `-implicit_functors` bucket-lift gate is OWA-unaware (safe, but unindexed)

Filed at P3-2 close-out per the ledger (Task 6 minor, deferred). P3-2 Task 6
shipped `-implicit_functors` (ruling R7) — the net-new per-module OWA
directive for functor construction/matching (`docs/directives.md`
§"-implicit_functors"). This todo covers a coverage gap in how OWA-unknown
functors interact with first-arg indexing, not a correctness bug.

## The gap

The bucket-lift gate (`clausal/logic/compiler/list_dispatch.py`,
`_lift_clause_at_pos` and the deep-gate flag computation
`_lifted_head_arg_needs_deep_gate`/`_nested_term_carries_a_literal` added in
Task 4) has no awareness of `-implicit_functors`/OWA at all. A clause head
whose structural argument is an OWA-unknown functor (one with no registered
signature, reachable only because the module carries `-implicit_functors`)
never gets lifted into an indexed bucket pattern — it always falls to the
default (all-clauses) bucket and is matched by the ordinary runtime `unify()`.

## Why it's safe as-is

The all-clauses fallback is exactly the same code path a shallow first-arg
index miss already falls back to — it is CORRECT, just unindexed. An
OWA-unknown functor head arg is matched via full runtime unification, which
handles every argument mode (ground, partially ground, unbound) correctly; it
simply does not benefit from the `(functor, arity)` bucket-key dispatch that a
declared or default-signature functor gets. No wrong answer is possible from
this gap — only a missed optimization.

## Why it's not fixed here

- OWA-unknown functor references are, by construction, ones the compiler
  cannot resolve a signature for at compile time — which is exactly the
  information the indexing machinery needs to build a specific bucket key in
  the first place. Making OWA-unknown heads indexable would need either a
  compile-time-resolved fallback signature (defeating the point of OWA) or a
  more elaborate runtime specialization pass — out of scope for a
  directive-shipping task.
- `-implicit_functors` is default OFF and is explicitly an escape-hatch
  directive for prototypes/meta-programming, not the hot-path default; the
  performance cost of an unindexed bucket for OWA-unknown heads is expected
  to be low in the programs that opt into it.

## Where to look

- `clausal/logic/compiler/list_dispatch.py` — `_lift_clause_at_pos`,
  `_lifted_head_arg_needs_deep_gate` (Task 4's deep-gate flag computation) —
  where an OWA-awareness check would need to be added if this is ever picked
  up.
- `clausal/logic/compiler/head_match.py` — `_implicit_functors_active` — the
  existing per-module OWA check to reuse, if a lift-time OWA branch is added.
- `tests/test_implicit_functors.py` — the OWA construction/matching test
  suite; a driven indexing test would belong alongside
  `tests/test_first_arg_index.py`.
