# Phase 5: LP/MIP Solver (GLOP, SCIP, CBC, HiGHS, Gurobi, CPLEX, BOP, PDLP)

Linear programming and mixed-integer programming via `ortools.linear_solver.
pywraplp`, supporting 9 solver backends through a unified constraint-block API
with per-solver predicate namespaces.

---

## 1. Import Guard

```python
try:
    from ortools.linear_solver import pywraplp as _pywraplp
    _HAS_LP = True
except ImportError:
    _HAS_LP = False

def _require_lp() -> None:
    if not _HAS_LP:
        raise ImportError(
            "OR-Tools LP/MIP backend requires ortools: pip install ortools"
        )
```

---

## 2. Solver Backend Registry

```python
_LP_SOLVER_IDS = {
    'glop':   'GLOP_LINEAR_PROGRAMMING',
    'scip':   'SCIP_MIXED_INTEGER_PROGRAMMING',
    'cbc':    'CBC_MIXED_INTEGER_PROGRAMMING',
    'highs':  'HIGHS_MIXED_INTEGER_PROGRAMMING',
    'gurobi': 'GUROBI_MIXED_INTEGER_PROGRAMMING',
    'cplex':  'CPLEX_MIXED_INTEGER_PROGRAMMING',
    'bop':    'BOP_INTEGER_PROGRAMMING',
    'pdlp':   'PDLP_LINEAR_PROGRAMMING',
    'sat':    'SAT_INTEGER_PROGRAMMING',

    # LP variants for MIP-capable solvers
    'highs_lp':  'HIGHS_LINEAR_PROGRAMMING',
    'gurobi_lp': 'GUROBI_LINEAR_PROGRAMMING',
    'cplex_lp':  'CPLEX_LINEAR_PROGRAMMING',
    'glpk':      'GLPK_LINEAR_PROGRAMMING',
    'glpk_mip':  'GLPK_MIXED_INTEGER_PROGRAMMING',
}
```

Pattern: mirrors `clpsat.py:_SOLVER_NAMES` — one registry for all backends,
selected by string name at first use.

---

## 3. LPVarInfo

```python
LP_KEY = "lp"

class LPVarInfo:
    """Attribute stored on a Clausal Var under key LP_KEY."""
    __slots__ = ('lp_var', 'kind')

    def __init__(self, lp_var, kind: str) -> None:
        self.lp_var = lp_var     # pywraplp.Variable
        self.kind = kind          # 'continuous', 'integer', or 'boolean'
```

---

## 4. LPConstraintEntry

```python
class LPConstraintEntry:
    """A linear constraint tagged with its activation scope.

    Used for constraint-set rebuild on solve.
    """
    __slots__ = ('lower', 'upper', 'coeffs', 'scope_id')

    def __init__(self, lower: float, upper: float,
                 coeffs: list[tuple], scope_id: int) -> None:
        self.lower = lower       # lower bound (-inf for >=)
        self.upper = upper       # upper bound (+inf for <=)
        self.coeffs = coeffs     # list of (var_id, coefficient)
        self.scope_id = scope_id # which scope added this constraint
```

---

## 5. LPState

```python
class LPState:
    """Per-query LP/MIP solver state, one instance per Trail."""
    __slots__ = ('solver_name', 'var_entries', 'var_map', 'rev_map',
                 'constraints', 'active_scopes', '_scope_counter',
                 '_var_counter', 'objective', 'obj_sense')

    def __init__(self, solver_name: str) -> None:
        _require_lp()
        sid = _LP_SOLVER_IDS.get(solver_name)
        if sid is None:
            raise ValueError(
                f"Unknown LP/MIP solver: {solver_name!r}. "
                f"Available: {sorted(_LP_SOLVER_IDS)}"
            )
        self.solver_name = solver_name
        self.var_entries: list[tuple] = []       # (name, lo, hi, kind)
        self.var_map: dict[int, int] = {}        # id(Var) -> var_entries index
        self.rev_map: dict[int, Any] = {}        # var_entries index -> Var
        self.constraints: list[LPConstraintEntry] = []
        self.active_scopes: set[int] = set()
        self._scope_counter: int = 0
        self._var_counter: int = 0
        self.objective: list[tuple] | None = None   # [(var_idx, coeff), ...]
        self.obj_sense: str | None = None            # 'min' or 'max'
```

