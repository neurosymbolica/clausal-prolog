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

from clausal.logic.atoms import is_atom, mint, spelling
from clausal.logic.variables import (
    present_number,
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
    CompareChain as _CompareChain,
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
        self._soft_constraints: list = []   # list of (z3_expr, weight, group) | None


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

    # ── Z3 expressions passed through directly ────────────────────────────────
    if isinstance(expr, _z3.ExprRef):
        return expr

    # ── Ground values ────────────────────────────────────────────────────────
    # bool must come before int (bool is a subclass of int)
    if isinstance(expr, bool):
        return _z3.BoolVal(expr)
    if isinstance(expr, int):
        # When default_sort is a BitVecSort, emit BitVecVal instead of IntVal
        if (default_sort is not None and _z3.is_bv_sort(default_sort)):
            return _z3.BitVecVal(expr, default_sort)
        if default_sort == _z3.RealSort():
            return _z3.RealVal(expr)
        return _z3.IntVal(expr)
    if isinstance(expr, float):
        return _z3.RealVal(expr)
    if isinstance(expr, Fraction):
        return _z3.RealVal(expr.numerator) / _z3.RealVal(expr.denominator)
    if isinstance(expr, str):
        return _z3.StringVal(expr)

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
        l = clausal_to_z3(expr.left, trail, default_sort)
        r = clausal_to_z3(expr.right, trail, default_sort)
        if default_sort is not None and _z3.is_bv_sort(default_sort):
            return _z3.ULT(l, r)
        return l < r
    if isinstance(expr, _LtE):
        l = clausal_to_z3(expr.left, trail, default_sort)
        r = clausal_to_z3(expr.right, trail, default_sort)
        if default_sort is not None and _z3.is_bv_sort(default_sort):
            return _z3.ULE(l, r)
        return l <= r
    if isinstance(expr, _Gt):
        l = clausal_to_z3(expr.left, trail, default_sort)
        r = clausal_to_z3(expr.right, trail, default_sort)
        if default_sort is not None and _z3.is_bv_sort(default_sort):
            return _z3.UGT(l, r)
        return l > r
    if isinstance(expr, _GtE):
        l = clausal_to_z3(expr.left, trail, default_sort)
        r = clausal_to_z3(expr.right, trail, default_sort)
        if default_sort is not None and _z3.is_bv_sort(default_sort):
            return _z3.UGE(l, r)
        return l >= r

    # ── Chained comparisons (1 <= X <= 10) ──────────────────────────────────
    if isinstance(expr, _CompareChain):
        parts = [clausal_to_z3(cmp, trail, default_sort)
                 for cmp in expr.comparisons]
        return _z3.And(*parts) if len(parts) > 1 else parts[0]

    # ── Boolean / bitwise operators ─────────────────────────────────────────
    # In BV context, BitAnd/BitOr/BitXor/Invert produce BV operations.
    # In Bool context, they produce logical And/Or/Xor/Not.
    _bv_context = (default_sort is not None and _z3.is_bv_sort(default_sort))

    if isinstance(expr, _BitAnd):
        if _bv_context:
            return (clausal_to_z3(expr.left, trail, default_sort) &
                    clausal_to_z3(expr.right, trail, default_sort))
        bool_sort = _z3.BoolSort()
        return _z3.And(clausal_to_z3(expr.left, trail, bool_sort),
                       clausal_to_z3(expr.right, trail, bool_sort))
    if isinstance(expr, _BitOr):
        if _bv_context:
            return (clausal_to_z3(expr.left, trail, default_sort) |
                    clausal_to_z3(expr.right, trail, default_sort))
        bool_sort = _z3.BoolSort()
        return _z3.Or(clausal_to_z3(expr.left, trail, bool_sort),
                      clausal_to_z3(expr.right, trail, bool_sort))
    if isinstance(expr, _BitXor):
        if _bv_context:
            return (clausal_to_z3(expr.left, trail, default_sort) ^
                    clausal_to_z3(expr.right, trail, default_sort))
        bool_sort = _z3.BoolSort()
        return _z3.Xor(clausal_to_z3(expr.left, trail, bool_sort),
                       clausal_to_z3(expr.right, trail, bool_sort))
    if isinstance(expr, _Invert):
        if _bv_context:
            return ~clausal_to_z3(expr.operand, trail, default_sort)
        bool_sort = _z3.BoolSort()
        return _z3.Not(clausal_to_z3(expr.operand, trail, bool_sort))
    if isinstance(expr, _And):
        bool_sort = _z3.BoolSort()
        return _z3.And(clausal_to_z3(expr.left, trail, bool_sort),
                       clausal_to_z3(expr.right, trail, bool_sort))
    if isinstance(expr, _Or):
        bool_sort = _z3.BoolSort()
        return _z3.Or(clausal_to_z3(expr.left, trail, bool_sort),
                      clausal_to_z3(expr.right, trail, bool_sort))
    if isinstance(expr, _Not):
        bool_sort = _z3.BoolSort()
        return _z3.Not(clausal_to_z3(expr.operand, trail, bool_sort))

    raise TypeError(
        f"Cannot translate {type(expr).__name__!r} to Z3: {expr!r}"
    )


# ── Value conversion ──────────────────────────────────────────────────────────

def z3_to_python(z3_val: Any) -> int | float | Fraction | str:
    """Convert a Z3 model value to a Python value.

    Mapping:
    - Z3 integer       → Python int
    - Z3 rational      → Fraction (exact); int when integral
    - Z3 true/false    → 1 / 0  (Clausal uses 0/1 for booleans)
    - Z3 bitvector     → Python int (unsigned)
    - Z3 string        → Python str
    - Z3 algebraic     → float approximation
    - Other            → str (fallback)
    """
    if _z3.is_int_value(z3_val):
        return z3_val.as_long()
    if _z3.is_rational_value(z3_val):
        # Z3 answers a Real-sorted value as a rational even when it is whole.
        # An integral rational presents as int, as every other binder in the
        # engine does (``present_number``): ``Fraction(5, 1)`` is not the term
        # ``5`` in the standard order.
        return present_number(
            Fraction(z3_val.numerator_as_long(), z3_val.denominator_as_long()))
    if _z3.is_true(z3_val):
        return 1
    if _z3.is_false(z3_val):
        return 0
    if _z3.is_bv_value(z3_val):
        return z3_val.as_long()
    if _z3.is_string_value(z3_val):
        return z3_val.as_string()
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


def _build_optimize(state: Z3State, trail: Trail) -> Any:
    """Create a fresh Z3 Optimize instance from current solver state.

    Copies hard assertions and active soft constraints.
    """
    opt = _z3.Optimize()
    for a in state.solver.assertions():
        opt.add(a)
    for entry in state._soft_constraints:
        if entry is not None:
            z3_expr, weight, group = entry
            if group is not None:
                opt.add_soft(z3_expr, weight, id=group)
            else:
                opt.add_soft(z3_expr, weight)
    return opt


def _z3_optimize(expr: Any, trail: Trail, direction: str):
    """Internal helper: run Z3 Optimize in the given direction ('max' or 'min').

    Returns the optimal Python value, or None if infeasible/unbounded-infinite.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(expr, trail, default_sort=_z3.RealSort())

    opt = _build_optimize(state, trail)

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


# ── Phase 5: UserPropagateBase integration ────────────────────────────────────

_PROP_FAIL = object()  # sentinel for propagator goal failure


class ClausalPropagator(_z3.UserPropagateBase):
    """Bridge between Z3's CDCL solver and Clausal's trail/backtracking.

    Registered push/pop callbacks keep the Clausal trail in sync with Z3's
    CDCL decision stack.  Optional on_fixed_goals run inside an inner
    trampoline when Z3 assigns a registered variable.

    Usage pattern::

        state = get_z3_state(trail)
        prop = ClausalPropagator(state.solver, trail, state.var_map, state.rev_map,
                                 on_fixed_goals=[my_goal_factory])
        prop.add(state.var_map[id(x)])   # register x for fixed callbacks
        state.solver.check()             # CDCL loop; callbacks fire here

    The propagator reference must be kept alive (store it in state._propagators).
    """

    def __init__(
        self,
        s: Any,
        trail: Trail,
        var_map: dict,
        rev_map: dict,
        *,
        on_fixed_goals: list | None = None,
        on_final_goal: Any = None,
        _fresh_ctx: Any = None,
    ) -> None:
        if _fresh_ctx is not None:
            super().__init__(None, ctx=_fresh_ctx)
        else:
            super().__init__(s)
        self.trail = trail
        self.var_map = var_map
        self.rev_map = rev_map
        self.scope_marks: list = []
        self.on_fixed_goals: list = on_fixed_goals or []
        self.on_final_goal = on_final_goal

        if s is not None:
            if self.on_fixed_goals:
                self.add_fixed(self._handle_fixed)
            if self.on_final_goal is not None:
                self.add_final(self._handle_final)

    # ── Z3 CDCL callbacks ─────────────────────────────────────────────────────

    def push(self) -> None:
        """Z3 is making a CDCL decision. Save trail state."""
        self.scope_marks.append(self.trail.mark())

    def pop(self, num_scopes: int) -> None:
        """Z3 is backtracking. Restore trail state."""
        for _ in range(num_scopes):
            mark = self.scope_marks.pop()
            self.trail.undo(mark)

    def fresh(self, new_ctx: Any) -> 'ClausalPropagator':
        """Z3 needs a propagator clone for a parallel solving context.

        Creates a new propagator with a fresh Trail. var_map/rev_map are
        shared (read-only during solving).
        """
        new_trail = Trail()
        return ClausalPropagator(
            None, new_trail, self.var_map, self.rev_map,
            on_fixed_goals=self.on_fixed_goals,
            on_final_goal=self.on_final_goal,
            _fresh_ctx=new_ctx,
        )

    # ── Callback handlers ─────────────────────────────────────────────────────

    def _handle_fixed(self, z3_var: Any, z3_value: Any) -> None:
        """Z3 assigned z3_var to z3_value — run registered Clausal goals."""
        z3_id = z3_var.get_id()
        clausal_var = self.rev_map.get(z3_id)
        if clausal_var is None:
            return  # not a Clausal-tracked variable

        value = z3_to_python(z3_value)

        for goal_factory in self.on_fixed_goals:
            try:
                result = self._run_goal(goal_factory, clausal_var, value)
            except Exception:
                self.conflict([z3_var])
                return

            if result is _PROP_FAIL:
                self.conflict([z3_var])
                return

            if result is not None:
                for z3_consequence in result:
                    self.propagate(z3_consequence, [z3_var])

    def _handle_final(self) -> None:
        """Z3 found a complete model — optionally verify with Clausal."""
        if self.on_final_goal is None:
            return
        try:
            result = self._run_goal_simple(self.on_final_goal)
        except Exception:
            self.conflict([])
            return
        if result is _PROP_FAIL:
            self.conflict([])

    # ── Inner trampoline ──────────────────────────────────────────────────────

    def _run_goal(self, goal_factory: Any, var: Any, value: Any) -> Any:
        """Run a Clausal goal inside a fresh trampoline.

        goal_factory(var, value, trail) should return a StepGenerator or
        plain generator.  Returns None (success), a list of Z3 BoolRef
        consequences, or _PROP_FAIL.
        """
        from clausal.logic.trampoline import StepGenerator, trampoline

        gen_or_sg = goal_factory(var, value, self.trail)
        try:
            if isinstance(gen_or_sg, StepGenerator):
                trampoline(gen_or_sg)
            else:
                for _ in gen_or_sg:
                    pass
            return None
        except Exception:
            return _PROP_FAIL

    def _run_goal_simple(self, goal: Any) -> Any:
        """Run a no-argument Clausal goal inside a fresh trampoline."""
        from clausal.logic.trampoline import StepGenerator, trampoline

        if callable(goal):
            gen_or_sg = goal(self.trail)
            try:
                if isinstance(gen_or_sg, StepGenerator):
                    trampoline(gen_or_sg)
                else:
                    for _ in gen_or_sg:
                        pass
                return None
            except Exception:
                return _PROP_FAIL
        return _PROP_FAIL


def z3_table(vars_list: Any, tuples_list: Any, trail: Trail) -> bool:
    """Table (extensional) constraint: the tuple of variables must match one of
    the given tuples.

    Encoded as a disjunction of conjunctions — suitable for small to medium
    tables.  For large tables (thousands of rows), a UserPropagateBase-based
    incremental filtering approach would be more efficient (deferred).

    Each element in vars_list can be a Var or a ground integer value.
    Each tuple in tuples_list is a list/cons-list of integer values.
    """
    state = get_z3_state(trail)
    vars_items = _as_list(vars_list)
    tuples_items = _as_list(tuples_list)

    # Translate each variable position to a Z3 IntSort expression
    z3_pos = [clausal_to_z3(deref(v), trail, default_sort=_z3.IntSort())
              for v in vars_items]

    if not tuples_items:
        # Empty table → unsatisfiable
        z3_push(trail)
        state.solver.add(_z3.BoolVal(False))
        return True

    clauses: list = []
    for raw_tup in tuples_items:
        tup_items = _as_list(raw_tup)
        if len(tup_items) != len(z3_pos):
            raise ValueError(
                f"z3_table: tuple length {len(tup_items)} "
                f"!= vars length {len(z3_pos)}"
            )
        conj_parts = [
            z3_pos[i] == clausal_to_z3(deref(tup_items[i]), trail, default_sort=_z3.IntSort())
            for i in range(len(z3_pos))
        ]
        clauses.append(_z3.And(conj_parts))

    z3_push(trail)
    state.solver.add(_z3.Or(clauses))
    return True


# ── Phase 6: advanced theories ────────────────────────────────────────────────

# ── BV helpers ────────────────────────────────────────────────────────────────

def _z3_bv_expr(val: Any, trail: Trail) -> Any:
    """Return the Z3 BitVec expression for a registered Clausal Var.

    Raises ValueError if the var is not yet registered with in_z3_bv().
    """
    val = deref(val)
    if is_var(val):
        state = get_z3_state(trail)
        z3_v = state.var_map.get(id(val))
        if z3_v is None:
            raise ValueError(
                "BV variable not registered with Z3. Call in_z3_bv first."
            )
        return z3_v
    raise TypeError(
        f"_z3_bv_expr: expected registered BV Var, got {type(val).__name__!r}"
    )


def _z3_bv_val(val: Any, sort: Any, trail: Trail) -> Any:
    """Convert val to a Z3 BitVec expression of the given sort.

    - int → BitVecVal(val, sort)
    - registered Var → existing Z3 constant
    - unregistered Var → auto-register with sort
    """
    val = deref(val)
    if isinstance(val, int):
        return _z3.BitVecVal(val, sort)
    if is_var(val):
        state = get_z3_state(trail)
        existing = state.var_map.get(id(val))
        if existing is not None:
            return existing
        return z3_var_for(val, sort, trail)
    raise TypeError(
        f"_z3_bv_val: expected int or Var, got {type(val).__name__!r}"
    )


def _bv_binop(x: Any, y: Any, result: Any, op, trail: Trail) -> bool:
    """Post result == op(x, y) for BV operands of the same sort."""
    state = get_z3_state(trail)
    z3_x = _z3_bv_expr(x, trail)
    sort = z3_x.sort()
    z3_y = _z3_bv_val(y, sort, trail)
    z3_r = _z3_bv_val(result, sort, trail)
    z3_push(trail)
    state.solver.add(z3_r == op(z3_x, z3_y))
    return True


def _bv_unop(x: Any, result: Any, op, trail: Trail) -> bool:
    """Post result == op(x) for a BV unary operation."""
    state = get_z3_state(trail)
    z3_x = _z3_bv_expr(x, trail)
    z3_r = _z3_bv_val(result, z3_x.sort(), trail)
    z3_push(trail)
    state.solver.add(z3_r == op(z3_x))
    return True


def _bv_cmp(x: Any, y: Any, trail: Trail, op) -> bool:
    """Post a BV comparison constraint (signed or unsigned)."""
    state = get_z3_state(trail)
    z3_x = _z3_bv_expr(x, trail)
    z3_y = _z3_bv_val(y, z3_x.sort(), trail)
    z3_push(trail)
    state.solver.add(op(z3_x, z3_y))
    return True


# ── Bitvectors ────────────────────────────────────────────────────────────────

def in_z3_bv(var_or_list: Any, width: int, trail: Trail) -> bool:
    """Declare bitvector variable(s) of the given bit-width.

    The variable is registered with BitVecSort(width) but no domain
    constraints are posted — the full 2^width range is available.
    """
    for v in _as_list(var_or_list):
        v = deref(v)
        if is_var(v):
            z3_var_for(v, _z3.BitVecSort(width), trail)
        elif isinstance(v, int):
            pass  # ground — nothing to register
        else:
            raise TypeError(
                f"in_z3_bv: expected int or Var, got {type(v).__name__!r}"
            )
    return True


def label_z3_bv(vars_list: Any, trail: Trail):
    """Enumerate bitvector solutions via blocking clauses.

    Generator: yields None for each solution with vars bound to int values.
    Same blocking-clause pattern as label_z3 for integers.
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
                    "label_z3_bv: variable not registered. Call in_z3_bv first."
                )
            z3_vars.append(z3_v)
            clausal_vars.append(v)
        elif isinstance(v, int):
            pass  # already ground
        else:
            raise TypeError(
                f"label_z3_bv: expected int or Var, got {type(v).__name__!r}"
            )

    if not z3_vars:
        if z3_check(trail):
            yield None
        return

    z3_push(trail)

    while state.solver.check() == _z3.sat:
        m = state.solver.model()
        values = [z3_to_python(m.eval(z3v, model_completion=True))
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


# BV arithmetic (result-binding)
def bv_add(x, y, result, trail): return _bv_binop(x, y, result, lambda a,b: a+b, trail)
def bv_sub(x, y, result, trail): return _bv_binop(x, y, result, lambda a,b: a-b, trail)
def bv_mul(x, y, result, trail): return _bv_binop(x, y, result, lambda a,b: a*b, trail)
def bv_udiv(x, y, result, trail): return _bv_binop(x, y, result, _z3.UDiv, trail)
def bv_sdiv(x, y, result, trail): return _bv_binop(x, y, result, lambda a,b: a/b, trail)
def bv_urem(x, y, result, trail): return _bv_binop(x, y, result, _z3.URem, trail)
def bv_srem(x, y, result, trail): return _bv_binop(x, y, result, _z3.SRem, trail)

# BV bitwise (result-binding)
def bv_and(x, y, result, trail): return _bv_binop(x, y, result, lambda a,b: a&b, trail)
def bv_or(x, y, result, trail):  return _bv_binop(x, y, result, lambda a,b: a|b, trail)
def bv_xor(x, y, result, trail): return _bv_binop(x, y, result, lambda a,b: a^b, trail)
def bv_not(x, result, trail):    return _bv_unop(x, result, lambda a: ~a, trail)

# BV shifts (result-binding)
def bv_shl(x, n, result, trail):  return _bv_binop(x, n, result, lambda a,b: a<<b, trail)
def bv_lshr(x, n, result, trail): return _bv_binop(x, n, result, _z3.LShR, trail)
def bv_ashr(x, n, result, trail): return _bv_binop(x, n, result, lambda a,b: a>>b, trail)

# BV signed comparisons (constraint-posting)
def bv_eq(x, y, trail):  return _bv_cmp(x, y, trail, lambda a,b: a==b)
def bv_ne(x, y, trail):  return _bv_cmp(x, y, trail, lambda a,b: a!=b)
def bv_slt(x, y, trail): return _bv_cmp(x, y, trail, lambda a,b: a<b)
def bv_sle(x, y, trail): return _bv_cmp(x, y, trail, lambda a,b: a<=b)
def bv_sgt(x, y, trail): return _bv_cmp(x, y, trail, lambda a,b: a>b)
def bv_sge(x, y, trail): return _bv_cmp(x, y, trail, lambda a,b: a>=b)

# BV unsigned comparisons (constraint-posting)
def bv_ult(x, y, trail): return _bv_cmp(x, y, trail, _z3.ULT)
def bv_ule(x, y, trail): return _bv_cmp(x, y, trail, _z3.ULE)
def bv_ugt(x, y, trail): return _bv_cmp(x, y, trail, _z3.UGT)
def bv_uge(x, y, trail): return _bv_cmp(x, y, trail, _z3.UGE)


def bv_concat(x: Any, y: Any, result: Any, trail: Trail) -> bool:
    """Post result == Concat(x, y). Result width = width(x) + width(y)."""
    state = get_z3_state(trail)
    z3_x = _z3_bv_expr(x, trail)
    z3_y = _z3_bv_expr(y, trail)
    result_sort = _z3.BitVecSort(z3_x.size() + z3_y.size())
    z3_r = _z3_bv_val(result, result_sort, trail)
    z3_push(trail)
    state.solver.add(z3_r == _z3.Concat(z3_x, z3_y))
    return True


def bv_extract(hi: int, lo: int, x: Any, result: Any, trail: Trail) -> bool:
    """Post result == Extract(hi, lo, x). Result width = hi - lo + 1."""
    state = get_z3_state(trail)
    z3_x = _z3_bv_expr(x, trail)
    result_sort = _z3.BitVecSort(hi - lo + 1)
    z3_r = _z3_bv_val(result, result_sort, trail)
    z3_push(trail)
    state.solver.add(z3_r == _z3.Extract(hi, lo, z3_x))
    return True


def bv_zext(x: Any, n: int, result: Any, trail: Trail) -> bool:
    """Post result == ZeroExt(n, x). Result width = width(x) + n."""
    state = get_z3_state(trail)
    z3_x = _z3_bv_expr(x, trail)
    result_sort = _z3.BitVecSort(z3_x.size() + n)
    z3_r = _z3_bv_val(result, result_sort, trail)
    z3_push(trail)
    state.solver.add(z3_r == _z3.ZeroExt(n, z3_x))
    return True


def bv_sext(x: Any, n: int, result: Any, trail: Trail) -> bool:
    """Post result == SignExt(n, x). Result width = width(x) + n."""
    state = get_z3_state(trail)
    z3_x = _z3_bv_expr(x, trail)
    result_sort = _z3.BitVecSort(z3_x.size() + n)
    z3_r = _z3_bv_val(result, result_sort, trail)
    z3_push(trail)
    state.solver.add(z3_r == _z3.SignExt(n, z3_x))
    return True


# ── Arrays ────────────────────────────────────────────────────────────────────

def z3_array(var: Any, domain_sort: Any, range_sort: Any, trail: Trail) -> bool:
    """Declare an array variable: Array(domain_sort → range_sort).

    domain_sort and range_sort are Z3 sort objects (e.g., _z3.IntSort()).
    """
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"z3_array: expected Var, got {type(var).__name__!r}")
    z3_var_for(var, _z3.ArraySort(domain_sort, range_sort), trail)
    return True


