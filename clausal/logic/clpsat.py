"""clausal.logic.clpsat — PySAT Boolean satisfiability backend.

Provides access to 15+ state-of-the-art CDCL SAT solvers (CaDiCaL, Glucose,
Minisat, Kissat, etc.) through PySAT's unified Solver API, integrated with
Clausal's trail-based backtracking via activation literals.

Variable mapping
----------------
Each Clausal Var that participates in SAT constraints gets a positive integer
(PySAT variable number), stored in two places:

  - SATState.var_map   id(Var) → int           (for fast lookup)
  - SATState.rev_map   int → Var               (for model extraction)
  - Var attribute      SAT_KEY → SATVarInfo     (trail-safe; for hooks)

Backtracking via activation literals
------------------------------------
PySAT solvers lack push/pop.  Instead, each scope creates a fresh "activation
literal" added to the assumptions list.  Clauses are guarded by the negation
of the activation literal::

    sat_push(trail)
    # clause [x, -y] becomes [-act, x, -y]
    sat_add_clause([x, -y], trail)
    # on backtrack: act removed from assumptions → clause dormant

State lifecycle
---------------
One SATState per Trail (keyed by id(trail) in a module-level dict).
Cleaned up automatically when the Trail is garbage-collected via weakref.

Import guard
------------
All pysat usage is conditional; Clausal works fine without python-sat installed.
"""

from __future__ import annotations

import weakref
from typing import Any

from clausal.logic.variables import (
    Var, Trail, deref, is_var, unify, put_attr,
)

# ── PySAT import guard ──────────────────────────────────────────────────────

try:
    from pysat.solvers import Solver as _PySATSolver
    from pysat.card import CardEnc as _CardEnc, EncType as _EncType
    _HAS_PYSAT = True
except ImportError:  # pragma: no cover
    _HAS_PYSAT = False


def _require_pysat() -> None:
    if not _HAS_PYSAT:
        raise ImportError(
            "PySAT backend requires the python-sat package: "
            "pip install python-sat"
        )


# ── AST node imports (for expression translation) ───────────────────────────

from clausal.pythonic_ast.nodes import (
    BitAnd as _BitAnd, BitOr as _BitOr, BitXor as _BitXor,
    Invert as _Invert,
    And as _And, Or as _Or, Not as _Not,
    ArithEq as _ArithEq, ArithNeq as _ArithNeq,
)


# ── Constants ───────────────────────────────────────────────────────────────

SAT_KEY = "sat"  # attribute key on Clausal Vars


# ── SATVarInfo — attribute stored on a Var ──────────────────────────────────

class SATVarInfo:
    """Attribute value stored on a Clausal Var under key SAT_KEY.

    Stores the corresponding PySAT variable number.  Trail-safe:
    put_attr records the old value so backtracking restores it.
    """
    __slots__ = ('sat_var',)

    def __init__(self, sat_var: int) -> None:
        self.sat_var = sat_var


# ── Solver name mapping ────────────────────────────────────────────────────

_SOLVER_NAMES: dict[str, str] = {
    'cadical195': 'cadical195', 'cadical153': 'cadical153',
    'cadical': 'cadical195',
    'glucose': 'g421', 'glucose3': 'g3', 'glucose4': 'g4',
    'g421': 'g421', 'g4': 'g4', 'g3': 'g3',
    'minisat': 'm22', 'm22': 'm22', 'mgh': 'mgh',
    'kissat': 'kissat',
    'lingeling': 'lgl', 'lgl': 'lgl',
    'maplesat': 'mpl', 'mpl': 'mpl',
    'maplechrono': 'mcb', 'mcb': 'mcb',
    'maplelcm': 'mcl', 'mcl': 'mcl',
    'mergesat': 'mg3', 'mg3': 'mg3',
    'minicard': 'mc', 'mc': 'mc',
}


# ── SATState — per-query solver state ───────────────────────────────────────

