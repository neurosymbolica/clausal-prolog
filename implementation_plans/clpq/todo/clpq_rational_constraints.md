# Implement CLP(Q) — constraints over rationals

## Context

CLP(Q) solves linear constraints over exact rational numbers using the simplex
method.  Unlike CLP(R) (which uses floating-point interval arithmetic), CLP(Q)
produces **exact** results with no rounding errors.  This is essential for:

- Linear programming with exact solutions
- Scheduling with fractional time units
- Financial calculations requiring exactness
- Any domain where floating-point approximation is unacceptable

SICStus Prolog and SWI-Prolog both provide `library(clpq)`.  The API mirrors
CLP(R) but with exact rational arithmetic.

## Design

### Number representation

Use Python's `fractions.Fraction` for exact rationals.  Advantages:
- Built into the standard library
- Arbitrary precision numerator/denominator
- All arithmetic operators work correctly
- Comparison operators work correctly
- Hashable (can be dict keys)

### Solver: Revised Simplex

CLP(Q) uses the **revised simplex method** for linear constraints:

1. Maintain a tableau of linear equations in standard form
2. Each constraint `a1*X1 + a2*X2 + ... = b` becomes a row
3. Slack/surplus variables handle `≤` and `≥`
4. Pivoting to find feasible/optimal solutions
5. Incremental: adding a new constraint updates the existing tableau

The key insight: CLP(Q) is **incremental**.  Each new constraint is added to
the tableau one at a time (as the user program posts them), not solved as a
batch.  The simplex algorithm must support incremental constraint addition and
backtracking (undo via trail).

### Module structure

Create `clausal/logic/clpq.py` with this structure:

```python
"""CLP(Q) — constraint logic programming over rationals.

Uses the revised simplex method for linear constraints over exact
rational numbers (Python fractions.Fraction).
"""

from fractions import Fraction
from collections import deque
from clausal.logic.variables import (
    Var, Trail, deref, is_var, unify,
    put_attr, get_attr, register_attr_hook,
)

Q_KEY = "q"  # attribute key for rational constraints

class QVar:
    """State for a rational-constrained variable."""
    __slots__ = ('lo', 'hi', 'constraints')
    def __init__(self, lo=None, hi=None, constraints=()):
        self.lo = lo   # Fraction or None (unbounded below)
        self.hi = hi   # Fraction or None (unbounded above)
        self.constraints = constraints
```

### Public API

Mirror the CLP(R) API with `q_` prefix:

```python
def q_eq(l, r, trail) -> bool:
    """Post X = Y over rationals."""

def q_ne(l, r, trail) -> bool:
    """Post X ≠ Y over rationals."""

def q_lt(l, r, trail) -> bool:
    """Post X < Y over rationals."""

def q_le(l, r, trail) -> bool:
    """Post X ≤ Y over rationals."""

def q_gt(l, r, trail) -> bool:
    """Post X > Y over rationals."""

def q_ge(l, r, trail) -> bool:
    """Post X ≥ Y over rationals."""

def in_q(var, lo, hi, trail) -> bool:
    """Declare var ∈ [lo, hi] over rationals."""

def maximize(expr, trail):
    """Find maximum of linear expression subject to posted constraints."""

def minimize(expr, trail):
    """Find minimum of linear expression subject to posted constraints."""
```

### Compiler integration

The compiler needs to recognise when CLP(Q) is active and route arithmetic
constraints to `q_eq` etc. instead of `fd_eq`.  Options:

**Option A: Explicit module import** — user writes `from clpq import ...`
and the compiler routes based on imported names.

**Option B: Type-based dispatch** — if an argument is a `Fraction`, dispatch
to CLP(Q).  This is how CLP(R) currently works (float detection in `fd_eq`
dispatches to `real_eq`).

**Recommendation: Option B** — add a `Fraction` check alongside the existing
`float` check in `fd_eq` etc.:
```python
def fd_eq(l, r, trail):
    l = deref(l)
    r = deref(r)
    if type(l) is int and type(r) is int:
        return l == r
    if _any_rational(l, r):
        from clausal.logic.clpq import q_eq
        return q_eq(l, r, trail)
    if _any_real(l, r):
        from clausal.logic.clpr import real_eq
        return real_eq(l, r, trail)
    ...
```

### Trail integration

The simplex tableau is mutable state.  For backtracking:

**Option A: Copy-on-write** — before each constraint addition, snapshot the
tableau.  On undo, restore the snapshot.  Simple but memory-heavy.

**Option B: Incremental undo** — record the pivot operations performed and
reverse them on undo.  More efficient but more complex.

**Recommendation: Option A** for the initial implementation.  The tableau is
typically small (tens of rows/columns).  Optimise later if profiling shows
it's a bottleneck.

## Gotchas

1. **Simplex pivoting** is well-documented but tricky to implement correctly.
   Edge cases: degeneracy (cycling), unbounded objectives, infeasible systems.
   Use Bland's rule to prevent cycling.

