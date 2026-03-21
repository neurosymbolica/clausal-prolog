"""Constraint builtins: Dif/2, Eq/3, DifT/3, InDomain/3, Label/1,
AllDifferent/1, Equivalent/2, Sat/1, Taut/2, SatCount/2, BoolLabeling/1,
InReal/1, InReal/3, LabelReal/1, LabelReal/2."""

from __future__ import annotations

from clausal.logic.builtins._registry import _builtin


@_builtin("Dif", 2)
def _dif__2(x, y, trail, k):
    """dif(X, Y) — disequality constraint: succeed if X and Y can remain different."""
    from clausal.logic.constraints import dif as _dif_fn  # noqa: PLC0415
    if _dif_fn(x, y, trail):
        yield None


# ── Reified builtins (V2-8 Phase B) ──────────────────────────────────────────


@_builtin("Eq", 3)
def _eq__3(x, y, t, trail, k):
    """eq(X, Y, T) — reified equality: T is True if X=Y, False if dif(X,Y)."""
    from clausal.logic.reif import eq__3  # noqa: PLC0415
    yield from eq__3(x, y, t, trail, k)


@_builtin("DifT", 3)
def _dif_t__3(x, y, t, trail, k):
    """dif_t(X, Y, T) — reified disequality: T is True if dif(X,Y), False if X=Y."""
    from clausal.logic.reif import dif_t__3  # noqa: PLC0415
    yield from dif_t__3(x, y, t, trail, k)


# ── CLP(FD) builtins ─────────────────────────────────────────────────────────


@_builtin("InDomain", 3)
def _in_domain__3(var_or_list, lo, hi, trail, k):
    """in_domain(Var, Lo, Hi) — post domain [Lo, Hi] on Var or list of Vars."""
    from clausal.logic.clpfd import in_domain as _in_domain_fn  # noqa: PLC0415
    if _in_domain_fn(var_or_list, lo, hi, trail):
        yield None


@_builtin("Label", 1)
def _label__1(vars_list, trail, k):
    """label(Vars) — enumerate values for FD-constrained variables."""
    from clausal.logic.clpfd import label as _label_fn  # noqa: PLC0415
    yield from _label_fn(vars_list, trail)


@_builtin("AllDifferent", 1)
def _all_different__1(vars_list, trail, k):
    """all_different(Vars) — post all-different constraint on list of Vars."""
    from clausal.logic.clpfd import all_different as _all_diff_fn  # noqa: PLC0415
    if _all_diff_fn(vars_list, trail):
        yield None


@_builtin("Equivalent", 2)
def _equivalent__2(t1, t2, trail, k):
    """equivalent(T1, T2) — structural equality (old == behavior)."""
    from clausal.logic.clpfd import equivalent as _equiv_fn  # noqa: PLC0415
    if _equiv_fn(t1, t2, trail):
        yield None


# ── CLP(B) builtins ─────────────────────────────────────────────────────────


@_builtin("Sat", 1)
def _sat__1(expr, trail, k):
    """Sat(Expr) — post Boolean constraint, fail if unsatisfiable."""
    from clausal.logic.clpb import sat as _sat_fn  # noqa: PLC0415
    if _sat_fn(expr, trail):
        yield None


@_builtin("Taut", 2)
def _taut__2(expr, t, trail, k):
    """Taut(Expr, T) — T=1 if tautology, T=0 if contradiction, else fail."""
    from clausal.logic.clpb import taut as _taut_fn  # noqa: PLC0415
    if _taut_fn(expr, t, trail):
        yield None


@_builtin("SatCount", 2)
def _sat_count__2(expr, count, trail, k):
    """SatCount(Expr, N) — N is the number of satisfying assignments."""
    from clausal.logic.clpb import sat_count as _sat_count_fn  # noqa: PLC0415
    if _sat_count_fn(expr, count, trail):
        yield None


@_builtin("BoolLabeling", 1)
def _bool_labeling__1(vars_list, trail, k):
    """BoolLabeling(Vars) — enumerate 0/1 assignments for Boolean variables."""
    from clausal.logic.clpb import bool_labeling as _bool_labeling_fn  # noqa: PLC0415
    yield from _bool_labeling_fn(vars_list, trail)


# ── CLP(R) builtins ──────────────────────────────────────────────────────────

import math as _math  # noqa: E402


@_builtin("InReal", 1)
def _in_real__1(var_or_list, trail, k):
    """InReal(Var) — declare real variable with unbounded domain [-inf, +inf]."""
    from clausal.logic.clpr import in_real as _in_real_fn  # noqa: PLC0415
    if _in_real_fn(var_or_list, -_math.inf, _math.inf, trail):
        yield None


@_builtin("InReal", 3)
def _in_real__3(var_or_list, lo, hi, trail, k):
    """InReal(Var, Lo, Hi) — declare real variable with domain [Lo, Hi]."""
    from clausal.logic.clpr import in_real as _in_real_fn  # noqa: PLC0415
    if _in_real_fn(var_or_list, float(lo), float(hi), trail):
        yield None


@_builtin("LabelReal", 1)
def _label_real__1(vars_list, trail, k):
    """LabelReal(Vars) — bisect real intervals to IEEE float precision."""
    from clausal.logic.clpr import label_real as _label_real_fn  # noqa: PLC0415
    yield from _label_real_fn(vars_list, trail)


@_builtin("LabelReal", 2)
def _label_real__2(vars_list, eps, trail, k):
    """LabelReal(Vars, Eps) — bisect real intervals until width <= Eps."""
    from clausal.logic.clpr import label_real as _label_real_fn  # noqa: PLC0415
    yield from _label_real_fn(vars_list, trail, eps=float(eps))
