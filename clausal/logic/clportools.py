"""clausal.logic.clportools — Google OR-Tools CP-SAT backend.

Provides access to Google's CP-SAT solver (constraint programming with SAT)
through OR-Tools, integrated with Clausal's trail-based backtracking via
OnlyEnforceIf activation literals.

Variable mapping
----------------
Each Clausal Var that participates in CP-SAT constraints gets an IntVar or
BoolVar, stored in three places:

  - CPSATState.var_map   id(Var) → IntVar|BoolVar   (for fast lookup)
  - CPSATState.rev_map   var index → Var             (for model extraction)
  - Var attribute         OR_KEY → ORVarInfo          (trail-safe)

Backtracking via OnlyEnforceIf
------------------------------
CP-SAT natively supports reification.  Each scope creates a fresh BoolVar as
an activation literal.  Constraints are guarded via OnlyEnforceIf::

    or_push(trail)
    # constraint x + y <= 10 becomes: Add(x + y <= 10).OnlyEnforceIf(act)
    or_add_constraint(cpsat_x + cpsat_y <= 10, trail)
    # on backtrack: act removed from assumptions → constraint dormant

Before each solve, all active activation literals are assumed True via
AddAssumptions.

State lifecycle
---------------
One CPSATState per Trail (keyed by id(trail) in a module-level dict).
Cleaned up automatically when the Trail is garbage-collected via weakref.

Import guard
------------
All ortools usage is conditional; Clausal works fine without ortools installed.
"""

from __future__ import annotations

import weakref
from typing import Any

from clausal.logic.variables import (
    Var, Trail, deref, is_var, unify, put_attr,
)

# ── OR-Tools import guard ──────────────────────────────────────────────────

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
except ImportError:  # pragma: no cover
    _HAS_ORTOOLS = False
    # _SolutionCounter subclasses this at import time; any use goes through
    # get_cpsat_state, which calls _require_ortools first.
    _CpSolverSolutionCallback = object


def _require_ortools() -> None:
    if not _HAS_ORTOOLS:
        raise ImportError(
            "OR-Tools backend requires the ortools package: "
            "pip install ortools"
        )


# ── AST node imports (for expression translation) ─────────────────────────

from clausal.pythonic_ast.nodes import (
    # Arithmetic
    Add as _Add,
    Sub as _Sub,
    Mult as _Mult,
    FloorDiv as _FloorDiv,
    Mod as _Mod,
    Negate as _Negate,
    # Bitwise / Boolean
    BitAnd as _BitAnd,
    BitOr as _BitOr,
    BitXor as _BitXor,
    Invert as _Invert,
    # Logical
    And as _And,
    Or as _Or,
    Not as _Not,
    # Comparison
    ArithEq as _ArithEq,
    ArithNeq as _ArithNeq,
    Lt as _Lt,
    LtE as _LtE,
    Gt as _Gt,
    GtE as _GtE,
    CompareChain as _CompareChain,
)


# ── Constants ──────────────────────────────────────────────────────────────

OR_KEY = "or"  # attribute key on Clausal Vars


# ── ORVarInfo — attribute stored on a Var ──────────────────────────────────

class ORVarInfo:
    """Attribute value stored on a Clausal Var under key OR_KEY.

    Stores the corresponding CP-SAT variable and its kind.
    Trail-safe: put_attr records the old value so backtracking restores it.
    """
    __slots__ = ('cpsat_var', 'kind')

    def __init__(self, cpsat_var, kind: str) -> None:
        self.cpsat_var = cpsat_var   # IntVar or BoolVar from CpModel
        self.kind = kind             # 'int' or 'bool'


# ── CPSATState — per-Trail solver state ────────────────────────────────────

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
        self.rev_map: dict[int, Any] = {}        # cpsat var index -> Var
        self.active_lits: list[Any] = []         # active activation BoolVars
        self._int_counter: int = 0               # unique name counter
        self._bool_counter: int = 0
        self._interval_counter: int = 0
        self._interval_map: dict[int, Any] = {}  # id(Var) -> IntervalVar


# ── State registry ─────────────────────────────────────────────────────────

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


# ── Variable registration (integer) ───────────────────────────────────────

