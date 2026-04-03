"""clausal.logic.clpz3 — Z3 constraint solver backend.

Provides Z3-backed constraint predicates as an alternative to Clausal's
native CLP(FD)/CLP(B)/CLP(Q)/CLP(R) solvers.

Variable mapping
----------------
Each Clausal Var that participates in Z3 constraints gets a corresponding
Z3 symbolic constant, stored in two places:

  - Z3State.var_map   id(Var) → ExprRef      (for fast lookup)
  - Z3State.rev_map   ExprRef.get_id() → Var  (for callbacks)
  - Var attribute     Z3_KEY → Z3VarInfo       (trail-safe; for hooks)

Trail synchronization
---------------------
Z3's Solver.push()/pop() are kept in sync with Clausal's trail via
trail.record() callbacks:

    z3_push(trail)
    # ... solver.add(constraint) ...
    trail.undo(mark)   # → solver.pop() fires automatically

State lifecycle
---------------
One Z3State per Trail (keyed by id(trail) in a module-level dict).
Cleaned up automatically when the Trail is garbage-collected via weakref.

Import guard
------------
All z3 usage is conditional; Clausal works fine without z3-solver installed.
"""

from __future__ import annotations

import weakref
from fractions import Fraction
from typing import Any

from clausal.logic.variables import (
    Var, Trail, deref, is_var, unify, put_attr, get_attr,
)

# ── Z3 import guard ──────────────────────────────────────────────────────────

try:
    import z3 as _z3
    _HAS_Z3 = True
except ImportError:  # pragma: no cover
    _HAS_Z3 = False


def _require_z3() -> None:
    if not _HAS_Z3:
        raise ImportError(
            "Z3 backend requires the z3-solver package: pip install z3-solver"
        )


# ── AST node imports (for expression translation) ────────────────────────────

from clausal.pythonic_ast.nodes import (
    Add as _Add, Sub as _Sub, Mult as _Mult,
    FloorDiv as _FloorDiv, Mod as _Mod,
    Negate as _Negate,
    BitAnd as _BitAnd, BitOr as _BitOr, BitXor as _BitXor,
    Invert as _Invert,
    And as _And, Or as _Or, Not as _Not,
    ArithEq as _ArithEq, ArithNeq as _ArithNeq,
    Lt as _Lt, LtE as _LtE, Gt as _Gt, GtE as _GtE,
)


# ── Constants ────────────────────────────────────────────────────────────────

Z3_KEY = "z3"  # attribute key on Clausal Vars


# ── Z3VarInfo — attribute stored on a Var ───────────────────────────────────

class Z3VarInfo:
    """Attribute value stored on a Clausal Var under key Z3_KEY.

    Stores the corresponding Z3 constant and its sort. Trail-safe:
    put_attr records the old value so backtracking restores it.
    """
    __slots__ = ('z3_const', 'sort')

    def __init__(self, z3_const: Any, sort: Any) -> None:
        self.z3_const = z3_const
        self.sort = sort


# ── Z3State — per-query solver state ────────────────────────────────────────

class Z3State:
    """Per-query Z3 solver state, one instance per Trail."""

    # __slots__ not used: need to allow dynamic attribute assignment
    # (_soft_constraints, _named_constraints, etc. added in later phases)

    def __init__(self) -> None:
        _require_z3()
        self.solver = _z3.Solver()
        self.var_map: dict[int, Any] = {}   # id(Var) → Z3 ExprRef
        self.rev_map: dict[int, Var] = {}   # ExprRef.get_id() → Var
        self._counter: int = 0              # unique name counter


# ── State registry ────────────────────────────────────────────────────────────
# Keyed by id(trail). weakref.finalize cleans up on GC.

_z3_states: dict[int, Z3State] = {}


def get_z3_state(trail: Trail) -> Z3State:
    """Get or create the Z3State for this trail.

    One Z3State is created per Trail and reused for all Z3 operations
    within that query. Cleaned up automatically when the Trail is GC'd.
    """
    tid = id(trail)
    state = _z3_states.get(tid)
    if state is not None:
        return state
    state = Z3State()
    _z3_states[tid] = state
    weakref.finalize(trail, _z3_states.pop, tid, None)
    return state


# ── Variable registration ─────────────────────────────────────────────────────

