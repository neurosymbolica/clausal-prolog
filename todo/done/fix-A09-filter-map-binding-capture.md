# fix(A09-F002): filter_map/3 captures output AFTER trail.undo — inner bindings lost

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F002
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F002_filter_map_inner_bindings (xfail — flip to pass)

## Bug

`_filter_map__3` (higher_order.py:471-479) runs the goal, then
`kept.append(deref(out))` — but `deref` is top-level only, and the very next
`trail.undo(mark)` unbinds every variable the goal bound INSIDE the output
term. `fmg(X,P) <- (Y is 1, P is pair(X,Y))`, `filter_map(fmg,[5],R)` →
`R = [pair(5, _unbound)]` — a silent wrong answer.

## Fix direction

Either keep the successful goal's bindings (don't undo on success — undo only
on failure; solutions' bindings escaping is the include/SWI semantics), or
snapshot the output with a deep copy (`_copy_term`) BEFORE `trail.undo`.
Prefer keep-bindings: it also fixes the sibling A09-F003 pattern and matches
maplist/3 (which accumulates without per-element undo). Note the per-element
undo also exists in include/exclude/partition/take_while/drop_while/span —
coordinate with fix-A09-ho-var-element-bindings.md.

## Acceptance

- xfail passes: `R == [pair(5,1)]` fully ground; existing filter_map tests
  stay green; goal failure still undoes cleanly.
