# fix(A04-F002): _naf_tabled unsound for never-called / other-variant subgoals

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F002
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF002NafTabledNoEntry` (3 xfail — flip to pass)
**Design:** A04-D004 (parked) — spawn-vs-scan; see `investigate-A04-wfs-variant-resolution.md`

## Bug

`tabling.py:226-277` (`_naf_tabled`):

- **No table entry** for the exact variant and no same-functor variant
  currently evaluating → `return True` ("treat as no answers"). Negating a
  derivable goal SUCCEEDS if the positive side was never queried:
  `not tp(1,2)` with fact `tp(1,2)` succeeds before any `tp` query, fails
  after — query-order-dependent logic.
- The complete-table arm (`:240-252`) looks up the **exact variant key
  only**: a complete `tp(_,_)` table whose answers include `(1,2)` is
  ignored by `not tp(1,2)`.
- Downstream, acyclic negation chains record wrong unconditional TRUE
  answers (`even_node(1)` with `EVEN_ODD_SRC` fixture).

## Fix direction

Stopgap (this todo): before the no-entry fallthrough,
1. scan same-functor/arity **complete** entries whose variant key
   *subsumes* the call (at minimum the all-var variant) and run the same
   answer-match check against them;
2. if any same-functor entry is incomplete, DELAY (current any-variant
   branch) — never return unconditional True merely because the subgoal
   was not yet called;
3. if the predicate has never been called at all, either spawn the
   positive subgoal (correct; needs dispatch access — compiler seam with
   A03's `tabled_naf.py` emission) or raise a loud "NAF on unevaluated
   tabled predicate" error rather than silently succeeding.

Full semantics (spawning, WFS integration) = `investigate-A04-wfs-variant-resolution.md`.

## Acceptance

- `ntp` before/after query order gives identical (empty) results.
- `not tp(1,2)` after `tp(X,Y)` var query fails.
- `even_node(X)` on the acyclic chain yields only `2`.
- `tests/test_wfs.py` unit tests updated where they pin the old no-entry
  behaviour (they currently assert `True` for no-entry — that assertion is
  the bug fossilized).
