# Retract-conjunction fix: follow-ups from the round-4 review (2026-10-16)

1. **clause/2 returns a partial-list HEAD as an engine object** (Major; same on main). `c([H|T])` comes back as `[H, StarUnpack(value=T)]`, so `retract((d([a,b,c], X) :- X = [a,b,c]))` deletes nothing where Scryer deletes. Misses only. The leak guard covers bodies, not heads.
2. ~~**int/float conflation is data-destructive through retract**~~ FIXED 2026-10-23 with todo/done/iso-unify-conflates-int-and-float-2026-09-09.md: `2.0 = 2` fails now (ISO 7.3), so retracting `X is 1.5*2.0` leaves `X is 1.5*2`; `retract(q(1.0))` of `q(1)` is pinned in tests/test_iso_int_float_unify.py (`t(7)`) and tests/iso/test_int_float_unify_scryer.py (`assertz_then_retract_float`).
3. **The leak guard is untested** and doesn't descend into partial lists or Quantity values. Not reachable from source (constants are ground).
4. **`call(lists:append(...))` raises existence_error** while a direct `lists:append(...)` works, so `clause(H,B), call(B)` fails for bodies with qualified goals.
5. **`lists:G` with unbound G is refused at load**, and the message prints an internal `VarRef(i=1)`.
6. **if_/3 bodies still fail closed**, though their written term is now stored; lifting that ruling would turn 31 misses into matches.
7. **test_the_source_body_survives_the_bytecode_cache assumes the in-tree .pyc**: it fails under PYTHONPYCACHEPREFIX (a downstream checker's environment) and passes without it. Make it locate the cached file via importlib.util.cache_from_source / sys.pycache_prefix.
