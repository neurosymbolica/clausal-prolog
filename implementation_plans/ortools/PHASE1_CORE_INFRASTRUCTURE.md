# Phase 1: Core Infrastructure

Core data structures, variable mapping, OnlyEnforceIf activation-literal
backtracking, and basic constraint operations for CP-SAT.  Also establishes
the shared LP/MIP state pattern used in Phase 5.

---

## 1. Import Guard

```python
try:
    from ortools.sat.python import cp_model as _cp_model
    _CpModel = _cp_model.CpModel
    _CpSolver = _cp_model.CpSolver
    _CpSolverSolutionCallback = _cp_model.CpSolverSolutionCallback
    _OPTIMAL = _cp_model.OPTIMAL
    _FEASIBLE = _cp_model.FEASIBLE
    _INFEASIBLE = _cp_model.INFEASIBLE
    _MODEL_INVALID = _cp_model.MODEL_INVALID
    _Domain = _cp_model.Domain
    _LinearExpr = _cp_model.LinearExpr
    _HAS_ORTOOLS = True
except ImportError:
    _HAS_ORTOOLS = False

def _require_ortools() -> None:
    if not _HAS_ORTOOLS:
        raise ImportError(
            "OR-Tools backend requires the ortools package: pip install ortools"
        )
```

Pattern: identical to `clpsat.py:10-20` and `clpz3.py:44-57`.

---

## 2. ORVarInfo

```python
OR_KEY = "or"

class ORVarInfo:
    """Attribute stored on a Clausal Var under key OR_KEY."""
    __slots__ = ('cpsat_var', 'kind')

    def __init__(self, cpsat_var, kind: str) -> None:
        self.cpsat_var = cpsat_var   # IntVar or BoolVar from CpModel
        self.kind = kind             # 'int' or 'bool'
```

Pattern: similar to `Z3VarInfo` in `clpz3.py:82-93`, with `kind` instead of
Z3's `sort`.  Two kinds: `'int'` for `IntVar`, `'bool'` for `BoolVar`.

---

## 3. CPSATState

```python
class CPSATState:
    """Per-query CP-SAT solver state, one instance per Trail."""
    __slots__ = ('model', 'solver', 'var_map', 'rev_map',
                 'active_lits', '_int_counter', '_bool_counter',
                 '_interval_counter', '_interval_map')

    def __init__(self) -> None:
        _require_ortools()
        self.model = _CpModel()
        self.solver = _CpSolver()
        self.var_map: dict[int, Any] = {}        # id(Var) -> IntVar|BoolVar
        self.rev_map: dict[int, Any] = {}         # cpsat var index -> Var
        self.active_lits: list[Any] = []          # active activation BoolVars
        self._int_counter: int = 0                # unique name counter
        self._bool_counter: int = 0
        self._interval_counter: int = 0
        self._interval_map: dict[int, Any] = {}   # id(Var) -> IntervalVar
```

Note: Unlike PySAT (which requires solver name selection from 15+ backends),
CP-SAT has a single solver.  No `solver_name` parameter.

---

## 4. State Registry

```python
_cpsat_states: dict[int, CPSATState] = {}

def get_cpsat_state(trail: Trail) -> CPSATState:
    """Get or create the CPSATState for this trail."""
    tid = id(trail)
    state = _cpsat_states.get(tid)
    if state is not None:
        return state
    state = CPSATState()
    _cpsat_states[tid] = state
    weakref.finalize(trail, _cleanup_cpsat_state, tid)
    return state

def _cleanup_cpsat_state(tid: int) -> None:
    _cpsat_states.pop(tid, None)
```

Pattern: `clpsat.py:get_sat_state()`, simplified (no solver name).
CP-SAT objects are pure Python/protobuf — Python GC handles cleanup.

---

## 5. Variable Registration (Integer)