---

## 6. State Registry

```python
_lp_states: dict[int, LPState] = {}

def get_lp_state(trail: Trail, solver_name: str = 'glop') -> LPState:
    """Get or create the LPState for this trail."""
    tid = id(trail)
    state = _lp_states.get(tid)
    if state is not None:
        if state.solver_name != solver_name:
            raise ValueError(
                f"LP solver mismatch: trail already using {state.solver_name!r}, "
                f"cannot switch to {solver_name!r}"
            )
        return state
    state = LPState(solver_name)
    _lp_states[tid] = state
    weakref.finalize(trail, _cleanup_lp_state, tid)
    return state

def _cleanup_lp_state(tid: int) -> None:
    _lp_states.pop(tid, None)
```

Pattern: `clpsat.py:get_sat_state()` with solver name mismatch check.

---

## 7. Variable Registration

```python
def lp_var(var: Var, lo: float, hi: float, trail: Trail,
           solver_name: str = 'glop') -> int:
    """Register a continuous LP variable."""
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"lp_var: expected unbound Var, got {type(var).__name__}")
    state = get_lp_state(trail, solver_name)
    vid = id(var)
    if vid in state.var_map:
        return state.var_map[vid]
    state._var_counter += 1
    idx = len(state.var_entries)
    state.var_entries.append((f'x_{state._var_counter}', lo, hi, 'continuous'))
    state.var_map[vid] = idx
    state.rev_map[idx] = var
    put_attr(var, LP_KEY, LPVarInfo(idx, 'continuous'), trail)
    return idx


def lp_int_var(var: Var, lo: int, hi: int, trail: Trail,
               solver_name: str = 'glop') -> int:
    """Register an integer LP/MIP variable."""
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"lp_int_var: expected unbound Var")
    state = get_lp_state(trail, solver_name)
    vid = id(var)
    if vid in state.var_map:
        return state.var_map[vid]
    state._var_counter += 1
    idx = len(state.var_entries)
    state.var_entries.append((f'i_{state._var_counter}', float(lo), float(hi), 'integer'))
    state.var_map[vid] = idx
    state.rev_map[idx] = var
    put_attr(var, LP_KEY, LPVarInfo(idx, 'integer'), trail)
    return idx


def lp_bool_var(var: Var, trail: Trail, solver_name: str = 'glop') -> int:
    """Register a Boolean LP/MIP variable."""
    return lp_int_var(var, 0, 1, trail, solver_name)
```

---

## 8. Scope Management (Constraint Tagging)

```python
def lp_push(trail: Trail, solver_name: str = 'glop') -> None:
    """Create a new constraint scope.

    Subsequent constraints are tagged with this scope's ID.
    On backtrack, the scope is removed from active_scopes.
    """
    state = get_lp_state(trail, solver_name)
    state._scope_counter += 1
    scope_id = state._scope_counter
    state.active_scopes.add(scope_id)
    trail.record(lambda: state.active_scopes.discard(scope_id))
```

Unlike CP-SAT's OnlyEnforceIf, LP/MIP uses **constraint tagging + rebuild**.
Each constraint is tagged with the scope that created it.  On solve, only
constraints whose scope is in `active_scopes` are included in the rebuilt model.

---

## 9. Expression Translation (Linear)

