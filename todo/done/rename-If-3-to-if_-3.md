# `If/3` should be spelled `if_/3`

**Filed:** 2026-08-26, user request during the one-drive-loop planning.
**Status: DONE 2026-08-26.** Policy (2) shipped: `if_` canonical, `If`
accepted with a load-time deprecation lint.

## What shipped

`if_(COND, THEN, ELSE)` is the canonical spelling of the reified if-then-else
— lower-case like every other goal, trailing underscore to dodge the Python
keyword, matching Neumerkel & Kral's `if_/3` (`docs/reified_ite.md`).

`clausal/templating/term_rewriting.py` gained `ITE_NAME` / `ITE_DEPRECATED_NAME`
/ `_ITE_NAMES`; every recogniser now matches `_ITE_NAMES`:

- the goal-position recogniser in `_lower_dict_reads_in_goal`
- `TermTransformer.visit_Call` (which also raises the arity SyntaxError, now
  naming `if_`)
- the DCG body rewriter
- the EDCG body rewriter — see the caveat below

`TermTransformer.visit_IfExp`'s ternary SyntaxError names `if_`, and
`clausal/reflection.py`'s renderer emits `if_`, so a `reify_source` /
`render_source` round-trip migrates a clause off the old spelling.

The old spelling warns once per site with
`ClausalDeprecatedSpellingWarning(ClausalLintWarning)`, formatted like the
singleton lint (`file.clausal:12 — <source line>: ...`) and naming the rewrite
`` `If` -> `if_` ``. Deliberately *not* a `DeprecationWarning`: those are
silenced by default outside `__main__`, which is the silent alias the warning
exists to avoid.

Both rewriters rebuild the ITE node with the author's own spelling rather than
normalising to `if_`, so an `If` inside a grammar body still reaches the term
pass's lint instead of being laundered upstream.

Tests: `tests/test_if_spelling.py` (12). Sweep: `clausal/stdlib/reif.clausal`,
every `tests/fixtures/*.clausal` and `tests/fixtures/docs/*` using the
construct, the live test suite, `docs/reified_ite.md` (which documents the old
spelling and how to silence its lint), `docs/builtins.md`,
`docs/meta_predicates.md`. Historical records — `implementation_plans/`,
`docs/superpowers/{audits,specs,plans}/` — were left on the old spelling on
purpose; they still load.

## Caveat found on the way

The EDCG body rewriter's ITE case is **unreachable** — a generic `Call` case
above it matches first. Pre-existing, verified against canonical main; the
rename keeps the dead case in sync but does not fix it. Tracked in
[[edcg-ite-case-is-unreachable]], which also carries the EDCG test
`tests/test_if_spelling.py` had to drop.

Related: [[one-drive-loop-not-six]], `docs/reified_ite.md`.