2. **Incremental constraint addition** means the tableau must be kept in a
   feasible state at all times.  Adding a new constraint that makes the system
   infeasible should return False (fail) without corrupting the tableau.

3. **`Fraction` arithmetic is slow** compared to int or float — it's exact but
   involves GCD computation on every operation.  This is fine for Python-level
   CLP(Q) but will be the bottleneck if ported to C later.  A C implementation
   should use GMP rationals (`mpq_t`).

4. **Interaction with CLP(Z)**: A rational constraint `X #= 1/3` on an integer
   variable should fail (1/3 is not an integer).  The dispatch logic must check
   for this.

5. **Interaction with CLP(R)**: If both CLP(Q) and CLP(R) are active on the
   same variable, CLP(Q) takes precedence (exact subsumes approximate).

6. **`maximize`/`minimize`**: These are non-backtrackable — they find the optimum
   and bind the result.  SWI-Prolog's `library(clpq)` provides these.

7. **Testing**: Use known LP problems with exact rational solutions.  Example:
   maximize 3*X + 5*Y subject to X ≤ 4, Y ≤ 6, X + Y ≤ 8 → solution X=2, Y=6,
   objective=36.

## Overlaps

- **CLP(R)** (`clausal/logic/clpr.py`) — similar API but different solver
  (intervals vs simplex).  Share the public API naming convention.
- **CLP(Z)** (`clpz_upgrade.md`) — dispatch from `fd_eq` etc. adds a new
  branch for rationals alongside the existing float branch.
- **C porting** (`C_clpr_interval_arithmetic.md`) — wait until CLP(Q) is stable
  before porting either CLP(Q) or CLP(R) to C.  The C versions can share a
  common rational arithmetic library (GMP).

## Tests to write

Create `tests/test_clpq.py`.  Follow the pattern in `tests/test_clpr.py`:
imports from `clausal.logic.variables` (Var, Trail, deref, unify, is_var, get_attr)
and the new `clausal.logic.clpq`.  Use `fractions.Fraction` for exact values.

```python
from fractions import Fraction as F
```

### TestBasicRationalConstraints

```python
class TestBasicRationalConstraints:
    def test_eq_ground_rationals(self):
        """F(1,3) == F(1,3) succeeds."""
        trail = Trail()
        assert q_eq(F(1, 3), F(1, 3), trail)

    def test_eq_ground_rationals_fail(self):
        """F(1,3) == F(1,2) fails."""
        trail = Trail()
        assert not q_eq(F(1, 3), F(1, 2), trail)

    def test_eq_var_to_rational(self):
        """X == F(1,3) binds X to 1/3."""
        trail = Trail()
        x = Var()
        assert q_eq(x, F(1, 3), trail)
        assert deref(x) == F(1, 3)

    def test_ne_ground(self):
        trail = Trail()
        assert q_ne(F(1, 3), F(1, 2), trail)
        assert not q_ne(F(1, 3), F(1, 3), trail)

    def test_lt_ground(self):
        trail = Trail()
        assert q_lt(F(1, 3), F(1, 2), trail)
        assert not q_lt(F(1, 2), F(1, 3), trail)

    def test_le_ground(self):
        trail = Trail()
        assert q_le(F(1, 3), F(1, 3), trail)
        assert q_le(F(1, 3), F(1, 2), trail)
        assert not q_le(F(1, 2), F(1, 3), trail)
```

### TestRationalBounds

```python
class TestRationalBounds:
    def test_in_q_bounds(self):
        """in_q(X, 0, 1) constrains X to [0, 1]."""
        trail = Trail()
        x = Var()
        assert in_q(x, F(0), F(1), trail)
        state = get_attr(x, Q_KEY)
        assert state is not None
        assert state.lo == F(0)
        assert state.hi == F(1)

    def test_lt_narrows_upper(self):
        """X < 1/2 constrains upper bound."""
        trail = Trail()
        x = Var()
        assert in_q(x, F(0), F(1), trail)
        assert q_lt(x, F(1, 2), trail)
        state = get_attr(x, Q_KEY)
        assert state.hi < F(1, 2)  # strict: upper bound < 1/2

    def test_gt_narrows_lower(self):
        """X > 1/3 constrains lower bound."""
        trail = Trail()
        x = Var()
        assert in_q(x, F(0), F(1), trail)
        assert q_gt(x, F(1, 3), trail)
        state = get_attr(x, Q_KEY)
        assert state.lo > F(1, 3)
```

### TestLinearConstraints — simplex-level tests

