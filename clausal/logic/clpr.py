"""clausal.logic.clpr — CLP(R) real-domain constraint solver.

Interval arithmetic over IEEE doubles with outward rounding.  Unified
syntax with CLP(FD): the same ``==``, ``<``, ``<=``, ``>``, ``>=``,
``!=`` operators work for both domains.  The domain type is determined
by how the variable was declared (``in_real``) or by the presence of a
``float`` literal in the constraint.

Domain representation
---------------------
A ``RealVar`` stores a closed interval ``[lo, hi]`` of IEEE doubles.
``lo`` is rounded toward ``-inf`` and ``hi`` toward ``+inf`` after
every floating-point operation, so the true real value is always
inside the interval (soundness guarantee).

Trail safety
------------
Every narrowing creates a **new** ``RealVar`` and calls
``put_attr(var, REAL_KEY, new_state, trail)``.  The old ``RealVar`` is
restored on backtrack.  Never mutate in place.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any

from clausal.logic.variables import (
    Var,
    Trail,
    deref,
    is_var,
    unify,
    put_attr,
    get_attr,
    del_attr,
    register_attr_hook,
)

# ── Constants ─────────────────────────────────────────────────────────────────

REAL_KEY = "real"


# ── RealVar: per-variable real-domain state ───────────────────────────────────


class RealVar:
    """Real-domain state for one variable.

    Immutable for trail safety — narrowing creates a new instance.
    ``lo`` is rounded toward ``-inf``, ``hi`` toward ``+inf`` after
    every arithmetic operation, so the true value is always inside.
    """
    __slots__ = ('lo', 'hi', 'constraints')

    def __init__(self, lo: float, hi: float, constraints: tuple = ()):
        self.lo = lo
        self.hi = hi
        self.constraints = constraints  # tuple[RealConstraint, ...]


# ── Outward-rounded interval arithmetic ───────────────────────────────────────


def _dn_py(x: float) -> float:
    """Round x toward -inf by one ULP (for lower bounds)."""
    return math.nextafter(x, -math.inf)


def _up_py(x: float) -> float:
    """Round x toward +inf by one ULP (for upper bounds)."""
    return math.nextafter(x, math.inf)


def _iadd_py(alo: float, ahi: float, blo: float, bhi: float) -> tuple[float, float]:
    return _dn(alo + blo), _up(ahi + bhi)


def _isub_py(alo: float, ahi: float, blo: float, bhi: float) -> tuple[float, float]:
    return _dn(alo - bhi), _up(ahi - blo)


def _imul_py(alo: float, ahi: float, blo: float, bhi: float) -> tuple[float, float]:
    corners = [alo * blo, alo * bhi, ahi * blo, ahi * bhi]
    # A 0*inf corner is NaN; Python min/max propagate NaN (order-dependent),
    # which _narrow_real then reads as a wipeout → spurious failure.  Skip NaN
    # corners like the C fmin/fmax path so the fallback stays bit-identical
    # (A08-F012).
    corners = [c for c in corners if not math.isnan(c)] or [0.0]
    return _dn(min(corners)), _up(max(corners))


def _idiv_py(alo: float, ahi: float, blo: float, bhi: float) -> tuple[float, float]:
    """Divide [alo,ahi] by [blo,bhi]. Returns [-inf,inf] if 0 ∈ denominator."""
    if blo <= 0.0 <= bhi:
        return -math.inf, math.inf
    corners = [alo / blo, alo / bhi, ahi / blo, ahi / bhi]
    corners = [c for c in corners if not math.isnan(c)] or [0.0]  # A08-F012
    return _dn(min(corners)), _up(max(corners))


def _ipow_int_py(alo: float, ahi: float, n: int) -> tuple[float, float]:
    """Interval [alo,ahi] raised to integer power n."""
    if n == 0:
        return 1.0, 1.0
    if n < 0:
        lo, hi = _ipow_int(alo, ahi, -n)
        return _idiv(1.0, 1.0, lo, hi)
    if n % 2 == 0:
        # Even power: non-negative result
        if alo <= 0.0 <= ahi:
            lo_val = 0.0
        else:
            lo_val = min(abs(alo), abs(ahi)) ** n
        hi_val = max(abs(alo), abs(ahi)) ** n
        return _dn(lo_val), _up(hi_val)
    # Odd power: monotone increasing
    return _dn(alo ** n), _up(ahi ** n)


def _isqrt_py(alo: float, ahi: float) -> tuple[float, float]:
    lo = max(0.0, alo)
    if lo > ahi:
        return math.nan, math.nan  # wipeout
    return _dn(math.sqrt(lo)), _up(math.sqrt(ahi))


def _iabs_py(alo: float, ahi: float) -> tuple[float, float]:
    if alo >= 0:
        return alo, ahi
    if ahi <= 0:
        return -ahi, -alo
    return 0.0, max(-alo, ahi)


def _isin_py(alo: float, ahi: float) -> tuple[float, float]:
    """Interval of sin over [alo, ahi]."""
    if ahi - alo >= 2 * math.pi:
        return -1.0, 1.0
    k_lo = math.ceil(alo / (math.pi / 2))
    k_hi = math.floor(ahi / (math.pi / 2))
    vals = [math.sin(alo), math.sin(ahi)]
    for k in range(int(k_lo), int(k_hi) + 1):
        vals.append(math.sin(k * math.pi / 2))
    return _dn(min(vals)), _up(max(vals))


def _icos_py(alo: float, ahi: float) -> tuple[float, float]:
    """Interval of cos over [alo, ahi]."""
    if ahi - alo >= 2 * math.pi:
        return -1.0, 1.0
    k_lo = math.ceil(alo / math.pi)
    k_hi = math.floor(ahi / math.pi)
    vals = [math.cos(alo), math.cos(ahi)]
    for k in range(int(k_lo), int(k_hi) + 1):
        vals.append(math.cos(k * math.pi))
    return _dn(min(vals)), _up(max(vals))


def _iexp_py(alo: float, ahi: float) -> tuple[float, float]:
    return _dn(math.exp(alo)), _up(math.exp(ahi))


def _ilog_py(alo: float, ahi: float) -> tuple[float, float]:
    if ahi <= 0.0:
        return math.nan, math.nan  # wipeout
    if alo <= 0.0:
        return -math.inf, _up(math.log(ahi))
    return _dn(math.log(alo)), _up(math.log(ahi))


def _ifloordiv_py(alo: float, ahi: float, blo: float, bhi: float) -> tuple[float, float]:
    """Interval of a // b (floor division)."""
    if blo <= 0.0 <= bhi:
        return -math.inf, math.inf
    corners = [math.floor(alo / blo), math.floor(alo / bhi),
               math.floor(ahi / blo), math.floor(ahi / bhi)]
    return float(min(corners)), float(max(corners))