def z3_select(array: Any, index: Any, value: Any, trail: Trail) -> bool:
    """Post Select(array, index) == value.

    If value is an unbound Var, auto-registers it with the array's range sort.
    """
    state = get_z3_state(trail)
    z3_arr = clausal_to_z3(array, trail)
    z3_idx = clausal_to_z3(index, trail, default_sort=z3_arr.sort().domain())
    range_sort = z3_arr.sort().range()
    value_d = deref(value)
    z3_val = (z3_var_for(value_d, range_sort, trail) if is_var(value_d)
              else clausal_to_z3(value_d, trail, default_sort=range_sort))
    z3_push(trail)
    state.solver.add(_z3.Select(z3_arr, z3_idx) == z3_val)
    return True


def z3_store(array: Any, index: Any, value: Any, result: Any, trail: Trail) -> bool:
    """Post result == Store(array, index, value).

    If result is an unbound Var, auto-registers it with the array's sort.
    """
    state = get_z3_state(trail)
    z3_arr = clausal_to_z3(array, trail)
    arr_sort = z3_arr.sort()
    z3_idx = clausal_to_z3(index, trail, default_sort=arr_sort.domain())
    z3_val = clausal_to_z3(value, trail, default_sort=arr_sort.range())
    result_d = deref(result)
    z3_res = (z3_var_for(result_d, arr_sort, trail) if is_var(result_d)
              else clausal_to_z3(result_d, trail))
    z3_push(trail)
    state.solver.add(z3_res == _z3.Store(z3_arr, z3_idx, z3_val))
    return True


