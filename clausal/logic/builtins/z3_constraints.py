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


# ── Phase 4: real/rational constraints ────────────────────────────────────────

@_builtin("in_z3_real", 3)
def _in_z3_real__3(var_or_list, lo, hi, trail, k):
    """in_z3_real(Var, Lo, Hi) — declare real variable with bounds via Z3."""
    from clausal.logic.clpz3 import in_z3_real as _fn
    if _fn(var_or_list, lo, hi, trail):
        yield None


@_builtin("in_z3_real", 1)
def _in_z3_real__1(var_or_list, trail, k):
    """in_z3_real(Var) — declare unbounded real variable via Z3."""
    from clausal.logic.clpz3 import in_z3_real as _fn
    if _fn(var_or_list, None, None, trail):
        yield None


@_builtin("z3_real_eq", 2)
def _z3_real_eq__2(l, r, trail, k):
    """z3_real_eq(L, R) — post L == R as a Z3 real constraint."""
    from clausal.logic.clpz3 import z3_real_eq as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("z3_real_ne", 2)
def _z3_real_ne__2(l, r, trail, k):
    """z3_real_ne(L, R) — post L != R as a Z3 real constraint."""
    from clausal.logic.clpz3 import z3_real_ne as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("z3_real_lt", 2)
def _z3_real_lt__2(l, r, trail, k):
    """z3_real_lt(L, R) — post L < R as a Z3 real constraint."""
    from clausal.logic.clpz3 import z3_real_lt as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("z3_real_le", 2)
def _z3_real_le__2(l, r, trail, k):
    """z3_real_le(L, R) — post L <= R as a Z3 real constraint."""
    from clausal.logic.clpz3 import z3_real_le as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("z3_real_gt", 2)
def _z3_real_gt__2(l, r, trail, k):
    """z3_real_gt(L, R) — post L > R as a Z3 real constraint."""
    from clausal.logic.clpz3 import z3_real_gt as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("z3_real_ge", 2)
def _z3_real_ge__2(l, r, trail, k):
    """z3_real_ge(L, R) — post L >= R as a Z3 real constraint."""
    from clausal.logic.clpz3 import z3_real_ge as _fn
    if _fn(l, r, trail):
        yield None


@_builtin("label_z3_real", 1)
def _label_z3_real__1(vars_list, trail, k):
    """label_z3_real(Vars) — find one real-valued assignment via Z3."""
    from clausal.logic.clpz3 import label_z3_real as _fn
    yield from _fn(vars_list, trail)


@_builtin("maximize_z3", 2)
def _maximize_z3__2(expr, result, trail, k):
    """maximize_z3(Expr, Result) — maximize expression via Z3 Optimize."""
    from clausal.logic.clpz3 import maximize_z3 as _fn
    if _fn(expr, result, trail):
        yield None


@_builtin("minimize_z3", 2)
def _minimize_z3__2(expr, result, trail, k):
    """minimize_z3(Expr, Result) — minimize expression via Z3 Optimize."""
    from clausal.logic.clpz3 import minimize_z3 as _fn
    if _fn(expr, result, trail):
        yield None


@_builtin("entailed_z3", 1)
def _entailed_z3__1(constraint_expr, trail, k):
    """entailed_z3(Expr) — succeed if Expr is implied by current Z3 constraints."""
    from clausal.logic.clpz3 import entailed_z3 as _fn
    if _fn(constraint_expr, trail):
        yield None


@_builtin("sup_z3", 2)
def _sup_z3__2(expr, result, trail, k):
    """sup_z3(Expr, Result) — supremum of Expr via Z3 Optimize."""
    from clausal.logic.clpz3 import sup_z3 as _fn
    if _fn(expr, result, trail):
        yield None


@_builtin("inf_z3", 2)
def _inf_z3__2(expr, result, trail, k):
    """inf_z3(Expr, Result) — infimum of Expr via Z3 Optimize."""
    from clausal.logic.clpz3 import inf_z3 as _fn
    if _fn(expr, result, trail):
        yield None


# ── Phase 5: UserPropagateBase / table constraint ─────────────────────────────

@_builtin("z3_table", 2)
def _z3_table__2(vars_list, tuples_list, trail, k):
    """z3_table(Vars, Tuples) — table/extensional constraint via Z3."""
    from clausal.logic.clpz3 import z3_table as _fn
    if _fn(vars_list, tuples_list, trail):
        yield None


# ── Phase 6: advanced theories ────────────────────────────────────────────────

# ─ Bitvectors ─

