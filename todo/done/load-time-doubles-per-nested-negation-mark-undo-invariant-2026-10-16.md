# Load time doubles per nested `\+` level: the mark/undo invariant re-walks nested funcdefs (pre-existing)

**Status: FIXED 2026-11-04 (d9c21d8e).** The mark/undo check visits each node
once and pairs each scope's marks with its own undos only, as sketched below.
Two more passes re-walked nested bodies per level and are fixed in the same
commit: `body_segments.fold_sequence` lowered a long conjunction inside a
long conjunction twice per level (2**depth; it now refuses segments at once,
as hoisting always did afterwards), and `codegen._Outliner.localise`
re-counted every nested def's names for each enclosing function (memoised).
The generated code is unchanged (every AST compiled while loading all the
repo's `.pl`/`.clausal`/`.seam` files hashes the same). Measured load of one
clause, before -> after: `\+` nested 16 deep 5.1 s -> 0.012 s, 64 deep
(did not load) -> 0.045 s; `findall/3` 16 deep 6.3 s -> 0.026 s, 64 deep ->
0.095 s; nested if-then-else, `;` and `catch/3` were not affected (64 deep:
0.17 s, 0.18 s, 0.5 s). Generated code size is linear in the depth for `\+`
(65 AST nodes per level), `findall/3`, if-then-else and `;`; for `catch/3` it
is quadratic. Pinning tests:
`tests/test_invariant_errors.py::test_mark_undo_paired_is_linear_in_nesting_depth`,
`::test_mark_undo_paired_fires_on_orphan_deep_in_nesting` (an unpaired mark
300 funcdefs deep still raises), `::test_mark_undo_paired_does_not_pair_across_scopes`,
`tests/test_body_segments.py::test_nested_long_conjunctions_are_lowered_a_bounded_number_of_times`,
`tests/test_codegen.py::test_outlining_nested_functions_is_linear`. What is
left (CPython's compile of a deep constant `source_body` tuple, the quadratic
nested `catch/3` code, nested long conjunctions never segmented):
`todo/deep-nesting-load-costs-left-after-the-nested-negation-fix-2026-11-04.md`.

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
