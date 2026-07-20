# renderer (`render_source`/`render_ast`) — deref bound logic vars before rendering

STATUS: DONE (2026-07-20). `_ClauseRenderer.term()` now derefs its argument at
entry: a bound logic `Var` renders its value; an unbound one raises a distinct
`RenderError("cannot render unbound variable: …")`. Since `term()` is the
recursive entry for every rendered *operand/element* position, this covers
bound vars nested anywhere those positions reach. Pinned by
`tests/test_reflection_render.py::TestBoundLogicVars` (scalar, compound, and
nested-deep operands; unbound still raises) and the end-to-end op_node repro
`tests/test_reflection_op_node.py::…::test_operand_bound_after_construct_renders`.
Full suite green (9807 passed).

A follow-up Fable review found `term()` is **not** the only entry: name and
structural field positions (`Goal.name`/`args`/`kwargs`, `Clause.goals`,
`Variable.name`, `Escape.code`, dict keys) bypass it and, when they hold a bound
var, leak `TypeError`/`AttributeError` past `render_ast`'s RenderError contract.
That broader hardening is filed separately as
`todo/renderer-deref-name-and-structural-fields.md`.

## The gap
`_ClauseRenderer.term()` (`clausal/reflection.py`, the `~460–520` block) has **no
`Var` branch and never dereferences**. So a reified term that contains a bound
logic variable — e.g. an operator node whose operand is a `Var` bound to `5` —
renders as a `RenderError` instead of following the binding:

    RenderError: cannot render term: AttVar(_3=5)

even though the variable *is* bound. Only fully-ground terms render.

## Repro (via `op_node/3`, but the limitation is the renderer's)
```
BuildLate(NEW) <- (op_node(NEW, "Gt", [X, 1]), X is 5)
```
`op_node` stores the operands it is given (shallow-deref'd at construct time), so
`X` is still an unbound `Var` when the `Gt` is built; binding `X` afterwards
leaves `Gt.left` pointing at the now-bound `Var`. `render_source(NEW)` then raises
`RenderError` rather than emitting `5 > 1`. The standard logic-programming order
"build with a variable, bind it, render" is what fails.

`op_node/3` already mitigates the common case (operands bound *before* construct
are shallow-deref'd; the usual auditor flow reconstructs from a decomposed node
whose operands are already ground — see
`todo/done/op-node-reflection-decompose-construct.md`). This todo is the durable,
renderer-side fix for the deferred-binding case.

## Deliverable
Make `_ClauseRenderer.term()` (and any peer entry point) `deref` its argument
first:
- bound `Var` → render the dereferenced value;
- unbound `Var` → keep the current loud `RenderError` (an unbound variable has no
  surface form).

## Acceptance
- The repro above renders `5 > 1` and re-reifies to a `Gt(5, 1)`.
- A reified term containing an unbound `Var` still raises `RenderError` (no silent
  or malformed output).
- Full suite stays green; add a focused renderer test for both cases.

## Scope note
Pure renderer change; `op_node/3`'s shallow-deref stays as the cheap fast path.
Check whether `render_ast`'s other term kinds (lists, dict values, nested
operator operands) also need the deref to propagate — the fix should be at the
single `term()` entry so it covers every recursive position.
