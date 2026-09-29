# Query cache keys on `id(module)` while `_coerce_module` can mint a transient Module

**Found:** 2026-09-06 by the P3-3 Task 6 reviewer (F9). Pre-existing pattern;
newly reachable through `solve(goal, "plain.python.module")` now that `solve`
accepts a str designator.

`clausal/logic/solve.py::_goal_cache_key` returns `(structural_key, id(module))`
(~:323) and `_query_cache` does not retain the `Module` object. For a `.clausal`
module the `__clausal_module__` object is stable, so the key is sound (and
`tests/test_qualified_goals.py::TestTermToGoalQualified::
test_the_qualified_cell_goal_is_cached_per_resolved_module` pins the
resolved-module key). For a PLAIN Python module (no `__clausal_module__`),
`_coerce_module` (~:571) mints a FRESH `Module(module.__name__,
module_dict=vars(module))` on every call; that object is collected as soon as
`solve` returns, so its `id` is immediately reusable — a later, unrelated
Module can land on the same id and hit a stale compiled entry whose code was
resolved against a different `module_dict`.

**Not observed in practice** (CPython id reuse + same structural goal + a
different module is a narrow coincidence), but it is a silent-wrong-code path,
not a diagnostic one.

**Fix options.**
1. Cache the wrapping: memoize `_coerce_module`'s plain-module wrap on the
   Python module object (e.g. set `module.__clausal_module__` once, or a
   `WeakKeyDictionary`), so the same py-module always yields the same `Module`
   and its id is stable for as long as the py-module lives.
2. Key the cache on something stable instead of `id()` — the module's dotted
   name plus a per-`Module` generation counter bumped on `Database.mutate`
   writes (the P3-3 write gate makes that counter cheap to maintain).
3. Keep a strong reference to the `Module` inside the cache entry so the id
   cannot be reused while the entry lives (simplest; costs memory for
   transient wraps).

Owner: the query-cache / `_compile_as_query` code, not the qualified-goal
work. Home: P3-3 Task 9 (perf/reconciliation) if option 1 is chosen, since
it also removes a per-call `Module` allocation on the plain-module path.

## Closed 2026-09-30

REPRODUCED on 9b6b58a1 as a silent wrong answer, not a narrow coincidence: two
plain Python modules binding `g` to handles of `p/1` and `q/1`, queried with
the same `g(X)` goal in turn, answered each other's value in 14 of 20 pairs
(the second wrap lands on the first one's freed id almost every time).

Fixed with option 3 on fix/todo-batch-2-2026-09-30: the cache entry holds its
module (slot 4), so the id cannot be reused while the entry lives. No
semantic change for plain modules (each call still wraps afresh); option 1
(memoize the wrap, which would also let those queries HIT) is left as a perf
follow-up -- it changes whether an assertz into a plain module's wrap
persists across calls. Pinned by tests/test_query_cache_transient_module.py
(the 40-pair loop, and a deterministic keep-alive check).