def or_var_for(var: Var, lo: int, hi: int, trail: Trail) -> Any:
    """Get or create a CP-SAT IntVar for a Clausal Var.

    Returns the CpModel IntVar.  If the Var already has a CP-SAT variable,
    returns the existing one (domain was set at creation; use additional
    constraints to narrow it further).
    """
    var = deref(var)
    if not is_var(var):
        raise TypeError(
            f"or_var_for: expected unbound Var, got {type(var).__name__}"
        )

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


# ── Variable registration (sparse domain) ─────────────────────────────────

def or_var_from_domain(var: Var, values: list[int], trail: Trail) -> Any:
    """Create a CP-SAT IntVar with a sparse domain."""
    var = deref(var)
    if not is_var(var):
        raise TypeError(
            f"or_var_from_domain: expected unbound Var, "
            f"got {type(var).__name__}"
        )

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


# ── Variable registration (Boolean) ───────────────────────────────────────

def or_bool_for(var: Var, trail: Trail) -> Any:
    """Get or create a CP-SAT BoolVar for a Clausal Var."""
    var = deref(var)
    if not is_var(var):
        raise TypeError(
            f"or_bool_for: expected unbound Var, got {type(var).__name__}"
        )

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


# ── Fresh activation literal ──────────────────────────────────────────────

def _fresh_act_lit(state: CPSATState) -> Any:
    """Allocate a fresh BoolVar for use as an activation literal.

    Not mapped to any Clausal Var.  Used only for OnlyEnforceIf scoping.
    """
    state._bool_counter += 1
    return state.model.NewBoolVar(f'_act_{state._bool_counter}')


# ── Activation literal scope management ───────────────────────────────────

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


# ── Constraint addition ───────────────────────────────────────────────────

def or_add_constraint(constraint_expr, trail: Trail) -> None:
    """Add a CP-SAT constraint guarded by the current activation literal.

    ``constraint_expr`` is a BoundedLinearExpression (the argument to
    model.Add()), e.g. ``cpsat_x + cpsat_y <= 10``.

    If no activation scope is active, the constraint is added unguarded.
    """
    state = get_cpsat_state(trail)
    ct = state.model.Add(constraint_expr)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])


# ── Apply assumptions ─────────────────────────────────────────────────────

def _apply_assumptions(state: CPSATState) -> None:
    """Fix all active activation literals to True via model assumptions.

    Must be called before every solver.Solve() call.
    """
    state.model.ClearAssumptions()
    if state.active_lits:
        state.model.AddAssumptions(state.active_lits)


# ── Satisfiability check ──────────────────────────────────────────────────

def or_check(trail: Trail) -> bool:
    """Return True if current constraints are satisfiable."""
    state = get_cpsat_state(trail)
    _apply_assumptions(state)
    status = state.solver.Solve(state.model)
    return status in (_OPTIMAL, _FEASIBLE)


# ── _as_list helper ────────────────────────────────────────────────────────

def _as_list(val: Any) -> list:
    """Coerce a Clausal term to a Python list."""
    val = deref(val)
    if isinstance(val, list):
        return val
    if isinstance(val, tuple):
        return list(val)
    if is_var(val) or isinstance(val, int):
        return [val]
    raise TypeError(
        f"Expected a list, got {type(val).__name__!r}: {val!r}"
    )


# ── _to_cpsat helper ──────────────────────────────────────────────────────

def _to_cpsat(expr: Any, trail: Trail) -> Any:
    """Convert a single Var or int to CP-SAT variable/constant."""
    expr = deref(expr)
    if is_var(expr):
        state = get_cpsat_state(trail)
        cv = state.var_map.get(id(expr))
        if cv is None:
            raise ValueError("Variable not registered with CP-SAT")
        return cv
    if isinstance(expr, int):
        return expr
    raise TypeError(f"Expected Var or int, got {type(expr).__name__}")


def _to_cpsat_bool(expr: Any, trail: Trail) -> Any:
    """Convert a Var or literal to a CP-SAT BoolVar or its negation."""
    expr = deref(expr)
    if isinstance(expr, _Invert):
        inner = _to_cpsat_bool(expr.operand, trail)
        return inner.Not()
    if is_var(expr):
        return or_bool_for(expr, trail)
    if isinstance(expr, (bool, int)):
        state = get_cpsat_state(trail)
        state._bool_counter += 1
        bv = state.model.NewBoolVar(f'_const_{state._bool_counter}')
        state.model.Add(bv == int(bool(expr)))
        return bv
    raise TypeError(f"Expected Boolean Var or literal, got {type(expr).__name__}")


