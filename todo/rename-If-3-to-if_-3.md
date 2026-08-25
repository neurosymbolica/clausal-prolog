# `If/3` should be spelled `if_/3`

**Filed:** 2026-08-26, user request during the one-drive-loop planning.
**Status: OPEN — small rename, blocked only on the compat-policy decision
below.**

## What

The general/reified if-then-else goal is spelled `If(COND, THEN, ELSE)`.
It should be `if_(COND, THEN, ELSE)` — lower-case like every other goal,
trailing underscore to dodge the Python keyword, and matching the
reified-conditional literature this construct implements
(Neumerkel & Kral's `if_/3`, see `docs/reified_ite.md`).

`if_` is currently unclaimed anywhere in `clausal/` or `tests/`
(checked 2026-08-26).

## Site inventory (2026-08-26)

Recognition / construction / rendering:

- `clausal/templating/term_rewriting.py:795` — goal-position recognizer
  (`goal.func.id == "If" and len(goal.args) == 3`)
- `clausal/templating/term_rewriting.py:1258` — second recognizer
- `clausal/templating/term_rewriting.py:2592` + `:2602` — recognize +
  rebuild `Name(id="If")`
- `clausal/templating/term_rewriting.py:3045` + `:3073` — match-case arm +
  rebuild
- `clausal/templating/term_rewriting.py:1538` — the ternary SyntaxError
  message says "use If(COND, THEN, ELSE) instead"; must name the new
  canonical spelling
- `clausal/reflection.py:602` — renders the construct back to surface
  syntax; should emit the canonical spelling

Do NOT touch `clausal/pythonic_terms.py:89` or
`clausal/pythonic_ast/nodes.py:97` — that `"If"` is the Python-AST
statement node (`ast.If`), a different thing entirely.

Usages to sweep:

- `tests/fixtures/reified_memberd.clausal:7`
- `tests/fixtures/reified_max.clausal:3`
- `tests/fixtures/tabled_ite.clausal:14`
- `tests/test_dcg.py:350` and `:370` (string-embedded DCG sources,
  `a_or_c >> (If(...))` — confirms the DCG path goes through the same
  recognizer)
- `docs/builtins.md`, `docs/meta_predicates.md`, `docs/reified_ite.md`
- Fixtures added by the one-drive-loop work
  (`tests/fixtures/bench_naf_ite.clausal`, the ITE additions to
  `tests/fixtures/catch_trampolined.clausal`) if it has landed by then —
  see `docs/superpowers/plans/2026-08-26-one-drive-loop.md`

## The one design decision

What happens to the old spelling:

1. **Accept both forever, `if_` canonical** — recognizers take
   `{"If", "if_"}`, renderer and docs emit `if_`, no user breakage, no
   machinery. Cheapest; leaves a silent alias.
2. **Alias + warning** — as (1) plus a lint-style deprecation warning on
   `If(` (the `ClausalSingletonWarning` plumbing in
   `templating/term_rewriting.py` is the precedent for surfacing
   file:line warnings at load time).
3. **Hard rename** — breaks existing user programs; a
   `clausal-rewrite` rule could migrate them mechanically.

Recommendation: (2). The warning names the rewrite (`If -> if_`), the
alias keeps old code running, and a later major release can drop it.

Related: [[one-drive-loop-not-six]] (its fixtures use the current
spelling), `docs/reified_ite.md`.
