# Two places still REFUSE a wrong-arity call the operator ruled should resolve normally

**Filed:** 2026-09-24, by the W4b-3 dispatch-conversion lane after applying the ruling.

**Ruling (operator, 2026-09-24):** a predicate name is name+ARITY. A call at
another arity than a local binding's resolves normally (a builtin, the local
db, another predicate); the class-era `PredicateArityMismatchError` refusal
was an artefact of `PredicateMeta` being a class.

Applied in `compiler/globals_env._inject_resolved_targets` (merged). Still
refusing, both eras agreeing, so no flip hazard -- but against the ruling:

1. `solve.call` Phase 5: `call("last", ...)` against a user `last/1` at arity
   2 refuses rather than reaching the builtin `last/2`.
2. `_dispatch_at`'s mangled-handle arm: F7's
   `test_wrong_arity_does_not_silently_resolve_to_a_builtin_at_the_other_arity`
   PINS that a local `numlist/1` called at 2 refuses rather than answering
   with the builtin `numlist/2`. The ruling reverses that pin.

Do both together, update the F7 pin to the ruled behaviour, and keep the
refusal where nothing else answers (both eras).
