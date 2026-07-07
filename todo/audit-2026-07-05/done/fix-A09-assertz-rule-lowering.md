# fix(A09-F005): assertz/1 of a rule poisons the predicate

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F005
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F005_assertz_rule (xfail — flip to pass)
**Doc:** docs/database_ops.md says rules are "not supported" — see fix-A09-doc-drift.md (A09-F026).

## Bug

`_build_clause` (database_ops.py:56-61) accepts a runtime `Predicate` node
(`assertz(seen2(Z) <- q3(Z))`) and stores `Clause(head, _flatten_body(body))`
— but the stored body goals are raw term INSTANCES that
`compile_predicate_trampoline` cannot lower: the assert SUCCEEDS, then every
later query of the predicate — including its pre-existing facts — raises
`NotImplementedError: terms_to_goalop: goal shape not yet supported (q3)`.
One assertz bricks the whole predicate.

## Fix direction

Either (a) make asserted rules work: lower the body through the same
goal-transformation the DSL uses (needs the module env for cross-predicate
resolution — it is available as `module_dict`), or (b) reject rules cleanly at
assert time (`type_error`/`permission_error` LogicException) per the current
doc. Even for (a), validate lowerability BEFORE `db.assertz` so a failed
compile can't leave the clause list poisoned.

## Acceptance

- xfail passes under (a) (seen2 derives 7) or is updated to expect a clean
  typed error under (b); pre-existing facts always stay queryable.