```python
def clausal_to_lp_coeffs(expr: Any, trail: Trail) -> dict[int, float]:
    """Translate a Clausal arithmetic expression to LP coefficient dict.

    Returns {var_idx: coefficient, ...} plus a special key -1 for the
    constant term.

    Only linear expressions are supported.  Raises TypeError for
    nonlinear expressions (x * y where both are variables).
    """
    expr = deref(expr)
    state = get_lp_state(trail)

    if is_var(expr):
        vid = id(expr)
        idx = state.var_map.get(vid)
        if idx is None:
            raise ValueError("Variable not registered with LP solver")
        return {idx: 1.0}

    if isinstance(expr, (int, float)):
        return {-1: float(expr)}

    if isinstance(expr, _Add):
        left = clausal_to_lp_coeffs(expr.left, trail)
        right = clausal_to_lp_coeffs(expr.right, trail)
        result = dict(left)
        for k, v in right.items():
            result[k] = result.get(k, 0.0) + v
        return result

    if isinstance(expr, _Sub):
        left = clausal_to_lp_coeffs(expr.left, trail)
        right = clausal_to_lp_coeffs(expr.right, trail)
        result = dict(left)
        for k, v in right.items():
            result[k] = result.get(k, 0.0) - v
        return result

    if isinstance(expr, _Mult):
        left = clausal_to_lp_coeffs(expr.left, trail)
        right = clausal_to_lp_coeffs(expr.right, trail)
        # One side must be a constant
        left_vars = {k: v for k, v in left.items() if k != -1}
        right_vars = {k: v for k, v in right.items() if k != -1}
        if left_vars and right_vars:
            raise TypeError("LP constraints must be linear: x * y is not allowed")
        if not left_vars:
            # left is constant
            c = left.get(-1, 0.0)
            return {k: v * c for k, v in right.items()}
        else:
            c = right.get(-1, 0.0)
            return {k: v * c for k, v in left.items()}

    if isinstance(expr, _Negate):
        inner = clausal_to_lp_coeffs(expr.operand, trail)
        return {k: -v for k, v in inner.items()}

    raise TypeError(f"Cannot translate {type(expr).__name__} to LP expression")
```

---

## 10. Constraint Translation

```python
def _translate_lp_constraint(expr: Any, trail: Trail) -> LPConstraintEntry:
    """Translate a comparison expression to an LPConstraintEntry."""
    expr = deref(expr)
    state = get_lp_state(trail)
    scope_id = max(state.active_scopes) if state.active_scopes else 0
    INF = float('inf')

    if isinstance(expr, _ArithEq):
        # left == right  =>  left - right == 0
        diff = clausal_to_lp_coeffs(_Sub(expr.left, expr.right), trail)
        const = diff.pop(-1, 0.0)
        coeffs = list(diff.items())
        return LPConstraintEntry(-const, -const, coeffs, scope_id)

    if isinstance(expr, _LtE):
        # left <= right  =>  left - right <= 0
        diff = clausal_to_lp_coeffs(_Sub(expr.left, expr.right), trail)
        const = diff.pop(-1, 0.0)
        coeffs = list(diff.items())
        return LPConstraintEntry(-INF, -const, coeffs, scope_id)

    if isinstance(expr, _GtE):
        # left >= right  =>  left - right >= 0
        diff = clausal_to_lp_coeffs(_Sub(expr.left, expr.right), trail)
        const = diff.pop(-1, 0.0)
        coeffs = list(diff.items())
        return LPConstraintEntry(-const, INF, coeffs, scope_id)

    if isinstance(expr, _Lt):
        # left < right  =>  left - right <= -epsilon
        # For LP, strict inequalities are approximated
        diff = clausal_to_lp_coeffs(_Sub(expr.left, expr.right), trail)
        const = diff.pop(-1, 0.0)
        coeffs = list(diff.items())
        return LPConstraintEntry(-INF, -const - 1e-6, coeffs, scope_id)

    if isinstance(expr, _Gt):
        diff = clausal_to_lp_coeffs(_Sub(expr.left, expr.right), trail)
        const = diff.pop(-1, 0.0)
        coeffs = list(diff.items())
        return LPConstraintEntry(-const + 1e-6, INF, coeffs, scope_id)

    raise TypeError(f"Cannot translate {type(expr).__name__} to LP constraint")
```