class SATState:
    """Per-query SAT solver state, one instance per Trail."""
    __slots__ = ('solver', 'var_map', 'rev_map', 'assumptions',
                 '_counter', 'solver_name')

    def __init__(self, solver_name: str = 'cadical195') -> None:
        _require_pysat()
        name = _SOLVER_NAMES.get(solver_name)
        if name is None:
            raise ValueError(
                f"Unknown SAT solver: {solver_name!r}. "
                f"Available: {sorted(set(_SOLVER_NAMES.values()))}"
            )
        self.solver_name = name
        self.solver = _PySATSolver(name=name)
        self.var_map: dict[int, int] = {}    # id(Var) → SAT var number
        self.rev_map: dict[int, Var] = {}    # SAT var number → Var
        self.assumptions: list[int] = []     # active activation literals
        self._counter: int = 0               # next SAT variable number


# ── State registry ──────────────────────────────────────────────────────────

_sat_states: dict[int, SATState] = {}


def _cleanup_sat_state(tid: int) -> None:
    state = _sat_states.pop(tid, None)
    if state is not None:
        state.solver.delete()


def get_sat_state(trail: Trail, solver_name: str = 'cadical195') -> SATState:
    """Get or create the SATState for this trail.

    One SATState is created per Trail and reused for all SAT operations
    within that query.  Cleaned up automatically when the Trail is GC'd.
    """
    tid = id(trail)
    state = _sat_states.get(tid)
    if state is not None:
        resolved = _SOLVER_NAMES.get(solver_name, solver_name)
        if state.solver_name != resolved:
            raise ValueError(
                f"SAT solver mismatch: trail already using "
                f"{state.solver_name!r}, cannot switch to {solver_name!r}"
            )
        return state
    state = SATState(solver_name)
    _sat_states[tid] = state
    weakref.finalize(trail, _cleanup_sat_state, tid)
    return state


# ── Variable registration ──────────────────────────────────────────────────

def _get_existing_sat_state(trail: Trail) -> SATState:
    """Get the existing SATState for this trail, or create with default solver.

    If no state exists yet, creates one with cadical195 (the default).
    Internal functions use this to avoid accidentally overriding the
    user's solver choice.
    """
    tid = id(trail)
    state = _sat_states.get(tid)
    if state is not None:
        return state
    return get_sat_state(trail)  # default solver (cadical195)


def sat_var_for(var: Var, trail: Trail) -> int:
    """Get or create a SAT variable number for a Clausal Var.

    Returns a positive integer (PySAT variable number).
    The mapping is cached in var_map (not trailed).
    A SATVarInfo attribute is stored on the Var (trail-safe).
    """
    var = deref(var)
    if not is_var(var):
        raise TypeError(
            f"sat_var_for: expected unbound Var, got {type(var).__name__}"
        )

    state = _get_existing_sat_state(trail)
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


def _fresh_sat_var(state: SATState) -> int:
    """Allocate a fresh SAT variable number (not mapped to a Clausal Var).

    Used for activation literals and Tseitin auxiliary variables.
    """
    state._counter += 1
    return state._counter


# ── Activation literal scope management ─────────────────────────────────────

def sat_push(trail: Trail) -> None:
    """Push a new activation-literal scope.

    Creates a fresh SAT variable as an activation literal, adds it to
    the assumptions list, and records a trail callback to remove it on
    backtrack.
    """
    state = _get_existing_sat_state(trail)
    act = _fresh_sat_var(state)
    state.assumptions.append(act)
    # Capture act by value for the closure
    trail.record(lambda a=act, st=state: st.assumptions.remove(a))


# ── Clause addition ────────────────────────────────────────────────────────

def sat_add_clause(literals: list[int], trail: Trail) -> None:
    """Add a clause guarded by the current activation literal.

    If no activation scope is active, the clause is added unguarded
    (permanent).
    """
    state = _get_existing_sat_state(trail)
    if state.assumptions:
        act = state.assumptions[-1]
        state.solver.add_clause([-act] + literals)
    else:
        state.solver.add_clause(literals)


# ── Satisfiability check ───────────────────────────────────────────────────

def sat_check(trail: Trail) -> bool:
    """Return True if current SAT constraints are satisfiable."""
    state = _get_existing_sat_state(trail)
    return state.solver.solve(assumptions=state.assumptions)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: CNF Translation & Labeling
# ═══════════════════════════════════════════════════════════════════════════

def _is_literal(expr: Any) -> bool:
    """Check if expression is a simple literal (Var, ~Var, or ground 0/1)."""
    expr = deref(expr)
    if is_var(expr):
        return True
    if isinstance(expr, int) and expr in (0, 1):
        return True
    if isinstance(expr, (_Invert, _Not)):
        return _is_literal(expr.operand)
    return False