def _imod_py(alo: float, ahi: float, blo: float, bhi: float) -> tuple[float, float]:
    """Interval of a % b (real modulo). Conservative outer bound.

    Python float ``%`` takes the sign of the divisor: ``a % b`` lies in
    ``[0, b)`` for ``b > 0`` and ``(b, 0]`` for ``b < 0``.  The previous
    ``[0, |b|-1]`` bound was integer-modulo semantics — it excluded real
    results (1.5 % 2 == 1.5 fell outside [0, 1]) and, for ``|b| < 1``, produced
    an inverted/empty interval that failed every posting (A08-F009).
    """
    if blo <= 0.0 <= bhi:
        return -math.inf, math.inf
    if blo > 0:
        # b > 0: result in [0, b) ⊆ [0, bhi] (upper end kept closed for soundness)
        return 0.0, _up(bhi)
    # b < 0: result in (b, 0] ⊆ [blo, 0]
    return _dn(blo), 0.0


def _iatan_py(alo: float, ahi: float) -> tuple[float, float]:
    return _dn(math.atan(alo)), _up(math.atan(ahi))


def _iasin_py(alo: float, ahi: float) -> tuple[float, float]:
    clo, chi = max(-1.0, alo), min(1.0, ahi)
    if clo > chi:
        return math.nan, math.nan
    return _dn(math.asin(clo)), _up(math.asin(chi))


def _iacos_py(alo: float, ahi: float) -> tuple[float, float]:
    clo, chi = max(-1.0, alo), min(1.0, ahi)
    if clo > chi:
        return math.nan, math.nan
    # acos is monotone decreasing
    return _dn(math.acos(chi)), _up(math.acos(clo))


# ── C-accelerated versions with Python fallback ─────────────────────────────

_dn = _dn_py
_up = _up_py
_iadd = _iadd_py
_isub = _isub_py
_imul = _imul_py
_idiv = _idiv_py
_ipow_int = _ipow_int_py
_isqrt = _isqrt_py
_iabs = _iabs_py
_isin = _isin_py
_icos = _icos_py
_iexp = _iexp_py
_ilog = _ilog_py
_iatan = _iatan_py
_iasin = _iasin_py
_iacos = _iacos_py
_ifloordiv = _ifloordiv_py
_imod = _imod_py

try:
    from clausal.logic._clpr_core import (  # noqa: F811
        _dn, _up,
        _iadd, _isub, _imul, _idiv,
        _ipow_int, _isqrt, _iabs,
        _isin, _icos, _iexp, _ilog,
        _iatan, _iasin, _iacos,
        _ifloordiv, _imod,
    )
except ImportError:
    pass


# ── Lazy term-node imports (mirrors clpfd.py) ─────────────────────────────────

_Add = _Sub = _Mult = _Div = _FloorDiv = _Mod = _Pow = _Negate = None
_ArithEq = _ArithNeq = _Lt = _LtE = _Gt = _GtE = _CompareChain = None


def _ensure_term_imports() -> None:
    global _Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow, _Negate
    global _ArithEq, _ArithNeq, _Lt, _LtE, _Gt, _GtE, _CompareChain
    if _Add is None:
        from clausal.terms import Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate
        _Add = Add
        _Sub = Sub
        _Mult = Mult
        _Div = Div
        _FloorDiv = FloorDiv
        _Mod = Mod
        _Pow = Pow
        _Negate = Negate
    if _ArithEq is None:
        from clausal.pythonic_ast.nodes import (
            ArithEq, ArithNeq, Lt, LtE, Gt, GtE, CompareChain,
        )
        _ArithEq, _ArithNeq = ArithEq, ArithNeq
        _Lt, _LtE, _Gt, _GtE = Lt, LtE, Gt, GtE
        _CompareChain = CompareChain


# ── Expression interval evaluator ─────────────────────────────────────────────


def _get_var_interval(var: Var) -> tuple[float, float]:
    """Return the current interval for a variable (real or FD).

    when both attributes exist, returns the intersection of both bounds
    so that real constraints see the tightest possible interval.
    """
    lo, hi = -math.inf, math.inf
    state = get_attr(var, REAL_KEY)
    if state is not None:
        lo, hi = state.lo, state.hi
    from clausal.logic.clpfd import FD_KEY, domain_min, domain_max
    fd_state = get_attr(var, FD_KEY)
    if fd_state is not None:
        fd_lo = float(domain_min(fd_state.domain))
        fd_hi = float(domain_max(fd_state.domain))
        lo = max(lo, fd_lo)
        hi = min(hi, fd_hi)
    return lo, hi


