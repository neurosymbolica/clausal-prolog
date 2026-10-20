# fix-A07: PySAT backend — Clausal bindings invisible to solver; label_sat emits unsound models

**Finding:** A07-F005.
**Severity:** correctness — unsound solutions.

`clausal/logic/clpsat.py` registers no attr hook for `SAT_KEY`, and
`label_sat` (493-571) / `sat_check` (256-259) skip vars that are already
ground WITHOUT telling the solver their values. Repro: post `X|Y` via
`sat_constraint_block`, `unify(X, 0)`, then `label_sat([X, Y])` yields
`(0, 0)` — violating the posted clause; `sat_check` stays True after
`Y = 0` too.

**Fix (recommended, pending A07-D003):** assumption bridge — in
`sat_check` and at the top of `label_sat`'s solve loop, extend
`assumptions` with `+sv`/`-sv` for every var in `var_map` whose Clausal
binding derefs to 1/0 (walk `state.rev_map`, deref each). ~5 lines, no
hook-protocol change, trail-safe by construction (assumptions are computed
per call). `pysat.count`/`pysat.model` inherit the fix via `label_sat`.
The deeper alternative (attr hook posting unit clauses per binding) is
design question A07-D003 / joint with A04-D001 — see
`investigate-A07-parked-design-decisions.md` §3.

**Test:** `test_A07_F005_label_sat_respects_clausal_bindings`,
`test_A07_F005_sat_check_sees_bindings` (xfail strict=False).
