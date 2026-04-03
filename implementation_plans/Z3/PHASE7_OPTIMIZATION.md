# Phase 7 — Optimization & Soft Constraints

Expose Z3's `Optimize` solver for optimization problems: minimize/maximize
objectives, soft constraints, weighted MaxSAT, and multi-objective optimization.

**Depends on:** Phase 2 (integers), Phase 3 (booleans), Phase 4 (reals)

---

## Files to Modify/Create

| File | Action |
|------|--------|
| `clausal/logic/clpz3.py` | Add `z3_soft`, `z3_max_sat`, `z3_optimize_label`, multi-objective support, `Z3OptState` |
| `clausal/logic/builtins/z3_constraints.py` | Register optimization builtins |
| `tests/test_clpz3_opt.py` | Optimization tests |
| `tests/fixtures/z3_optimize.clausal` | Integration test fixtures |

---

## 1. Architecture: Solver vs Optimize

Z3 has two distinct solver classes:

- **`Solver`**: Satisfiability checking. Used in Phases 1-6.
- **`Optimize`**: Optimization (min/max objectives + soft constraints). Separate
  class with different internals.

**Problem:** `Solver` and `Optimize` don't share state. Constraints added to
one aren't visible to the other.

### Options

**Option A: Copy assertions on demand (Phase 4 approach)**

When the user calls `maximize_z3()`, copy all `Solver` assertions into a
fresh `Optimize`, solve, return. Simple but doesn't support incremental
optimization or soft constraints posted before the objective.

**Option B: Dual-mode Z3State**

Z3State manages both a `Solver` and an `Optimize`. Constraints are added to
both. Push/pop applies to both.

```python
class Z3State:
    def __init__(self):
        self.solver = _z3.Solver()
        self._optimizer = None  # lazy init
        self._soft_constraints = []

    @property
    def optimizer(self):
        if self._optimizer is None:
            self._optimizer = _z3.Optimize()
            # Copy all existing assertions
            for a in self.solver.assertions():
                self._optimizer.add(a)
        return self._optimizer

    def add(self, constraint):
        self.solver.add(constraint)
        if self._optimizer is not None:
            self._optimizer.add(constraint)
```

**Problem:** `Optimize` doesn't support `push()`/`pop()` the same way as
`Solver`. Z3's `Optimize.push()`/`Optimize.pop()` exist but have limitations
(assertions are global, only soft constraints and objectives are scoped).

**Option C: Reconstruct Optimize from Solver at optimization time**

Keep using `Solver` for everything. When optimization is needed, create a
fresh `Optimize`, copy assertions, add soft constraints and objective. This
is stateless and avoids the push/pop synchronization problem.

**Recommendation: Option C.** Simplest, most robust. The cost of copying
assertions is negligible compared to the optimization solve time.

---

## 2. Soft Constraints: `z3_soft(Constraint, Weight)`

Soft constraints are satisfied if possible but can be violated at a cost.

### Design

Soft constraints are accumulated in the `Z3State` and applied when
optimization is triggered:

```python
class Z3State:
    def __init__(self):
        # ... existing fields ...
        self._soft_constraints = []  # list of (z3_expr, weight, group)

    def add_soft(self, z3_expr, weight, group=None):
        self._soft_constraints.append((z3_expr, weight, group))
```

### Implementation

```python
def z3_soft(constraint_expr, weight, trail: Trail, group=None) -> bool:
    """Add a soft constraint with weight.

    Soft constraints are satisfied if possible. When they conflict with
    hard constraints or each other, Z3 maximizes total satisfied weight.

    Args:
        constraint_expr: Clausal expression (translated to Z3 BoolRef)
        weight: integer or real weight
        group: optional string group name (for multi-objective)
    """
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(constraint_expr, trail, default_sort=_z3.IntSort())
    weight = deref(weight)
    if group is not None:
        group = deref(group)
    state.add_soft(z3_expr, weight, group)
    # Record undo callback to remove the soft constraint on backtrack
    idx = len(state._soft_constraints) - 1
    trail.record(lambda: _remove_soft(state, idx))
    return True


def _remove_soft(state, idx):
    """Remove soft constraint at index (called on trail undo)."""
    # Mark as removed rather than actually removing (preserves indices)
    if idx < len(state._soft_constraints):
        state._soft_constraints[idx] = None
```

### Gotcha: Soft Constraint Backtracking

Soft constraints need to be retractable on backtrack. Use `trail.record()`
to register a cleanup callback. Since `Optimize` is reconstructed each time,
the removed soft constraints simply won't be included.