def z3_const_array(value: Any, domain_sort: Any, result: Any, trail: Trail) -> bool:
    """Post result == K(domain_sort, value) — array where every index maps to value."""
    state = get_z3_state(trail)
    z3_val = clausal_to_z3(value, trail)
    arr = _z3.K(domain_sort, z3_val)
    result_d = deref(result)
    z3_res = (z3_var_for(result_d, arr.sort(), trail) if is_var(result_d)
              else clausal_to_z3(result_d, trail))
    z3_push(trail)
    state.solver.add(z3_res == arr)
    return True


# ── Sets ──────────────────────────────────────────────────────────────────────

def z3_set(var: Any, elem_sort: Any, trail: Trail) -> bool:
    """Declare a set variable over elem_sort (encoded as Array(elem_sort, Bool))."""
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"z3_set: expected Var, got {type(var).__name__!r}")
    z3_var_for(var, _z3.SetSort(elem_sort), trail)
    return True


def z3_set_member(elem: Any, s: Any, trail: Trail) -> bool:
    """Post elem ∈ s."""
    state = get_z3_state(trail)
    z3_e = clausal_to_z3(elem, trail)
    z3_s = clausal_to_z3(s, trail)
    z3_push(trail)
    state.solver.add(_z3.IsMember(z3_e, z3_s))
    return True


