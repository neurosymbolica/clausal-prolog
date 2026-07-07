"""clausal.logic.clportools_lp — OR-Tools LP/MIP backend.

Provides access to LP and mixed-integer programming solvers (GLOP, SCIP, CBC,
HiGHS, Gurobi, CPLEX, BOP, PDLP) through OR-Tools' pywraplp interface,
integrated with Clausal's trail-based backtracking via constraint-set rebuild.

Backtracking via constraint tagging + rebuild
---------------------------------------------
pywraplp solvers lack push/pop or reification.  Instead, each constraint is
tagged with a scope ID.  On solve, the model is rebuilt from scratch using
only constraints whose scope is active.

Lazy solver binding
-------------------
One LPState per Trail.  Variables can be registered before the solver is
chosen — the solver name is bound lazily when the first constraint block
(``ortools.glop(...)``, ``ortools.cbc(...)``, etc.) is posted.  Once bound,
switching solvers on the same trail raises ValueError.
"""

from __future__ import annotations

import weakref
from typing import Any

from clausal.logic.variables import (
    Var, Trail, deref, is_var, unify, put_attr,
)

# ── OR-Tools LP import guard ──────────────────────────────────────────────

try:
    from ortools.linear_solver import pywraplp as _pywraplp
    _HAS_LP = True
except ImportError:  # pragma: no cover
    _HAS_LP = False


def _require_lp() -> None:
    if not _HAS_LP:
        raise ImportError(
            "OR-Tools LP/MIP backend requires ortools: pip install ortools"
        )


# ── AST node imports ──────────────────────────────────────────────────────

from clausal.pythonic_ast.nodes import (
    Add as _Add,
    Sub as _Sub,
    Mult as _Mult,
    Negate as _Negate,
    ArithEq as _ArithEq,
    ArithNeq as _ArithNeq,
    Lt as _Lt,
    LtE as _LtE,
    Gt as _Gt,
    GtE as _GtE,
    CompareChain as _CompareChain,
)


# ── Constants ──────────────────────────────────────────────────────────────

LP_KEY = "lp"

# LP solvers express only non-strict inequalities (<=, >=), so a strict `<`/`>`
# is approximated by nudging the bound by this fixed absolute epsilon
# (`x < c` → `x <= c - _STRICT_INEQ_EPSILON`).  This is a documented
# approximation, not exact: it is too coarse for models whose feasible margin
# is below the epsilon (it can cut valid points) and negligible for
# large-magnitude models.  Prefer integer variables (where the caller can post
# the exact `<= c-1`) when strictness must be precise (A08-F017).
_STRICT_INEQ_EPSILON = 1e-6

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
    'highs_lp':  'HIGHS_LINEAR_PROGRAMMING',
    'gurobi_lp': 'GUROBI_LINEAR_PROGRAMMING',
    'cplex_lp':  'CPLEX_LINEAR_PROGRAMMING',
    'glpk':      'GLPK_LINEAR_PROGRAMMING',
    'glpk_mip':  'GLPK_MIXED_INTEGER_PROGRAMMING',
}


# ── LPVarInfo ─────────────────────────────────────────────────────────────

class LPVarInfo:
    """Attribute stored on a Clausal Var under key LP_KEY."""
    __slots__ = ('lp_var', 'kind')

    def __init__(self, lp_var, kind: str) -> None:
        self.lp_var = lp_var       # index into var_entries
        self.kind = kind           # 'continuous', 'integer'


# ── LPConstraintEntry ─────────────────────────────────────────────────────

class LPConstraintEntry:
    """A linear constraint tagged with its activation scope."""
    __slots__ = ('lower', 'upper', 'coeffs', 'scope_id')

    def __init__(self, lower: float, upper: float,
                 coeffs: list[tuple], scope_id: int) -> None:
        self.lower = lower
        self.upper = upper
        self.coeffs = coeffs       # list of (var_idx, coefficient)
        self.scope_id = scope_id


# ── LPState ───────────────────────────────────────────────────────────────