@_builtin("in_z3_bv", 2)
def _in_z3_bv__2(var_or_list, width, trail, k):
    """in_z3_bv(Var, Width) — declare bitvector variable(s)."""
    from clausal.logic.clpz3 import in_z3_bv as _fn
    if _fn(var_or_list, width, trail): yield None

@_builtin("label_z3_bv", 1)
def _label_z3_bv__1(vars_list, trail, k):
    """label_z3_bv(Vars) — enumerate bitvector solutions."""
    from clausal.logic.clpz3 import label_z3_bv as _fn
    yield from _fn(vars_list, trail)

@_builtin("bv_add", 3)
def _bv_add__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_add as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_sub", 3)
def _bv_sub__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_sub as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_mul", 3)
def _bv_mul__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_mul as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_udiv", 3)
def _bv_udiv__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_udiv as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_sdiv", 3)
def _bv_sdiv__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_sdiv as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_urem", 3)
def _bv_urem__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_urem as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_srem", 3)
def _bv_srem__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_srem as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_and", 3)
def _bv_and__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_and as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_or", 3)
def _bv_or__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_or as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_xor", 3)
def _bv_xor__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_xor as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_not", 2)
def _bv_not__2(x, r, trail, k):
    from clausal.logic.clpz3 import bv_not as _fn
    if _fn(x, r, trail): yield None

@_builtin("bv_shl", 3)
def _bv_shl__3(x, n, r, trail, k):
    from clausal.logic.clpz3 import bv_shl as _fn
    if _fn(x, n, r, trail): yield None

@_builtin("bv_lshr", 3)
def _bv_lshr__3(x, n, r, trail, k):
    from clausal.logic.clpz3 import bv_lshr as _fn
    if _fn(x, n, r, trail): yield None

@_builtin("bv_ashr", 3)
def _bv_ashr__3(x, n, r, trail, k):
    from clausal.logic.clpz3 import bv_ashr as _fn
    if _fn(x, n, r, trail): yield None

@_builtin("bv_eq", 2)
def _bv_eq__2(x, y, trail, k):
    from clausal.logic.clpz3 import bv_eq as _fn
    if _fn(x, y, trail): yield None

@_builtin("bv_ne", 2)
def _bv_ne__2(x, y, trail, k):
    from clausal.logic.clpz3 import bv_ne as _fn
    if _fn(x, y, trail): yield None

@_builtin("bv_slt", 2)
def _bv_slt__2(x, y, trail, k):
    from clausal.logic.clpz3 import bv_slt as _fn
    if _fn(x, y, trail): yield None

@_builtin("bv_sle", 2)
def _bv_sle__2(x, y, trail, k):
    from clausal.logic.clpz3 import bv_sle as _fn
    if _fn(x, y, trail): yield None

@_builtin("bv_sgt", 2)
def _bv_sgt__2(x, y, trail, k):
    from clausal.logic.clpz3 import bv_sgt as _fn
    if _fn(x, y, trail): yield None

@_builtin("bv_sge", 2)
def _bv_sge__2(x, y, trail, k):
    from clausal.logic.clpz3 import bv_sge as _fn
    if _fn(x, y, trail): yield None

@_builtin("bv_ult", 2)
def _bv_ult__2(x, y, trail, k):
    from clausal.logic.clpz3 import bv_ult as _fn
    if _fn(x, y, trail): yield None

@_builtin("bv_ule", 2)
def _bv_ule__2(x, y, trail, k):
    from clausal.logic.clpz3 import bv_ule as _fn
    if _fn(x, y, trail): yield None

@_builtin("bv_ugt", 2)
def _bv_ugt__2(x, y, trail, k):
    from clausal.logic.clpz3 import bv_ugt as _fn
    if _fn(x, y, trail): yield None

@_builtin("bv_uge", 2)
def _bv_uge__2(x, y, trail, k):
    from clausal.logic.clpz3 import bv_uge as _fn
    if _fn(x, y, trail): yield None

@_builtin("bv_concat", 3)
def _bv_concat__3(x, y, r, trail, k):
    from clausal.logic.clpz3 import bv_concat as _fn
    if _fn(x, y, r, trail): yield None

@_builtin("bv_extract", 4)
def _bv_extract__4(hi, lo, x, r, trail, k):
    from clausal.logic.clpz3 import bv_extract as _fn
    if _fn(hi, lo, x, r, trail): yield None

@_builtin("bv_zext", 3)
def _bv_zext__3(x, n, r, trail, k):
    from clausal.logic.clpz3 import bv_zext as _fn
    if _fn(x, n, r, trail): yield None

@_builtin("bv_sext", 3)
def _bv_sext__3(x, n, r, trail, k):
    from clausal.logic.clpz3 import bv_sext as _fn
    if _fn(x, n, r, trail): yield None


