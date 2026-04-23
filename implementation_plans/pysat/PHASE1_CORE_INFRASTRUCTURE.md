# Phase 1: Core Infrastructure

Core data structures, variable mapping, activation-literal backtracking, and
basic clause operations.

---

## 1. Import Guard

```python
try:
    from pysat.solvers import Solver as _PySATSolver
    from pysat.card import CardEnc as _CardEnc, EncType as _EncType
    from pysat.formula import CNF as _CNF
    _HAS_PYSAT = True
except ImportError:
    _HAS_PYSAT = False

def _require_pysat() -> None:
    if not _HAS_PYSAT:
        raise ImportError(
            "PySAT backend requires the python-sat package: pip install python-sat"
        )
```

Pattern: identical to `clpz3.py:44-57`.

---

## 2. SATVarInfo

```python
SAT_KEY = "sat"

class SATVarInfo:
    """Attribute stored on a Clausal Var under key SAT_KEY."""
    __slots__ = ('sat_var',)

    def __init__(self, sat_var: int) -> None:
        self.sat_var = sat_var   # positive integer (PySAT variable number)
```

Pattern: identical to `Z3VarInfo` in `clpz3.py:82-93`, but simpler (SAT vars
are just ints, no sort).

---

## 3. SATState

```python
# Solver name aliases (PySAT abbreviations)
_SOLVER_NAMES = {
    'cadical195': 'cadical195', 'cadical153': 'cadical153', 'cadical': 'cadical195',
    'glucose': 'g421', 'glucose3': 'g3', 'glucose4': 'g4', 'g421': 'g421',
    'g4': 'g4', 'g3': 'g3',
    'minisat': 'm22', 'm22': 'm22', 'mgh': 'mgh',
    'kissat': 'kissat',
    'lingeling': 'lgl', 'lgl': 'lgl',
    'maplesat': 'mpl', 'mpl': 'mpl',
    'maplechrono': 'mcb', 'mcb': 'mcb',
    'maplelcm': 'mcl', 'mcl': 'mcl',
    'mergesat': 'mg3', 'mg3': 'mg3',
    'minicard': 'mc', 'mc': 'mc',
}

class SATState:
    """Per-query SAT solver state, one instance per Trail."""
    __slots__ = ('solver', 'var_map', 'rev_map', 'assumptions',
                 '_counter', 'solver_name')

    def __init__(self, solver_name: str = 'cadical195') -> None:
        _require_pysat()
        name = _SOLVER_NAMES.get(solver_name)
        if name is None:
            raise ValueError(f"Unknown SAT solver: {solver_name!r}. "
                             f"Available: {sorted(_SOLVER_NAMES)}")
        self.solver_name = name
        self.solver = _PySATSolver(name=name)
        self.var_map: dict[int, int] = {}      # id(Var) -> SAT var number
        self.rev_map: dict[int, Var] = {}       # SAT var number -> Var
        self.assumptions: list[int] = []        # active activation literals
        self._counter: int = 0                  # next SAT variable number
```

---

## 4. State Registry

```python
_sat_states: dict[int, SATState] = {}

def get_sat_state(trail: Trail, solver_name: str = 'cadical195') -> SATState:
    """Get or create the SATState for this trail."""
    tid = id(trail)
    state = _sat_states.get(tid)
    if state is not None:
        if state.solver_name != _SOLVER_NAMES.get(solver_name, solver_name):
            raise ValueError(
                f"SAT solver mismatch: trail already using {state.solver_name!r}, "
                f"cannot switch to {solver_name!r}"
            )
        return state
    state = SATState(solver_name)
    _sat_states[tid] = state
    # Clean up when Trail is GC'd
    weakref.finalize(trail, _cleanup_sat_state, tid)
    return state

def _cleanup_sat_state(tid: int) -> None:
    state = _sat_states.pop(tid, None)
    if state is not None:
        state.solver.delete()
```

Note: PySAT solvers have a `delete()` method that must be called for cleanup.
The `weakref.finalize` callback handles this.

Pattern: `clpz3.py:118-131`, extended with solver cleanup.

---

## 5. Variable Registration

```python
def sat_var_for(var: Var, trail: Trail) -> int:
    """Get or create a SAT variable number for a Clausal Var.

    Returns a positive integer (PySAT variable number).
    """
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"sat_var_for: expected unbound Var, got {type(var).__name__}")

    state = get_sat_state(trail)
    vid = id(var)
    existing = state.var_map.get(vid)
    if existing is not None:
        return existing

    state._counter += 1
    sat_var = state._counter

    state.var_map[vid] = sat_var
    state.rev_map[sat_var] = var

    put_attr(var, SAT_KEY, SATVarInfo(sat_var), trail)

    return sat_var
```

Pattern: `clpz3.py:136-170`, simplified (no sort parameter).

