# Phase 4 — CLP(Z3) Real/Rational Constraints

Linear and nonlinear arithmetic over reals, backed by Z3's arithmetic solver.
Replaces CLP(Q)'s simplex/Gaussian elimination and CLP(R)'s interval arithmetic.

**Depends on:** Phase 1 (core infrastructure)  
**Independent of:** Phases 2, 3

---

## Files to Modify/Create

| File | Action |
|------|--------|
| `clausal/logic/clpz3.py` | Add `in_z3_real`, `z3_real_eq/ne/lt/le/gt/ge`, `label_z3_real`, `maximize_z3`, `minimize_z3`, `entailed_z3`, `sup_z3`, `inf_z3` |
| `clausal/logic/builtins/z3_constraints.py` | Register real/rational constraint builtins |
| `tests/test_clpz3_real.py` | Real constraint tests |
| `tests/fixtures/z3_lp.clausal` | LP optimization fixtures |

---

## 1. Variable Declaration: `in_z3_real(Vars, Lo, Hi)`

```python
def in_z3_real(var_or_list, lo, hi, trail: Trail) -> bool:
    """Declare real-sorted variable(s) with bounds [lo, hi].

    lo/hi can be int, float, or Fraction. They are converted to Z3 RealVal.
    Use lo=None or hi=None for unbounded.
    """
    state = get_z3_state(trail)
    lo_val = deref(lo) if lo is not None else None
    hi_val = deref(hi) if hi is not None else None

    var_or_list = deref(var_or_list)
    if not isinstance(var_or_list, list):
        from clausal.terms import cons_to_list
        try:
            var_or_list = cons_to_list(var_or_list)
        except (ValueError, TypeError):
            var_or_list = [var_or_list]

    for v in var_or_list:
        v = deref(v)
        if not is_var(v):
            # Ground: check membership
            if lo_val is not None and v < lo_val:
                return False
            if hi_val is not None and v > hi_val:
                return False
            continue
        z3_v = z3_var_for(v, _z3.RealSort(), trail)
        if lo_val is not None:
            state.solver.add(z3_v >= _to_z3_real(lo_val))
        if hi_val is not None:
            state.solver.add(z3_v <= _to_z3_real(hi_val))

    return True


def _to_z3_real(val):
    """Convert a Python numeric value to a Z3 RealVal."""
    if isinstance(val, Fraction):
        return _z3.RealVal(val.numerator) / _z3.RealVal(val.denominator)
    if isinstance(val, int):
        return _z3.RealVal(val)
    if isinstance(val, float):
        return _z3.RealVal(val)
    raise TypeError(f"Cannot convert {type(val).__name__} to Z3 Real: {val}")
```

### Edge Cases

- **Unbounded:** `in_z3_real(X)` with no bounds (alias `rational_z3(X)`)
- **Fraction bounds:** `in_z3_real(X, Fraction(1,3), Fraction(2,3))`
- **Mixed int/float bounds:** `in_z3_real(X, 0, 10.5)` — Z3 auto-coerces
- **Negative bounds:** `in_z3_real(X, -100, 100)`
- **Infinite bounds:** `in_z3_real(X, float('-inf'), float('inf'))` — omit bounds

---

## 2. Arithmetic Constraints

Same pattern as Phase 2 but with `RealSort`:

```python
def z3_real_eq(l, r, trail: Trail) -> bool:
    state = get_z3_state(trail)
    z3_l = clausal_to_z3(l, trail, default_sort=_z3.RealSort())
    z3_r = clausal_to_z3(r, trail, default_sort=_z3.RealSort())
    state.solver.add(z3_l == z3_r)
    return True

# z3_real_ne, z3_real_lt, z3_real_le, z3_real_gt, z3_real_ge — same pattern
```

### Automatic Dispatch from `fd_eq` etc.

The same dispatch hook from Phase 2 applies. If a variable has a `"z3"`
attribute with `RealSort`, `fd_eq` should dispatch to `z3_real_eq`:

```python
# In _any_z3 or separate check:
def _z3_sort_for(var):
    """Get the Z3 sort of a variable, or None if not Z3-registered."""
    info = get_attr(var, Z3_KEY)
    return info.sort if info is not None else None
```

