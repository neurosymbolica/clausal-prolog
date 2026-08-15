# `clausal fmt` — open style questions after the v1 landing

**Status:** v1 shipped (`clausal/fmt/`, `clausal-fmt` CLI, `tests/fmt/`).  It is
comment-conserving, idempotent, and AST-preserving over every `.clausal` file in
the repo, and the whole test suite has the same failure set before and after
formatting all 343 files it changes.  These are the calls v1 made by default or
deferred, each cheap to revisit.

## 1. No line-width engine (deferred by design)

v1 emits one goal per line at a fixed indent and never wraps.  Consequences
visible in the corpus:

- a long `-module([...])` export list written across many lines collapses onto
  ONE long line;
- a long list literal inside a goal (`FACTS is [ ... ]`) does the same;
- a long goal stays long.

A width engine would need: a target width, a splitting rule for call argument
lists and list literals, and a decision on Black-style magic trailing commas
(the earlier design in `clausal-fmt-black-operator-patch.md` chose to KEEP
trailing commas on exploded groups, which is a different default from v1's
"drop the optional comma").  Deciding width and comma policy together is the
right shape for that work.

## 2. Comments inside a construct that is re-rendered on one line

A note against one entry of a multi-line directive has nowhere to sit once the
directive is one line, so it files ABOVE the whole statement.  That is the
conservative choice — it stays with the statement it was written in — but the
comment now describes an entry rather than the statement.  If §1 lands and such
directives keep their per-entry lines, per-entry attachment becomes possible and
this should be revisited with it.

## 3. Generated `.clausal` snapshots must not be formatted

`tests/fixtures/prolog_golden/*.clausal` are byte-compared against a
translator's output (`test_prolog_golden.py`).  Formatting them fails those
tests, exactly as formatting any generated artifact would.  Two options:

- an ignore mechanism in the CLI (`--exclude`, or a `.clausal-fmt-ignore`
  file), which every formatter ends up needing anyway; or
- teach `clausal.tools.clausal_to_prolog`'s reverse direction to emit canonical
  form, and regenerate the goldens, so the snapshots are fmt-stable by
  construction.

The second is better if the reverse translator is meant to produce idiomatic
source; the first is needed regardless for generated files elsewhere.

## 4. Decided in v1, recorded so it is not re-litigated by accident

- **Double quotes** where re-quoting costs no escapes.  `ast.unparse` prefers
  single quotes; adopting that would have rewritten the quoting of every string
  in the language on the first run.
- **The optional final comma inside a body is dropped**; the LOAD-BEARING one is
  kept (`head <- (g,)` is a one-element tuple, `head <- (g)` is not).
- **A statement's own trailing comma is preserved** — `head <- (...),` differs
  from `head <- (...)` in the tree.
- **The file header** — comment groups detached from the first statement — is
  emitted at the top of the file; the group nearest the first statement belongs
  to that statement.
- **Fact tables**: consecutive one-line facts with the same head functor get no
  blank line between them; a comment above one re-introduces the blank.
- **The arrow ledger** (added after v1, and a bug fix rather than a style
  call): `head <- body` and `head < -body` are the same tree, so which one a
  node IS cannot be read off the AST.  Capture records it from the source
  spacing using the loader's own adjacency test, and emission restores the
  tight spelling for exactly those nodes.  Without it, `ast.unparse` flattened
  every inline lambda into a comparison — AST-equal, valid Python, different
  program — and the corpus's own lambda fixtures were being rewritten that way.
  The sweep now counts arrows in and out, since AST equivalence cannot see it.

## 5. Not yet built (the plan's follow-on)

The rewrite RULES over this infrastructure — lambda elimination, head folds,
tell-don't-ask — plus a runner for the comment-repair pass whose prompt and
fence already ship in `clausal/fmt/repair_prompt.py`.
