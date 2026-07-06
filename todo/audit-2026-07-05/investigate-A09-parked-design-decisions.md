# investigate(A09): parked design decisions — for Opus / user session

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