# ══════════════════════════════════════════════════════════════════════════
# Phase 2: Domain declarations, expression translation, constraints, labeling
# ══════════════════════════════════════════════════════════════════════════

# ── Domain declaration ─────────────────────────────────────────────────────

def or_in(var: Var, lo_or_values, hi=None, trail: Trail = None) -> bool:
    """Declare an integer variable with a domain.

    or_in(X, 1, 9, trail)         -> IntVar [1, 9]
    or_in(X, [1, 3, 5], trail=trail)   -> IntVar with sparse domain
    """
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"or_in: expected unbound Var, got {type(var).__name__}")

    state = get_cpsat_state(trail)
    vid = id(var)

    if hi is not None:
        lo, hi = int(lo_or_values), int(hi)
        existing = state.var_map.get(vid)
        if existing is not None:
            or_push(trail)
            or_add_constraint(existing >= lo, trail)
            or_add_constraint(existing <= hi, trail)
            return True
        or_var_for(var, lo, hi, trail)
        return True
    else:
        values = [int(v) for v in lo_or_values]
        existing = state.var_map.get(vid)
        if existing is not None:
            or_push(trail)
            ct = state.model.AddAllowedAssignments([existing], [[v] for v in values])
            if state.active_lits:
                ct.OnlyEnforceIf(state.active_lits[-1])
            return True
        or_var_from_domain(var, values, trail)
        return True


def or_bool(var: Var, trail: Trail) -> bool:
    """Declare a Boolean variable (domain {0, 1})."""
    or_bool_for(var, trail)
    return True


# ── Expression translation ─────────────────────────────────────────────────

def clausal_to_cpsat(expr: Any, trail: Trail) -> Any:
    """Translate a Clausal expression to a CP-SAT IntVar / LinearExpr."""
    expr = deref(expr)

    if is_var(expr):
        state = get_cpsat_state(trail)
        vid = id(expr)
        cpsat_var = state.var_map.get(vid)
        if cpsat_var is not None:
            return cpsat_var
        raise ValueError(
            "Variable not registered with CP-SAT. "
            "Call ortools.cpsat.in(Var, Lo, Hi) first."
        )

    if isinstance(expr, (int, float)):
        return int(expr)

    if isinstance(expr, _Add):
        return clausal_to_cpsat(expr.left, trail) + clausal_to_cpsat(expr.right, trail)

    if isinstance(expr, _Sub):
        return clausal_to_cpsat(expr.left, trail) - clausal_to_cpsat(expr.right, trail)

    if isinstance(expr, _Mult):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        if isinstance(left, int) or isinstance(right, int):
            return left * right
        state = get_cpsat_state(trail)
        state._int_counter += 1
        prod = state.model.NewIntVar(-10**9, 10**9, f'_prod_{state._int_counter}')
        state.model.AddMultiplicationEquality(prod, [left, right])
        return prod

    if isinstance(expr, _FloorDiv):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        state = get_cpsat_state(trail)
        state._int_counter += 1
        quot = state.model.NewIntVar(-10**9, 10**9, f'_div_{state._int_counter}')
        state.model.AddDivisionEquality(quot, left, right)
        return quot

    if isinstance(expr, _Mod):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        state = get_cpsat_state(trail)
        state._int_counter += 1
        rem = state.model.NewIntVar(0, 10**9, f'_mod_{state._int_counter}')
        state.model.AddModuloEquality(rem, left, right)
        return rem

    if isinstance(expr, _Negate):
        return -clausal_to_cpsat(expr.operand, trail)

    raise TypeError(f"Cannot translate {type(expr).__name__} to CP-SAT expression")


# ── Comparison translation ─────────────────────────────────────────────────

