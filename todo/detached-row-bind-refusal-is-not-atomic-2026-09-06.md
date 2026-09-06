# `_bind_row`'s both-rows-non-empty refusal fires after the triggering write is applied

**Filed:** 2026-09-06 at the P3-3 final fix wave re-review (finding N1, Minor, confirmed).

Final fix wave I-1 made `PredicateMeta._bind_row` (clausal/logic/predicate.py) MOVE clauses
held on a detached row into an empty target row, and raise `LogicException` when BOTH rows
hold clauses (silent loss was the forbidden outcome). The refusal is correct but not atomic
on the runtime-assert path: `clausal/logic/builtins/database_ops.py:~369` appends the new
clause to the module row BEFORE the recompile that triggers the bind, so after the raise the
row holds the new clause (stamped `assertz/1 (failed)`), the class still holds its detached
clauses, and the module answers through the class. Nothing is lost — both sets stay readable
and the message's remedy ("retract or clear one side first") resolves it — but the gate's
"refuse before writing" story (Task 3 step 3d dry-run pre-pass) does not cover this bind.

**To close.** Either run the detached-vs-target check in the dry-run pre-pass (refuse before
the append), or roll the append back when the bind refuses. Pin with the final-review probe:
`make_predicate` + 2× `_assertz`, compile with db=None, then builtin `assertz` → refusal AND
`mod.db.row(...).clauses` unchanged.