---

## 11. Constraint Block

```python
def lp_constraint_block(constraint_set: Any, solver_name: str,
                         trail: Trail) -> bool:
    """Post a block of linear constraints.

    Each element in the tuple/list is a comparison expression.
    All are tagged with the current scope for backtracking.
    """
    state = get_lp_state(trail, solver_name)

    if isinstance(constraint_set, (list, tuple)):
        elements = constraint_set
    else:
        elements = [constraint_set]

    lp_push(trail, solver_name)

    for elem in elements:
        elem = deref(elem)
        entry = _translate_lp_constraint(elem, trail)
        state.constraints.append(entry)

    return True
```

---

## 12. Model Rebuild and Solve

```python
def _rebuild_and_solve(state: LPState) -> tuple:
    """Rebuild the LP/MIP model from active constraints and solve.

    Returns (status, solver) where status is pywraplp.Solver.OPTIMAL etc.
    """
    sid_str = _LP_SOLVER_IDS[state.solver_name]
    solver = _pywraplp.Solver.CreateSolver(sid_str)
    if solver is None:
        raise RuntimeError(
            f"LP solver {state.solver_name!r} not available. "
            f"Check ortools installation."
        )

    # Recreate variables
    lp_vars = []
    for name, lo, hi, kind in state.var_entries:
        if kind == 'continuous':
            lp_vars.append(solver.NumVar(lo, hi, name))
        elif kind == 'integer':
            lp_vars.append(solver.IntVar(lo, hi, name))
        else:
            raise ValueError(f"Unknown var kind: {kind}")

    # Add only active constraints
    for ct in state.constraints:
        if ct.scope_id in state.active_scopes or ct.scope_id == 0:
            constraint = solver.Constraint(ct.lower, ct.upper)
            for var_idx, coeff in ct.coeffs:
                constraint.SetCoefficient(lp_vars[var_idx], coeff)

    # Set objective if any
    if state.objective is not None:
        obj = solver.Objective()
        for var_idx, coeff in state.objective:
            obj.SetCoefficient(lp_vars[var_idx], coeff)
        if state.obj_sense == 'min':
            obj.SetMinimization()
        else:
            obj.SetMaximization()

    status = solver.Solve()
    return status, solver, lp_vars


def lp_check(trail: Trail) -> bool:
    """Return True if current LP/MIP constraints are feasible."""
    state = get_lp_state(trail)
    status, _, _ = _rebuild_and_solve(state)
    return status in (_pywraplp.Solver.OPTIMAL, _pywraplp.Solver.FEASIBLE)
```

---

## 13. Solve and Bind Values

```python
def lp_solve(vars_list: Any, trail: Trail):
    """Solve the LP/MIP and bind Clausal variables to their values.

    Generator: yields once on success.  For LP, there is typically one
    solution.  For MIP, yields the optimal/feasible solution.
    """
    state = get_lp_state(trail)
    status, solver, lp_vars = _rebuild_and_solve(state)

    if status not in (_pywraplp.Solver.OPTIMAL, _pywraplp.Solver.FEASIBLE):
        return  # fail

    mark = trail.mark()
    items = _as_list(vars_list)
    ok = True
    for v in items:
        v = deref(v)
        if is_var(v):
            vid = id(v)
            idx = state.var_map.get(vid)
            if idx is None:
                raise ValueError("lp_solve: variable not registered")
            value = lp_vars[idx].solution_value()
            # For integer vars, round to int
            kind = state.var_entries[idx][3]
            if kind == 'integer':
                value = int(round(value))
            if not unify(v, value, trail):
                ok = False
                break

    if ok:
        yield None
    trail.undo(mark)
```

---

## 14. Optimization