---

## 6. Fresh Variable (no Clausal Var)

```python
def _fresh_sat_var(state: SATState) -> int:
    """Allocate a fresh SAT variable number (not mapped to a Clausal Var).

    Used for activation literals and Tseitin auxiliary variables.
    """
    state._counter += 1
    return state._counter
```

---

## 7. Activation Literal Scope Management

```python
def sat_push(trail: Trail) -> None:
    """Push a new activation-literal scope.

    Creates a fresh SAT variable as an activation literal, adds it to
    the assumptions list, and records a trail callback to remove it on
    backtrack.
    """
    state = get_sat_state(trail)
    act = _fresh_sat_var(state)
    state.assumptions.append(act)
    trail.record(lambda: state.assumptions.remove(act))
```

---

## 8. Clause Addition

```python
def sat_add_clause(literals: list[int], trail: Trail) -> None:
    """Add a clause guarded by the current activation literal.

    If no activation scope is active, the clause is added unguarded
    (permanent).
    """
    state = get_sat_state(trail)
    if state.assumptions:
        act = state.assumptions[-1]
        state.solver.add_clause([-act] + literals)
    else:
        state.solver.add_clause(literals)
```

---

## 9. Satisfiability Check

```python
def sat_check(trail: Trail) -> bool:
    """Return True if current constraints are satisfiable."""
    state = get_sat_state(trail)
    return state.solver.solve(assumptions=state.assumptions)
```

---

## 10. Tests (Phase 1)

```python
class TestSATCoreInfrastructure:

    def test_var_mapping_bidirectional(self):
        trail = Trail()
        x = Var()
        state = get_sat_state(trail, 'cadical195')
        sat_x = sat_var_for(x, trail)
        assert sat_x > 0
        assert state.var_map[id(x)] == sat_x
        assert state.rev_map[sat_x] is x

    def test_var_mapping_idempotent(self):
        trail = Trail()
        x = Var()
        v1 = sat_var_for(x, trail)
        v2 = sat_var_for(x, trail)
        assert v1 == v2

    def test_ground_var_raises(self):
        trail = Trail()
        x = Var()
        unify(x, 1, trail)
        with pytest.raises(TypeError):
            sat_var_for(x, trail)

    def test_simple_sat(self):
        trail = Trail()
        x = Var()
        v = sat_var_for(x, trail)
        sat_add_clause([v], trail)       # unit clause: x must be True
        assert sat_check(trail)

    def test_simple_unsat(self):
        trail = Trail()
        x = Var()
        v = sat_var_for(x, trail)
        sat_add_clause([v], trail)       # x
        sat_add_clause([-v], trail)      # ~x
        assert not sat_check(trail)

    def test_backtracking_retracts_clauses(self):
        """Clauses added inside a scope become dormant after backtrack."""
        trail = Trail()
        x = Var()
        v = sat_var_for(x, trail)

        # Outer: x is unconstrained
        mark = trail.mark()
        sat_push(trail)
        sat_add_clause([v], trail)       # x (guarded by act)
        sat_add_clause([-v], trail)      # ~x (guarded by act)
        assert not sat_check(trail)      # UNSAT

        trail.undo(mark)                 # backtrack — activation lit removed
        assert sat_check(trail)          # SAT again (clauses dormant)

    def test_nested_backtracking(self):
        """Inner scope clauses retracted independently of outer."""
        trail = Trail()
        x, y = Var(), Var()
        vx = sat_var_for(x, trail)
        vy = sat_var_for(y, trail)

        sat_push(trail)
        sat_add_clause([vx], trail)      # x (scope 1)
        mark = trail.mark()

        sat_push(trail)
        sat_add_clause([-vx], trail)     # ~x (scope 2) — contradicts scope 1
        assert not sat_check(trail)

        trail.undo(mark)                 # retract scope 2
        assert sat_check(trail)          # scope 1 still active

    def test_solver_mismatch_raises(self):
        trail = Trail()
        get_sat_state(trail, 'cadical195')
        with pytest.raises(ValueError, match="mismatch"):
            get_sat_state(trail, 'glucose')

    def test_solver_cleanup_on_gc(self):
        import gc
        trail = Trail()
        state = get_sat_state(trail, 'cadical195')
        tid = id(trail)
        assert tid in _sat_states
        del trail
        gc.collect()
        assert tid not in _sat_states
```

---

## Implementation Order

1. Import guard + `_require_pysat()`
2. `SATVarInfo`, `SAT_KEY`
3. `SATState` + `_SOLVER_NAMES`
4. `get_sat_state()` + `_cleanup_sat_state()`
5. `sat_var_for()`
6. `_fresh_sat_var()`
7. `sat_push()`
8. `sat_add_clause()`
9. `sat_check()`
10. Tests
