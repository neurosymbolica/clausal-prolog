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