---

## 3. Optimization Labels: `z3_optimize_label(Vars, Objective, Mode)`

A combined label + optimize that finds the optimal solution and binds variables:

```python
def z3_optimize_label(vars_list, objective_expr, result_var, mode, trail: Trail):
    """Find the optimal solution and bind variables.

    mode: "maximize" or "minimize"

    Yields one solution: the optimal assignment.
    """
    state = get_z3_state(trail)
    vars_list = _to_var_list(deref(vars_list))
    z3_vars, clausal_vars = _partition_vars(vars_list, state, trail)
    z3_obj = clausal_to_z3(objective_expr, trail, default_sort=_z3.IntSort())
    mode = deref(mode)

    # Build Optimize instance
    opt = _z3.Optimize()

    # Copy hard constraints
    for a in state.solver.assertions():
        opt.add(a)

    # Add soft constraints
    for entry in state._soft_constraints:
        if entry is not None:
            z3_expr, weight, group = entry
            if group is not None:
                opt.add_soft(z3_expr, weight, id=group)
            else:
                opt.add_soft(z3_expr, weight)

    # Set objective
    if mode == "maximize":
        handle = opt.maximize(z3_obj)
    elif mode == "minimize":
        handle = opt.minimize(z3_obj)
    else:
        raise ValueError(f"z3_optimize_label: mode must be 'maximize' or 'minimize', got {mode}")

    if opt.check() == _z3.sat:
        m = opt.model()

        # Bind objective value
        obj_val = z3_to_python(m.eval(z3_obj))

        mark = trail.mark()
        ok = unify(result_var, obj_val, trail)
        if ok:
            # Bind variable values
            for cv, z3v in zip(clausal_vars, z3_vars):
                val = z3_to_python(m.eval(z3v, model_completion=True))
                if not unify(cv, val, trail):
                    ok = False
                    break
        if ok:
            yield None
        trail.undo(mark)
```

---

## 4. MaxSAT: `z3_max_sat(Satisfied)`

Maximize the total weight of satisfied soft constraints:

```python
def z3_max_sat(satisfied_var, trail: Trail) -> bool:
    """Solve as MaxSAT: maximize total weight of satisfied soft constraints.

    Binds satisfied_var to the total weight of satisfied soft constraints.
    """
    state = get_z3_state(trail)
    opt = _z3.Optimize()

    # Copy hard constraints
    for a in state.solver.assertions():
        opt.add(a)

    # Add soft constraints, collecting handles
    handles = []
    total_weight = 0
    for entry in state._soft_constraints:
        if entry is not None:
            z3_expr, weight, group = entry
            h = opt.add_soft(z3_expr, weight)
            handles.append((h, weight))
            total_weight += weight

    if opt.check() != _z3.sat:
        return False

    # Calculate satisfied weight
    m = opt.model()
    satisfied_weight = 0
    for entry in state._soft_constraints:
        if entry is not None:
            z3_expr, weight, _ = entry
            if _z3.is_true(m.eval(z3_expr)):
                satisfied_weight += weight

    return unify(satisfied_var, satisfied_weight, trail)
```

---

## 5. Multi-Objective Optimization

Z3's `Optimize` supports multiple objectives with three priority modes:

- **`lex`** (lexicographic): Optimize objectives in order of declaration
- **`pareto`**: Find Pareto-optimal points
- **`box`**: Optimize each objective independently

```python
def z3_multi_optimize(objectives, results, priority, trail: Trail):
    """Multi-objective optimization.

    objectives: list of (expr, mode) where mode is "maximize" or "minimize"
    results: list of Vars to bind to optimal values
    priority: "lex", "pareto", or "box"

    For "pareto" mode, yields multiple Pareto-optimal solutions.
    For "lex" and "box", yields one solution.
    """
    state = get_z3_state(trail)
    objectives = deref(objectives)
    results = deref(results)
    priority = deref(priority)

    opt = _z3.Optimize()
    for a in state.solver.assertions():
        opt.add(a)

    # Add soft constraints
    for entry in state._soft_constraints:
        if entry is not None:
            z3_expr, weight, group = entry
            opt.add_soft(z3_expr, weight)

    opt.set(priority=priority)

    # Declare objectives
    handles = []
    for expr, mode in objectives:
        z3_expr = clausal_to_z3(expr, trail, default_sort=_z3.RealSort())
        if mode == "maximize":
            handles.append(opt.maximize(z3_expr))
        else:
            handles.append(opt.minimize(z3_expr))

    if priority == "pareto":
        # Enumerate Pareto-optimal solutions
        while opt.check() == _z3.sat:
            m = opt.model()
            mark = trail.mark()
            ok = True
            for rv, (expr, _) in zip(results, objectives):
                z3_expr = clausal_to_z3(expr, trail, default_sort=_z3.RealSort())
                val = z3_to_python(m.eval(z3_expr))
                if not unify(rv, val, trail):
                    ok = False
                    break
            if ok:
                yield None
            trail.undo(mark)
    else:
        # Single optimal solution
        if opt.check() == _z3.sat:
            m = opt.model()
            mark = trail.mark()
            ok = True
            for rv, (expr, _) in zip(results, objectives):
                z3_expr = clausal_to_z3(expr, trail, default_sort=_z3.RealSort())
                val = z3_to_python(m.eval(z3_expr))
                if not unify(rv, val, trail):
                    ok = False
                    break
            if ok:
                yield None
            trail.undo(mark)
```