def z3_set_not_member(elem: Any, s: Any, trail: Trail) -> bool:
    """Post elem ∉ s."""
    state = get_z3_state(trail)
    z3_e = clausal_to_z3(elem, trail)
    z3_s = clausal_to_z3(s, trail)
    z3_push(trail)
    state.solver.add(_z3.Not(_z3.IsMember(z3_e, z3_s)))
    return True


def z3_set_subset(s1: Any, s2: Any, trail: Trail) -> bool:
    """Post s1 ⊆ s2."""
    state = get_z3_state(trail)
    z3_s1 = clausal_to_z3(s1, trail)
    z3_s2 = clausal_to_z3(s2, trail)
    z3_push(trail)
    state.solver.add(_z3.IsSubset(z3_s1, z3_s2))
    return True


def z3_set_union(s1: Any, s2: Any, result: Any, trail: Trail) -> bool:
    """Post result == s1 ∪ s2."""
    state = get_z3_state(trail)
    z3_s1 = clausal_to_z3(s1, trail)
    z3_s2 = clausal_to_z3(s2, trail)
    result_d = deref(result)
    z3_r = (z3_var_for(result_d, z3_s1.sort(), trail) if is_var(result_d)
            else clausal_to_z3(result_d, trail))
    z3_push(trail)
    state.solver.add(z3_r == _z3.SetUnion(z3_s1, z3_s2))
    return True


def z3_set_intersect(s1: Any, s2: Any, result: Any, trail: Trail) -> bool:
    """Post result == s1 ∩ s2."""
    state = get_z3_state(trail)
    z3_s1 = clausal_to_z3(s1, trail)
    z3_s2 = clausal_to_z3(s2, trail)
    result_d = deref(result)
    z3_r = (z3_var_for(result_d, z3_s1.sort(), trail) if is_var(result_d)
            else clausal_to_z3(result_d, trail))
    z3_push(trail)
    state.solver.add(z3_r == _z3.SetIntersect(z3_s1, z3_s2))
    return True


