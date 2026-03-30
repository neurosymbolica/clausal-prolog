# C arithmetic implementation issues

Issues and follow-ups from the `_arithmetic_core.c` implementation.

## 1. succ/2 silent overflow at LLONG_MAX (correctness bug)

`py_arith_succ` has a fast path that converts x to `long long` via
`PyLong_AsLongLong`, then does `xv + 1` in C.  If x == LLONG_MAX
(9223372036854775807), the addition overflows silently to LLONG_MIN and
`PyLong_FromLongLong` creates a large negative number.

The overflow fallback only triggers when `PyLong_AsLongLong` returns -1
with an error set — i.e. when the value **does not fit** in a long long.
LLONG_MAX fits, so the fallback never fires.

**Fix:** either always use `PyNumber_Add`/`PyNumber_Subtract` (simpler,
slightly slower), or explicitly check for LLONG_MAX before adding.

The backward (y→x) path has the same class of issue if y == LLONG_MIN+1,
though that's unreachable because `yv < 1` rejects negatives first.


## 2. Refcount leak on inline PyLong_FromLong(0)

Multiple functions pass `PyLong_FromLong(0)` directly to
`PyObject_RichCompareBool` without decrementing the result:

- `py_arith_succ` (lines 159, 181)
- `py_arith_divmod` (line 390)
- `py_arith_exp_mod` (line 475)
- `py_arith_popcount` (line 502)
- `py_arith_msb` (line 529)
- `py_arith_lsb` (line 560)

CPython caches small integers so this leaks one refcount to an immortal
object per call — not a real memory leak, but it is technically incorrect
and will trigger under refcount-auditing tools.  `py_arith_sign` already
does this correctly (creates `zero`, uses it, `Py_DECREF`s it).

**Fix:** create a `static PyObject *` cached zero at module init, or
allocate + DECREF locally (the `sign` pattern).


## 3. is_quantity() error return (-1) silently swallowed

`is_quantity()` wraps `PyObject_IsInstance` which can return -1 on error.
All call sites check `== 1`, so -1 is treated as "not a Quantity" and
execution continues with an error indicator set on the thread.  This can
cause confusing failures later.

**Fix:** check `< 0` after `is_quantity()` and `return NULL` to propagate.


## 4. gcd/lcm call PyImport_ImportModule("math") per invocation

`py_arith_gcd` and `py_arith_lcm` both call
`PyImport_ImportModule("math")` on every predicate invocation.  While
Python caches the module in `sys.modules`, the lookup still has overhead
(dict lookup, refcount bump, DECREF on return).

**Fix:** cache `math.gcd` as a `static PyObject *` at module init time,
similar to how `Quantity_type` is cached.


## 5. Arbitrary precision: fully supported (not finite-domain)

All arithmetic goes through Python's `PyNumber_*` API and `PyLong` type,
which are arbitrary-precision.  There is no truncation to int64 or any
fixed width — **except** for the succ/2 fast path (issue #1).

- `plus/3`: `PyNumber_Add` / `PyNumber_Subtract` — arbitrary precision
- `gcd/3`, `lcm/3`: delegate to `math.gcd` — arbitrary precision
- `divmod_/4`: `PyNumber_Divmod` — arbitrary precision
- `exp_mod/4`: `PyNumber_Power` (three-arg) — arbitrary precision
- `popcount/2`: `int.bit_count()` — works on any size int
- `msb/2`, `lsb/2`: `int.bit_length()` — works on any size int
- `abs/2`, `max/3`, `min/3`, `sign/2`: comparison/abs — no precision issues
- `between/3`: range bounds are PyLong objects; generate mode returns to
  Python which iterates with `range()` — arbitrary precision

The only narrowing to `long long` is the succ/2 fast path, which has the
overflow bug described in issue #1.  Once that is fixed (by using
`PyNumber_Add` unconditionally), the entire C extension is fully
arbitrary-precision.


## 6. plus/3 accepts non-numeric types

The Python `_plus__3_py` allows any types that support `+`/`-` operators
(e.g. strings via `+`).  The C version does the same via `PyNumber_Add` /
`PyNumber_Subtract`, which will raise `TypeError` for non-numeric types
that lack `__add__`.  This matches the Python behavior (neither validates
input types for plus), but it's a semantic question whether plus/3 should
only accept numeric operands.  Low priority — not a C-specific issue.


## 7. between/3 check mode does a redundant unify

When x is already bound and in range, the C version calls
`mark_unify(x, x_val, trail)` which unifies x with its own value — always
succeeds, always a no-op on the trail.  This is required by the return
protocol (needs to return a mark), but wastes a unify call.

**Fix:** could return a special "success, no mark needed" sentinel (e.g.
`True`) and handle it in the Python wrapper.  Minor optimization.


## 8. No Trail type-check on cast

All functions cast `trail_obj` to `TrailObject *` without checking
`Trail_Check(trail_obj)`.  Passing a non-Trail object causes undefined
behavior.  This is consistent with other C extensions in the codebase, but
worth noting.
