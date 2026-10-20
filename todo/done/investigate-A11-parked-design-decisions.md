# investigate(A11): parked design decisions — for Opus / user review

The A11 audit parked 11 design questions
(docs/superpowers/audits/2026-07-05-fable-partition/11-modules-interop/design-questions.md),
per the standing user preference. Two are cross-cutting and appended to
DESIGN-DECISIONS.md:

- **A11-D001 — error protocol for py.* module predicates**: fail-clean vs raw
  escape vs catchable; regex/reflection errors currently BYPASS catch/3 while
  ++-thunk errors are caught (executed differential). Recommended: convert at
  the ModulePredicate/trampoline boundary (one fix for all wrappers), then
  document a data-fails/usage-throws policy. Joint with A09-F012.
- **A11-D002 — coercion vs type guards in wrappers**: re `str()`-coerces
  subjects (unbound Var matches its own repr; char-lists violate
  strings-as-lists Liskov); datetime `int()`-truncates components.
  Recommended: Liskov char-list join + instantiation/type errors; reject
  fractional floats in datetime.

Module-local (D003–D011): regex reserved-name gating, optional-group None,
keyword-head reification shape, anonymous-var naming, Prolog atom
representation, arithmetic-vs-structural comparison mapping, integer
div/mod strategy, graph vertex representability/directionality, units
ergonomics (strip_units totality, callable Quantity). Options + recommendations
recorded in the design-questions ledger; each has a pointer from its fix todo.
