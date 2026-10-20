# Style and Formatting

Clausal source has one house layout: **one goal per line**. For seam
(`.seam`) source it is enforced by a tool, `clausal-fmt`; the conventions
below are exactly what the formatter emits, so a formatted seam tree never
churns under it again (formatting is idempotent, comment-preserving, and
AST-preserving). `clausal-fmt` formats seam only: it refuses a Clausal
Prolog (`.clausal`) file rather than mangle it. The examples on this page,
like the rest of these docs, are Clausal Prolog written in the same layout.

## One goal per line

A clause body lists **exactly one goal per line**, indented one step under
the head, and the clause ends with `.` after its last goal:

```clausal
:- use_module(library(clpz)).

positive(1).
positive(2).

doubled(X, V) :-
    positive(X),
    V #= X * 2.

test("doubled") :-
    doubled(2, V),
    V == 4.
```

Only **top-level** body conjunction commas break lines. Commas inside
`findall(...)` arguments, list literals `[...]`, nested compounds and
strings stay where they are.

In seam, the formatter normalises every rule body to the parenthesised
form: a single-goal rule written `q(X) <- r(X)` is emitted as

```seam
r(1),

q(X) <- (
    r(X)
)
```

and the same rule in Clausal Prolog reads

```clausal
r(1).

q(X) :-
    r(X).

test("q") :-
    q(1).
```

Why this is the standard: one goal per line reads top-to-bottom like the proof it is,
keeps diffs minimal when a goal is inserted or removed, and is the easiest
shape for code generators and language models to produce correctly.

## Clause separation

- Every clause, fact or rule, ends with `.`: `positive(1).`
- One blank line separates clause groups.

In seam, where clauses are Python expressions, facts end with a trailing
comma (`positive(1),`) and rules end at the closing `)` with no trailing
comma; see [the seam](syntax.md).

## The formatter

```
clausal-fmt src/                 # rewrite every .seam file under src/
clausal-fmt --check src/         # exit 1 if any file would change (CI gate)
clausal-fmt --diff  src/         # print what would change, write nothing
```

A directory walk picks up `.seam` files only. A `.clausal` or `.pl` file
named on the command line is refused (exit 2), not reformatted.

Properties worth relying on:

- **Comment-preserving** — comments are captured into a side table and the
  emitter hard-errors on any comment it did not re-emit, so a format run can
  never silently drop one.
- **AST-preserving** — the parse tree before and after formatting is
  identical; only whitespace and layout change.
- **Spelling-preserving** — every string literal is written back exactly as
  the source spelled it. In seam the quote character is the term (`'f'` is
  an atom, `"f"` a string, and never a functor), so the formatter never
  requotes, and its own check refuses a result that does.
- **Idempotent** — formatting formatted output is a no-op.

There is no separate advisory lint for multi-goal lines: `clausal-fmt
--check` is that lint, for seam source.

Deliberately deferred style calls (line-width wrapping, long export-list
layout, and friends) are recorded in
`todo/clausal-fmt-open-style-questions.md`.

## See also

- [Clausal Prolog](clausal_prolog.md) — the `.clausal` surface and how its
  spellings differ from the seam's.
- [Syntax](syntax.md) — the seam: the trailing-comma convention,
  logic-variable spelling (ALL_CAPS preferred), clause syntax.
- [Purity](purity.md) — the cut-free design the layout serves.
