# fix(A03-F010): compiler README §5 says continuation-TCO doesn't exist — it does

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md` A03-F010 (doc-drift)

`clausal/logic/compiler/README.md` §5 ("How solutions reach the caller")
states: "**What does NOT happen today:** continuation-level tail-call
optimisation … The compiler doesn't do this yet. Deferred as a future
optimisation; see `todo/continuation_tco.md`."

That landed: `optimisations/continuation_tco.py` (analyse/apply pass, run
in `_compile_body_impl` behind the `continuation_tco` flag and the
`_head_has_deferred_pattern` gate) + `TrampolineStrategy.emit_sub_call`
(`strategy.py:132-183`, `tail_position` → child yields solutions directly
on the caller's `_proceed`).

Update §5 to describe the implemented behaviour (including the two safety
gates: deferred-head-pattern skip and the `_k_stmts_is_bare_leaf_yield`
emit-time check), and reconcile `todo/continuation_tco.md` /
`implementation_plans/CONTINUATION_TCO_PLAN.md` status lines. Doc-only.