Then in `fd_eq`:
```python
if _any_z3(l, r):
    sort = _infer_z3_sort(l, r)  # IntSort or RealSort
    if sort == _z3.RealSort():
        return z3_real_eq(l, r, trail)
    else:
        return z3_eq(l, r, trail)
```

---

## 3. Real Labeling: `label_z3_real(Vars)`

For real-valued variables, there are infinitely many solutions. Z3 finds *one*
satisfying assignment. The labeling generator returns exactly one solution
(the model), unlike integer labeling which enumerates all.

```python
def label_z3_real(vars_list, trail: Trail):
    """Find a satisfying assignment for real-valued variables.

    Yields at most one solution (reals have infinitely many, so
    enumeration is not meaningful). Use maximize_z3/minimize_z3
    for optimization.
    """
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        from clausal.terms import cons_to_list
        vars_list = cons_to_list(vars_list)

    z3_vars = []
    clausal_vars = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            z3_v = state.var_map.get(id(v))
            if z3_v is None:
                raise ValueError("label_z3_real: variable not registered with Z3")
            z3_vars.append(z3_v)
            clausal_vars.append(v)

    if not z3_vars:
        yield None
        return

    if state.solver.check() == _z3.sat:
        m = state.solver.model()
        mark = trail.mark()
        ok = True
        for cv, z3v in zip(clausal_vars, z3_vars):
            val = z3_to_python(m.eval(z3v, model_completion=True))
            if not unify(cv, val, trail):
                ok = False
                break
        if ok:
            yield None
        trail.undo(mark)
```

### Alternative: Enumerate Rational Points

For bounded real variables, we could enumerate rational solutions by adding
blocking constraints (disequalities). But this is generally not useful — the
user should use optimization or projection instead.

---

## 4. Optimization: `maximize_z3`, `minimize_z3`

### Implementation

```python
def maximize_z3(expr, result_var, trail: Trail) -> bool:
    """Maximize a linear expression subject to current Z3 constraints.

    Uses Z3's Optimize solver. Copies all assertions from the main Solver.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(expr, trail, default_sort=_z3.RealSort())

    opt = _z3.Optimize()
    for a in state.solver.assertions():
        opt.add(a)
    handle = opt.maximize(z3_expr)

    if opt.check() == _z3.sat:
        m = opt.model()
        obj_val = z3_to_python(m.eval(z3_expr))
        return unify(result_var, obj_val, trail)
    return False


def minimize_z3(expr, result_var, trail: Trail) -> bool:
    """Minimize a linear expression subject to current Z3 constraints."""
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(expr, trail, default_sort=_z3.RealSort())

    opt = _z3.Optimize()
    for a in state.solver.assertions():
        opt.add(a)
    handle = opt.minimize(z3_expr)

    if opt.check() == _z3.sat:
        m = opt.model()
        obj_val = z3_to_python(m.eval(z3_expr))
        return unify(result_var, obj_val, trail)
    return False
```

### Gotchas

1. **Optimize vs Solver:** Z3's `Optimize` is a separate class from `Solver`.
   It doesn't share the push/pop state. We copy assertions, which is a
   snapshot. Constraints added after `maximize_z3` won't affect the result.
   This is correct for CLP(Q) semantics (maximize at the point of call).

2. **Unbounded objective:** If the objective can be infinitely large, Z3
   returns `+oo` (infinity). Handle: `z3_to_python` should detect this:
   ```python
   if z3_val.is_int() and False:
       pass
   # Check for infinity
   if str(z3_val) in ('+oo', '-oo', 'oo'):
       return float('inf') if '+' in str(z3_val) or str(z3_val) == 'oo' else float('-inf')
   ```

3. **Infeasible:** If constraints are contradictory, `opt.check()` returns
   `unsat` and `maximize_z3` returns `False` (Prolog failure).

4. **Integer variables in Optimize:** If some variables are IntSort, Z3's
   Optimize handles mixed integer-real optimization natively (MILP).

5. **Nonlinear objectives:** Z3's Optimize supports nonlinear objectives
   in some cases, but may return `unknown`. Handle gracefully.

---

## 5. Entailment: `entailed_z3(Constraint)`

