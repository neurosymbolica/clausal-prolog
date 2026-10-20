# fix(A12-F004): engine helpers leak into .clausal module namespaces and break same-named user predicates

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/12-seams/findings.md` A12-F004
**Tests:** `tests/audit_2026_07_05/test_12_seams.py::TestF004EngineNamespaceLeak` (3 xfail — flip to pass; leak-set pin + `solve/2` control to update)
**Design:** A12-D002 (parked) — sanitize vs guard vs document

## Bug

Every loaded .clausal module's dict contains engine internals under their
public names: `walk`, `deref`, `unify`, `Var`, `Trail` (from
clausal.logic.variables) and `Compound`. Defining a user predicate named
`walk/2`, `deref/2` or `unify/2` fails at LOAD with
`TypeError: ..._variables.walk() takes no keyword arguments` — nowhere
near an explanation. `solve/2` works fine (not leaked), so the effective
reserved-name set is an implementation accident, not a policy.

Docs/cheat-sheet reserve only *Python builtins*. Mirror image of
A10-F013 (builtin `call/N` class shadows the `clausal.call` query API).

## Fix direction

Per A12-D002 recommendation: rename the injected engine bindings to
underscore-prefixed internals (`$walk`/`_clausal_walk` style) in the
module-dict the compiler emits against, so no public name is reserved;
as an interim guard, raise a clear "name reserved by the engine" load
error when a clause head collides with a still-leaked name. Document
whichever reserved set remains in docs/syntax.md. Sequence with the
A10-F013 fix (same seam, opposite direction).

## Acceptance

- `walk("a", "b"),` (and deref/unify) load and query correctly, or fail
  with an error that names the collision explicitly.
- Update `test_leak_is_observable_in_module_dict` (pins today's leak set)
  and the `solve/2` control alongside.
