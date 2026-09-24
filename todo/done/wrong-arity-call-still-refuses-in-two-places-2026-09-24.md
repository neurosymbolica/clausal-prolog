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

## Resolved (2026-09-24, branch fix/name-arity-ruling-remaining-refusals-2026-09-24)

Both sites now follow the ruling, mirroring `globals_env._inject_resolved_targets`:

1. `solve.call` Phase 5: a module-dict binding (class or handle) that is not
   the name's predicate at the call arity (`predicate.binding_grants_arity`:
   declared there, and for an import, imported there) is no longer the
   call's target.  The call asks `module.db.get_dispatch` (the calling
   module's own row, then the builtin registry) and then Phase 6; when
   neither answers it REFUSES naming the name used
   (`_refuse_unqualified_other_arity`) -- it never resolves the other arity
   in the binding's owner.  (Final form after two review rounds and the
   aliased-import ruling; see
   `todo/done/aliased-import-other-arity-resolves-in-the-owner-2026-09-24.md`.)
2. `predicate._dispatch_at`:
   - handle arm: `Database.get_dispatch` (the module's row at the call arity,
     else the builtin registry) is asked BEFORE
     `_refuse_if_known_at_another_arity`; the refusal stays after it.
   - class arm: when `_refuse_call_at` would refuse, the call is first
     resolved in the class's own module (`row._db.get_dispatch`, new helper
     `_resolve_other_arity_of_class`), i.e. exactly what the handle arm asks.
     This also fixes a real era DISAGREEMENT: a module's own `ping/2` row
     answered a `ping/2` call through a `ping/0` handle but was refused
     through the `ping/0` class.

`_dispatch_at`'s two arms serve a binding held DIRECTLY or reached by a
QUALIFIED reference; an unqualified name never reaches their other-arity
fallback (body calls are rerouted at compile time, meta-calls localized --
see the aliased-import todo).

Tests: F7's `test_wrong_arity_does_not_silently_resolve_to_a_builtin_at_the_other_arity`
is REVERSED (renamed `test_wrong_arity_resolves_normally_to_the_builtin_at_the_call_arity`,
both eras, docstring cites the ruling); w4b3's
`test_dotted_sys_modules_route_at_another_arity` updated (run-time half now
answers with the owner's builtin `last/2` -- a dotted, i.e. qualified,
reference).  New: both-era refusal-kept test,
own-row test, and two `solve.call` Phase 5 tests (builtin; local row).  Every
other `PredicateArityMismatchError` pin (38 in
`test_predicate_arity_mismatch_diagnostic.py`, the w4b3 phrase/time_goal/
specializer/Phase-5 refusals, F7's `pred/1`-at-2) is KEPT: nothing else
answers at the call arity there, and each still passes unmodified.