def z3_var_for(var: Var, sort: Any, trail: Trail) -> Any:
    """Get or create a Z3 constant for a Clausal Var.

    The mapping is cached in var_map (not trailed — see plan for rationale).
    A Z3VarInfo attribute is stored on the Var (trail-safe).

    Raises TypeError if var is ground or if a sort mismatch is detected.
    """
    var = deref(var)
    if not is_var(var):
        raise TypeError(
            f"z3_var_for: expected unbound Var, got {type(var).__name__}"
        )

    state = get_z3_state(trail)
    vid = id(var)
    existing = state.var_map.get(vid)
    if existing is not None:
        if existing.sort() != sort:
            raise TypeError(
                f"Z3 variable sort mismatch: already registered as "
                f"{existing.sort()}, now requesting {sort}"
            )
        return existing

    state._counter += 1
    name = f"v_{state._counter}"
    z3_const = _z3.Const(name, sort)

    state.var_map[vid] = z3_const
    state.rev_map[z3_const.get_id()] = var

    put_attr(var, Z3_KEY, Z3VarInfo(z3_const, sort), trail)

    return z3_const


# ── Expression translation ────────────────────────────────────────────────────

def clausal_to_z3(expr: Any, trail: Trail, default_sort: Any = None) -> Any:
    """Translate a Clausal expression to a Z3 ExprRef.

    Handles:
    - Ground values (int, float, bool, Fraction) → Z3 literals
    - Unbound Var → look up in var_map, or create with default_sort
    - Arithmetic/boolean AST nodes → Z3 operator applications
    - Comparison nodes → Z3 BoolRef

    default_sort: if provided, used to register unbound Vars on the fly.
                  If None and the Var isn't registered, raises ValueError.
    """
    expr = deref(expr)

    # ── Ground values ────────────────────────────────────────────────────────
    # bool must come before int (bool is a subclass of int)
    if isinstance(expr, bool):
        return _z3.BoolVal(expr)
    if isinstance(expr, int):
        return _z3.IntVal(expr)
    if isinstance(expr, float):
        return _z3.RealVal(expr)
    if isinstance(expr, Fraction):
        return _z3.RealVal(expr.numerator) / _z3.RealVal(expr.denominator)

    # ── Logic variable ───────────────────────────────────────────────────────
    if is_var(expr):
        state = get_z3_state(trail)
        z3_c = state.var_map.get(id(expr))
        if z3_c is not None:
            return z3_c
        if default_sort is None:
            raise ValueError(
                "Unregistered Z3 variable with no default sort. "
                "Declare the variable first with in_z3(), in_z3_real(), etc."
            )
        return z3_var_for(expr, default_sort, trail)

    # ── Arithmetic binary operators ──────────────────────────────────────────
    if isinstance(expr, _Add):
        return (clausal_to_z3(expr.left, trail, default_sort) +
                clausal_to_z3(expr.right, trail, default_sort))
    if isinstance(expr, _Sub):
        return (clausal_to_z3(expr.left, trail, default_sort) -
                clausal_to_z3(expr.right, trail, default_sort))
    if isinstance(expr, _Mult):
        return (clausal_to_z3(expr.left, trail, default_sort) *
                clausal_to_z3(expr.right, trail, default_sort))
    if isinstance(expr, _FloorDiv):
        return (clausal_to_z3(expr.left, trail, default_sort) /
                clausal_to_z3(expr.right, trail, default_sort))
    if isinstance(expr, _Mod):
        return (clausal_to_z3(expr.left, trail, default_sort) %
                clausal_to_z3(expr.right, trail, default_sort))
    if isinstance(expr, _Negate):
        return -clausal_to_z3(expr.operand, trail, default_sort)

    # ── Comparison operators → BoolRef ───────────────────────────────────────
    if isinstance(expr, _ArithEq):
        return (clausal_to_z3(expr.left, trail, default_sort) ==
                clausal_to_z3(expr.right, trail, default_sort))
    if isinstance(expr, _ArithNeq):
        return (clausal_to_z3(expr.left, trail, default_sort) !=
                clausal_to_z3(expr.right, trail, default_sort))
    if isinstance(expr, _Lt):
        return (clausal_to_z3(expr.left, trail, default_sort) <
                clausal_to_z3(expr.right, trail, default_sort))
    if isinstance(expr, _LtE):
        return (clausal_to_z3(expr.left, trail, default_sort) <=
                clausal_to_z3(expr.right, trail, default_sort))
    if isinstance(expr, _Gt):
        return (clausal_to_z3(expr.left, trail, default_sort) >
                clausal_to_z3(expr.right, trail, default_sort))
    if isinstance(expr, _GtE):
        return (clausal_to_z3(expr.left, trail, default_sort) >=
                clausal_to_z3(expr.right, trail, default_sort))

    # ── Boolean binary operators ─────────────────────────────────────────────
    # These arise from CLP(B) expressions and Boolean arithmetic
    if isinstance(expr, (_And, _BitAnd)):
        bool_sort = _z3.BoolSort() if _HAS_Z3 else None
        return _z3.And(clausal_to_z3(expr.left, trail, bool_sort),
                       clausal_to_z3(expr.right, trail, bool_sort))
    if isinstance(expr, (_Or, _BitOr)):
        bool_sort = _z3.BoolSort() if _HAS_Z3 else None
        return _z3.Or(clausal_to_z3(expr.left, trail, bool_sort),
                      clausal_to_z3(expr.right, trail, bool_sort))
    if isinstance(expr, _BitXor):
        bool_sort = _z3.BoolSort() if _HAS_Z3 else None
        return _z3.Xor(clausal_to_z3(expr.left, trail, bool_sort),
                       clausal_to_z3(expr.right, trail, bool_sort))
    if isinstance(expr, (_Not, _Invert)):
        bool_sort = _z3.BoolSort() if _HAS_Z3 else None
        return _z3.Not(clausal_to_z3(expr.operand, trail, bool_sort))

    raise TypeError(
        f"Cannot translate {type(expr).__name__!r} to Z3: {expr!r}"
    )


