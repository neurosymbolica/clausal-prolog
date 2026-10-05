# Style and Formatting

Seam (`.seam`) source has one authoritative style, and one tool that produces it:
`clausal-fmt`. The conventions below are not aspirational — they are exactly
what the formatter emits, so a formatted tree never churns under it again
(formatting is idempotent, comment-preserving, and AST-preserving).

## One goal per line

A parenthesised clause body lists **exactly one goal per line**, indented one
step, with the closing parenthesis on its own line:

```seam
positive(1),
positive(2),

doubled(X, V) <- (
    positive(X),
    V == X * 2
)
```

Only **top-level** body conjunction commas break lines. Commas inside
`findall(...)` arguments, list literals `[...]`, nested compounds, dict
literals and strings stay where they are.

The formatter normalises every rule body to the parenthesised form — a
single-goal rule written `q(X) <- r(X)` is emitted as:

```seam
r(1),

q(X) <- (
    r(X)
)
```

Why this is the standard: one goal per line reads top-to-bottom like the proof it is,
keeps diffs minimal when a goal is inserted or removed, and is the easiest
shape for code generators and language models to produce correctly.

## Clause separation

- Facts end with a trailing comma: `positive(1),`
- Rules end at the closing `)` with no trailing comma.
- One blank line separates clause groups.

## The formatter

```
clausal-fmt src/                 # rewrite every .seam file under src/
clausal-fmt --check src/         # exit 1 if any file would change (CI gate)
clausal-fmt --diff  src/         # print what would change, write nothing
```

Properties worth relying on:

- **Comment-preserving** — comments are captured into a side table and the
  emitter hard-errors on any comment it did not re-emit, so a format run can
  never silently drop one.
- **AST-preserving** — the parse tree before and after formatting is
  identical; only whitespace and layout change.
- **Idempotent** — formatting formatted output is a no-op.

There is no separate advisory lint for multi-goal lines: `clausal-fmt
--check` is that lint.

Deliberately deferred style calls (line-width wrapping, long export-list
layout, and friends) are recorded in
`todo/clausal-fmt-open-style-questions.md`.

## See also

- [Syntax](syntax.md) — the trailing-comma convention, logic-variable
  spelling (ALL_CAPS preferred), clause syntax.
- [Purity](purity.md) — the cut-free design the layout serves.