```python
def or_var_for(var: Var, lo: int, hi: int, trail: Trail) -> Any:
    """Get or create a CP-SAT IntVar for a Clausal Var.

    Returns the CpModel IntVar.  If the Var already has a CP-SAT variable,
    returns the existing one (domain was set at creation; use additional
    constraints to narrow it further).
    """
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"or_var_for: expected unbound Var, got {type(var).__name__}")

    state = get_cpsat_state(trail)
    vid = id(var)
    existing = state.var_map.get(vid)
    if existing is not None:
        return existing

    state._int_counter += 1
    name = f'x_{state._int_counter}'
    cpsat_var = state.model.NewIntVar(lo, hi, name)

    state.var_map[vid] = cpsat_var
    state.rev_map[cpsat_var.Index()] = var

    put_attr(var, OR_KEY, ORVarInfo(cpsat_var, 'int'), trail)

    return cpsat_var
```

Pattern: `clpz3.py:z3_var_for()` + `clpsat.py:sat_var_for()`.

### Gotcha: Domain Fixed at Creation

CP-SAT `NewIntVar(lb, ub, name)` fixes the variable's domain at creation.
If the user calls `ortools.cpsat.in(X, 1, 9)` then later
`ortools.cpsat.in(X, 3, 7)`, the second call must detect the existing
variable and add explicit bound constraints:

```python
state.model.Add(cpsat_var >= 3).OnlyEnforceIf(act_lit)
state.model.Add(cpsat_var <= 7).OnlyEnforceIf(act_lit)
```

This is handled in Phase 2's `or_in()` function.

---

## 6. Variable Registration (Sparse Domain)

```python
def or_var_from_domain(var: Var, values: list[int], trail: Trail) -> Any:
    """Create a CP-SAT IntVar with a sparse domain."""
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"or_var_from_domain: expected unbound Var, got {type(var).__name__}")

    state = get_cpsat_state(trail)
    vid = id(var)
    existing = state.var_map.get(vid)
    if existing is not None:
        return existing

    state._int_counter += 1
    name = f'x_{state._int_counter}'
    domain = _Domain.FromValues(values)
    cpsat_var = state.model.NewIntVarFromDomain(domain, name)

    state.var_map[vid] = cpsat_var
    state.rev_map[cpsat_var.Index()] = var

    put_attr(var, OR_KEY, ORVarInfo(cpsat_var, 'int'), trail)

    return cpsat_var
```

---

## 7. Variable Registration (Boolean)

```python
def or_bool_for(var: Var, trail: Trail) -> Any:
    """Get or create a CP-SAT BoolVar for a Clausal Var."""
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"or_bool_for: expected unbound Var, got {type(var).__name__}")

    state = get_cpsat_state(trail)
    vid = id(var)
    existing = state.var_map.get(vid)
    if existing is not None:
        return existing

    state._bool_counter += 1
    name = f'b_{state._bool_counter}'
    cpsat_var = state.model.NewBoolVar(name)

    state.var_map[vid] = cpsat_var
    state.rev_map[cpsat_var.Index()] = var

    put_attr(var, OR_KEY, ORVarInfo(cpsat_var, 'bool'), trail)

    return cpsat_var
```

---

## 8. Fresh Activation Literal

```python
def _fresh_act_lit(state: CPSATState) -> Any:
    """Allocate a fresh BoolVar for use as an activation literal.

    Not mapped to any Clausal Var.  Used only for OnlyEnforceIf scoping.
    """
    state._bool_counter += 1
    return state.model.NewBoolVar(f'_act_{state._bool_counter}')
```

Pattern: `clpsat.py:_fresh_sat_var()`, but returns a BoolVar instead of an int.

---

## 9. Activation Literal Scope Management

```python
def or_push(trail: Trail) -> None:
    """Push a new activation-literal scope.

    Creates a fresh BoolVar as an activation literal, adds it to
    the active list, and records a trail callback to remove it on
    backtrack.
    """
    state = get_cpsat_state(trail)
    act = _fresh_act_lit(state)
    state.active_lits.append(act)
    trail.record(lambda: state.active_lits.remove(act))
```