def _is_simple_clause(expr: Any) -> bool:
    """Check if expression is a disjunction of literals (no AND/XOR nesting)."""
    expr = deref(expr)
    if _is_literal(expr):
        return True
    if isinstance(expr, (_BitOr, _Or)):
        return _is_simple_clause(expr.left) and _is_simple_clause(expr.right)
    return False


def _expr_to_literal(expr: Any, trail: Trail) -> int:
    """Translate a simple literal expression to a signed SAT integer."""
    expr = deref(expr)

    if is_var(expr):
        return sat_var_for(expr, trail)

    if isinstance(expr, (_Invert, _Not)):
        return -_expr_to_literal(expr.operand, trail)

    if isinstance(expr, bool):
        expr = int(expr)
    if isinstance(expr, int):
        if expr == 1:
            # True literal: create a fresh var forced to True
            state = _get_existing_sat_state(trail)
            t = _fresh_sat_var(state)
            sat_add_clause([t], trail)
            return t
        elif expr == 0:
            # False literal: create a fresh var forced to False
            state = _get_existing_sat_state(trail)
            t = _fresh_sat_var(state)
            sat_add_clause([-t], trail)
            return t

    raise TypeError(
        f"Cannot translate {type(expr).__name__} to SAT literal: {expr!r}"
    )


def _collect_disjuncts(expr: Any, trail: Trail) -> list[int]:
    """Flatten a disjunction tree into a list of SAT literals."""
    expr = deref(expr)
    if isinstance(expr, (_BitOr, _Or)):
        return (_collect_disjuncts(expr.left, trail)
                + _collect_disjuncts(expr.right, trail))
    return [_expr_to_literal(expr, trail)]


def clausal_to_cnf(expr: Any, trail: Trail) -> tuple[int, list[list[int]]]:
    """Translate a Boolean expression to CNF via Tseitin transformation.

    Returns (root_literal, aux_clauses) where:
    - root_literal is the SAT literal representing the whole expression
    - aux_clauses are the Tseitin auxiliary clauses that must be added

    The caller must add aux_clauses AND assert [root_literal].
    """
    state = _get_existing_sat_state(trail)
    aux: list[list[int]] = []

    def tseitin(e: Any) -> int:
        e = deref(e)

        # Base cases
        if is_var(e):
            return sat_var_for(e, trail)
        if isinstance(e, bool):
            e = int(e)
        if isinstance(e, int) and e in (0, 1):
            t = _fresh_sat_var(state)
            aux.append([t] if e else [-t])
            return t

        # NOT: ~A
        if isinstance(e, (_Invert, _Not)):
            return -tseitin(e.operand)

        # OR: A | B
        if isinstance(e, (_BitOr, _Or)):
            a = tseitin(e.left)
            b = tseitin(e.right)
            t = _fresh_sat_var(state)
            # t <-> (a | b)
            aux.append([-t, a, b])
            aux.append([t, -a])
            aux.append([t, -b])
            return t

        # AND: A & B
        if isinstance(e, (_BitAnd, _And)):
            a = tseitin(e.left)
            b = tseitin(e.right)
            t = _fresh_sat_var(state)
            # t <-> (a & b)
            aux.append([t, -a, -b])
            aux.append([-t, a])
            aux.append([-t, b])
            return t

        # XOR: A ^ B
        if isinstance(e, _BitXor):
            a = tseitin(e.left)
            b = tseitin(e.right)
            t = _fresh_sat_var(state)
            # t <-> (a ^ b)
            aux.append([-t, -a, -b])
            aux.append([-t, a, b])
            aux.append([t, -a, b])
            aux.append([t, a, -b])
            return t

        # EQ: A == B (XNOR)
        if isinstance(e, _ArithEq):
            a = tseitin(e.left)
            b = tseitin(e.right)
            t = _fresh_sat_var(state)
            # t <-> (a <-> b) = t <-> NOT(a XOR b)
            aux.append([-t, a, -b])
            aux.append([-t, -a, b])
            aux.append([t, a, b])
            aux.append([t, -a, -b])
            return t

        # NEQ: A != B (XOR)
        if isinstance(e, _ArithNeq):
            a = tseitin(e.left)
            b = tseitin(e.right)
            t = _fresh_sat_var(state)
            # Same encoding as XOR
            aux.append([-t, -a, -b])
            aux.append([-t, a, b])
            aux.append([t, -a, b])
            aux.append([t, a, -b])
            return t

        raise TypeError(
            f"Cannot translate {type(e).__name__} to SAT CNF: {e!r}"
        )

    root = tseitin(expr)
    return root, aux