```python
class TestLinearConstraints:
    def test_two_var_equality(self):
        """X + Y == 1, X == F(1,3) → Y == F(2,3)."""
        trail = Trail()
        x, y = Var(), Var()
        # X + Y = 1  (as linear constraint)
        assert q_eq(Add(x, y), F(1), trail)
        assert q_eq(x, F(1, 3), trail)
        assert deref(y) == F(2, 3)

    def test_simple_system(self):
        """X + Y == 1, X - Y == F(1,3) → X = F(2,3), Y = F(1,3)."""
        trail = Trail()
        x, y = Var(), Var()
        assert q_eq(Add(x, y), F(1), trail)
        assert q_eq(Sub(x, y), F(1, 3), trail)
        assert deref(x) == F(2, 3)
        assert deref(y) == F(1, 3)

    def test_infeasible_system(self):
        """X >= 0, X <= -1 → failure."""
        trail = Trail()
        x = Var()
        assert q_ge(x, F(0), trail)
        assert not q_le(x, F(-1), trail)

    def test_three_variable_system(self):
        """X + Y + Z == 1, X == F(1,4), Y == F(1,4) → Z == F(1,2)."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        assert q_eq(Add(Add(x, y), z), F(1), trail)
        assert q_eq(x, F(1, 4), trail)
        assert q_eq(y, F(1, 4), trail)
        assert deref(z) == F(1, 2)
```

### TestBacktracking

```python
class TestBacktracking:
    def test_undo_restores_state(self):
        """Constraints are undone on backtrack."""
        trail = Trail()
        x = Var()
        mark = trail.mark()
        assert q_eq(x, F(1, 3), trail)
        assert deref(x) == F(1, 3)
        trail.undo(mark)
        assert is_var(deref(x))

    def test_undo_restores_bounds(self):
        """Bounds narrowing is undone on backtrack."""
        trail = Trail()
        x = Var()
        assert in_q(x, F(0), F(1), trail)
        mark = trail.mark()
        assert q_lt(x, F(1, 2), trail)
        trail.undo(mark)
        state = get_attr(x, Q_KEY)
        assert state.hi == F(1)  # restored to original upper bound
```

### TestDispatchFromFdEq — integration with existing constraint system

```python
class TestDispatchFromFdEq:
    def test_fraction_dispatches_to_clpq(self):
        """fd_eq(X, Fraction(1,3)) should dispatch to q_eq."""
        trail = Trail()
        x = Var()
        assert fd_eq(x, F(1, 3), trail)
        assert deref(x) == F(1, 3)

    def test_int_does_not_dispatch_to_clpq(self):
        """fd_eq(X, 5) should NOT dispatch to CLP(Q) — stays in CLP(Z)."""
        trail = Trail()
        x = Var()
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5
        # Should have FD_KEY attribute, not Q_KEY
        # (unless fd_eq narrowed x to ground before posting)
```

### TestOptimization — maximize/minimize

```python
class TestOptimization:
    def test_maximize_simple(self):
        """maximize X subject to X <= 4 → X = 4."""
        trail = Trail()
        x = Var()
        assert q_le(x, F(4), trail)
        assert q_ge(x, F(0), trail)
        result = maximize(x, trail)
        assert result == F(4)

    def test_minimize_simple(self):
        """minimize X subject to X >= 2 → X = 2."""
        trail = Trail()
        x = Var()
        assert q_ge(x, F(2), trail)
        assert q_le(x, F(10), trail)
        result = minimize(x, trail)
        assert result == F(2)

    def test_maximize_linear(self):
        """Classic LP: maximize 3X + 5Y subject to X <= 4, Y <= 6, X + Y <= 8.
        Solution: X=2, Y=6, objective=36."""
        trail = Trail()
        x, y = Var(), Var()
        assert q_ge(x, F(0), trail)
        assert q_ge(y, F(0), trail)
        assert q_le(x, F(4), trail)
        assert q_le(y, F(6), trail)
        assert q_le(Add(x, y), F(8), trail)
        obj = Add(Mult(F(3), x), Mult(F(5), y))
        result = maximize(obj, trail)
        assert result == F(36)
        assert deref(x) == F(2)
        assert deref(y) == F(6)
```

### Edge cases to test

- **Zero coefficients**: `0*X + Y == 1` should simplify to `Y == 1`
- **Redundant constraints**: `X <= 5, X <= 10` — second is redundant, no error
- **Contradictory constraints**: `X >= 5, X <= 3` → fails immediately
- **Single variable**: `2*X == 1` → X = 1/2
- **Unbounded optimization**: `maximize(X)` with no upper bound → error or inf
- **Degenerate pivot**: system where multiple basic variables are zero
- **Large coefficients**: `999999*X == 1` → X = F(1, 999999)

## How to verify

```bash
# New CLP(Q) tests
python -m pytest tests/test_clpq.py -x -v

# Integration — existing tests must still pass
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q

# Benchmark — must not regress (CLP(Q) is new, won't affect existing benchmarks)
python benchmarks/workloads.py
```

## References

- Holzbaur (1995) "OFAI CLP(Q,R) Manual" — the original implementation
- Triska (2012) "The Finite Domain Constraint Solver of SWI-Prolog" — CLP(Z) design
- Chvátal (1983) "Linear Programming" — simplex method reference
- SWI-Prolog `library(clpq)` source — API reference


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

