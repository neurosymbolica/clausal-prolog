"""Constraint builtins: dif/2, eq/3, dif_t/3, in_domain/3, label/1,
all_different/1, structural_eq/2, sum_/3, scalar_product/4, element/3, circuit/1,
sat/1, taut/2, sat_count/2, bool_labeling/1,
in_real/1, in_real/3, label_real/1, label_real/2,
in_q/1, in_q/3, maximize/2, minimize/2."""

from __future__ import annotations

from clausal.logic.builtins._registry import _builtin


@_builtin("dif", 2)
def _dif__2(x, y, trail, k):
    """dif(X, Y) — disequality constraint: succeed if X and Y can remain different."""
    from clausal.logic.constraints import dif as _dif_fn  # noqa: PLC0415
    if _dif_fn(x, y, trail):
        yield None


# ── Reified builtins (V2-8 Phase B) ──────────────────────────────────────────


@_builtin("eq", 3)
def _eq__3(x, y, t, trail, k):
    """eq(X, Y, T) — reified equality: T is True if X=Y, False if dif(X,Y)."""
    from clausal.logic.reif import eq__3  # noqa: PLC0415
    yield from eq__3(x, y, t, trail, k)


@_builtin("dif_t", 3)
def _dif_t__3(x, y, t, trail, k):
    """dif_t(X, Y, T) — reified disequality: T is True if dif(X,Y), False if X=Y."""
    from clausal.logic.reif import dif_t__3  # noqa: PLC0415
    yield from dif_t__3(x, y, t, trail, k)


# ── CLP(FD) builtins ─────────────────────────────────────────────────────────


@_builtin("in_domain", 3)
def _in_domain__3(var_or_list, lo, hi, trail, k):
    """in_domain(Var, Lo, Hi) — post domain [Lo, Hi] on Var or list of Vars."""
    from clausal.logic.clpfd import in_domain as _in_domain_fn  # noqa: PLC0415
    if _in_domain_fn(var_or_list, lo, hi, trail):
        yield None


@_builtin("label", 1)
def _label__1(vars_list, trail, k):
    """label(Vars) — enumerate values for FD-constrained variables."""
    from clausal.logic.clpfd import label as _label_fn  # noqa: PLC0415
    yield from _label_fn(vars_list, trail)


@_builtin("all_different", 1)
def _all_different__1(vars_list, trail, k):
    """all_different(Vars) — post all-different constraint on list of Vars."""
    from clausal.logic.clpfd import all_different as _all_diff_fn  # noqa: PLC0415
    if _all_diff_fn(vars_list, trail):
        yield None


@_builtin("structural_eq", 2)
def _structural_eq__2(t1, t2, trail, k):
    """structural_eq(T1, T2) — true structural equality (Prolog ==/2).

    Succeeds iff T1 and T2 are identical after dereferencing, without
    binding variables or evaluating arithmetic.
    """
    from clausal.logic.constraints import structural_eq as _seq_fn  # noqa: PLC0415
    if _seq_fn(t1, t2):
        yield None


@_builtin("sum_", 3)
def _sum__3(vars_list, op, value, trail, k):
    """sum_(Vars, Op, Value) — constrain sum of Vars under Op to Value."""
    from clausal.logic.clpfd import fd_sum as _sum_fn  # noqa: PLC0415
    yield from _sum_fn(vars_list, op, value, trail)


@_builtin("scalar_product", 4)
def _scalar_product__4(coeffs, vars_list, op, value, trail, k):
    """scalar_product(Coeffs, Vars, Op, Value) — weighted sum constraint."""
    from clausal.logic.clpfd import fd_scalar_product as _sp_fn  # noqa: PLC0415
    yield from _sp_fn(coeffs, vars_list, op, value, trail)


@_builtin("element", 3)
def _element__3(index, lst, value, trail, k):
    """element(Index, List, Value) — Value is the Index-th element (1-based)."""
    from clausal.logic.clpfd import fd_element as _elem_fn  # noqa: PLC0415
    yield from _elem_fn(index, lst, value, trail)


@_builtin("circuit", 1)
def _circuit__1(vars_list, trail, k):
    """circuit(Vars) — Vars form a single Hamiltonian circuit."""
    from clausal.logic.clpfd import fd_circuit as _circuit_fn  # noqa: PLC0415
    yield from _circuit_fn(vars_list, trail)


