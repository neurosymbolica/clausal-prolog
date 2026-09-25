# A -private atom in one module changes another module's `m.p(...)` call (2026-09-25)

Pre-existing on main 8b02f4f8; found by an order-dependent failure while
merging main into fix/small-todos-batch-2026-09-24. Parked for the operator.

Load any module that declares `-private([nosuch])` (for example
`-module(leak_decl, []) -private([nosuch]) foo(nosuch),`), and then run
`tests/test_unknown_direct_call_is_iso_existence_error.py`. In main's own
worktree 4 of its tests then fail:
`test_a_qualified_unknown_call_names_the_module_in_the_context[class|handle]`
and `test_a_qualified_unknown_call_raises_the_same_python_type[class|handle]`.

`udc_owner_ERA.nosuch(1, 2)` no longer misses as an unknown procedure
(`PredicateNotFoundError`, "nosuch/2 is not defined in module 'udc_owner_ERA'").
It resolves `udc_owner_ERA.nosuch` to the plain atom `'nosuch'` and raises from
`predicate._dispatch_at`'s "atom 'nosuch' is not callable at arity 2 (resolved
via a data reference ...)" arm. The ISO term (`existence_error(procedure,
nosuch/2)`) is the same, but the context and the Python type are not. So the
dotted attribute lookup on the owner module finds an atom that another module
declared.