def z3_set_add(s: Any, elem: Any, result: Any, trail: Trail) -> bool:
    """Post result == s ∪ {elem}."""
    state = get_z3_state(trail)
    z3_s = clausal_to_z3(s, trail)
    z3_e = clausal_to_z3(elem, trail)
    result_d = deref(result)
    z3_r = (z3_var_for(result_d, z3_s.sort(), trail) if is_var(result_d)
            else clausal_to_z3(result_d, trail))
    z3_push(trail)
    state.solver.add(z3_r == _z3.SetAdd(z3_s, z3_e))
    return True


# ── Strings ───────────────────────────────────────────────────────────────────

def z3_string(var: Any, trail: Trail) -> bool:
    """Declare a string variable."""
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"z3_string: expected Var, got {type(var).__name__!r}")
    z3_var_for(var, _z3.StringSort(), trail)
    return True


def z3_str_length(s: Any, n: Any, trail: Trail) -> bool:
    """Post Length(s) == n."""
    state = get_z3_state(trail)
    z3_s = clausal_to_z3(s, trail, default_sort=_z3.StringSort())
    n_d = deref(n)
    z3_n = (z3_var_for(n_d, _z3.IntSort(), trail) if is_var(n_d)
            else clausal_to_z3(n_d, trail, default_sort=_z3.IntSort()))
    z3_push(trail)
    state.solver.add(_z3.Length(z3_s) == z3_n)
    return True


def z3_str_contains(s: Any, substr: Any, trail: Trail) -> bool:
    """Post Contains(s, substr)."""
    state = get_z3_state(trail)
    z3_s = clausal_to_z3(s, trail, default_sort=_z3.StringSort())
    z3_sub = clausal_to_z3(deref(substr), trail, default_sort=_z3.StringSort())
    z3_push(trail)
    state.solver.add(_z3.Contains(z3_s, z3_sub))
    return True


def z3_str_concat(s1: Any, s2: Any, result: Any, trail: Trail) -> bool:
    """Post result == Concat(s1, s2)."""
    state = get_z3_state(trail)
    z3_s1 = clausal_to_z3(s1, trail, default_sort=_z3.StringSort())
    z3_s2 = clausal_to_z3(s2, trail, default_sort=_z3.StringSort())
    result_d = deref(result)
    z3_r = (z3_var_for(result_d, _z3.StringSort(), trail) if is_var(result_d)
            else clausal_to_z3(result_d, trail, default_sort=_z3.StringSort()))
    z3_push(trail)
    state.solver.add(z3_r == _z3.Concat(z3_s1, z3_s2))
    return True


def z3_str_regex(s: Any, pattern: Any, trail: Trail) -> bool:
    """Post InRe(s, pattern) — s matches the Z3 regex pattern.

    pattern can be a Z3 ReRef (built with z3.Re, z3.Star, etc.) or a
    string (converted via z3.Re).
    """
    state = get_z3_state(trail)
    z3_s = clausal_to_z3(s, trail, default_sort=_z3.StringSort())
    if isinstance(pattern, str):
        z3_re = _z3.Re(pattern)
    else:
        z3_re = pattern
    z3_push(trail)
    state.solver.add(_z3.InRe(z3_s, z3_re))
    return True


def label_z3_str(var: Any, trail: Trail):
    """Find one satisfying assignment for a Z3 string variable.

    Yields at most one solution (string domains are infinite).
    Bindings are undone after the caller resumes the generator.
    """
    state = get_z3_state(trail)
    v = deref(var)
    if not is_var(v):
        yield None
        return

    z3_v = state.var_map.get(id(v))
    if z3_v is None:
        raise ValueError(
            "label_z3_str: variable not registered. Call z3_string first."
        )

    if state.solver.check() == _z3.sat:
        m = state.solver.model()
        val = z3_to_python(m.eval(z3_v, model_completion=True))
        mark = trail.mark()
        if unify(v, val, trail):
            yield None
        trail.undo(mark)


# ── Uninterpreted functions ───────────────────────────────────────────────────

class Z3FuncInfo:
    """Metadata for a Z3 uninterpreted function, stored as a Var attribute."""
    __slots__ = ('func', 'domain_sorts', 'range_sort')

    def __init__(self, func: Any, domain_sorts: list, range_sort: Any) -> None:
        self.func = func
        self.domain_sorts = domain_sorts
        self.range_sort = range_sort


def z3_function(var: Any, domain_sorts: list, range_sort: Any, trail: Trail) -> bool:
    """Declare an uninterpreted function and attach it to a Clausal Var.

    domain_sorts: list of Z3 sort objects for argument types
    range_sort: Z3 sort for return type

    The function declaration is stored as a Z3FuncInfo attribute on var.
    """
    state = get_z3_state(trail)
    state._counter += 1
    func = _z3.Function(f"uf_{state._counter}", *domain_sorts, range_sort)
    var_d = deref(var)
    if not is_var(var_d):
        raise TypeError(f"z3_function: expected Var, got {type(var_d).__name__!r}")
    put_attr(var_d, Z3_KEY, Z3FuncInfo(func, domain_sorts, range_sort), trail)
    return True


def z3_app(func_var: Any, args: list, result: Any, trail: Trail) -> bool:
    """Post result == func_var(args...) for an uninterpreted function.

    func_var must have been declared with z3_function.
    """
    state = get_z3_state(trail)
    info = get_attr(deref(func_var), Z3_KEY)
    if not isinstance(info, Z3FuncInfo):
        raise TypeError(
            "z3_app: func_var is not an uninterpreted function. "
            "Declare it first with z3_function."
        )
    args_list = _as_list(args)
    z3_args = [clausal_to_z3(deref(a), trail, default_sort=info.domain_sorts[i])
               for i, a in enumerate(args_list)]
    result_d = deref(result)
    z3_r = (z3_var_for(result_d, info.range_sort, trail) if is_var(result_d)
            else clausal_to_z3(result_d, trail, default_sort=info.range_sort))
    z3_push(trail)
    state.solver.add(z3_r == info.func(*z3_args))
    return True


# ── Quantifiers ───────────────────────────────────────────────────────────────

def z3_forall(var_sorts: list, body_fn, trail: Trail) -> bool:
    """Post a universal quantification ForAll(vars, body).

    var_sorts: list of (name, sort) pairs for quantified variables.
    body_fn: callable taking Z3 bound variable expressions, returning a BoolRef.

    Note: Z3's E-matching heuristics handle instantiation. Providing patterns
    via ForAll(..., patterns=[...]) can improve performance but is not exposed
    here — use z3_forall_raw for that.
    """
    state = get_z3_state(trail)
    bound = [_z3.Const(name, sort) for name, sort in var_sorts]
    body = body_fn(*bound)
    z3_push(trail)
    state.solver.add(_z3.ForAll(bound, body))
    return True