# ── CLP(B) builtins ─────────────────────────────────────────────────────────


@_builtin("sat", 1)
def _sat__1(expr, trail, k):
    """sat(Expr) — post Boolean constraint, fail if unsatisfiable."""
    from clausal.logic.clpb import sat as _sat_fn  # noqa: PLC0415
    if _sat_fn(expr, trail):
        yield None


@_builtin("taut", 2)
def _taut__2(expr, t, trail, k):
    """taut(Expr, T) — T=1 if tautology, T=0 if contradiction, else fail."""
    from clausal.logic.clpb import taut as _taut_fn  # noqa: PLC0415
    if _taut_fn(expr, t, trail):
        yield None


@_builtin("sat_count", 2)
def _sat_count__2(expr, count, trail, k):
    """sat_count(Expr, N) — N is the number of satisfying assignments."""
    from clausal.logic.clpb import sat_count as _sat_count_fn  # noqa: PLC0415
    if _sat_count_fn(expr, count, trail):
        yield None


@_builtin("bool_labeling", 1)
def _bool_labeling__1(vars_list, trail, k):
    """bool_labeling(Vars) — enumerate 0/1 assignments for Boolean variables."""
    from clausal.logic.clpb import bool_labeling as _bool_labeling_fn  # noqa: PLC0415
    yield from _bool_labeling_fn(vars_list, trail)


# ── CLP(R) builtins ──────────────────────────────────────────────────────────

import math as _math  # noqa: E402


@_builtin("in_real", 1)
def _in_real__1(var_or_list, trail, k):
    """in_real(Var) — declare real variable with unbounded domain [-inf, +inf]."""
    from clausal.logic.clpr import in_real as _in_real_fn  # noqa: PLC0415
    if _in_real_fn(var_or_list, -_math.inf, _math.inf, trail):
        yield None


@_builtin("in_real", 3)
def _in_real__3(var_or_list, lo, hi, trail, k):
    """in_real(Var, Lo, Hi) — declare real variable with domain [Lo, Hi]."""
    from clausal.logic.clpr import in_real as _in_real_fn  # noqa: PLC0415
    if _in_real_fn(var_or_list, float(lo), float(hi), trail):
        yield None


@_builtin("label_real", 1)
def _label_real__1(vars_list, trail, k):
    """label_real(Vars) — bisect real intervals to IEEE float precision."""
    from clausal.logic.clpr import label_real as _label_real_fn  # noqa: PLC0415
    yield from _label_real_fn(vars_list, trail)


@_builtin("label_real", 2)
def _label_real__2(vars_list, eps, trail, k):
    """label_real(Vars, Eps) — bisect real intervals until width <= Eps."""
    from clausal.logic.clpr import label_real as _label_real_fn  # noqa: PLC0415
    yield from _label_real_fn(vars_list, trail, eps=float(eps))


# ── CLP(Q) builtins ─────────────────────────────────────────────────────────


@_builtin("in_q", 1)
def _in_q__1(var_or_list, trail, k):
    """in_q(Var) — declare rational variable with unbounded domain."""
    from clausal.logic.clpq import in_q as _in_q_fn  # noqa: PLC0415
    if _in_q_fn(var_or_list, None, None, trail):
        yield None


@_builtin("in_q", 3)
def _in_q__3(var_or_list, lo, hi, trail, k):
    """in_q(Var, Lo, Hi) — declare rational variable with domain [Lo, Hi]."""
    from clausal.logic.clpq import in_q as _in_q_fn  # noqa: PLC0415
    if _in_q_fn(var_or_list, lo, hi, trail):
        yield None


# Pythonic alias: rational/1 declares a variable as rational-domain
@_builtin("rational", 1)
def _rational__1(var_or_list, trail, k):
    """rational(X) — declare X as a rational variable (alias for in_q/1).

    For bounded declaration, use ``rational(X), 0 <= X <= 10`` instead
    of ``in_q(X, 0, 10)``.
    """
    from clausal.logic.clpq import in_q as _in_q_fn  # noqa: PLC0415
    if _in_q_fn(var_or_list, None, None, trail):
        yield None