Pattern: identical to `clpsat.py:sat_push()`, using CP-SAT BoolVar instead
of a raw SAT integer.

---

## 10. Constraint Addition

```python
def or_add_constraint(constraint_expr, trail: Trail) -> None:
    """Add a CP-SAT constraint guarded by the current activation literal.

    `constraint_expr` is a BoundedLinearExpression (the argument to
    model.Add()), e.g., `cpsat_x + cpsat_y <= 10`.

    If no activation scope is active, the constraint is added unguarded.
    """
    state = get_cpsat_state(trail)
    ct = state.model.Add(constraint_expr)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
```

### Design: Guard on Innermost Literal Only

We guard on `active_lits[-1]` (the innermost scope) rather than all active
literals.  This is correct because:

1. Outer activation literals are always in `active_lits` and will be assumed
   True via `AddAssumptions` before solving
2. `OnlyEnforceIf(act)` only needs `act` to be True — it doesn't care about
   other literals
3. When the inner scope is backtracked, `act` is removed from `active_lits`
   and no longer assumed True, so the constraint becomes dormant

Guarding on just the innermost literal is equivalent to guarding on all of
them (since outer ones are always True), and is simpler.

---

## 11. Apply Assumptions

```python
def _apply_assumptions(state: CPSATState) -> None:
    """Fix all active activation literals to True via model assumptions.

    Must be called before every solver.Solve() call.
    """
    state.model.ClearAssumptions()
    if state.active_lits:
        state.model.AddAssumptions(state.active_lits)
```

---

## 12. Satisfiability Check

```python
def or_check(trail: Trail) -> bool:
    """Return True if current constraints are satisfiable."""
    state = get_cpsat_state(trail)
    _apply_assumptions(state)
    status = state.solver.Solve(state.model)
    return status in (_OPTIMAL, _FEASIBLE)
```

Note: CP-SAT returns `OPTIMAL` for satisfaction problems (no objective) and
`FEASIBLE` for optimization problems with a feasible but possibly non-optimal
solution.  Both mean "satisfiable".

---

## 13. Tests (Phase 1)