# ─ Arrays ─

@_builtin("z3_array", 3)
def _z3_array__3(var, domain_sort, range_sort, trail, k):
    """z3_array(Var, DomainSort, RangeSort) — declare array variable."""
    from clausal.logic.clpz3 import z3_array as _fn
    if _fn(var, domain_sort, range_sort, trail): yield None

@_builtin("z3_select", 3)
def _z3_select__3(array, index, value, trail, k):
    """z3_select(Array, Index, Value) — Select(array, index) == value."""
    from clausal.logic.clpz3 import z3_select as _fn
    if _fn(array, index, value, trail): yield None

@_builtin("z3_store", 4)
def _z3_store__4(array, index, value, result, trail, k):
    """z3_store(Array, Index, Value, Result) — result == Store(array, index, value)."""
    from clausal.logic.clpz3 import z3_store as _fn
    if _fn(array, index, value, result, trail): yield None

@_builtin("z3_const_array", 3)
def _z3_const_array__3(value, domain_sort, result, trail, k):
    """z3_const_array(Value, DomainSort, Result) — constant array."""
    from clausal.logic.clpz3 import z3_const_array as _fn
    if _fn(value, domain_sort, result, trail): yield None


# ─ Sets ─

@_builtin("z3_set", 2)
def _z3_set__2(var, elem_sort, trail, k):
    from clausal.logic.clpz3 import z3_set as _fn
    if _fn(var, elem_sort, trail): yield None

@_builtin("z3_set_member", 2)
def _z3_set_member__2(elem, s, trail, k):
    from clausal.logic.clpz3 import z3_set_member as _fn
    if _fn(elem, s, trail): yield None

@_builtin("z3_set_not_member", 2)
def _z3_set_not_member__2(elem, s, trail, k):
    from clausal.logic.clpz3 import z3_set_not_member as _fn
    if _fn(elem, s, trail): yield None

@_builtin("z3_set_subset", 2)
def _z3_set_subset__2(s1, s2, trail, k):
    from clausal.logic.clpz3 import z3_set_subset as _fn
    if _fn(s1, s2, trail): yield None

@_builtin("z3_set_union", 3)
def _z3_set_union__3(s1, s2, r, trail, k):
    from clausal.logic.clpz3 import z3_set_union as _fn
    if _fn(s1, s2, r, trail): yield None

@_builtin("z3_set_intersect", 3)
def _z3_set_intersect__3(s1, s2, r, trail, k):
    from clausal.logic.clpz3 import z3_set_intersect as _fn
    if _fn(s1, s2, r, trail): yield None

@_builtin("z3_set_add", 3)
def _z3_set_add__3(s, elem, r, trail, k):
    from clausal.logic.clpz3 import z3_set_add as _fn
    if _fn(s, elem, r, trail): yield None


# ─ Strings ─

@_builtin("z3_string", 1)
def _z3_string__1(var, trail, k):
    from clausal.logic.clpz3 import z3_string as _fn
    if _fn(var, trail): yield None

@_builtin("z3_str_length", 2)
def _z3_str_length__2(s, n, trail, k):
    from clausal.logic.clpz3 import z3_str_length as _fn
    if _fn(s, n, trail): yield None

@_builtin("z3_str_contains", 2)
def _z3_str_contains__2(s, sub, trail, k):
    from clausal.logic.clpz3 import z3_str_contains as _fn
    if _fn(s, sub, trail): yield None

@_builtin("z3_str_concat", 3)
def _z3_str_concat__3(s1, s2, r, trail, k):
    from clausal.logic.clpz3 import z3_str_concat as _fn
    if _fn(s1, s2, r, trail): yield None

@_builtin("z3_str_regex", 2)
def _z3_str_regex__2(s, pattern, trail, k):
    from clausal.logic.clpz3 import z3_str_regex as _fn
    if _fn(s, pattern, trail): yield None

@_builtin("label_z3_str", 1)
def _label_z3_str__1(var, trail, k):
    from clausal.logic.clpz3 import label_z3_str as _fn
    yield from _fn(var, trail)


# ─ Uninterpreted functions ─

@_builtin("z3_function", 3)
def _z3_function__3(var, domain_sorts, range_sort, trail, k):
    from clausal.logic.clpz3 import z3_function as _fn
    if _fn(var, domain_sorts, range_sort, trail): yield None

@_builtin("z3_app", 3)
def _z3_app__3(func_var, args, result, trail, k):
    from clausal.logic.clpz3 import z3_app as _fn
    if _fn(func_var, args, result, trail): yield None


# ─ Quantifiers ─

