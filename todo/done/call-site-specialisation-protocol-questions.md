# Design questions parked while fixing the call-site direct-bucket bug

Surfaced during
`todo/done/call-site-imported-ground-arg-4plus-clauses-runtime-error.md`
(2026-07-11). **Both confirmed as real defects and fixed 2026-07-11** —
see the resolution notes under each question.

## 1. Does call-site specialisation bypass tabling? — CONFIRMED + FIXED 2026-07-11

Yes, it was real: an imported tabled predicate with >= `_INDEX_THRESHOLD`
clauses and head constants got bucket-specialised at ground call sites,
bypassing `make_tabled_wrapper_trampoline` — probe showed 2 solutions
(raw clause semantics, no answer dedup) at the call site vs 1 via the
wrapped dispatch. Fixed in `compile_predicate_trampoline`: tabled
predicates expose empty `_index_plans` / `_index_plans_joint`, so no
bucket-ref walker (legacy inject, `call_site.analyse`, D6c shadow) ever
writes a hint for them — one choke point keeps the walkers in parity with
the D6c cross-check. Regression tests: `TestImportedTabledCallSite` in
`tests/test_callsite_imported_ground_call.py` (+ fixtures
`callsite_tabled_lib/use.clausal`).

## 2. Secondary dispatch drops fallback TRO tail calls — CONFIRMED + FIXED 2026-07-11

Real and reachable: a Phase 9c predicate (6 constant-headed clauses over two
positions, coverage 0.75 < 0.8, non-indexable result column) with a
TRO-eligible tail-recursive clause returned **0 solutions** when called with
the level-0 key unbound (fallback route) — the SIGNAL-mode fallback set
`tro_state` and returned, and the secondary dispatch yielded DONE without
re-dispatching. Silent wrong answer; ground-key calls were unaffected
(secondary buckets compile without TRO), which is why no existing test
caught it. Fixed in `_make_secondary_dispatch_impl`: it now accepts
`tro_state`/`arity` and loops exactly like the single-position and joint
dispatchers (reset flag, route, on signal update args and re-dispatch —
the updated args may key into a level-0 bucket). Regression tests:
`tests/test_secondary_dispatch_tro.py` (+ fixture
`secondary_dispatch_tro.clausal`), with strategy and TRO-active pins so the
coverage can't silently evaporate if index analysis changes.

Probe-craft notes (cost ~2 fixture iterations): `M is N - 1` builds a LAZY
arith term — evaluated by `==`/`>` guards but NOT by structural
head-constant matching, so a recursion counter can never select
constant-headed clauses; and an `OUT is "str"` result column IS indexable
and will win best-single-index (make it a list — pitfall already in the
audit-probe memory).