```python
def entailed_z3(op_str, left, right, trail: Trail) -> bool:
    """Test if a constraint is entailed (implied) by the current store.

    Returns True if the constraint is necessarily true given all posted
    constraints. False otherwise.
    """
    state = get_z3_state(trail)
    z3_l = clausal_to_z3(left, trail, default_sort=_z3.RealSort())
    z3_r = clausal_to_z3(right, trail, default_sort=_z3.RealSort())

    op_map = {
        '=': lambda l, r: l == r,
        '\\=': lambda l, r: l != r,
        '<': lambda l, r: l < r,
        '=<': lambda l, r: l <= r,
        '>': lambda l, r: l > r,
        '>=': lambda l, r: l >= r,
    }
    z3_constraint = op_map[op_str](z3_l, z3_r)

    # Entailed iff negation is unsatisfiable
    state.solver.push()
    state.solver.add(_z3.Not(z3_constraint))
    result = state.solver.check()
    state.solver.pop()

    return result == _z3.unsat
```

---

## 6. Supremum / Infimum: `sup_z3`, `inf_z3`

```python
def sup_z3(expr, result_var, trail: Trail) -> bool:
    """Compute supremum of expression without committing to variable bindings."""
    return maximize_z3(expr, result_var, trail)

def inf_z3(expr, result_var, trail: Trail) -> bool:
    """Compute infimum of expression without committing to variable bindings."""
    return minimize_z3(expr, result_var, trail)
```

These are thin aliases for maximize/minimize, matching CLP(Q) semantics.

---

## 7. Nonlinear Arithmetic (Z3-Only Capability)

CLP(Q) only handles **linear** constraints. Z3 can handle nonlinear real
arithmetic (NRA) via the NLSAT algorithm:

```prolog
# Nonlinear: circle constraint
Circle(X, Y) <- (
    in_z3_real([X, Y], -10, 10),
    z3_real_le(X * X + Y * Y, 25),   # x² + y² ≤ 25
    z3_real_ge(X + Y, 3),
    label_z3_real([X, Y])
)

# Polynomial constraint
Poly(X, Y) <- (
    in_z3_real([X, Y], 0, 10),
    z3_real_eq(X * X + Y * Y - X * Y, 7),
    label_z3_real([X, Y])
)
```

### Gotcha: NLSAT Performance

Z3's NLSAT solver can be very slow or return `unknown` for complex nonlinear
systems. The user should be aware:
- **Linear only:** Use `SolverFor("QF_LRA")` for quantifier-free linear real
  arithmetic — much faster.
- **Nonlinear:** Default solver handles it via NLSAT, but may timeout.
- **Mixed int/real nonlinear:** `QF_NIRA` — very hard, may fail.

---

## 8. Builtin Registration

```python
# Phase 4 additions to z3_constraints.py

@_builtin("in_z3_real", 3)
def _in_z3_real__3(var_or_list, lo, hi, trail, k):
    """in_z3_real(Var, Lo, Hi) — declare real variable with bounds via Z3."""
    from clausal.logic.clpz3 import in_z3_real
    if in_z3_real(var_or_list, lo, hi, trail):
        yield None

@_builtin("in_z3_real", 1)
def _in_z3_real__1(var_or_list, trail, k):
    """in_z3_real(Var) — declare unbounded real variable via Z3."""
    from clausal.logic.clpz3 import in_z3_real
    if in_z3_real(var_or_list, None, None, trail):
        yield None

@_builtin("label_z3_real", 1)
def _label_z3_real__1(vars_list, trail, k):
    """label_z3_real(Vars) — find one real-valued assignment via Z3."""
    from clausal.logic.clpz3 import label_z3_real
    yield from label_z3_real(vars_list, trail)

@_builtin("maximize_z3", 2)
def _maximize_z3__2(expr, result, trail, k):
    """maximize_z3(Expr, Result) — maximize expression via Z3 Optimize."""
    from clausal.logic.clpz3 import maximize_z3
    if maximize_z3(expr, result, trail):
        yield None

@_builtin("minimize_z3", 2)
def _minimize_z3__2(expr, result, trail, k):
    """minimize_z3(Expr, Result) — minimize expression via Z3 Optimize."""
    from clausal.logic.clpz3 import minimize_z3
    if minimize_z3(expr, result, trail):
        yield None

@_builtin("entailed_z3", 1)
def _entailed_z3__1(constraint_expr, trail, k):
    """entailed_z3(X <= 5) — test if constraint is implied by Z3 store."""
    from clausal.logic.clpz3 import entailed_z3
    from clausal.logic.variables import deref as _deref
    from clausal.pythonic_ast.nodes import LtE, Lt, GtE, Gt, ArithEq, ArithNeq
    expr = _deref(constraint_expr)
    op_map = {LtE: '=<', Lt: '<', GtE: '>=', Gt: '>', ArithEq: '=', ArithNeq: '\\='}
    for cls, op_str in op_map.items():
        if isinstance(expr, cls):
            if entailed_z3(op_str, expr.left, expr.right, trail):
                yield None
            return

@_builtin("sup_z3", 2)
def _sup_z3__2(expr, result, trail, k):
    from clausal.logic.clpz3 import sup_z3
    if sup_z3(expr, result, trail):
        yield None

@_builtin("inf_z3", 2)
def _inf_z3__2(expr, result, trail, k):
    from clausal.logic.clpz3 import inf_z3
    if inf_z3(expr, result, trail):
        yield None
```

