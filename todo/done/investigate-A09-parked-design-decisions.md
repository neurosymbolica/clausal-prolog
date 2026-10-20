# investigate(A09): parked design decisions — for Opus / user session

**Status: RESOLVED 2026-10-20 (split).**
- **A09-D001** fixed: maplist/foldl backtrack into every call (operator rulings R5/R6, commits 8f85c27f, 94e7dada; todo/done/investigate-A09-ho-committed-choice.md).
- **A09-D002** and **A09-D003** ruled by the operator 2026-07-07 (DESIGN-DECISIONS.md, "Resolved by user").
- **A09-D004**: dif/2 is copied since commit 09ec3467 (2026-09-30); the rest is tracked in todo/copy-term-attributes-freeze-clpz-and-copy-term-3-2026-09-30.md (see todo/done/investigate-A09-copy-term-attrs.md).
- **A09-D005**: the A09-F022 sites are closed (sort/2 2026-09-09, group_pairs_by_key by ruling R4 2026-09-28, subtract by the D47 review 2026-09-30); pinned in tests/audit_2026_07_05/test_09_builtins.py::test_F022_*. The int/float residue is tracked in todo/iso-unify-conflates-int-and-float-2026-09-09.md.

Parked per standing user preference (design questions go to todos, not
interactive prompts). Full statements + options:
`docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/design-questions.md`.

| ID | One-liner | Gates |
|----|-----------|-------|
| A09-D001 | maplist/foldl committed choice (implicit cut) — restore backtracking? | investigate-A09-ho-committed-choice.md |
| A09-D002 | Builtin error-signaling convention + drive-loop RuntimeError swallow | investigate-A09-runtimeerror-swallow.md, fix-A09-db-permission-logic-exception.md, fix-A09-raw-exception-escapes.md, fix-A09-arith-type-checks.md |
| A09-D003 | retract/1: ISO binding + re-satisfiability vs current undo | fix-A09-retract-bindings.md |
| A09-D004 | copy_term/2 attribute-constraint copying | investigate-A09-copy-term-attrs.md |
| A09-D005 | Cross-type ==/hash in equality-family builtins + bool matrix — inherits A01-D001 | fix-A09-bool-acceptance-matrix.md; A09-F022 fixes sequenced after A01-D001 (interim: group_pairs_by_key id()-split is wrong under any policy) |