class LPState:
    """Per-query LP/MIP solver state, one instance per Trail.

    The solver_name may be None initially (variables registered before the
    solver is chosen) and is bound when the first constraint block is posted.
    """
    __slots__ = ('solver_name', 'var_entries', 'var_map', 'rev_map',
                 'constraints', 'active_scopes', '_scope_counter',
                 '_var_counter', 'objective', 'obj_sense')

    def __init__(self, solver_name: str | None = None) -> None:
        _require_lp()
        if solver_name is not None and solver_name not in _LP_SOLVER_IDS:
            raise ValueError(
                f"Unknown LP/MIP solver: {solver_name!r}. "
                f"Available: {sorted(_LP_SOLVER_IDS)}"
            )
        self.solver_name = solver_name
        self.var_entries: list[tuple] = []          # (name, lo, hi, kind)
        self.var_map: dict[int, int] = {}           # id(Var) -> var_entries index
        self.rev_map: dict[int, Any] = {}           # var_entries index -> Var
        self.constraints: list[LPConstraintEntry] = []
        self.active_scopes: set[int] = set()
        self._scope_counter: int = 0
        self._var_counter: int = 0
        self.objective: list[tuple] | None = None   # [(var_idx, coeff), ...]
        self.obj_sense: str | None = None           # 'min' or 'max'


# ── State registry ────────────────────────────────────────────────────────

_lp_states: dict[int, LPState] = {}


def get_lp_state(trail: Trail, solver_name: str | None = None) -> LPState:
    """Get or create the LPState for this trail.

    If solver_name is given and the state has no solver yet, binds it.
    If the state already has a different solver, raises ValueError.
    """
    tid = id(trail)
    state = _lp_states.get(tid)
    if state is not None:
        if solver_name is not None:
            if state.solver_name is None:
                # Bind the solver lazily
                if solver_name not in _LP_SOLVER_IDS:
                    raise ValueError(
                        f"Unknown LP/MIP solver: {solver_name!r}. "
                        f"Available: {sorted(_LP_SOLVER_IDS)}"
                    )
                state.solver_name = solver_name
            elif state.solver_name != solver_name:
                raise ValueError(
                    f"LP solver mismatch: trail already using "
                    f"{state.solver_name!r}, cannot switch to {solver_name!r}"
                )
        return state
    state = LPState(solver_name)
    _lp_states[tid] = state
    weakref.finalize(trail, _cleanup_lp_state, tid)
    return state


def _cleanup_lp_state(tid: int) -> None:
    _lp_states.pop(tid, None)


def _get_existing_lp_state(trail: Trail) -> LPState:
    """Get the existing LPState for this trail (must already exist)."""
    state = _lp_states.get(id(trail))
    if state is None:
        raise ValueError("No LP state for this trail — register a variable first")
    return state


# ── Variable registration ─────────────────────────────────────────────────

def lp_var(var: Var, lo: float, hi: float, trail: Trail,
           solver_name: str | None = None) -> int:
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
               solver_name: str | None = None) -> int:
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


def lp_bool_var(var: Var, trail: Trail, solver_name: str | None = None) -> int:
    """Register a Boolean LP/MIP variable."""
    return lp_int_var(var, 0, 1, trail, solver_name)


# ── Scope management ──────────────────────────────────────────────────────

def lp_push(trail: Trail, solver_name: str | None = None) -> None:
    """Create a new constraint scope."""
    state = get_lp_state(trail, solver_name)
    state._scope_counter += 1
    scope_id = state._scope_counter
    state.active_scopes.add(scope_id)
    trail.record(lambda: state.active_scopes.discard(scope_id))


# ── _as_list helper ────────────────────────────────────────────────────────

def _as_list(val: Any) -> list:
    """Coerce a Clausal term to a Python list."""
    val = deref(val)
    if isinstance(val, list):
        return val
    if isinstance(val, tuple):
        return list(val)
    if is_var(val) or isinstance(val, (int, float)):
        return [val]
    try:
        from clausal.terms import cons_to_list
        return cons_to_list(val)
    except (ValueError, TypeError, ImportError):
        raise TypeError(
            f"Expected a list, got {type(val).__name__!r}: {val!r}"
        )


# ── Expression translation (linear) ───────────────────────────────────────

