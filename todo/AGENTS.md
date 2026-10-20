# todo/ — known open problems, and the record of closed ones

One Markdown file per problem, question or deferred idea. Open items sit at the
top level; closed ones move to `done/` or `rejected/`. Check here before
"fixing" something: many gaps are recorded and deliberate, parked for an
operator ruling. Code comments and tests cite these files by path
(`todo/<name>.md`, `todo/done/<name>.md`).

Up: [../AGENTS.md](../AGENTS.md)

## Map

| Path | What |
|---|---|
| `*.md` (top level, ~180) | Open todos. Names are a kebab-case statement of the problem, newer ones dated: `clpz-nonlinear-eq-late-binding-does-not-narrow-2026-10-01.md` |
| `done/` (~440) | Closed todos, each with a `**Status: FIXED ...**` / `RESOLVED` line. Also a few `.seam` repro files that went with them. Includes the 2026-07-05 subsystem audit's closed todos (`fix-<ID>-<slug>.md`, `investigate-<ID>-<slug>.md`, IDs A01-A12) and that audit's old index, `done/audit-2026-07-05-index.md` |
| `rejected/` | Ideas decided against, each with a `**Status: REJECTED date (who).**` line |
| `cross_cutting_issues.md` | A ledger of issues spanning several C extensions; sections marked RESOLVED in place |
| `*open-questions*.md` | Question lists waiting on operator rulings |

Older, pre-September todos also live under `../implementation_plans/*/todo/`
(e.g. `implementation_plans/compiler/todo/`); treat them as history and verify
before acting.

## A todo file

```
# <Title: the problem as a statement>

**Status: ...**            (optional while open; required when closing)

Filed/found: date, by whom, in what work. Severity if known.
## What / Repro          (smallest failing input, observed vs expected)
## Candidates / Options  (if a ruling is needed)
```

Quote the operator verbatim with the date when a ruling is involved
("Operator, 2026-10-02: ...").

## Conventions

**Filing.** New file at the top level, kebab-case name stating the defect,
suffix `-YYYY-MM-DD`. Include a repro and where it was found. If it comes from
an audit with finding IDs, keep the ID in the title line (`(A08-F013)`) so it
stays searchable.

**Closing (fixed).** Verify against current code first: the fixing commit, the
code that now does it, and a test that pins it (re-run it). Then:

1. Insert directly under the title:
   `**Status: FIXED 2026-10-04 (commit 12c7cc07).** <one sentence on what changed>. Pinned in tests/test_x.py::TestY::test_z.`
   Use `RESOLVED` when it was settled by a ruling or by a change elsewhere rather
   than a direct fix; name the commits either way.
2. `git mv` the file to `done/`.
3. Grep the repo for the old path (`todo/<name>`) and update code comments,
   docstrings and tests that cite it.

**Rejecting.** Add `**Status: REJECTED date (operator).** <why>` and move to
`rejected/`. A todo that was never done, only overtaken by later work, is
deleted, not moved to `done/`; say so in the commit message.

**Commits** use the `todo:` subject prefix and list what moved where and why.

## Gotchas

- `.clausal` in a todo written before 2026-10-02 (the extension flip) usually
  means seam source, now `.seam`.
- Some `done/` files carry older status words (`DONE`, `SUPERSEDED`, `RULED`)
  or none; do not normalise them in passing.
- The 2026-07-05 audit's index (`done/audit-2026-07-05-index.md`) says its own
  cluster lists and per-subsystem status columns are stale, and the Status
  column of `../docs/superpowers/audits/2026-07-05-fable-partition/DESIGN-DECISIONS.md`
  still reads "open" for decisions settled since. The fix commits and the
  status lines of the `done/investigate-A0N-parked-design-decisions.md` files
  (triaged 2026-10-20) are the record of what was decided.
- Paths like `/workspace/...` inside todos are from another machine; map them
  to this checkout.