@_builtin("maximize", 2)
def _maximize__2(expr, result, trail, k):
    """maximize(Expr, Result) — find maximum of linear expression."""
    from clausal.logic.clpq import maximize as _maximize_fn  # noqa: PLC0415
    if _maximize_fn(expr, result, trail):
        yield None


@_builtin("minimize", 2)
def _minimize__2(expr, result, trail, k):
    """minimize(Expr, Result) — find minimum of linear expression."""
    from clausal.logic.clpq import minimize as _minimize_fn  # noqa: PLC0415
    if _minimize_fn(expr, result, trail):
        yield None


@_builtin("int_minimize", 3)
def _int_minimize__3(int_vars, expr, result, trail, k):
    """int_minimize(IntVars, Expr, Min) — minimize with integrality constraints."""
    from clausal.logic.clpq import bb_inf as _bb_inf_fn  # noqa: PLC0415
    from clausal.logic.variables import deref as _deref  # noqa: PLC0415
    if _bb_inf_fn(_deref(int_vars), expr, result, trail):
        yield None


# SICStus compatibility alias
@_builtin("bb_inf", 3)
def _bb_inf__3(int_vars, expr, result, trail, k):
    """bb_inf(IntVars, Expr, Inf) — alias for int_minimize/3."""
    from clausal.logic.clpq import bb_inf as _bb_inf_fn  # noqa: PLC0415
    from clausal.logic.variables import deref as _deref  # noqa: PLC0415
    if _bb_inf_fn(_deref(int_vars), expr, result, trail):
        yield None


@_builtin("dump_q", 2)
def _dump_q__2(vars_list, result, trail, k):
    """dump_q(Vars, Constraints) — project constraint store onto Vars."""
    from clausal.logic.clpq import dump_q as _dump_q_fn  # noqa: PLC0415
    from clausal.logic.variables import deref as _deref, unify as _unify  # noqa: PLC0415
    constraints = _dump_q_fn(_deref(vars_list), trail)
    if _unify(result, constraints, trail):
        yield None




@_builtin("entailed", 1)
def _entailed__1(constraint_expr, trail, k):
    """entailed(X <= 5) — test if constraint is implied (Pythonic form).

    The comparison expression is in argument position, so it arrives as
    an AST node (e.g., LtE), not as an evaluated goal.
    """
    from clausal.logic.clpq import entailed as _entailed_fn  # noqa: PLC0415
    from clausal.logic.variables import deref as _deref  # noqa: PLC0415
    from clausal.pythonic_ast.nodes import LtE, Lt, GtE, Gt, ArithEq, ArithNeq  # noqa: PLC0415
    expr = _deref(constraint_expr)
    op_map = {LtE: '=<', Lt: '<', GtE: '>=', Gt: '>', ArithEq: '=', ArithNeq: '\\='}
    for cls, op_str in op_map.items():
        if isinstance(expr, cls):
            if _entailed_fn(op_str, expr.left, expr.right, trail):
                yield None
            return


@_builtin("sup", 2)
def _sup__2(expr, result, trail, k):
    """sup(Expr, Sup) — compute supremum without committing.

    CLP(R) when *Expr* mentions a real-domain variable (ruling R17: the
    upper bound propagation has established, a float; fails when unbounded),
    CLP(Q) otherwise."""
    from clausal.logic.clpr import is_real_expression, real_bound  # noqa: PLC0415
    if is_real_expression(expr, "sup/2"):
        if real_bound(expr, result, trail, "sup"):
            yield None
        return
    from clausal.logic.clpq import sup as _sup_fn  # noqa: PLC0415
    if _sup_fn(expr, result, trail):
        yield None


@_builtin("inf", 2)
def _inf__2(expr, result, trail, k):
    """inf(Expr, Inf) — compute infimum without committing.

    CLP(R) when *Expr* mentions a real-domain variable (ruling R17), CLP(Q)
    otherwise; see ``sup/2``."""
    from clausal.logic.clpr import is_real_expression, real_bound  # noqa: PLC0415
    if is_real_expression(expr, "inf/2"):
        if real_bound(expr, result, trail, "inf"):
            yield None
        return
    from clausal.logic.clpq import inf as _inf_fn  # noqa: PLC0415
    if _inf_fn(expr, result, trail):
        yield None


