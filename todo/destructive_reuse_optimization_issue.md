# Destructive Reuse Optimization — Issues & Design Notes

## Implementation Summary

The optimization has been implemented with three components:

1. **Destructive variant builtins** (`lists.py:_append_dr__3`, `dict_set.py:_dict_put_dr__4`, `dict_set.py:_set_union_dr__3`): trampoline-protocol functions that attempt in-place mutation guarded by `sys.getrefcount()`, falling back to the standard copying implementation when the object is shared.

2. **Compile-time liveness analysis** (`compiler.py:_find_destructive_reuse_goals`): identifies clause body goals eligible for destructive reuse based on five criteria.

3. **Goal rewriting** (`compiler.py:_apply_destructive_reuse`): rewrites eligible Call goals to reference the DR variant dispatch functions injected into `base_globals`.

## Known Issues & Limitations

### 1. Alias-through-Unify not detected at compile time

**Issue:** If a body-only variable is unified with a head variable in a preceding goal, it becomes an alias for the caller's data:

```prolog
process(In, Out) <- Temp = In, append(Temp, [x], Out).
```

`Temp` is body-only (criterion 3 passes), dead after the append (criterion 4 passes), and `Temp = In` is deterministic (criterion 5 passes). So the compiler marks this as eligible and dispatches to `_append_dr__3`. However, `Temp` is aliased to `In`, which is the caller's data.

**Mitigation:** The runtime `sys.getrefcount(deref(source)) <= 3` check catches this case. When `Temp` is bound to `In`'s value, the value has references from both the Var binding *and* the original `In` parameter (and the caller's scope), so refcount > 3 and the destructive path is skipped.

**Risk level:** Low. The runtime check provides a correct safety net. No correctness bug, but the compile-time analysis is overly optimistic — it marks goals as eligible that the runtime then falls back from. This is a performance miss (extra dispatch overhead for the DR variant), not a correctness issue.

**Future improvement:** Add alias analysis to criterion 3: track which body variables are transitively unified with head variables. This would avoid the unnecessary DR dispatch overhead.

### 2. `sys.getrefcount()` threshold is CPython-specific

**Issue:** The `<= 3` threshold is calibrated for CPython's reference counting. It assumes:
- 1 ref from the Var's `.binding` field (C struct)
- 1 ref from the local `l1_val = deref(l1)` in the DR function
- 1 ref from `sys.getrefcount()`'s own argument

This does not work on PyPy, GraalPy, or other Python implementations without CPython-compatible `sys.getrefcount()`. On those runtimes, `sys.getrefcount()` either raises `NotImplementedError` or returns meaningless values.

**Mitigation:** The DR functions import `sys` locally and the refcount check is in a simple `if` guard. If `sys.getrefcount` is unavailable, the fallback path is taken.

**Future improvement:** Add a module-level flag (`_HAS_REFCOUNT`) that checks for CPython at import time and disables the optimization on other runtimes.

### 3. SetTerm mutation creates a new frozenset anyway

**Issue:** `SetTerm._elements` is a `frozenset`. The DR variant replaces it with `s1._elements | s2._elements`, which still allocates a new `frozenset`. The only saving is avoiding a new `SetTerm` wrapper object.

**Impact:** Minimal. The main cost for sets is the frozenset union, not the wrapper allocation. The optimization is more impactful for lists (avoiding list copy) and dicts (avoiding dict copy).

**Future improvement:** Consider using a mutable `set` internally in `SetTerm` with a copy-on-read pattern, or accept that set DR provides marginal benefit.

### 4. Only flat clause bodies are analyzed

**Issue:** The liveness analysis only operates on the flat list of goals in `clause.body`. Goals nested inside `And`, `Or`, `Not`, or `IfExpr` nodes are not analyzed. The optimization only fires when the eligible call is a top-level goal in the body.

**Impact:** Moderate. Many real Prolog clauses have flat bodies (a conjunction of top-level goals). But clauses with conditionals or disjunctions won't benefit.

**Future improvement:** Extend `_find_destructive_reuse_goals` to recurse into `And` conjunctions (which are semantically equivalent to flat goal lists). `Or` and `Not` are inherently non-deterministic or have different scoping rules, so they need more careful handling.

### 5. Determinism check is conservative

**Issue:** Criterion 5 requires ALL preceding goals to be deterministic. This prevents the optimization when any preceding goal is a predicate Call, even if that call is known to be deterministic (e.g., a single-clause fact-only predicate, or a builtin like `length/2`).

**Impact:** Moderate. Many real predicates call other predicates before the append/dict_put/set_union. The optimization won't fire in those cases.

**Future improvement:** Expand `_is_deterministic_goal()` to recognize more deterministic patterns: known-deterministic builtins (length, atom_length, succ, etc.), single-clause predicates, and calls wrapped in `once/1`.

### 6. No trail-recorded mutation undo

**Issue:** The current implementation does NOT record mutations on the trail. If the mutation fires and then backtracking occurs (e.g., the unify of the result fails), the source object remains mutated. This is safe because:
- The refcount check ensures no one else holds a reference
- The trail.undo only needs to undo the unify, not the mutation

However, if the optimization were extended to non-deterministic contexts (e.g., inside choice points), mutations would need to be reversible via the trail.

**Future improvement:** For extending beyond deterministic contexts, add trail entries that record the pre-mutation state (e.g., original list contents) and restore on undo. This would require C-level trail support.
