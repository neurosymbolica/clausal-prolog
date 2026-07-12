# Design questions parked while fixing the call-site direct-bucket bug

Surfaced during
`todo/done/call-site-imported-ground-arg-4plus-clauses-runtime-error.md`
(2026-07-11); neither is exercised by that bug's repro, so both were left
untouched. Verify before acting — these are questions, not confirmed defects.

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

## 2. Secondary (hierarchical) dispatch: SIGNAL-mode fallback without a TRO loop

`_make_secondary_dispatch_trampoline(sec, level0_compiled, level0_default_fn,
fallback_fn, DONE)` takes no `tro_state` (predicate.py, Phase 9c branch). Its
level-0/level-1 buckets are compiled WITHOUT `tro_indices`, so they never
signal — but `fallback_fn` is the shared `{functor}__all`, compiled with
`tro_indices=_idx_tro_indices` and `emit_done=False` ⇒ SIGNAL mode. If a
TRO-eligible predicate takes the secondary-dispatch path and is called with
the indexed args unground (fallback route), a signalled tail call appears to
be dropped on the floor (no `tro_state` re-dispatch loop in the secondary
dispatch). Question: real gap or unreachable (e.g. TRO sweep and secondary
analysis mutually exclusive in practice)? A probe needs: >= 4 clauses, joint
coverage below `_JOINT_COVERAGE_THRESHOLD` triggering Phase 9c, a
tail-recursive clause, and an unground call.
