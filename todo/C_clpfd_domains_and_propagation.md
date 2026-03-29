# Move CLP(FD) domain operations and propagation to C

## Context

`clausal/logic/clpfd.py` (1,706 lines) implements the finite-domain constraint
solver.  It is the hottest pure-Python module in constraint-heavy workloads.
In nqueens, `fd_ne` alone accounts for 450K calls / 0.179s cumtime, and the
domain operations it calls internally (intersection, removal, narrowing) are
called millions of times during propagation.

### Profile data

| Function | Benchmark | Calls | tottime | cumtime |
|----------|-----------|-------|---------|---------|
| `fd_ne` | nqueens | 450,066 | 0.132s | 0.179s |
| `fd_gt` (→ fd_lt) | fib | 121,392 | 0.037s | 0.051s |
| `fd_le` | qsort | 38,000 | 0.012s | 0.016s |

These numbers undercount the real cost — the domain operations called FROM
these functions (intersection, narrowing, propagation) are not separately
profiled because they're inlined/called within the same Python frame.

### Why C

The domain representation is a sorted tuple of `(lo, hi)` interval pairs.
Operations like intersection and removal iterate over these tuples with tight
loops and integer comparisons — exactly the workload where C is 10–50x faster
than Python.  The propagation queue is a simple worklist algorithm.

## What to move

### Tier 1 — Domain operations (pure functions, no dependencies)

These are self-contained and can be moved first:

```python
# clausal/logic/clpfd.py — approximate line numbers

domain_from_range(lo, hi)          # ~line 50   — create ((lo, hi),)
domain_contains(domain, value)     # ~line 65   — membership test
domain_min(domain)                 # ~line 80   — first interval lo
domain_max(domain)                 # ~line 85   — last interval hi
domain_size(domain)                # ~line 90   — sum of interval widths
domain_intersection(d1, d2)        # ~line 100  — sorted merge, HOT
domain_union(d1, d2)               # ~line 140  — sorted merge
domain_remove(domain, value)       # ~line 180  — remove single int
domain_remove_above(domain, limit) # ~line 210  — truncate upper
domain_remove_below(domain, limit) # ~line 240  — truncate lower
domain_subtract(d1, d2)            # ~line 270  — set difference
domain_to_list(domain)             # ~line 300  — expand to list of ints
```

The domain is always a tuple of `(int, int)` pairs sorted by lo, non-overlapping,
non-adjacent.  For example, `{1,2,3,5,7,8}` = `((1,3), (5,5), (7,8))`.

### Tier 2 — Constraint posting and narrowing

These call into domain operations and unify/trail:

```python
_ensure_fd(var, trail)             # create FDVar attribute if not present
_narrow(var, new_domain, trail, queue)         # apply domain change
_narrow_if_changed(var, new_domain, trail, queue)  # skip no-op
propagate(queue, trail)            # worklist propagation loop
_post_constraint(constraint, trail)            # register + propagate
```

### Tier 3 — Constraint classes

Each constraint has a `propagate(queue, trail)` method.  The hot ones:

- `NeConstraint` — used in nqueens (450K calls to fd_ne)
- `LtConstraint` / `LeConstraint` — used in fib/qsort
- `EqConstraint` — general equality
- `AllDiffConstraint` — global constraint
- `ScalarProductConstraint` — linearised arithmetic

### Tier 4 — Public API functions

```python
fd_eq(l, r, trail)   fd_ne(l, r, trail)
fd_lt(l, r, trail)   fd_le(l, r, trail)
fd_gt(l, r, trail)   fd_ge(l, r, trail)
all_different(vars, trail)
labeling(vars, trail)
in_fd(var, lo, hi, trail)
```

## Overlaps

- `clpfd_skip_resolve_for_vars.md` — a minor Python-level tweak to fd_eq/ne/lt/le.
  Superseded by this todo (the C version won't call `_resolve` at all for Vars).
- The `_resolve` function evaluates arithmetic expression trees.  Keep it in
  Python (it's only called for non-Var, non-int operands which is rare).

## Build approach

Create `clausal/logic/_clpfd_core.c`:

```c
// Domain represented as C array of (int64_t lo, int64_t hi) pairs
// Stored as a Python tuple of 2-tuples for compatibility with existing code
// Internal C functions work on a stack-allocated array, convert on boundaries
```

Add to `setup.py`:
```python
ext_clpfd = Extension(
    "clausal.logic._clpfd_core",
    sources=["clausal/logic/_clpfd_core.c"],
    extra_compile_args=extra_compile_args,
)
```

In `clpfd.py`, import with fallback:
```python
try:
    from clausal.logic._clpfd_core import (
        domain_intersection, domain_union, domain_remove, ...
    )
except ImportError:
    pass  # Python implementations above
```

## Gotchas

1. **Domain representation must stay compatible** with Python code that reads
   domains.  The C functions should accept and return the same tuple-of-tuples
   format.  Internal C representation can be a flat array.

2. **`_narrow` calls `trail.undo_push`** to record domain changes for
   backtracking.  The C code needs to call back into the Trail C object.
   Since Trail is defined in `_variables.c`, you'll need to either:
   - Link against `_variables` (tricky with separate .so files)
   - Use `PyObject_CallMethod` to call trail methods (slower but safe)
   - Add domain narrowing to `_variables.c` itself (cleanest but makes the file bigger)

3. **Constraint propagation creates a Python queue** (list of constraint objects).
   Each constraint's `propagate()` is a Python method.  The C propagation loop
   would need to call back into Python for each constraint.  Alternatively, move
   the hot constraint classes (NeConstraint, LtConstraint) to C too.

4. **`_ensure_fd` uses attributed variables** (`put_attr`/`get_attr` from
   `_variables.c`).  The C code can call these directly.

5. **Arithmetic expression evaluation** (`_resolve`, `_linearise`) should stay
   in Python — it's complex, rarely called (only for expression trees), and
   not performance-critical.

## How to verify

```bash
# Before
python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep -E 'fd_|domain_|propagat|narrow'

# After
pip install -e . && python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep -E 'fd_|domain_|propagat|narrow'

# Correctness
python -m pytest tests/ -k "clpfd or clp_fd or nqueens or sudoku" -x -q
python -m pytest tests/conformity/ -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: nqueens drops by 0.3–0.5s, fib by 0.02–0.05s.
Result values must not change.
