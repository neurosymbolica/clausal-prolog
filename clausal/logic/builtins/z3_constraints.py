"""Z3-backed constraint builtins.

These predicates use Z3 as the constraint solver backend.  They follow the
same Clausal syntax and semantics as the native CLP predicates, with a _z3
suffix to make the backend explicit.

Phases:
  Phase 1 — nothing to register (infrastructure only)
  Phase 2 — integer constraints: in_z3/3, label_z3/1, all_different_z3/1, ...
  Phase 3 — boolean constraints: sat_z3/1, taut_z3/2, label_z3_bool/1, ...
  Phase 4 — real/rational:       in_z3_real/1,3, maximize_z3/2, minimize_z3/2
  Phase 5 — propagator:          z3_table/2
  Phase 6 — advanced theories:   in_z3_bv/2, z3_array/3, ...
  Phase 7 — optimization:        z3_soft/2,3, z3_max_sat/1, ...
  Phase 8 — diagnostics:         z3_named/2, z3_unsat_core/1, ...
"""

from __future__ import annotations

from clausal.logic.builtins._registry import _builtin

# ── Phase 1: no predicates — infrastructure lives in clpz3.py ────────────────


# ── Phase 2: integer constraints ──────────────────────────────────────────────

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
    """z3_check — succeed if current Z3 constraints are satisfiable."""
    from clausal.logic.clpz3 import z3_check as _fn
    if _fn(trail):
        yield None


@_builtin("z3_eq", 2)
def _z3_eq__2(l, r, trail, k):
    """z3_eq(L, R) — post L == R as a Z3 integer constraint."""
    from clausal.logic.clpz3 import z3_eq as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("z3_ne", 2)
def _z3_ne__2(l, r, trail, k):
    """z3_ne(L, R) — post L != R as a Z3 integer constraint."""
    from clausal.logic.clpz3 import z3_ne as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("z3_lt", 2)
def _z3_lt__2(l, r, trail, k):
    """z3_lt(L, R) — post L < R as a Z3 integer constraint."""
    from clausal.logic.clpz3 import z3_lt as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("z3_le", 2)
def _z3_le__2(l, r, trail, k):
    """z3_le(L, R) — post L <= R as a Z3 integer constraint."""
    from clausal.logic.clpz3 import z3_le as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("z3_gt", 2)
def _z3_gt__2(l, r, trail, k):
    """z3_gt(L, R) — post L > R as a Z3 integer constraint."""
    from clausal.logic.clpz3 import z3_gt as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("z3_ge", 2)
def _z3_ge__2(l, r, trail, k):
    """z3_ge(L, R) — post L >= R as a Z3 integer constraint."""
    from clausal.logic.clpz3 import z3_ge as _fn
    if _fn(l, r, trail):
        yield None


# ── Phase 3: boolean constraints ──────────────────────────────────────────────

@_builtin("sat_z3", 1)
def _sat_z3__1(expr, trail, k):
    """sat_z3(Expr) — post Boolean constraint via Z3 (lazy, trail-scoped)."""
    from clausal.logic.clpz3 import sat_z3 as _fn
    if _fn(expr, trail):
        yield None


@_builtin("z3_try", 1)
def _z3_try__1(expr, trail, k):
    """z3_try(Expr) — probe satisfiability of Expr without committing it."""
    from clausal.logic.clpz3 import z3_try as _fn
    if _fn(expr, trail):
        yield None


@_builtin("taut_z3", 2)
def _taut_z3__2(expr, t, trail, k):
    """taut_z3(Expr, T) — T=1 if tautology, T=0 if contradiction, else fail."""
    from clausal.logic.clpz3 import taut_z3 as _fn
    if _fn(expr, t, trail):
        yield None


@_builtin("sat_count_z3", 2)
def _sat_count_z3__2(expr, count, trail, k):
    """sat_count_z3(Expr, N) — count satisfying Boolean assignments."""
    from clausal.logic.clpz3 import sat_count_z3 as _fn
    if _fn(expr, count, trail):
        yield None


@_builtin("label_z3_bool", 1)
def _label_z3_bool__1(vars_list, trail, k):
    """label_z3_bool(Vars) — enumerate 0/1 assignments via Z3."""
    from clausal.logic.clpz3 import label_z3_bool as _fn
    yield from _fn(vars_list, trail)


@_builtin("at_most_z3", 2)
def _at_most_z3__2(vars_list, bound, trail, k):
    """at_most_z3(Vars, K) — at most K of Vars are true."""
    from clausal.logic.clpz3 import at_most_z3 as _fn
    if _fn(vars_list, bound, trail):
        yield None


@_builtin("at_least_z3", 2)
def _at_least_z3__2(vars_list, bound, trail, k):
    """at_least_z3(Vars, K) — at least K of Vars are true."""
    from clausal.logic.clpz3 import at_least_z3 as _fn
    if _fn(vars_list, bound, trail):
        yield None


@_builtin("exactly_z3", 2)
def _exactly_z3__2(vars_list, bound, trail, k):
    """exactly_z3(Vars, K) — exactly K of Vars are true."""
    from clausal.logic.clpz3 import exactly_z3 as _fn
    if _fn(vars_list, bound, trail):
        yield None