# ── Value conversion ──────────────────────────────────────────────────────────

def z3_to_python(z3_val: Any) -> int | float | Fraction | str:
    """Convert a Z3 model value to a Python value.

    Mapping:
    - Z3 integer  → Python int
    - Z3 rational → Fraction (exact)
    - Z3 true     → 1  (Clausal uses 0/1 for booleans)
    - Z3 false    → 0
    - Z3 algebraic number → float approximation
    - Other       → str (fallback)
    """
    if _z3.is_int_value(z3_val):
        return z3_val.as_long()
    if _z3.is_rational_value(z3_val):
        return Fraction(z3_val.numerator_as_long(), z3_val.denominator_as_long())
    if _z3.is_true(z3_val):
        return 1
    if _z3.is_false(z3_val):
        return 0
    if _z3.is_algebraic_value(z3_val):
        return float(z3_val.approx(20))
    return str(z3_val)


# ── Trail ↔ Solver synchronization ───────────────────────────────────────────

def z3_push(trail: Trail) -> None:
    """Push a Z3 solver scope, recording the undo callback on the trail.

    When trail.undo() reaches this point, solver.pop() fires automatically,
    retracting all Z3 constraints added since this push.
    """
    state = get_z3_state(trail)
    state.solver.push()
    trail.record(lambda: state.solver.pop())


def z3_add(constraint: Any, trail: Trail) -> bool:
    """Add a Z3 BoolRef constraint to the current scope (lazy — no check).

    Returns True. Consistency is checked lazily at label/check time.
    """
    state = get_z3_state(trail)
    state.solver.add(constraint)
    return True


# ── Phase 2: integer constraints ──────────────────────────────────────────────

def _as_list(val: Any) -> list:
    """Coerce to a Python list.

    - Python list → returned as-is.
    - Scalar (Var/AttVar, int, float, Fraction) → wrapped in [val].
    - Cons-list / SegList → converted via cons_to_list().
    - Anything else → TypeError.
    """
    val = deref(val)
    if isinstance(val, list):
        return val
    if is_var(val) or isinstance(val, (int, float, Fraction)):
        return [val]
    # May be a Clausal cons-list (compound term)
    try:
        from clausal.terms import cons_to_list  # type: ignore[attr-defined]
        return cons_to_list(val)
    except (ValueError, TypeError):
        raise TypeError(
            f"Expected a list, got {type(val).__name__!r}: {val!r}"
        )