@_builtin("z3_forall", 2)
def _z3_forall__2(var_sorts, body_fn, trail, k):
    from clausal.logic.clpz3 import z3_forall as _fn
    if _fn(var_sorts, body_fn, trail): yield None

@_builtin("z3_exists", 2)
def _z3_exists__2(var_sorts, body_fn, trail, k):
    from clausal.logic.clpz3 import z3_exists as _fn
    if _fn(var_sorts, body_fn, trail): yield None


# ══════════════════════════════════════════════════════════════════════════════
# Phase 7 — Soft Constraints & Optimization
# ══════════════════════════════════════════════════════════════════════════════

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
    """z3_max_sat(Satisfied) — maximize total satisfied soft weight."""
    from clausal.logic.clpz3 import z3_max_sat
    if z3_max_sat(satisfied, trail):
        yield None

@_builtin("z3_optimize_label", 4)
def _z3_optimize_label__4(vars_list, obj_expr, result, mode, trail, k):
    """z3_optimize_label(Vars, ObjExpr, Result, Mode) — optimize and label."""
    from clausal.logic.clpz3 import z3_optimize_label
    yield from z3_optimize_label(vars_list, obj_expr, result, mode, trail)

@_builtin("z3_multi_optimize", 3)
def _z3_multi_optimize__3(objectives, results, priority, trail, k):
    """z3_multi_optimize(Objectives, Results, Priority) — multi-objective."""
    from clausal.logic.clpz3 import z3_multi_optimize
    yield from z3_multi_optimize(objectives, results, priority, trail)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 8 — Diagnostics
# ══════════════════════════════════════════════════════════════════════════════

@_builtin("z3_named", 2)
def _z3_named__2(constraint_expr, name, trail, k):
    """z3_named(Constraint, Name) — add named constraint for unsat core."""
    from clausal.logic.clpz3 import z3_named
    if z3_named(constraint_expr, name, trail): yield None

@_builtin("z3_unsat_core", 1)
def _z3_unsat_core__1(core, trail, k):
    """z3_unsat_core(Core) — get unsat core as list of names."""
    from clausal.logic.clpz3 import z3_unsat_core
    if z3_unsat_core(core, trail): yield None

@_builtin("z3_minimal_unsat_core", 1)
def _z3_minimal_unsat_core__1(core, trail, k):
    """z3_minimal_unsat_core(Core) — get minimal unsat core."""
    from clausal.logic.clpz3 import z3_minimal_unsat_core
    if z3_minimal_unsat_core(core, trail): yield None

@_builtin("z3_is_sat", 1)
def _z3_is_sat__1(result, trail, k):
    """z3_is_sat(Result) — Result is 'sat', 'unsat', or 'unknown'."""
    from clausal.logic.clpz3 import z3_is_sat
    if z3_is_sat(result, trail): yield None

@_builtin("z3_model", 2)
def _z3_model__2(vars_list, values, trail, k):
    """z3_model(Vars, Values) — get model without binding variables."""
    from clausal.logic.clpz3 import z3_model
    if z3_model(vars_list, values, trail): yield None

@_builtin("z3_disentailed", 1)
def _z3_disentailed__1(constraint_expr, trail, k):
    """z3_disentailed(Constraint) — succeed if constraint is impossible."""
    from clausal.logic.clpz3 import z3_disentailed
    if z3_disentailed(constraint_expr, trail): yield None

@_builtin("z3_simplify", 2)
def _z3_simplify__2(expr, result, trail, k):
    """z3_simplify(Expr, Result) — simplify expression via Z3."""
    from clausal.logic.clpz3 import z3_simplify
    if z3_simplify(expr, result, trail): yield None

@_builtin("z3_assertions", 1)
def _z3_assertions__1(assertions, trail, k):
    """z3_assertions(List) — get all Z3 assertions as strings."""
    from clausal.logic.clpz3 import z3_assertions
    if z3_assertions(assertions, trail): yield None

@_builtin("z3_stats", 1)
def _z3_stats__1(stats, trail, k):
    """z3_stats(Stats) — get solver statistics."""
    from clausal.logic.clpz3 import z3_stats
    if z3_stats(stats, trail): yield None

@_builtin("z3_set_option", 2)
def _z3_set_option__2(key, value, trail, k):
    """z3_set_option(Key, Value) — set Z3 solver option."""
    from clausal.logic.clpz3 import z3_set_option
    if z3_set_option(key, value, trail): yield None

@_builtin("z3_set_logic", 1)
def _z3_set_logic__1(logic, trail, k):
    """z3_set_logic(Logic) — switch to logic-specific solver."""
    from clausal.logic.clpz3 import z3_set_logic
    if z3_set_logic(logic, trail): yield None