def z3_exists(var_sorts: list, body_fn, trail: Trail) -> bool:
    """Post an existential quantification Exists(vars, body).

    var_sorts: list of (name, sort) pairs for quantified variables.
    body_fn: callable taking Z3 bound variable expressions, returning a BoolRef.
    """
    state = get_z3_state(trail)
    bound = [_z3.Const(name, sort) for name, sort in var_sorts]
    body = body_fn(*bound)
    z3_push(trail)
    state.solver.add(_z3.Exists(bound, body))
    return True


# ── Algebraic datatypes ───────────────────────────────────────────────────────

def z3_declare_datatype(name: Any, constructors: list, trail: Trail) -> Any:
    """Declare a Z3 algebraic datatype and store it in Z3State.datatypes.

    constructors: list of (ctor_name, [(field_name, sort_or_typename), ...])
                  Use the datatype's own NAME for self-referential fields.

    The datatype name, every constructor name and every field name are NAME
    positions (§6.4): each is an ATOM, read by spelling through
    :func:`_constraint_name`, and a STRING there is ``type_error(atom, …)``.
    Before that funnel the term went straight to ``_z3.Datatype(...)`` /
    ``dt.declare(...)``, so a source-written ``"IntList"`` — a cell in the
    default ``-double_quotes(atom)`` mode — surfaced as a raw z3
    ``ArgumentError`` from the C bindings.  An unbound name answers ``None``
    and the caller fails, as everywhere else in this module.

    Returns the created Z3 sort object. Also registers the sort under
    state.datatypes[spelling] for later use.

    Example (linked list)::

        z3_declare_datatype(mint("IntList"), [
            (mint("nil"),  []),
            (mint("cons"), [(mint("head"), z3.IntSort()),
                            (mint("tail"), mint("IntList"))]),
        ], trail)
    """
    context = "z3.declare_datatype/2"
    state = get_z3_state(trail)
    name = _constraint_name(name, context)
    if name is None:
        return None
    dt = _z3.Datatype(name)
    for ctor_name, fields in constructors:
        ctor_name = _constraint_name(ctor_name, context)
        if ctor_name is None:
            return None
        processed: list = []
        for fname, fsort in fields:
            fname = _constraint_name(fname, context)
            if fname is None:
                return None
            fsort = deref(fsort)
            # A NAME in the sort slot means "the datatype being declared" —
            # the self-reference form.  It goes through the same funnel, so a
            # STRING there is the same type_error as everywhere else.
            if is_atom(fsort) or type(fsort) is str:
                _constraint_name(fsort, context)
                processed.append((fname, dt))
            else:
                processed.append((fname, fsort))
        dt.declare(ctor_name, *processed)
    sort = dt.create()
    if not hasattr(state, 'datatypes'):
        state.datatypes: dict = {}
    state.datatypes[name] = sort
    return sort


# ══════════════════════════════════════════════════════════════════════════════
# Phase 8 — Diagnostics (Named Constraints, Unsat Cores, Model Inspection)
# ══════════════════════════════════════════════════════════════════════════════


def _constraint_name(name: Any, context: str = "z3_named/2") -> str | None:
    """The SPELLING of a NAME this library hands to Z3, which is an ATOM (§6.4).

    Before THE FLIP (2026-09-06-atoms-as-cells-strings) this was
    ``name = str(name)``, and ``str(("x_big",))`` is the Python tuple REPR
    ``"('x_big',)"`` — so the Z3 indicator, the ``_named_constraints`` key
    and every unsat-core answer carried a repr for the atom every source
    program writes here.  Spec §3 goal 5 wants that class of leak loud.

    An UNBOUND name answers ``None`` and the caller FAILS, matching the two
    sibling funnels this task added (``clpfd._op_spelling``,
    ``attributes._storage_key``): a variable here is a mode signal, not a
    type fault — the term is the right sort, only the binding is missing.
    Every other non-atom, a STRING included, is ``type_error(atom, …)``.

    The one funnel for every name position in this module: the constraint
    name, an option key, a logic name, a datatype/constructor/field name.
    The sites that lacked it passed the raw term to Z3 and got a bare
    ``ArgumentError``/``Z3Exception`` out of the C bindings for the atom a
    source program writes — ``z3_set_option("timeout", 5000)`` and
    ``z3_set_logic("QF_LIA")`` are the documented spellings, and in the
    default ``-double_quotes(atom)`` mode both arrive as cells.

    *context* is the predicate indicator that appears in the ``type_error``.
    """
    name = deref(name)
    if is_atom(name):
        return spelling(name)
    if is_var(name):
        return None
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, type_error,
    )
    raise LogicException(type_error("atom", name, context))


def z3_named(constraint_expr: Any, name: Any, trail: Trail) -> bool:
    """Add a constraint with a name, trackable via unsat core.

    Creates a Boolean indicator: ``indicator => constraint``.
    The indicator is used as an assumption in ``z3_unsat_core``.

    *name* is an ATOM (§6.4); it is stored by its spelling and minted back
    into an atom by ``z3_unsat_core``/``z3_minimal_unsat_core``.  An unbound
    Name fails; a string raises ``type_error(atom, …)``.
    """
    state = get_z3_state(trail)
    name = _constraint_name(name)
    if name is None:
        return False

    z3_expr = clausal_to_z3(constraint_expr, trail, default_sort=_z3.IntSort())
    indicator = _z3.Bool(f"_named_{name}")

    z3_push(trail)
    state.solver.add(_z3.Implies(indicator, z3_expr))

    if not hasattr(state, '_named_constraints'):
        state._named_constraints: dict = {}
    state._named_constraints[name] = indicator
    trail.record(lambda: state._named_constraints.pop(name, None))
    return True


def z3_unsat_core(core_var: Any, trail: Trail) -> bool:
    """Get the unsat core as a sorted list of constraint name ATOMS.

    Checks satisfiability using all named constraints as assumptions.
    If unsatisfiable, *core_var* is unified with the list of names from
    the unsatisfiable subset.  Fails if constraints are satisfiable.

    Names go out as they came in — atoms (§6.4) — so the answer is
    comparable against what the program wrote in ``z3_named/2``.
    """
    state = get_z3_state(trail)
    named = getattr(state, '_named_constraints', {})

    if not named:
        if state.solver.check() == _z3.unsat:
            return unify(core_var, [], trail)
        return False

    indicators = list(named.values())
    ind_to_name = {ind.get_id(): name for name, ind in named.items()}

    result = state.solver.check(*indicators)
    if result == _z3.unsat:
        core = state.solver.unsat_core()
        core_set = {c.get_id() for c in core}
        core_names = [ind_to_name[cid] for cid in core_set if cid in ind_to_name]
        return unify(core_var, [mint(n) for n in sorted(core_names)], trail)
    return False