# ── Constraint block ───────────────────────────────────────────────────────

def sat_constraint_block(constraint_set: Any, solver_name: str,
                         trail: Trail) -> bool:
    """Walk constraint elements and post each as CNF clauses.

    Each element in the tuple/list is a Boolean formula that must hold
    (conjunction of all elements).  Simple disjunctions are added directly;
    complex expressions use Tseitin transformation.

    Returns True on success.  Consistency is checked lazily at label/check.
    """
    get_sat_state(trail, solver_name)  # ensure state exists with right solver

    constraint_set = deref(constraint_set)
    if isinstance(constraint_set, (list, tuple)):
        elements = list(constraint_set)
    else:
        elements = [constraint_set]

    sat_push(trail)  # one activation scope for this block

    # Process elements, flattening top-level AND (conjunction) since each
    # element is already conjunctive.  (X & Y,) becomes two separate
    # constraints X and Y, avoiding unnecessary Tseitin variables.
    while elements:
        elem = deref(elements.pop(0))

        if isinstance(elem, (_BitAnd, _And)):
            # Flatten: push children back for separate processing
            elements.insert(0, elem.right)
            elements.insert(0, elem.left)
            continue

        if _is_simple_clause(elem):
            # Fast path: disjunction of literals → single clause
            lits = _collect_disjuncts(elem, trail)
            sat_add_clause(lits, trail)
        else:
            # Complex expression: Tseitin transform
            root, aux_clauses = clausal_to_cnf(elem, trail)
            for clause in aux_clauses:
                sat_add_clause(clause, trail)
            sat_add_clause([root], trail)  # assert root is true

    return True


# ── List coercion ──────────────────────────────────────────────────────────

def _as_list(val: Any) -> list:
    """Coerce to a Python list."""
    val = deref(val)
    if isinstance(val, list):
        return val
    if isinstance(val, tuple):
        return list(val)
    if is_var(val) or isinstance(val, int):
        return [val]
    try:
        from clausal.terms import cons_to_list
        return cons_to_list(val)
    except (ValueError, TypeError, ImportError):
        raise TypeError(
            f"Expected a list, got {type(val).__name__!r}: {val!r}"
        )


# ── Labeling (solution enumeration) ────────────────────────────────────────

def label_sat(vars_list: Any, trail: Trail):
    """Enumerate satisfying Boolean assignments for SAT-constrained variables.

    Generator: yields None for each solution, with Clausal vars bound to
    0 or 1.  Bindings are undone between solutions; the caller sees
    each solution fresh.
    """
    state = _get_existing_sat_state(trail)
    items = _as_list(vars_list)

    sat_vars: list[int] = []
    clausal_vars: list[Var] = []

    for v in items:
        v = deref(v)
        if is_var(v):
            sv = state.var_map.get(id(v))
            if sv is None:
                raise ValueError(
                    "label_sat: variable not registered with SAT solver. "
                    "Post a constraint first."
                )
            sat_vars.append(sv)
            clausal_vars.append(v)
        elif isinstance(v, int) and v in (0, 1):
            pass  # already ground
        else:
            raise TypeError(
                f"label_sat: expected 0/1 or Var, got {type(v).__name__}"
            )

    if not sat_vars:
        # All variables ground — yield one solution iff SAT
        if sat_check(trail):
            yield None
        return

    # Create an activation literal to guard blocking clauses.
    # Managed manually (not via sat_push) so we can remove it both:
    #   - on generator exhaustion/close (finally block below)
    #   - on trail backtracking (trail.record callback)
    act = _fresh_sat_var(state)
    state.assumptions.append(act)
    trail.record(
        lambda: state.assumptions.remove(act)
        if act in state.assumptions else None
    )

    try:
        while state.solver.solve(assumptions=state.assumptions):
            model = state.solver.get_model()
            model_set = set(model)

            # Extract 0/1 values for our variables
            values = [1 if sv in model_set else 0 for sv in sat_vars]

            mark = trail.mark()
            ok = all(unify(cv, val, trail)
                     for cv, val in zip(clausal_vars, values))

            if ok:
                yield None  # solution — control returns to caller

            trail.undo(mark)  # unbind Clausal vars for next iteration

            # Block this assignment so next solve() finds a new one.
            # Guarded by act so blocking clauses become dormant when act
            # is removed from assumptions (on backtrack or generator exit).
            state.solver.add_clause([-act] + [
                -sv if sv in model_set else sv for sv in sat_vars
            ])
    finally:
        # Clean up activation literal on generator exhaustion, early exit
        # (break), or close.  If trail.undo already removed it (backtrack),
        # the remove is a no-op.
        try:
            state.assumptions.remove(act)
        except ValueError:
            pass  # already removed by trail callback


