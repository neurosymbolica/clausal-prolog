# Load time doubles per nested `\+` level: the mark/undo invariant re-walks nested funcdefs (pre-existing)

**Found:** 2026-10-16, re-review 3 of the conjunction-body retract fix (Note N2). It is the same on
base 0731c12e, so it is not caused by that fix.

## Symptom

`c :- \+ \+ ... \+ g(1).` costs about twice as much to load per extra `\+`. Measured 2026-10-16 in
the `_todo_retractconj` worktree:

| depth | 10 | 12 | 14 | 20 (review) |
|---|---|---|---|---|
| load | 0.07 s | 0.29 s | 1.12 s | 128 s |

## Cause (profiled at depth 15: 11.8 s total)

- 10.0 s of that is `invariants.assert_mark_undo_paired`, called by
  `predicate._build_predicate_trampoline_funcdef`.
- `_check_mark_undo_pairing` was called 32769 times, which is 2^15.

`_check_mark_undo_pairing` (`clausal/logic/compiler/invariants.py:177`) recurses into each nested
`ast.FunctionDef` (the NAF mini-generators) as its own scope, then `continue`s. The `continue` only
skips processing the node: `ast.walk` still descends into that FunctionDef. So every ancestor scope
re-finds, and re-recurses into, every deeper funcdef, which is exponential in the nesting depth.

There is a second defect in the same code: the outer scope also collects the inner scope's
marks/undos. A mark in one scope can therefore be "paired" by an undo in another, which weakens the
check.

## Fix sketch

Walk each scope with an explicit stack that does not descend into a nested FunctionDef, and recurse
exactly once per funcdef. This makes it linear, and each scope's balance is checked only against
its own marks and undos. Then:

- Re-time depths 10 to 20.
- Check that the generated code size is linear in the depth too. The profile suggests it is, but
  this has not been measured.
- Keep a test that a deliberately unpaired mark in a nested funcdef still raises.
