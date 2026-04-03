# Phase 2 — CLP(Z3) Integer Constraints

Integer constraint predicates backed by Z3's integer arithmetic solver.
This is the first user-visible feature — the SEND+MORE=MONEY and Sudoku
benchmarks should work end-to-end.

**Depends on:** Phase 1 (core infrastructure)

---

## Files to Modify/Create

| File | Action |
|------|--------|
| `clausal/logic/clpz3.py` | Add `in_z3`, `all_different_z3`, `label_z3`, `z3_eq`, `z3_ne`, `z3_lt`, etc. |
| `clausal/logic/builtins/z3_constraints.py` | Register integer constraint builtins |
| `tests/test_clpz3_int.py` | Integer constraint tests |
| `tests/fixtures/z3_sendmore.clausal` | SEND+MORE=MONEY via Z3 |
| `tests/fixtures/z3_sudoku.clausal` | Sudoku via Z3 |
| `tests/fixtures/z3_nqueens.clausal` | N-Queens via Z3 |

---

## 1. Domain Declaration: `in_z3(Vars, Lo, Hi)`

### Implementation

```python
def in_z3(var_or_list, lo, hi, trail: Trail) -> bool:
    """Post integer domain constraint [lo, hi] via Z3.

    Each variable gets registered as IntSort and constrained to [lo, hi].
    """
    lo = deref(lo)
    hi = deref(hi)
    if not isinstance(lo, int) or not isinstance(hi, int):
        raise TypeError(f"in_z3: bounds must be integers, got {type(lo).__name__}, {type(hi).__name__}")
    if lo > hi:
        return False  # empty domain

    state = get_z3_state(trail)
    var_or_list = deref(var_or_list)

    if isinstance(var_or_list, list):
        vars_ = var_or_list
    else:
        vars_ = [var_or_list]

    for v in vars_:
        v = deref(v)
        if not is_var(v):
            # Ground: check membership
            if not (isinstance(v, int) and lo <= v <= hi):
                return False
            continue
        z3_v = z3_var_for(v, _z3.IntSort(), trail)
        state.solver.add(z3_v >= lo)
        state.solver.add(z3_v <= hi)

    return True
```

### Edge Cases

- **Ground variable:** `in_z3(5, 1, 9)` → succeeds (5 ∈ [1,9])
- **Ground variable out of range:** `in_z3(15, 1, 9)` → fails
- **Empty domain:** `in_z3(X, 5, 1)` → fails (lo > hi)
- **Singleton domain:** `in_z3(X, 3, 3)` → binds X = 3? No — Z3 doesn't
  propagate singletons automatically. X remains a Z3 variable constrained to
  `x >= 3, x <= 3`. The binding happens at labeling time when `check()` returns
  a model with `x = 3`.
  
  **Alternative:** Detect singleton and `unify(v, lo, trail)` immediately. This
  matches CLP(FD) behavior where a singleton domain triggers binding. **Recommend
  doing this** for consistency:
  ```python
  if lo == hi:
      return unify(v, lo, trail)
  ```
- **Already-registered variable:** `in_z3(X, 1, 9)` then `in_z3(X, 3, 7)` →
  both range constraints are added. Z3 intersects them automatically. This is
  correct and matches CLP(FD) domain narrowing.
- **Mixed list:** `in_z3([X, 5, Y], 1, 9)` → X and Y get constraints, 5 is
  checked for membership.