def in_z3(var_or_list: Any, lo: Any, hi: Any, trail: Trail) -> bool:
    """Post integer domain constraint [lo, hi] on each variable via Z3.

    - Unbound Var: registered as IntSort and constrained to [lo, hi].
      Singleton domain (lo == hi): unified directly (matches CLP(FD) behavior).
    - Ground int: membership check (fails if out of range).
    - Ground non-int: fails.
    - lo > hi: fails (empty domain).
    """
    lo = deref(lo)
    hi = deref(hi)
    if not isinstance(lo, int) or not isinstance(hi, int):
        raise TypeError(
            f"in_z3: bounds must be integers, got "
            f"{type(lo).__name__}, {type(hi).__name__}"
        )
    if lo > hi:
        return False  # empty domain

    state = get_z3_state(trail)
    items = _as_list(var_or_list)

    for v in items:
        v = deref(v)
        if not is_var(v):
            if not (isinstance(v, int) and lo <= v <= hi):
                return False
            continue
        # Singleton domain: unify immediately (matches CLP(FD) behavior).
        # Also tighten the Z3 constant if the var was already registered,
        # so z3_check and other constraints see the binding reflected in Z3.
        if lo == hi:
            z3_v_existing = state.var_map.get(id(v))
            if z3_v_existing is not None:
                z3_push(trail)
                state.solver.add(z3_v_existing == lo)
            if not unify(v, lo, trail):
                return False
            continue
        z3_v = z3_var_for(v, _z3.IntSort(), trail)
        z3_push(trail)
        state.solver.add(z3_v >= lo)
        state.solver.add(z3_v <= hi)

    return True


def all_different_z3(vars_list: Any, trail: Trail) -> bool:
    """Post Z3 Distinct constraint over a list of variables/ground values."""
    state = get_z3_state(trail)
    items = _as_list(vars_list)

    z3_exprs = []
    for v in items:
        v = deref(v)
        if is_var(v):
            z3_exprs.append(z3_var_for(v, _z3.IntSort(), trail))
        elif isinstance(v, int):
            z3_exprs.append(_z3.IntVal(v))
        else:
            raise TypeError(
                f"all_different_z3: expected int or Var, got {type(v).__name__}"
            )

    if len(z3_exprs) >= 2:
        z3_push(trail)
        state.solver.add(_z3.Distinct(*z3_exprs))
    return True


def label_z3(vars_list: Any, trail: Trail):
    """Enumerate satisfying integer assignments for Z3-constrained variables.

    Generator: yields None for each solution, with Clausal vars bound to
    their values. Bindings are undone between solutions; the caller sees
    each solution fresh.

    Blocking clauses are accumulated in a dedicated Z3 scope so they are
    automatically retracted when Clausal backtracks past this labeling call.
    """
    state = get_z3_state(trail)
    items = _as_list(vars_list)

    z3_vars: list[Any] = []
    clausal_vars: list[Var] = []

    for v in items:
        v = deref(v)
        if is_var(v):
            z3_v = state.var_map.get(id(v))
            if z3_v is None:
                raise ValueError(
                    "label_z3: variable not registered with Z3. "
                    "Declare it first with in_z3()."
                )
            z3_vars.append(z3_v)
            clausal_vars.append(v)
        elif isinstance(v, int):
            pass  # already ground — nothing to label
        else:
            raise TypeError(
                f"label_z3: expected int or Var, got {type(v).__name__}"
            )

    if not z3_vars:
        # All variables are already ground — yield one solution iff the
        # current constraint store is satisfiable (e.g., no Distinct(1,1)).
        if z3_check(trail):
            yield None
        return

    # Push a Z3 scope for blocking clauses.  This scope is popped when Clausal
    # backtracks past this call (via the trail callback registered by z3_push).
    z3_push(trail)

    while state.solver.check() == _z3.sat:
        m = state.solver.model()

        # Extract values and bind Clausal vars
        values = [z3_to_python(m.eval(z3v, model_completion=True))
                  for z3v in z3_vars]

        mark = trail.mark()
        ok = all(unify(cv, val, trail)
                 for cv, val in zip(clausal_vars, values))

        if ok:
            yield None  # solution — control returns to caller

        trail.undo(mark)  # unbind Clausal vars for next iteration

        # Block this exact assignment so the next check() finds a new one
        block = _z3.Or([z3v != m.eval(z3v, model_completion=True)
                        for z3v in z3_vars])
        state.solver.add(block)


def z3_check(trail: Trail) -> bool:
    """Return True if current Z3 constraints are satisfiable."""
    return get_z3_state(trail).solver.check() == _z3.sat


# ── Arithmetic constraint posting ─────────────────────────────────────────────

