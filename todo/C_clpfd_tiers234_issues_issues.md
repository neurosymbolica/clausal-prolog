# Follow-up issues from the tiers 2-4 fixes

Doubts, regressions, and things that could be done better.


## A. ~~`fn_sync_real` is always non-NULL — unnecessary Python call on every `c_narrow`~~ DONE

Added `REAL_KEY &&` gate back to the `fn_sync_real` call in `c_narrow`.
When CLP(R) is not loaded, `REAL_KEY` is NULL and the entire block is skipped
— no Python call overhead on pure-FD workloads.


## B. ~~`_is_fd_expr` adds two Python calls per `fd_eq` invocation~~ DONE

Replaced with cached `PyTypeObject *` pointers (`type_Add`, `type_Sub`,
`type_Mult`, `type_Negate`) fetched from `clausal.terms` at module init.
The isinstance check is now a C-level `PyObject_TypeCheck` — no Python call.
Removed the now-unused `_is_fd_expr` helper from `clpfd.py`.


## C. ~~Coefficient merging uses `PyLong_AsLongLong` — silent overflow~~ DONE

Switched to `PyLong_AsLongLongAndOverflow` throughout the coefficient merge
loop and constant extraction.  On overflow, the linearisation path is
abandoned and control falls through to `use_simple_eq` (EqConstraint),
which is sound (just less pruning).  Python's arbitrary-precision fallback
handles the rest correctly.


## D. BFS-to-DFS change in `c_propagate` is observable (not just perf) — NO ACTION

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


## E. ~~`_sync_real` does a lazy import on every call~~ DONE

`_sync_real` now caches `REAL_KEY` and `RealVar` in module-level sentinels
(`_clpr_REAL_KEY`, `_clpr_RealVar`) on first call.  Subsequent calls skip
the import entirely — just a `_clpr_loaded` flag check.


## F. `__repr__` recursion depth on deeply nested expression trees — NO ACTION

The `BinaryConstraint_repr` function calls `PyObject_Repr` on `lhs` and
`rhs`.  If these are deeply nested expression trees (e.g. a chain of 1000
`Add` nodes), this recurses through Python's repr machinery.  Python has a
recursion limit (~1000 by default) that would raise `RecursionError`.

Not a practical concern for normal CLP(FD) use, but theoretically reachable
via programmatically generated expressions.  No fix needed unless it surfaces.
