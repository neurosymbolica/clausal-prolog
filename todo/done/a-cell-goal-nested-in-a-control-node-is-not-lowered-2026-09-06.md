# A cell goal nested inside `And`/`Or`/`Not` is not lowered

Found during P3-3 Task 5 (R11, cells as goals). Parked: the brief scoped the
conversion to `solve._term_to_goal`, which only ever sees the TOP-LEVEL goal.

## What happens

`solve(("p", X), mod)` works after Task 5: `_compile_as_query` calls
`_term_to_goal`, whose new cell branch turns the cell into
`Call(LoadName("p"), [X])`.

`solve(And(("p", X), ("q", X)), mod)` does not. `_term_to_goal` returns the
`And` node unchanged (it is already a goal node), and the cells inside it reach
`clausal/logic/compiler/terms_to_goalop.py::_convert_inner`, which has no cell
branch and calls `_not_yet(goal)`:

```
NotImplementedError: terms_to_goalop: goal shape not yet supported (tuple): ('p', _4)
```

The same applies to a cell inside `Or`, `Not`, an if-then, and to a cell goal
written in a CLAUSE BODY (which reaches `terms_to_goalop` by the same route,
not through `_term_to_goal` at all).

## Why it was parked

`_term_to_goal` is a top-level query seam; the general fix belongs in
`terms_to_goalop._convert_inner`, next to the `Compound` branch it would mirror.
That is a compiler change with its own gate (the parity corpus, the codegen
golden test, TRO's `_DETERMINISTIC_BUILTINS` sweep), and Task 5's brief named
`solve.py` rather than the compiler. Doing it here would have widened the task's
diff into the one area whose regressions are hardest to read.

## The fix, when it is in scope

Add the cell branch to `terms_to_goalop._convert_inner`, keyed off
`cells.compound_cell_shape`, producing the same `GoalOp` the `Compound` branch
produces — and route the two deferred functors through the same two doors
`_term_to_goal` uses (`cells.resolve_qualified_goal_cell` and
`cells.refuse_control_construct_cell`) so the diagnostics stay identical
wherever a cell goal appears. `_term_to_goal`'s branch can then be a thin
pre-pass (or go away).

## Related

- `.superpowers/sdd/p33-state-relocation/task-5-report.md` (the concern list)
- `clausal/logic/solve.py::_term_to_goal` — the cell branch this one mirrors

## Closed 2026-09-30

Fixed on fix/todo-batch-5-2026-09-30 at the query seam rather than in
`terms_to_goalop`: `_term_to_goal` hands a control NODE that holds a cell in
goal position to call/1, whose body converter (call_body) already lowers
every cell -- plain, qualified and control -- with the same diagnostics as a
top-level cell. The compiler's goal lowering is untouched (a cell never
reaches a compiled clause body from source). Pinned by
tests/test_solve_cell_goals_in_control_nodes.py.