def z3_minimal_unsat_core(core_var: Any, trail: Trail) -> bool:
    """Get a minimal unsat core (no redundant constraints).

    Uses iterative deletion: removes each assumption and checks if
    the result is still unsatisfiable.  More expensive than
    ``z3_unsat_core`` but guaranteed minimal.
    """
    state = get_z3_state(trail)
    named = getattr(state, '_named_constraints', {})
    if not named:
        return False

    indicators = list(named.values())
    ind_to_name = {ind.get_id(): name for name, ind in named.items()}

    if state.solver.check(*indicators) != _z3.unsat:
        return False

    core = list(state.solver.unsat_core())
    minimal = list(core)
    for c in core:
        candidate = [x for x in minimal if x.get_id() != c.get_id()]
        if state.solver.check(*candidate) == _z3.unsat:
            minimal = candidate

    core_set = {c.get_id() for c in minimal}
    core_names = [ind_to_name[cid] for cid in core_set if cid in ind_to_name]
    return unify(core_var, [mint(n) for n in sorted(core_names)], trail)


def z3_is_sat(result_var: Any, trail: Trail) -> bool:
    """Check satisfiability, unifying *result_var* with the ATOM ``sat``,
    ``unsat``, or ``unknown``.

    A status is a NAME, not text (spec §6.4: names go in as atoms and come
    out as atoms), so the answer is minted.  Binding the plain ``str`` made
    the obvious source-level test — ``z3.satisfiability(R), R == sat`` —
    fail silently, because after THE FLIP a ``str`` is a STRING and a string
    never unifies with the atom of the same spelling (§6.8's distinction, at
    the term level).
    """
    state = get_z3_state(trail)
    r = state.solver.check()
    if r == _z3.sat:
        return unify(result_var, mint("sat"), trail)
    elif r == _z3.unsat:
        return unify(result_var, mint("unsat"), trail)
    return unify(result_var, mint("unknown"), trail)


def z3_disentailed(constraint_expr: Any, trail: Trail) -> bool:
    """Check if a constraint is disentailed (necessarily false).

    Returns True iff *constraint_expr* is impossible given the store
    (i.e., the constraint itself is unsatisfiable with the store).
    """
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(constraint_expr, trail, default_sort=_z3.IntSort())
    state.solver.push()
    state.solver.add(z3_expr)
    result = state.solver.check()
    state.solver.pop()
    return result == _z3.unsat


def z3_model(vars_list: Any, values_var: Any, trail: Trail) -> bool:
    """Get the current model without binding Clausal variables.

    Unifies *values_var* with a list of ``[Name, Value]`` pairs.  ``Name`` is
    the Z3 constant's NAME, so it is answered as an ATOM (§6.4) — the same
    position ``z3_named/2`` reads and ``z3_unsat_core`` answers.  ``Value`` is
    a VALUE (an int, a rational, a bool from ``z3_to_python``) and stays one.
    """
    state = get_z3_state(trail)
    vars_list = _as_list(deref(vars_list))

    if state.solver.check() != _z3.sat:
        return False

    m = state.solver.model()
    pairs: list = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            z3_v = state.var_map.get(id(v))
            if z3_v is not None:
                val = z3_to_python(m.eval(z3_v, model_completion=True))
                pairs.append([mint(str(z3_v)), val])
    return unify(values_var, pairs, trail)