def _z3_arith_binary(l: Any, r: Any, trail: Trail, op) -> bool:
    """Translate l and r to Z3 IntSort expressions and post op(l, r).

    Wraps in a z3_push scope so the constraint is retracted on backtracking.
    """
    state = get_z3_state(trail)
    z3_l = clausal_to_z3(l, trail, default_sort=_z3.IntSort())
    z3_r = clausal_to_z3(r, trail, default_sort=_z3.IntSort())
    z3_push(trail)
    state.solver.add(op(z3_l, z3_r))
    return True


def z3_eq(l: Any, r: Any, trail: Trail) -> bool:
    """Post l == r as a Z3 integer constraint."""
    return _z3_arith_binary(l, r, trail, lambda a, b: a == b)


def z3_ne(l: Any, r: Any, trail: Trail) -> bool:
    """Post l != r as a Z3 integer constraint."""
    return _z3_arith_binary(l, r, trail, lambda a, b: a != b)


def z3_lt(l: Any, r: Any, trail: Trail) -> bool:
    """Post l < r as a Z3 integer constraint."""
    return _z3_arith_binary(l, r, trail, lambda a, b: a < b)


def z3_le(l: Any, r: Any, trail: Trail) -> bool:
    """Post l <= r as a Z3 integer constraint."""
    return _z3_arith_binary(l, r, trail, lambda a, b: a <= b)


def z3_gt(l: Any, r: Any, trail: Trail) -> bool:
    """Post l > r as a Z3 integer constraint."""
    return _z3_arith_binary(l, r, trail, lambda a, b: a > b)


def z3_ge(l: Any, r: Any, trail: Trail) -> bool:
    """Post l >= r as a Z3 integer constraint."""
    return _z3_arith_binary(l, r, trail, lambda a, b: a >= b)


# ── Phase 3: boolean constraints ──────────────────────────────────────────────

def clausal_bool_to_z3(expr: Any, trail: Trail) -> Any:
    """Translate a Clausal Boolean expression to a Z3 BoolRef.

    Handles:
    - bool / int (0 or 1) → BoolVal
    - Var → BoolSort Z3 constant
    - BitAnd/BitOr/BitXor/Invert/And/Or/Not → Z3 boolean operators
    - BoolEq(L, R) → L == R in Z3
    - BoolImpl(L, R) → Implies(L, R) in Z3

    Delegates to clausal_to_z3 with default_sort=BoolSort() for all other
    nodes (comparisons, arithmetic AST nodes producing BoolRef, etc.).
    """
    expr = deref(expr)
    # bool must come before int — bool is a subclass of int
    if isinstance(expr, bool):
        return _z3.BoolVal(expr)
    # int 0/1 treated as boolean constants (unlike clausal_to_z3 which gives IntVal)
    if isinstance(expr, int):
        return _z3.BoolVal(bool(expr))
    # BoolEq / BoolImpl — make_predicate instances, detected via _functor
    functor = getattr(type(expr), '_functor', None)
    if functor == 'BoolEq':
        return (clausal_bool_to_z3(expr.left, trail) ==
                clausal_bool_to_z3(expr.right, trail))
    if functor == 'BoolImpl':
        return _z3.Implies(clausal_bool_to_z3(expr.left, trail),
                           clausal_bool_to_z3(expr.right, trail))
    # All other nodes (Var, BitAnd/BitOr/BitXor/Invert, And/Or/Not, comparisons)
    return clausal_to_z3(expr, trail, default_sort=_z3.BoolSort())


def _collect_z3_bool_vars(z3_expr: Any) -> list:
    """Collect all free Boolean constants from a Z3 expression tree."""
    result: list = []
    seen: set = set()

    def _walk(e: Any) -> None:
        eid = e.get_id()
        if eid in seen:
            return
        seen.add(eid)
        if (_z3.is_bool(e) and _z3.is_const(e)
                and not _z3.is_true(e) and not _z3.is_false(e)):
            result.append(e)
        for i in range(e.num_args()):
            _walk(e.arg(i))

    _walk(z3_expr)
    return result


def sat_z3(expr: Any, trail: Trail) -> bool:
    """Post a Boolean constraint via Z3 (lazy — no consistency check).

    Wraps in a z3_push scope so the constraint is retracted on backtracking.
    Consistency is deferred to the next z3_check() or label_z3_bool() call.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_bool_to_z3(expr, trail)
    z3_push(trail)
    state.solver.add(z3_expr)
    return True


def z3_try(expr: Any, trail: Trail) -> bool:
    """Probe whether current constraints + expr are satisfiable, non-committingly.

    Does NOT post expr to the solver. Succeeds if sat, fails if unsat.
    Use this to test a constraint before committing to it.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_bool_to_z3(expr, trail)
    state.solver.push()
    state.solver.add(z3_expr)
    result = state.solver.check() == _z3.sat
    state.solver.pop()
    return result


