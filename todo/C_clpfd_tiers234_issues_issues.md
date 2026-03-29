# Follow-up issues from the tiers 2-4 fixes

Doubts, regressions, and things that could be done better.


## A. `fn_sync_real` is always non-NULL — unnecessary Python call on every `c_narrow`

The old C code guarded CLP(R) sync with `if (REAL_KEY)`, where `REAL_KEY` is
NULL when `clpr` is not loaded.  The new code guards with `if (fn_sync_real)`,
but `_sync_real` is defined unconditionally in `clpfd.py`, so `fn_sync_real`
is **always** non-NULL.  This means every `c_narrow` call now crosses into
Python to call `_sync_real`, which calls `get_attr(var, REAL_KEY)` and returns
True immediately when the var has no real attribute.

For workloads that never use CLP(R), this adds a Python function call + attr
lookup per narrowing step that the old code avoided entirely.

**Fix:** either gate on `REAL_KEY` again (``if (REAL_KEY && fn_sync_real)``),
or have `_sync_real` set a module-level flag on import so C can skip the call
when clpr was never loaded.


## B. `_is_fd_expr` adds two Python calls per `fd_eq` invocation

Every `fd_eq(l, r, trail)` now calls `_is_fd_expr(rl)` and
`_is_fd_expr(rr)` — two Python function calls — before deciding whether to
attempt linearisation.  For the overwhelmingly common `var == int` case, both
calls return False and we fall through to EqConstraint anyway.

**Fix:** cache the four expression type objects (`_Add`, `_Sub`, `_Mult`,
`_Negate`) as `PyTypeObject *` in the C module and do a direct
`PyObject_TypeCheck` in C, avoiding the Python call entirely.  The types can
be fetched from `clausal.terms` at module init (same lazy-import pattern
`_ensure_term_imports` uses) or fetched once on first `fd_eq` call.


## C. Coefficient merging uses `PyLong_AsLongLong` — silent overflow for large coefficients

The `fd_eq` linearisation merge loop in C extracts coefficient values via
`PyLong_AsLongLong`, which saturates at `INT64_MIN`/`INT64_MAX` for Python
ints that exceed 64 bits.  Python handles arbitrary-precision natively.

In practice CLP(FD) coefficients are small integers (typically -10 to 10), so
this is unlikely to surface.  But if someone constructs a ScalarProduct with
huge coefficients, the C path would silently produce wrong results while the
Python fallback would be correct.

**Fix:** use `PyLong_AsLongLongAndOverflow` and fall through to the
`use_simple_eq` / Python-fallback path on overflow.


## D. BFS-to-DFS change in `c_propagate` is observable (not just perf)

Switching from pop-front (BFS) to pop-back (DFS) is correct for AC-3
convergence, but it changes the **order** in which variables are revisited.
This can change:

- Which solution `labeling/2` finds first (if the search isn't
  deterministic).
- How many propagation steps are needed to reach fixpoint (DFS can be fewer
  or more, depending on the constraint graph).
- Test output for any test that asserts on solution ordering.

No tests broke, but downstream users who rely on deterministic first-solution
order from CLP(FD) labeling might notice differences.  This isn't a bug — it's
a documented-acceptable change — but it's worth keeping in mind if someone
reports "same query, different first answer".


## E. `_sync_real` does a lazy import on every call

```python
def _sync_real(var, fd_lo, fd_hi, trail):
    from clausal.logic.clpr import REAL_KEY, RealVar
    ...
```

Python caches the import (just a dict lookup after first call), so this is
cheap.  But in a tight narrowing loop it's still a `__import__` + two
`getattr` calls per invocation.  The old inline code in `_narrow` had the same
pattern, so this is not a regression — just an inherited inefficiency.

**Fix:** hoist the import to module level behind a try/except, same as the
other optional imports, and let `_sync_real` reference the module-level names.


## F. `__repr__` recursion depth on deeply nested expression trees

The `BinaryConstraint_repr` function calls `PyObject_Repr` on `lhs` and
`rhs`.  If these are deeply nested expression trees (e.g. a chain of 1000
`Add` nodes), this recurses through Python's repr machinery.  Python has a
recursion limit (~1000 by default) that would raise `RecursionError`.

Not a practical concern for normal CLP(FD) use, but theoretically reachable
via programmatically generated expressions.  No fix needed unless it surfaces.