# ══════════════════════════════════════════════════════════════════════════════
# Module API — clpq.rational, clpr.real, clpq.maximize, etc.
# ══════════════════════════════════════════════════════════════════════════════

# ── CLP(Q) module ────────────────────────────────────────────────────────────

@_builtin("clpq.rational", 1)
def _clpq_mod_rational(constraints, trail, k):
    """clpq.rational((constraints)) — post rational constraints."""
    from clausal.logic.clpq import clpq_constraint_block
    if clpq_constraint_block(constraints, trail):
        yield None

@_builtin("clpq.maximize", 2)
def _clpq_mod_maximize(expr, result, trail, k):
    """clpq.maximize(Expr, Result) — maximize over rationals."""
    from clausal.logic.clpq import maximize as _fn
    if _fn(expr, result, trail):
        yield None

@_builtin("clpq.minimize", 2)
def _clpq_mod_minimize(expr, result, trail, k):
    """clpq.minimize(Expr, Result) — minimize over rationals."""
    from clausal.logic.clpq import minimize as _fn
    if _fn(expr, result, trail):
        yield None

@_builtin("clpq.supremum", 2)
def _clpq_mod_sup(expr, result, trail, k):
    """clpq.supremum(Expr, Result) — compute upper bound without committing."""
    from clausal.logic.clpq import sup as _fn
    if _fn(expr, result, trail):
        yield None

@_builtin("clpq.infimum", 2)
def _clpq_mod_inf(expr, result, trail, k):
    """clpq.infimum(Expr, Result) — compute lower bound without committing."""
    from clausal.logic.clpq import inf as _fn
    if _fn(expr, result, trail):
        yield None

@_builtin("clpq.entailed", 1)
def _clpq_mod_entailed(constraint, trail, k):
    """clpq.entailed(Constraint) — succeed if constraint is implied."""
    from clausal.logic.clpq import entailed as _fn
    from clausal.logic.variables import deref as _deref
    from clausal.pythonic_ast.nodes import LtE, Lt, GtE, Gt, ArithEq, ArithNeq
    node = _deref(constraint)
    op_map = {LtE: "=<", Lt: "<", GtE: ">=", Gt: ">", ArithEq: "=", ArithNeq: "\\="}
    op = op_map.get(type(node))
    if op and _fn(op, node.left, node.right, trail):
        yield None

@_builtin("clpq.dump", 2)
def _clpq_mod_dump(vars_list, result, trail, k):
    """clpq.dump(Vars, Constraints) — dump constraint store."""
    from clausal.logic.clpq import dump_q as _fn
    from clausal.logic.variables import deref as _deref, unify as _unify
    constraints = _fn(_deref(vars_list), trail)
    if _unify(result, constraints, trail):
        yield None

# ── CLP(R) module ────────────────────────────────────────────────────────────

@_builtin("clpr.real", 1)
def _clpr_mod_real(constraints, trail, k):
    """clpr.real((constraints)) — post real-domain constraints."""
    from clausal.logic.clpr import clpr_constraint_block
    if clpr_constraint_block(constraints, trail):
        yield None

@_builtin("clpr.label", 1)
def _clpr_mod_label(vars_list, trail, k):
    """clpr.label(Vars) — bisection labeling over reals."""
    from clausal.logic.clpr import label_real
    yield from label_real(vars_list, trail)

@_builtin("clpr.label", 2)
def _clpr_mod_label_eps(vars_list, eps, trail, k):
    """clpr.label(Vars, Eps) — bisection labeling with precision."""
    from clausal.logic.clpr import label_real
    from clausal.logic.variables import deref as _deref
    yield from label_real(vars_list, trail, eps=float(_deref(eps)))


# ── PySAT builtins ──────────────────────────────────────────────────────────
# Import to register pysat.* builtins (cadical, glucose, minisat, etc.)
import clausal.logic.builtins.sat_constraints  # noqa: E402, F401

# ── OR-Tools builtins ──────────────────────────────────────────────────────
# Import to register ortools.* builtins (cpsat, glop, scip, graph, routing)
import clausal.logic.builtins.ortools_constraints  # noqa: E402, F401