def _expr_interval(expr, trail: Trail) -> tuple[float, float]:
    """Compute the interval [lo, hi] containing all possible values of expr."""
    expr = deref(expr)
    if isinstance(expr, bool):
        return -math.inf, math.inf  # booleans are not reals
    if isinstance(expr, (int, float)):
        v = float(expr)
        return v, v
    if is_var(expr):
        return _get_var_interval(expr)
    _ensure_term_imports()
    if isinstance(expr, _Add):
        alo, ahi = _expr_interval(expr.left, trail)
        blo, bhi = _expr_interval(expr.right, trail)
        return _iadd(alo, ahi, blo, bhi)
    if isinstance(expr, _Sub):
        alo, ahi = _expr_interval(expr.left, trail)
        blo, bhi = _expr_interval(expr.right, trail)
        return _isub(alo, ahi, blo, bhi)
    if isinstance(expr, _Mult):
        alo, ahi = _expr_interval(expr.left, trail)
        blo, bhi = _expr_interval(expr.right, trail)
        return _imul(alo, ahi, blo, bhi)
    if isinstance(expr, _Div):
        alo, ahi = _expr_interval(expr.left, trail)
        blo, bhi = _expr_interval(expr.right, trail)
        return _idiv(alo, ahi, blo, bhi)
    if isinstance(expr, _Pow):
        alo, ahi = _expr_interval(expr.left, trail)
        r = deref(expr.right)
        if isinstance(r, int):
            return _ipow_int(alo, ahi, r)
        blo, bhi = _expr_interval(r, trail)
        # General real power: approximate (sound for alo >= 0)
        if alo >= 0 and blo >= 0:
            return _dn(alo ** blo), _up(ahi ** bhi)
        return -math.inf, math.inf
    if isinstance(expr, _FloorDiv):
        alo, ahi = _expr_interval(expr.left, trail)
        blo, bhi = _expr_interval(expr.right, trail)
        return _ifloordiv(alo, ahi, blo, bhi)
    if isinstance(expr, _Mod):
        alo, ahi = _expr_interval(expr.left, trail)
        blo, bhi = _expr_interval(expr.right, trail)
        return _imod(alo, ahi, blo, bhi)
    if isinstance(expr, _Negate):
        alo, ahi = _expr_interval(expr.operand, trail)
        return -ahi, -alo
    return -math.inf, math.inf


# ── Narrowing helper ──────────────────────────────────────────────────────────


def _narrow_real(var: Var, new_lo: float, new_hi: float,
                 trail: Trail, queue: deque) -> bool:
    """Narrow var's interval to [new_lo, new_hi].

    Returns False on wipeout (new_lo > new_hi or NaN).
    Queues all affected constraints for re-propagation.
    Trail-safe: creates new RealVar if bounds change.
    """
    if math.isnan(new_lo) or math.isnan(new_hi):
        return False
    state = get_attr(var, REAL_KEY)
    if state is None:
        return True  # not a real var, skip
    lo = max(state.lo, new_lo)
    hi = min(state.hi, new_hi)
    if lo > hi:
        return False  # wipeout
    if lo == state.lo and hi == state.hi:
        return True  # no change
    new_state = RealVar(lo, hi, state.constraints)
    put_attr(var, REAL_KEY, new_state, trail)
    queue.extend(state.constraints)
    return True


# ── HC4 inversion: narrow expression variables ────────────────────────────────


def _nth_root(x: float, n: int) -> float:
    """Real nth root (works for negative x when n is odd)."""
    if x >= 0:
        return x ** (1.0 / n)
    return -((-x) ** (1.0 / n))


