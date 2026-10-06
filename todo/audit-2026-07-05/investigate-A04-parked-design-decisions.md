# investigate(A04): parked design decisions — freeze nondeterminism, tabling invalidation granularity, misc hardening [Opus]

**Source:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/design-questions.md` (A04-D001, A04-D002) + minor notes from the A04 findings ledger.
Parked per user preference (A01 precedent): decide unhurried, not mid-audit.

## D001 — freeze/2 frozen-goal nondeterminism (A04-F011)

`_freeze_hook` (`coroutining.py:28-46`) drives each frozen goal to its
FIRST solution and breaks; the attr-hook protocol is boolean
(success/fail), so the frozen goal's choice points are discarded:
`freeze(X, in_(Y,[10,20])), X is 1` yields `(1,10)` only — SWI enumerates
both. Test: `TestF011FreezeFirstSolutionOnly` (xfail + current-behaviour
guard).

Options:
1. **Document the commitment** as intended semidet semantics
   (`docs/coroutining.md` is currently silent) + lint on obviously
   nondet frozen goals. Cheap, honest, un-Prolog-like.
2. **Redesign the attr-hook contract** so hooks can yield choice points.
   Touches dif/CLP(ℤ)/CLP(B) hooks (A05–A07) — cross-subsystem, large.
3. Reject nondet frozen goals loudly (hard to detect statically).

Recommendation: (1) now; revisit (2) only with A05 owners since the hook
protocol is shared.

## D002 — tabling invalidation granularity (dependency staleness)

A tabled predicate over a `-dynamic` NON-tabled predicate is silently
stale after `assertz` to the dependency (probe P16; per-predicate
invalidation itself works and is guarded). `docs/tabling.md` is honest by
the letter, silent in spirit.

Options: (a) document loudly + recommend manual `abolish_table` after
mutating dependencies; (b) opt-in conservative mode: any assertz/retract
abolishes all tables in the module; (c) dependency-graph invalidation
(compiler already has the call graph). Recommendation: (a) now, (c)
folded into the A04-F001 completion re-architecture if it happens.

## Minor hardening items (no ledger rows)

- **`_query_cache` id(module) keying** (`solve.py:183`): no lifetime
  pinning; a GC'd Module with a reused address would serve another
  module's compiled query. Unconfirmed (could not force id reuse).
  Cheap fix: key on a per-Module monotonic token, or hold a weakref that
  invalidates entries on module death.
- **Dead code candidates**: `make_tabled_wrapper_simple` +
  `_trampoline_to_simple_adapter` (`tabling.py:345-593`) — referenced
  only by tests. Decide: delete, or mark explicitly as
  reference/teaching implementations. (The other candidate,
  `continuation_search.py`, the greenlet `Search`, was deleted on
  2026-10-06 with the `greenlet` dependency.)
- **`_naf_tabled` perf**: any-variant fallback scans the whole
  `table_store` per NAF call (`tabling.py:267`); index by
  (functor, arity) if NAF-heavy workloads matter. Moot if
  `fix-A04-naf-tabled-no-entry.md` restructures the lookup.
- **retract on tabled predicates queries through the tabled wrapper**,
  minting table entries as a side effect (observed `('tz',1,(99,))`
  after a failed retract). Decide whether database ops should bypass the
  tabling wrapper (coordinate with A09/A11).
