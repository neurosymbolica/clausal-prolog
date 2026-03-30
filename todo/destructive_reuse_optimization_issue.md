# Destructive Reuse Optimization — Issues & Design Notes

## Implementation Summary

The optimization has been implemented with three components:

1. **Destructive variant builtins** (`lists.py:_append_dr__3`, `dict_set.py:_dict_put_dr__4`, `dict_set.py:_set_union_dr__3`): trampoline-protocol functions that attempt in-place mutation guarded by `sys.getrefcount()`, falling back to the standard copying implementation when the object is shared.

2. **Compile-time liveness analysis** (`compiler.py:_find_destructive_reuse_goals`): identifies clause body goals eligible for destructive reuse based on five criteria, including alias detection through Unify chains and And-conjunction flattening.

3. **Goal rewriting** (`compiler.py:_apply_destructive_reuse`): rewrites eligible Call goals to reference the DR variant dispatch functions injected into `base_globals`.

## Resolved Issues

### 1. Alias-through-Unify detection (RESOLVED)

**Was:** Body-only variables unified with head variables could be incorrectly marked as eligible.

**Fix:** `_head_aliased_var_ids()` computes the transitive closure of Var-Var Unify relationships, propagating head-var status through alias chains. A body var unified (directly or transitively) with any head var is excluded from DR eligibility.

### 2. CPython-specific `sys.getrefcount` guard (RESOLVED)

**Was:** The `<= 3` threshold assumed CPython's reference counting, risking crashes or incorrect behavior on PyPy/GraalPy.

**Fix:** Module-level `_HAS_REFCOUNT` flag (in both `lists.py` and `dict_set.py`) checks `platform.python_implementation() == "CPython"` and `hasattr(sys, "getrefcount")`. On non-CPython runtimes, the DR fast path is skipped entirely and the standard (copying) path is always used.

### 3. SetTerm frozenset limitation (ACKNOWLEDGED)

**Status:** Investigated but not changed. Converting `SetTerm._elements` from `frozenset` to `set` would break `__hash__` (needed for SetTerm in dicts/sets) and change the `.elements` property type. The DR variant already saves the `SetTerm` wrapper allocation by reusing the existing object. The frozenset union allocation is unavoidable without deeper refactoring that would have net-negative performance.

### 4. And-conjunction flattening (RESOLVED)

**Was:** Only flat clause bodies were analyzed; eligible calls inside `And(a, b)` nodes were invisible to the optimization.

**Fix:** `_flatten_and_goals()` recursively expands `And` nodes into a flat list before analysis. The body compiler also flattens before compilation, since `And(a, b)` compiles identically to sequential `[a, b]`.

### 5. Conservative determinism check (RESOLVED)

**Was:** Only primitive goals (Unify, Evaluate, comparisons) were recognized as deterministic, preventing DR when preceded by known-safe builtins.

**Fix:** `_DETERMINISTIC_BUILTINS` frozenset lists 50+ builtins known to produce at most one solution (length, dict_get, sort, set_union, etc.). `_is_deterministic_goal()` now checks against this set in addition to the existing structural patterns.

### 6. No trail-recorded mutation undo (SAFE BY DESIGN)

**Status:** Not a bug. The current implementation is safe because:
- **Criterion 5** ensures all preceding goals are deterministic — no choice points exist that could backtrack through the mutation.
- **The refcount check** ensures the mutated object is not referenced by anyone else, so even if the subsequent unify fails, the mutation is invisible.
- The only trail.undo that runs is for the unify of the result var, not for the mutation itself.

If the optimization were extended to non-deterministic contexts in the future, trail-recorded undo would be necessary. This would require C-level trail entries that store pre-mutation state (e.g., original list contents before `extend()`). This is explicitly out of scope for the current implementation.