def sat_count(vars_list: Any, trail: Trail) -> int:
    """Count the number of satisfying assignments."""
    count = 0
    for _ in label_sat(vars_list, trail):
        count += 1
    return count


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: Cardinality Constraints
# ═══════════════════════════════════════════════════════════════════════════

def sat_at_most(vars_list: Any, k: int, trail: Trail) -> bool:
    """At most k of the variables are True (1).

    Uses pysat.card.CardEnc.atmost with sequential counter encoding.
    """
    state = _get_existing_sat_state(trail)
    items = _as_list(vars_list)
    lits = []
    for v in items:
        v = deref(v)
        if is_var(v):
            lits.append(sat_var_for(v, trail))
        elif isinstance(v, int) and v in (0, 1):
            if v == 1:
                k -= 1  # ground True consumes one slot
        else:
            raise TypeError(f"sat_at_most: expected 0/1 or Var, got {type(v).__name__}")

    if k < 0:
        return False  # already exceeded bound with ground Trues

    if not lits:
        return True  # no unbound vars, bound not exceeded

    cnf = _CardEnc.atmost(lits=lits, bound=k, top_id=state._counter,
                          encoding=_EncType.seqcounter)
    if cnf.nv > state._counter:
        state._counter = cnf.nv

    sat_push(trail)
    for clause in cnf.clauses:
        sat_add_clause(clause, trail)

    return True


def sat_at_least(vars_list: Any, k: int, trail: Trail) -> bool:
    """At least k of the variables are True (1)."""
    state = _get_existing_sat_state(trail)
    items = _as_list(vars_list)
    lits = []
    for v in items:
        v = deref(v)
        if is_var(v):
            lits.append(sat_var_for(v, trail))
        elif isinstance(v, int) and v in (0, 1):
            if v == 1:
                k -= 1  # ground True satisfies one requirement
        else:
            raise TypeError(f"sat_at_least: expected 0/1 or Var, got {type(v).__name__}")

    if k <= 0:
        return True  # bound already met by ground Trues

    if not lits:
        return False  # no unbound vars, bound not met

    cnf = _CardEnc.atleast(lits=lits, bound=k, top_id=state._counter,
                           encoding=_EncType.seqcounter)
    if cnf.nv > state._counter:
        state._counter = cnf.nv

    sat_push(trail)
    for clause in cnf.clauses:
        sat_add_clause(clause, trail)

    return True


def sat_exactly(vars_list: Any, k: int, trail: Trail) -> bool:
    """Exactly k of the variables are True (1)."""
    state = _get_existing_sat_state(trail)
    items = _as_list(vars_list)
    lits = []
    for v in items:
        v = deref(v)
        if is_var(v):
            lits.append(sat_var_for(v, trail))
        elif isinstance(v, int) and v in (0, 1):
            if v == 1:
                k -= 1  # ground True satisfies one requirement
        else:
            raise TypeError(f"sat_exactly: expected 0/1 or Var, got {type(v).__name__}")

    if k < 0:
        return False  # too many ground Trues

    if not lits:
        return k == 0  # no unbound vars; succeed only if k is now 0

    cnf = _CardEnc.equals(lits=lits, bound=k, top_id=state._counter,
                          encoding=_EncType.seqcounter)
    if cnf.nv > state._counter:
        state._counter = cnf.nv

    sat_push(trail)
    for clause in cnf.clauses:
        sat_add_clause(clause, trail)

    return True