def clausal_to_cpsat_constraint(expr: Any, trail: Trail) -> Any:
    """Translate a Clausal comparison to a CP-SAT BoundedLinearExpression."""
    expr = deref(expr)

    if isinstance(expr, _ArithEq):
        return clausal_to_cpsat(expr.left, trail) == clausal_to_cpsat(expr.right, trail)

    if isinstance(expr, _ArithNeq):
        return clausal_to_cpsat(expr.left, trail) != clausal_to_cpsat(expr.right, trail)

    if isinstance(expr, _Lt):
        return clausal_to_cpsat(expr.left, trail) < clausal_to_cpsat(expr.right, trail)

    if isinstance(expr, _LtE):
        return clausal_to_cpsat(expr.left, trail) <= clausal_to_cpsat(expr.right, trail)

    if isinstance(expr, _Gt):
        return clausal_to_cpsat(expr.left, trail) > clausal_to_cpsat(expr.right, trail)

    if isinstance(expr, _GtE):
        return clausal_to_cpsat(expr.left, trail) >= clausal_to_cpsat(expr.right, trail)

    if isinstance(expr, _CompareChain):
        # Chained comparisons: 1 < X < 10 → [Lt(1, X), Lt(X, 10)]
        # Return list; caller must add each individually
        return [clausal_to_cpsat_constraint(cmp, trail) for cmp in expr.comparisons]

    raise TypeError(f"Cannot translate {type(expr).__name__} to CP-SAT constraint")


# ── Constraint block ───────────────────────────────────────────────────────

def or_constraint_block(constraint_set: Any, trail: Trail) -> bool:
    """Walk constraint elements and post each as CP-SAT constraints.

    Each element in the tuple/list is a comparison expression.
    All constraints are guarded by a single activation literal for this block.
    """
    constraint_set = deref(constraint_set)
    if isinstance(constraint_set, (list, tuple)):
        elements = constraint_set
    else:
        elements = [constraint_set]

    or_push(trail)

    for elem in elements:
        elem = deref(elem)
        ct_expr = clausal_to_cpsat_constraint(elem, trail)
        if isinstance(ct_expr, list):
            for sub in ct_expr:
                or_add_constraint(sub, trail)
        else:
            or_add_constraint(ct_expr, trail)

    return True


# ── All-different ──────────────────────────────────────────────────────────

def or_all_different(vars_list: Any, trail: Trail) -> bool:
    """Post an all-different constraint."""
    state = get_cpsat_state(trail)
    items = _as_list(vars_list)
    cpsat_vars = []
    for v in items:
        v = deref(v)
        if is_var(v):
            cv = state.var_map.get(id(v))
            if cv is None:
                raise ValueError("or_all_different: variable not registered")
            cpsat_vars.append(cv)
        elif isinstance(v, int):
            cpsat_vars.append(v)
        else:
            raise TypeError(
                f"or_all_different: expected Var or int, got {type(v).__name__}"
            )

    ct = state.model.AddAllDifferent(cpsat_vars)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


# ── Element constraint ─────────────────────────────────────────────────────

def or_element(index: Any, array: Any, target: Any, trail: Trail) -> bool:
    """Post element constraint: array[index] == target."""
    state = get_cpsat_state(trail)
    idx_cpsat = _to_cpsat(index, trail)
    tgt_cpsat = _to_cpsat(target, trail)
    arr_cpsat = [_to_cpsat(v, trail) for v in _as_list(array)]
    ct = state.model.AddElement(idx_cpsat, arr_cpsat, tgt_cpsat)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


# ── Boolean constraints ────────────────────────────────────────────────────

def or_bool_or(literals: Any, trail: Trail) -> bool:
    """Post Boolean OR: at least one literal is True."""
    state = get_cpsat_state(trail)
    cpsat_lits = [_to_cpsat_bool(lit, trail) for lit in _as_list(literals)]
    ct = state.model.AddBoolOr(cpsat_lits)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


def or_bool_and(literals: Any, trail: Trail) -> bool:
    """Post Boolean AND: all literals are True."""
    state = get_cpsat_state(trail)
    cpsat_lits = [_to_cpsat_bool(lit, trail) for lit in _as_list(literals)]
    ct = state.model.AddBoolAnd(cpsat_lits)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


def or_implication(a: Any, b: Any, trail: Trail) -> bool:
    """Post implication: a => b."""
    state = get_cpsat_state(trail)
    a_cpsat = _to_cpsat_bool(a, trail)
    b_cpsat = _to_cpsat_bool(b, trail)
    ct = state.model.AddImplication(a_cpsat, b_cpsat)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


def or_exactly_one(literals: Any, trail: Trail) -> bool:
    """Post exactly-one constraint."""
    state = get_cpsat_state(trail)
    cpsat_lits = [_to_cpsat_bool(lit, trail) for lit in _as_list(literals)]
    ct = state.model.AddExactlyOne(cpsat_lits)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


