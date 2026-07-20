# `replace_subterm/4` — generic structural subterm-rewrite predicate

STATUS: OPEN (filed 2026-07-20). Prerequisite for the Clausal-AST mutation
auditor (Approach B: the operator catalog rewrites one matched subterm of a
reified clause and rebuilds the clause term). Lower-criticality than the
renderer — see "Can this live in tooling?" below.

## Deliverable
A predicate in the reflection stdlib (`clausal/modules/reflection.py`):

    replace_subterm(TERM, OLD, NEW, RESULT)

**Semantics:** `RESULT` is `TERM` with ONE occurrence of a subterm unifying `OLD`
replaced by `NEW`; **nondeterministic over occurrences** — each solution rewrites
a different single occurrence (so a caller enumerating solutions gets one
single-site edit per solution, which is exactly one mutant per site). Depth-first
occurrence order, consistent with the existing `reified_subterm/2` walk
(reflection.py:136-159) so the two compose predictably.

Must preserve structure and variable sharing everywhere *except* the rewritten
occurrence (use `copy_term`/`functor`/`unpack` discipline; do not accidentally
alias or over-rename siblings). Deterministic accessor cousins already in the
module: `clause_head/2`, `clause_body/2`, `goal_functor/3`, `reified_subterm/2`.

## Why it belongs in the engine
It is a general-purpose AST-rewrite primitive (refactors, autofix, term
templating), the natural write-side companion to the read-side `reified_subterm/2`.
It is built entirely on existing builtins (`functor/3`, `arg/3`, `unpack/2`,
`copy_term/2` — all in `clausal/logic/builtins/inspection.py`), so it's a small,
self-contained stdlib addition (optionally C-accelerated later).

## Acceptance
- `replace_subterm(f(a,g(a)), a, b, R)` enumerates `R = f(b,g(a))` then
  `R = f(a,g(b))` (two occurrences → two solutions, DFS order).
- Replacing at a nested position leaves the rest byte-structural-identical
  (round-trip via the reified-term renderer re-reifies equal except the one site).
- Variables in unaffected positions keep their identity (no spurious renaming).
- Zero occurrences → no solutions (fails cleanly, not an error).

## Can this live in tooling instead?
Yes — it can be prototyped in the mutation-auditor's own `.clausal` module using
only the existing `functor/arg/unpack/copy_term` builtins, with no engine change.
File it here because it's a clean, reusable stdlib primitive and the engine is the
right long-term home; but if you'd rather not touch the engine now, the auditor
can ship its own `replace_subterm/4` and this todo becomes "promote it to stdlib."
The **renderer** (`reified-term-to-source-renderer.md`) is the hard engine
prerequisite; this one is promotable-from-tooling.
