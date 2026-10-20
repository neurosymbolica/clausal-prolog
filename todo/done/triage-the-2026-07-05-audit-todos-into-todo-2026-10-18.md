# The 2026-07-05 audit's todos sit in a subfolder, where they get forgotten

**Status: FIXED 2026-10-20 (branch todo/triage-audit-2026-07-05-2026-10-20).** `todo/audit-2026-07-05/` is gone: 166 closed todos moved to `todo/done/` under their own names, the 19 open ones were triaged against current code (verdicts below), its README is `todo/done/audit-2026-07-05-index.md`, and every citation of the old paths was updated. Pinned by tests/audit_2026_07_05/test_00_smoke.py::test_todo_index_exists (the index exists at its new path) and by `grep -rn "todo/audit-2026-07-05" .` finding only this file.

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

## Closing note (2026-10-20)

Counts: the audit queued 185 todos (161 fix + 24 investigate, A01-A12).
On 2026-10-20, 166 were closed and 19 open (4 fix, 15 investigate; one
fewer than the 20 above because `fix-A10-regex-autobind-body-vars` closed
the same day). There were 9 parked-design-decision files (A01-A09), not 8.
No name clashed in `todo/done/`, so every audit file kept its name.

### Verdicts for the 19 open todos

Each was re-run against current code (its pinning test, or a probe where
it had none). Under the default CLP(Q) solver unless stated;
`CLAUSAL_CLPQ=holzbaur` is the clp(q,r) port.

| Was (todo/audit-2026-07-05/...) | Verdict | Now |
|---|---|---|
| fix-A06-sum-op-strings.md | open (XFAIL; gated on A06-D002) | todo/sum-and-scalar-product-silently-ignore-python-spelled-ops-2026-07-05.md |
| fix-A08-clpq-float-mixing-enforcement.md | open (2 XFAIL on both solvers; A08-D003) | todo/clpq-silently-accepts-floats-and-real-variables-2026-07-05.md |
| fix-A08-ortools-floordiv-mod-translation.md | open (code unchanged; ortools not installed, tests skip; A08-D001) | todo/cpsat-adapter-floordiv-and-mod-differ-from-python-2026-07-05.md |
| fix-A08-z3-floordiv-mod-translation.md | open (3 XFAIL; A08-D001) | todo/z3-adapter-translates-floordiv-and-mod-with-smt-semantics-2026-07-05.md |
| investigate-A08-clpq-bound-enforcement.md | open on legacy (F002 now passes, F006 XFAIL); fixed under holzbaur | todo/legacy-clpq-bb-inf-cannot-branch-on-an-eliminated-variable-2026-07-05.md |
| investigate-A08-clpq-strict-inequalities.md | open on legacy (cycle + entailed XFAIL, aliasing fixed); fixed under holzbaur | todo/legacy-clpq-strict-inequality-is-a-passive-disequality-2026-07-05.md |
| investigate-A08-solver-store-sync-hooks.md | open (2 XFAIL; A08-D002) | todo/z3-and-ortools-variables-ignore-clausal-bindings-2026-07-05.md |
| investigate-A12-tabling-answer-constraints.md | open (2 + 2 XFAIL; plan in the file) | todo/tabled-answers-drop-their-constraints-on-replay-2026-07-05.md |
| investigate-A08-clpq-prolog-oracle.md | RESOLVED: the Scryer clpq oracle runs (216 passed) | todo/done/investigate-A08-clpq-prolog-oracle.md |
| investigate-A09-copy-term-attrs.md | RESOLVED: dif is copied (XPASS); the rest is tracked in todo/copy-term-attributes-freeze-clpz-and-copy-term-3-2026-09-30.md | todo/done/investigate-A09-copy-term-attrs.md |
| investigate-A01..A09-parked-design-decisions.md (9) | RESOLVED by splitting, below | todo/done/investigate-A0N-parked-design-decisions.md |

None was deleted as overtaken.

### The parked design decisions