def taut_z3(expr: Any, t_var: Any, trail: Trail) -> bool:
    """Tautology/contradiction check against current constraint store.

    - T = 1 if expr is necessarily true given constraints (tautology).
    - T = 0 if expr is necessarily false given constraints (contradiction).
    - Fails (returns False) if indeterminate.

    Uses push/pop directly (not trail.record) because these are temporary
    probes that must not persist on the trail.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_bool_to_z3(expr, trail)

    # Tautology check: is Not(expr) unsatisfiable?
    state.solver.push()
    state.solver.add(_z3.Not(z3_expr))
    neg_result = state.solver.check()
    state.solver.pop()

    if neg_result == _z3.unsat:
        return unify(t_var, 1, trail)

    # Contradiction check: is expr itself unsatisfiable?
    state.solver.push()
    state.solver.add(z3_expr)
    pos_result = state.solver.check()
    state.solver.pop()

    if pos_result == _z3.unsat:
        return unify(t_var, 0, trail)

    return False  # indeterminate


def sat_count_z3(expr: Any, count_var: Any, trail: Trail) -> bool:
    """Count satisfying Boolean assignments for expr via AllSMT enumeration.

    Enumerates all satisfying assignments to the free Boolean variables in
    expr using blocking clauses. O(2^n) in the worst case.

    The enumeration runs inside a temporary push/pop scope so the blocking
    clauses do not persist in the constraint store.

    Note: counting is performed within the current constraint context —
    prior solver constraints (e.g., from sat_z3) restrict which assignments
    are counted. Only assignments that satisfy both expr AND any pre-existing
    constraints are included in the count.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_bool_to_z3(expr, trail)
    bool_vars = _collect_z3_bool_vars(z3_expr)

    if not bool_vars:
        # Expression is a constant — check if it's satisfiable
        state.solver.push()
        state.solver.add(z3_expr)
        result = state.solver.check()
        state.solver.pop()
        count = 1 if result == _z3.sat else 0
        return unify(count_var, count, trail)

    state.solver.push()
    state.solver.add(z3_expr)
    count = 0
    while state.solver.check() == _z3.sat:
        count += 1
        m = state.solver.model()
        block = _z3.Or([v != m.eval(v, model_completion=True) for v in bool_vars])
        state.solver.add(block)
    state.solver.pop()

    return unify(count_var, count, trail)


def label_z3_bool(vars_list: Any, trail: Trail):
    """Enumerate satisfying 0/1 assignments for Boolean Z3 variables.

    Generator: yields None for each solution with Clausal vars bound to
    0 or 1. Bindings are undone between solutions.

    Variables not yet registered with Z3 are registered as BoolSort on
    first encounter.
    """
    state = get_z3_state(trail)
    items = _as_list(vars_list)

    z3_vars: list = []
    clausal_vars: list = []

    for v in items:
        v = deref(v)
        if is_var(v):
            z3_v = z3_var_for(v, _z3.BoolSort(), trail)
            z3_vars.append(z3_v)
            clausal_vars.append(v)
        elif isinstance(v, int) and v in (0, 1):
            pass  # already ground
        elif isinstance(v, bool):
            pass  # already ground
        else:
            raise TypeError(
                f"label_z3_bool: expected 0, 1, or Var, got {v!r}"
            )

    if not z3_vars:
        if z3_check(trail):
            yield None
        return

    z3_push(trail)

    while state.solver.check() == _z3.sat:
        m = state.solver.model()
        values = [1 if _z3.is_true(m.eval(z3v, model_completion=True)) else 0
                  for z3v in z3_vars]

        mark = trail.mark()
        ok = all(unify(cv, val, trail)
                 for cv, val in zip(clausal_vars, values))

        if ok:
            yield None

        trail.undo(mark)
        block = _z3.Or([z3v != m.eval(z3v, model_completion=True)
                        for z3v in z3_vars])
        state.solver.add(block)


def at_most_z3(vars_list: Any, k: Any, trail: Trail) -> bool:
    """Post: at most k of the Boolean variables are true."""
    state = get_z3_state(trail)
    k = deref(k)
    z3_exprs = [
        z3_var_for(deref(v), _z3.BoolSort(), trail) if is_var(deref(v))
        else _z3.BoolVal(bool(deref(v)))
        for v in _as_list(vars_list)
    ]
    z3_push(trail)
    state.solver.add(_z3.AtMost(*z3_exprs, k))
    return True


