# fix-A07: CLP(B) module globals pin every var + BDD node forever

**Finding:** A07-F006.
**Severity:** memory — linear leak per query in long-running processes.

`clausal/logic/clpb.py:79-116`: `_var_to_id` (id→ordinal), `_id_to_var`
(ordinal→**strong ref**), `_unique_tables` (id(var)→node dict) are
module-level and never pruned. 1000 throwaway `sat(X|Y)` queries leave 2000
permanent entries in each (measured; test asserts growth < 100 over 200
queries and xfails today).

**Fix options:**
- `weakref` the var in `_id_to_var` (and a weakref callback that pops
  `_var_to_id[id]` + `_unique_tables[id]`). `enumerate_var`'s id-keying is
  only safe *because* the strong ref prevents id reuse — the weakref callback
  must run before reuse (CPython: it does, at dealloc). Unique-table entries
  keep child nodes alive; dropping a var's table releases its whole level.
- Or scope the tables per Trail (like `clpsat._sat_states` with
  `weakref.finalize`), which also fixes cross-query BDD ordering bleed.

Note: `apply`/`restrict` C code receives these dicts as arguments, so the fix
is Python-side only. Keep the C fast path in mind: `c_make_node` re-fetches
the per-var table on every node creation.

**Test:** `test_A07_F006_global_tables_bounded` (xfail strict=False).