- **SegList:** The `var_or_list` might be a `SegList` (Clausal's segmented list).
  Need to convert to a Python list first via `cons_to_list()` or similar:
  ```python
  from clausal.terms import cons_to_list
  if not isinstance(var_or_list, list):
      try:
          var_or_list = cons_to_list(var_or_list)
      except (ValueError, TypeError):
          var_or_list = [var_or_list]
  ```

---

## 2. All-Different: `all_different_z3(Vars)`

### Implementation

```python
def all_different_z3(vars_list, trail: Trail) -> bool:
    """Post Z3 Distinct constraint."""
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        from clausal.terms import cons_to_list
        vars_list = cons_to_list(vars_list)

    z3_vars = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            z3_vars.append(z3_var_for(v, _z3.IntSort(), trail))
        elif isinstance(v, int):
            z3_vars.append(_z3.IntVal(v))
        else:
            raise TypeError(f"all_different_z3: expected int or Var, got {type(v).__name__}")

    if len(z3_vars) >= 2:
        state.solver.add(_z3.Distinct(*z3_vars))
    return True
```

### Edge Cases

- **Single element:** `all_different_z3([X])` → trivially true, don't add Distinct
- **Empty list:** `all_different_z3([])` → trivially true
- **Ground elements:** `all_different_z3([1, 2, 3])` → adds `Distinct(1, 2, 3)`,
  which Z3 evaluates to `True`. Or just check in Python and skip Z3.
- **Duplicate grounds:** `all_different_z3([1, 1])` → Z3 says unsat on check.
  Could detect this eagerly and `return False`.
- **Mixed ground/var:** `all_different_z3([X, 1, Y])` → `Distinct(x, 1, y)`.
  Z3 handles this natively.

---

## 3. Arithmetic Constraint Posting

When the user writes `X + Y == Z` in a `.clausal` file, the compiler generates
a call to `fd_eq(Add(X, Y), Z, trail)`. Currently, `fd_eq` dispatches to the
native CLP(FD) solver. For Z3 mode, we need either:

**Option A: New `z3_eq`, `z3_ne`, `z3_lt`, etc. functions**

The user writes explicit Z3 predicates:
```prolog
z3_eq(X + Y, Z)
```

**Option B: A `-solver z3` directive that redirects `fd_eq` etc.**

The compiler replaces `_fd_eq` with `_z3_eq` when the directive is active.

**Option C: Automatic dispatch based on variable attributes**

If a Var has a `"z3"` attribute (from `in_z3()`), arithmetic constraints
dispatch to Z3 automatically. This mirrors how CLP(FD)/CLP(Q)/CLP(R) already
dispatch based on `"fd"`, `"q"`, `"r"` attributes.

**Recommendation: Start with Option A (explicit), plan for Option C later.**

Option C is the cleanest long-term design but requires modifying `fd_eq` and
related dispatch functions in `clpfd.py`. That's risky in Phase 2. Option A
gives us working Z3 constraints without touching existing code.

### Implementation (Option A)

```python
def z3_eq(l, r, trail: Trail) -> bool:
    """Post Z3 arithmetic equality: l == r."""
    state = get_z3_state(trail)
    z3_l = clausal_to_z3(l, trail, default_sort=_z3.IntSort())
    z3_r = clausal_to_z3(r, trail, default_sort=_z3.IntSort())
    state.solver.add(z3_l == z3_r)
    return True

def z3_ne(l, r, trail: Trail) -> bool:
    """Post Z3 arithmetic disequality: l != r."""
    state = get_z3_state(trail)
    z3_l = clausal_to_z3(l, trail, default_sort=_z3.IntSort())
    z3_r = clausal_to_z3(r, trail, default_sort=_z3.IntSort())
    state.solver.add(z3_l != z3_r)
    return True

def z3_lt(l, r, trail: Trail) -> bool:
    state = get_z3_state(trail)
    z3_l = clausal_to_z3(l, trail, default_sort=_z3.IntSort())
    z3_r = clausal_to_z3(r, trail, default_sort=_z3.IntSort())
    state.solver.add(z3_l < z3_r)
    return True

def z3_le(l, r, trail: Trail) -> bool:
    state = get_z3_state(trail)
    z3_l = clausal_to_z3(l, trail, default_sort=_z3.IntSort())
    z3_r = clausal_to_z3(r, trail, default_sort=_z3.IntSort())
    state.solver.add(z3_l <= z3_r)
    return True

def z3_gt(l, r, trail: Trail) -> bool:
    state = get_z3_state(trail)
    z3_l = clausal_to_z3(l, trail, default_sort=_z3.IntSort())
    z3_r = clausal_to_z3(r, trail, default_sort=_z3.IntSort())
    state.solver.add(z3_l > z3_r)
    return True

def z3_ge(l, r, trail: Trail) -> bool:
    state = get_z3_state(trail)
    z3_l = clausal_to_z3(l, trail, default_sort=_z3.IntSort())
    z3_r = clausal_to_z3(r, trail, default_sort=_z3.IntSort())
    state.solver.add(z3_l >= z3_r)
    return True
```

### Builtin Registration for Arithmetic Constraints

```python
# In z3_constraints.py
# These are 2-arg builtins for explicit z3 arithmetic constraints

@_builtin("z3_eq", 2)
def _z3_eq__2(l, r, trail, k):
    from clausal.logic.clpz3 import z3_eq
    if z3_eq(l, r, trail):
        yield None

@_builtin("z3_ne", 2)
def _z3_ne__2(l, r, trail, k):
    from clausal.logic.clpz3 import z3_ne
    if z3_ne(l, r, trail):
        yield None

# ... z3_lt, z3_le, z3_gt, z3_ge similarly
```

### The Standard Operator Problem

**Problem:** In `.clausal` syntax, `X != 0` compiles to `fd_ne(X, 0, trail)`,
not `z3_ne(X, 0, trail)`. The user would need to write:
```prolog
z3_ne(S, 0),
z3_eq(S * 1000 + E * 100 + N * 10 + D + ..., ...)
```

This is ugly. The user expects `S != 0` and `X + Y == Z` to work with Z3 vars.

**Solution for Phase 2: Hook into the dispatch layer.**

Add a check in `fd_eq`/`fd_ne`/etc.: if any argument has a `Z3_KEY` attribute,
dispatch to the Z3 version:

```python
# In clpfd.py, modify fd_eq:
def fd_eq(l, r, trail: Trail) -> bool:
    l, r = deref(l), deref(r)
    # ... existing fast paths ...

    # NEW: Z3 dispatch
    if _any_z3(l, r):
        from clausal.logic.clpz3 import z3_eq
        return z3_eq(l, r, trail)

    # ... existing CLP(FD) code ...
```

Where `_any_z3` checks if either side (or any variable within an expression
tree) has a `"z3"` attribute:

```python
def _any_z3(*args) -> bool:
    """True if any argument is a Z3-declared variable."""
    for arg in args:
        arg = deref(arg)
        if is_var(arg) and get_attr(arg, Z3_KEY) is not None:
            return True
        if isinstance(arg, (_Add, _Sub, _Mult, _Negate)):
            if _expr_has_z3(arg):
                return True
    return False

def _expr_has_z3(expr) -> bool:
    """Recursively check if expression tree contains Z3 vars."""
    expr = deref(expr)
    if is_var(expr):
        return get_attr(expr, Z3_KEY) is not None
    if isinstance(expr, (_Add, _Sub, _Mult)):
        return _expr_has_z3(expr.left) or _expr_has_z3(expr.right)
    if isinstance(expr, _Negate):
        return _expr_has_z3(expr.operand)
    return False
```

**This means the user can write:**
```prolog
Sendmoney(S, E, N, D, M, O, R, Y) <- (
    in_z3([S, E, N, D, M, O, R, Y], 0, 9),   # declares as Z3
    all_different_z3([S, E, N, D, M, O, R, Y]),
    S != 0,                                     # dispatches to z3_ne via fd_ne
    M != 0,
    (S * 1000 + E * 100 + N * 10 + D + ...) == ...,  # dispatches to z3_eq
    label_z3([S, E, N, D, M, O, R, Y])
)
```

**Risk:** Modifying `fd_eq`/`fd_ne`/etc. could introduce bugs in the existing
CLP(FD) path. Mitigate by:
1. Adding the Z3 check as the **first** dispatch case (before all others)
2. Only activating if `_HAS_Z3` is True
3. Running the full existing CLP(FD) test suite after the change

---

## 4. Labeling: `label_z3(Vars)`

### Implementation

```python
def label_z3(vars_list, trail: Trail):
    """Enumerate solutions for Z3-constrained integer variables.

    Generator: yields None for each satisfying assignment.
    Uses Z3's check() + model() with blocking clauses for enumeration.
    """
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        from clausal.terms import cons_to_list
        vars_list = cons_to_list(vars_list)

    # Collect Z3 vars and Clausal vars
    z3_vars = []
    clausal_vars = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            z3_v = state.var_map.get(id(v))
            if z3_v is None:
                raise ValueError(f"label_z3: variable not registered with Z3. Use in_z3() first.")
            z3_vars.append(z3_v)
            clausal_vars.append(v)
        elif isinstance(v, int):
            # Already ground — nothing to label
            pass
        else:
            raise TypeError(f"label_z3: expected int or Var, got {type(v).__name__}")

    if not z3_vars:
        # All ground — one solution
        yield None
        return

    # Push a scope for the enumeration loop
    # This scope is popped when the generator is abandoned (via trail.undo)
    # or when enumeration is complete.
    enum_mark = trail.mark()
    z3_push(trail)

    try:
        while state.solver.check() == _z3.sat:
            m = state.solver.model()
            # Extract values
            values = []
            for z3v in z3_vars:
                val = m.eval(z3v, model_completion=True)
                values.append(z3_to_python(val))

            # Bind Clausal vars
            mark = trail.mark()
            ok = True
            for cv, val in zip(clausal_vars, values):
                if not unify(cv, val, trail):
                    ok = False
                    break

            if ok:
                yield None  # solution — back to trampoline

            trail.undo(mark)  # unbind Clausal vars

            # Block this solution
            block = _z3.Or([z3v != m.eval(z3v, model_completion=True)
                            for z3v in z3_vars])
            state.solver.add(block)
    finally:
        # When generator is abandoned or exhausted, pop the enumeration scope
        # Actually, trail.undo(enum_mark) will handle this via the z3_push callback
        # But if we exited normally (exhausted), we need to pop explicitly
        pass
```

**Wait — there's a subtlety with the enumeration scope.**

The blocking clauses need to persist across iterations but be retracted when
Clausal backtracks past the labeling call. The `z3_push` at `enum_mark` handles
this: all blocking clauses are added within that scope, and `trail.undo(enum_mark)`
pops them all.

But `trail.undo(mark)` (the per-solution mark) only unbinds Clausal vars — it
doesn't touch Z3 state. The per-solution bindings are purely Clausal-side.

**Revised flow:**

```
enum_mark = trail.mark()
z3_push(trail)                  # Z3 scope for blocking clauses
│
├─ solver.check() → sat
│   model → values = [9, 5, 6, 7, ...]
│   mark = trail.mark()
│   unify(S, 9), unify(E, 5), ...
│   yield None  ←── solution returned to caller
│   trail.undo(mark)            # unbind S, E, ... (Z3 unchanged)
│   solver.add(block)           # block this solution (in Z3 scope)
│
├─ solver.check() → sat        # next solution
│   ...
│
└─ solver.check() → unsat      # exhausted
    generator returns
    (caller's trail.undo will eventually pop Z3 scope)
```

### Labeling Options / Heuristics

Z3 doesn't have Clausal's first-fail heuristic — it uses its own internal
CDCL heuristics. For most problems, Z3's default is good enough. But we
could influence the search:

- **`SolverFor("QF_LIA")`** — quantifier-free linear integer arithmetic.
  Much faster for linear problems.
- **`SolverFor("QF_NIA")`** — quantifier-free nonlinear integer arithmetic.
  For problems with `X * Y` etc.
- **Tactic combinations:** `z3.Then('simplify', 'solve-eqs', 'smt')` for
  custom solving strategies.

**Defer heuristic configuration to a later phase.** For now, use `Solver()`.

### Partial Labeling

What if the user calls `label_z3([X, Y])` but there are other Z3 variables
(Z, W) in the constraint store? Z3 assigns **all** variables in its model,
not just the ones in the label list. This is correct — the model satisfies
all constraints. But we only bind the requested variables.

The blocking clause should only block the requested variables:
```python
block = _z3.Or([z3v != m.eval(z3v, ...) for z3v in z3_vars])
```
This means other variables may take different values in the next model. The
user gets all combinations of the labeled variables.

### Performance Considerations

- **`model_completion=True`:** Essential. Without it, Z3 may omit variables
  that don't affect satisfiability. `model_completion=True` assigns them
  arbitrary values within constraints.
- **Blocking clause growth:** Each solution adds one clause. For N solutions,
  the solver accumulates N clauses. For large N (thousands of solutions),
  this can slow down. Alternative: use `SolverFor("QF_LIA")` which handles
  this better internally.
- **Early termination:** If the caller only wants one solution (`once()`),
  the generator yields once and is abandoned. The Z3 scope is popped via
  trail cleanup.

---

## 5. `z3_check()`

An explicit satisfiability check, useful for testing and debugging:

```python
def z3_check(trail: Trail) -> bool:
    """Check if current Z3 constraints are satisfiable."""
    state = get_z3_state(trail)
    return state.solver.check() == _z3.sat

@_builtin("z3_check", 0)
def _z3_check__0(trail, k):
    """z3_check — succeed if Z3 constraints are satisfiable."""
    from clausal.logic.clpz3 import z3_check
    if z3_check(trail):
        yield None
```

---

## 6. Builtin Registration

```python
# clausal/logic/builtins/z3_constraints.py — Phase 2 additions

@_builtin("in_z3", 3)
def _in_z3__3(var_or_list, lo, hi, trail, k):
    """in_z3(Var, Lo, Hi) — post integer domain [Lo, Hi] via Z3."""
    from clausal.logic.clpz3 import in_z3 as _fn
    if _fn(var_or_list, lo, hi, trail):
        yield None

@_builtin("all_different_z3", 1)
def _all_different_z3__1(vars_list, trail, k):
    """all_different_z3(Vars) — Z3 Distinct constraint."""
    from clausal.logic.clpz3 import all_different_z3 as _fn
    if _fn(vars_list, trail):
        yield None

@_builtin("label_z3", 1)
def _label_z3__1(vars_list, trail, k):
    """label_z3(Vars) — enumerate integer solutions via Z3."""
    from clausal.logic.clpz3 import label_z3 as _fn
    yield from _fn(vars_list, trail)

@_builtin("z3_check", 0)
def _z3_check__0(trail, k):
    """z3_check — succeed if Z3 constraints are satisfiable."""
    from clausal.logic.clpz3 import z3_check as _fn
    if _fn(trail):
        yield None

# Arithmetic constraints (explicit form)
@_builtin("z3_eq", 2)
def _z3_eq__2(l, r, trail, k):
    from clausal.logic.clpz3 import z3_eq
    if z3_eq(l, r, trail):
        yield None

@_builtin("z3_ne", 2)
def _z3_ne__2(l, r, trail, k):
    from clausal.logic.clpz3 import z3_ne
    if z3_ne(l, r, trail):
        yield None

@_builtin("z3_lt", 2)
def _z3_lt__2(l, r, trail, k):
    from clausal.logic.clpz3 import z3_lt
    if z3_lt(l, r, trail):
        yield None

@_builtin("z3_le", 2)
def _z3_le__2(l, r, trail, k):
    from clausal.logic.clpz3 import z3_le
    if z3_le(l, r, trail):
        yield None

@_builtin("z3_gt", 2)
def _z3_gt__2(l, r, trail, k):
    from clausal.logic.clpz3 import z3_gt
    if z3_gt(l, r, trail):
        yield None

@_builtin("z3_ge", 2)
def _z3_ge__2(l, r, trail, k):
    from clausal.logic.clpz3 import z3_ge
    if z3_ge(l, r, trail):
        yield None
```

---

## 7. Tests

### Python Unit Tests: `tests/test_clpz3_int.py`

```python
"""Tests for Z3 integer constraints (Phase 2)."""

import pytest
z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.clpz3 import (
    in_z3, all_different_z3, label_z3, z3_eq, z3_ne, z3_lt, z3_le,
    get_z3_state, z3_var_for,
)


class TestInZ3:
    def test_single_var(self):
        trail = Trail()
        x = Var()
        assert in_z3(x, 1, 9, trail)

    def test_list_of_vars(self):
        trail = Trail()
        xs = [Var() for _ in range(5)]
        assert in_z3(xs, 0, 100, trail)

    def test_ground_in_range(self):
        trail = Trail()
        assert in_z3(5, 1, 9, trail)

    def test_ground_out_of_range(self):
        trail = Trail()
        assert not in_z3(15, 1, 9, trail)

    def test_empty_domain(self):
        trail = Trail()
        x = Var()
        assert not in_z3(x, 5, 1, trail)

    def test_singleton_domain(self):
        trail = Trail()
        x = Var()
        assert in_z3(x, 3, 3, trail)
        # Should be bound to 3
        assert deref(x) == 3

    def test_narrowing_via_double_declaration(self):
        trail = Trail()
        x = Var()
        assert in_z3(x, 1, 9, trail)
        assert in_z3(x, 3, 7, trail)
        # Both constraints added; effective domain is [3, 7]
        state = get_z3_state(trail)
        z3_x = state.var_map[id(x)]
        state.solver.push()
        state.solver.add(z3_x == 2)
        assert state.solver.check() == z3.unsat
        state.solver.pop()


class TestAllDifferent:
    def test_basic(self):
        trail = Trail()
        xs = [Var() for _ in range(3)]
        in_z3(xs, 1, 3, trail)
        assert all_different_z3(xs, trail)

    def test_with_ground(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 3, trail)
        assert all_different_z3([x, 1, y], trail)

    def test_duplicate_ground(self):
        trail = Trail()
        # Distinct(1, 1) → unsat, but we don't check eagerly
        assert all_different_z3([1, 1], trail)
        # Check reveals inconsistency
        state = get_z3_state(trail)
        assert state.solver.check() == z3.unsat

    def test_empty(self):
        trail = Trail()
        assert all_different_z3([], trail)

    def test_single(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 9, trail)
        assert all_different_z3([x], trail)


class TestLabel:
    def test_single_var(self):
        trail = Trail()
        x = Var()
        in_z3(x, 1, 3, trail)
        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert sorted(solutions) == [1, 2, 3]

    def test_two_vars_all_different(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 2, trail)
        all_different_z3([x, y], trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert sorted(solutions) == [(1, 2), (2, 1)]

    def test_no_solution(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 1, trail)
        all_different_z3([x, y], trail)
        solutions = list(label_z3([x, y], trail))
        assert solutions == []

    def test_single_solution(self):
        trail = Trail()
        x = Var()
        in_z3(x, 5, 5, trail)
        solutions = []
        for _ in label_z3([x], trail):
            solutions.append(deref(x))
        assert solutions == [5]

    def test_first_solution_only(self):
        """Test that early termination works (via once/break)."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 100, trail)
        for _ in label_z3([x], trail):
            val = deref(x)
            assert isinstance(val, int)
            assert 1 <= val <= 100
            break  # only first solution

    def test_vars_unbound_between_solutions(self):
        """After yield, vars are unbound for next iteration."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 3, trail)
        for _ in label_z3([x], trail):
            val = deref(x)
            assert isinstance(val, int)
        # After exhaustion, x should be unbound
        assert is_var(deref(x))

    def test_all_ground_passthrough(self):
        """If all vars are already ground, yield one solution."""
        trail = Trail()
        solutions = list(label_z3([1, 2, 3], trail))
        assert len(solutions) == 1


class TestArithmeticConstraints:
    def test_eq(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_eq(x, y, trail)
        for _ in label_z3([x, y], trail):
            assert deref(x) == deref(y)
            break

    def test_ne(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 2, trail)
        z3_ne(x, y, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert sorted(solutions) == [(1, 2), (2, 1)]

    def test_lt(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 3, trail)
        z3_lt(x, y, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert all(a < b for a, b in solutions)

    def test_linear_expression(self):
        """X + Y == 10 with domain [0, 10]."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        from clausal.terms import Add
        z3_eq(Add(x, y), 10, trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            assert deref(x) + deref(y) == 10
            solutions.append((deref(x), deref(y)))
        assert len(solutions) == 11  # (0,10), (1,9), ..., (10,0)


class TestSendMoreMoney:
    def test_sendmore(self):
        trail = Trail()
        S, E, N, D, M, O, R, Y = (Var() for _ in range(8))
        in_z3([S, E, N, D, M, O, R, Y], 0, 9, trail)
        all_different_z3([S, E, N, D, M, O, R, Y], trail)
        z3_ne(S, 0, trail)
        z3_ne(M, 0, trail)

        from clausal.terms import Add, Mult
        send = Add(Add(Add(Mult(S, 1000), Mult(E, 100)), Mult(N, 10)), D)
        more = Add(Add(Add(Mult(M, 1000), Mult(O, 100)), Mult(R, 10)), E)
        money = Add(Add(Add(Add(Mult(M, 10000), Mult(O, 1000)), Mult(N, 100)), Mult(E, 10)), Y)
        z3_eq(Add(send, more), money, trail)

        solutions = []
        for _ in label_z3([S, E, N, D, M, O, R, Y], trail):
            solutions.append(tuple(deref(v) for v in [S, E, N, D, M, O, R, Y]))

        assert len(solutions) == 1
        assert solutions[0] == (9, 5, 6, 7, 1, 0, 8, 2)


class TestBacktracking:
    def test_trail_undo_retracts_z3(self):
        """When Clausal backtracks past constraint posting, Z3 scope pops."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        state = get_z3_state(trail)

        mark = trail.mark()
        from clausal.logic.clpz3 import z3_push
        z3_push(trail)
        z3_lt(x, 5, trail)
        # Constraints: x in [1,10], x < 5

        trail.undo(mark)
        # z3_lt constraint should be retracted
        # Now x in [1,10] with no upper bound constraint
        state.solver.push()
        z3_x = state.var_map[id(x)]
        state.solver.add(z3_x == 8)
        assert state.solver.check() == z3.sat
        state.solver.pop()

    def test_label_backtrack_integration(self):
        """Label in a choice point that gets undone."""
        trail = Trail()
        x, y = Var(), Var()
        in_z3(x, 1, 3, trail)

        mark = trail.mark()
        # First: try labeling x
        found = False
        for _ in label_z3([x], trail):
            if deref(x) == 2:
                found = True
                break
        assert found

        trail.undo(mark)
        assert is_var(deref(x))
```

### Integration Tests: `tests/fixtures/z3_sendmore.clausal`

```prolog
Sendmoney(S, E, N, D, M, O, R, Y) <- (
    in_z3([S, E, N, D, M, O, R, Y], 0, 9),
    all_different_z3([S, E, N, D, M, O, R, Y]),
    S != 0,
    M != 0,
    (S * 1000 + E * 100 + N * 10 + D +
     M * 1000 + O * 100 + R * 10 + E
     == M * 10000 + O * 1000 + N * 100 + E * 10 + Y),
    label_z3([S, E, N, D, M, O, R, Y])
)

Test("SEND+MORE=MONEY via Z3") <- Sendmoney(9, 5, 6, 7, 1, 0, 8, 2)
```

**Note:** The `S != 0` and `== ...` operators will only work if the `fd_ne`
and `fd_eq` dispatch hooks are in place (Option C from section 3). If not,
the explicit form is needed:
```prolog
    z3_ne(S, 0),
    z3_ne(M, 0),
    z3_eq(S * 1000 + ..., M * 10000 + ...),
```

### Integration Tests: `tests/fixtures/z3_nqueens.clausal`

```prolog
NQueens(N, QS) <- (
    length(QS, N),
    in_z3(QS, 1, N),
    all_different_z3(QS),
    SafeQueens(QS),
    label_z3(QS)
)

SafeQueens([])         <- true
SafeQueens([Q | QS])   <- NoAttack(Q, QS, 1), SafeQueens(QS)

NoAttack(_, [], _)            <- true
NoAttack(Q, [Q2 | QS], D)    <- (
    z3_ne(Q, Q2 + D),
    z3_ne(Q, Q2 - D),
    D2 := D + 1,
    NoAttack(Q, QS, D2)
)

Test("4-queens has 2 solutions") <- (
    findall(QS, NQueens(4, QS), ALL),
    length(ALL, 2)
)
```

---

## 8. Gotchas & Edge Cases

1. **Z3 not installed:** All Z3 builtins should raise `ImportError` with a
   helpful message if `z3-solver` is not installed. Tests should be skipped
   with `pytest.importorskip("z3")`.

2. **Large domains:** `in_z3(X, 0, 1000000)` is fine for Z3 (it doesn't
   enumerate). But `label_z3` with large domains will produce millions of
   solutions. Consider adding a `limit` parameter or warning.

3. **Unbounded variables:** What if the user does `z3_eq(X, Y + 1)` without
   `in_z3`? Z3 will create an unconstrained Int. `label_z3` would find
   infinitely many solutions (but `check()` returns sat each time with
   arbitrary values). **Solution:** `label_z3` should check that all variables
   have finite domains (bounded). Emit an error otherwise.

4. **Negative integers:** `in_z3(X, -10, 10)` — works fine with Z3.

5. **Very large integers:** Z3 handles arbitrary-precision integers natively.
   `in_z3(X, 0, 10**100)` works but enumeration is obviously impractical.

6. **Non-linear constraints:** `z3_eq(X * Y, Z)` — Z3 handles this via NIA
   (nonlinear integer arithmetic). Slower than linear, but works. CLP(FD)'s
   `_linearise` would return `None` for `X * Y`.

7. **Z3 timeout:** `solver.check()` can take a long time for hard problems.
   Consider setting a timeout: `solver.set("timeout", 30000)` (30 seconds).
   Expose as a parameter or directive.

8. **model_completion=True:** Always use this in `label_z3`. Without it, Z3
   may omit variables whose values don't matter, causing `m.eval(z3v)` to
   return the variable itself (not a concrete value).

9. **Blocking clause for partial labeling:** If labeling only a subset of
   Z3 variables, blocking clauses should only mention the labeled variables.
   Otherwise, the same labeled-variable assignment with different unlabeled-
   variable assignments counts as one solution (correct for the user's intent).

---

## Implementation Order

1. `in_z3()` — domain declaration
2. `all_different_z3()` — Distinct constraint
3. `z3_eq`, `z3_ne`, `z3_lt`, `z3_le`, `z3_gt`, `z3_ge` — arithmetic constraints
4. `label_z3()` — solution enumeration
5. `z3_check()` — explicit satisfiability check
6. Builtin registration in `z3_constraints.py`
7. (Optional) `fd_eq`/`fd_ne` dispatch hooks for transparent operator use
8. Unit tests
9. Integration tests (SEND+MORE=MONEY, N-Queens, Sudoku)
10. Cross-validation: run same problems with CLP(FD) and Z3, compare solutions

---

## Implementation Issues (Post-Implementation Addendum)

### Issue 1 — `_to_python_list` / `_as_list` redundancy

**Problem:** After Phase 1 changed `_to_python_list` to raise on non-list scalars (fixing the silent
fallback bug), Phase 2's `in_z3`, `all_different_z3`, and `label_z3` broke on single-Var inputs
because they routed everything through `_to_python_list`. Fixed by adding `_as_list()` which wraps
scalars first and only calls `_to_python_list` for cons-list fallback. This left two helpers with
overlapping roles — `_to_python_list` is now only called from `_as_list`.

**Fix:** Inline `_to_python_list` into `_as_list` and remove `_to_python_list`.

---

### Issue 2 — `label_z3` yielded a spurious solution for the all-ground-but-inconsistent case

**Problem:** `in_z3([x,y], 1, 1)` + `all_different_z3([x,y])` binds both to 1 via singleton
fast-path. `label_z3([x,y])` saw no unregistered vars and yielded `None` without consulting the
constraint store. `Distinct(1, 1)` was in the store but never checked.

**Fix:** Added `z3_check(trail)` guard before the all-ground yield:
```python
if not z3_vars:
    if z3_check(trail):
        yield None
    return
```

---

### Issue 3 — `label_z3` Z3 scope stays open after generator exhaustion

**Problem:** `z3_push` records a `solver.pop()` callback at trail position P. After `label_z3`
exhausts normally, that callback is still pending. The Z3 scope (containing all blocking clauses)
is only popped when `trail.undo` reaches position P. For a trail that is abandoned or GC'd after
a query, this is harmless. But if the same trail is reused for a second query without undoing to
a pre-labeling mark, blocking clauses from the first query persist on the solver.

**Resolution:** Benign in practice — Clausal trails are per-query and not typically reused across
unrelated queries. The trail callback mechanism guarantees cleanup on any backtrack past the
labeling call. No code change; documented here.

---

### Issue 4 — Singleton binding leaves orphaned Z3 variable

**Problem:** `in_z3(x, 3, 3)` calls `unify(x, 3, trail)` immediately (singleton fast-path). If x
was previously registered in `var_map` via an earlier `in_z3(x, 1, 9)`, the Z3 constant `v_n` now
has `1 <= v_n <= 9` but is never told x = 3. `label_z3` skips x (already ground), so `v_n` is
assigned an arbitrary value in [1,9] by Z3 internally. Harmless correctness-wise but the Z3
constant for x now goes unlabelled forever.

**Possible fix:** After singleton-domain binding, add `z3_const == lo` to the Z3 solver (if the
var was already registered). This tightens Z3's internal state and makes `z3_check` more precise
for other constraints that may reference the same Z3 constant transitively.

**Resolution:** Fix — add the constraint. See code.

---

### Issue 5 — No tests for negative domains

**Problem:** `in_z3(x, -5, 5)` and crossing-zero constraints are untested.

**Fix:** Add tests.

---

### Issue 6 — `bool` redundant in `_as_list`

**Problem:** `isinstance(val, (int, float, bool, Fraction))` — `bool` is a subclass of `int`,
so it is already caught. The explicit `bool` entry is dead code.

**Fix:** Remove `bool` from the tuple.

---

### Issue 7 — `fd_eq` → `z3_eq` dispatch hook missing (design decision, resolved)

**Problem:** Standard Clausal operators (`X != 0`, `A + B == C`) route to CLP(FD) even when the
variables are Z3-tagged. Users must write explicit `z3_ne`, `z3_eq` etc.

**Resolution:** Explicit unambiguous functor names are the correct approach. The planned
long-term disambiguation mechanism is a Prolog CLPQR-style `{}` wrapper:

```prolog
z3({ S != 0, S*1000 + E*100 + ... == M*10000 + ... })
```

or a qualified form like `clpz({...})` / `z3.solver_name({...})`. This routes all constraints
inside `{}` to the named solver without modifying any existing solver's dispatch layer. Until
that wrapper syntax is implemented, all Z3 predicates use their explicit `_z3` suffix
(`z3_eq`, `z3_ne`, `in_z3`, `label_z3`, etc.) so there is never any ambiguity at the call
site. The `fd_eq` dispatch hook is **not** needed and will not be added.

---

### Issue 8 — Constraint-posting functions did not trail-scope their solver.add() calls (fixed in Phase 3)

**Problem discovered in Phase 3:** `in_z3`, `all_different_z3`, and `z3_eq`/`ne`/`lt`/`le`/`gt`/`ge`
all called `state.solver.add()` directly with no `z3_push` wrapper. A Clausal clause that posted a
Z3 constraint and then backtracked would leave the constraint in the solver — violating Prolog
cut/backtrack semantics.

**Fix applied in Phase 3:** All posting functions now call `z3_push(trail)` before `solver.add()`.
The push records a `solver.pop()` callback on the trail, so backtracking automatically retracts
the constraint. Behaviorally all Phase 2 tests pass unchanged.

**Scope granularity:** One `z3_push` per posting call (not per constraint within a call):
- `in_z3(x, 1, 9)` → one push covering `x >= 1` and `x <= 9` together
- `in_z3([x, y], 1, 9)` → one push per variable (x's and y's constraints in separate scopes)
- `z3_eq(A, B)` → one push for the single equality constraint

The per-variable granularity for `in_z3` means `in_z3(x, 3, 7)` after `in_z3(x, 1, 9)` can be
independently retracted — correct behaviour for narrowing.
