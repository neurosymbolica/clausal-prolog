# First-arg indexing drops a clause whose head writes a data functor at less than its declared arity

Found during the P3-2 whole-branch final review. Verified PRE-EXISTING
(identical on base `5bcd66ec`, before any P3-2 Task 3/4 change touched
indexing) — the cell-default flip *exposes* this more often (source-written
compound heads now reach the lift at all, per Task 3/Gap #1), it did not
*cause* it. Unindexed dispatch (below `_INDEX_THRESHOLD`) is unaffected and
correct.

## The bug

A clause head that references a declared data functor at LESS than its full
declared arity — a partial-positional reference (`pt(1)`) or a keyword-only
reference (`pt(y=2)`) — becomes UNREACHABLE by any real caller once the
predicate's clause count crosses `_INDEX_THRESHOLD` (4,
`clausal/logic/compiler/arg_index.py`). Below the threshold, the same clause
is matched correctly by the unindexed linear scan.

## Repro

Declare `pt(x, y)` (a 2-field data functor, no clauses of its own — a data
functor) and a discriminator predicate with clauses padded past
`_INDEX_THRESHOLD`:

```
-module(_repro, [pt(x, y), probe(S, K)])

probe(pt(1), "hit"),      # partial-positional: x=1, y backfills to Var()
probe(901, "n1"),
probe(902, "n2"),
probe(903, "n3"),
probe(904, "n4"),
probe(905, "n5"),
```

Querying with a fully-materialized cell that a real caller always builds
(construction-side placement always backfills to full declared arity — see
`terms_to_ast.term_to_ast_expr`'s `Call(LoadName)` branch and
`PredicateMeta.__call__`) finds nothing:

```python
call("probe", ("pt", 1, 9), K, module=lm)   # -> [] ; should be ["hit"]
```

Trim `probe` to 2 clauses (`probe(pt(1), "hit")` + one pad clause, below
`_INDEX_THRESHOLD`) and the identical query correctly yields `["hit"]` — the
same clause, same query, only the clause COUNT differs.

The keyword form (`probe(pt(y=2), "hit")`, queried as `("pt", 7, 2)`) fails
identically once padded past the threshold, and succeeds below it.

This is pinned as executable findings in
`tests/test_tagged_terms.py::TestPartialHeadReferenceIndexing` (fix-round
pattern established for this project — see e.g.
`TestHeadPatternReachability`): a saturated head reference above the
threshold passes (already correct, pinned as a regular test); the partial
and keyword forms above the threshold are `xfail(strict=True)` citing this
file; the same two forms below the threshold pass (pinning the correct
unindexed behaviour as the regression floor for whoever fixes this).

## Mechanism

Two functions disagree about what "arity" means for a data-functor head
reference:

- **`head_match.head_to_match_pattern`'s `Call(LoadName)` branch**
  (`clausal/logic/compiler/head_match.py`, ~line 661) places the PATTERN
  against the functor's DECLARED signature: `cell_signature_for_name` gives
  the full field list, `_place_signature_slots` fills every slot (positional
  args, then keyword args, then a wildcard `MatchAs` for anything left over).
  A clause head `pt(1)` therefore compiles to the pattern
  `case ('pt', 1, _)` — full declared arity (2), one slot pinned, one
  wildcarded. This is correct and is exactly what makes the CLAUSE itself
  still matchable in principle.

- **`arg_index._arg_to_index_key`'s `Call` branch** (same file area,
  ~line 99-102) keys the BUCKET the clause is filed under using the WRITTEN
  arity instead: `return (basename, len(arg.args))` reads `len(arg.args)`
  off the raw, pre-placement `Call(LoadName('pt'), args=[1], kwargs=[])` term
  — `('pt', 1)` for `pt(1)`, `('pt', 0)` for `pt(y=2)` (zero *positional*
  args). This key computation runs at `_analyze_index_positions` time,
  BEFORE `_lift_clause_at_pos` (and therefore before any placement/backfill)
  ever touches the clause.

A real caller's runtime key, by contrast, is always computed from an
ALREADY-backfilled, full-arity cell — every producer of a `pt(...)` value
(source-written construction via `terms_to_ast`'s `Call(LoadName)` site, or
`PredicateMeta.__call__` for a Python-side producer) performs
placement-and-backfill BEFORE the value exists at runtime, so the value in
flight is always the full 2-slot tuple `('pt', 1, Var())`. `arg_index.
_runtime_arg_key`'s cell branch (added in P3-2 Task 4) reads slot 0 and
`len(tuple) - 1`, giving `('pt', 2)`.

So the clause is filed under `('pt', 1)` (or `('pt', 0)` for the pure-keyword
case) and every real caller probes `('pt', 2)` — the bucket the caller wants
is never the bucket the clause landed in. Below `_INDEX_THRESHOLD` there is
no bucket at all — every clause is tried via full `unify()` against the
UNLIFTED body `Unify` goal (`_normalize_structural_head_args`'s hoist), which
resolves `pt(1)` correctly at runtime regardless of arity bookkeeping — so
the bug is invisible until indexing kicks in.

## Why it's not fixed here

- Confirmed PRE-EXISTING (identical behaviour on `5bcd66ec`, no P3-2 commit
  introduced it) — out of scope for a flip-focused branch's fix wave.
- The unindexed path is unaffected and correct, so there's no data-loss risk
  in production callers that stay below the threshold, or that never
  reference a data functor at less than full arity in a hot indexed
  position.
- The fix touches key computation for EVERY `Call`-shaped head reference
  (not just cells) and needs a decision about where the declared-signature
  lookup happens at index-analysis time (see below) — a real design task,
  not a one-line patch, and the review's mandate for this wave was fix-or-
  record, not indexing redesign.

## Fix direction sketch

`_arg_to_index_key`'s `Call` branch needs the same information
`head_to_match_pattern` already has: the functor's DECLARED field count, not
the written one. Concretely: resolve `cell_signature_for_name(basename,
globals_)` (or the equivalent registry lookup available at
`_analyze_index_positions` call time — the bucket-build loop already has
`base_globals` in scope, see `predicate.py`'s
`_lift_clause_at_pos(cl, pos, base_globals)` call sites) and key on
`(basename, len(declared_fields))` when a signature resolves, falling back to
`(basename, len(arg.args))` only when it doesn't (OWA-unknown functor,
`-implicit_functors` — see the sibling todo
`todo/owa-unknown-functor-head-args-never-indexed-2026-09-05.md`, which
documents that OWA-unknown heads already skip indexing entirely and stay
correct via the fallback).

This requires threading `globals_`/`base_globals` into `_arg_to_index_key`
(currently a pure, globals-free function called from `_analyze_index_positions`
before any bucket exists) — the bucket-build loop already has it available
(passed to `_lift_clause_at_pos` a few lines below where the key would need
it), so the plumbing is local, not structural. `_runtime_arg_key` (the
runtime twin) does NOT need to change — it already keys a real cell at its
actual (already-backfilled, declared) arity, which is the value every other
part of this fix needs to agree with.

OWA (`-implicit_functors`) is unaffected either way: an OWA-unknown functor
head arg is never lifted into a bucket in the first place (see the sibling
todo above) and always keys `_INDEX_VAR` — no arity bookkeeping applies to
it, so this fix and that gap are independent.
