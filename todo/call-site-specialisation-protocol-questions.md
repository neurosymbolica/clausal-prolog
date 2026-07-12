# Design questions parked while fixing the call-site direct-bucket bug

Surfaced during
`todo/done/call-site-imported-ground-arg-4plus-clauses-runtime-error.md`
(2026-07-11); neither is exercised by that bug's repro, so both were left
untouched. Verify before acting — these are questions, not confirmed defects.

## 1. Does call-site specialisation bypass tabling?

The bucket-ref hint criteria are only `_locked` + `_index_plans`
(`optimisations/call_site.py::analyse`). A **tabled** predicate is locked at
end-of-module-load like any other (import_hook step 7) and gets
`_index_plans` when it has >= `_INDEX_THRESHOLD` clauses — but its installed
dispatch is wrapped by `make_tabled_wrapper_trampoline`
(`compiler_v2.py` step 6-ish). A direct bucket ref at an importing call site
would drive the (now call-site-wrapped) bucket and skip the table store
entirely: no answer dedup, no SLG suspension, wrong WFS/NAF semantics.
Question: should `analyse` skip callees with `db.is_tabled(fname, arity)`
(and should `populate_runtime_from_plan` mirror that guard)?

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