def _invert_expr(expr, clo: float, chi: float, trail: Trail, queue: deque) -> bool:
    """Narrow variables in expr such that expr ∈ [clo, chi] (HC4 inversion).

    Returns False if the constraint is unsatisfiable.
    """
    if math.isnan(clo) or math.isnan(chi) or clo > chi:
        return False
    expr = deref(expr)
    if isinstance(expr, bool):
        return True  # booleans are not reals, cannot narrow
    if isinstance(expr, (int, float)):
        v = float(expr)
        return clo <= v <= chi
    if is_var(expr):
        state = get_attr(expr, REAL_KEY)
        if state is not None:
            return _narrow_real(expr, clo, chi, trail, queue)
        return True  # not a real var, can't narrow here
    _ensure_term_imports()
    if isinstance(expr, _Add):
        # L + R ∈ [clo, chi]
        # L ∈ [clo - R_hi, chi - R_lo], R ∈ [clo - L_hi, chi - L_lo]
        Rlo, Rhi = _expr_interval(expr.right, trail)
        if not _invert_expr(expr.left, _dn(clo - Rhi), _up(chi - Rlo), trail, queue):
            return False
        Llo, Lhi = _expr_interval(expr.left, trail)
        return _invert_expr(expr.right, _dn(clo - Lhi), _up(chi - Llo), trail, queue)
    if isinstance(expr, _Sub):
        # L - R ∈ [clo, chi]
        # L ∈ [clo + R_lo, chi + R_hi], R ∈ [L_lo - chi, L_hi - clo]
        Rlo, Rhi = _expr_interval(expr.right, trail)
        if not _invert_expr(expr.left, _dn(clo + Rlo), _up(chi + Rhi), trail, queue):
            return False
        Llo, Lhi = _expr_interval(expr.left, trail)
        return _invert_expr(expr.right, _dn(Llo - chi), _up(Lhi - clo), trail, queue)
    if isinstance(expr, _Mult):
        # L * R ∈ [clo, chi]
        lv = deref(expr.left)
        rv = deref(expr.right)
        if is_var(lv) and lv is rv:
            # V * V = V² — same variable on both sides; invert as square
            # V² ∈ [clo, chi]: need chi ≥ 0, and V ∈ [-sqrt(chi), sqrt(chi)] (hull)
            if chi < 0:
                return False
            hi_root = _up(math.sqrt(chi))
            lo_root = 0.0 if clo <= 0.0 else _dn(math.sqrt(clo))
            return _invert_expr(lv, -hi_root, hi_root, trail, queue)
        # General case: L * R ∈ [clo, chi]
        # L ∈ [clo, chi] / R_interval  (sound; no narrowing if 0 ∈ R)
        Rlo, Rhi = _expr_interval(expr.right, trail)
        Lnlo, Lnhi = _idiv(clo, chi, Rlo, Rhi)
        if not _invert_expr(expr.left, Lnlo, Lnhi, trail, queue):
            return False
        Llo, Lhi = _expr_interval(expr.left, trail)
        Rnlo, Rnhi = _idiv(clo, chi, Llo, Lhi)
        return _invert_expr(expr.right, Rnlo, Rnhi, trail, queue)
    if isinstance(expr, _Div):
        # L / R ∈ [clo, chi]
        # L ∈ [clo, chi] * R_interval
        Rlo, Rhi = _expr_interval(expr.right, trail)
        Lnlo, Lnhi = _imul(clo, chi, Rlo, Rhi)
        if not _invert_expr(expr.left, Lnlo, Lnhi, trail, queue):
            return False
        # R ∈ L_interval / [clo, chi]
        Llo, Lhi = _expr_interval(expr.left, trail)
        Rnlo, Rnhi = _idiv(Llo, Lhi, clo, chi)
        return _invert_expr(expr.right, Rnlo, Rnhi, trail, queue)
    if isinstance(expr, _Pow):
        r = deref(expr.right)
        if isinstance(r, int) and r > 0:
            if r % 2 == 0:
                # Even power: L^r ∈ [clo, chi], L ∈ [-chi^(1/r), chi^(1/r)] (hull)
                if chi < 0:
                    return False
                chi_r = _up(chi ** (1.0 / r))
                clo_r = 0.0 if clo <= 0.0 else _dn(clo ** (1.0 / r))
                return _invert_expr(expr.left, -chi_r, chi_r, trail, queue)
            else:
                # Odd power: monotone, fully invertible
                new_lo = _dn(_nth_root(clo, r))
                new_hi = _up(_nth_root(chi, r))
                return _invert_expr(expr.left, new_lo, new_hi, trail, queue)
        return True  # Can't invert general power — skip
    if isinstance(expr, _Negate):
        return _invert_expr(expr.operand, -chi, -clo, trail, queue)
    return True  # Unknown expression — can't narrow


# ── Variable collection ───────────────────────────────────────────────────────


def _collect_constraint_vars(lhs, rhs) -> tuple:
    result: list = []
    _collect_vars_from(lhs, result)
    _collect_vars_from(rhs, result)
    return tuple(result)


def _collect_vars_from(expr, result: list) -> None:
    expr = deref(expr)
    if is_var(expr):
        result.append(expr)
        return
    _ensure_term_imports()
    if isinstance(expr, (_Add, _Sub, _Mult)):
        _collect_vars_from(expr.left, result)
        _collect_vars_from(expr.right, result)
    elif _Div is not None and isinstance(expr, (_Div, _FloorDiv, _Mod)):
        _collect_vars_from(expr.left, result)
        _collect_vars_from(expr.right, result)
    elif _Pow is not None and isinstance(expr, _Pow):
        _collect_vars_from(expr.left, result)
        _collect_vars_from(expr.right, result)
    elif _Negate is not None and isinstance(expr, _Negate):
        _collect_vars_from(expr.operand, result)


# ── Constraint base class and concrete types ──────────────────────────────────


class RealConstraint:
    """Base class for CLP(R) constraints."""
    __slots__ = ('lhs', 'rhs', 'vars')

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs
        self.vars = _collect_constraint_vars(lhs, rhs)

    def propagate(self, trail: Trail, queue: deque) -> bool:
        raise NotImplementedError


class RealEqConstraint(RealConstraint):
    """lhs == rhs (real equality with active interval narrowing)."""

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        llo, lhi = _expr_interval(lhs, trail)
        rlo, rhi = _expr_interval(rhs, trail)
        # Intersect intervals
        clo = max(llo, rlo)
        chi = min(lhi, rhi)
        if clo > chi:
            return False
        # HC4 inversion: narrow variables in lhs
        if not _invert_expr(lhs, clo, chi, trail, queue):
            return False
        # Recompute after lhs narrowing, then narrow rhs
        rlo2, rhi2 = _expr_interval(rhs, trail)
        clo2 = max(clo, rlo2)
        chi2 = min(chi, rhi2)
        if clo2 > chi2:
            return False
        return _invert_expr(rhs, clo2, chi2, trail, queue)


class RealLeConstraint(RealConstraint):
    """lhs <= rhs."""

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        llo, lhi = _expr_interval(lhs, trail)
        rlo, rhi = _expr_interval(rhs, trail)
        if llo > rhi:
            return False  # definitely unsatisfied
        # lhs can't exceed rhs's maximum
        if not _invert_expr(lhs, -math.inf, rhi, trail, queue):
            return False
        # rhs must be at least lhs's minimum
        return _invert_expr(rhs, llo, math.inf, trail, queue)