---

## 6. Builtin Registration

```python
@_builtin("z3_soft", 2)
def _z3_soft__2(constraint_expr, weight, trail, k):
    """z3_soft(Constraint, Weight) — add soft constraint."""
    from clausal.logic.clpz3 import z3_soft
    if z3_soft(constraint_expr, weight, trail):
        yield None

@_builtin("z3_soft", 3)
def _z3_soft__3(constraint_expr, weight, group, trail, k):
    """z3_soft(Constraint, Weight, Group) — add grouped soft constraint."""
    from clausal.logic.clpz3 import z3_soft
    if z3_soft(constraint_expr, weight, trail, group=group):
        yield None

@_builtin("z3_max_sat", 1)
def _z3_max_sat__1(satisfied, trail, k):
    """z3_max_sat(Satisfied) — MaxSAT: maximize satisfied soft weight."""
    from clausal.logic.clpz3 import z3_max_sat
    if z3_max_sat(satisfied, trail):
        yield None

@_builtin("z3_optimize_label", 4)
def _z3_optimize_label__4(vars_list, obj_expr, result, mode, trail, k):
    """z3_optimize_label(Vars, ObjExpr, Result, Mode) — optimize and label."""
    from clausal.logic.clpz3 import z3_optimize_label
    yield from z3_optimize_label(vars_list, obj_expr, result, mode, trail)
```

---

## 7. Clausal Syntax Examples

```prolog
# Job scheduling with preferences
Schedule(T1, T2, T3, COST) <- (
    in_z3([T1, T2, T3], 0, 100),
    all_different_z3([T1, T2, T3]),
    # Hard: T1 before T2
    T1 + 5 <= T2,
    # Soft preferences
    z3_soft(T1 <= 10, 3),       # prefer T1 early
    z3_soft(T2 <= 20, 2),       # prefer T2 early
    z3_soft(T3 <= 15, 1),       # prefer T3 early
    # Minimize makespan
    z3_optimize_label([T1, T2, T3], T3, COST, "minimize")
)

Test("schedule finds optimal") <- Schedule(T1, T2, T3, COST), T1 < T2

# MaxSAT: satisfy as many constraints as possible
MaxSAT(SATISFIED) <- (
    in_z3([X, Y, Z], 0, 1),
    z3_soft(X == 1, 10),
    z3_soft(Y == 1, 5),
    z3_soft(X + Y + Z <= 1, 8),   # conflicts with X=1, Y=1
    z3_max_sat(SATISFIED)
)

Test("maxsat optimal weight") <- MaxSAT(S), S >= 10

# Diet problem (classic LP)
Diet(BREAD, MILK, CHEESE, COST) <- (
    in_z3_real([BREAD, MILK, CHEESE], 0, 100),
    # Nutritional constraints
    2*BREAD + 3.5*MILK + CHEESE >= 6,     # protein
    BREAD + 2*MILK + 3*CHEESE >= 10,      # calcium
    0.5*BREAD + MILK + 2*CHEESE >= 8,     # vitamin
    # Minimize cost
    minimize_z3(2*BREAD + 3.5*MILK + 8*CHEESE, COST)
)
```

---

## 8. Tests

### `tests/test_clpz3_opt.py`

