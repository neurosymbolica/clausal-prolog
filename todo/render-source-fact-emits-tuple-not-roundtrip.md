# BUG: `render_source` renders a FACT as `(head,)` — breaks round-trip

STATUS: DONE (2026-07-20). Fixed in `clausal/reflection.py` (`_unparse_clause`):
a fact now renders to the canonical surface `head,` (bare head + trailing comma),
not the Python 1-tuple literal `(head,)`. Regression test added
(`TestFacts::test_fact_surface_is_bare_head_comma`, tests/test_reflection_render.py).

RESULT / CORRECTED DIAGNOSIS: the original impact claim below is partly wrong.
`(head,)` does NOT reify as a non-clause — the reflection reifier and the real
`.clausal` compiler both accept it and produce the *same* Clause/fact as `head,`
(verified end-to-end: rendered fact loads and queries identically, incl. a mutated
literal `500→999`). So the structural round-trip `reify(render(fact)) ==struct==
fact` was already GREEN (positions aside — which differ for rules too, by
construction; the corpus gate strips positions). The real defect was purely the
**surface text**: `(head,)` is non-idiomatic parenthesised-tuple syntax that the
mutation auditor would splice into a file, diverging from the corpus convention
and the renderer design spec (fact → bare-head `Expr` statement). Root cause:
`_ClauseRenderer.clause` emits `ast.Expr(ast.Tuple([head]))` (the AST-level tuple
is *needed* so `reify_ast(render_ast(fact))` sees a clause, not embedded Python),
and `ast.unparse` prints that tuple as `(head,)`. Fix keeps the AST tuple and
special-cases it in `_unparse_clause` to emit `head,`.

Because the structural gate was (correctly) green, "add a fact case to the corpus
sweep" was unnecessary — the new guard asserts the *surface* form instead, which
the structure-only comparison is blind to.

---
Original report (kept for context; impact section partly inaccurate — see above):

## Symptom
`render_source` of a reified **fact** (a `Clause` with `goals == []`) emits the
head wrapped in a **1-tuple** — `(head,)` — instead of the bare head statement.
This does NOT structurally round-trip: `reify_source(render_source(fact))` is not
equal to `fact`. Rules (`goals != []`) render correctly.

## Minimal repro (venv: `/workspace/clausal/venv/bin/python`)
```python
from clausal import reflection as R
items = R.reify_file(
    "/workspace/clausify-domains/eu/mifid/client_categorisation/constants.clausal")
fact = [it for it in items if type(it).__name__=="Clause" and it.goals==[]][0]

rendered = R.render_source(fact)
# => '(per_se_ecp_entity_type(eu.mifid.client_categorisation.schema.investment_firm),)'
#    ^ wrapped in parens + trailing comma = a Python tuple expression

back = R.reify_source(rendered)
# reifies to a Clause, but a structurally DIFFERENT one (head is now tuple-shaped)
assert back[0] == fact          # FAILS — round-trip broken
```
The clean fact surface DOES reify correctly:
```python
type(R.reify_source(
  'per_se_ecp_entity_type(eu.mifid.client_categorisation.schema.investment_firm),'
)[0]).__name__            # 'Clause'  (bare head + trailing comma, no wrapping parens)
```

## Expected
Per the renderer design (`docs/superpowers/specs/2026-07-20-reified-term-renderer-design.md`,
Clause row): a fact (`goals == []`) → **head expr as an `Expr` statement** (bare
head), NOT a tuple. `render_source(fact)` should yield `head` (the splice/harness
adds the fact's trailing comma), and `reify_source(render_source(fact)) == fact`.

Likely cause: the fact branch emits `ast.Tuple([head_expr])` (or an `Expr`
wrapping a 1-tuple) rather than `ast.Expr(head_expr)`. The `<-`-arrow /
`_unparse_clause` path is for rules; the fact path needs to unparse the bare head.

## Why the corpus gate did not catch it
The renderer's completeness gate reportedly passed 571 files / 4171 clauses, yet
facts don't round-trip — so **the gate is not exercising `goals == []` facts**
(or its structural comparison is too lenient). This is the "green fixtures ≠
complete" risk realized on the corpus gate itself. Fix should ADD a fact case to
both the fixture set AND ensure the corpus sweep asserts
`reify(render(c)) == c` for every clause **including facts** (26/26 mifid
`constants.clausal` clauses are facts — a good regression fixture).

## Impact
Mutation auditor mutates fact literals (statutory thresholds live in
`constants.clausal` facts). Until fixed, a fact mutant renders to an inert tuple
expression → reifies as non-clause / wrong structure → the mutant would fail to
load or falsely "survive", corrupting the coverage report. Rules are unaffected,
so rule-body mutations can proceed meanwhile.