| Decision | Disposition |
|---|---|
| A01-D001 | ruled 2026-07-07 (c); bool half closed by D35/D47; int/float half in todo/iso-unify-conflates-int-and-float-2026-09-09.md |
| A01-D002 | new: todo/dimensionless-quantity-is-not-equal-to-its-number-2026-07-05.md |
| A01-D004 | overtaken: Compound deleted (09d77d93), Var functor retired (10f6784e) |
| A02-D002 | fallback scan in place; rest waits on the int/float ruling (todo/iso-unify-conflates-int-and-float-2026-09-09.md, todo/a01-d001-tabling-half-2026-09-09.md) |
| A03-D001 | overtaken: Compound deleted (09d77d93) |
| A03-D002 | settled, ISO copy (4851e69e) |
| A03-D003 | settled, refuse loudly (44ad6f02) |
| A03 notes | determinism table + `_tro_state`: new todo/tro-determinism-table-is-hand-written-2026-07-05.md; zero-arity solve() fixed |
| A04-D001 | resolved 2026-10-09 (abbf536b) |
| A04-D002 | new: todo/tables-over-a-dynamic-dependency-go-stale-after-assertz-2026-07-05.md |
| A04 minor | query cache fixed (080d4271); retract minting no longer reproduces; dead wrapper + NAF scan: new todo/tabling-leftovers-simple-wrapper-dead-code-and-naf-full-scan-2026-07-05.md |
| A05-D001 | bool half closed by D35/D47; int/float half in todo/iso-unify-conflates-int-and-float-2026-09-09.md |
| A05-D002 | new: todo/engine-attribute-keys-are-user-writable-2026-07-05.md |
| A06-D001 | new: todo/label-of-a-variable-with-no-domain-succeeds-unbound-2026-07-05.md |
| A06-D002 | open, in todo/sum-and-scalar-product-silently-ignore-python-spelled-ops-2026-07-05.md |
| A06-D003 | settled 2026-09-30 (2a10ca72) |
| A06-D004 | new: todo/circuit-of-zero-or-one-variables-fails-2026-07-05.md |
| A06-D005 | resolved by D47 (4bb6a79e) |
| A07-D001 | new: todo/taut-and-sat-count-ignore-the-clpb-store-2026-07-05.md |
| A07-D002 | settled, reject bools (fa196561) |
| A07-D003 | settled, assumption bridge (282e414f) |
| A08-D001..D004 | open, each in its fix/investigate todo above |
| A08-D005 | new: todo/optimize-results-follow-a-different-contract-per-solver-backend-2026-07-05.md |
| A09-D001 | fixed (R5/R6; 8f85c27f, 94e7dada) |
| A09-D002, D003 | ruled 2026-07-07 |
| A09-D004 | dif copied (09ec3467); rest in todo/copy-term-attributes-freeze-clpz-and-copy-term-3-2026-09-30.md |
| A09-D005 | F022 sites closed (2026-09-09, R4, D47 review); int/float residue in todo/iso-unify-conflates-int-and-float-2026-09-09.md |

### From the old README, still useful

- The A12 synthesis (2026-07-06) re-ran all 11 subsystem test files and
  reproduced every recorded pass/xfail count; no finding was culled as a
  false positive.
- Its seven "fix once, close many" clusters (error protocol, cross-type
  conflation, walker blindness, `//`/`%`, tabling answer representation,
  directive robustness, namespace reservation) are all closed except the
  `//`/`%` cluster (A08-D001: the Z3 and CP-SAT todos) and the tabling
  answer representation (the A12-F001 todo).
- `DESIGN-DECISIONS.md`'s Status column is stale in the same way the
  README's was; the parked-decisions files' status lines above are the
  current record.

Citations fixed: 209 lines citing `todo/audit-2026-07-05` in 60 files
before the move (code comments in clausal/logic/tabling.py,
clausal/logic/compiler/ir.py (an error message) and
clausal/logic/builtins/iso_compare.py; tests; docs; the audit's ledgers,
prompts and transcripts; other todos), plus 35 bare names of the renamed
files. Moves, status lines and path fixes only: no behaviour change.
