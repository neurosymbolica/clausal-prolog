# fix(A11-F004/F005): py.* module-predicate errors bypass catch/3; arity dispatch inconsistent

- F004: `re.PatternError`/`TypeError` from regex predicates (re.py:39-43,
  114-122) escape solve() UNCAUGHT even under a catch-all `catch/3`, while
  ++-thunk Python errors ARE caught (executed differential). Same for
  reflection's raw ReifyError (see fix-A11-reflection-unbound-inputs.md).
  Family: A09-F012.
- F005: `ModulePredicate._multi_dispatch` (modules/py/__init__.py:73-84)
  yields silent failure for an unregistered arity on multi-arity predicates,
  but a single-arity predicate called with the wrong arity explodes with a raw
  arg-count TypeError.

**Fix** (A11-D001 recommendation): convert Python exceptions to catchable
LogicException terms at the ModulePredicate/trampoline boundary (the same
conversion ++ escapes get) — one fix for every py.* module; make wrong-arity
an existence/arity error consistently.

**Tests**: test_F004_invalid_pattern_catchable,
test_F004_replace_unbound_repl_fails_cleanly, test_F005_wrong_arity_* (xfail).
