# Known issues in C CLP(FD) Tiers 2-4

Issues and gaps in `_clpfd_propagate.c` relative to the Python reference.

## 1. ~~`fd_eq` linearisation falls through to `EqConstraint`~~ DONE

Implemented coefficient-dict merging in C `py_fd_eq`: when at least one
operand is an expression tree (`_is_fd_expr` guard), both sides are
linearised, coefficients are merged (subtracting RHS from LHS), and a
`ScalarProductConstraint` is posted for full bounds-consistency propagation.
Added `_is_fd_expr` Python helper to gate the linearisation path.

## 2. ~~`c_propagate` pops from front of a `PyList` — O(n) per pop~~ DONE

Changed to pop from end (`PyList_GET_ITEM(queue, len-1)` + `SetSlice`),
giving O(1) per pop.  Switches traversal from BFS to DFS; AC-3 converges
regardless of order.

## 3. ~~`domain_singleton_c` returns `Py_None` — `INT64_MIN` ambiguity~~ DONE

Added `PyLong_Check(lo)` guard in `domain_singleton_c` — if the singleton
value is not a Python int (e.g. `float('-inf')`), returns `Py_None` instead
of the non-int value.

## 4. ~~CLP(R) sync in `c_narrow` calls `Py_TYPE(real_state)` as constructor~~ DONE

Added `_sync_real(var, fd_lo, fd_hi, trail)` Python helper in `clpfd.py`;
C code now calls `fn_sync_real` instead of directly constructing a `RealVar`.
The Python `_narrow` was also refactored to call `_sync_real`.

## 5. ~~No `__slots__` / `__repr__` on C constraint types~~ DONE

Added `tp_repr` functions for all constraint type families:
`BinaryConstraint_repr` (Eq/Ne/Lt/Le), `AllDiffConstraint_repr`,
`SumConstraint_repr`, `ScalarProductConstraint_repr`.  Each shows the
short type name and its fields, e.g. `EqConstraint(X, 5)`.

## 6. `_collect_vars_from` called via Python for Sum/ScalarProduct `__new__`

**Severity: minor performance**

When constructing `SumConstraint` or `ScalarProductConstraint`, the C
`__new__` calls the Python `_collect_vars_from` function once per element
to build the `.vars` tuple.  This only happens at constraint construction
time (not during propagation), but for constraints over many variables it
adds Python call overhead.

Not worth optimising unless profiling shows it matters.


## IMPORTANT: Python fallback requirement

All C extensions MUST keep the Python reference implementation as a fallback.
Pattern:

```python
# Python reference implementation
def _foo_py(...):
    ...

# C-accelerated version with fallback
_foo = _foo_py
try:
    from clausal.logic._c_module import _foo
except ImportError:
    pass
```

Do NOT delete the Python originals when adding C versions. The codebase must
work correctly (just slower) if C extensions fail to build.

