# `replace_subterm/4` — generic structural subterm-rewrite predicate

STATUS: DONE (2026-07-20). Implemented as `replace_subterm/4` in
`clausal/modules/reflection.py` (recursive `_rewrites` walker + generator
predicate), with `tests/test_reflection_replace_subterm.py` (10 tests:
DFS-order enumeration, zero-occurrence clean fail, whole-term match, pattern-var
capture, unaffected-var identity, KWTerm/dict kinds, unbound-OLD, non-ground-var
semantics, and the end-to-end reified relop-swap). A Fable review confirmed the
trail/backtracking mechanics sound; its contract corrections are folded in
(occurrence-order claim scoped to the reified domain; the unbound-var guard
documented honestly; `_position` preserved on rebuilt Compound/KWTerm spines).
Full suite green (9817 passed). Original design notes follow.

**REQUIRED (not promotable-from-tooling)** for
the Clausal-AST mutation auditor's relop/structural operators — the earlier
"can live in tooling" note was WRONG; see "Why tooling can't do this" below.
The operator catalog rewrites one matched subterm of a reified clause and
rebuilds the clause term; for relops that subterm is an operator node sitting at
an unknown position in the clause's `goals` **Python list**, and rebuilding that
list position-preservingly is not expressible in tooling Clausal.

## Why tooling can't do this (probed 2026-07-20, op_node in hand)
Reified `Clause.goals` / `Goal.args` are **Python lists**, not Clausal cons
cells. Verified against a reified `f(X) <- (get(P,k,V), V >= 1)`:
- `[H|T]` head-pattern destructuring of `goals` → **fails** (0 solutions); a
  fixed-length pattern like `[OLD]` works, but a variable `| REST` tail does not.
- `append(Before,[X|After],Goals)` → **fails** (the mid-arg cons doesn't unify a
  Python-list slice). `member` is only `in_`/`X in Y`.
- `select/3` (global builtin) **works** on the Python list, BUT it is NOT
  position-preserving and `select/4` does not exist. A non-position-preserving
  replace REORDERS goals — and order is load-bearing: moving the comparison ahead
  of the `get/3` that binds its variable makes the mutant fail for the WRONG
  reason (unbound var), a spurious "killed" that hides a real survivor. So
  select-based replace is unsafe for the auditor.
`op_node/3` (DONE) correctly decomposes/constructs the operator NODE, but the
clause-`goals`-list rebuild around it is the blocker. A Python-side
`replace_subterm` traverses Python lists and preserves position trivially.

## Requirements sharpened by the above
- **Position-preserving**: `RESULT` keeps every non-target element in its original
  index (only the single matched occurrence changes).
- **Python-list-aware**: descends into reified `list` fields (`goals`, `args`)
  even though Clausal cons ops don't traverse them.
- **Operator-node-aware**: composes with `op_node` — the matched OLD may be a
  `simple_ast` operator node (relop), not only a `Goal`/`Atom`.

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

## Resolution note (supersedes the original "can this live in tooling?")
The original filing speculated this could be prototyped in the auditor's own
`.clausal` module. The 2026-07-20 probing (top of this file) proved otherwise:
position-preserving rewrite over reified `goals`/`args` **Python lists** is not
expressible in tooling Clausal (cons/`append`/`select` don't traverse or don't
preserve order). It therefore landed as an engine primitive.

## As-built notes (vs. the design above)
- Built on the term-model walk directly (mirroring `_copy_term_py`'s kind
  dispatch), not the `functor/arg/unpack` surface — those don't traverse the
  Python lists either, which was the whole point.
- Occurrence order equals `reified_subterm/2` **on the reified domain**
  (vocab / `simple_ast` / lists / dicts). Raw `Compound`/`KWTerm` are descended
  position-preservingly here but exposed field-wise by `_subterms`, so the two
  walks intentionally diverge off the reified domain (documented in `_rewrites`).
- An unbound var **in TERM** is an opaque leaf (never a match site), so bare-var
  identity is preserved; OLD's pattern vars still bind. For a *non-ground* TERM a
  var nested inside a matched subterm can bind (undone on backtracking) — the
  intended input is a ground reified clause, where unaffected positions are
  preserved exactly.
- `DictTerm`/`SegList`/`SegString` native containers are leaves (a var bound
  inside one is unreachable) — not needed for the reified AST, which uses plain
  Python `dict`/`list`. Revisit if a future caller needs to rewrite inside them.