class RealLtConstraint(RealConstraint):
    """lhs < rhs (strict)."""

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        # Aliased operands: X < X is unsatisfiable.  Also prevents the
        # ULP-by-ULP narrowing hang when {X<Y} is followed by X is Y
        # (A08-F010).
        if lhs is rhs:
            return False
        llo, lhi = _expr_interval(lhs, trail)
        rlo, rhi = _expr_interval(rhs, trail)
        if llo >= rhi:
            return False
        if not _invert_expr(lhs, -math.inf, _dn(rhi), trail, queue):
            return False
        return _invert_expr(rhs, _up(llo), math.inf, trail, queue)


class RealNeConstraint(RealConstraint):
    """lhs != rhs (real disequality, passive — checked when ground)."""

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        # Aliased operands: X != X is unsatisfiable.  The point-interval check
        # below misses this after X is Y aliases the two vars (A08-F011).
        if lhs is rhs:
            return False
        llo, lhi = _expr_interval(lhs, trail)
        rlo, rhi = _expr_interval(rhs, trail)
        # Only fail when both sides are a single point with equal value
        if llo == lhi and rlo == rhi and llo == rlo:
            return False
        return True


# ── Propagation engine ────────────────────────────────────────────────────────


# A strict-inequality cycle ({X<Y, Y<X}) provably narrows the store to empty,
# but only over ~1/ULP passes as each pass shaves a single ULP off both ends —
# an effective hang.  Interval CLP(R) cannot decide such strict cycles exactly
# without ε-augmented rationals (deferred, A08-D004), so bound the fixpoint:
# a well-posed system reaches its fixpoint in far fewer steps, while ULP-creep
# blows past the budget and is reported unsatisfiable (A08-F010).
_PROPAGATE_STEP_BUDGET = 100_000


def _propagate(queue: deque, trail: Trail) -> bool:
    """Fixpoint narrowing loop: process constraints until stable or wipeout."""
    steps = 0
    while queue:
        constraint = queue.popleft()
        if not constraint.propagate(trail, queue):
            return False
        steps += 1
        if steps > _PROPAGATE_STEP_BUDGET:
            # Non-terminating ULP-creep — treat as unsatisfiable rather than
            # hang (A08-F010).
            return False
    return True


# ── Constraint attachment ─────────────────────────────────────────────────────


def _add_real_constraint(var: Var, constraint: RealConstraint, trail: Trail) -> None:
    """Attach a constraint to a real variable (trail-safe)."""
    state = get_attr(var, REAL_KEY)
    if state is None:
        return
    new_state = RealVar(state.lo, state.hi, state.constraints + (constraint,))
    put_attr(var, REAL_KEY, new_state, trail)


def _post_real_constraint(constraint: RealConstraint, trail: Trail) -> bool:
    """Attach constraint to all its variables and run initial propagation."""
    for v in constraint.vars:
        v = deref(v)
        if is_var(v):
            _add_real_constraint(v, constraint, trail)
    queue: deque = deque([constraint])
    return _propagate(queue, trail)


# ── Ensure real state ─────────────────────────────────────────────────────────


def _ensure_real(var: Var, trail: Trail) -> RealVar:
    """Get or auto-create RealVar for a variable.

    If the variable already has an FD attribute, promotes it to a real
    interval with the same outer bounds (losing interior holes).
    """
    state = get_attr(var, REAL_KEY)
    if state is not None:
        return state
    from clausal.logic.clpfd import FD_KEY, domain_min, domain_max
    fd_state = get_attr(var, FD_KEY)
    if fd_state is not None:
        _promote_fd_to_real(var, trail)
        return get_attr(var, REAL_KEY)
    state = RealVar(-math.inf, math.inf)
    put_attr(var, REAL_KEY, state, trail)
    return state


# ── FD promotion ──────────────────────────────────────────────────────────────


def _promote_fd_to_real(var: Var, trail: Trail) -> None:
    """Add a real interval [fd_min, fd_max] alongside the existing FD attribute.

    The FD attribute is kept so that both hooks fire independently on
    unification — the FD hook continues to enforce integrality and domain
    holes while the real hook handles continuous narrowing.
    """
    from clausal.logic.clpfd import FD_KEY, domain_min, domain_max
    fd_state = get_attr(var, FD_KEY)
    if fd_state is None:
        return
    lo = float(domain_min(fd_state.domain))
    hi = float(domain_max(fd_state.domain))
    real_state = RealVar(lo, hi, ())
    put_attr(var, REAL_KEY, real_state, trail)


# ── Attribute hook ────────────────────────────────────────────────────────────


def _real_hook(attr_value: Any, bound_to: Any, trail: Trail) -> bool:
    """Called when a real-constrained var is unified.

    *attr_value* is the RealVar instance.
    *bound_to* is the value the variable was bound to.
    """
    state = attr_value
    bound_to = deref(bound_to)

    if isinstance(bound_to, bool):
        return False  # booleans are not reals

    if isinstance(bound_to, (int, float)):
        v = float(bound_to)
        if not (state.lo <= v <= state.hi):
            return False
        queue: deque = deque(state.constraints)
        return _propagate(queue, trail)

    if is_var(bound_to):
        other_state = get_attr(bound_to, REAL_KEY)
        if other_state is None:
            # Other var has no real state — check if it's an FD var
            from clausal.logic.clpfd import FD_KEY
            fd_state = get_attr(bound_to, FD_KEY)
            if fd_state is not None:
                _promote_fd_to_real(bound_to, trail)
                other_state = get_attr(bound_to, REAL_KEY)
            if other_state is None:
                # Transfer our real state to the other var
                put_attr(bound_to, REAL_KEY, state, trail)
                return True
        # Both have real state — intersect intervals, merge constraints
        new_lo = max(state.lo, other_state.lo)
        new_hi = min(state.hi, other_state.hi)
        if new_lo > new_hi:
            return False
        seen_ids: set[int] = set()
        merged: list = []
        for c in state.constraints + other_state.constraints:
            cid = id(c)
            if cid not in seen_ids:
                seen_ids.add(cid)
                merged.append(c)
        new_state = RealVar(new_lo, new_hi, tuple(merged))
        put_attr(bound_to, REAL_KEY, new_state, trail)
        queue = deque(merged)
        return _propagate(queue, trail)

    return False  # bound to non-numeric, non-var