def or_at_most_one(literals: Any, trail: Trail) -> bool:
    """Post at-most-one constraint."""
    state = get_cpsat_state(trail)
    cpsat_lits = [_to_cpsat_bool(lit, trail) for lit in _as_list(literals)]
    ct = state.model.AddAtMostOne(cpsat_lits)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


def or_at_least_one(literals: Any, trail: Trail) -> bool:
    """Post at-least-one constraint."""
    state = get_cpsat_state(trail)
    cpsat_lits = [_to_cpsat_bool(lit, trail) for lit in _as_list(literals)]
    ct = state.model.AddAtLeastOne(cpsat_lits)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


# ── Labeling (solution enumeration) ───────────────────────────────────────

def label_or(vars_list: Any, trail: Trail):
    """Enumerate satisfying integer assignments for CP-SAT variables.

    Generator: yields None for each solution, with Clausal vars bound.
    Bindings are undone between solutions.
    """
    state = get_cpsat_state(trail)
    items = _as_list(vars_list)

    cpsat_vars: list = []
    clausal_vars: list[Var] = []

    for v in items:
        v = deref(v)
        if is_var(v):
            cv = state.var_map.get(id(v))
            if cv is None:
                raise ValueError(
                    "label_or: variable not registered with CP-SAT. "
                    "Post a constraint first (ortools.cpsat.in)."
                )
            cpsat_vars.append(cv)
            clausal_vars.append(v)
        elif isinstance(v, int):
            pass  # already ground
        else:
            raise TypeError(f"label_or: expected int or Var, got {type(v).__name__}")

    if not cpsat_vars:
        if or_check(trail):
            yield None
        return

    # Create a scope for blocking clauses so they're retracted when
    # the generator is done or the caller backtracks past this point
    label_act = _fresh_act_lit(state)
    state.active_lits.append(label_act)

    try:
        while True:
            _apply_assumptions(state)
            status = state.solver.Solve(state.model)
            if status not in (_OPTIMAL, _FEASIBLE):
                return

            values = [state.solver.Value(cv) for cv in cpsat_vars]

            mark = trail.mark()
            ok = all(unify(cv, val, trail)
                     for cv, val in zip(clausal_vars, values))

            if ok:
                yield None

            trail.undo(mark)

            # Block this assignment (guarded by label_act)
            blocking_literals = []
            for cv, val in zip(cpsat_vars, values):
                state._bool_counter += 1
                b = state.model.NewBoolVar(f'_blk_{state._bool_counter}')
                state.model.Add(cv != val).OnlyEnforceIf(b)
                state.model.Add(cv == val).OnlyEnforceIf(b.Not())
                blocking_literals.append(b)
            ct = state.model.AddBoolOr(blocking_literals)
            ct.OnlyEnforceIf(label_act)
    finally:
        if label_act in state.active_lits:
            state.active_lits.remove(label_act)


# ── Solution counting ──────────────────────────────────────────────────────

class _SolutionCounter(_CpSolverSolutionCallback):
    def __init__(self):
        super().__init__()
        self.count = 0

    def on_solution_callback(self):
        self.count += 1


def or_count(vars_list: Any, trail: Trail) -> int:
    """Count solutions using CP-SAT's native callback."""
    state = get_cpsat_state(trail)
    _apply_assumptions(state)
    counter = _SolutionCounter()
    state.solver.parameters.enumerate_all_solutions = True
    state.solver.Solve(state.model, counter)
    state.solver.parameters.enumerate_all_solutions = False
    return counter.count


# ══════════════════════════════════════════════════════════════════════════
# Phase 3: Scheduling constraints (intervals, no-overlap, cumulative)
# ══════════════════════════════════════════════════════════════════════════

def or_interval(start: Any, size: Any, end: Any, trail: Trail) -> Any:
    """Create an IntervalVar: start + size == end."""
    state = get_cpsat_state(trail)
    start_cp = _to_cpsat(start, trail)
    end_cp = _to_cpsat(end, trail)
    size_d = deref(size)
    size_cp = int(size_d) if isinstance(size_d, int) else _to_cpsat(size, trail)
    state._interval_counter += 1
    return state.model.NewIntervalVar(start_cp, size_cp, end_cp,
                                      f'iv_{state._interval_counter}')