```python
class TestSoftConstraints:
    def test_soft_satisfied(self):
        """Soft constraint that can be satisfied."""
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_soft(ArithEq(x, 5), 1, trail)
        for _ in z3_optimize_label([x], x, Var(), "maximize", trail):
            assert deref(x) == 10  # hard constraint wins: maximize x

    def test_soft_conflict(self):
        """Soft constraints that conflict with each other."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 1, trail)
        z3_soft(ArithEq(x, 0), 5, trail)
        z3_soft(ArithEq(x, 1), 3, trail)
        sat = Var()
        z3_max_sat(sat, trail)
        # Higher weight wins: x=0 (weight 5 > 3)
        assert deref(sat) == 5

    def test_soft_backtrack(self):
        """Soft constraints are retracted on backtrack."""
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)

        mark = trail.mark()
        z3_soft(ArithEq(x, 5), 10, trail)

        trail.undo(mark)

        state = get_z3_state(trail)
        # Soft constraint should be removed
        active = [s for s in state._soft_constraints if s is not None]
        assert len(active) == 0


class TestMaximize:
    def test_integer_maximize(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        from clausal.terms import Add
        z3_eq(Add(x, y), 10, trail)
        obj = Var()
        maximize_z3(x, obj, trail)
        assert deref(obj) == 10

    def test_integer_minimize(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        obj = Var()
        minimize_z3(x, obj, trail)
        assert deref(obj) == 0


class TestMultiObjective:
    def test_lexicographic(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        r1, r2 = Var(), Var()
        results = list(z3_multi_optimize(
            [(x, "maximize"), (y, "maximize")],
            [r1, r2], "lex", trail
        ))
        # Lex: first maximize x (=10), then maximize y (=10)
        assert len(results) == 1

    def test_infeasible(self):
        trail = Trail()
        x = Var()
        in_z3(x, 0, 5, trail)
        z3_eq(x, 10, trail)  # contradicts
        obj = Var()
        assert not maximize_z3(x, obj, trail)
```

---

## 9. Gotchas

1. **Optimize vs Solver push/pop:** `Optimize` supports `push()`/`pop()` but
   only for objectives and soft constraints, not hard assertions. Hard
   assertions are always global. This is why we reconstruct `Optimize` from
   `Solver` rather than maintaining a parallel `Optimize`.

2. **Soft constraint semantics:** A soft constraint with weight 0 is effectively
   ignored. Negative weights are allowed (penalty for satisfaction).

3. **MaxSAT completeness:** `z3_max_sat` returns the globally optimal weight.
   It's not incremental — it solves from scratch each time.

4. **Multi-objective Pareto:** In Pareto mode, `opt.check()` returns successive
   Pareto-optimal points. The loop terminates when no more Pareto points exist.
   This can be expensive for many objectives.

5. **Timeout:** Optimization can be slow for large problems. Consider
   `opt.set("timeout", milliseconds)`.

6. **Unbounded objectives:** If the objective is unbounded, `opt.check()` may
   return `sat` with `+oo` as the objective value. Handle in `z3_to_python`.

7. **Integer vs real optimization:** Z3's `Optimize` handles both. For mixed
   integer-real (MILP), it uses branch-and-bound internally.

---

## Implementation Order

1. Soft constraint storage in `Z3State`
2. `z3_soft()` with trail undo callback
3. `maximize_z3()` / `minimize_z3()` reconstruction from Solver (update Phase 4 impl)
4. `z3_max_sat()`
5. `z3_optimize_label()`
6. Multi-objective optimization
7. Builtin registration
8. Unit tests
9. Integration tests (scheduling, diet problem, MaxSAT)

---

## Issues Encountered During Implementation

### Issue 1: `_build_optimize` shared helper
Extracted the Optimize reconstruction logic (copy assertions + soft constraints) into `_build_optimize()` to share between `_z3_optimize`, `z3_max_sat`, `z3_optimize_label`, and `z3_multi_optimize`.

### Issue 2: Soft constraints interact with maximize/minimize objectives
Z3's Optimize treats soft constraints as part of the optimization problem. `maximize(x)` with `add_soft(x <= 5)` returns x=5, not x=10, because the optimizer balances the objective against soft constraint penalties. This is Z3's intended behavior.

### Issue 3: `in_z3_real` requires bounds
Phase 4's `in_z3_real(var, lo, hi, trail)` requires explicit bounds. Tests initially tried `in_z3_real(x, trail)` which fails. Fixed by providing explicit bounds.

### Issue 4: Consolidated test file
All Phase 7 tests placed in `tests/test_clpz3_opt.py` (26 tests): soft constraints, MaxSAT, optimize+label, multi-objective (lex/box), integration (scheduling), and real-valued optimization.