register_attr_hook(REAL_KEY, _real_hook)


# ── Top-level API: domain declaration ────────────────────────────────────────


def in_real(var_or_list, lo: float, hi: float, trail: Trail) -> bool:
    """Post real domain [lo, hi] on a variable or list of variables."""
    lo = float(deref(lo))
    hi = float(deref(hi))
    targets = deref(var_or_list)
    if isinstance(targets, list):
        for v in targets:
            if not _post_real_domain(deref(v), lo, hi, trail):
                return False
        return True
    return _post_real_domain(targets, lo, hi, trail)


def _post_real_domain(target, lo: float, hi: float, trail: Trail) -> bool:
    """Post real domain on a single target (var or numeric)."""
    if isinstance(target, bool):
        return False
    if isinstance(target, (int, float)):
        v = float(target)
        return lo <= v <= hi
    if not is_var(target):
        return False
    state = get_attr(target, REAL_KEY)
    if state is None:
        final_lo, final_hi = lo, hi
        new_state = RealVar(final_lo, final_hi)
        put_attr(target, REAL_KEY, new_state, trail)
    else:
        final_lo = max(state.lo, lo)
        final_hi = min(state.hi, hi)
        if final_lo > final_hi:
            return False
        new_state = RealVar(final_lo, final_hi, state.constraints)
        put_attr(target, REAL_KEY, new_state, trail)
    # Bind if already a point
    if final_lo == final_hi:
        if not unify(target, final_lo, trail):
            return False
    return True


# ── Top-level API: constraint posting ────────────────────────────────────────


def _ensure_real_for_expr(expr, trail: Trail) -> None:
    """Ensure all Vars in expr have a real-domain attribute."""
    vars_list: list = []
    _collect_vars_from(expr, vars_list)
    for v in vars_list:
        v = deref(v)
        if is_var(v) and get_attr(v, REAL_KEY) is None:
            _ensure_real(v, trail)


def _is_ground_real_scalar(x) -> bool:
    """True for a concrete int/float that ``==`` can bind a var to.

    bools are not reals; NaN never equals anything, so it must take the
    constraint path (which fails it) rather than bind.
    """
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return True
    return isinstance(x, float) and not math.isnan(x)


def _cells_as_nodes(l, r, context):
    """clpfd's post-boundary rewrite, STRICT (ruling R9 A1, 2026-09-27): an
    arithmetic cell becomes its operator node, which is what the CLP(R) propagators
    walk; an atom or a non-evaluable compound raises ``type_error(evaluable,
    F/N)`` -- the CLP(R) propagators had no diagnosis of their own for it."""
    global _cells_as_nodes
    from clausal.logic.clpfd import _cells_as_nodes as impl  # noqa: PLC0415 -- clpfd imports this module lazily
    _cells_as_nodes = impl
    return impl(l, r, context)


_strip_for_real_solver = None


def _units_strip(l, r, context, trail):
    """The units side channel (clausal.logic.units_clp) after the cell
    rewrite, as CLP(Q) runs it: a physical quantity is its magnitude in the
    base unit and a united variable its shadow (the ``units_link`` hook binds
    the user's variable to a Quantity when the shadow binds); money is
    refused, since it must not be computed in floats. Untouched when no
    units material is involved."""
    global _strip_for_real_solver
    if _strip_for_real_solver is None:
        from clausal.logic.units_clp import strip_for_real_solver  # noqa: PLC0415
        _strip_for_real_solver = strip_for_real_solver
    stripped = _strip_for_real_solver(l, r, context, trail)
    return (l, r) if stripped is None else stripped


def real_eq(l, r, trail: Trail) -> bool:
    """Post lhs == rhs as a real constraint."""
    l = deref(l)
    r = deref(r)
    l, r = _cells_as_nodes(l, r, "(==)/2")   # ruling R9 A1
    l, r = _units_strip(l, r, "(==)/2", trail)
    # Ground check
    if not is_var(l) and not _is_expr(l) and not is_var(r) and not _is_expr(r):
        if isinstance(l, int) and not isinstance(l, bool) and isinstance(r, int) and not isinstance(r, bool):
            return l == r
        try:
            return float(l) == float(r)
        except (TypeError, ValueError):
            return l == r
    # One side ground, other a var: bind directly (mirrors q_eq).  The
    # attr hook checks any existing real domain/constraints on unify.
    # NaN is excluded — == with NaN has no solution, which the
    # constraint path establishes via interval wipeout.
    if is_var(l) and _is_ground_real_scalar(r):
        return unify(l, float(r), trail)
    if is_var(r) and _is_ground_real_scalar(l):
        return unify(r, float(l), trail)
    _ensure_real_for_expr(l, trail)
    _ensure_real_for_expr(r, trail)
    return _post_real_constraint(RealEqConstraint(l, r), trail)


