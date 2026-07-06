# investigate(A04-F003): WFS resolution is mode/order-dependent; wrong results cached permanently [Opus]

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F003
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF003WfsModeOrderDependence` (2 xfail — flip to pass)
**Related:** A04-F002 (`fix-A04-naf-tabled-no-entry.md`), A04-F001 (completion architecture), A04-D004 (parked)

## Bug

`docs/wfs.md` asymmetric-win truth table: a=true, b=false, c=false. Actual:

- `win("b")` queried FIRST → 1 answer, condition stuck (its delayed
  `not win("a")` names variant `("a",)`, whose entry is never created), so
  `_resolve_conditions` (`tabling.py:283-339`) can never resolve it →
  `undefined` → yielded, and the wrong answer is cached `complete` forever.
- `win("b")` queried after `win("a")` → correctly 0 answers.
- Var-mode `win(X)` → `{a, b}`; ground-mode docs order → `{a}`. The
  solution set depends on call MODE.

Root causes:

1. Delayed negations are recorded against the *ground* variant key of the
   negated call, but resolution only looks up that exact key in
   `table_store` — nothing ever evaluates it (no spawning, F002), and a
   complete subsuming variant is not consulted.
2. Resolution runs per-leader at completion; conditions in an
   already-completed entry are never revisited when a later query
   completes the table they reference (cross-session staleness — the
   sticky `win("b")` answer).

## Investigation goals

- Decide the negation-evaluation strategy (spawn positive subgoals during
  resolution — SLGWAM "answer completion"; or global resolution pass over
  all entries at outermost-leader exit; couples to the F001 SCC redesign).
- Define completeness semantics for conditional answers referencing
  never-evaluated variants (currently: permanent undefined).
- Decide whether completed entries with unresolved conditions may be
  re-resolved on later queries (mutability of "complete" tables) — or
  whether conditions must be fully resolved before an entry can be marked
  complete.

## Acceptance

- `win("b")`-first yields 0; var-mode `win(X)` = `{a}`; both stable across
  query orders. Symmetric-win undefined results unchanged.
- `docs/wfs.md` examples all reproduce as documented, in any query order
  and mode.