```python
def lp_minimize(expr: Any, val: Any, trail: Trail):
    """Minimize a linear objective and unify val with the optimal value."""
    state = get_lp_state(trail)
    coeffs = clausal_to_lp_coeffs(expr, trail)
    const = coeffs.pop(-1, 0.0)
    state.objective = list(coeffs.items())
    state.obj_sense = 'min'

    status, solver, lp_vars = _rebuild_and_solve(state)

    if status in (_pywraplp.Solver.OPTIMAL, _pywraplp.Solver.FEASIBLE):
        obj_val = solver.Objective().Value() + const
        mark = trail.mark()
        # Bind variables
        for idx, clausal_var in state.rev_map.items():
            value = lp_vars[idx].solution_value()
            kind = state.var_entries[idx][3]
            if kind == 'integer':
                value = int(round(value))
            unify(clausal_var, value, trail)
        if unify(val, obj_val, trail):
            yield None
        trail.undo(mark)


def lp_maximize(expr: Any, val: Any, trail: Trail):
    """Maximize a linear objective and unify val with the optimal value."""
    state = get_lp_state(trail)
    coeffs = clausal_to_lp_coeffs(expr, trail)
    const = coeffs.pop(-1, 0.0)
    state.objective = list(coeffs.items())
    state.obj_sense = 'max'

    status, solver, lp_vars = _rebuild_and_solve(state)

    if status in (_pywraplp.Solver.OPTIMAL, _pywraplp.Solver.FEASIBLE):
        obj_val = solver.Objective().Value() + const
        mark = trail.mark()
        for idx, clausal_var in state.rev_map.items():
            value = lp_vars[idx].solution_value()
            kind = state.var_entries[idx][3]
            if kind == 'integer':
                value = int(round(value))
            unify(clausal_var, value, trail)
        if unify(val, obj_val, trail):
            yield None
        trail.undo(mark)
```

---

## 15. Tests (Phase 5)

```python
class TestLPCoreInfra:

    def test_glop_available(self):
        solver = _pywraplp.Solver.CreateSolver('GLOP')
        assert solver is not None

    def test_var_registration(self):
        trail = Trail()
        x = Var()
        lp_var(x, 0.0, 100.0, trail, 'glop')
        state = get_lp_state(trail, 'glop')
        assert id(x) in state.var_map

    def test_solver_mismatch(self):
        trail = Trail()
        get_lp_state(trail, 'glop')
        with pytest.raises(ValueError, match="mismatch"):
            get_lp_state(trail, 'scip')


class TestLPFeasibility:

    def test_simple_feasible(self):
        trail = Trail()
        x = Var()
        lp_var(x, 0.0, 100.0, trail, 'glop')
        lp_constraint_block((LtE(x, 50),), 'glop', trail)
        assert lp_check(trail)

    def test_simple_infeasible(self):
        trail = Trail()
        x = Var()
        lp_var(x, 0.0, 10.0, trail, 'glop')
        lp_constraint_block((GtE(x, 20),), 'glop', trail)
        assert not lp_check(trail)

    def test_backtracking_retracts(self):
        trail = Trail()
        x = Var()
        lp_var(x, 0.0, 100.0, trail, 'glop')
        mark = trail.mark()
        lp_constraint_block((
            GtE(x, 50),
            LtE(x, 30),   # contradicts
        ), 'glop', trail)
        assert not lp_check(trail)
        trail.undo(mark)
        assert lp_check(trail)


class TestLPOptimization:

    def test_minimize_glop(self):
        """Minimize 3x + 5y subject to x + y >= 10, x >= 0, y >= 0."""
        trail = Trail()
        x, y = Var(), Var()
        lp_var(x, 0.0, 100.0, trail, 'glop')
        lp_var(y, 0.0, 100.0, trail, 'glop')
        lp_constraint_block((GtE(Add(x, y), 10),), 'glop', trail)
        val = Var()
        for _ in lp_minimize(Add(Mult(3, x), Mult(5, y)), val, trail):
            assert deref(val) == pytest.approx(30.0)  # x=10, y=0

    def test_diet_problem(self):
        """Classic diet LP."""
        trail = Trail()
        bread, milk = Var(), Var()
        lp_var(bread, 0.0, 10.0, trail, 'glop')
        lp_var(milk, 0.0, 10.0, trail, 'glop')
        lp_constraint_block((
            GtE(Add(Mult(2, bread), Mult(3, milk)), 6),   # protein
            GtE(Add(bread, Mult(2, milk)), 4),            # calcium
        ), 'glop', trail)
        val = Var()
        for _ in lp_minimize(Add(Mult(2, bread), Mult(3, milk)), val, trail):
            assert isinstance(deref(val), float)
            assert deref(val) >= 0


class TestMIP:

    def test_integer_optimization_cbc(self):
        """MIP with integer variables via CBC."""
        trail = Trail()
        x, y = Var(), Var()
        lp_int_var(x, 0, 100, trail, 'cbc')
        lp_int_var(y, 0, 100, trail, 'cbc')
        lp_constraint_block((
            LtE(Add(x, y), 10),
        ), 'cbc', trail)
        val = Var()
        for _ in lp_maximize(Add(Mult(3, x), Mult(5, y)), val, trail):
            # x=0, y=10 -> 50
            assert deref(val) == 50.0

    def test_scip_available(self):
        """SCIP backend should be available."""
        trail = Trail()
        state = get_lp_state(trail, 'scip')
        assert state.solver_name == 'scip'
```