def clausal_to_lp_coeffs(expr: Any, trail: Trail) -> dict[int, float]:
    """Translate a Clausal expression to LP coefficient dict.

    Returns {var_idx: coefficient, ...} with key -1 for the constant term.
    Only linear expressions are supported.
    """
    expr = deref(expr)
    state = _get_existing_lp_state(trail)

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
        left_vars = {k: v for k, v in left.items() if k != -1}
        right_vars = {k: v for k, v in right.items() if k != -1}
        if left_vars and right_vars:
            raise TypeError("LP constraints must be linear: x * y is not allowed")
        if not left_vars:
            c = left.get(-1, 0.0)
            return {k: v * c for k, v in right.items()}
        else:
            c = right.get(-1, 0.0)
            return {k: v * c for k, v in left.items()}

    if isinstance(expr, _Negate):
        inner = clausal_to_lp_coeffs(expr.operand, trail)
        return {k: -v for k, v in inner.items()}

    raise TypeError(f"Cannot translate {type(expr).__name__} to LP expression")


# ── Constraint translation ────────────────────────────────────────────────

def _translate_lp_constraint(expr: Any, trail: Trail) -> LPConstraintEntry:
    """Translate a comparison expression to an LPConstraintEntry."""
    expr = deref(expr)
    state = _get_existing_lp_state(trail)
    scope_id = max(state.active_scopes) if state.active_scopes else 0
    INF = float('inf')

    if isinstance(expr, _ArithEq):
        diff = clausal_to_lp_coeffs(_Sub(left=expr.left, right=expr.right), trail)
        const = diff.pop(-1, 0.0)
        return LPConstraintEntry(-const, -const, list(diff.items()), scope_id)

    if isinstance(expr, _LtE):
        diff = clausal_to_lp_coeffs(_Sub(left=expr.left, right=expr.right), trail)
        const = diff.pop(-1, 0.0)
        return LPConstraintEntry(-INF, -const, list(diff.items()), scope_id)

    if isinstance(expr, _GtE):
        diff = clausal_to_lp_coeffs(_Sub(left=expr.left, right=expr.right), trail)
        const = diff.pop(-1, 0.0)
        return LPConstraintEntry(-const, INF, list(diff.items()), scope_id)

    if isinstance(expr, _Lt):
        diff = clausal_to_lp_coeffs(_Sub(left=expr.left, right=expr.right), trail)
        const = diff.pop(-1, 0.0)
        return LPConstraintEntry(-INF, -const - _STRICT_INEQ_EPSILON,
                                 list(diff.items()), scope_id)

    if isinstance(expr, _Gt):
        diff = clausal_to_lp_coeffs(_Sub(left=expr.left, right=expr.right), trail)
        const = diff.pop(-1, 0.0)
        return LPConstraintEntry(-const + _STRICT_INEQ_EPSILON, INF,
                                 list(diff.items()), scope_id)

    if isinstance(expr, _ArithNeq):
        raise TypeError(
            "LP cannot express `!=`: a linear program's feasible region is "
            "convex, so a strict disequality (a non-convex hole) has no LP "
            "encoding.  Use two disjunctive `<`/`>` constraints across separate "
            "solves, or an integer/CP model (clportools) instead."
        )

    if isinstance(expr, _CompareChain):
        raise TypeError("LP does not support chained comparisons directly")

    raise TypeError(f"Cannot translate {type(expr).__name__} to LP constraint")


# ── Constraint block ──────────────────────────────────────────────────────

def lp_constraint_block(constraint_set: Any, solver_name: str,
                        trail: Trail) -> bool:
    """Post a block of linear constraints."""
    state = get_lp_state(trail, solver_name)
    constraint_set = deref(constraint_set)
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


# ── Model rebuild and solve ───────────────────────────────────────────────