def at_least_z3(vars_list: Any, k: Any, trail: Trail) -> bool:
    """Post: at least k of the Boolean variables are true."""
    state = get_z3_state(trail)
    k = deref(k)
    z3_exprs = [
        z3_var_for(deref(v), _z3.BoolSort(), trail) if is_var(deref(v))
        else _z3.BoolVal(bool(deref(v)))
        for v in _as_list(vars_list)
    ]
    z3_push(trail)
    state.solver.add(_z3.AtLeast(*z3_exprs, k))
    return True


def exactly_z3(vars_list: Any, k: Any, trail: Trail) -> bool:
    """Post: exactly k of the Boolean variables are true."""
    # Convert once to avoid double _as_list on cons-lists
    items = _as_list(vars_list)
    return at_most_z3(items, k, trail) and at_least_z3(items, k, trail)


# ── Phase 4: real/rational constraints ────────────────────────────────────────

def _to_z3_real(val: Any) -> Any:
    """Convert a Python numeric to a Z3 RealVal (exact for Fraction, int; approx for float)."""
    if isinstance(val, bool):
        return _z3.RealVal(int(val))
    if isinstance(val, Fraction):
        return _z3.RealVal(val.numerator) / _z3.RealVal(val.denominator)
    if isinstance(val, int):
        return _z3.RealVal(val)
    if isinstance(val, float):
        # Convert via Fraction for exact representation where possible
        return _z3.RealVal(str(Fraction(val).limit_denominator(10**15)))
    raise TypeError(f"Cannot convert {type(val).__name__} to Z3 Real: {val!r}")


def in_z3_real(var_or_list: Any, lo: Any, hi: Any, trail: Trail) -> bool:
    """Declare real-sorted variable(s) with optional bounds [lo, hi].

    lo/hi can be int, float, Fraction, or None for unbounded.
    Ground values are checked against bounds (returns False if out of range).
    For unbound Vars, registers them as RealSort and posts bound constraints.
    """
    state = get_z3_state(trail)
    lo_val = deref(lo) if lo is not None else None
    hi_val = deref(hi) if hi is not None else None

    for v in _as_list(var_or_list):
        v = deref(v)
        if not is_var(v):
            # Ground: check membership
            if lo_val is not None and v < lo_val:
                return False
            if hi_val is not None and v > hi_val:
                return False
            continue
        z3_v = z3_var_for(v, _z3.RealSort(), trail)
        z3_push(trail)
        if lo_val is not None:
            state.solver.add(z3_v >= _to_z3_real(lo_val))
        if hi_val is not None:
            state.solver.add(z3_v <= _to_z3_real(hi_val))

    return True


def _z3_real_binary(l: Any, r: Any, trail: Trail, op) -> bool:
    """Translate l and r to Z3 RealSort expressions and post op(l, r).

    Wraps in a z3_push scope so the constraint is retracted on backtracking.
    """
    state = get_z3_state(trail)
    z3_l = clausal_to_z3(l, trail, default_sort=_z3.RealSort())
    z3_r = clausal_to_z3(r, trail, default_sort=_z3.RealSort())
    z3_push(trail)
    state.solver.add(op(z3_l, z3_r))
    return True


def z3_real_eq(l: Any, r: Any, trail: Trail) -> bool:
    """Post l == r as a Z3 real constraint."""
    return _z3_real_binary(l, r, trail, lambda a, b: a == b)


def z3_real_ne(l: Any, r: Any, trail: Trail) -> bool:
    """Post l != r as a Z3 real constraint."""
    return _z3_real_binary(l, r, trail, lambda a, b: a != b)


def z3_real_lt(l: Any, r: Any, trail: Trail) -> bool:
    """Post l < r as a Z3 real constraint."""
    return _z3_real_binary(l, r, trail, lambda a, b: a < b)


def z3_real_le(l: Any, r: Any, trail: Trail) -> bool:
    """Post l <= r as a Z3 real constraint."""
    return _z3_real_binary(l, r, trail, lambda a, b: a <= b)


def z3_real_gt(l: Any, r: Any, trail: Trail) -> bool:
    """Post l > r as a Z3 real constraint."""
    return _z3_real_binary(l, r, trail, lambda a, b: a > b)


