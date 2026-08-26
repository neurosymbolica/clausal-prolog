# investigate(A04-F003): WFS resolution is mode/order-dependent; wrong results cached permanently [Opus]

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F003
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF003WfsModeOrderDependence` (2 xfail — flip to pass)
**Related:** A04-F002 (`fix-A04-naf-tabled-no-entry.md`), A04-F001 (completion architecture — DONE), A04-D004 (parked)

## Investigation findings (2026-07-07) — design validated, full fix DEFERRED

Attempted a full fix on top of the F001 SCC rework and REVERTED it: it fixed
ground-mode but each variant broke a different case, because correct var-mode
WFS needs a **disjunction-of-conditions residual model** the engine does not
have. What was built and learned (each piece is sound in isolation):

1. **Compiler seam for spawning (works, reverted).** Inject `$naf_db` (the db)
   into `base_globals` alongside `$table_store` (predicate.py, both trampoline
   & simple paths) and emit it as a 6th arg of the `_naf_tabled(...)` call
   (`compiler/tabled_naf.py`). `_naf_tabled(functor, arity, args, trail,
   table_store, db=None)` can then `db.get_dispatch(functor, arity)` and drive
   the +goal to completion via `_drive_trampoline(dispatch, scratch, *args)`.
   This makes `not win("a")` actually EVALUATE win("a") — fixes ground-mode
   asymmetric win (win("b")-first → 0) and is the F002 spawn residual too.

2. **Global resolution at outermost-leader exit (works).** `_resolve_conditions`
   should return whether it changed anything; a `_resolve_all_conditions(store)`
   loops it over every complete entry to a fixpoint, run when `not
   _leader_ctx.stack` after the root completes. Fixes the sticky-`win("b")`
   cross-query staleness (root cause #2): a late-completing win("a") finalizes
   win("b")'s delayed `not win("a")`.

3. **Conditional-aware NAF re-check + answer completion (works partially).**
   After a spawn, an UNCONDITIONAL matching answer → NAF fails; an only-
   conditional match → undefined (delay). `add_answer` upgrades a conditional
   answer to unconditional on an unconditional re-derivation.

4. **The blocker — disjunction of conditions.** In the asymmetric win, `win(a)`
   is derived two ways: via `move(a,b),not win(b)` (condition `{not win(b)}`)
   and via `move(a,c),not win(c)` (condition `{not win(c)}`, which resolves to
   TRUE). WFS truth = OR over derivations, so win(a) is TRUE. But the engine
   stores ONE condition-set per answer (add_answer dedups and keeps the first),
   so the true c-path derivation is lost and win(a) stays conditional. Two
   spawn strategies were tried and each is wrong without disjunctions:
   - *spawn-always* (spawn even under a subsuming evaluating variant): var-mode
     asym win = {a} ✓, but SYMMETRIC win regresses to [1] (should be [1,2]
     undefined) and it proliferates exact sub-tables (breaks the single-entry
     guard `test_wfs_symmetric_win_internal_truth_values`).
   - *subsuming-delay* (delay `not win(Y)` against an evaluating win(_) instead
     of spawning): keeps one table, but var-mode asym win = {a,b} (the a-answer
     never becomes unconditional — same disjunction gap).

**Next implementer:** make an answer's condition a **set of condition-sets**
(disjunction of conjunctions of delayed literals — the WFS residual program).
`add_answer` unions a new derivation's condition-set in; `truth_value` is TRUE
if any inner set is empty, FALSE if all became `_FAILED`, else undefined;
`_resolve_conditions` resolves per inner set and drops satisfied disjuncts.
With that, spawn-always + global resolution + subsuming-variant lookup in
resolution give mode- and order-independent WFS. Also update the single-entry
guard and re-check `query_wfs` (A04-F004) against the multi-table var-mode
shape. Everything else in items 1–3 is ready to reinstate.

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

## IMPLEMENTED (2026-08-27)

The "next implementer" plan above was carried out, together with
`todo/wfs-undefined-lost-at-query-surface.md` (whose ground-query asymmetry
was this finding surfacing at the query API):

1. **Disjunction of condition-sets** — `TableEntry.conditions[i]` is now
   `frozenset[frozenset[DelayedNegation]] | _FAILED` (one inner set per
   derivation). `add_answer` unions a re-derivation's delay set in (an
   unconditional derivation erases the rest; absorption drops superset
   disjuncts); `truth_value` = True on any empty disjunct, False on
   `_FAILED`, else Undefined; `_resolve_conditions` resolves per disjunct.
2. **Spawn-always** — `_naf_tabled(..., db=None)` gained the `$naf_db` seam
   (injected in both compile modes; emitted by `tabled_naf.py` and both
   general-ITE lowerings). A ground negated call with no exact table and no
   complete subsuming table drives the positive dispatch to completion
   (`_drive_dispatch_to_completion`, mirroring the adapter's
   mini-trampoline) and decides against the result. A spawned entry that
   consumed a still-evaluating ancestor stays dormant per A04-F001 SCC and
   the caller falls back to delaying — the partial-consume hazard the old
   delay-branch guarded against is handled by the SCC machinery.
3. **Conditional-aware NAF** — a complete table whose only matching answers
   are conditional DELAYS (`not Undefined` is `Undefined`) instead of
   failing; unconditional matches still fail the negation outright.
4. **Global resolution** — `_resolve_conditions` returns changed;
   `_resolve_all_conditions` runs over all complete entries at root-leader
   exit (both wrapper modes, and after top-level spawns).
5. **Resolution subsumption** — `_delay_target_entry` falls back to a
   complete subsuming variant when the delayed key has no exact entry.

Acceptance from this file: `win("b")`-first → 0; var-mode `win(X)` = {a};
symmetric win unchanged (both undefined, either order, both modes); the
F002/F003 xfails in `tests/audit_2026_07_05/test_04_runtime_tabling.py`
are un-marked and pass; the single-entry guard was updated for the exact
sub-tables spawning creates. `query_wfs` also now resolves `Call`/`Compound`
goals to their entries and carries `_delays` (see docs/wfs.md).
