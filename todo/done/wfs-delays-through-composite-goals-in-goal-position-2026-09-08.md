# WFS strictness in goal position reaches only a SINGLE tabled call

Found in the final review of the goal-position `--` feature
(`feat/goal-position-seam-2026-09-08`, finding I1) and extended by the fix
wave's own pinning tests.

Spec §4a promises that `if --goal:` is true, and `for ... in --goal` yields,
"only for answers with an empty delay set". That is delivered for a goal that
IS a single tabled-predicate call, and for nothing else. The docs say so
precisely (spec §4a, `docs/python_integration.md` "Goal position"); this todo
is the engine follow-up for the rest.

**Causes (2) and (3) below are FIXED** (2026-09-08): a non-ground tabled
call is judged like a ground one, and a call's arguments are keyed as the
query makes them (compounds, `++` values). Cause (1) — composite goals and
untabled wrappers — is what remains.

## What is judged, and what is not

`clausal/logic/seam.py::_definite_answers` reads the delay set out of the
tabled entry the call site names. It finds one only for a goal that is itself
a single tabled-predicate call. Everything else is judged as `query_wfs`
judges it — which, for a composite goal, is not at all
("Composite/conjunctive goals are not decomposed here and keep True",
`query_wfs`'s own comment).

Pinned by `tests/test_goal_position_seam.py::TestSoundnessThroughTheRewriter`:

1. **Composite goal or untabled wrapper.** With the 3-cycle program whose
   `wins/1` is entirely WFS-undefined:

   | goal | today | should be |
   |---|---|---|
   | `if --wins(a):` | raises `UndefinedAnswer` | raises |
   | `if --(X is a, wins(X)):` | **true** | raises |
   | `if --p(a):` with `p(X) <- wins(X)` (p untabled) | **true** | raises |

   `_tabled_entry_for_goal` returns `(None, None)` for the `TupleLiteral`
   conjunction node and for `p/1` (not tabled), so no delay set is ever read.

2. ~~**A non-ground tabled call.**~~ **FIXED 2026-09-08.** `for X in
   --wins(X):` used to yield every answer, conditional ones included, and
   raise nothing — even though the goal IS a single tabled call.
   `_definite_answers` defers the entry lookup to the first answer on purpose
   (the entry does not exist before `solve()` runs, so an earlier lookup would
   misread a genuinely tabled goal as untabled), but it also DERIVED the
   subgoal key at that moment, from arguments the answer had just bound — so
   it looked for `wins(d)`'s entry rather than the open call's and
   `table_store.get(...)` missed.

   The fix splits `_tabled_call_site` out of
   `clausal/logic/solve.py::_tabled_entry_for_goal` (the shape walk, minus the
   store lookup; nothing in it depends on the bindings) and has
   `_definite_answers` call it BEFORE `solve()` starts, taking
   `make_subgoal_key(goal_args, trail)` there. The store lookup still waits
   for the first answer, now using that snapshotted key. Each answer is then
   judged by its own per-answer key against the entry's `_answer_index`, so a
   mixed table exports the definite answer and raises on the conditional one.
   `query_wfs` is unaffected: it calls `_tabled_entry_for_goal`, which is now
   a thin wrapper with its old behaviour.

3. ~~**A tabled call with a `++` argument.**~~ **FIXED 2026-09-08 (second
   wave), together with a wider gap found on the way:** not only `++x` but
   ANY non-atomic argument written in the goal — `if --wins(pair(a)):` — went
   unjudged, because the key was taken from the reified NODE's arguments
   (a `Call`, a `PyThunk`) while the entry is stored under the key of the
   call as the compiled query MAKES it (a cell, a value). `_definite_answers`
   now lowers the arguments through `seam_term` first (`_lower_call_args`),
   so compounds, `++` values and `++` inside compounds all match; a `++`
   that reads a variable of the same goal is refused with a `SyntaxError`.
   Pinned in `tests/test_goal_position_seam.py::TestJudgementThroughLoweredArguments`
   and `::TestJudgementAtTheSeamQueryBoundary` (an omitted signature slot is
   judged conservatively over every row of that shape; an argument the seam
   cannot build leaves the call unjudged with `UnjudgedTabledCallWarning`).
   Cost: a `++` in a judged tabled call is evaluated twice (key + query).
   Known unjudged-but-warned or harmless edges (review 2026-09-08): ground
   arithmetic in an argument keys as its value while the query keeps it
   structural (such a goal fails anyway); a dotted PREDICATE functor as an
   argument lowers differently on the two sides (unjudged, exotic).

## The fix for (1), when it is in scope

The judgement has to be per-CONJUNCT rather than per-goal: walk the
goal node for the tabled calls inside it and take the min-truth over their
delay sets (the "min-truth semantics over tabled conjuncts" `query_wfs`
already names as future work), or push the delay set out of `solve()` with the
answer instead of reconstructing it from the table afterwards. The sugar and
`query_wfs` should get whichever lands, from one place — the goal-position
helpers deliberately inherit `query_wfs`'s judgement rather than growing a
second one.

## Related

- `clausal/logic/seam.py::_definite_answers`
- `clausal/logic/solve.py::query_wfs`, `::_tabled_entry_for_goal`,
  `::_tabled_call_site`
- `docs/wfs.md`, spec §4a of
  `docs/superpowers/specs/2026-09-08-goal-position-seam-design.md`

## DONE 2026-09-08 (evening) — cause (1) closed by the throwaway leader

`clausal/logic/seam.py::judged_answers` pushes a fresh, never-stored `TableEntry` as the
tabling leader for the whole goal-position solve; every delay the derivation incurs (negation
delayed in ANY clause body, conditional answers consumed or streamed from tabled calls
beneath) lands on it; conditional answers are deferred, resolved globally at exit, and
delivered last (raise / export / drop). Conjunctions, untabled wrappers, `++`-fed calls and
nested predicates are all judged; `query_wfs` shares the core. The key-based path (causes
2–3's fixes) is deleted — it is subsumed. Plan: `docs/superpowers/plans/2026-09-08-wfs-goal-leader.md`.
Pins: `tests/test_goal_position_seam.py::TestJudgementThroughCompositeGoals` and
`tests/test_wfs.py::TestQueryWfsJudgesCompositeGoals`.

## Review round 2 (2026-09-08, opus) — the judgement made per-ANSWER

The throwaway leader above was reviewed before landing and held back on two blockers, both
of which turned a WFS-TRUE answer into a raised `UndefinedAnswer` — the direction a caller
cannot work around. Fixed on the same branch, each with a pin that fails without it
(`tests/test_goal_position_seam.py::TestDelaysAreChargedToTheRightAnswer`):

1. **Delays from a FAILED branch were charged to the next answer.** `_current_delays` is one
   mutable bucket, snapshotted when an answer arrives and cleared then — nothing retracted a
   delay when the branch that incurred it backtracked. `p(X) <- (wins(X), ok(X))` with
   `ok(d)` the only fact raised on `d`. FIX: `tabling._charge_delays` records every addition
   on the trail (`Trail.record`), so backtracking retracts conditions exactly as it retracts
   bindings. The `clear()` in `judged_answers` is gone with it — it was the coarse
   approximation the trail replaces, and it lost a delay that a LATER answer of the same
   branch still stood on.
2. **A delay-free re-derivation never rescued an already-deferred answer.** Two shapes:
   (a) tabled — `t(a) <- (not u(a))` plus the fact `t(a)`: the table's own row ends
   unconditional, but `add_answer` returns `None` for the re-derivation so nothing
   re-streams, and the consumer kept the FIRST derivation's delays. FIX: a leader may opt in
   to LATE binding (`TableEntry._sources`, `tabling._credit_consumer`) and record the ROW it
   consumed rather than the delay set that row held at that moment; the rows are read back
   after resolution. (b) untabled — `r(a) <- wins(a)` plus the fact `r(a)`: definite answers
   bypassed the entry entirely, so a deferred conditional row for the same bindings was
   never neutralised and `for X in --r(X)` exported `a` and then raised on `a`. FIX: every
   derivation, definite ones included, goes into the entry (the disjunction collapses to
   unconditional); definite answers still stream at once and their row is skipped at delivery.
3. **Two judged goals alive at once cross-contaminated.** A generator suspended at a live
   yield kept its leader on the stack; a second pushed above it; resuming the first charged
   its conditions to the second's leader — a two-fact goal with no negation anywhere raised.
   FIX: `judged_answers` detaches its leader (and any tabled frame parked above it, which is
   also its own) at every yield and restores it on resume, so the stack always reflects who
   is actually running.
4. `judged_answers` now resolves over every store the drive TOUCHED
   (`_leader_ctx.driven_stores`, recorded as each wrapper takes its leader) rather than only
   the goal module's store plus the ones its own delays name: under a judging leader no inner
   leader is ever the root, so nothing else runs that pass.
5. Deferred rows are deduplicated over the GOAL's own variables (plus the caller's, for goal
   shapes `_goal_vars` cannot walk — a `ModulePredicate` call object holds its arguments
   privately). `query_wfs(goal, {})` used to merge every answer into one row.
6. An SCC edge recorded against the throwaway (`scc_deps`) is forwarded to the leader below
   on pop instead of being dropped. NOT PINNED: a judged goal reached from inside a tabled
   clause body was built as a probe (a 3-node `n1→n2→n3→n1` cycle with `++` calling back into
   `--`) and never reached the shape — the edge landed on the nested tabled leader, not on the
   throwaway — so the forwarding is defensive. Anyone who finds the witness should pin it.

## Review round 3 (2026-09-08, opus, of the round-2 fixes)

The condition trailing had a hole, found by review and CONFIRMED by A/B against
`a6baeaf1`:

7. **A collected bag lost the conditions its rows stand on.** `findall`/`bagof`/
   `setof` and `count_all` collect over a private trail mark, backtrack between
   solutions and unwind the mark at the end; the BAG survives that unwind, but
   the (now trailed) conditions its rows were derived under did not, so a
   derivation reading a bag built entirely out of undefined answers was reported
   unconditionally TRUE where it had been Undefined. FIX: the collecting
   lowering harvests the leader's conditions once per kept solution
   (`$harvest_conditions`, `tabling.harvest_conditions` — the retraction happens
   BETWEEN solutions, so harvesting only at the end catches nothing) and charges
   the union back after the unwind (`$charge_conditions`), at the mark, so
   backtracking OVER the whole construct still retracts them exactly once.
   Pin: `test_a_collected_bag_keeps_the_conditions_its_rows_stand_on`, red on
   `60047dad`, green on `a6baeaf1` and on the fix.

Also from that review: the judging leader's driven-store list is now detached
and re-registered with its leader segment (a table another judged goal drove
while we were suspended is not ours), and the global-resolution pass is gated
on that list rather than on `_leader_ctx.pushes` — a THREAD-GLOBAL counter that
another goal's pushes could satisfy; the source rows' stores are folded into
the pass (they were recorded and then dropped); and a definite derivation is no
longer retained at all — its key in `streamed` is the whole of what the late
judgement needs, so retention is back to O(conditional answers) and the common
path copies neither channel.

Two findings from that review are NOT fixed here and are filed instead:
`todo/wfs-conditions-lost-across-a-tabled-leader-answer-2026-09-08.md` (verified
PRE-EXISTING, and the review's proposed fix was implemented, measured not to fix
it, and reverted) and
`todo/wfs-spawn-boundaries-are-absolute-stack-indices-2026-09-08.md` (not
reproduced). Two test gaps it named are also still open: the `_FAILED`-source
branch (a consumed row that resolution invalidates) and a cross-module witness
for the driven-store widening.

## Review round 4 (2026-09-08, opus, of the round-3 aggregate fix)

Round 3 fixed only HALF the aggregate case, and the pin's own `warm()` call is
what hid the other half. CONFIRMED by A/B against `a6baeaf1`:

8. **A bag collected off a LIVE drive still lost its conditions.**
   `harvest_conditions` resolved `current_leader()` per solution. While a tabled
   goal beneath is STREAMING its answers, the top of the leader stack is that
   table's own entry — the whole reason `_streaming_consumer_leader` exists —
   so the credit for a conditional row lands on the leader BELOW it, and the
   harvest read the table's (cleared, `_sources is None`) bucket and collected
   nothing. `findall(X, wins(X), L)` over a COLD table came back
   unconditionally true; over a warmed one (the COMPLETE path, where no table
   leader is pushed) it was already right, which is exactly what the round-3
   pin tested. FIX: bind the target ONCE at the construct's entry
   (`_fa_cl = $current_leader()` before the mark) and pass it to both
   `$harvest_conditions` and `$charge_conditions`.
   Pins: `test_a_bag_collected_off_a_LIVE_drive_keeps_its_conditions_too` and
   `test_setof_and_bagof_keep_their_conditions`, both red on `143ed324`.

Also from that review: the harvest ACCUMULATES into the bag (a set + a dict)
instead of appending a copy of the whole source map per collected row, which
was the quadratic shape the sibling change had just removed from the answer
loop; and `test_backtracking_over_a_bag_retracts_the_conditions_it_charged`
pins that the charge lands at the construct's own mark — verified to
discriminate by mutation (making the charge permanent turns it red), since
`_charge_delays`' dedup would otherwise hide a double charge.

The one gap that review named -- a bag mixing a definite row and an undefined
one -- turned out to be covered already, and is now said so explicitly in the
pin: ``findall(X, wins(X), L)`` collects the definite ``d`` alongside the
undefined ``a``/``b``/``c``, so it pins that ONE undefined row makes the bag's
reader undefined. Measured, not assumed.

## Review round 5 (2026-09-08, opus, of the round-4 fix)

Its High — that the entry-time leader binding disagrees with the stack-relative
target `_credit_consumer`/`_delay_negation` use, so a bag over a MULTI-table
goal loses its conditions — was **not reproduced**: both witnesses it named
raise correctly on `a6baeaf1` and on the branch alike. The conditions reach the
bag transitively (each table folds them into its own answers, which credit one
frame further down on streaming). Both shapes are now pinned, and the residual
ordering worry plus the review's proposed "explicit sink" redesign are filed in
`todo/wfs-collected-conditions-reach-the-bag-transitively-2026-09-08.md`.

Its Medium WAS right and is fixed: `count_all`'s lowering changed identically
to `findall`'s but was only exercised warm, and behind an untabled goal, so no
test drove `count_all` through the streaming path round 4 repaired —
`test_count_all_keeps_its_conditions_off_a_live_drive_too` fails on `143ed324`.
The three cold pins also lacked the `self._stack() == []` assertion the rest of
the class carries; they have it now. Both Lows fixed: the bag's
`[delays_set, sources_dict]` layout is stated in both halves that maintain it,
and `_charge_stmt`'s parameter order now matches the call it emits.
