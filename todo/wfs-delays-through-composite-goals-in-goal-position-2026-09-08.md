# WFS strictness in goal position reaches only a GROUND, single tabled call

Found in the final review of the goal-position `--` feature
(`feat/goal-position-seam-2026-09-08`, finding I1) and extended by the fix
wave's own pinning tests.

Spec §4a promises that `if --goal:` is true, and `for ... in --goal` yields,
"only for answers with an empty delay set". That is delivered for one goal
shape only. The docs now say so precisely (spec §4a, `docs/python_integration.md`
"Goal position"); this todo is the engine follow-up.

## What is judged, and what is not

`clausal/logic/seam.py::_definite_answers` reads the delay set out of the
tabled entry `clausal/logic/solve.py::_tabled_entry_for_goal` finds. It finds
one only for a goal that is itself a single tabled-predicate call, and only
when the subgoal key it computes matches the one the table was stored under.
Everything else is judged as `query_wfs` judges it — which, for a composite
goal, is not at all ("Composite/conjunctive goals are not decomposed here and
keep True", `query_wfs`'s own comment).

Two distinct causes, both pinned by
`tests/test_goal_position_seam.py::TestSoundnessThroughTheRewriter`:

1. **Composite goal or untabled wrapper.** With the 3-cycle program whose
   `wins/1` is entirely WFS-undefined:

   | goal | today | should be |
   |---|---|---|
   | `if --wins(a):` | raises `UndefinedAnswer` | raises |
   | `if --(X is a, wins(X)):` | **true** | raises |
   | `if --p(a):` with `p(X) <- wins(X)` (p untabled) | **true** | raises |

   `_tabled_entry_for_goal` returns `(None, None)` for the `TupleLiteral`
   conjunction node and for `p/1` (not tabled), so no delay set is ever read.

2. **A non-ground tabled call.** `for X in --wins(X):` yields every answer,
   conditional ones included, and raises nothing — even though the goal IS a
   single tabled call. `_definite_answers` defers the entry lookup to the
   first answer on purpose (the entry does not exist before `solve()` runs, so
   an earlier lookup would misread a genuinely tabled goal as untabled), but
   by then the goal's arguments are BOUND to that answer, so
   `make_subgoal_key` computes `wins(d)`'s key rather than the open call's and
   `table_store.get(...)` misses. `query_wfs` does the same lookup AFTER solve
   has finished and the bindings are undone, which is why it reports all four
   answers with the right truth values.

## The fix, when it is in scope

For (2), which is the cheaper and the more alarming of the two: snapshot the
subgoal key at CALL time (before `solve()` starts) and use that key for the
store lookup at the first answer, instead of re-deriving it from the
now-bound arguments. The deferral itself must stay — only the key needs to
be taken early. That turns `for X in --wins(X):` strict without touching any
other caller of `_tabled_entry_for_goal`, but it DOES change the behaviour of
shipped `each`/`once_bind` calls from "silently true" to "raises", so it wants
its own gate run.

For (1), the judgement has to be per-CONJUNCT rather than per-goal: walk the
goal node for the tabled calls inside it and take the min-truth over their
delay sets (the "min-truth semantics over tabled conjuncts" `query_wfs`
already names as future work), or push the delay set out of `solve()` with the
answer instead of reconstructing it from the table afterwards. The sugar and
`query_wfs` should get whichever lands, from one place — the goal-position
helpers deliberately inherit `query_wfs`'s judgement rather than growing a
second one.

## Related

- `clausal/logic/seam.py::_definite_answers`
- `clausal/logic/solve.py::query_wfs`, `::_tabled_entry_for_goal`
- `docs/wfs.md`, spec §4a of
  `docs/superpowers/specs/2026-09-08-goal-position-seam-design.md`