def or_optional_interval(start: Any, size: Any, end: Any,
                         presence: Any, trail: Trail) -> Any:
    """Create an optional IntervalVar that exists only when presence is True."""
    state = get_cpsat_state(trail)
    start_cp = _to_cpsat(start, trail)
    end_cp = _to_cpsat(end, trail)
    presence_cp = _to_cpsat_bool(presence, trail)
    size_d = deref(size)
    size_cp = int(size_d) if isinstance(size_d, int) else _to_cpsat(size, trail)
    state._interval_counter += 1
    return state.model.NewOptionalIntervalVar(
        start_cp, size_cp, end_cp, presence_cp,
        f'oiv_{state._interval_counter}'
    )


def or_interval_scoped(start: Any, size: Any, end: Any, trail: Trail) -> Any:
    """Create a trail-scoped interval using optional interval + activation lit."""
    state = get_cpsat_state(trail)
    if not state.active_lits:
        return or_interval(start, size, end, trail)

    act = state.active_lits[-1]
    start_cp = _to_cpsat(start, trail)
    end_cp = _to_cpsat(end, trail)
    size_d = deref(size)
    size_cp = int(size_d) if isinstance(size_d, int) else _to_cpsat(size, trail)
    state._interval_counter += 1
    return state.model.NewOptionalIntervalVar(
        start_cp, size_cp, end_cp, act,
        f'siv_{state._interval_counter}'
    )


def or_fixed_interval(start: Any, size: int, trail: Trail) -> tuple:
    """Create an interval with a fixed size, auto-creating the end variable.

    Returns (IntervalVar, end_cpsat_var).
    """
    state = get_cpsat_state(trail)
    start_cp = _to_cpsat(start, trail)
    size = int(size)
    state._int_counter += 1
    end_cp = state.model.NewIntVar(0, 10**6, f'_end_{state._int_counter}')
    state._interval_counter += 1
    iv = state.model.NewIntervalVar(start_cp, size, end_cp,
                                    f'fiv_{state._interval_counter}')
    return iv, end_cp


def or_no_overlap(intervals: list, trail: Trail) -> bool:
    """Post a no-overlap constraint: intervals must not overlap in time."""
    state = get_cpsat_state(trail)
    state.model.AddNoOverlap(intervals)
    return True


def or_no_overlap_2d(x_intervals: list, y_intervals: list, trail: Trail) -> bool:
    """Post a 2D no-overlap constraint for rectangle packing."""
    state = get_cpsat_state(trail)
    if len(x_intervals) != len(y_intervals):
        raise ValueError(
            "or_no_overlap_2d: x and y interval lists must have same length"
        )
    state.model.AddNoOverlap2D(x_intervals, y_intervals)
    return True


def or_cumulative(intervals: list, demands: list, capacity: Any,
                  trail: Trail) -> bool:
    """Post a cumulative resource constraint."""
    state = get_cpsat_state(trail)
    demands_cp = []
    for d in demands:
        d = deref(d)
        if isinstance(d, int):
            demands_cp.append(d)
        elif is_var(d):
            demands_cp.append(_to_cpsat(d, trail))
        else:
            raise TypeError(
                f"or_cumulative: demand must be int or Var, got {type(d).__name__}"
            )
    capacity = deref(capacity)
    if isinstance(capacity, int):
        cap_cp = capacity
    elif is_var(capacity):
        cap_cp = _to_cpsat(capacity, trail)
    else:
        raise TypeError("or_cumulative: capacity must be int or Var")
    state.model.AddCumulative(intervals, demands_cp, cap_cp)
    return True


def _intervals_from_clausal(interval_terms: list, trail: Trail) -> list:
    """Convert a list of Clausal interval terms to CP-SAT IntervalVars."""
    result = []
    for term in interval_terms:
        term = deref(term)
        if type(term) is tuple and len(term) == 4 and term[0] == 'interval':
            start, size, end = term[1:]
            iv = or_interval_scoped(start, size, end, trail)
            result.append(iv)
        elif type(term) is tuple and len(term) == 5 and term[0] == 'optional_interval':
            start, size, end, presence = term[1:]
            iv = or_optional_interval(start, size, end, presence, trail)
            result.append(iv)
        else:
            raise TypeError(f"Expected interval/3 or optional_interval/4 term, got {term}")
    return result


