# The 2026-07-05 audit's todos sit in a subfolder, where they get forgotten

Filed 2026-10-18 at the operator's request ("those audit
todos might get forgotten").

## What

`todo/audit-2026-07-05/` holds the todos queued by the 2026-07-05
subsystem audit (A01-A12). It keeps its own `README.md` index and its own
`done/`. Nobody browsing `todo/` sees the open ones, so they get forgotten.

On main b73591df: 20 open (5 `fix-*`, 15 `investigate-*`), 165 closed in
`audit-2026-07-05/done/`. 49 files outside the folder cite
`todo/audit-2026-07-05/...` paths: code comments, tests, docs and other
todos.

Open today:

- fix: A06-sum-op-strings, A08-clpq-float-mixing-enforcement,
  A08-ortools-floordiv-mod-translation, A08-z3-floordiv-mod-translation,
  A10-regex-autobind-body-vars.
- investigate: A01..A09 parked-design-decisions (8 files),
  A08-clpq-bound-enforcement, A08-clpq-prolog-oracle,
  A08-clpq-strict-inequalities, A08-solver-store-sync-hooks,
  A09-copy-term-attrs, A12-tabling-answer-constraints.

## Do

1. **Triage each open file against current code.** Re-run its pinning
   test or repro. For each one:
   - fixed or resolved since: add the `**Status: FIXED|RESOLVED date
     (commit).**` line naming the pinning test (see todo/AGENTS.md);
   - overtaken, never done: delete it and say so in the commit message;
   - still open: keep it, and refresh the repro if it has drifted (for
     example, the CLP(Q) items against the clp(q,r) port, `CLAUSAL_CLPQ=holzbaur`).
   - The 8 "parked design decisions" files: split out each still-open
     decision into its own top-level todo, or point to the D-number that
     ruled it (docs/superpowers/audits/2026-07-05-fable-partition/DESIGN-DECISIONS.md).
2. **Move.** `git mv` the still-open ones to `todo/`. Rename each to the
   todo/ convention: a kebab-case statement of the problem plus a date
   suffix. Keep the audit ID in the title line (`(A08-F013)`) so it stays
   searchable. Move the fixed ones, and all 165 in `audit-2026-07-05/done/`,
   to `todo/done/`. Watch for name clashes there.
3. **Fix the citations.** Grep the whole repo for `todo/audit-2026-07-05/`
   and update every path: code comments, tests, docs, other todos,
   `tests/audit_2026_07_05/` docstrings.
4. **Retire the folder.** Fold anything still useful from its `README.md`
   (counts, cluster notes) into this todo's closing note or a done/ file,
   and remove the folder. Update todo/AGENTS.md: drop the
   `audit-2026-07-05/` map row, the "file audit todos in
   `audit-2026-07-05/`" rule, and "an audit todo goes to
   `audit-2026-07-05/done/`" under Closing.

## Watch out

- The cut branch (feat/pl-cut-and-ite-2026-10-14) edits
  `audit-2026-07-05/investigate-A12-tabling-answer-constraints.md` and
  may cite other audit paths. Do this after the cut branch lands, or
  rebase it over the move.
- Moves only, plus status lines and path fixes: no behaviour change.
  Todo-only commits skip the lane gates, but not while a candidate is
  out.
- Some tests pin line numbers or paths (tests/test_doc_snippet_coverage.py,
  tests/test_funnel_lint.py); run the suite after the path fixes.

## Acceptance

- `todo/audit-2026-07-05/` no longer exists.
- `grep -rn "todo/audit-2026-07-05" .` finds nothing (or only this file
  in `done/`).
- Every formerly open audit todo is in `todo/` (still open) or
  `todo/done/` (with a status line), or deleted with a reason in the
  commit message.