def z3_real_ge(l: Any, r: Any, trail: Trail) -> bool:
    """Post l >= r as a Z3 real constraint."""
    return _z3_real_binary(l, r, trail, lambda a, b: a >= b)


def label_z3_real(vars_list: Any, trail: Trail):
    """Find one satisfying assignment for real-valued Z3 variables.

    Yields at most one solution — real domains are continuous so enumeration
    is not meaningful. Use maximize_z3/minimize_z3 for optimization.
    Bindings are undone after the caller resumes the generator.
    """
    state = get_z3_state(trail)
    items = _as_list(vars_list)

    z3_vars: list = []
    clausal_vars: list = []
    for v in items:
        v = deref(v)
        if is_var(v):
            z3_v = state.var_map.get(id(v))
            if z3_v is None:
                raise ValueError(
                    "label_z3_real: variable not registered with Z3. "
                    "Declare it first with in_z3_real()."
                )
            z3_vars.append(z3_v)
            clausal_vars.append(v)
        elif isinstance(v, (int, float, Fraction)):
            pass  # already ground
        else:
            raise TypeError(
                f"label_z3_real: expected numeric or Var, got {type(v).__name__}"
            )

    if not z3_vars:
        if z3_check(trail):
            yield None
        return

    if state.solver.check() == _z3.sat:
        m = state.solver.model()
        values = [z3_to_python(m.eval(z3v, model_completion=True))
                  for z3v in z3_vars]
        mark = trail.mark()
        ok = all(unify(cv, val, trail)
                 for cv, val in zip(clausal_vars, values))
        if ok:
            yield None
        trail.undo(mark)


def _z3_optimize(expr: Any, trail: Trail, direction: str):
    """Internal helper: run Z3 Optimize in the given direction ('max' or 'min').

    Returns the optimal Python value, or None if infeasible/unbounded-infinite.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(expr, trail, default_sort=_z3.RealSort())

    opt = _z3.Optimize()
    for a in state.solver.assertions():
        opt.add(a)

    if direction == 'max':
        handle = opt.maximize(z3_expr)
    else:
        handle = opt.minimize(z3_expr)

    if opt.check() != _z3.sat:
        return None

    # Use the bound from the handle for the optimal value (handles +oo/-oo)
    if direction == 'max':
        bound = opt.upper(handle)
    else:
        bound = opt.lower(handle)

    val = z3_to_python(bound)
    # Detect +oo / -oo strings from Z3
    if isinstance(val, str):
        s = val.strip()
        if s in ('+oo', 'oo'):
            return float('inf')
        if s == '-oo':
            return float('-inf')
        return None  # unknown or error
    return val


def maximize_z3(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Maximize a linear/nonlinear expression subject to current Z3 constraints.

    Uses Z3's Optimize solver (snapshot of current assertions).
    Returns False if constraints are infeasible or objective is unbounded.
    """
    val = _z3_optimize(expr, trail, 'max')
    if val is None or val == float('inf'):
        return False
    return unify(result_var, val, trail)


def minimize_z3(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Minimize a linear/nonlinear expression subject to current Z3 constraints.

    Uses Z3's Optimize solver (snapshot of current assertions).
    Returns False if constraints are infeasible or objective is unbounded below.
    """
    val = _z3_optimize(expr, trail, 'min')
    if val is None or val == float('-inf'):
        return False
    return unify(result_var, val, trail)


def entailed_z3(constraint_expr: Any, trail: Trail) -> bool:
    """Test if a constraint expression is entailed by the current Z3 store.

    Returns True iff constraint_expr is necessarily true given all posted
    constraints (i.e., its negation is unsatisfiable).

    constraint_expr should be a Clausal comparison AST node (ArithEq, LtE,
    GtE, etc.) or any expression that translates to a Z3 BoolRef.
    """
    state = get_z3_state(trail)
    z3_constr = clausal_to_z3(constraint_expr, trail, default_sort=_z3.RealSort())
    state.solver.push()
    state.solver.add(_z3.Not(z3_constr))
    result = state.solver.check()
    state.solver.pop()
    return result == _z3.unsat


def sup_z3(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Compute supremum (maximum) of expr subject to current Z3 constraints."""
    return maximize_z3(expr, result_var, trail)


def inf_z3(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Compute infimum (minimum) of expr subject to current Z3 constraints."""
    return minimize_z3(expr, result_var, trail)
