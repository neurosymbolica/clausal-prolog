# C arithmetic implementation issues

Issues and follow-ups from the `_arithmetic_core.c` implementation.

## 1. ~~succ/2 silent overflow at LLONG_MAX~~ — FIXED

`py_arith_succ` had a fast path that converted x to `long long` via
`PyLong_AsLongLong`, then did `xv + 1` in C.  If x == LLONG_MAX
(9223372036854775807), the addition overflowed silently to LLONG_MIN.

**Fixed:** removed the `long long` fast path entirely.  Now uses
`PyNumber_Add(x_val, cached_one)` / `PyNumber_Subtract(y_val, cached_one)`
which are arbitrary-precision via Python's `PyLong`.


## 2. ~~Refcount leak on inline PyLong_FromLong(0)~~ — FIXED

Multiple functions passed `PyLong_FromLong(0)` directly to
`PyObject_RichCompareBool` without decrementing the result.

**Fixed:** cached `PyLong(0)` and `PyLong(1)` as `cached_zero` /
`cached_one` at module init.  All comparison and arithmetic sites now use
the cached references — no allocation, no leak.


## 3. ~~is_quantity() error return (-1) silently swallowed~~ — FIXED

`is_quantity()` wraps `PyObject_IsInstance` which can return -1 on error.
All call sites checked `== 1`, so -1 was treated as "not a Quantity" and
execution continued with an error indicator set on the thread.

**Fixed:** added `CHECK_QUANTITY(obj)` macro that checks for -1 and
`return NULL` to propagate, or `Py_RETURN_FALSE` on 1 to fall back.
All call sites now use this macro.


## 4. ~~gcd/lcm call PyImport_ImportModule("math") per invocation~~ — FIXED

`py_arith_gcd` and `py_arith_lcm` both called
`PyImport_ImportModule("math")` on every predicate invocation.

**Fixed:** cached `math.gcd` as `math_gcd_func` at module init.  Both
gcd/3 and lcm/3 now call `PyObject_CallFunctionObjArgs(math_gcd_func, ...)`
directly.


## 5. Arbitrary precision: fully supported (not finite-domain)

All arithmetic goes through Python's `PyNumber_*` API and `PyLong` type,
which are arbitrary-precision.  There is no truncation to int64 or any
fixed width.

- `succ/2`: `PyNumber_Add` / `PyNumber_Subtract` — arbitrary precision
- `plus/3`: `PyNumber_Add` / `PyNumber_Subtract` — arbitrary precision
- `gcd/3`, `lcm/3`: delegate to `math.gcd` — arbitrary precision
- `divmod_/4`: `PyNumber_Divmod` — arbitrary precision
- `exp_mod/4`: `PyNumber_Power` (three-arg) — arbitrary precision
- `popcount/2`: `int.bit_count()` — works on any size int
- `msb/2`, `lsb/2`: `int.bit_length()` — works on any size int
- `abs/2`, `max/3`, `min/3`, `sign/2`: comparison/abs — no precision issues
- `between/3`: range bounds are PyLong objects; generate mode returns to
  Python which iterates with `range()` — arbitrary precision


## 6. plus/3 accepts non-numeric types (won't fix — matches Python)

The Python `_plus__3_py` allows any types that support `+`/`-` operators
(e.g. strings via `+`).  The C version does the same via `PyNumber_Add` /
`PyNumber_Subtract`, which raises `TypeError` for non-numeric types that
lack `__add__`.  This matches the existing Python behavior exactly, so no
change needed.  If type-restriction is desired it should be done in both
versions simultaneously — not a C-specific issue.


## 7. ~~between/3 check mode does a redundant unify~~ — FIXED

When x was already bound and in range, the C version called
`mark_unify(x, x_val, trail)` — always succeeds, always a no-op.

**Fixed:** now returns `Py_True` as a "success, no mark to undo" sentinel.
The Python wrapper yields without touching the trail.


## 8. No Trail type-check on cast (won't fix — consistent with codebase)

All functions cast `trail_obj` to `TrailObject *` without checking
`Trail_Check(trail_obj)`.  Passing a non-Trail object causes undefined
behavior.  This is consistent with every other C extension in the codebase
(`_constraints_dif.c`, `_tabling_core.c`, `_list_unify.c`, etc.) which all
use the same raw-cast pattern.  Adding a check here alone would be
inconsistent; if this is addressed it should be done project-wide.