def _rebuild_and_solve(state: LPState) -> tuple:
    """Rebuild the LP/MIP model from active constraints and solve.

    Returns (status, solver, lp_vars).
    """
    if state.solver_name is None:
        raise ValueError(
            "No LP/MIP solver specified — post constraints via "
            "ortools.glop/cbc/scip/highs/... first"
        )
    sid_str = _LP_SOLVER_IDS[state.solver_name]
    solver = _pywraplp.Solver.CreateSolver(sid_str)
    if solver is None:
        raise RuntimeError(
            f"LP solver {state.solver_name!r} not available. "
            f"Check ortools installation."
        )

    lp_vars = []
    for name, lo, hi, kind in state.var_entries:
        if kind == 'continuous':
            lp_vars.append(solver.NumVar(lo, hi, name))
        elif kind == 'integer':
            lp_vars.append(solver.IntVar(lo, hi, name))
        else:
            raise ValueError(f"Unknown var kind: {kind}")

    for ct in state.constraints:
        if ct.scope_id in state.active_scopes or ct.scope_id == 0:
            constraint = solver.Constraint(ct.lower, ct.upper)
            for var_idx, coeff in ct.coeffs:
                constraint.SetCoefficient(lp_vars[var_idx], coeff)

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
    state = _get_existing_lp_state(trail)
    status, _, _ = _rebuild_and_solve(state)
    return status in (_pywraplp.Solver.OPTIMAL, _pywraplp.Solver.FEASIBLE)


# ── Solve and bind ────────────────────────────────────────────────────────

def lp_solve(vars_list: Any, trail: Trail):
    """Solve the LP/MIP and bind Clausal variables to their values.

    Generator: yields once on success.
    """
    state = _get_existing_lp_state(trail)
    status, solver, lp_vars = _rebuild_and_solve(state)

    if status not in (_pywraplp.Solver.OPTIMAL, _pywraplp.Solver.FEASIBLE):
        return

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
            kind = state.var_entries[idx][3]
            if kind == 'integer':
                value = int(round(value))
            if not unify(v, value, trail):
                ok = False
                break

    if ok:
        yield None
    trail.undo(mark)


# ── Optimization ──────────────────────────────────────────────────────────

def lp_minimize(expr: Any, val: Any, trail: Trail):
    """Minimize a linear objective and unify val with the optimal value."""
    state = _get_existing_lp_state(trail)
    coeffs = clausal_to_lp_coeffs(expr, trail)
    const = coeffs.pop(-1, 0.0)
    state.objective = list(coeffs.items())
    state.obj_sense = 'min'

    status, solver, lp_vars = _rebuild_and_solve(state)

    if status in (_pywraplp.Solver.OPTIMAL, _pywraplp.Solver.FEASIBLE):
        obj_val = solver.Objective().Value() + const
        mark = trail.mark()
        # Honour unify results: a registered var already bound to a conflicting
        # value (no LP attr hook, A08-F013) must not yield an inconsistent
        # "optimal" solution (A08-F016).
        ok = True
        for idx, clausal_var in state.rev_map.items():
            value = lp_vars[idx].solution_value()
            kind = state.var_entries[idx][3]
            if kind == 'integer':
                value = int(round(value))
            if not unify(clausal_var, value, trail):
                ok = False
                break
        if ok and unify(val, obj_val, trail):
            yield None
        trail.undo(mark)


def lp_maximize(expr: Any, val: Any, trail: Trail):
    """Maximize a linear objective and unify val with the optimal value."""
    state = _get_existing_lp_state(trail)
    coeffs = clausal_to_lp_coeffs(expr, trail)
    const = coeffs.pop(-1, 0.0)
    state.objective = list(coeffs.items())
    state.obj_sense = 'max'

    status, solver, lp_vars = _rebuild_and_solve(state)

    if status in (_pywraplp.Solver.OPTIMAL, _pywraplp.Solver.FEASIBLE):
        obj_val = solver.Objective().Value() + const
        mark = trail.mark()
        # Honour unify results: a registered var already bound to a conflicting
        # value (no LP attr hook, A08-F013) must not yield an inconsistent
        # "optimal" solution (A08-F016).
        ok = True
        for idx, clausal_var in state.rev_map.items():
            value = lp_vars[idx].solution_value()
            kind = state.var_entries[idx][3]
            if kind == 'integer':
                value = int(round(value))
            if not unify(clausal_var, value, trail):
                ok = False
                break
        if ok and unify(val, obj_val, trail):
            yield None
        trail.undo(mark)
