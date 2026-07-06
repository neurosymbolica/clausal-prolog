# fix(A09-F003): include/exclude/partition/take_while/drop_while/span lose Var-element bindings

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F003
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F003_include_var_element_binding, ::test_F003_take_while_var_element_binding (xfail — flip to pass)

## Bug

Six higher-order builtins share the pattern (higher_order.py:127-134 and
siblings): run goal on `deref(elem)`, `trail.undo(mark)`, THEN
`kept.append(deref(elem))`. For a Var element the undo strips the binding the
test goal just made: `include(one_,[X,2],R)` with `one_(1)` yields `R=[X]`
with X UNBOUND (SWI: X=1, R=[1]).

## Fix direction

Keep the successful test's bindings (undo only when the goal fails) — SWI
semantics; the per-element undo exists to isolate FAILED attempts, success
bindings should persist. Same decision as fix-A09-filter-map-binding-capture.md
(A09-F002) — fix jointly. Watch: exclude/partition's "failed" branch must
still undo (a failed include test may have half-bound the element).

## Acceptance

- Both xfails pass; committed-choice semantics per docs unchanged;
  existing include/exclude tests green.