```python
class TestCPSATCoreInfrastructure:

    def test_var_mapping_bidirectional(self):
        trail = Trail()
        x = Var()
        state = get_cpsat_state(trail)
        cpsat_x = or_var_for(x, 0, 10, trail)
        assert id(x) in state.var_map
        assert state.var_map[id(x)] is cpsat_x
        assert state.rev_map[cpsat_x.Index()] is x

    def test_var_mapping_idempotent(self):
        trail = Trail()
        x = Var()
        v1 = or_var_for(x, 0, 10, trail)
        v2 = or_var_for(x, 0, 10, trail)
        assert v1 is v2

    def test_bool_var_mapping(self):
        trail = Trail()
        b = Var()
        cpsat_b = or_bool_for(b, trail)
        state = get_cpsat_state(trail)
        assert id(b) in state.var_map
        assert state.rev_map[cpsat_b.Index()] is b

    def test_sparse_domain(self):
        trail = Trail()
        x = Var()
        cpsat_x = or_var_from_domain(x, [1, 3, 5, 7], trail)
        state = get_cpsat_state(trail)
        assert id(x) in state.var_map

    def test_ground_var_raises(self):
        trail = Trail()
        x = Var()
        unify(x, 1, trail)
        with pytest.raises(TypeError):
            or_var_for(x, 0, 10, trail)

    def test_simple_sat(self):
        trail = Trail()
        x = Var()
        cpsat_x = or_var_for(x, 0, 10, trail)
        or_add_constraint(cpsat_x >= 5, trail)
        assert or_check(trail)

    def test_simple_unsat(self):
        trail = Trail()
        x = Var()
        cpsat_x = or_var_for(x, 0, 10, trail)
        or_add_constraint(cpsat_x >= 8, trail)
        or_add_constraint(cpsat_x <= 3, trail)
        assert not or_check(trail)

    def test_backtracking_retracts_constraints(self):
        """Constraints added inside a scope become dormant after backtrack."""
        trail = Trail()
        x = Var()
        cpsat_x = or_var_for(x, 0, 10, trail)

        mark = trail.mark()
        or_push(trail)
        or_add_constraint(cpsat_x >= 8, trail)
        or_add_constraint(cpsat_x <= 3, trail)
        assert not or_check(trail)      # UNSAT

        trail.undo(mark)                 # backtrack — activation lit removed
        assert or_check(trail)           # SAT again

    def test_nested_backtracking(self):
        """Inner scope constraints retracted independently of outer."""
        trail = Trail()
        x = Var()
        cpsat_x = or_var_for(x, 0, 10, trail)

        or_push(trail)
        or_add_constraint(cpsat_x >= 5, trail)    # scope 1: x >= 5
        mark = trail.mark()

        or_push(trail)
        or_add_constraint(cpsat_x <= 3, trail)    # scope 2: x <= 3 (contradicts)
        assert not or_check(trail)

        trail.undo(mark)                  # retract scope 2
        assert or_check(trail)            # scope 1 still active: x in [5, 10]

    def test_three_nested_scopes(self):
        trail = Trail()
        x = Var()
        cpsat_x = or_var_for(x, 0, 100, trail)

        or_push(trail)
        or_add_constraint(cpsat_x >= 10, trail)
        mark1 = trail.mark()

        or_push(trail)
        or_add_constraint(cpsat_x >= 50, trail)
        mark2 = trail.mark()

        or_push(trail)
        or_add_constraint(cpsat_x >= 200, trail)  # UNSAT: domain [0,100]
        assert not or_check(trail)

        trail.undo(mark2)
        assert or_check(trail)   # x in [50, 100]

        trail.undo(mark1)
        assert or_check(trail)   # x in [10, 100]

    def test_state_cleanup_on_gc(self):
        import gc
        trail = Trail()
        get_cpsat_state(trail)
        tid = id(trail)
        assert tid in _cpsat_states
        del trail
        gc.collect()
        assert tid not in _cpsat_states

    def test_multiple_vars(self):
        trail = Trail()
        x = Var()
        y = Var()
        cpsat_x = or_var_for(x, 0, 10, trail)
        cpsat_y = or_var_for(y, 0, 10, trail)
        or_add_constraint(cpsat_x + cpsat_y == 15, trail)
        assert or_check(trail)
        or_add_constraint(cpsat_x + cpsat_y == 25, trail)  # contradicts domain
        assert not or_check(trail)
```

---

## Implementation Order

1. Import guard + `_require_ortools()`
2. `ORVarInfo`, `OR_KEY`
3. `CPSATState`
4. `get_cpsat_state()` + `_cleanup_cpsat_state()`
5. `or_var_for()`
6. `or_var_from_domain()`
7. `or_bool_for()`
8. `_fresh_act_lit()`
9. `or_push()`
10. `or_add_constraint()`
11. `_apply_assumptions()`
12. `or_check()`
13. Tests

---

## Review & Checkpoint

After implementing this phase, perform the following review before moving on.

### 1. Run Tests

```bash
pytest tests/test_clportools.py -v -k "TestCPSATCoreInfrastructure"
```

All tests listed in this phase must pass. If any fail, diagnose and fix
before continuing.

### 2. Code Review Checklist

- [ ] Every `deref()` call happens before `isinstance` checks
- [ ] Every `trail.record(callback)` callback captures only simple values
      (ints, not Trail objects) to avoid preventing GC
- [ ] Every constraint addition is guarded by `OnlyEnforceIf` when
      `active_lits` is non-empty
- [ ] `yield None` for success, bare `return` for failure — never
      `yield True` or `return False`
- [ ] No circular imports — builtin functions use lazy imports
- [ ] Verify `weakref.finalize` actually fires on `CPSATState` cleanup
      (the Z3 plan had a real issue here with Trail not supporting weakrefs)

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