def real_ne(l, r, trail: Trail) -> bool:
    """Post lhs != rhs as a real constraint."""
    l = deref(l)
    r = deref(r)
    l, r = _cells_as_nodes(l, r, "(!=)/2")   # ruling R9 A1
    l, r = _units_strip(l, r, "(!=)/2", trail)
    if not is_var(l) and not _is_expr(l) and not is_var(r) and not _is_expr(r):
        if isinstance(l, int) and not isinstance(l, bool) and isinstance(r, int) and not isinstance(r, bool):
            return l != r
        try:
            return float(l) != float(r)
        except (TypeError, ValueError):
            return l != r
    _ensure_real_for_expr(l, trail)
    _ensure_real_for_expr(r, trail)
    return _post_real_constraint(RealNeConstraint(l, r), trail)


def real_lt(l, r, trail: Trail) -> bool:
    """Post lhs < rhs as a real constraint."""
    l = deref(l)
    r = deref(r)
    l, r = _cells_as_nodes(l, r, "(<)/2")   # ruling R9 A1
    l, r = _units_strip(l, r, "(<)/2", trail)
    if not is_var(l) and not _is_expr(l) and not is_var(r) and not _is_expr(r):
        if isinstance(l, int) and not isinstance(l, bool) and isinstance(r, int) and not isinstance(r, bool):
            return l < r
        try:
            return float(l) < float(r)
        except (TypeError, ValueError):
            return l < r
    _ensure_real_for_expr(l, trail)
    _ensure_real_for_expr(r, trail)
    return _post_real_constraint(RealLtConstraint(l, r), trail)


def real_le(l, r, trail: Trail) -> bool:
    """Post lhs <= rhs as a real constraint."""
    l = deref(l)
    r = deref(r)
    l, r = _cells_as_nodes(l, r, "(=<)/2")   # ruling R9 A1
    l, r = _units_strip(l, r, "(=<)/2", trail)
    if not is_var(l) and not _is_expr(l) and not is_var(r) and not _is_expr(r):
        if isinstance(l, int) and not isinstance(l, bool) and isinstance(r, int) and not isinstance(r, bool):
            return l <= r
        try:
            return float(l) <= float(r)
        except (TypeError, ValueError):
            return l <= r
    _ensure_real_for_expr(l, trail)
    _ensure_real_for_expr(r, trail)
    return _post_real_constraint(RealLeConstraint(l, r), trail)


def real_gt(l, r, trail: Trail) -> bool:
    """Post lhs > rhs as a real constraint (swaps to <=)."""
    l, r = _cells_as_nodes(deref(l), deref(r), "(>)/2")
    l, r = _units_strip(l, r, "(>)/2", trail)      # under the operator the user wrote
    return real_lt(r, l, trail)


def real_ge(l, r, trail: Trail) -> bool:
    """Post lhs >= rhs as a real constraint (swaps to <=)."""
    l, r = _cells_as_nodes(deref(l), deref(r), "(>=)/2")
    l, r = _units_strip(l, r, "(>=)/2", trail)
    return real_le(r, l, trail)


def _is_expr(x) -> bool:
    """True if x is an arithmetic expression node (not a plain number or var)."""
    _ensure_term_imports()
    return isinstance(x, (_Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow, _Negate))


# ── Labeling: bisection search ────────────────────────────────────────────────


# ── Reading bounds: inf/2, sup/2 (ruling R17) ────────────────────────────────


def is_real_expression(expr, context: str) -> bool:
    """True if *expr* mentions a variable with a CLP(R) interval -- the test
    ``inf/2``/``sup/2`` use to answer from CLP(R) rather than CLP(Q)."""
    vars_list: list = []
    _collect_vars_from(_expr_node(expr, context), vars_list)
    return any(is_var(v := deref(x)) and get_attr(_solver_var(v), REAL_KEY) is not None
               for x in vars_list)


def _solver_var(v):
    """The variable CLP(R) holds the interval on: a united variable's shadow
    (the side channel posts there), else *v* itself."""
    from clausal.logic.units_constraint import UNITS_KEY  # noqa: PLC0415
    state = get_attr(v, UNITS_KEY)
    if state is not None and state.shadow is not None:
        return state.shadow
    return v


def _expr_node(expr, context):
    """*expr* with arithmetic cells as operator nodes (``type_error(evaluable,
    F/N)`` for anything else), as the constraint posters see it."""
    return _cells_as_nodes(deref(expr), 0, context)[0]


def real_bound(expr, result, trail: Trail, which: str) -> bool:
    """``inf(Expr, Inf)`` (*which* ``"inf"``) or ``sup(Expr, Sup)``: unify
    *result* with the lower (upper) bound CLP(R) has established for *expr*,
    as a float; FAIL when it is unbounded on that side.  Reads the store and
    never changes it, as the classic CLP(R) ``inf/2`` and ``sup/2`` do.

    The bound is the one interval propagation has PROVEN: sound (the true
    infimum is never below ``inf``), and exact for a variable whose bounds
    propagation fixed, but it can be looser than the true infimum where
    interval arithmetic over-approximates (``X - X`` over ``[0, 1]`` is
    ``[-1, 1]``) -- this solver narrows intervals, it is not a simplex.
    """
    context = f"{which}/2"
    node = _expr_node(expr, context)
    # The units side channel, as CLP(Q)'s sup/inf run it: a united variable
    # reads its shadow's interval and the bound comes back with the
    # expression's dimension (it read the unconstrained user variable before
    # and answered wrongly or not at all).
    from clausal.logic.units_clp import reattach, strip_expr_for_solver  # noqa: PLC0415
    stripped = strip_expr_for_solver(node, context, trail)
    node, dims = (node, {}) if stripped is None else stripped
    lo, hi = _expr_interval(node, trail)
    bound = lo if which == "inf" else hi
    if math.isinf(bound) or math.isnan(bound):
        return False
    return unify(result, reattach(bound, dims) if dims else bound, trail)