---

## 9. Tests

### Unit Tests: `tests/test_clpz3_real.py`

```python
"""Tests for Z3 real/rational constraints (Phase 4)."""

import pytest
from fractions import Fraction
z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.clpz3 import (
    in_z3_real, label_z3_real, maximize_z3, minimize_z3,
    z3_real_eq, z3_real_le, entailed_z3, sup_z3, inf_z3,
    get_z3_state,
)


class TestInZ3Real:
    def test_bounded(self):
        trail = Trail()
        x = Var()
        assert in_z3_real(x, 0, 10, trail)

    def test_unbounded(self):
        trail = Trail()
        x = Var()
        assert in_z3_real(x, None, None, trail)

    def test_fraction_bounds(self):
        trail = Trail()
        x = Var()
        assert in_z3_real(x, Fraction(1, 3), Fraction(2, 3), trail)

    def test_ground_in_range(self):
        trail = Trail()
        assert in_z3_real(5.0, 0, 10, trail)

    def test_ground_out_of_range(self):
        trail = Trail()
        assert not in_z3_real(15.0, 0, 10, trail)


class TestLinearConstraints:
    def test_two_var_eq(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3_real([x, y], 0, 10, trail)
        from clausal.terms import Add
        z3_real_eq(Add(x, y), 10, trail)
        z3_real_eq(x, 3, trail)
        for _ in label_z3_real([x, y], trail):
            assert deref(x) == 3 or deref(x) == Fraction(3)
            assert deref(y) == 7 or deref(y) == Fraction(7)

    def test_inequality(self):
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        z3_real_le(x, 5, trail)
        for _ in label_z3_real([x], trail):
            val = deref(x)
            assert val <= 5


class TestOptimization:
    def test_maximize(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3_real([x, y], 0, 1000, trail)
        from clausal.terms import Add, Mult
        # 2x + y <= 16
        z3_real_le(Add(Mult(2, x), y), 16, trail)
        # x + 2y <= 11
        z3_real_le(Add(x, Mult(2, y)), 11, trail)
        # x + 3y <= 15
        z3_real_le(Add(x, Mult(3, y)), 15, trail)

        obj = Var()
        # maximize 30x + 50y
        assert maximize_z3(Add(Mult(30, x), Mult(50, y)), obj, trail)
        result = deref(obj)
        # Optimal: x=7, y=2, obj=310
        assert result == 310 or result == Fraction(310)

    def test_minimize(self):
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 100, trail)
        obj = Var()
        assert minimize_z3(x, obj, trail)
        assert deref(obj) == 0 or deref(obj) == Fraction(0)

    def test_infeasible(self):
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 5, trail)
        from clausal.logic.clpz3 import z3_real_eq
        z3_real_eq(x, 10, trail)  # contradicts bounds
        obj = Var()
        assert not maximize_z3(x, obj, trail)

    def test_unbounded_max(self):
        """Unbounded variable → maximize returns infinity (or fails)."""
        trail = Trail()
        x = Var()
        in_z3_real(x, None, None, trail)
        obj = Var()
        # Unbounded max — Z3 may return +oo or fail
        result = maximize_z3(x, obj, trail)
        # Behavior depends on Z3 version; document expected behavior


class TestEntailment:
    def test_entailed(self):
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 5, trail)
        # x <= 5 is entailed by bounds
        assert entailed_z3('=<', x, 10, trail)

    def test_not_entailed(self):
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        assert not entailed_z3('<', x, 5, trail)


class TestNonlinear:
    def test_quadratic(self):
        trail = Trail()
        x = Var()
        in_z3_real(x, 0, 10, trail)
        from clausal.terms import Mult
        z3_real_eq(Mult(x, x), 4, trail)  # x² = 4
        for _ in label_z3_real([x], trail):
            val = deref(x)
            assert abs(val - 2.0) < 0.001 or abs(val + 2.0) < 0.001

    def test_circle(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3_real([x, y], -10, 10, trail)
        from clausal.terms import Add, Mult
        z3_real_le(Add(Mult(x, x), Mult(y, y)), 25, trail)
        for _ in label_z3_real([x, y], trail):
            xv, yv = deref(x), deref(y)
            # Convert to float for comparison
            xf = float(xv) if isinstance(xv, Fraction) else xv
            yf = float(yv) if isinstance(yv, Fraction) else yv
            assert xf**2 + yf**2 <= 25.001


class TestCrossValidation:
    """Compare Z3 results with CLP(Q) for linear problems."""

    def test_lp_matches_clpq(self):
        """Same LP problem should give same optimal value via both solvers."""
        from clausal.logic.clpq import in_q, q_le, maximize

        # CLP(Q) version
        trail_q = Trail()
        xq, yq = Var(), Var()
        in_q([xq, yq], 0, 1000, trail_q)
        from clausal.terms import Add, Mult
        q_le(Add(Mult(2, xq), yq), 16, trail_q)
        q_le(Add(xq, Mult(2, yq)), 11, trail_q)
        obj_q = Var()
        maximize(Add(Mult(30, xq), Mult(50, yq)), obj_q, trail_q)
        clpq_result = deref(obj_q)

        # Z3 version
        trail_z = Trail()
        xz, yz = Var(), Var()
        in_z3_real([xz, yz], 0, 1000, trail_z)
        z3_real_le(Add(Mult(2, xz), yz), 16, trail_z)
        z3_real_le(Add(xz, Mult(2, yz)), 11, trail_z)
        obj_z = Var()
        maximize_z3(Add(Mult(30, xz), Mult(50, yz)), obj_z, trail_z)
        z3_result = deref(obj_z)

        assert float(clpq_result) == pytest.approx(float(z3_result))
```

