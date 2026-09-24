# Residual Low findings on the name+arity branch (landed with them, 2026-09-24)

Round-7 roborev of fix/name-arity-ruling-remaining-refusals-2026-09-24 had only Lows;
landed with these open:

1. solve.call Phase 5 passes a DOTTED functor into binding_grants_arity (globals_env
   passes name=None for dotted names), so
       call("alow.numlist", 3, L, module=I)    # refuses
   while a compiled `alow.numlist(3, L)` in the same module answers [1,2,3]. Pass
   name=None for a dotted functor, as globals_env does.
2. localize_goal localizes only when the caller binds the exact class/handle under a
   plain name; the leak returns in two cases (see the review) incl. the db=None path
   of _make_localizing_factory.
3. _import_index trusts a negative answer while the module dict's (id, len) snapshot
   is unchanged -- a same-size rebinding is missed until unrelated churn.
4. _is_mangled_fast runs a function-level `from clausal.logic.atoms import is_mangled`
   on every call with a string goal (hot path) -- hoist it.
Plus the pinned strict-xfail known gap: a double import `[numlist, alias(numlist, nl)]`
makes `nl(3, L)` resolve under numlist.