---

## Implementation Order

1. Import guard + `_require_lp()`
2. `_LP_SOLVER_IDS`
3. `LPVarInfo`, `LP_KEY`
4. `LPConstraintEntry`
5. `LPState`
6. `get_lp_state()` + `_cleanup_lp_state()`
7. `lp_var()`, `lp_int_var()`, `lp_bool_var()`
8. `lp_push()`
9. `clausal_to_lp_coeffs()`
10. `_translate_lp_constraint()`
11. `lp_constraint_block()`
12. `_rebuild_and_solve()`
13. `lp_check()`
14. `lp_solve()`
15. `lp_minimize()`, `lp_maximize()`
16. Tests

---

## Review & Checkpoint

After implementing this phase, perform the following review before moving on.

### 1. Run Tests

```bash
pytest tests/test_clportools_lp.py -v -k "TestLPCoreInfra or TestLPFeasibility or TestLPOptimization or TestMIP"
```

All tests listed in this phase must pass. If any fail, diagnose and fix
before continuing.

### 2. Code Review Checklist

- [ ] Every `deref()` call happens before `isinstance` checks
- [ ] Every `trail.record(callback)` callback captures only simple values
      (ints, not Trail objects) to avoid preventing GC
- [ ] Every constraint addition is tagged with the correct scope ID
      (LP/MIP uses scope ID tagging, not `OnlyEnforceIf`)
- [ ] `yield None` for success, bare `return` for failure — never
      `yield True` or `return False`
- [ ] No circular imports — builtin functions use lazy imports
- [ ] Verify `_rebuild_and_solve` correctly excludes constraints from
      inactive scopes

### 3. Write Issues Into This File

If you discover any issues during implementation — bugs, design decisions
that needed to change, gotchas not covered in the plan, or things that
worked differently than expected — **append them to this file** under a new
section:

```markdown
## Implementation Issues (Post-Implementation Addendum)

### Issue 1 — [short description]

**Problem:** ...
**Resolution:** ...
```

Number issues sequentially. Include enough detail that someone reading the
plan later understands what happened and why.

### 4. Ask Before Continuing If:

- A design decision in the plan seems wrong or suboptimal after seeing
  the real code
- A test requires infrastructure that doesn't exist yet (e.g., a missing
  `cons_to_list`, a Trail method that behaves differently than documented)
- You need to modify files outside the scope of this phase (e.g., changing
  the Trail C extension, modifying the compiler, editing another solver's
  code)
- The phase's approach is fundamentally incompatible with something you
  discovered in the codebase

**Do not silently work around these — surface them so the right decision
can be made.**