# ══════════════════════════════════════════════════════════════════════════
# Phase 4: Advanced constraints + optimization
# ══════════════════════════════════════════════════════════════════════════

def or_circuit(arcs: list, trail: Trail) -> bool:
    """Post a Hamiltonian circuit constraint.

    arcs: list of (tail, head, literal) triples.
    """
    state = get_cpsat_state(trail)
    cpsat_arcs = []
    for arc in arcs:
        arc = deref(arc)
        if isinstance(arc, (list, tuple)) and len(arc) == 3:
            tail, head, lit = arc
        elif type(arc) is tuple and len(arc) == 4 and arc[0] == 'arc':
            tail, head, lit = arc[1:]
        else:
            raise TypeError(f"Expected arc(Tail, Head, Lit), got {arc}")
        cpsat_arcs.append((int(deref(tail)), int(deref(head)),
                           _to_cpsat_bool(lit, trail)))

    state.model.AddCircuit(cpsat_arcs)
    return True


def or_table(vars_list: Any, tuples_list: Any, trail: Trail) -> bool:
    """Post a table (extensional) constraint — allowed assignments."""
    state = get_cpsat_state(trail)
    cpsat_vars = [_to_cpsat(v, trail) for v in _as_list(vars_list)]
    tuples = []
    for t in tuples_list:
        t = deref(t)
        row = [int(deref(v)) for v in (t if isinstance(t, (list, tuple)) else [t])]
        tuples.append(row)
    ct = state.model.AddAllowedAssignments(cpsat_vars, tuples)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


def or_forbidden(vars_list: Any, tuples_list: Any, trail: Trail) -> bool:
    """Post a forbidden-assignments constraint (negated table)."""
    state = get_cpsat_state(trail)
    cpsat_vars = [_to_cpsat(v, trail) for v in _as_list(vars_list)]
    tuples = []
    for t in tuples_list:
        t = deref(t)
        row = [int(deref(v)) for v in (t if isinstance(t, (list, tuple)) else [t])]
        tuples.append(row)
    ct = state.model.AddForbiddenAssignments(cpsat_vars, tuples)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


def or_inverse(vars1: Any, vars2: Any, trail: Trail) -> bool:
    """Post inverse constraint: vars1[vars2[i]] == i for all i."""
    state = get_cpsat_state(trail)
    cpsat_v1 = [_to_cpsat(v, trail) for v in _as_list(vars1)]
    cpsat_v2 = [_to_cpsat(v, trail) for v in _as_list(vars2)]
    ct = state.model.AddInverse(cpsat_v1, cpsat_v2)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True


def or_automaton(vars_list: Any, start: int, accepting: list,
                 transitions: list, trail: Trail) -> bool:
    """Post an automaton (regular language) constraint."""
    state = get_cpsat_state(trail)
    cpsat_vars = [_to_cpsat(v, trail) for v in _as_list(vars_list)]
    start = int(start)
    acc = [int(a) for a in accepting]
    trans = []
    for t in transitions:
        t = deref(t)
        if isinstance(t, (list, tuple)) and len(t) == 3:
            s, v, ns = t
        elif type(t) is tuple and len(t) == 4 and type(t[0]) is str:
            s, v, ns = t[1:]
        else:
            raise TypeError(f"Expected transition(State, Value, NextState), got {t}")
        trans.append((int(deref(s)), int(deref(v)), int(deref(ns))))
    state.model.AddAutomaton(cpsat_vars, start, acc, trans)
    return True


def or_reservoir(times: list, level_changes: list,
                 min_level: int, max_level: int, trail: Trail) -> bool:
    """Post a reservoir constraint."""
    state = get_cpsat_state(trail)
    times_cp = [_to_cpsat(t, trail) if is_var(deref(t)) else int(deref(t))
                for t in times]
    changes = [int(deref(c)) for c in level_changes]
    state.model.AddReservoirConstraint(times_cp, changes, min_level, max_level)
    return True


# ── Optimization ───────────────────────────────────────────────────────────

def _to_cpsat_expr(expr: Any, trail: Trail) -> Any:
    """Convert expr to CP-SAT expression. Accepts both Clausal AST and native CP-SAT."""
    expr = deref(expr)
    # If it's already a CP-SAT expression (IntVar, BoolVar, LinearExpr, etc.)
    if isinstance(expr, _LinearExpr):
        return expr
    return clausal_to_cpsat(expr, trail)


