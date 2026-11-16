# WFS judgement for ANY goal in goal position (and query_wfs): the throwaway leader

**Approach A**, chosen by the operator 2026-09-08 over B (post-hoc conjunct walk) and C
(table the goal). Closes cause (1) of
`todo/wfs-delays-through-composite-goals-in-goal-position-2026-09-08.md`.

## Why this works (facts, all read from canonical 7d8a4889)

- The tabling leader stack (`tabling._leader_ctx`) is Python-only and thread-local; the C
  core never touches it. `push_leader`/`pop_leader(entry)` are identity-based.
- Every delay a derivation incurs lands on `current_leader()._current_delays`:
  `_delay_negation` (a `not tabled(...)` that must be delayed, from ANY clause body,
  tabled or not) and `_propagate_answer_delays` (consuming a conditional answer from a
  COMPLETE table). A streaming (non-root) leader attributes its incremental conditional
  yields to the leader BELOW it (`_streaming_consumer_leader`).
- A tabled call is ROOT iff the stack is empty at push. Only a root defers conditional
  rows until after `_resolve_all_conditions(store)`; a non-root streams them.
- `end_drive_episode()` repairs only entries recorded via `_record_created_entry`; an
  entry never stored is invisible to it.

So: push a fresh, never-stored `TableEntry` as the leader BEFORE `solve()`, and the whole
derivation — conjunctions, untabled wrappers, `++`-fed calls, nested predicates — reports
its delays to it. The tabled calls inside become non-root and stream; the throwaway
leader takes over the root duties (defer conditional answers, resolve globally at exit,
deliver survivors / raise / drop).

## Task 1 — `judged_answers` core (clausal/logic/seam.py)

`judged_answers(goal, module, exported_vars, trail)` yields `(truth, delays)` per answer
with bindings live on the trail; truth is True or Undefined; WFS-false answers never
surface.
1. `leader = TableEntry()`; `push_leader(leader)`; snapshot the push counter.
2. Per `solve()` answer: `ds = frozenset(leader._current_delays)`; clear. Empty → yield
   `(True, ∅)` live. Else DEFER: `leader.add_answer(freeze_args(exported_vars, trail), ds)`.
3. After exhaustion, if any leader was pushed during the solve: `_resolve_all_conditions`
   over the goal module's store and every `dn.store` the deferred rows reference; then
   `_resolve_conditions(leader, module_store)`.
4. Deliver deferred rows in index order: False → skip; True → unify exported_vars with
   the frozen row under the trail, yield `(True, ∅)`, undo; Undefined → the same with
   `(Undefined, delays_for(i))`.
5. `finally: pop_leader(leader)`.
`_definite_answers` keeps only the `++`-over-goal-variable refusal (pinned) and consumes
`judged_answers`; the key-based path, `_lower_call_args`, minted wildcards and
`UnjudgedTabledCallWarning` are deleted — nothing is unjudged any more.

## Task 2 — pins (tests/test_goal_position_seam.py)

Flip the conjunction/wrapper pin to RAISE; new class for composite goals: the oracle shape
(untabled `decide(++profile, verdict(S, IDS))` over a tabled predicate with negation),
mixed bound/open conjuncts, `for` delivering definite answers first then raising, a
WFS-false-after-resolution answer never surfacing, `break`/body exception leave the
leader stack empty, a nested seam inside a judged body. Lowered-argument tests pass
unchanged; boundary tests: partial slot judged exactly, arithmetic-over-var → 'false'
with no warning.

## Task 3 — query_wfs on the same core (clausal/logic/solve.py)

`query_wfs` consumes `judged_answers`; composite goals get real `_truth`/`_delays`.
`_tabled_entry_for_goal`/`_tabled_call_site` stay for the refusal check.

## Task 4 — docs

`docs/python_integration.md`, spec §4a, `docs/wfs.md`, todo → `todo/done/`. Outside the
engine after landing: the downstream integration guides that quote §4a.

## Gate

Full-suite name-set diff vs 7d8a4889 (0 NEW); opus review; land canonical → clone (from
the clone's own cwd) → box.
