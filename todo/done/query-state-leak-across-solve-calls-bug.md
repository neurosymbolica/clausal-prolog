# BUG: successive solve() on one loaded module leaks the first query's bindings into all later queries

> **RESOLVED 2026-06-24** — fix in `clausal/logic/solve.py` (`_goal_cache_key` /
> `_structural_key`), regression test `tests/test_query_cache_value_isolation.py`.
>
> ## Root cause (not a trail-unwind bug)
>
> The "Likely cause" guess below (trail/constraint store not unwound) was wrong — this is a **query-cache**
> bug. `solve()` compiles a top-level goal into a zero-arity `_query` predicate, baking ground arguments
> into the generated code as **literal constants**, and memoises the compiled function in
> `solve._query_cache`. The cache key keyed on argument *types* only — so `plus_ten(1, V)` and
> `plus_ten(2, V)` shared one entry: `(plus_ten, (int, Var), id(module))`. The second query reused code with
> the literal `1` baked in → `11`. Reusing the module wasn't even required; *any* two same-typed ground
> queries collided. (This is exactly the `_query_cache` gotcha noted in project memory.)
>
> ## Fix
>
> Replaced the type-only key with a recursive, value-sensitive structural key (`_structural_key`): ground
> leaves key on `('lit', type, value)`, variables key on first-occurrence index (so `p(V,V)` ≠ `p(V,W)`),
> and compound/predicate/sequence terms recurse. Goals with an unhashable ground leaf (list/dict/ndarray)
> are simply not cached. Because value-keying makes the cache grow with distinct argument values, it is now
> bounded (`_QUERY_CACHE_MAX`, FIFO eviction) — the prior type-only key was naturally small. The documented
> "clear `_query_cache` between solves" workaround is no longer needed.
>
> ---
>
> *Original report follows.*

**Reported 2026-06-24.** Hit **independently by three agents** during a Clausal formalization calibration
(two formalizers + a scorer), each of which had to work around it. High severity: it **silently returns
wrong answers** (no error), and querying one loaded module more than once is the *normal* harness pattern.

## Symptom

Load a `.clausal` module once (Python API `_load_module`, or any long-lived `Module`), then run several
**independent** top-level `solve()` queries against it. The **first** query's variable bindings pin every
subsequent query's result — the trail / constraint store is not unwound between top-level queries on the
same module instance.

## Minimal repro

`todo/query-state-leak-repro/` — `leakmod.clausal`:
```clausal
plus_ten(X, Y) <- (Y == X + 10)
```
`leak_repro.py` (run `source /workspace/clausal/venv/bin/activate && python .../leak_repro.py`):
```python
import sys; sys.path.insert(0, "/workspace/clausal")   # lazy Var/solve resolution needs clausal ahead of script dir
import clausal.import_hook
from clausal.import_hook import _load_module
from clausal import Var, solve

m = _load_module("leakmod", ".../leakmod.clausal")      # load ONCE, reuse (the leak condition)
def run(x):
    V = Var()
    for _ in solve(m.plus_ten(x, V)):
        return V.value
print(run(1), run(2), run(5))                           # -> 11 11 11   (BUG; expect 11 12 15)
```

Observed:
```
plus_ten(1,?)=11   (expect 11)
plus_ten(2,?)=11   (expect 12)   <- pinned to first query
plus_ten(5,?)=11   (expect 15)   <- pinned to first query
CONTROL fresh-module-per-query: 11 12 15   (correct)
```

## Scope (what reproduces vs not)

- **Python API — CONFIRMED.** Reusing a loaded module across `solve()` calls leaks; every later query is
  pinned to the first query's bindings (repro above).
- **`.clausal` testing harness — does NOT reproduce (isolated).** Running the *same* variable-pinning
  pattern as three `Test` clauses in one file gives the correct `11 / 12 / 15` (3/3), and a prior
  var-binding does **not** poison a later `not (Goal, A==...)`. So the test runner resets trail/bindings
  between `Test` clauses. Two calibration agents reported "test-harness order-dependence" and rewrote
  negative controls to bind-and-compare — but that did **not** reproduce minimally; it was most likely
  their *scoring harnesses* (which drive the **Python API**, where the leak is real), not the `.clausal`
  runner. Left here as unconfirmed unless a minimal `.clausal`-runner repro turns up.
- Reading a binding **after** the solution loop exits (vs inside) is a separate, expected trail-unwind
  effect, not this bug.

## Impact

A harness that queries a module more than once can silently report wrong results. In a downstream tax-domain calibration the
numeric score **spuriously collapsed to 1/9** until the scorer reloaded a fresh module per query; correct
score with fresh-per-query is 9/9. Any multi-case oracle/test that reuses a module instance is at risk.

## Likely cause

Trail not unwound / attributed-variable constraint store not reset between independent top-level queries on a
`Module`; or the `Solutions` iterator shares mutable state with the module across calls.

## Workaround (in use)

Load a **fresh module instance per query** (control above passes), or otherwise reset the trail between
top-level queries. Fresh-per-query is the robust fix the calibration harnesses adopted.
