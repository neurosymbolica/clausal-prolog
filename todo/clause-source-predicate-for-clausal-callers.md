# No `clause_source/2` — the renderer is Python-only

**Filed:** 2026-07-30, splitting the explicitly-optional follow-on out of
`todo/done/reified-term-to-source-renderer.md` before archiving it.

The renderer itself is done: `render_ast` (`clausal/reflection.py:1245`) and
`render_source` (`:1261`), reified term → `ast` → `ast.unparse` with arrow
repair, raising `RenderError` rather than guessing, and round-tripping the test
corpus. The completeness extension of 2026-07-30 (`3f3cc6c5`) closed the last
known refusals.

What is missing is the Clausal-callable wrapper. `clausal/modules/reflection.py`
registers `reified_item/2`, `reified_clause/2`, `reified_file_item/2`,
`reified_subterm/2`, `clause_head/2`, `clause_body/2`, `goal_functor/3`,
`op_node/3` and `replace_subterm/4` — but no `clause_source(ClauseTerm, Text)`.
A rulebase can therefore take a clause apart and rebuild it, but cannot render
what it built back to source without dropping into Python.

The archived todo marked this "optional follow-on (not required for the
auditor)", which is why it did not hold that file open. It matters when the
auditor wants to *quote* the clause it is objecting to.