def z3_simplify(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Simplify a Z3 expression and return the result."""
    z3_expr = clausal_to_z3(expr, trail, default_sort=_z3.IntSort())
    simplified = _z3.simplify(z3_expr)
    try:
        val = z3_to_python(simplified)
    except (TypeError, ValueError):
        val = str(simplified)
    return unify(result_var, val, trail)


def z3_assertions(assertions_var: Any, trail: Trail) -> bool:
    """Get all current Z3 assertions as a list of strings."""
    state = get_z3_state(trail)
    assertions = [str(a) for a in state.solver.assertions()]
    return unify(assertions_var, assertions, trail)


def z3_stats(stats_var: Any, trail: Trail) -> bool:
    """Get solver statistics as a list of ``[key, value]`` pairs.

    Runs ``check()`` first to populate stats.
    """
    state = get_z3_state(trail)
    state.solver.check()
    stats = state.solver.statistics()
    pairs: list = []
    for i in range(len(stats)):
        key = stats[i][0]
        val = stats[i][1]
        pairs.append([key, val])
    return unify(stats_var, pairs, trail)


def z3_set_option(key: Any, value: Any, trail: Trail) -> bool:
    """Set a Z3 solver option (``z3.set_option("timeout", 5000)``).

    KEY is a NAME position (§6.4) — an atom, read by spelling; a STRING is
    ``type_error(atom, …)`` and an unbound key fails.  A VALUE that is an
    atom (``memory_high_watermark``-style symbolic settings) crosses as its
    spelling; numbers and booleans cross as themselves.  Both used to go to
    ``solver.set`` raw, so the cell a source-written literal produces in the
    default ``-double_quotes(atom)`` mode raised a bare z3 ``Z3Exception``.
    """
    state = get_z3_state(trail)
    key = _constraint_name(key, "z3.set_option/2")
    if key is None:
        return False
    value = deref(value)
    if is_atom(value):
        value = spelling(value)
    state.solver.set(key, value)
    return True


def z3_set_logic(logic: Any, trail: Trail) -> bool:
    """Switch to a logic-specific solver (``z3.set_logic("QF_LIA")``).

    LOGIC is a NAME position (§6.4): an atom read by spelling, a STRING is
    ``type_error(atom, …)``, an unbound logic fails.  It used to reach
    ``_z3.SolverFor`` raw, which answered a source-written atom with a z3
    ``Z3Exception``.

    Replaces the solver, copying all existing assertions.
    """
    state = get_z3_state(trail)
    logic = _constraint_name(logic, "z3.set_logic/1")
    if logic is None:
        return False
    old_assertions = list(state.solver.assertions())
    state.solver = _z3.SolverFor(logic)
    for a in old_assertions:
        state.solver.add(a)
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Phase 7 — Soft Constraints & Optimization
# ══════════════════════════════════════════════════════════════════════════════


def z3_soft(constraint_expr: Any, weight: Any, trail: Trail,
            *, group: Any = None) -> bool:
    """Add a soft constraint with weight.

    Soft constraints are satisfied if possible.  When they conflict with
    hard constraints or each other, Z3's Optimize maximizes total satisfied
    weight.

    The constraint is retracted on trail backtrack.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(constraint_expr, trail, default_sort=_z3.IntSort())
    weight = deref(weight)
    if group is not None:
        group = deref(group)
    entry = (z3_expr, weight, group)
    state._soft_constraints.append(entry)
    idx = len(state._soft_constraints) - 1
    trail.record(lambda: _remove_soft(state, idx))
    return True


def _remove_soft(state: Z3State, idx: int) -> None:
    """Mark soft constraint at *idx* as removed (called on trail undo)."""
    if idx < len(state._soft_constraints):
        state._soft_constraints[idx] = None


def z3_max_sat(satisfied_var: Any, trail: Trail) -> bool:
    """MaxSAT: maximize total weight of satisfied soft constraints.

    Binds *satisfied_var* to the total weight of soft constraints that
    are satisfied in the optimal model.  Returns False on infeasibility.
    """
    state = get_z3_state(trail)
    opt = _build_optimize(state, trail)

    if opt.check() != _z3.sat:
        return False

    m = opt.model()
    satisfied_weight = 0
    for entry in state._soft_constraints:
        if entry is not None:
            z3_expr, weight, _ = entry
            if _z3.is_true(m.eval(z3_expr)):
                satisfied_weight += weight

    return unify(satisfied_var, satisfied_weight, trail)


def z3_optimize_label(vars_list: Any, objective_expr: Any,
                      result_var: Any, mode: Any, trail: Trail):
    """Find the optimal solution, bind variables, and yield once.

    mode: ``"maximize"`` or ``"minimize"``

    Yields exactly one solution (the optimal assignment).  Bindings are
    undone on backtrack so the generator can be re-entered.
    """
    state = get_z3_state(trail)
    vars_list = _as_list(deref(vars_list))
    mode = deref(mode)

    z3_vars: list = []
    clausal_vars: list = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            z3_v = state.var_map.get(id(v))
            if z3_v is None:
                raise ValueError(f"z3_optimize_label: variable not registered")
            z3_vars.append(z3_v)
            clausal_vars.append(v)
        # ground values are ignored during labeling

    z3_obj = clausal_to_z3(objective_expr, trail, default_sort=_z3.IntSort())

    opt = _build_optimize(state, trail)

    if mode == "maximize":
        handle = opt.maximize(z3_obj)
    elif mode == "minimize":
        handle = opt.minimize(z3_obj)
    else:
        raise ValueError(
            f"z3_optimize_label: mode must be 'maximize' or 'minimize', got {mode!r}"
        )

    if opt.check() != _z3.sat:
        return

    m = opt.model()
    # Get optimal objective value
    if mode == "maximize":
        bound = opt.upper(handle)
    else:
        bound = opt.lower(handle)
    obj_val = z3_to_python(bound)
    if isinstance(obj_val, str):
        s = obj_val.strip()
        if s in ('+oo', 'oo'):
            obj_val = float('inf')
        elif s == '-oo':
            obj_val = float('-inf')
        else:
            return  # unknown

    mark = trail.mark()
    ok = unify(result_var, obj_val, trail)
    if ok:
        for cv, z3v in zip(clausal_vars, z3_vars):
            val = z3_to_python(m.eval(z3v, model_completion=True))
            if not unify(cv, val, trail):
                ok = False
                break
    if ok:
        yield None
    trail.undo(mark)


def z3_multi_optimize(objectives: Any, results: Any, priority: Any,
                      trail: Trail):
    """Multi-objective optimization.

    objectives: list of ``(expr, mode)`` where mode is ``"maximize"``
                or ``"minimize"``
    results:    list of Vars to bind to optimal objective values
    priority:   ``"lex"``, ``"pareto"``, or ``"box"``

    For ``"pareto"`` mode, yields multiple Pareto-optimal solutions.
    For ``"lex"`` and ``"box"``, yields one solution.
    """
    state = get_z3_state(trail)
    objectives = deref(objectives)
    results = _as_list(deref(results))
    priority = deref(priority)

    opt = _build_optimize(state, trail)
    opt.set(priority=priority)

    handles = []
    z3_objs = []
    for expr, mode in objectives:
        z3_expr = clausal_to_z3(expr, trail, default_sort=_z3.RealSort())
        z3_objs.append(z3_expr)
        if mode == "maximize":
            handles.append(opt.maximize(z3_expr))
        else:
            handles.append(opt.minimize(z3_expr))

    if priority == "pareto":
        while opt.check() == _z3.sat:
            m = opt.model()
            mark = trail.mark()
            ok = True
            for rv, z3_e in zip(results, z3_objs):
                val = z3_to_python(m.eval(z3_e))
                if not unify(rv, val, trail):
                    ok = False
                    break
            if ok:
                yield None
            trail.undo(mark)
    else:
        if opt.check() == _z3.sat:
            m = opt.model()
            mark = trail.mark()
            ok = True
            for rv, z3_e in zip(results, z3_objs):
                val = z3_to_python(m.eval(z3_e))
                if not unify(rv, val, trail):
                    ok = False
                    break
            if ok:
                yield None
            trail.undo(mark)


# ══════════════════════════════════════════════════════════════════════════════
# Module API — constraint block evaluator
# ══════════════════════════════════════════════════════════════════════════════

def z3_constraint_block(constraint_set: Any, sort: Any, trail: Trail) -> bool:
    """Walk constraint elements and post each under *sort*.

    *constraint_set* is typically a tuple (from ``(C1, C2, ...)``) or list.
    Each element is a Clausal AST node (e.g. ``LtE(X, 10)``,
    ``CompareChain([LtE(1, X), LtE(X, 10)])``).  Unbound Vars encountered
    during translation are auto-registered with the given Z3 sort.
    """
    constraint_set = deref(constraint_set)
    if isinstance(constraint_set, (list, tuple)):
        elements = constraint_set
    else:
        elements = [constraint_set]

    if not elements:
        return True

    state = get_z3_state(trail)
    z3_exprs = [clausal_to_z3(deref(elem), trail, default_sort=sort)
                for elem in elements]
    z3_push(trail)
    for expr in z3_exprs:
        state.solver.add(expr)
    return True


def label_z3_polymorphic(vars_list: Any, trail: Trail):
    """Sort-polymorphic labeling: dispatches based on each variable's Z3 sort.

    Handles IntSort, BoolSort, BitVecSort, RealSort, and StringSort
    in a single call.  All variables must be registered with Z3.
    """
    state = get_z3_state(trail)
    items = _as_list(deref(vars_list))

    # Collect Z3 vars and their sorts
    z3_vars: list = []
    clausal_vars: list = []
    for v in items:
        v = deref(v)
        if not is_var(v):
            continue
        z3_v = state.var_map.get(id(v))
        if z3_v is None:
            raise ValueError(
                f"label: variable not registered with Z3. "
                f"Declare it first with z3.integer, z3.real, etc."
            )
        z3_vars.append(z3_v)
        clausal_vars.append(v)

    if not z3_vars:
        # All ground — yield one solution iff store is satisfiable.
        if z3_check(trail):
            yield None
        return

    # For continuous sorts (real, string): yield at most one model.
    continuous = any(_is_continuous_sort(z3v.sort()) for z3v in z3_vars)

    # Push a scope for blocking clauses — popped on backtrack.
    z3_push(trail)

    while state.solver.check() == _z3.sat:
        m = state.solver.model()
        values = [z3_to_python(m.eval(z3v, model_completion=True))
                  for z3v in z3_vars]

        mark = trail.mark()
        ok = all(unify(cv, val, trail)
                 for cv, val in zip(clausal_vars, values))
        if ok:
            yield None
        trail.undo(mark)

        if continuous:
            break

        # Block this assignment so next check() finds a new one.
        block = _z3.Or([z3v != m.eval(z3v, model_completion=True)
                        for z3v in z3_vars])
        state.solver.add(block)


def _is_continuous_sort(sort: Any) -> bool:
    """Return True for sorts that have continuous/infinite domains."""
    return (sort == _z3.RealSort() or
            (hasattr(_z3, 'StringSort') and sort == _z3.StringSort()))