### Integration Tests: `tests/fixtures/z3_lp.clausal`

```prolog
LP(X, Y, OBJ) <- (
    in_z3_real([X, Y], 0, 1000),
    2 * X + Y <= 16,
    X + 2 * Y <= 11,
    X + 3 * Y <= 15,
    maximize_z3(30 * X + 50 * Y, OBJ)
)

Test("LP optimal value is 310") <- LP(_, _, OBJ), OBJ == 310
```

---

## 10. Gotchas & Edge Cases

1. **Fraction vs float:** CLP(Q) returns `Fraction` (exact). Z3's `RealSort`
   returns rationals from `model.eval()`. The `z3_to_python` converter should
   return `Fraction` for exact values. But some Z3 models return algebraic
   numbers (irrational) for NRA — use float approximation.

2. **Z3 RealVal precision:** `z3.RealVal(0.1)` converts the float 0.1 to
   its exact binary fraction (3602879701896397/36028797018963968). Use
   `z3.RealVal("1/10")` for exact tenth. When translating from Clausal
   `Fraction(1, 10)`, use the numerator/denominator form.

3. **Mixed integer and real:** If the user has both `in_z3(X, ...)` (IntSort)
   and `in_z3_real(Y, ...)` (RealSort) and writes `X + Y == 10`, Z3
   auto-coerces Int to Real. This works but the result type is Real.

4. **Optimize copies assertions:** The `maximize_z3`/`minimize_z3` functions
   copy all current solver assertions into a fresh `Optimize`. Constraints
   added after optimization don't affect the result. This matches CLP(Q)'s
   `maximize/2` semantics.

5. **Multiple objectives:** Z3's `Optimize` supports multiple objectives
   (`maximize` + `minimize` in one check). Defer multi-objective optimization
   to Phase 7.