def or_minimize(expr: Any, val: Any, trail: Trail):
    """Minimize a CP-SAT expression and unify val with the optimal value."""
    state = get_cpsat_state(trail)
    cpsat_expr = _to_cpsat_expr(expr, trail)
    state.model.Minimize(cpsat_expr)

    _apply_assumptions(state)
    status = state.solver.Solve(state.model)

    if status in (_OPTIMAL, _FEASIBLE):
        obj_val = int(state.solver.ObjectiveValue())
        mark = trail.mark()
        # A registered var may already be bound to a conflicting value (there
        # is no OR attr hook, A08-F013), so honour the unify result instead of
        # discarding it — otherwise an "optimal" solution inconsistent with the
        # substitution escapes (A08-F016).
        ok = all(
            unify(cv, state.solver.Value(state.var_map[id(cv)]), trail)
            for cv in state.rev_map.values()
        )
        if ok and unify(val, obj_val, trail):
            yield None
        trail.undo(mark)


def or_maximize(expr: Any, val: Any, trail: Trail):
    """Maximize a CP-SAT expression and unify val with the optimal value."""
    state = get_cpsat_state(trail)
    cpsat_expr = _to_cpsat_expr(expr, trail)
    state.model.Maximize(cpsat_expr)

    _apply_assumptions(state)
    status = state.solver.Solve(state.model)

    if status in (_OPTIMAL, _FEASIBLE):
        obj_val = int(state.solver.ObjectiveValue())
        mark = trail.mark()
        # A registered var may already be bound to a conflicting value (there
        # is no OR attr hook, A08-F013), so honour the unify result instead of
        # discarding it — otherwise an "optimal" solution inconsistent with the
        # substitution escapes (A08-F016).
        ok = all(
            unify(cv, state.solver.Value(state.var_map[id(cv)]), trail)
            for cv in state.rev_map.values()
        )
        if ok and unify(val, obj_val, trail):
            yield None
        trail.undo(mark)


# ── Solution hints ─────────────────────────────────────────────────────────

def or_hint(vars_list: Any, values_list: Any, trail: Trail) -> bool:
    """Provide solution hints to warm-start the solver."""
    state = get_cpsat_state(trail)
    vars_ = _as_list(vars_list)
    vals = _as_list(values_list)
    if len(vars_) != len(vals):
        raise ValueError("or_hint: vars and values must have same length")
    for v, val in zip(vars_, vals):
        cpsat_var = _to_cpsat(v, trail)
        state.model.AddHint(cpsat_var, int(deref(val)))
    return True


# ── Decision strategy ─────────────────────────────────────────────────────

def or_decision_strategy(vars_list: Any, var_strategy: str,
                         domain_strategy: str, trail: Trail) -> bool:
    """Set the search strategy for variable/value selection."""
    state = get_cpsat_state(trail)
    cpsat_vars = [_to_cpsat(v, trail) for v in _as_list(vars_list)]

    var_strats = {
        'choose_first': _cp_model.CHOOSE_FIRST,
        'choose_lowest_min': _cp_model.CHOOSE_LOWEST_MIN,
        'choose_highest_max': _cp_model.CHOOSE_HIGHEST_MAX,
        'choose_min_domain_size': _cp_model.CHOOSE_MIN_DOMAIN_SIZE,
        'choose_max_domain_size': _cp_model.CHOOSE_MAX_DOMAIN_SIZE,
    }
    dom_strats = {
        'select_min_value': _cp_model.SELECT_MIN_VALUE,
        'select_max_value': _cp_model.SELECT_MAX_VALUE,
        'select_lower_half': _cp_model.SELECT_LOWER_HALF,
        'select_upper_half': _cp_model.SELECT_UPPER_HALF,
    }

    vs = var_strats.get(var_strategy)
    ds = dom_strats.get(domain_strategy)
    if vs is None:
        raise ValueError(f"Unknown var_strategy: {var_strategy}")
    if ds is None:
        raise ValueError(f"Unknown domain_strategy: {domain_strategy}")

    state.model.AddDecisionStrategy(cpsat_vars, vs, ds)
    return True
