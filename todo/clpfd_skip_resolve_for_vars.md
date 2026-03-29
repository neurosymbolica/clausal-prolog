# Skip `_resolve` for Vars in CLP(FD) constraint functions — DONE

## Context

The CLP(FD) constraint functions `fd_eq`, `fd_ne`, `fd_lt`, `fd_le` call
`_resolve(l)` and `_resolve(r)` on both operands after the ground-int fast
path.  `_resolve` (line 1066) evaluates arithmetic expression trees (`Add`,
`Sub`, `Mult`, etc.).  A Var is never an arithmetic expression tree, so
`_resolve(var)` always returns the Var unchanged — but still incurs a function
call, a `_Add is None` guard check, and two `isinstance` checks.

### Profile data

| Function | Benchmark | Calls | tottime | cumtime |
|----------|-----------|-------|---------|---------|
| `fd_ne` | nqueens | 450,066 | 0.132s | 0.179s |
| `fd_gt` (→ `fd_lt`) | fib | 121,392 | 0.037s | 0.051s |
| `fd_le` | qsort | 38,000 | 0.012s | 0.016s |

A Python-only guard (`if not is_var(l): l = _resolve(l)`) was attempted but
showed zero wall-clock improvement.  The `_resolve` overhead per call is ~20ns
which is below measurement noise at the benchmark level.  However, the change is
safe, clean, and correct — and it may matter in workloads with higher CLP(FD)
call density.

## What to do

**File:** `clausal/logic/clpfd.py`

In each of these four functions, find the two consecutive lines after the
ground-int fast path:
```python
    l = _resolve(l)
    r = _resolve(r)
```

Replace with:
```python
    if not is_var(l):
        l = _resolve(l)
    if not is_var(r):
        r = _resolve(r)
```

### Gotchas from prior attempt

We implemented this exact change across all four functions.  Results:

1. **fd_ne (nqueens)**: tottime stayed at 0.132s, cumtime went from 0.179s to
   0.180s — zero improvement.  The `_resolve` overhead per call is ~20ns.  With
   450K calls that's ~9ms total — below cProfile measurement noise.

2. **The real bottleneck in fd_ne is `_post_constraint` and `_ensure_fd`**, not
   `_resolve`.  If you want to actually speed up nqueens CLP(FD), the constraint
   posting machinery itself needs optimization (or move to C).

3. **`is_var` is already a C function** (from `_variables.c`), so adding
   `if not is_var(l)` before `_resolve` adds one fast C call to save one slow
   Python call.  The net saving is the difference between a C function call
   (~15ns) and `_resolve`'s Python overhead (~20ns) = ~5ns per call.  At 450K
   calls that's ~2ms.  Essentially unmeasurable.

4. **The change IS safe and correct** — it just doesn't help with current
   benchmarks.  It might matter in a workload with millions of CLP(FD) calls.

### Exact locations

- **`fd_eq`** (line ~1096): the `_resolve` lines are at ~1114–1115
- **`fd_ne`** (line ~1153): the `_resolve` lines are at ~1161–1162
- **`fd_lt`** (line ~1176): the `_resolve` lines are at ~1184–1185
- **`fd_le`** (line ~1199): the `_resolve` lines are at ~1207–1208

Do NOT change `fd_gt` or `fd_ge` — they delegate to `fd_lt`/`fd_le` after their
own ground-int fast path, so the guard is applied transitively.

### Why this is safe

A Var is never an instance of `_Add`, `_Sub`, `_Mult`, `_Negate`, `_Div`,
`_FloorDiv`, or `_Mod`.  The `_resolve` function would return it unchanged.
The code after `_resolve` already handles Vars via `is_var(l)`/`is_var(r)` checks.

## How to verify

```bash
# Before
python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep -E 'fd_(eq|ne|lt|le|gt|ge)'

# After
python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep -E 'fd_(eq|ne|lt|le|gt|ge)'

# Correctness
python -m pytest tests/ -k "clpfd or clp_fd or arithmetic" -x -q
python -m pytest tests/conformity/ -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: Minor cumtime reduction in fd_ne/fd_lt.  May not be visible in
wall-clock benchmarks.
Result values must not change.