def label_real(vars_list, trail: Trail, eps: float | None = None):
    """Bisect real intervals until IEEE-point or eps width.

    Generator: yields None for each assignment leaf.

    Strategy: widest-first (pick the variable with the widest interval),
    analogous to largest-domain-first in CLP(FD), then bisect at midpoint.

    With eps=None: bisect until (lo + hi) / 2.0 == lo or hi in IEEE
    arithmetic — i.e., the interval is indistinguishable from a point at
    double precision.

    With eps: stop when hi - lo <= eps.
    """
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        vars_list = [vars_list]
    # A united variable's interval sits on its shadow (the units side
    # channel posted there): label the shadow, as label/1 and CLP(Q) do.
    from clausal.logic.units_clp import label_targets  # noqa: PLC0415
    vars_list = label_targets(vars_list, "label_real/1")

    # Collect unbound real vars that are still bisectable (not yet at resolution).
    # A var is "resolved" if its midpoint equals an endpoint (IEEE precision)
    # or its width is within eps.
    unbound: list = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            s = get_attr(v, REAL_KEY)
            if s is not None:
                if eps is None:
                    mid = (s.lo + s.hi) / 2.0
                    if mid > s.lo and mid < s.hi:
                        unbound.append(v)
                else:
                    if s.hi - s.lo > eps:
                        unbound.append(v)

    if not unbound:
        yield None
        return

    # Widest-first heuristic
    best = None
    best_width: float | None = None
    for v in unbound:
        v = deref(v)
        if not is_var(v):
            continue
        state = get_attr(v, REAL_KEY)
        if state is None:
            continue
        w = state.hi - state.lo
        if best_width is None or w > best_width:
            best = v
            best_width = w

    if best is None:
        yield None
        return

    # Bisect this variable iteratively (avoids Python recursion-limit issues
    # for intervals spanning subnormal floats, which can require ~1074 halvings).
    yield from _bisect_var(best, vars_list, trail, eps)


def _bisect_var(var: Var, vars_list: list, trail: Trail, eps: float | None):
    """Iteratively bisect *var*'s interval, recursing into label_real for
    the remaining variables at each leaf.

    Uses an explicit deque-based stack of (lo, hi, trail_mark) triples so
    that we never exhaust Python's call stack even for intervals that span
    the subnormal range (~1074 halvings from 0 to 1).
    """
    # Each stack entry: (lo, hi, mark) — the interval to try and the trail
    # mark to restore before trying it.
    stack: deque = deque()
    outer_mark = trail.mark()
    state = get_attr(var, REAL_KEY)
    stack.append((state.lo, state.hi, outer_mark))

    while stack:
        lo, hi, mark = stack.pop()

        # Restore trail to the state before this interval was committed
        trail.undo(mark)

        # Commit [lo, hi] for *var*
        q: deque = deque()
        if not (_narrow_real(var, lo, hi, trail, q) and _propagate(q, trail)):
            continue  # wipeout — skip this interval

        # Check termination
        mid = (lo + hi) / 2.0
        if eps is None:
            at_point = (mid <= lo or mid >= hi)
        else:
            at_point = (hi - lo <= eps)

        if at_point:
            # This variable is resolved; recurse for remaining vars
            yield from label_real(vars_list, trail, eps)
        else:
            # Push the two halves (right half first so left is processed first)
            mark_after = trail.mark()
            stack.append((mid, hi, mark_after))
            stack.append((lo, mid, mark_after))

    # Restore to state before any bisection
    trail.undo(outer_mark)


# ══════════════════════════════════════════════════════════════════════════════
# Module API — constraint block evaluator
# ══════════════════════════════════════════════════════════════════════════════

def clpr_constraint_block(constraints: Any, trail: Trail) -> bool:
    """Walk a tuple of Clausal AST constraint nodes and post each via CLP(R).

    Handles comparisons and ``CompareChain``.  Variables are auto-registered
    as real-domain.
    """
    _ensure_term_imports()
    constraints = deref(constraints)
    if isinstance(constraints, (list, tuple)):
        elements = constraints
    else:
        elements = [constraints]

    for elem in elements:
        elem = deref(elem)
        if not _post_real_constraint_node(elem, trail):
            return False
    return True


def _post_real_constraint_node(node: Any, trail: Trail) -> bool:
    """Post a single AST constraint node to CLP(R)."""
    _ensure_term_imports()

    if isinstance(node, _CompareChain):
        for cmp in node.comparisons:
            if not _post_real_constraint_node(cmp, trail):
                return False
        return True

    if isinstance(node, _ArithEq):
        return real_eq(node.left, node.right, trail)
    if isinstance(node, _ArithNeq):
        return real_ne(node.left, node.right, trail)
    if isinstance(node, _LtE):
        return real_le(node.left, node.right, trail)
    if isinstance(node, _Lt):
        return real_lt(node.left, node.right, trail)
    if isinstance(node, _GtE):
        return real_ge(node.left, node.right, trail)
    if isinstance(node, _Gt):
        return real_gt(node.left, node.right, trail)

    raise TypeError(
        f"clpr constraint block: unsupported node {type(node).__name__}: {node}"
    )
