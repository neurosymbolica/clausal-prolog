# Known issues in C CLP(FD) Tiers 2-4

Issues and gaps in `_clpfd_propagate.c` relative to the Python reference.

## 1. `fd_eq` linearisation falls through to `EqConstraint`

**Severity: propagation weakness (not incorrect)**

The Python `fd_eq` linearises expression trees (`Add`/`Sub`/`Mult`/`Negate`)
into a `ScalarProductConstraint` for full bounds-consistency propagation back
to leaf variables.  The C `fd_eq` detects that `_linearise` succeeds on both
sides but then does `goto use_simple_eq` — posting a plain `EqConstraint`.

`EqConstraint` only narrows its top-level operands.  When one operand is an
expression tree (e.g. `Add(X, Y)`), `is_var(lhs)` is false so no narrowing
propagates back into X or Y.  The result is *sound but incomplete*: correct
solutions are always found during labeling, but the solver does more
backtracking than necessary because domains aren't pre-narrowed.

**Fix:** implement the coefficient-dict merging in C (the `merged = dict(
l_coeffs)` loop from Python `fd_eq` lines 1228-1239), then construct and post
a C `ScalarProductConstraint`.  Alternatively, detect expression trees early
and delegate the entire call to the Python `fd_eq` for those cases only.

## 2. `c_propagate` pops from front of a `PyList` — O(n) per pop

**Severity: performance**

The Python version uses `collections.deque` with O(1) `popleft()`.  The C
version internally creates `PyList` queues and pops from the front via
`PyList_SetSlice(queue, 0, 1, NULL)`, which is O(n) because it shifts all
remaining elements.

For most workloads the queue stays small (< 20 entries) so this is not
measurable.  But for large constraint networks with deep propagation chains
(e.g. cumulative scheduling), this could quadratically degrade.

**Fix options:**
- Use a C-level ring buffer or linked list for the internal queue, converting
  at the boundary when called from Python with a `deque`.
- Pop from the *end* (`PyList_GET_ITEM(queue, len-1)` + `PyList_SetSlice(
  queue, len-1, len, NULL)`) — O(1) and changes the traversal order from
  BFS to DFS.  AC-3 converges regardless of order; DFS may even be faster
  in practice due to cache locality.
- Use `PyList_Reverse` once, then pop from the end (amortised O(1) per batch).

## 3. `domain_singleton_c` returns `Py_None` — `INT64_MIN` ambiguity

**Severity: edge case correctness**

`domain_singleton_c` uses `PyObject_RichCompareBool(lo, hi, Py_EQ)`.  When
the singleton value is `float('-inf')` (i.e. INT64_MIN), `lo == hi` is true,
but the returned value is a Python float `-inf`, not an int.  Code that does
`PyLong_AsLongLong(val)` on the result will get a `TypeError`.

In practice `float('-inf')` as a singleton domain only appears in degenerate
edge cases (the domain `((-inf, -inf),)` is semantically empty in CLP(Z)).
But if a bug ever produces this domain, the error will be confusing.

## 4. CLP(R) sync in `c_narrow` calls `Py_TYPE(real_state)` as constructor

**Severity: fragile coupling**

When `c_narrow` detects a REAL_KEY attribute and needs to update the real
interval, it reconstructs the RealVar by calling
`PyObject_CallFunctionObjArgs(RealVarCls, lo_py, hi_py, r_constraints, NULL)`
where `RealVarCls = Py_TYPE(real_state)`.

This assumes the RealVar constructor signature is `(lo, hi, constraints)`.
If `clausal.logic.clpr.RealVar` ever changes its constructor, this will
break silently (wrong field values) or raise a `TypeError`.

**Fix:** cache a `_sync_real(var, fd_lo, fd_hi, trail)` Python helper from
`clpfd.py` that wraps the RealVar reconstruction, so the C code only calls
one stable interface.

## 5. No `__slots__` / `__repr__` on C constraint types

**Severity: cosmetic / debugging**

The Python constraint classes define `__slots__` and inherit a default
`__repr__`.  The C types expose members via `PyMemberDef` (functionally
equivalent to `__slots__`) but lack `__repr__`.  This makes debugging
harder — `print(constraint)` shows `<NeConstraint object at 0x...>` instead
of the fields.

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