6. **Strict vs non-strict inequality:** Z3 supports both `<` (strict) and
   `<=` (non-strict). CLP(Q) also supports both. Mapping is direct.

7. **Division:** `X / Y` in Z3's RealSort is real division. In IntSort, it's
   integer division (floor). Clausal's `FloorDiv` node maps to integer division;
   regular `/` maps to real division when in RealSort.

---

## Implementation Order

1. `in_z3_real()` — variable declaration with bounds
2. `z3_real_eq/ne/lt/le/gt/ge` — arithmetic constraints
3. `label_z3_real()` — find one satisfying assignment
4. `maximize_z3()`, `minimize_z3()` — optimization
5. `entailed_z3()` — entailment check
6. `sup_z3()`, `inf_z3()` — supremum/infimum
7. Builtin registration
8. Unit tests + cross-validation with CLP(Q)
9. Integration tests (LP problems)
10. Nonlinear tests (circles, polynomials)

---

## Implementation Issues (Post-Implementation Addendum)

### Issue 1 — `entailed_z3` simplified to single-expression API

**Plan:** The plan showed `entailed_z3(op_str, left, right, trail)` with a string operator and
separate left/right operands, dispatched via a dict. The builtin was responsible for unwrapping
the AST node.

**Fix:** Implemented as `entailed_z3(constraint_expr, trail)` — takes a full Clausal comparison
AST node (e.g., `LtE(left=x, right=5)`) and translates it via `clausal_to_z3`. Cleaner,
consistent with how `taut_z3`/`sat_z3` take full expressions. The builtin is correspondingly
simple (`entailed_z3/1` passes the whole expression through).

---

### Issue 2 — `_to_z3_real` float conversion uses Fraction

**Plan:** Used `z3.RealVal(float_val)` directly, which converts via the float's binary
representation (potentially many-digit decimal).

**Fix:** Used `z3.RealVal(str(Fraction(val).limit_denominator(10**15)))` to get a cleaner
rational approximation. This avoids surprising representations like `3602879701896397/36028797018963968`
for `0.1`. For exact inputs (int, Fraction), the exact value is preserved.

---

### Issue 3 — `in_z3_real` uses single z3_push for both bounds

**Observation:** Both lo and hi bounds are posted in a single `z3_push` scope. This means both
are retracted together on backtracking, which is correct — they are logically one domain
declaration. Consistent with how `in_z3` handles integer domains.

---

### Issue 4 — `maximize_z3`/`minimize_z3` treat unbounded objective as failure

**Design decision:** If the optimization objective is unbounded (+oo/-oo), the functions return
`False` (Prolog failure) rather than unifying with `float('inf')`. Rationale: an unbounded
objective usually indicates a modeling error. If the user genuinely wants to detect unboundedness,
they can use `z3_check` + entailment checks.

The `_z3_optimize` helper correctly detects the +oo/-oo string output from Z3's `Optimize`
and propagates `float('inf')`/`float('-inf')`, which `maximize_z3`/`minimize_z3` then treat
as failure.

---

### Issue 5 — `label_z3_real` yields exactly one solution

**Design decision:** Real-valued constraint systems have infinitely many solutions; yielding
a single model value is the correct semantic. The one solution is undone after the generator
resumes (same trail.undo(mark) pattern as `label_z3`). For optimization, use
`maximize_z3`/`minimize_z3`. For discrete real solutions, the user should structure the
problem differently (e.g., enumerate via blocking constraints — not provided).

---

### Issue 6 — Cross-validation with CLP(Q) uses `q_le` directly (no q_add_le)

**Observation:** The plan showed `q_le(Add(Mult(2,xq), yq), 16, trail)` — this works because
`clpq.q_le` calls `_linearize` internally which handles arithmetic AST nodes. This is
consistent with how all CLP(Q) constraint-posting functions work. No extra helpers needed.

---

### Issue 7 — `entailed_z3` does not register unbound Vars

**Observation:** If the constraint expression contains a Var not yet registered with Z3 (no
`in_z3_real` call), `clausal_to_z3` raises `ValueError`. This is correct — entailment of
an unconstrained variable is undefined. Users must register variables before testing entailment.
No change needed.
