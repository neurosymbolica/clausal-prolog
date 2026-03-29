# Move CLP(R) interval arithmetic to C

## Context

`clausal/logic/clpr.py` (923 lines) implements the real-domain constraint solver
using interval arithmetic with outward rounding.  The core operations (`_iadd`,
`_isub`, `_imul`, `_idiv`, `_ipow_int`, `_isqrt`, plus transcendentals) perform
floating-point computation with explicit rounding direction control.

Not hot in current benchmarks (fib/nqueens/qsort don't use CLP(R)), but
CLP(R) workloads (e.g., continuous optimisation, hybrid discrete-continuous
problems) will be bottlenecked by these functions.

## What to move

### Tier 1 — Interval arithmetic core

```python
# clausal/logic/clpr.py — key functions

_dn(x)                  # round toward -infinity
_up(x)                  # round toward +infinity
_iadd(a, b)             # interval addition → (lo, hi)
_isub(a, b)             # interval subtraction
_imul(a, b)             # interval multiplication (9-case)
_idiv(a, b)             # interval division (handles zero-crossing)
_ipow_int(a, n)         # interval integer power
_isqrt(a)               # interval square root
_iabs(a)                # interval absolute value
_ineg(a)                # interval negation
```

These are all pure functions: `(float, float) → (float, float)`.

### Tier 2 — Transcendental interval functions

```python
_isin(a)   _icos(a)   _itan(a)
_iexp(a)   _ilog(a)
_iasin(a)  _iacos(a)  _iatan(a)
```

### Tier 3 — Constraint propagation

```python
RealEqConstraint.propagate(queue, trail)
RealLeConstraint.propagate(queue, trail)
RealLtConstraint.propagate(queue, trail)
RealNeConstraint.propagate(queue, trail)
_propagate(queue, trail)    # worklist loop
```

### Tier 4 — Public API

```python
real_eq(l, r, trail)   real_ne(l, r, trail)
real_lt(l, r, trail)   real_le(l, r, trail)
real_gt(l, r, trail)   real_ge(l, r, trail)
in_real(var, lo, hi, trail)
label_real(vars, trail, eps)
```

## Build approach

Create `clausal/logic/_clpr_core.c`.  The interval arithmetic functions are
straightforward C with `<fenv.h>` for rounding mode control:

```c
#include <fenv.h>
#include <math.h>

static double dn(double x) {
    // Current Python: math.nextafter(x, -math.inf)
    return nextafter(x, -INFINITY);
}

static double up(double x) {
    return nextafter(x, INFINITY);
}

// Interval: (double lo, double hi)
// Python representation: 2-tuple of floats
```

## Gotchas

1. **Rounding mode**: The Python implementation uses `math.nextafter` to
   simulate outward rounding (one ULP wider).  In C, you can use `fesetround`
   for exact directed rounding, or continue using `nextafter` for portability.
   `fesetround` is faster but has thread-safety concerns on some platforms.

2. **Special values**: Intervals can be `(-inf, inf)` for unconstrained.
   Division by an interval containing zero produces `(-inf, inf)`.  The C code
   must handle `NaN`, `±inf`, and zero-width intervals correctly.

3. **9-case multiplication**: `_imul` considers all combinations of signs of
   interval endpoints.  The Python implementation has explicit branches.  The C
   version can use the same structure or compute all 4 products and take min/max.

4. **Constraint propagation** calls back into Python for `put_attr`/`get_attr`
   (attributed variables).  Same pattern as CLP(FD) — see
   `C_clpfd_domains_and_propagation.md` for approach.

5. **Transcendentals** use `math.sin`/`math.cos` etc. with outward rounding.
   In C, use `sin`/`cos` from `<math.h>` with `fesetround(FE_DOWNWARD)` /
   `fesetround(FE_UPWARD)`.  Be aware that libm transcendental accuracy varies
   by platform; `nextafter` padding may still be needed.

## Overlaps

None with existing todos.  CLP(R) is independent of CLP(FD) and CLP(B).
The constraint framework (`constraints.py`) is shared but thin.

## How to verify

```bash
# Before
python benchmarks/workloads.py   # baseline (CLP(R) not in default benchmarks)
python -m pytest tests/ -k "clpr or real" -x -q

# After
pip install -e . && python -m pytest tests/ -k "clpr or real" -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q

# For performance, need a CLP(R) benchmark (not yet in benchmarks/workloads.py)
```

Expected: CLP(R)-heavy workloads should see 10–50x speedup on interval operations.
Result values must not change.
