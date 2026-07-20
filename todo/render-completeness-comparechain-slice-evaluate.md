# Renderer completeness gaps: CompareChain / Slice / Evaluate / SetLiteral

STATUS: OPEN (filed 2026-07-20, from the Fable review of the reified-term renderer).

The `render_ast`/`render_source` renderer in `clausal/reflection.py` (inverse of
`reify_ast`; see `todo/reified-term-to-source-renderer.md`, DONE) correctly RAISES
`RenderError` — never corrupts — for several node kinds it does not yet handle. This
is contract-compliant (loud, not silent), but each is legal, reachable `.clausal`
surface, so a mutation auditor built on the renderer cannot process clauses that use
them. They did not appear in the reifiable corpus sweep (4171 clauses), so they are a
coverage gap rather than a live bug.

Node kinds that currently raise `RenderError: cannot render operator node: <name>`:
- **`CompareChain`** — chained comparison, e.g. `Range(X) <- (0 < X < 10)`. Reifies to
  `CompareChain([...])`; the surface is a single `ast.Compare` with multiple ops.
- **`Slice`** — subscript slices `P[lo:hi:step]` → `ast.Slice(lower, upper, step)`.
- **`Evaluate`** (`:=`) — arithmetic evaluate-and-bind.
- **`SetLiteral`** — set surface `{a, b, c}` (distinct from dict `{k: v}`).

## Work
For each, add a dedicated `_operator_ast`/`term()` branch building the matching Python
`ast` node, and prove the round-trip with a fixture in `tests/test_reflection_render.py`
(`reify(render_source(clause)) ≡ clause`). Mirror the existing dispatch-table style.
Verify each surface first with a probe (reify the clause, `repr` the node, its fields).

## Notes
- `CompareChain` → `ast.Compare(left, ops=[...], comparators=[...])`; confirm the
  reifier's field layout (list of ops/operands) before emitting.
- `Slice` appears inside `ast.Subscript.slice`; `LoadSubscript` rendering already
  exists — extend it to accept a `Slice` index.
- Keep the "raise loudly, never corrupt" contract: any sub-kind still unhandled must
  keep raising `RenderError`.
