"""clausal.logic.clpfd — CLP(Z) integer constraint solver.

Provides CLP(Z) constraint logic programming over all integers as a
first-class language feature.  Variables default to the entire integer
line (-inf, +inf) until constrained.  Comparison operators (``==``,
``!=``, ``<``, ``>``, ``<=``, ``>=``) become CLP(Z) constraint
operators.  Domains are stored as AttVar attributes under the ``"fd"``
key.

Domain representation
---------------------
A ``Domain`` is a sorted tuple of ``(lo, hi)`` inclusive integer intervals::

    Domain = tuple[tuple[int, int], ...]

Single-interval fast path: most domains are contiguous ``((lo, hi),)``
which is optimized throughout.

Trail safety
------------
Every domain narrowing or constraint addition creates a **new** ``FDVar``
and calls ``put_attr(var, FD_KEY, new_state, trail)``.  The old ``FDVar``
is restored on backtrack.  Never mutate in place.
"""

from __future__ import annotations

import math
import numbers
import sys
from collections import deque
from decimal import Decimal
from fractions import Fraction
from typing import Any

from clausal.logic.atoms import is_atom, mint, spelling
from dataclasses import replace as _replace   # a rebuilt node keeps its position
from clausal.logic.exact_arith import EVALUABLE as _EVALUABLE, NODE_EVALUABLE as _NODE_EVALUABLE
from clausal.logic.exact_arith import cell_key_args as _cell_key_args, node_keys as _node_keys
from clausal.logic.exact_arith import key_nodes as _key_nodes, not_evaluable as _not_evaluable
from clausal.logic.variables import (
    present_number,
    exact_cell_number,
    Var,
    Trail,
    deref,
    is_var,
    unify,
    put_attr,
    get_attr,
    register_attr_hook,
)

# ── Constants ────────────────────────────────────────────────────────────────

FD_KEY = "fd"
_NEG_INF = float('-inf')
_POS_INF = float('inf')
DEFAULT_MIN = _NEG_INF
DEFAULT_MAX = _POS_INF

# Type alias for domains: sorted tuple of (lo, hi) inclusive intervals
Domain = tuple[tuple[int, int], ...]


# ── C-accelerated domain operations (with Python fallback) ──────────────────
# The Python definitions below serve as the reference implementation.
# If the C extension is available, its versions silently replace them.

_USE_C_DOMAINS = False
try:
    from clausal.logic._clpfd_core import (
        domain_from_range as _c_domain_from_range,
        domain_contains as _c_domain_contains,
        domain_min as _c_domain_min,
        domain_max as _c_domain_max,
        domain_size as _c_domain_size,
        domain_singleton as _c_domain_singleton,
        domain_intersection as _c_domain_intersection,
        domain_remove as _c_domain_remove,
        domain_remove_above as _c_domain_remove_above,
        domain_remove_below as _c_domain_remove_below,
        domain_values as _c_domain_values,
    )
    _USE_C_DOMAINS = True
except ImportError:
    pass


# ── FDVar: per-variable finite-domain state ──────────────────────────────────


class FDVar:
    """Finite-domain state for one variable.

    Immutable for trail safety — narrowing creates a new instance.
    """
    __slots__ = ('domain', 'constraints')

    def __init__(self, domain: Domain, constraints: tuple = ()):
        self.domain = domain
        self.constraints = constraints  # tuple[Constraint, ...]


# ── Domain operations ────────────────────────────────────────────────────────


def domain_from_range(lo, hi) -> Domain:
    """Create a single-interval domain [lo, hi].

    Returns empty domain if lo > hi or either bound is NaN.
    """
    # NaN guard: NaN comparisons are always False, so lo > hi won't catch it
    if lo != lo or hi != hi:  # fast NaN check (NaN != NaN is True)
        return ()
    if lo > hi:
        return ()
    return ((lo, hi),)


def domain_contains(domain: Domain, value: int) -> bool:
    """Check if *value* is in the domain."""
    for lo, hi in domain:
        if lo <= value <= hi:
            return True
        if value < lo:
            return False
    return False


def domain_min(domain: Domain) -> int:
    """Minimum value in domain. Raises ValueError on empty."""
    if not domain:
        raise ValueError("empty domain")
    return domain[0][0]


def domain_max(domain: Domain) -> int:
    """Maximum value in domain. Raises ValueError on empty."""
    if not domain:
        raise ValueError("empty domain")
    return domain[-1][1]


def domain_size(domain: Domain) -> int | float:
    """Number of values in domain, or float('inf') if unbounded."""
    total = 0
    for lo, hi in domain:
        if lo == _NEG_INF or hi == _POS_INF:
            return _POS_INF
        total += hi - lo + 1
    return total


def domain_singleton(domain: Domain) -> int | None:
    """If domain is a single value, return it; otherwise None."""
    if len(domain) == 1:
        lo, hi = domain[0]
        if lo == hi:
            return lo
    return None


def domain_intersection(d1: Domain, d2: Domain) -> Domain:
    """intersection of two domains."""
    result: list[tuple[int, int]] = []
    i = j = 0
    while i < len(d1) and j < len(d2):
        lo = max(d1[i][0], d2[j][0])
        hi = min(d1[i][1], d2[j][1])
        if lo <= hi:
            result.append((lo, hi))
        if d1[i][1] < d2[j][1]:
            i += 1
        else:
            j += 1
    return tuple(result)


def _domain_from_set(values: set) -> Domain:
    """Build a minimal domain from a set of integer values."""
    if not values:
        return ()
    sorted_vals = sorted(values)
    intervals: list[tuple[int, int]] = []
    lo = hi = sorted_vals[0]
    for v in sorted_vals[1:]:
        if v == hi + 1:
            hi = v
        else:
            intervals.append((lo, hi))
            lo = hi = v
    intervals.append((lo, hi))
    return tuple(intervals)


def domain_remove(domain: Domain, value: int) -> Domain:
    """Remove a single value from domain."""
    result: list[tuple[int, int]] = []
    for lo, hi in domain:
        if value < lo or value > hi:
            result.append((lo, hi))
        else:
            if lo < value:
                result.append((lo, value - 1))
            if value < hi:
                result.append((value + 1, hi))
    return tuple(result)


def domain_remove_above(domain: Domain, limit: int) -> Domain:
    """Remove all values > limit from domain."""
    result: list[tuple[int, int]] = []
    for lo, hi in domain:
        if lo > limit:
            break
        result.append((lo, min(hi, limit)))
    return tuple(result)


def domain_remove_below(domain: Domain, limit: int) -> Domain:
    """Remove all values < limit from domain."""
    result: list[tuple[int, int]] = []
    for lo, hi in domain:
        if hi < limit:
            continue
        result.append((max(lo, limit), hi))
    return tuple(result)


def domain_values(domain: Domain):
    """Iterate over all values in a finite domain.

    Raises ValueError if domain is unbounded.
    """
    for lo, hi in domain:
        if lo == _NEG_INF or hi == _POS_INF:
            raise ValueError(
                "Cannot enumerate unbounded domain. "
                "Use in_domain/3 to declare bounds before labeling."
            )
        yield from range(lo, hi + 1)


# Preserve Python implementations under _py_* names so the C extensions
# can fall back to them when domain bounds exceed int64 (bignum case).
# These references must be captured BEFORE the C versions overwrite the
# public names below.
_py_domain_from_range = domain_from_range
_py_domain_contains = domain_contains
_py_domain_min = domain_min
_py_domain_max = domain_max
_py_domain_size = domain_size
_py_domain_singleton = domain_singleton
_py_domain_intersection = domain_intersection
_py_domain_remove = domain_remove
_py_domain_remove_above = domain_remove_above
_py_domain_remove_below = domain_remove_below
_py_domain_values = domain_values


# Replace Python domain ops with C versions when available
if _USE_C_DOMAINS:
    domain_from_range = _c_domain_from_range
    domain_contains = _c_domain_contains
    domain_min = _c_domain_min
    domain_max = _c_domain_max
    domain_size = _c_domain_size
    domain_singleton = _c_domain_singleton
    domain_intersection = _c_domain_intersection
    domain_remove = _c_domain_remove
    domain_remove_above = _c_domain_remove_above
    domain_remove_below = _c_domain_remove_below
    domain_values = _c_domain_values


# ── Ensure FD state ─────────────────────────────────────────────────────────


def _ensure_fd(var: Var, trail: Trail) -> FDVar:
    """Get or auto-create FDVar for a variable."""
    state = get_attr(var, FD_KEY)
    if state is not None:
        return state
    state = FDVar(domain_from_range(DEFAULT_MIN, DEFAULT_MAX))
    put_attr(var, FD_KEY, state, trail)
    return state


# ── Narrow + propagation queue ───────────────────────────────────────────────


_clpr_REAL_KEY = None
_clpr_RealVar = None
_clpr_loaded = False


def _safe_float_lo(x: int | float) -> float:
    """Convert a *lower*-bound FD value to float, rounded toward -inf so
    the result never exceeds the true value (clpr's soundness invariant:
    a real interval's ``lo`` must be <= every value it claims to admit —
    see ``clausal/logic/clpr.py`` lines 11-14, 52-55).

    A lower bound whose magnitude overflows *negative* (``x < -float_max``,
    e.g. a bignum growing without bound downward) saturates to ``-inf``:
    that is still <= the true value, so it stays sound.

    A lower bound overflowing *positive* (``x > float_max`` — e.g. a
    tabled-Fibonacci lower bound past fib(~1475)) must NOT saturate to
    ``+inf``: ``+inf`` is *greater* than the true (finite) bignum ``x``,
    which is unsound (excludes real values that must remain admissible),
    and combined with an unbounded upper bound of ``+inf`` produces a
    degenerate ``[inf, inf]`` interval that reads as a spurious wipeout
    downstream.  ``sys.float_info.max`` is the tightest float that is
    still <= any such ``x``, so it is the correct saturation target.
    """
    try:
        return float(x)
    except OverflowError:
        return sys.float_info.max if x > 0 else -math.inf


def _safe_float_hi(x: int | float) -> float:
    """Convert an *upper*-bound FD value to float, rounded toward +inf so
    the result never falls short of the true value (the mirror of
    ``_safe_float_lo`` — see clpr's soundness invariant, same references).

    An upper bound overflowing *positive* saturates to ``+inf`` (sound:
    ``+inf`` is never less than any finite value).  An upper bound
    overflowing *negative* (``x < -float_max``) must saturate to
    ``-sys.float_info.max``, not ``-inf`` — ``-inf`` would be *less* than
    the true (finite, very negative) bignum ``x``, unsoundly excluding
    admissible values between ``-sys.float_info.max`` and ``x``.
    """
    try:
        return float(x)
    except OverflowError:
        return math.inf if x > 0 else -sys.float_info.max


def _sync_real(var, fd_lo: int | float, fd_hi: int | float, trail):
    """Synchronise the CLP(R) real interval on *var* with FD bounds.

    *fd_lo*/*fd_hi* are the raw (possibly bignum) FD domain bounds —
    conversion to float happens in here, lazily, only once we know a
    real interval is actually attached to *var*, so plain FD-only
    narrowing (the overwhelming common case) never pays for it and
    never risks an ``OverflowError`` it has no use for.  Conversion is
    direction-aware (``_safe_float_lo``/``_safe_float_hi``) so an
    out-of-float-range bignum bound saturates soundly rather than
    silently producing a false interval — see those functions' docs.

    Returns False on wipeout, True otherwise.  Called from both the
    Python ``_narrow`` and the C ``c_narrow`` — the latter caches a
    reference to this function so it never has to know ``RealVar``'s
    constructor signature.
    """
    global _clpr_REAL_KEY, _clpr_RealVar, _clpr_loaded
    if not _clpr_loaded:
        _clpr_loaded = True
        try:
            from clausal.logic.clpr import REAL_KEY, RealVar
            _clpr_REAL_KEY = REAL_KEY
            _clpr_RealVar = RealVar
        except ImportError:
            pass
    if _clpr_REAL_KEY is None:
        return True
    real_state = get_attr(var, _clpr_REAL_KEY)
    if real_state is None:
        return True
    new_lo = max(real_state.lo, _safe_float_lo(fd_lo))
    new_hi = min(real_state.hi, _safe_float_hi(fd_hi))
    if new_lo > new_hi:
        return False
    if new_lo != real_state.lo or new_hi != real_state.hi:
        updated = _clpr_RealVar(new_lo, new_hi, real_state.constraints)
        put_attr(var, _clpr_REAL_KEY, updated, trail)
    return True


def _narrow(var: Var, new_domain: Domain, trail: Trail, queue: deque) -> bool:
    """Narrow var's domain to new_domain. Returns False on wipeout."""
    if not new_domain:
        return False  # wipeout

    old_state = get_attr(var, FD_KEY)
    old_constraints = old_state.constraints if old_state else ()

    new_state = FDVar(new_domain, old_constraints)
    put_attr(var, FD_KEY, new_state, trail)

    # Keep real interval in sync if present.  Pass the raw (possibly
    # bignum) bounds — _sync_real converts to float lazily, only if a
    # real interval is actually attached (see _safe_float_lo/_hi and
    # _sync_real).
    if not _sync_real(var, domain_min(new_domain),
                      domain_max(new_domain), trail):
        return False

    # Keep Q bounds in sync if present (mirrors REAL sync above)
    from clausal.logic.clpq import Q_KEY, QVar  # noqa: PLC0415
    q_state = get_attr(var, Q_KEY)
    if q_state is not None:
        fd_lo_q = Fraction(domain_min(new_domain))
        fd_hi_q = Fraction(domain_max(new_domain))
        new_q_lo = max(q_state.lo, fd_lo_q) if q_state.lo is not None else fd_lo_q
        new_q_hi = min(q_state.hi, fd_hi_q) if q_state.hi is not None else fd_hi_q
        if new_q_lo > new_q_hi:
            return False
        if new_q_lo != q_state.lo or new_q_hi != q_state.hi:
            updated_q = QVar(new_q_lo, new_q_hi, q_state.tab_id)
            put_attr(var, Q_KEY, updated_q, trail)

    # Singleton → bind variable
    val = domain_singleton(new_domain)
    if val is not None:
        if not unify(var, val, trail):
            return False

    # Schedule for propagation
    queue.append(var)
    return True


def _narrow_if_changed(var: Var, new_domain: Domain, trail: Trail, queue: deque) -> bool:
    """Narrow only if domain actually changed. Returns False on wipeout."""
    old_state = get_attr(var, FD_KEY)
    if old_state is not None and old_state.domain == new_domain:
        return True  # no change
    return _narrow(var, new_domain, trail, queue)


# ── Constraint base class ───────────────────────────────────────────────────


class Constraint:
    """Base class for FD constraints."""
    __slots__ = ('vars',)

    def __init__(self, vars_: tuple):
        self.vars = vars_

    def propagate(self, trail: Trail, queue: deque) -> bool:
        """Narrow domains. Return False on wipeout."""
        raise NotImplementedError


# ── Bignum fallback helpers for the C propagator ─────────────────────────────
#
# When _clpfd_propagate.c detects that a constraint's operand domains contain
# bignum bounds (out of int64 range), it tail-calls into one of these helpers
# instead of running its int64 fast path.  The logic mirrors the corresponding
# class.propagate() methods below; the public domain_* names here resolve to
# the C-accelerated wrappers, which themselves fall back to _py_domain_* when
# bignum bounds are present (see Slice 1+2).


def _eq_propagate_bignum(lhs, rhs, trail, queue) -> bool:
    """Equivalent of EqConstraint.propagate with bignum-safe operations."""
    lhs = deref(lhs)
    rhs = deref(rhs)
    ld = _expr_domain(lhs, trail)
    rd = _expr_domain(rhs, trail)
    inter = domain_intersection(ld, rd)
    if not inter:
        return False
    if is_var(lhs):
        if not _narrow_if_changed(lhs, inter, trail, queue):
            return False
    if is_var(rhs):
        if not _narrow_if_changed(rhs, inter, trail, queue):
            return False
    return True


def _lt_propagate_bignum(lhs, rhs, trail, queue) -> bool:
    """Equivalent of LtConstraint.propagate with bignum-safe operations."""
    lhs = deref(lhs)
    rhs = deref(rhs)
    ld = _expr_domain(lhs, trail)
    rd = _expr_domain(rhs, trail)
    if not ld or not rd:
        return False
    rd_max = domain_max(rd)
    ld_min = domain_min(ld)
    new_l_hi = rd_max if rd_max == _POS_INF else rd_max - 1
    new_r_lo = ld_min if ld_min == _NEG_INF else ld_min + 1
    new_ld = domain_remove_above(ld, new_l_hi)
    new_rd = domain_remove_below(rd, new_r_lo)
    if not new_ld or not new_rd:
        return False
    if is_var(lhs):
        if not _narrow_if_changed(lhs, new_ld, trail, queue):
            return False
    elif domain_min(ld) >= rd_max:
        return False
    if is_var(rhs):
        if not _narrow_if_changed(rhs, new_rd, trail, queue):
            return False
    return True


def _le_propagate_bignum(lhs, rhs, trail, queue) -> bool:
    """Equivalent of LeConstraint.propagate with bignum-safe operations."""
    lhs = deref(lhs)
    rhs = deref(rhs)
    ld = _expr_domain(lhs, trail)
    rd = _expr_domain(rhs, trail)
    if not ld or not rd:
        return False
    rd_max = domain_max(rd)
    ld_min = domain_min(ld)
    new_ld = domain_remove_above(ld, rd_max)
    new_rd = domain_remove_below(rd, ld_min)
    if not new_ld or not new_rd:
        return False
    if is_var(lhs):
        if not _narrow_if_changed(lhs, new_ld, trail, queue):
            return False
    elif ld_min > rd_max:
        return False
    if is_var(rhs):
        if not _narrow_if_changed(rhs, new_rd, trail, queue):
            return False
    return True


def _ne_propagate_bignum(lhs, rhs, trail, queue) -> bool:
    """Equivalent of NeConstraint.propagate with bignum-safe operations."""
    lhs = deref(lhs)
    rhs = deref(rhs)
    # Aliased operands: X != X can never hold — fail (A06-F010).
    if lhs is rhs:
        return False
    if not is_var(lhs) and not is_var(rhs):
        # Evaluate expression operands before comparing (A06-F001).
        _ensure_exc_imports()
        lv = lhs if type(lhs) is int else _eval_propagating(lhs)
        rv = rhs if type(rhs) is int else _eval_propagating(rhs)
        if lv is _NO_VALUE or rv is _NO_VALUE:
            return False           # a zero divisor: no value to differ
        if lv is None or rv is None:
            return True
        return lv != rv
    if not is_var(lhs) and isinstance(lhs, int) and is_var(rhs):
        state = get_attr(rhs, FD_KEY)
        if state is not None:
            new_d = domain_remove(state.domain, lhs)
            return _narrow_if_changed(rhs, new_d, trail, queue)
    if not is_var(rhs) and isinstance(rhs, int) and is_var(lhs):
        state = get_attr(lhs, FD_KEY)
        if state is not None:
            new_d = domain_remove(state.domain, rhs)
            return _narrow_if_changed(lhs, new_d, trail, queue)
    if is_var(lhs) and is_var(rhs):
        ls = get_attr(lhs, FD_KEY)
        rs = get_attr(rhs, FD_KEY)
        if ls and rs:
            lv = domain_singleton(ls.domain)
            rv = domain_singleton(rs.domain)
            if lv is not None and rv is not None:
                return lv != rv
            if lv is not None:
                new_d = domain_remove(rs.domain, lv)
                return _narrow_if_changed(rhs, new_d, trail, queue)
            if rv is not None:
                new_d = domain_remove(ls.domain, rv)
                return _narrow_if_changed(lhs, new_d, trail, queue)
    return True


def _sum_propagate_bignum(sum_vars, total, trail, queue) -> bool:
    """Equivalent of SumConstraint.propagate with bignum-safe operations.

    Slice 4 of clpz_bignum.md.  The C ``sum_propagate`` accumulates
    bounds in ``double``, which loses integer precision past 2**53 — so
    bignum bounds AND large-but-int64 sums both need this path.
    """
    vars_ = [deref(v) for v in sum_vars]
    total = deref(total)

    # Finite-only sums + ±inf counts so an output-mode var whose OWN domain is
    # the sole infinite contributor still narrows (A06-F002).
    min_sum = max_sum = 0
    finite_hi_sum = finite_lo_sum = 0
    pos_inf_count = neg_inf_count = 0
    for v in vars_:
        d = _expr_domain(v, trail)
        if not d:
            return False
        v_lo = domain_min(d)
        v_hi = domain_max(d)
        min_sum += v_lo
        max_sum += v_hi
        if v_hi == _POS_INF:
            pos_inf_count += 1
        else:
            finite_hi_sum += v_hi
        if v_lo == _NEG_INF:
            neg_inf_count += 1
        else:
            finite_lo_sum += v_lo

    total_d = _expr_domain(total, trail)
    new_total_d = domain_intersection(total_d, domain_from_range(min_sum, max_sum))
    if not new_total_d:
        return False
    if is_var(total) and not _narrow_if_changed(total, new_total_d, trail, queue):
        return False
    total_lo = domain_min(new_total_d)
    total_hi = domain_max(new_total_d)

    for v in vars_:
        if not is_var(v):
            continue
        d = _expr_domain(v, trail)
        v_max = domain_max(d)
        v_min = domain_min(d)
        others_pos_inf = pos_inf_count - (1 if v_max == _POS_INF else 0)
        other_max = _POS_INF if others_pos_inf > 0 else \
            finite_hi_sum - (0 if v_max == _POS_INF else v_max)
        others_neg_inf = neg_inf_count - (1 if v_min == _NEG_INF else 0)
        other_min = _NEG_INF if others_neg_inf > 0 else \
            finite_lo_sum - (0 if v_min == _NEG_INF else v_min)
        new_lo = _NEG_INF if other_max == _POS_INF else total_lo - other_max
        new_hi = _POS_INF if other_min == _NEG_INF else total_hi - other_min
        new_d = domain_intersection(d, domain_from_range(new_lo, new_hi))
        if not new_d:
            return False
        if not _narrow_if_changed(v, new_d, trail, queue):
            return False

    return True


def _scalar_propagate_bignum(coeffs, sum_vars, total, trail, queue) -> bool:
    """Equivalent of ScalarProductConstraint.propagate with bignum-safe ops.

    Slice 4 of clpz_bignum.md.  Mirrors ``ScalarProductConstraint.
    propagate`` but uses ``math.ceil``/``math.floor`` only on finite
    operands; for infinite bounds, the new var bounds are kept as
    ``±inf`` directly to avoid OverflowError on ``int(inf)``.
    """
    vars_ = [deref(v) for v in sum_vars]
    total = deref(total)

    # Finite-only contribution sums + ±inf counts (A06-F002).
    min_sum = max_sum = 0
    finite_cmax_sum = finite_cmin_sum = 0
    cmax_pos_inf = cmin_neg_inf = 0
    for c, v in zip(coeffs, vars_):
        d = _expr_domain(v, trail)
        if not d:
            return False
        v_lo, v_hi = domain_min(d), domain_max(d)
        contrib_min = _safe_mult(c, v_lo) if c >= 0 else _safe_mult(c, v_hi)
        contrib_max = _safe_mult(c, v_hi) if c >= 0 else _safe_mult(c, v_lo)
        min_sum += contrib_min
        max_sum += contrib_max
        if contrib_max == _POS_INF:
            cmax_pos_inf += 1
        else:
            finite_cmax_sum += contrib_max
        if contrib_min == _NEG_INF:
            cmin_neg_inf += 1
        else:
            finite_cmin_sum += contrib_min

    total_d = _expr_domain(total, trail)
    new_total_d = domain_intersection(total_d, domain_from_range(min_sum, max_sum))
    if not new_total_d:
        return False
    if is_var(total) and not _narrow_if_changed(total, new_total_d, trail, queue):
        return False
    total_lo = domain_min(new_total_d)
    total_hi = domain_max(new_total_d)

    for c, v in zip(coeffs, vars_):
        if not is_var(v) or c == 0:
            continue
        d = _expr_domain(v, trail)
        v_lo, v_hi = domain_min(d), domain_max(d)
        contrib_max = _safe_mult(c, v_hi) if c > 0 else _safe_mult(c, v_lo)
        contrib_min = _safe_mult(c, v_lo) if c > 0 else _safe_mult(c, v_hi)
        others_cmax_inf = cmax_pos_inf - (1 if contrib_max == _POS_INF else 0)
        other_max = _POS_INF if others_cmax_inf > 0 else \
            finite_cmax_sum - (0 if contrib_max == _POS_INF else contrib_max)
        others_cmin_inf = cmin_neg_inf - (1 if contrib_min == _NEG_INF else 0)
        other_min = _NEG_INF if others_cmin_inf > 0 else \
            finite_cmin_sum - (0 if contrib_min == _NEG_INF else contrib_min)
        num_lo = _NEG_INF if other_max == _POS_INF else total_lo - other_max
        num_hi = _POS_INF if other_min == _NEG_INF else total_hi - other_min
        # Exact integer ceil/floor division — this is the designated
        # bignum-safe path, so float true division (which loses precision past
        # 2^53) would over-prune valid large-int solutions (A06-F004).
        # ceil(a/c) == -((-a) // c); floor(a/c) == a // c  (Python // floors).
        if c > 0:
            new_v_lo = _NEG_INF if num_lo == _NEG_INF else -((-num_lo) // c)
            new_v_hi = _POS_INF if num_hi == _POS_INF else num_hi // c
        else:
            new_v_lo = _NEG_INF if num_hi == _POS_INF else -((-num_hi) // c)
            new_v_hi = _POS_INF if num_lo == _NEG_INF else num_lo // c
        new_d = domain_intersection(d, domain_from_range(new_v_lo, new_v_hi))
        if not new_d:
            return False
        if not _narrow_if_changed(v, new_d, trail, queue):
            return False

    return True


# ── Concrete constraint types ────────────────────────────────────────────────


class EqConstraint(Constraint):
    """X == Y (or X == expr)."""
    __slots__ = ('lhs', 'rhs')

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs
        super().__init__(_collect_constraint_vars(lhs, rhs))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        ld = _expr_domain(lhs, trail)
        rd = _expr_domain(rhs, trail)
        inter = domain_intersection(ld, rd)
        if not inter:
            return False
        if is_var(lhs):
            if not _narrow_if_changed(lhs, inter, trail, queue):
                return False
        if is_var(rhs):
            if not _narrow_if_changed(rhs, inter, trail, queue):
                return False
        return True


class NeConstraint(Constraint):
    """X != Y."""
    __slots__ = ('lhs', 'rhs')

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs
        super().__init__(_collect_constraint_vars(lhs, rhs))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        # Aliased operands (e.g. unify merged the two vars after posting):
        # X != X can never hold — fail (A06-F010).
        if lhs is rhs:
            return False
        # Only propagate when one side is ground
        if not is_var(lhs) and not is_var(rhs):
            # Evaluate expression operands (e.g. Add(X, 1)): comparing the
            # expression node structurally to an int is always "different" and
            # would wrongly satisfy the constraint (A06-F001).
            _ensure_exc_imports()
            lv = lhs if type(lhs) is int else _eval_propagating(lhs)
            rv = rhs if type(rhs) is int else _eval_propagating(rhs)
            if lv is _NO_VALUE or rv is _NO_VALUE:
                return False     # a zero divisor: no value to differ
            if lv is None or rv is None:
                return True  # an expression still has unbound vars — pending
            return lv != rv
        if not is_var(lhs) and isinstance(lhs, int) and is_var(rhs):
            state = get_attr(rhs, FD_KEY)
            if state is not None:
                new_d = domain_remove(state.domain, lhs)
                return _narrow_if_changed(rhs, new_d, trail, queue)
        if not is_var(rhs) and isinstance(rhs, int) and is_var(lhs):
            state = get_attr(lhs, FD_KEY)
            if state is not None:
                new_d = domain_remove(state.domain, rhs)
                return _narrow_if_changed(lhs, new_d, trail, queue)
        # Both vars — check for singleton
        if is_var(lhs) and is_var(rhs):
            ls = get_attr(lhs, FD_KEY)
            rs = get_attr(rhs, FD_KEY)
            if ls and rs:
                lv = domain_singleton(ls.domain)
                rv = domain_singleton(rs.domain)
                if lv is not None and rv is not None:
                    return lv != rv
                if lv is not None:
                    new_d = domain_remove(rs.domain, lv)
                    return _narrow_if_changed(rhs, new_d, trail, queue)
                if rv is not None:
                    new_d = domain_remove(ls.domain, rv)
                    return _narrow_if_changed(lhs, new_d, trail, queue)
        return True


class LtConstraint(Constraint):
    """X < Y."""
    __slots__ = ('lhs', 'rhs')

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs
        super().__init__(_collect_constraint_vars(lhs, rhs))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        ld = _expr_domain(lhs, trail)
        rd = _expr_domain(rhs, trail)
        if not ld or not rd:
            return False
        # X < Y → X's max < max(Y), Y's min > min(X)
        new_ld = domain_remove_above(ld, domain_max(rd) - 1)
        new_rd = domain_remove_below(rd, domain_min(ld) + 1)
        if not new_ld or not new_rd:
            return False
        if is_var(lhs):
            if not _narrow_if_changed(lhs, new_ld, trail, queue):
                return False
        elif domain_min(ld) >= domain_max(rd):
            return False
        if is_var(rhs):
            if not _narrow_if_changed(rhs, new_rd, trail, queue):
                return False
        return True


class LeConstraint(Constraint):
    """X <= Y."""
    __slots__ = ('lhs', 'rhs')

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs
        super().__init__(_collect_constraint_vars(lhs, rhs))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        ld = _expr_domain(lhs, trail)
        rd = _expr_domain(rhs, trail)
        if not ld or not rd:
            return False
        new_ld = domain_remove_above(ld, domain_max(rd))
        new_rd = domain_remove_below(rd, domain_min(ld))
        if not new_ld or not new_rd:
            return False
        if is_var(lhs):
            if not _narrow_if_changed(lhs, new_ld, trail, queue):
                return False
        elif domain_min(ld) > domain_max(rd):
            return False
        if is_var(rhs):
            if not _narrow_if_changed(rhs, new_rd, trail, queue):
                return False
        return True


class AllDiffConstraint(Constraint):
    """all_different(Vars) — when one var is ground, remove its value from all others."""
    __slots__ = ('all_vars',)

    def __init__(self, vars_: tuple):
        self.all_vars = vars_
        super().__init__(vars_)

    def propagate(self, trail: Trail, queue: deque) -> bool:
        ground_vals: set[int] = set()
        free_vars: list = []
        for v in self.all_vars:
            v = deref(v)
            if is_var(v):
                free_vars.append(v)
            elif isinstance(v, int):
                if v in ground_vals:
                    return False  # duplicate ground value
                ground_vals.add(v)
            else:
                return False  # non-integer
        for v in free_vars:
            state = get_attr(v, FD_KEY)
            if state is None:
                continue
            new_d = state.domain
            for gv in ground_vals:
                new_d = domain_remove(new_d, gv)
            if not _narrow_if_changed(v, new_d, trail, queue):
                return False
        return True


class SumConstraint(Constraint):
    """Σ vars == total. Bounds-consistency propagation."""
    __slots__ = ('sum_vars', 'total')

    def __init__(self, sum_vars: tuple, total):
        self.sum_vars = sum_vars
        self.total = total
        result: list = []
        for v in sum_vars:
            _collect_vars_from(v, result)
        _collect_vars_from(total, result)
        super().__init__(tuple(result))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        vars_ = [deref(v) for v in self.sum_vars]
        total = deref(self.total)

        # Track finite-only sums plus ±inf counts so a var's "other side"
        # (total minus every OTHER var) is finite whenever its OWN domain is
        # the sole infinite contributor — the old `max_sum - own_max` gave
        # inf - inf = nan and skipped narrowing, leaving output-mode vars
        # unbounded (A06-F002).
        min_sum = max_sum = 0
        finite_hi_sum = finite_lo_sum = 0
        pos_inf_count = neg_inf_count = 0
        for v in vars_:
            d = _expr_domain(v, trail)
            if not d:
                return False
            v_lo = domain_min(d)
            v_hi = domain_max(d)
            min_sum += v_lo
            max_sum += v_hi
            if v_hi == _POS_INF:
                pos_inf_count += 1
            else:
                finite_hi_sum += v_hi
            if v_lo == _NEG_INF:
                neg_inf_count += 1
            else:
                finite_lo_sum += v_lo

        total_d = _expr_domain(total, trail)
        new_total_d = domain_intersection(total_d, domain_from_range(min_sum, max_sum))
        if not new_total_d:
            return False
        if is_var(total) and not _narrow_if_changed(total, new_total_d, trail, queue):
            return False
        total_lo = domain_min(new_total_d)
        total_hi = domain_max(new_total_d)

        for v in vars_:
            if not is_var(v):
                continue
            d = _expr_domain(v, trail)
            v_max = domain_max(d)
            v_min = domain_min(d)
            others_pos_inf = pos_inf_count - (1 if v_max == _POS_INF else 0)
            other_max = _POS_INF if others_pos_inf > 0 else \
                finite_hi_sum - (0 if v_max == _POS_INF else v_max)
            others_neg_inf = neg_inf_count - (1 if v_min == _NEG_INF else 0)
            other_min = _NEG_INF if others_neg_inf > 0 else \
                finite_lo_sum - (0 if v_min == _NEG_INF else v_min)
            new_lo = _NEG_INF if other_max == _POS_INF else total_lo - other_max
            new_hi = _POS_INF if other_min == _NEG_INF else total_hi - other_min
            new_d = domain_intersection(d, domain_from_range(new_lo, new_hi))
            if not new_d:
                return False
            if not _narrow_if_changed(v, new_d, trail, queue):
                return False

        return True


class ScalarProductConstraint(Constraint):
    """Σ coeffs[i] * vars[i] == total. Bounds-consistency propagation."""
    __slots__ = ('coeffs', 'sum_vars', 'total')

    def __init__(self, coeffs: tuple, sum_vars: tuple, total):
        self.coeffs = coeffs
        self.sum_vars = sum_vars
        self.total = total
        result: list = []
        for v in sum_vars:
            _collect_vars_from(v, result)
        _collect_vars_from(total, result)
        super().__init__(tuple(result))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        vars_ = [deref(v) for v in self.sum_vars]
        total = deref(self.total)

        # Finite-only contribution sums + ±inf counts, so a var's other-side
        # bound is finite when its OWN contribution is the sole infinite one
        # (A06-F002 — see SumConstraint.propagate).
        min_sum = max_sum = 0
        finite_cmax_sum = finite_cmin_sum = 0
        cmax_pos_inf = cmin_neg_inf = 0
        for c, v in zip(self.coeffs, vars_):
            d = _expr_domain(v, trail)
            if not d:
                return False
            v_lo, v_hi = domain_min(d), domain_max(d)
            contrib_min = _safe_mult(c, v_lo) if c >= 0 else _safe_mult(c, v_hi)
            contrib_max = _safe_mult(c, v_hi) if c >= 0 else _safe_mult(c, v_lo)
            min_sum += contrib_min
            max_sum += contrib_max
            if contrib_max == _POS_INF:
                cmax_pos_inf += 1
            else:
                finite_cmax_sum += contrib_max
            if contrib_min == _NEG_INF:
                cmin_neg_inf += 1
            else:
                finite_cmin_sum += contrib_min

        total_d = _expr_domain(total, trail)
        new_total_d = domain_intersection(total_d, domain_from_range(min_sum, max_sum))
        if not new_total_d:
            return False
        if is_var(total) and not _narrow_if_changed(total, new_total_d, trail, queue):
            return False
        total_lo = domain_min(new_total_d)
        total_hi = domain_max(new_total_d)

        for c, v in zip(self.coeffs, vars_):
            if not is_var(v) or c == 0:
                continue
            d = _expr_domain(v, trail)
            v_lo, v_hi = domain_min(d), domain_max(d)
            contrib_max = _safe_mult(c, v_hi) if c > 0 else _safe_mult(c, v_lo)
            contrib_min = _safe_mult(c, v_lo) if c > 0 else _safe_mult(c, v_hi)
            others_cmax_inf = cmax_pos_inf - (1 if contrib_max == _POS_INF else 0)
            other_max = _POS_INF if others_cmax_inf > 0 else \
                finite_cmax_sum - (0 if contrib_max == _POS_INF else contrib_max)
            others_cmin_inf = cmin_neg_inf - (1 if contrib_min == _NEG_INF else 0)
            other_min = _NEG_INF if others_cmin_inf > 0 else \
                finite_cmin_sum - (0 if contrib_min == _NEG_INF else contrib_min)
            # Bounds on c*var_i, guarding inf - inf; math.ceil/floor of ±inf
            # raises OverflowError, so short-circuit the infinite ends.
            num_lo = _NEG_INF if other_max == _POS_INF else total_lo - other_max
            num_hi = _POS_INF if other_min == _NEG_INF else total_hi - other_min
            # Exact integer ceil/floor division — float true division loses
            # precision past 2^53 and over-prunes large-int solutions
            # (A06-F004).  ceil(a/c) == -((-a) // c); floor(a/c) == a // c.
            if c > 0:
                new_v_lo = _NEG_INF if num_lo == _NEG_INF else -((-num_lo) // c)
                new_v_hi = _POS_INF if num_hi == _POS_INF else num_hi // c
            else:
                new_v_lo = _NEG_INF if num_hi == _POS_INF else -((-num_hi) // c)
                new_v_hi = _POS_INF if num_lo == _NEG_INF else num_lo // c
            new_d = domain_intersection(d, domain_from_range(new_v_lo, new_v_hi))
            if not new_d:
                return False
            if not _narrow_if_changed(v, new_d, trail, queue):
                return False

        return True


# ── Domain union helper ───────────────────────────────────────────────────────


def _domain_union(domains: list) -> Domain:
    """union of multiple domains. Returns sorted merged intervals."""
    if not domains:
        return ()
    intervals = sorted(lo_hi for d in domains for lo_hi in d)
    if not intervals:
        return ()
    result: list[tuple[int, int]] = [intervals[0]]
    for lo, hi in intervals[1:]:
        prev_lo, prev_hi = result[-1]
        if lo <= prev_hi + 1:
            result[-1] = (prev_lo, max(prev_hi, hi))
        else:
            result.append((lo, hi))
    return tuple(result)


def _indices_to_domain(indices: list) -> Domain:
    """Convert a sorted list of integers to interval representation."""
    if not indices:
        return ()
    result = []
    start = prev = indices[0]
    for v in indices[1:]:
        if v == prev + 1:
            prev = v
        else:
            result.append((start, prev))
            start = prev = v
    result.append((start, prev))
    return tuple(result)


class ElementConstraint(Constraint):
    """element(Index, List, Value): Value = List[Index-1], 1-based."""
    __slots__ = ('index', 'lst', 'value')

    def __init__(self, index, lst: tuple, value):
        self.index = index
        self.lst = lst
        self.value = value
        result: list = []
        _collect_vars_from(index, result)
        for item in lst:
            _collect_vars_from(item, result)
        _collect_vars_from(value, result)
        super().__init__(tuple(result))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        index = deref(self.index)
        value = deref(self.value)
        n = len(self.lst)

        if is_var(index):
            idx_state = get_attr(index, FD_KEY)
            if idx_state is None:
                if not _narrow(index, domain_from_range(1, n), trail, queue):
                    return False
                idx_state = get_attr(index, FD_KEY)
            idx_domain = idx_state.domain if idx_state else domain_from_range(1, n)
        elif isinstance(index, int):
            if index < 1 or index > n:
                return False
            idx_domain = ((index, index),)
        else:
            return False

        # Defensive: clamp to valid positions so a hand-posted wide domain
        # (or the default unbounded one) can never reach domain_values as an
        # infinite range (A06-F005).
        idx_domain = domain_intersection(idx_domain, domain_from_range(1, n))
        if not idx_domain:
            return False

        val_domain = _expr_domain(value, trail)

        # Step 1: narrow index — keep only positions where List[i] intersects value domain
        valid_indices = []
        for i in domain_values(idx_domain):
            item = deref(self.lst[i - 1])
            item_d = _expr_domain(item, trail)
            if domain_intersection(item_d, val_domain):
                valid_indices.append(i)

        if not valid_indices:
            return False

        new_idx_d = _indices_to_domain(valid_indices)
        if is_var(index) and not _narrow_if_changed(index, new_idx_d, trail, queue):
            return False

        # Step 2: narrow value — union of domains at valid index positions
        item_domains = [_expr_domain(deref(self.lst[i - 1]), trail) for i in valid_indices]
        new_val_d = domain_intersection(val_domain, _domain_union(item_domains))
        if not new_val_d:
            return False
        if is_var(value) and not _narrow_if_changed(value, new_val_d, trail, queue):
            return False

        # Step 3: if index singleton, unify value with List[k-1]
        idx_singleton = domain_singleton(new_idx_d)
        if idx_singleton is not None:
            item = deref(self.lst[idx_singleton - 1])
            if is_var(deref(self.value)):
                return unify(deref(self.value), item, trail)
            item_d = _expr_domain(item, trail)
            return bool(item_d and domain_intersection(item_d, new_val_d))

        return True


class CircuitConstraint(Constraint):
    """circuit(Vars): Vars[i] = j means node i+1's successor is j (1-based)."""
    __slots__ = ('circuit_vars', 'n', 'alldiff')

    def __init__(self, vars_: tuple):
        self.circuit_vars = vars_
        self.n = len(vars_)
        self.alldiff = AllDiffConstraint(vars_)
        super().__init__(vars_)

    def propagate(self, trail: Trail, queue: deque) -> bool:
        n = self.n
        vars_ = [deref(v) for v in self.circuit_vars]

        # Step 1: restrict all domains to [1, n], exclude self-loops
        for i, v in enumerate(vars_):
            if is_var(v):
                state = get_attr(v, FD_KEY)
                if state is None:
                    d = domain_remove(domain_from_range(1, n), i + 1)
                    if not _narrow(v, d, trail, queue):
                        return False
                else:
                    d = domain_intersection(state.domain, domain_from_range(1, n))
                    d = domain_remove(d, i + 1)
                    if not _narrow_if_changed(v, d, trail, queue):
                        return False
            elif isinstance(v, int):
                if v < 1 or v > n or v == i + 1:
                    return False

        # Step 2: all_different propagation
        if not self.alldiff.propagate(trail, queue):
            return False

        # Step 3: Sub-tour elimination
        vars_ = [deref(v) for v in self.circuit_vars]
        ground = {}
        for i, v in enumerate(vars_):
            if isinstance(v, int):
                ground[i + 1] = v

        for start in ground:
            chain = []
            current = start
            seen_chain: set[int] = set()
            while current in ground and current not in seen_chain:
                seen_chain.add(current)
                chain.append(current)
                current = ground[current]

            if len(chain) < n and current == start:
                return False  # premature cycle

            if len(chain) == n - 1 and current not in seen_chain:
                v = deref(self.circuit_vars[current - 1])
                if is_var(v):
                    new_d = domain_from_range(start, start)
                    if not _narrow_if_changed(v, new_d, trail, queue):
                        return False

        return True


# ── Expression domain computation ────────────────────────────────────────────

# Import term node types lazily to avoid circular imports
_Add = _Sub = _Mult = _Div = _FloorDiv = _Mod = _Pow = _Negate = None
#: ``{operator node class: evaluable-table key}`` (exact_arith.node_keys),
#: filled with the node imports below.
_NODE_KEYS: dict = {}
#: ``{node class: (table entry, binary?)}`` -- the same table, pre-resolved
#: for _eval_ground's hot path.  A zero divisor RAISES inside the entry
#: (``evaluation_error(zero_divisor)``, Q4 2026-09-28); it used to answer
#: None here, "not evaluable yet", so ``X == 1 // 0`` succeeded unbound.
_NODE_OPS: dict = {}
_Node = None


def _ensure_term_imports():
    global _Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow, _Negate, _Node
    if _Add is None:
        from clausal.terms import Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate
        from clausal.pythonic_ast.nodes import Node
        # the table views first: ``_Add`` is the "imports done" flag, so it
        # must not be set while they could still be empty
        _NODE_KEYS.update(_node_keys())
        _NODE_OPS.update({cls: (_NODE_EVALUABLE[k], k[1] == 2)
                          for cls, k in _NODE_KEYS.items()})
        # Ruling Q15 (2026-09-28): inside a CLP post ``/`` is RATIONAL
        # (``X == 7 / 2`` is 7 rdiv 2, like Scryer's ``{X = 7/2}``), on both
        # spellings -- evaluation (is/2, eval_) has Python's / Scryer's float
        from clausal.logic.exact_arith import exact_div as _exact_div_q  # noqa: PLC0415
        for cls, k in _NODE_KEYS.items():
            if k in (("$python_div", 2), ("/", 2), ("rdiv", 2)):
                _NODE_OPS[cls] = (_exact_div_q, True)
        _Add = Add
        _Sub = Sub
        _Mult = Mult
        _Div = Div
        _FloorDiv = FloorDiv
        _Mod = Mod
        _Pow = Pow
        _Negate = Negate
        _Node = Node


# Lazily cached exception machinery (same circular-import caution as above).
_LogicException = None
_type_error = None

# The units side channel (clausal.logic.units_clp), cached on first use.
_strip_for_solver = None
_strip_list_for_solver = None
_in_domain_units = None
_label_targets = None
_whole_units_only = None


def _ensure_units_imports() -> None:
    global _strip_for_solver, _strip_list_for_solver, _in_domain_units, _label_targets
    global _whole_units_only
    if _strip_for_solver is None:
        from clausal.logic import units_clp  # noqa: PLC0415
        _strip_for_solver = units_clp.strip_for_solver
        _strip_list_for_solver = units_clp.strip_list_for_solver
        _in_domain_units = units_clp.in_domain_units
        _label_targets = units_clp.label_targets
        _whole_units_only = units_clp.whole_units_only


def _units_flag_active() -> bool:
    from clausal.logic import _units_flag  # noqa: PLC0415
    return _units_flag.active


def _units_strip(l, r, context, trail):
    """Run the units side channel on a comparison: None when no Quantity or
    united Var is involved (the existing path is untouched), else the
    stripped ``(l, r)`` the solvers can take. Must run BEFORE ``_resolve``,
    which raises on a Quantity leaf, and before the non-numeric guards."""
    if _strip_for_solver is None:
        _ensure_units_imports()
    return _strip_for_solver(l, r, context, trail)


def _units_strip_list(items, context, trail):
    """List form of :func:`_units_strip` for the finite-domain builtins whose
    operands must share one dimension; returns the (possibly untouched)
    list. Every caller is a finite-domain builtin (chain/2, which feeds the
    comparators, calls the strip directly), so a quantity that is not a
    whole number of units throws here (units_unsupported) rather than being
    skipped, failed or miscounted by the builtin's own integer guard."""
    if _strip_list_for_solver is None:
        _ensure_units_imports()
    stripped, dims = _strip_list_for_solver(items, context, trail)
    if dims is not None:
        stripped = _whole_units_only(items, stripped, context)
    return stripped


def _ensure_exc_imports():
    global _LogicException, _type_error
    if _LogicException is None:
        from clausal.logic.exceptions import LogicException, type_error
        _LogicException = LogicException
        _type_error = type_error


def _unknown_expr_leaf_error(leaf) -> "Exception":
    """Catchable ``domain_error(clpz_expression, Leaf)`` for a LEAF
    inside an arithmetic expression tree that CLP(FD) cannot type as an
    integer (str, atom, date, Quantity, Decimal, None, compound, bare
    float/Fraction, …).  Both leaf fall-throughs — ``_expr_domain``'s
    catch-all and ``_eval_ground``'s final ``return None`` — previously
    treated such a leaf as an unconstrained integer / still-pending
    expression, so ``X + "a" == 5`` posted and produced silently wrong
    verdicts (the todo's confident-silence class).  Same house style as the
    operand-level guards (:func:`_reject_nonnumeric_eq`): the error term is
    ground and round-trips through unification, so ``catch/3`` handles it.
    The context is a fixed string because these walkers are shared by every
    comparator (their signatures are frozen — the C extension calls them)."""
    _ensure_exc_imports()
    # Scryer's formal (Q3, 2026-09-28; it was type_error(integer, Leaf)).  The
    # second argument is an unbound variable, as Scryer's library throws it.
    return _LogicException(_domain_error_clpz(leaf))


def _domain_error_clpz(term):
    from clausal.logic.exceptions import domain_error  # noqa: PLC0415
    return domain_error("clpz_expression", term, "clpfd expression")


def _no_value_in_propagation(exc) -> bool:
    """*exc* (a LogicException) is an evaluable entry saying "this has no
    value": any ``evaluation_error`` (a zero divisor, Q4 2026-09-28; an
    undefined ``'^'(0, -1)``) or the ``type_error(float, Base)`` of an
    integer ``'^'`` with a negative exponent.

    At the POST of a ground expression it propagates to the caller; inside
    PROPAGATION -- a divisor or exponent that took such a value while
    labelling -- the expression has no value, so the constraint FAILS and
    the search goes on, as Scryer's clpz prunes it (``X #= 10 // Y, Y in
    0..2, label([Y])`` gives Y = 1 and Y = 2; ``X #= 2^Y, Y in -1..2``
    labels Y = 0, 1, 2).  clpz's own ``domain_error(clpz_expression, _)`` for
    a non-arithmetic leaf is NOT one: it still raises."""
    from clausal.logic.exceptions import evaluation_error_kind  # noqa: PLC0415
    if evaluation_error_kind(exc) is not None:
        return True
    term = exc.term
    if type(term) is tuple and len(term) == 3 and type(term[1]) is tuple:
        formal = term[1]
        return len(formal) == 3 and formal[0] == "type_error" and formal[1] == "float"
    return False


def _eval_propagating(x):
    """``_eval_ground(x)`` inside propagation: an expression with no value
    (see :func:`_no_value_in_propagation`: any ``evaluation_error`` --
    ``zero_divisor``, ``undefined``, ``float_overflow`` -- or the
    ``type_error(float, _)`` of ``'^'`` with a negative exponent) is
    :data:`_NO_VALUE` (the constraint fails), not an error."""
    try:
        return _eval_ground(x)
    except _LogicException as exc:
        if _no_value_in_propagation(exc):
            return _NO_VALUE
        raise


#: What :func:`_eval_propagating` answers for an expression with no value.
_NO_VALUE = object()


def _expr_domain(expr, trail: Trail) -> Domain:
    """Compute the domain of an expression (Var, int, or arithmetic node).
    A ground expression with no value -- any ``evaluation_error``
    (``zero_divisor``, ``undefined``, ``float_overflow``) or the
    ``type_error(float, _)`` of ``'^'`` with a negative exponent -- has an
    EMPTY domain, so a propagator over it fails (see
    :func:`_no_value_in_propagation`).  clpz's ``domain_error(
    clpz_expression, _)`` for a non-arithmetic leaf still raises."""
    expr = deref(expr)
    if isinstance(expr, int):
        return ((expr, expr),)
    if is_var(expr):
        state = get_attr(expr, FD_KEY)
        if state is not None:
            return state.domain
        return domain_from_range(DEFAULT_MIN, DEFAULT_MAX)
    _ensure_term_imports()
    if isinstance(expr, _Add):
        ld = _expr_domain(expr.left, trail)
        rd = _expr_domain(expr.right, trail)
        return _domain_add(ld, rd)
    if isinstance(expr, _Sub):
        ld = _expr_domain(expr.left, trail)
        rd = _expr_domain(expr.right, trail)
        return _domain_sub(ld, rd)
    if isinstance(expr, _Mult):
        ld = _expr_domain(expr.left, trail)
        rd = _expr_domain(expr.right, trail)
        return _domain_mult(ld, rd)
    if isinstance(expr, _Negate):
        od = _expr_domain(expr.operand, trail)
        return _domain_negate(od)
    if _NODE_KEYS.get(type(expr)) == ("**", 2):
        # A quoted ``'**'`` cell (Scryer's FLOAT power, Q2 2026-09-28) posted
        # over CLP(FD): not a clpz expression -- Scryer's ``X #= Y**2``
        # raises exactly this.  Folded, its float would leave the FD
        # variable silently unconstrained.  Reached only after the CLP(Q) /
        # CLP(R) dispatch, which keeps it.  A ground one folds to its float
        # only as a WHOLE comparison side (``_resolve``); nested in a CLP(FD)
        # tree (``Y + '**'(2, 3)``) it is refused here too.
        _ensure_exc_imports()
        raise _LogicException(_domain_error_clpz(expr))
    if isinstance(expr, _Node):
        # Recognized expression NODE (Div/FloorDiv/Mod/Pow, …): if ground,
        # evaluate.  Only an integer result is a valid CLP(Z) domain bound —
        # a Fraction/float (e.g. from a Div subexpression that slipped past
        # CLP(Q) dispatch) must NOT become a domain bound, or the C domain
        # ops raise a TypeError that escapes through unify (A06-F006).
        _ensure_exc_imports()
        try:
            val = _eval_ground(expr)
            if isinstance(val, int) and not isinstance(val, bool):
                return ((val, val),)
        except _LogicException as exc:
            if _no_value_in_propagation(exc):
                return ()          # no value: the propagator fails
            raise  # a garbage leaf deeper in the node — keep it catchable
        except Exception:
            pass
        return domain_from_range(DEFAULT_MIN, DEFAULT_MAX)
    # An unrecognized LEAF: not an int, not a Var, not an expression node.
    # The old catch-all handed back the default domain here, silently
    # treating the leaf as an unconstrained integer (A06-F014 note) —
    # `X + "a" == 5` then posted and produced wrong verdicts.  Raise the
    # catchable typed error at the exact point where the "unconstrained
    # integer" assumption is made instead.
    raise _unknown_expr_leaf_error(expr)


def _domain_add(d1: Domain, d2: Domain) -> Domain:
    """Bounds-based addition: [a,b] + [c,d] = [a+c, b+d]."""
    if not d1 or not d2:
        return ()
    lo = domain_min(d1) + domain_min(d2)
    hi = domain_max(d1) + domain_max(d2)
    return ((lo, hi),)


def _domain_sub(d1: Domain, d2: Domain) -> Domain:
    """Bounds-based subtraction: [a,b] - [c,d] = [a-d, b-c]."""
    if not d1 or not d2:
        return ()
    lo = domain_min(d1) - domain_max(d2)
    hi = domain_max(d1) - domain_min(d2)
    return ((lo, hi),)


def _safe_mult(a, b):
    """Multiply handling 0 * inf → 0 (not NaN)."""
    if a == 0 or b == 0:
        return 0
    return a * b


def _domain_mult(d1: Domain, d2: Domain) -> Domain:
    """Bounds-based multiplication."""
    if not d1 or not d2:
        return ()
    corners = [
        _safe_mult(domain_min(d1), domain_min(d2)),
        _safe_mult(domain_min(d1), domain_max(d2)),
        _safe_mult(domain_max(d1), domain_min(d2)),
        _safe_mult(domain_max(d1), domain_max(d2)),
    ]
    return ((min(corners), max(corners)),)


def _domain_negate(d: Domain) -> Domain:
    """Negate a domain: -[a,b] = [-b, -a]."""
    if not d:
        return ()
    result = []
    for lo, hi in reversed(d):
        result.append((-hi, -lo))
    return tuple(result)


def _eval_ground(expr):
    """Evaluate an expression if all vars are bound to numbers.

    Returns int or float on success, None if expression contains unbound Vars.

    Raises the catchable :func:`_unknown_expr_leaf_error` on a LEAF that is
    not a number, a Var, or an expression node: returning ``None`` for it
    meant "still has unbound vars" to every caller — NeConstraint kept the
    constraint pending forever (``X + "a" != 5`` could never fail) and
    ``_resolve`` left the tree unevaluated, so garbage inside an expression
    tree produced silently wrong verdicts.
    """
    expr = deref(expr)
    # float is DELIBERATELY accepted here (roborev job 14): a fully-ground
    # tree with a float leaf folds numerically and dispatches to CLP(R)
    # (``2 + 0.5 == 2.5`` is True and must stay so) — that boundary predates
    # the leaf guard.  A float leaf beside an FD *Var* never reaches this
    # fold; it is rejected by _expr_domain's stricter fallback instead.
    if isinstance(expr, (int, float, Fraction)) and not isinstance(expr, bool):
        # An integral rational presents as int (see the tail below).
        if type(expr) is Fraction:
            return present_number(expr)
        return expr
    if type(expr) is Decimal:
        # Step 2 of the rdiv/decimal design (2026-09-17): a Decimal LEAF is a
        # number here -- exact, scale-carrying; NaN/Infinity have no finite
        # shape and fall to the leaf error like any non-number.
        if not expr.is_finite():
            raise _unknown_expr_leaf_error(expr)
        return present_number(expr)
    if is_var(expr):
        return None
    _ensure_term_imports()
    if not isinstance(expr, _Node):
        if isinstance(expr, bool):
            return None  # bools are deliberately not FD numbers; keep pending
        # An exact-number CELL (the transfer form of a Fraction or a Decimal,
        # RULED 2026-09-17) evaluates as the number it denotes: an ``rdiv``
        # cell is its Fraction and a ``decimal`` cell its Decimal, both
        # accepted above on re-entry.  A look-alike stays a compound.
        num = exact_cell_number(expr)
        if num is not None:
            return _eval_ground(num)
        # An arithmetic CELL -- ``('+', 1, 2)``, as ``=..``/``functor/3``
        # build at runtime -- evaluates through the SAME table as the node
        # arms below (ruling R9 A1, 2026-09-27).  A compound whose
        # ``name/arity`` is not in the table is the leaf error, as before.
        ka = _cell_key_args(expr)
        fn = _CLP_CELL_EVALUABLE.get(ka[0]) if ka is not None else None
        if fn is None:
            raise _unknown_expr_leaf_error(expr)
        result = _apply_evaluable(fn, ka[1])
    else:
        # An operator NODE: its table key (``node_keys``), then the one
        # table.  A node the table does not know (``UnaryPlus``, the bitwise
        # nodes, ...) stays "not evaluable yet" (None), as it always was.
        op = _NODE_OPS.get(type(expr))
        if op is None:
            return None
        # (inlined _apply_evaluable: this is the hot path of is/2 and of
        # every ground fold in the CLP posts)
        fn, binary = op
        if binary:
            l = _eval_ground(expr.left)
            r = _eval_ground(expr.right)
            if l is None or r is None:
                return None
            result = fn(l, r)
        else:
            o = _eval_ground(expr.operand)
            if o is None:
                return None
            result = fn(o)
    if result is None:
        return None
    # The single choke point for "no evaluated expression yields an integral
    # Fraction": ``int/int`` is exact (``3/2`` is ``Fraction(3, 2)``, never
    # 1.5), but ``4/2``, ``(1/2) + (1/2)`` and ``(4/2) * 3`` are the INTEGERS
    # 2, 1 and 6 and present as ``int``. ``Fraction(2, 1)`` is not the term
    # ``2``: ``'=='``/``compare/3`` tag every numeric type as its own kind in
    # the standard order while ``unify`` compares by ``==``, so an integral
    # Fraction made ``'is'(X, 4/2), '=='(X, 2)`` false and ``'='(X, 2)``
    # true at once. This tail is the single exit for EVERY operator node, so
    # a Fraction reached by any route — Div, a Fraction leaf, ``Fraction(1,
    # 2) ** -1`` under Pow, Mod/FloorDiv over Fraction operands — is
    # presented here. The rule itself is ``present_number`` (one spelling,
    # in clausal.logic.variables); the ``type(...) is Fraction`` guard is a
    # hot-path choice: one pointer compare per node for the int case.
    if type(result) is Fraction or type(result) is Decimal:
        return present_number(result)
    return result


def _apply_evaluable(fn, args):
    """Apply one evaluable-table entry to its evaluated *args*.

    None when an argument is still unbound.  A zero divisor raises inside
    the entry (``evaluation_error(zero_divisor)``); every argument is
    evaluated first, so a garbage leaf on either side raises whatever the
    other side holds."""
    if len(args) == 1:
        o = _eval_ground(args[0])
        if o is None:
            return None
        return fn(o)
    l = _eval_ground(args[0])
    r = _eval_ground(args[1])
    if l is None or r is None:
        return None
    return fn(l, r)


def _arith_cells_to_nodes(x, strict=None):
    """*x* with every arithmetic CELL rewritten as its operator node, or None
    when *x* holds none (the common case: nothing is allocated).

    The CLP posts -- ``==``/``!=``/``<``/``=<`` over CLP(FD), CLP(Q) and
    CLP(R), and ``between/3``'s bounds -- walk operator NODES (linearising,
    bounds, residual constraints over unbound variables), so an arithmetic
    cell such as ``+(X, 2)`` built by ``=..`` at runtime was invisible to
    them: silently unposted, or a raw TypeError.  Rewriting it at the post
    boundary through the SAME table as the evaluator (``exact_arith``'s
    ``EVALUABLE``, whose keys map back to node classes) gives the cell the
    node's semantics without teaching every walker a second spelling (ruling
    R9 A1, 2026-09-27).  Bound variables inside a rewritten subtree are
    replaced by their values; an untouched subtree is returned as is.

    A compound that is NOT evaluable is left alone, so each post keeps its
    own diagnosis -- unless *strict* is a context string: then an atom or a
    non-evaluable compound raises ``type_error(evaluable, Name/Arity)``
    (CLP(Q)/CLP(R), whose linearisers had no diagnosis of their own).
    """
    x = deref(x)
    t = type(x)
    if t is int or t is float:
        return None
    if _Add is None:
        _ensure_term_imports()
    key = _NODE_KEYS.get(t)
    if key is not None:
        # One frame per level, like _linearise: a number operand is answered
        # inline, anything else by the recursive call (a deep left-leaning
        # sum must not hit the recursion limit here first).
        if key[1] == 1:
            o = x.operand
            to = type(o)
            oc = None if to is int or to is float else _arith_cells_to_nodes(o, strict)
            return None if oc is None else _replace(x, operand=oc)
        a, b = x.left, x.right
        ta, tb = type(a), type(b)
        lc = None if ta is int or ta is float else _arith_cells_to_nodes(a, strict)
        rc = None if tb is int or tb is float else _arith_cells_to_nodes(b, strict)
        if lc is None and rc is None:
            return None
        return _replace(x, left=a if lc is None else lc, right=b if rc is None else rc)
    if is_var(x) or exact_cell_number(x) is not None:
        return None
    ka = _cell_key_args(x)
    if ka is not None and ka[0] in _EVALUABLE:
        args = []
        for a in ka[1]:
            c = _arith_cells_to_nodes(a, strict)
            if c is None:
                a = deref(a)
                if not _arith_leaf(a):
                    # A DATA term that merely uses an arithmetic functor --
                    # a key-value pair ``-(a, 1)`` from =.. or keysort -- is
                    # left exactly as it was: ``==`` on two ground pairs
                    # keeps its ground fallback (roborev job 273).  Strict
                    # posts refuse the offending leaf instead.
                    if strict is not None:
                        raise _not_evaluable(a, strict)
                    return None
                c = a
            args.append(c)
        cls = _key_nodes().get(ka[0])
        if cls is None:
            # An evaluable with no operator node (``abs/1``, ``min/2``,
            # ``max/2``): no linearising walker knows it, so a GROUND one is
            # folded to its value here and a non-ground one is left as the
            # cell, for each post's own diagnosis (the CLP posts do not
            # propagate through it).
            return _eval_ground(x)
        if len(args) == 1:
            return cls(operand=args[0])
        return cls(left=args[0], right=args[1])
    if strict is not None and (ka is not None or t is str):
        raise _not_evaluable(x, strict)
    return None


def _arith_leaf(a) -> bool:
    """*a* (dereferenced) can stand under an arithmetic node: a number, an
    unbound variable, an operator node, or an exact-number cell."""
    t = type(a)
    if t is int or t is float or t is Fraction or t is Decimal:
        return True
    if is_var(a) or t in _NODE_KEYS:
        return True
    return exact_cell_number(a) is not None


def _cells_as_nodes(l, r, strict=None):
    """``(l, r)`` with arithmetic cells rewritten (see _arith_cells_to_nodes;
    CLP(Q) and CLP(R) pass their context as *strict*)."""
    tl, tr = type(l), type(r)
    cl = None if tl is int or tl is float else _arith_cells_to_nodes(l, strict)
    cr = None if tr is int or tr is float else _arith_cells_to_nodes(r, strict)
    return (l if cl is None else cl), (r if cr is None else cr)


# ── Variable collection ──────────────────────────────────────────────────────


def _collect_constraint_vars(lhs, rhs) -> tuple:
    """Collect all Vars from both sides of a constraint."""
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


def _linearise(expr) -> tuple[dict, int] | None:
    """Try to express *expr* as a linear combination of Vars plus a constant.

    Returns ``(coeffs, constant)`` where *coeffs* maps each Var to its integer
    coefficient, or ``None`` if the expression is non-linear (e.g. var * var).
    """
    expr = deref(expr)
    if isinstance(expr, int):
        return {}, expr
    if is_var(expr):
        return {expr: 1}, 0
    _ensure_term_imports()
    if isinstance(expr, _Add):
        lc = _linearise(expr.left)
        rc = _linearise(expr.right)
        if lc is None or rc is None:
            return None
        l_coeffs, l_const = lc
        r_coeffs, r_const = rc
        merged = dict(l_coeffs)
        for v, c in r_coeffs.items():
            merged[v] = merged.get(v, 0) + c
        return {v: c for v, c in merged.items() if c != 0}, l_const + r_const
    if isinstance(expr, _Sub):
        lc = _linearise(expr.left)
        rc = _linearise(expr.right)
        if lc is None or rc is None:
            return None
        l_coeffs, l_const = lc
        r_coeffs, r_const = rc
        merged = dict(l_coeffs)
        for v, c in r_coeffs.items():
            merged[v] = merged.get(v, 0) - c
        return {v: c for v, c in merged.items() if c != 0}, l_const - r_const
    if isinstance(expr, _Mult):
        lc = _linearise(expr.left)
        rc = _linearise(expr.right)
        if lc is None or rc is None:
            return None
        l_coeffs, l_const = lc
        r_coeffs, r_const = rc
        if not l_coeffs:  # left is a pure constant k
            k = l_const
            return {v: c * k for v, c in r_coeffs.items()}, r_const * k
        if not r_coeffs:  # right is a pure constant k
            k = r_const
            return {v: c * k for v, c in l_coeffs.items()}, l_const * k
        return None  # var * var — non-linear
    if isinstance(expr, _Negate):
        inner = _linearise(expr.operand)
        if inner is None:
            return None
        coeffs, const = inner
        return {v: -c for v, c in coeffs.items()}, -const
    return None


# ── Propagation engine (AC-3) ───────────────────────────────────────────────


def propagate(queue: deque, trail: Trail) -> bool:
    """AC-3 fixpoint loop: propagate constraints until stable or wipeout.

    No seen-set: _narrow_if_changed only enqueues when a domain actually
    shrinks, so termination is guaranteed by the finite total domain size.
    """
    while queue:
        var = queue.popleft()
        var = deref(var)
        if not is_var(var):
            continue
        state = get_attr(var, FD_KEY)
        if state is None:
            continue
        for constraint in state.constraints:
            if not constraint.propagate(trail, queue):
                return False
    return True


def _add_constraint(var: Var, constraint: Constraint, trail: Trail) -> None:
    """Attach a constraint to a variable, creating new FDVar (trail-safe)."""
    state = _ensure_fd(var, trail)
    new_state = FDVar(state.domain, state.constraints + (constraint,))
    put_attr(var, FD_KEY, new_state, trail)


def _post_constraint(constraint: Constraint, trail: Trail) -> bool:
    """Attach constraint to all its variables and run initial propagation."""
    for v in constraint.vars:
        v = deref(v)
        if is_var(v):
            _add_constraint(v, constraint, trail)
    queue: deque = deque()
    if not constraint.propagate(trail, queue):
        return False
    return propagate(queue, trail)


# ── Top-level constraint posting functions ───────────────────────────────────


def _is_fd_candidate(x) -> bool:
    """True if x is a Var or an integer (types that participate in CLP(FD))."""
    return is_var(x) or (isinstance(x, int) and not isinstance(x, bool))


def _is_fd_sum_element(x) -> bool:
    """True if *x* may legally appear as a sum_/scalar_product element: an FD
    candidate (Var or plain int) or an arithmetic-expression node such as the
    compiler emits for ``X + 1`` (A06-F014).  A non-integer atom (string,
    float, Fraction) would otherwise reach _expr_domain's catch-all — which
    historically treated it as an unconstrained integer and now raises the
    typed unknown-leaf error; rejecting up front keeps sum_/scalar_product's
    silent-skip contract for malformed element lists."""
    if _is_fd_candidate(x):
        return True
    _ensure_term_imports()
    return isinstance(x, (_Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow, _Negate))


def _is_rational_arg(x) -> bool:
    """True if x is a Fraction, a Var with a rational-domain attribute,
    or an expression tree containing one of the above.

    Fast-path: plain ints and floats (the common case for CLP(Z) and CLP(R))
    are rejected immediately without touching expression-tree imports.
    """
    x = deref(x)
    # Fast reject: int and float are the overwhelmingly common cases
    if type(x) is int or type(x) is float:
        return False
    if isinstance(x, (Fraction, Decimal)):
        # a Decimal enters CLP(Q) exactly (Fraction(d)); its scale is not
        # reconstructed on the way out -- a CLP(Q) result is a rational
        return True
    if is_var(x):
        from clausal.logic.clpq import Q_KEY  # noqa: PLC0415
        return get_attr(x, Q_KEY) is not None
    # Walk expression trees (only reached for Add/Sub/Mult/... nodes)
    if _Add is None:
        _ensure_term_imports()
    if isinstance(x, _Div):
        # Div is TRUE division in Clausal, so int/int → a Fraction: the node
        # is CLP(Q) territory unless one side is real/float (A06-F006).
        # Detecting this at post time routes `X == Y + 1/2` to q_eq rather
        # than posting as CLP(Z) and crashing when Y is later bound.
        if _is_real_arg(x.left) or _is_real_arg(x.right):
            return _is_rational_arg(x.left) or _is_rational_arg(x.right)
        return True
    if isinstance(x, (_Add, _Sub, _Mult, _FloorDiv, _Mod, _Pow)):
        return _is_rational_arg(x.left) or _is_rational_arg(x.right)
    if isinstance(x, _Negate):
        return _is_rational_arg(x.operand)
    return False


def _any_rational(l, r) -> bool:
    """True if either argument should use CLP(Q) dispatch."""
    return _is_rational_arg(l) or _is_rational_arg(r)


def _is_real_arg(x) -> bool:
    """True if x is a float literal or a Var with a real-domain attribute."""
    x = deref(x)
    if isinstance(x, float):
        return True
    if is_var(x):
        from clausal.logic.clpr import REAL_KEY
        return get_attr(x, REAL_KEY) is not None
    return False


def _any_real(l, r) -> bool:
    """True if either argument should use CLP(R) dispatch."""
    return _is_real_arg(l) or _is_real_arg(r)


def _ground_number_pair(l, r) -> bool:
    """Both sides are ground NUMBERS (int, float, Fraction, Decimal; not
    bool): the comparison is a VALUE question and needs no solver.

    Sits ahead of ``_check_no_mixed_rational_real`` in the four comparison
    entries: that check refuses a Fraction beside a float as "cannot mix
    CLP(Q) and CLP(R)" -- right for a constraint over VARIABLES, wrong for
    two ground values, where ``Fraction(1, 2) == 0.5`` is simply true.
    Latent while the compiled tree divided to floats; exposed 2026-09-17 when
    runtime ``1 / N`` became rational (step 2) and the suite's own
    ``safe reciprocal of 2`` (``R == 0.5``) hit the refusal.  Python compares
    all four kinds by exact value, which is what ``=:=`` means here.
    """
    return (isinstance(l, (int, float, Fraction, Decimal)) and not isinstance(l, bool)
            and isinstance(r, (int, float, Fraction, Decimal)) and not isinstance(r, bool))


def _check_no_mixed_rational_real(l, r) -> None:
    """Raise TypeError if one arg is rational and the other is float/real."""
    l_rat = _is_rational_arg(l)
    r_rat = _is_rational_arg(r)
    if l_rat and _is_real_arg(r):
        raise TypeError(
            "cannot mix CLP(Q) rational and CLP(R) float in the same constraint"
        )
    if r_rat and _is_real_arg(l):
        raise TypeError(
            "cannot mix CLP(Q) rational and CLP(R) float in the same constraint"
        )


def _resolve(x):
    """Resolve x: if it's an arithmetic expression tree, try to evaluate it.

    Returns the evaluated integer if fully ground, otherwise the original value.
    """
    if _Add is None:
        _ensure_term_imports()
    if isinstance(x, (_Add, _Sub, _Mult, _Negate)):
        val = _eval_ground(x)
        if val is not None:
            return val
    if _Div is not None and isinstance(x, (_Div, _FloorDiv, _Mod)):
        val = _eval_ground(x)
        if val is not None:
            return val
    if _NODE_KEYS.get(type(x)) == ("**", 2):
        # a quoted '**' cell is Scryer's float power: a ground one folds to
        # its float here, ahead of the CLP(Q)/CLP(R) dispatch (the bare
        # ``**`` node is Python's integer power and is not folded)
        val = _eval_ground(x)
        if val is not None:
            return val
    if type(x) is tuple:
        # an exact-number cell (``rdiv(7, 2)``, ``decimal(15, 1)``) is the
        # number it denotes in a post too (ruling Q15: rdiv is exact
        # everywhere)
        num = exact_cell_number(x)
        if num is not None:
            return present_number(num)
        # an arithmetic CELL (ruling R9 A1) folds EXACTLY as its node does:
        # rewrite it, then resolve the node (``**`` is not folded, above).  A
        # data term that merely uses an arithmetic functor (``-(a, 1)``) is
        # not rewritten and keeps the ground fallback it always had.
        node = _arith_cells_to_nodes(x)
        if node is not None:
            return _resolve(node)
    return x


_TEXT_SPELLINGS: tuple = ()
_LIST_SPELLINGS: tuple = ()


def _ensure_text_list_imports() -> None:
    """Bind the two spelling families a text term can wear (lazy: ``terms``
    imports back into this module)."""
    global _TEXT_SPELLINGS, _LIST_SPELLINGS
    if _TEXT_SPELLINGS:
        return
    from clausal.terms import SegList, SegString  # noqa: PLC0415
    _TEXT_SPELLINGS = (SegString,)          # STAGE 2: a bare str is an ATOM; the carrier is unwrapped by the caller
    _LIST_SPELLINGS = (list, SegList)


def _text_list_eq(l, r):
    """Chars-model equality for the two spellings of ONE text term.

    Under ``-double_quotes(chars)`` a ``str`` IS the list of its 1-char atoms:
    ``"ab"`` and ``[('a',), ('b',)]`` are the same term, and ground
    unification and ``length/2`` already say so.  The ground fallback of
    ``==`` / ``!=`` is Python's own equality, and ``str.__eq__`` answers
    ``False`` to a list on sight — so ``"ab" == [a, b]`` failed where ISO
    says true, and the two operations disagreed about one term.

    Answers ``True``/``False`` when the pair is a text spelling against a list
    spelling, and ``None`` when the rule does not apply, leaving every other
    ground pair on Python equality (notably ``1 == 1.0``, which is arithmetic
    truth and NOT term identity).  The decision itself is delegated to
    ``structural_eq`` — the unifier is the one authority on which terms are
    the same term, so ``==`` cannot drift from ``is``.

    A char atom against a 1-char str stays UNEQUAL: ``"a"`` is the one-element
    list ``[a]``, not the cell ``a``, and a tuple is neither spelling here.
    """
    from clausal.logic.cells import chars, is_chars, chars_text  # noqa: PLC0415
    if not _TEXT_SPELLINGS:
        _ensure_text_list_imports()
    l_text = is_chars(l) or isinstance(l, _TEXT_SPELLINGS)
    r_text = is_chars(r) or isinstance(r, _TEXT_SPELLINGS)
    if is_chars(l):
        l = chars_text(l)
    if is_chars(r):
        r = chars_text(r)
    if l_text and r_text:
        from clausal.logic.constraints import structural_eq  # noqa: PLC0415
        return structural_eq(l, r)
    if l_text:
        if not isinstance(r, _LIST_SPELLINGS):
            return None
        return _text_eq_list(l, r)
    if isinstance(l, _LIST_SPELLINGS):
        if not r_text:
            return None
        return _text_eq_list(r, l)
    return None


def _text_eq_list(text, lst) -> bool:
    """The text (a str already unwrapped from the carrier, or a SegString)
    against a list: equal iff the list is exactly the text's chars.  STAGE 2:
    the C unifier reads a bare str as an ATOM, so this compare is done here,
    char by char (a char is a 1-char str)."""
    from clausal.logic.cells import chars, is_chars, chars_text  # noqa: PLC0415
    from clausal.terms import SegString, SegList  # noqa: PLC0415
    if isinstance(text, SegString):
        w = text.__walk__()
        if not is_chars(w):
            from clausal.logic.constraints import structural_eq  # noqa: PLC0415
            return structural_eq(text, lst)           # non-ground: the unifier decides
        text = chars_text(w)
    if isinstance(lst, SegList):
        w = lst.__walk__()
        if is_chars(w):
            return chars_text(w) == text
        if not isinstance(w, list):
            from clausal.logic.constraints import structural_eq  # noqa: PLC0415
            return structural_eq(chars(text), lst)
        lst = w
    if len(lst) != len(text):
        return False
    for c, e in zip(text, lst):
        e = deref(e)
        if not (type(e) is str and e == c):
            return False
    return True


def _both_ground(l, r) -> bool:
    """True if both sides are concrete values with no unbound Vars or expression trees."""
    if is_var(l) or is_var(r):
        return False
    if _Add is None:
        _ensure_term_imports()
    expr_types = (_Add, _Sub, _Mult, _Negate, _Div, _FloorDiv, _Mod, _Pow)
    if isinstance(l, expr_types) or isinstance(r, expr_types):
        return False
    return True


def _walk_compound(x):
    """A compound operand of the ground fallback, with every BOUND variable
    inside it replaced by its value (unbound ones stay).

    ``_both_ground`` looks at the top of each side only, and the fallback is
    Python equality -- which compares a bound ``Var`` object inside a list,
    cell or dict, not its value.  So ``X is [Y], Y is 1, X == [1]`` failed
    where unification, the quoted ``'=='`` and ISO ==/2 (8.4.1.1, which
    dereferences every subterm) all hold.  A scalar is returned as is, so the
    walk costs nothing on the common numeric path."""
    if isinstance(x, (list, tuple, dict)) or hasattr(type(x), "__walk__"):
        from clausal.logic.solve import _deref_walk  # noqa: PLC0415
        return _deref_walk(x)
    return x


def _expr_tree_has_var(x) -> bool:
    """True if *x* is an unbound Var, or an arithmetic expression tree with
    at least one unbound Var leaf (dereferenced).  Used by the non-numeric
    guards to classify a comparison side as "constrainable": ``X + 1``
    against a ground non-numeric operand is the same broken-var defect as
    bare ``X`` against it, one level down.  A fully-ground tree returns
    False — ``_resolve`` (Python) / the C impls evaluate those to scalars,
    so ``2 + 3 == "banana"`` must keep its ground fallback (Python ``==`` →
    False), not become a guard rejection."""
    x = deref(x)
    if is_var(x):
        return True
    # The node classes are imported LAZILY; before any arithmetic node has
    # been evaluated in the process they are still ``None`` and the
    # ``isinstance`` below raises a raw TypeError on any ground non-var leaf
    # -- measured 2026-09-17 on a Fraction reaching a reified ``==`` from a
    # compiled ``$div`` (step 2), latent before because the compiled tree
    # produced floats that took the C fast path instead.
    if _Add is None:
        _ensure_term_imports()
    if isinstance(x, (_Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow)):
        return _expr_tree_has_var(x.left) or _expr_tree_has_var(x.right)
    if isinstance(x, _Negate):
        return _expr_tree_has_var(x.operand)
    return False


def _reject_nonnumeric_eq(l, r, context: str = "(==)/2") -> None:
    """A12-F002: raise a catchable ``domain_error(clpz_expression, Ground)``
    (Scryer's clpz formal, Q3 2026-09-28) when a Var is compared with ``==``
    (or ``!=``, which passes ``context="(!=)/2"`` — arithmetic disequality is
    the same defect family, while ``dif/2`` stays the structural form)
    against a GROUND operand that is not a number.  Posting the EqConstraint
    instead made a broken FD var — its unification hook accepts integers
    only, so the var rejected anything EXCEPT ints, including a later
    binding to the very operand it was equated with (an atom, a string, a
    collection, a ground compound, and — the gap the original blocklist
    left open — a date, a Quantity, a Decimal, None, …).  A side counts as
    the "var side" when it is a bare Var OR an expression tree containing
    one (``X + 1 == "banana"`` is the same defect one level down — the
    ``_expr_domain`` catch-all treated the string as an unconstrained
    integer and produced silently WRONG answers); both-ground ``==`` (incl.
    fully-ground trees, which _resolve/the C impls evaluate to scalars)
    falls back to Python equality, and Var==Var / Var==<arith-expr> stay
    legal.  The ground side must be ``numbers.Real`` — the same allowlist as
    :func:`_reject_nonnumeric_order` — so int posts CLP(FD), float
    dispatches to CLP(R) and Fraction to CLP(Q); a fully-ground expr tree
    (Add/…/Pow/Negate, plain ``pythonic_ast`` dataclasses) also passes.
    Like the ordering guard, run BEFORE the CLP(Q)/CLP(R) dispatch in both
    the Python ``fd_eq`` and the C-accelerated wrapper, so an attr-carrying
    var cannot smuggle a non-numeric operand into q_eq/real_eq."""
    dl, dr = deref(l), deref(r)
    if _Add is None:
        _ensure_term_imports()
    varish_l = is_var(dl) or _expr_tree_has_var(dl)
    varish_r = is_var(dr) or _expr_tree_has_var(dr)
    if varish_l == varish_r:
        return  # both constrainable, or both ground — not the broken case
    ground = dr if varish_l else dl
    if isinstance(ground, numbers.Real):
        return
    if isinstance(ground, (_Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow,
                           _Negate)):
        return  # fully-ground tree: dispatch resolves and compares it
    # Scryer's ``X #= foo(1)`` formal (Q3, 2026-09-28; it was
    # type_error(evaluable, Ground)).
    from clausal.logic.exceptions import LogicException, domain_error
    raise LogicException(domain_error("clpz_expression", ground, context))


def _incomparable_order_error(culprit, context: str) -> "LogicException":
    """Catchable error for an order comparison of two ground values that are
    each orderable but not orderable against each other (e.g. a ``date`` vs a
    ``datetime``, a naive vs a tz-aware ``datetime``, or a ``date`` vs an
    ``int``).  Reuses the ``type_error(orderable, Culprit, Context)`` shape
    that ``min_list/2`` / ``max_list/2`` already raise, so one handler
    catches them all.  *culprit* is the right-hand operand; *context* names
    the primitive operator (``"(<)/2"`` or ``"(=<)/2"``)."""
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    return LogicException(type_error("orderable", culprit, context))


def _reject_nonnumeric_order(l, r, context: str) -> None:
    """Ordering-comparator sibling of :func:`_reject_nonnumeric_eq`: raise a
    catchable ``domain_error(clpz_expression, Culprit)`` (Scryer's clpz
    formal, Q3 2026-09-28) when a ground
    NON-NUMERIC operand is ordered against an unbound var.  Posting the FD
    Lt/Le constraint instead made the same broken var as A12-F002 — the
    unification hook then rejected EVERY later binding, so ``X < "banana",
    X is "apple"`` had 0 solutions with no diagnostic.  Like the ``==``
    guard, a side counts as the "var side" when it is a bare Var OR an
    expression tree containing one (``X + 1 < "banana"`` is the same defect
    one level down); both-ground ordering — fully-ground trees included —
    falls back to Python ``<``/``<=`` (which handles strings, dates, … fine),
    and Var-vs-Var / Var-vs-expr-tree stay legal residual constraints.  The
    ground side must be ``numbers.Real`` — int posts CLP(FD), float
    dispatches to CLP(R), Fraction to CLP(Q); everything else (str, date,
    Quantity, Decimal, atom class, compound, …) is rejected.  A fully-ground
    arithmetic expression tree also passes.  (Before Q3 this reused the
    ``orderable`` shape of :func:`_incomparable_order_error`, which stays the
    error of two GROUND values that do not order.)  *culprit* is the
    offending ground operand, whichever side it appears on.  Call-order independent, and deliberately run BEFORE the
    CLP(Q)/CLP(R) dispatch in both the Python comparators and the
    C-accelerated wrappers: a var carrying a rational/real attribute
    triggers the dispatch on its own, and q_lt/real_lt would otherwise post
    against the ground non-numeric operand unchecked."""
    dl, dr = deref(l), deref(r)
    if _Add is None:
        _ensure_term_imports()
    varish_l = is_var(dl) or _expr_tree_has_var(dl)
    varish_r = is_var(dr) or _expr_tree_has_var(dr)
    if varish_l == varish_r:
        return  # both constrainable, or both ground — not the broken case
    ground = dr if varish_l else dl
    if isinstance(ground, numbers.Real):
        return
    if isinstance(ground, (_Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow,
                           _Negate)):
        return  # fully-ground tree: dispatch resolves and compares it
    # Scryer's ``X #< foo(1)`` formal (Q3, 2026-09-28; it was
    # type_error(orderable, Ground)).
    from clausal.logic.exceptions import LogicException, domain_error  # noqa: PLC0415
    raise LogicException(domain_error("clpz_expression", ground, context))


def fd_eq(l, r, trail: Trail, *, _units_done: bool = False) -> bool:
    """Post X == Y.

    Dispatches to CLP(R) if either argument is a float or real variable;
    otherwise posts a CLP(FD) constraint.  For ground non-Var values,
    falls back to Python ``==``.

    when either side is a linear arithmetic expression tree (Add/Sub/Mult/
    Negate), linearises both sides and posts a ScalarProductConstraint for
    full bounds-consistency propagation back to the leaf variables.  Non-
    linear expressions (var * var) fall back to EqConstraint.
    """
    l = deref(l)
    r = deref(r)
    # ── fast path: ground integer comparison ──
    if type(l) is int and type(r) is int:
        return l == r
    # ── end fast path ──
    stripped = None if _units_done else _units_strip(l, r, "(==)/2", trail)
    if stripped is not None:
        l, r = stripped
    if not is_var(l):
        l = _resolve(l)
    if not is_var(r):
        r = _resolve(r)
    if _ground_number_pair(l, r):
        return l == r
    # ruling R9 A1: an arithmetic CELL (``+(X, 2)`` built by ``=..``) posts
    # as its operator node -- every walker below reads nodes
    l, r = _cells_as_nodes(l, r)
    _check_no_mixed_rational_real(l, r)
    # A12-F002: a ground non-numeric operand against a Var made a broken FD
    # var (one that equals anything EXCEPT the operand). Reject it as a
    # catchable type error (A09-D002) — BEFORE the CLP(Q)/CLP(R) dispatch,
    # so an attr-carrying var cannot route it into q_eq/real_eq unchecked.
    _reject_nonnumeric_eq(l, r)
    if _any_rational(l, r):
        from clausal.logic.clpq import q_eq  # noqa: PLC0415
        return q_eq(l, r, trail)
    if _any_real(l, r):
        from clausal.logic.clpr import real_eq
        return real_eq(l, r, trail)
    # If either side is an expression tree, try to linearise
    if _Add is None:
        _ensure_term_imports()
    if isinstance(l, (_Add, _Sub, _Mult, _Negate)) or isinstance(r, (_Add, _Sub, _Mult, _Negate)):
        lc = _linearise(l)
        rc = _linearise(r)
        if lc is not None and rc is not None:
            l_coeffs, l_const = lc
            r_coeffs, r_const = rc
            # l == r  →  (l_coeffs - r_coeffs)·vars = r_const - l_const
            merged = dict(l_coeffs)
            for v, c in r_coeffs.items():
                merged[v] = merged.get(v, 0) - c
            coeffs_dict = {v: c for v, c in merged.items() if c != 0}
            value = r_const - l_const
            if not coeffs_dict:
                return l_const == r_const  # purely constant: no vars
            vars_tuple = tuple(coeffs_dict.keys())
            coeffs_tuple = tuple(coeffs_dict[v] for v in vars_tuple)
            for v in vars_tuple:
                _ensure_fd(v, trail)
            return _post_constraint(ScalarProductConstraint(coeffs_tuple, vars_tuple, value), trail)
        # Non-linear: fall through to EqConstraint
    if _both_ground(l, r):
        l, r = _walk_compound(l), _walk_compound(r)
        _eq = _text_list_eq(l, r)
        return (l == r) if _eq is None else _eq
    # At least one Var — use CLP(FD)
    if is_var(l):
        _ensure_fd(l, trail)
    if is_var(r):
        _ensure_fd(r, trail)
    constraint = EqConstraint(l, r)
    return _post_constraint(constraint, trail)


def fd_ne(l, r, trail: Trail, *, _units_done: bool = False) -> bool:
    """Post X != Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    # ── fast path: ground integer comparison ──
    if type(l) is int and type(r) is int:
        return l != r
    # ── end fast path ──
    stripped = None if _units_done else _units_strip(l, r, "(!=)/2", trail)
    if stripped is not None:
        l, r = stripped
    if not is_var(l):
        l = _resolve(l)
    if not is_var(r):
        r = _resolve(r)
    if _ground_number_pair(l, r):
        return l != r
    # ruling R9 A1: an arithmetic CELL (``+(X, 2)`` built by ``=..``) posts
    # as its operator node -- every walker below reads nodes
    l, r = _cells_as_nodes(l, r)
    _check_no_mixed_rational_real(l, r)
    # A ground non-numeric operand against a Var made the same broken var as
    # == (A12-F002 family): the NeConstraint's hook rejects every non-integer
    # binding, so X != "banana" excluded "apple" too. Guard before the
    # CLP(Q)/CLP(R) dispatch, like ==/</=<.
    _reject_nonnumeric_eq(l, r, "(!=)/2")
    if _any_rational(l, r):
        from clausal.logic.clpq import q_ne  # noqa: PLC0415
        return q_ne(l, r, trail)
    if _any_real(l, r):
        from clausal.logic.clpr import real_ne
        return real_ne(l, r, trail)
    if _both_ground(l, r):
        l, r = _walk_compound(l), _walk_compound(r)
        _eq = _text_list_eq(l, r)
        return (l != r) if _eq is None else (not _eq)
    if is_var(l):
        _ensure_fd(l, trail)
    if is_var(r):
        _ensure_fd(r, trail)
    constraint = NeConstraint(l, r)
    return _post_constraint(constraint, trail)


def fd_lt(l, r, trail: Trail, *, _units_done: bool = False) -> bool:
    """Post X < Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    # ── fast path: ground integer comparison ──
    if type(l) is int and type(r) is int:
        return l < r
    # ── end fast path ──
    stripped = None if _units_done else _units_strip(l, r, "(<)/2", trail)
    if stripped is not None:
        l, r = stripped
    if not is_var(l):
        l = _resolve(l)
    if not is_var(r):
        r = _resolve(r)
    if _ground_number_pair(l, r):
        return l < r
    # ruling R9 A1: an arithmetic CELL (``+(X, 2)`` built by ``=..``) posts
    # as its operator node -- every walker below reads nodes
    l, r = _cells_as_nodes(l, r)
    _check_no_mixed_rational_real(l, r)
    # BEFORE the CLP(Q)/CLP(R) dispatch, not after: a var carrying a
    # rational/real attribute triggers the dispatch on its own, and q_lt /
    # real_lt would post against the ground non-numeric operand unchecked —
    # diverging from the C-accelerated wrapper, which guards first.
    _reject_nonnumeric_order(l, r, "(<)/2")
    try:
        if _any_rational(l, r):
            from clausal.logic.clpq import q_lt  # noqa: PLC0415
            return q_lt(l, r, trail)
        if _any_real(l, r):
            from clausal.logic.clpr import real_lt
            return real_lt(l, r, trail)
        if _both_ground(l, r):
            return l < r
    except TypeError:
        if is_var(l) or is_var(r):
            raise
        if _any_rational(l, r) and _any_real(l, r):
            raise
        raise _incomparable_order_error(r, "(<)/2")
    if is_var(l):
        _ensure_fd(l, trail)
    if is_var(r):
        _ensure_fd(r, trail)
    constraint = LtConstraint(l, r)
    return _post_constraint(constraint, trail)


def fd_le(l, r, trail: Trail, *, _units_done: bool = False) -> bool:
    """Post X <= Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    # ── fast path: ground integer comparison ──
    if type(l) is int and type(r) is int:
        return l <= r
    # ── end fast path ──
    stripped = None if _units_done else _units_strip(l, r, "(=<)/2", trail)
    if stripped is not None:
        l, r = stripped
    if not is_var(l):
        l = _resolve(l)
    if not is_var(r):
        r = _resolve(r)
    if _ground_number_pair(l, r):
        return l <= r
    # ruling R9 A1: an arithmetic CELL (``+(X, 2)`` built by ``=..``) posts
    # as its operator node -- every walker below reads nodes
    l, r = _cells_as_nodes(l, r)
    _check_no_mixed_rational_real(l, r)
    # Guard before the dispatch, matching fd_lt and the C wrapper.
    _reject_nonnumeric_order(l, r, "(=<)/2")
    try:
        if _any_rational(l, r):
            from clausal.logic.clpq import q_le  # noqa: PLC0415
            return q_le(l, r, trail)
        if _any_real(l, r):
            from clausal.logic.clpr import real_le
            return real_le(l, r, trail)
        if _both_ground(l, r):
            return l <= r
    except TypeError:
        if is_var(l) or is_var(r):
            raise
        if _any_rational(l, r) and _any_real(l, r):
            raise
        raise _incomparable_order_error(r, "(=<)/2")
    if is_var(l):
        _ensure_fd(l, trail)
    if is_var(r):
        _ensure_fd(r, trail)
    constraint = LeConstraint(l, r)
    return _post_constraint(constraint, trail)


def fd_gt(l, r, trail: Trail, *, _units_done: bool = False) -> bool:
    """Post X > Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    if type(l) is int and type(r) is int:
        return l > r
    if not _units_done:
        stripped = _units_strip(l, r, "(>)/2", trail)   # name the operator the user wrote
        if stripped is not None:
            l, r = stripped
    return fd_lt(r, l, trail, _units_done=True)      # scanned here, once


def fd_ge(l, r, trail: Trail, *, _units_done: bool = False) -> bool:
    """Post X >= Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    if type(l) is int and type(r) is int:
        return l >= r
    if not _units_done:
        stripped = _units_strip(l, r, "(>=)/2", trail)   # name the operator the user wrote
        if stripped is not None:
            l, r = stripped
    return fd_le(r, l, trail, _units_done=True)      # scanned here, once


# ── FD attribute hook ────────────────────────────────────────────────────────


def _fd_hook(attr_value: Any, bound_to: Any, trail: Trail) -> bool:
    """Called when an FD-constrained var is unified.

    *attr_value* is the FDVar instance.
    *bound_to* is the value the variable was bound to.
    """
    state = attr_value
    bound_to = deref(bound_to)

    # Accept int or integer-valued Fraction (e.g., Fraction(3) from CLP(Q))
    int_val = None
    if isinstance(bound_to, int) and not isinstance(bound_to, bool):
        int_val = bound_to
    elif isinstance(bound_to, Fraction) and bound_to.denominator == 1:
        int_val = int(bound_to)

    if int_val is not None:
        # Check domain membership
        if not domain_contains(state.domain, int_val):
            return False
        # Propagate constraints
        queue: deque = deque()
        for constraint in state.constraints:
            if not constraint.propagate(trail, queue):
                return False
        return propagate(queue, trail)

    if is_var(bound_to):
        # Unified with another var — merge FD state
        other_state = get_attr(bound_to, FD_KEY)
        if other_state is None:
            # Narrow FD domain against real interval if bound_to has one
            from clausal.logic.clpr import REAL_KEY
            real_state = get_attr(bound_to, REAL_KEY)
            if real_state is not None:
                import math
                r_lo = _NEG_INF if real_state.lo == -math.inf else math.ceil(real_state.lo)
                r_hi = _POS_INF if real_state.hi == math.inf else math.floor(real_state.hi)
                narrowed = domain_intersection(
                    state.domain, domain_from_range(r_lo, r_hi)
                )
                if not narrowed:
                    return False
                state = FDVar(narrowed, state.constraints)
            put_attr(bound_to, FD_KEY, state, trail)
            # Propagate constraints from transferred state
            val = domain_singleton(state.domain)
            if val is not None:
                if not unify(bound_to, val, trail):
                    return False
            queue = deque()
            for constraint in state.constraints:
                if not constraint.propagate(trail, queue):
                    return False
            return propagate(queue, trail)
        else:
            # Both have FD — intersect domains, merge constraints
            new_domain = domain_intersection(state.domain, other_state.domain)
            if not new_domain:
                return False
            # Deduplicate constraints by identity
            seen_ids: set[int] = set()
            merged: list = []
            for c in state.constraints + other_state.constraints:
                cid = id(c)
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    merged.append(c)
            new_state = FDVar(new_domain, tuple(merged))
            put_attr(bound_to, FD_KEY, new_state, trail)
            # Check singleton
            val = domain_singleton(new_domain)
            if val is not None:
                if not unify(bound_to, val, trail):
                    return False
            # Propagate
            queue = deque()
            for constraint in merged:
                if not constraint.propagate(trail, queue):
                    return False
            return propagate(queue, trail)
        return True

    # Non-integer, non-var → fail
    return False


register_attr_hook(FD_KEY, _fd_hook)


# ── Builtins: in_domain, label, all_different, structural_eq ──────────────────


def in_domain(var_or_list, lo, hi, trail: Trail) -> bool:
    """Post domain [lo, hi] on a variable or list of variables.

    Quantity bounds go through the units side channel: the targets become
    united vars and the stripped bounds are posted on their shadows."""
    if _in_domain_units is None:
        _ensure_units_imports()
    united = _in_domain_units(var_or_list, lo, hi, trail)
    if united is not None:
        return united
    lo = deref(lo)
    hi = deref(hi)
    if not isinstance(lo, int) or not isinstance(hi, int):
        raise TypeError(f"in_domain bounds must be integers, got {lo!r}, {hi!r}")
    new_domain = domain_from_range(lo, hi)
    if not new_domain:
        return False

    targets = deref(var_or_list)
    # One shared queue across all targets, then a single propagation fixpoint,
    # so that constraints already posted on any target (or its peers) re-fire
    # against the narrowed domains (A06-F008).
    queue: deque = deque()
    if isinstance(targets, list):
        for v in targets:
            if not _post_domain(deref(v), new_domain, trail, queue):
                return False
    else:
        if not _post_domain(targets, new_domain, trail, queue):
            return False
    return propagate(queue, trail)


def _post_domain(target, new_domain: Domain, trail: Trail, queue: deque) -> bool:
    """Post domain on a single target, scheduling re-propagation via *queue*."""
    if isinstance(target, int):
        return domain_contains(new_domain, target)
    if not is_var(target):
        return False
    state = get_attr(target, FD_KEY)
    if state is None:
        final_domain = new_domain
    else:
        final_domain = domain_intersection(state.domain, new_domain)
        if not final_domain:
            return False
    # Narrow against real interval if present
    from clausal.logic.clpr import REAL_KEY
    real_state = get_attr(target, REAL_KEY)
    if real_state is not None:
        import math
        r_lo = _NEG_INF if real_state.lo == -math.inf else math.ceil(real_state.lo)
        r_hi = _POS_INF if real_state.hi == math.inf else math.floor(real_state.hi)
        final_domain = domain_intersection(final_domain, domain_from_range(r_lo, r_hi))
        if not final_domain:
            return False
    # Route the narrow through _narrow_if_changed (queues the var and runs the
    # singleton→unify step) rather than a bare put_attr, which left dependent
    # vars un-narrowed because no constraint ever re-fired (A06-F008).
    return _narrow_if_changed(target, final_domain, trail, queue)


def label(vars_list, trail: Trail):
    """label variables: enumerate all values in domains.

    Uses first-fail strategy: picks the variable with the smallest domain first.
    Generator: yields None for each assignment.
    """
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        vars_list = [vars_list]
    # A united var is labelled through its shadow (units side channel);
    # the units_link hook rebinds the user's var on every solution. The
    # substitution happens ONCE here; the search recurses on _label_fd.
    if _label_targets is None:
        _ensure_units_imports()
    yield from _label_fd(_label_targets(vars_list), trail)


def _label_fd(vars_list: list, trail: Trail):
    """The labelling search proper, over a list already stripped of united
    vars (see :func:`label`)."""
    # Collect unbound vars with FD domains
    unbound: list = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            unbound.append(v)

    if not unbound:
        yield None
        return

    # First-fail: pick var with smallest domain
    best = None
    best_size = None
    for v in unbound:
        v = deref(v)
        if not is_var(v):
            continue
        state = get_attr(v, FD_KEY)
        if state is None:
            continue
        sz = domain_size(state.domain)
        if best_size is None or sz < best_size:
            best = v
            best_size = sz

    if best is None:
        # All vars already ground
        yield None
        return

    state = get_attr(best, FD_KEY)
    if state is None:
        yield None
        return

    if domain_size(state.domain) == _POS_INF:
        raise ValueError(
            f"Cannot label variable with unbounded domain "
            f"[{domain_min(state.domain)}, {domain_max(state.domain)}]. "
            f"Use in_domain/3 to declare bounds before labeling."
        )

    for val in domain_values(state.domain):
        mark = trail.mark()
        if unify(best, val, trail):
            # Recurse for remaining vars
            yield from _label_fd(vars_list, trail)
        trail.undo(mark)


def all_different(vars_list, trail: Trail) -> bool:
    """Post all_different constraint on a list of variables."""
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        return False
    vars_list = _units_strip_list(vars_list, "all_different/1", trail)
    vars_tuple = tuple(deref(v) for v in vars_list)
    constraint = AllDiffConstraint(vars_tuple)
    return _post_constraint(constraint, trail)


import operator as _operator_module

_REIFY_OPS = {
    "eq": _operator_module.eq,
    "ne": _operator_module.ne,
    "lt": _operator_module.lt,
    "le": _operator_module.le,
    "gt": _operator_module.gt,
    "ge": _operator_module.ge,
}


def reify_fd(op: str, x, y, trail: Trail) -> bool | None:
    """Reified FD comparison: three-valued decision.

    op is one of "eq", "ne", "lt", "le", "gt", "ge".
    Returns True (ground-satisfies), False (ground-violates), None (undetermined).
    """
    x = deref(x)
    y = deref(y)
    # A reified test commits nothing, so the side channel runs only when
    # both sides are ground: stripping a non-ground side would create a
    # shadow (and declare the variable's dimension) for an answer of None.
    if not (_expr_tree_has_var(x) or _expr_tree_has_var(y)):
        stripped = _units_strip(x, y, "reify(" + op + ")/3", trail)
        if stripped is not None:
            x, y = stripped
    try:
        x = _resolve(x)
        y = _resolve(y)
    except _LogicException as exc:
        # Ruling Q14 (2026-09-28): a CLP(FD) relation over an expression
        # with no value (``1 // 0``) has no solutions -- so, reified, it is
        # FALSE, never an error.
        if _no_value_in_propagation(exc):
            return False
        raise
    if _both_ground(x, y):
        if op in ("eq", "ne"):
            x, y = _walk_compound(x), _walk_compound(y)
            # the chars-model arm ``fd_eq``/``fd_ne`` already have: the two
            # spellings of one text term (str / carrier / char list) are
            # equal here too, where Python's ``==`` on the raw values says no
            # (stage 1 -- a reified ``==`` inside ``if_/3`` took this path)
            _eq = _text_list_eq(x, y)
            if _eq is not None:
                return _eq if op == "eq" else (not _eq)
        return _REIFY_OPS[op](x, y)
    return None


def structural_eq(t1, t2, trail: Trail) -> bool:
    """Structural equality (Prolog ==/2): succeed iff deref'd terms are identical.

    Delegates to ``clausal.logic.constraints.structural_eq`` which does a
    proper recursive walk.  The *trail* argument is accepted for call-signature
    compatibility with other fd_* functions but is never modified.
    """
    from clausal.logic.constraints import structural_eq as _seq  # noqa: PLC0415
    return _seq(t1, t2)


# Backward-compat alias — will be removed in a future release.
equivalent = structural_eq


# ── Global constraints (Phase 5) ──────────────────────────────────────────


_FD_OPS = {
    "#=": _operator_module.eq,
    "#<": _operator_module.lt,
    "#>": _operator_module.gt,
    "#=<": _operator_module.le,
    "#>=": _operator_module.ge,
    "#\\=": _operator_module.ne,
    # Also accept without # prefix for convenience
    "=": _operator_module.eq,
    "<": _operator_module.lt,
    ">": _operator_module.gt,
    "=<": _operator_module.le,
    ">=": _operator_module.ge,
    "\\=": _operator_module.ne,
}


def _op_spelling(op, context):
    """The SPELLING of an operator ATOM (``#=``, ``#<``, ``<``, …), or None.

    Spec §6.4: an operator name is an ATOM.  ``#=`` cannot be written bare in
    the surface (``#`` opens a comment), so source spells it ``'#='`` -- or
    ``"#="`` under ``-double_quotes(atom)``; under the chars default that
    spelling is a STRING and is refused with the type_error below.
    Before THE FLIP (2026-09-06-atoms-as-cells-strings) this library gated on
    ``isinstance(op, str)``, which after the flip matches a STRING and nothing
    a source program can write, so every source-written call failed silently.

    - an atom → its spelling, which is what ``_FD_OPS`` and
      ``_op_to_binary_constraint`` key on;
    - a plain ``str`` → ``type_error(atom, …)``: a string is not a name, and
      a silent failure is exactly what hid this bug;
    - anything else (an unbound Var, a number, a compound) → ``None``, and
      the caller fails as it has always failed on a malformed operator.

    A string has two shapes — a plain ``str`` and a ground ``SegString`` that
    walks to one — and both must answer the same way, so the operator is
    walked first.  Without the walk a ``SegString`` operator fell through to
    ``None`` and failed silently instead of raising, exactly the reporting
    hole this funnel exists to close.
    """
    from clausal.logic.runtime._seg_helpers import walk_seg  # noqa: PLC0415
    from clausal.logic.cells import is_chars  # noqa: PLC0415
    op_as_written = op
    op = walk_seg(op)
    if is_atom(op):
        return spelling(op)
    if is_chars(op):                   # STAGE 2: a str IS the atom; the carrier is the string
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, type_error,
        )
        raise LogicException(type_error("atom", op_as_written, context))   # the culprit as the caller wrote it
    return None


def _op_to_binary_constraint(op_str, lhs, rhs):
    """Return the appropriate binary Constraint for lhs OP rhs, or None.

    *op_str* is an operator SPELLING (see :func:`_op_spelling`), not a term.
    """
    op_str = op_str.removeprefix("#")
    if op_str == "<":
        return LtConstraint(lhs, rhs)
    if op_str == ">":
        return LtConstraint(rhs, lhs)
    if op_str == "=<":
        return LeConstraint(lhs, rhs)
    if op_str == ">=":
        return LeConstraint(rhs, lhs)
    if op_str == "\\=":
        return NeConstraint(lhs, rhs)
    return None


def fd_sum(vars_list, op_str, value, trail: Trail):
    """sum_(Vars, Op, Value) — constrain sum of Vars under comparison Op to Value.

    Uses bounds-consistency propagation via SumConstraint.
    """
    vars_list = deref(vars_list)
    op_str = deref(op_str)
    value = deref(value)

    if not isinstance(vars_list, list):
        return
    op_str = _op_spelling(op_str, "sum_/3")
    if op_str is None:
        return
    op_fn = _FD_OPS.get(op_str)
    if op_fn is None:
        return
    # Units (after the operator check, so a bad operator still wins): every
    # summand and the value share one dimension, and a quantity must be a
    # whole number of units (the integer guard below would skip it silently).
    both = _units_strip_list(list(vars_list) + [value], "sum_/3", trail)
    vars_list, value = both[:-1], both[-1]

    vars_deref = [deref(v) for v in vars_list]

    # Reject non-integer elements up front (A06-F014): a string/float element
    # would otherwise post happily and be treated as an unconstrained integer.
    if not all(_is_fd_sum_element(v) for v in vars_deref):
        return

    # If all ground and value is also ground, just check
    val = deref(value)
    if all(isinstance(v, int) for v in vars_deref) and isinstance(val, int):
        if op_fn(sum(vars_deref), val):
            yield None
        return

    # Has FD vars — ensure domains, then post SumConstraint
    for v in vars_deref:
        if is_var(v):
            _ensure_fd(v, trail)

    value_d = deref(value)

    if op_str in ("#=", "="):
        # Post SumConstraint directly: Σ vars = value
        if is_var(value_d):
            _ensure_fd(value_d, trail)
        vars_tuple = tuple(deref(v) for v in vars_deref)
        if _post_constraint(SumConstraint(vars_tuple, value_d), trail):
            yield None
    else:
        # Introduce intermediate total variable, post SumConstraint + relational constraint
        total_var = Var()
        _ensure_fd(total_var, trail)
        vars_tuple = tuple(deref(v) for v in vars_deref)
        if not _post_constraint(SumConstraint(vars_tuple, total_var), trail):
            return
        bin_c = _op_to_binary_constraint(op_str, total_var, value_d)
        if bin_c is None:
            return
        if _post_constraint(bin_c, trail):
            yield None


def fd_scalar_product(coeffs, vars_list, op_str, value, trail: Trail):
    """scalar_product(Coeffs, Vars, Op, Value) — weighted sum constraint.

    Uses bounds-consistency propagation via ScalarProductConstraint.
    """
    coeffs = deref(coeffs)
    vars_list = deref(vars_list)
    op_str = deref(op_str)
    value = deref(value)

    if not isinstance(coeffs, list) or not isinstance(vars_list, list):
        return
    if len(coeffs) != len(vars_list):
        return
    op_str = _op_spelling(op_str, "scalar_product/4")
    if op_str is None:
        return
    op_fn = _FD_OPS.get(op_str)
    if op_fn is None:
        return
    # Units (after the operator check): coefficients are plain numbers; the vars and the value share
    # one dimension.
    if _strip_list_for_solver is None:
        _ensure_units_imports()
    if _units_flag_active():
        # Coefficients are plain numbers: dimensioned material is refused
        # before any strip (no shadow on the refusal path), a dimensionless
        # quantity becomes a plain int.
        from clausal.logic.units_clp import plain_fields_or_unsupported  # noqa: PLC0415
        coeffs = plain_fields_or_unsupported(coeffs, "scalar_product/4")
    both = _units_strip_list(list(vars_list) + [value], "scalar_product/4", trail)
    vars_list, value = both[:-1], both[-1]

    coeffs_deref = [deref(c) for c in coeffs]
    if not all(isinstance(c, int) for c in coeffs_deref):
        return

    vars_deref = [deref(v) for v in vars_list]

    # Reject non-integer elements up front (A06-F014).
    if not all(_is_fd_sum_element(v) for v in vars_deref):
        return

    # If all ground and value is also ground, just check
    val = deref(value)
    if all(isinstance(v, int) for v in vars_deref) and isinstance(val, int):
        if op_fn(sum(c * v for c, v in zip(coeffs_deref, vars_deref)), val):
            yield None
        return

    # Has FD vars — ensure domains, then post ScalarProductConstraint
    for v in vars_deref:
        if is_var(v):
            _ensure_fd(v, trail)

    value_d = deref(value)
    coeffs_tuple = tuple(coeffs_deref)
    vars_tuple = tuple(deref(v) for v in vars_deref)

    if op_str in ("#=", "="):
        if is_var(value_d):
            _ensure_fd(value_d, trail)
        if _post_constraint(ScalarProductConstraint(coeffs_tuple, vars_tuple, value_d), trail):
            yield None
    else:
        total_var = Var()
        _ensure_fd(total_var, trail)
        if not _post_constraint(ScalarProductConstraint(coeffs_tuple, vars_tuple, total_var), trail):
            return
        bin_c = _op_to_binary_constraint(op_str, total_var, value_d)
        if bin_c is None:
            return
        if _post_constraint(bin_c, trail):
            yield None


def fd_element(index, lst, value, trail: Trail):
    """element(Index, List, Value) — Value is the Index-th element of List (1-based).

    Uses arc-consistency propagation via ElementConstraint when index is a Var.
    """
    lst = deref(lst)
    if not isinstance(lst, list):
        return

    index = deref(index)
    value = deref(value)
    # Units: the list elements and the value share one dimension; the
    # index is a plain position.
    both = _units_strip_list(list(lst) + [value], "element/3", trail)
    lst, value = both[:-1], both[-1]
    n = len(lst)

    if isinstance(index, int):
        # Ground index: direct lookup
        if 1 <= index <= n:
            elem = deref(lst[index - 1])
            if unify(value, elem, trail):
                yield None
        return

    if not is_var(index):
        return

    # Index is a variable: bound it to the valid positions [1, n] up front.
    # A bare _ensure_fd would install the default unbounded (-inf, inf)
    # domain, which defeats ElementConstraint's lazy [1, n] initialisation
    # (that only fires when the index has NO fd attr) and makes propagate's
    # domain_values() enumerate an unbounded domain → ValueError (A06-F005).
    idx_state = get_attr(index, FD_KEY)
    base_idx_d = domain_from_range(1, n)
    if idx_state is not None:
        base_idx_d = domain_intersection(idx_state.domain, base_idx_d)
    if not _narrow(index, base_idx_d, trail, deque()):
        return
    index = deref(index)
    if not is_var(index):
        # Narrowing bound the index (singleton [1, 1] when n == 1)
        item = deref(lst[index - 1])
        if unify(value, item, trail):
            yield None
        return
    if is_var(value):
        _ensure_fd(value, trail)

    constraint = ElementConstraint(index, tuple(lst), value)
    if not _post_constraint(constraint, trail):
        return

    # After propagation, enumerate remaining valid indices
    index = deref(index)
    if not is_var(index):
        # Fully grounded by propagation
        item = deref(lst[index - 1])
        if unify(value, item, trail):
            yield None
        return

    idx_state = get_attr(index, FD_KEY)
    if idx_state is None:
        return
    for i in domain_values(idx_state.domain):
        mark = trail.mark()
        if unify(index, i, trail):
            item = deref(lst[i - 1])
            if unify(value, item, trail):
                yield None
        trail.undo(mark)


def fd_circuit(vars_list, trail: Trail):
    """circuit(Vars) — Vars form a single Hamiltonian circuit.

    Vars[i] = j means the successor of node i+1 is node j (1-based indexing).
    Uses CircuitConstraint for sub-tour elimination during labeling.
    """
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        return
    # circuit/1's arguments are 1-based node INDICES — positions, not
    # measurements — so dimensioned material is refused BEFORE any strip
    # (one error code, no shadow created on the refusal path); a
    # dimensionless quantity is a plain position.
    if _units_flag_active():
        from clausal.logic.units_clp import plain_fields_or_unsupported  # noqa: PLC0415
        vars_list = plain_fields_or_unsupported(vars_list, "circuit/1")

    n = len(vars_list)
    if n == 0:
        return

    vars_deref = [deref(v) for v in vars_list]

    # Ensure all have FD domains
    for v in vars_deref:
        if is_var(v):
            _ensure_fd(v, trail)

    vars_tuple = tuple(vars_deref)
    constraint = CircuitConstraint(vars_tuple)
    if not _post_constraint(constraint, trail):
        return

    yield from label(vars_list, trail)


# ── Global constraints (Tier 1 + Tier 2) ───────────────────────────────────


class CumulativeConstraint(Constraint):
    """cumulative(Tasks, Capacity) — time-table filtering.

    Each task is (start_var, duration, resource).  At every time point the
    total resource consumption of overlapping tasks must not exceed *limit*.
    """
    __slots__ = ('tasks', 'limit')

    def __init__(self, tasks: tuple, limit):
        self.tasks = tasks   # tuple of (start_var, duration, resource)
        self.limit = limit
        vars_ = []
        for start, _dur, _res in tasks:
            _collect_vars_from(start, vars_)
        _collect_vars_from(limit, vars_)
        super().__init__(tuple(vars_))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        limit_val = deref(self.limit)
        if isinstance(limit_val, int):
            cap = limit_val
        elif is_var(limit_val):
            st = get_attr(limit_val, FD_KEY)
            if st is None:
                return True  # can't propagate yet
            cap = domain_max(st.domain)
        else:
            return True

        tasks_info = []
        for start, dur, res in self.tasks:
            s = deref(start)
            d = dur if isinstance(dur, int) else deref(dur)
            r = res if isinstance(res, int) else deref(res)
            if not isinstance(d, int) or not isinstance(r, int):
                return True  # can't propagate non-ground durations/resources
            if d <= 0 or r <= 0:
                continue  # zero-duration or zero-resource tasks are no-ops
            if isinstance(s, int):
                s_lo = s_hi = s
            elif is_var(s):
                st = get_attr(s, FD_KEY)
                if st is None:
                    st = _ensure_fd(s, trail)
                s_lo = domain_min(st.domain)
                s_hi = domain_max(st.domain)
            else:
                return True
            tasks_info.append((start, s, s_lo, s_hi, d, r))

        if not tasks_info:
            return True

        # Time-table filtering: build compulsory parts and check/filter
        for i, (start_i, si, si_lo, si_hi, di, ri) in enumerate(tasks_info):
            if not is_var(deref(start_i)):
                continue
            si = deref(start_i)
            if not is_var(si):
                continue
            state_i = get_attr(si, FD_KEY)
            if state_i is None:
                continue

            new_domain = state_i.domain
            changed = False

            # For each possible start time of task i, check if placing it there
            # would exceed capacity at any time point (using compulsory parts
            # of other tasks).
            for t_lo, t_hi in state_i.domain:
                if t_lo == _NEG_INF or t_hi == _POS_INF:
                    continue  # skip unbounded intervals
                for t in range(int(t_lo), int(t_hi) + 1):
                    # Check resource usage at each time point in [t, t+di-1]
                    feasible = True
                    for tp in range(t, t + di):
                        usage = ri  # this task's usage
                        for j, (start_j, sj, sj_lo, sj_hi, dj, rj) in enumerate(tasks_info):
                            if j == i:
                                continue
                            # Compulsory part of task j: [sj_hi, sj_lo + dj - 1]
                            cp_start = sj_hi
                            cp_end = sj_lo + dj - 1
                            if cp_start <= tp <= cp_end:
                                usage += rj
                        if usage > cap:
                            feasible = False
                            break
                    if not feasible:
                        new_domain = domain_remove(new_domain, t)
                        changed = True

            if changed:
                if not _narrow_if_changed(si, new_domain, trail, queue):
                    return False
                # Refresh this task's snapshot so tasks processed LATER in
                # this same pass see the narrowed compulsory part.  With the
                # stale bounds kept, each pass filtered against pre-pass
                # state — weaker per-pass filtering, extra AC-3 iterations
                # to converge (cross_cutting_issues.md item 3; not unsound).
                tasks_info[i] = (
                    start_i, si,
                    domain_min(new_domain), domain_max(new_domain), di, ri,
                )

        # Final check: at each time point where all tasks have compulsory parts,
        # verify total doesn't exceed capacity
        for i, (start_i, si, si_lo, si_hi, di, ri) in enumerate(tasks_info):
            cp_start = si_hi
            cp_end = si_lo + di - 1
            if cp_start > cp_end:
                continue  # no compulsory part
            if cp_start == _POS_INF or cp_end == _NEG_INF:
                continue
            for tp in range(int(cp_start), int(cp_end) + 1):
                usage = 0
                for j, (start_j, sj, sj_lo, sj_hi, dj, rj) in enumerate(tasks_info):
                    cp_s = sj_hi
                    cp_e = sj_lo + dj - 1
                    if cp_s <= tp <= cp_e:
                        usage += rj
                if usage > cap:
                    return False

        return True


class GlobalCardinalityConstraint(Constraint):
    """global_cardinality(Vars, Pairs) — counting constraint.

    Pairs is a tuple of (value, count) pairs.  Decomposes into: for each
    value, the number of vars equal to that value == count.
    """
    __slots__ = ('gc_vars', 'pairs')

    def __init__(self, gc_vars: tuple, pairs: tuple):
        self.gc_vars = gc_vars
        self.pairs = pairs  # tuple of (value, count)
        vars_ = list(gc_vars)
        for _val, cnt in pairs:
            if is_var(cnt):
                vars_.append(cnt)
        super().__init__(tuple(v for v in vars_ if is_var(deref(v))))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        for value, count in self.pairs:
            count = deref(count)
            count_is_var = is_var(count)
            if not count_is_var and not isinstance(count, int):
                continue  # malformed count — leave pending

            # Re-deref all vars each iteration (prior narrowing may have
            # bound some vars, making the old references stale).
            vars_ = [deref(v) for v in self.gc_vars]

            if not count_is_var and count == 0:
                # Remove this value from all variable domains
                for v in vars_:
                    if is_var(v):
                        state = get_attr(v, FD_KEY)
                        if state is not None and domain_contains(state.domain, value):
                            new_d = domain_remove(state.domain, value)
                            if not _narrow_if_changed(v, new_d, trail, queue):
                                return False
                continue

            # Count how many vars are definitely this value (ground)
            # and how many could possibly be this value
            definite = 0
            possible = 0
            possible_vars = []
            for v in vars_:
                if isinstance(v, int):
                    if v == value:
                        definite += 1
                elif is_var(v):
                    state = get_attr(v, FD_KEY)
                    if state is None or domain_contains(state.domain, value):
                        possible += 1
                        possible_vars.append(v)

            if count_is_var:
                # Bound the count variable to [definite, definite + possible]
                # (A06-F013): definite occurrences are locked in, and at most
                # `possible` more vars can still take this value.  A singleton
                # (possible == 0) binds the count; the value-level narrowing
                # then runs on the next pass via the int-count branch once the
                # count deref's to an int.  Intersect with any existing count
                # domain so a user-posted bound still constrains.
                new_cnt_d = domain_from_range(definite, definite + possible)
                cnt_state = get_attr(count, FD_KEY)
                if cnt_state is not None:
                    new_cnt_d = domain_intersection(cnt_state.domain, new_cnt_d)
                if not new_cnt_d:
                    return False
                if not _narrow_if_changed(count, new_cnt_d, trail, queue):
                    return False
                continue

            if definite > count:
                return False  # too many already assigned
            if definite + possible < count:
                return False  # not enough vars can take this value

            if definite == count:
                # All remaining must NOT be this value
                for v in possible_vars:
                    v = deref(v)
                    if not is_var(v):
                        continue
                    state = get_attr(v, FD_KEY)
                    if state is not None and domain_contains(state.domain, value):
                        new_d = domain_remove(state.domain, value)
                        if not _narrow_if_changed(v, new_d, trail, queue):
                            return False

            elif definite + possible == count:
                # All possible vars MUST be this value
                for v in possible_vars:
                    v = deref(v)
                    if not is_var(v):
                        continue
                    new_d = domain_from_range(value, value)
                    if not _narrow_if_changed(v, new_d, trail, queue):
                        return False

        return True


class TuplesInConstraint(Constraint):
    """tuples_in(Tuples, Relation) — table constraint.

    Each tuple of vars must match one of the allowed tuples in the relation.
    Uses simple tabular reduction: remove values from domains that don't
    appear in any supporting tuple.
    """
    __slots__ = ('tuple_vars', 'relation')

    def __init__(self, tuple_vars: tuple, relation: tuple):
        self.tuple_vars = tuple_vars   # tuple of vars
        self.relation = relation       # tuple of allowed value-tuples
        super().__init__(tuple(v for v in tuple_vars if is_var(deref(v))))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        n = len(self.tuple_vars)
        vars_ = [deref(v) for v in self.tuple_vars]

        # Filter relation to only tuples consistent with current domains
        valid_tuples = []
        for tup in self.relation:
            if len(tup) != n:
                continue
            ok = True
            for k, v in enumerate(vars_):
                val = tup[k]
                if isinstance(v, int):
                    if v != val:
                        ok = False
                        break
                elif is_var(v):
                    state = get_attr(v, FD_KEY)
                    if state is not None and not domain_contains(state.domain, val):
                        ok = False
                        break
            if ok:
                valid_tuples.append(tup)

        if not valid_tuples:
            return False  # no valid tuple exists

        # For each variable position, compute the set of allowed values
        for k, v in enumerate(vars_):
            if not is_var(v):
                continue
            allowed = set()
            for tup in valid_tuples:
                allowed.add(tup[k])

            state = get_attr(v, FD_KEY)
            if state is None:
                continue

            # Build domain from allowed values and intersect with current
            if not allowed:
                return False
            allowed_d = _domain_from_set(allowed)
            new_d = domain_intersection(state.domain, allowed_d)
            if new_d != state.domain:
                if not _narrow_if_changed(v, new_d, trail, queue):
                    return False

        return True


class ZcompareConstraint(Constraint):
    """zcompare(Order, X, Y) — reified three-way comparison.

    Order is unified with the ATOM ``<``, ``=`` or ``>`` depending on X vs Y
    (spec §6.4: the ISO order names are atoms, not strings).
    """
    __slots__ = ('order', 'x', 'y')

    def __init__(self, order, x, y):
        self.order = order
        self.x = x
        self.y = y
        # Only track FD vars (x, y), not the order var (which is bound to an atom)
        vars_ = []
        _collect_vars_from(x, vars_)
        _collect_vars_from(y, vars_)
        super().__init__(tuple(vars_))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        x = deref(self.x)
        y = deref(self.y)
        order = deref(self.order)

        xd = _expr_domain(x, trail)
        yd = _expr_domain(y, trail)
        if not xd or not yd:
            return False

        x_lo, x_hi = domain_min(xd), domain_max(xd)
        y_lo, y_hi = domain_min(yd), domain_max(yd)

        # Order is an ATOM when ground (§6.4).  A STRING here can only come
        # from a later ``unify(Order, "<")``, which binds the order var to a
        # term that is not an order name at all: the constraint is then
        # unsatisfiable and fails through the tail below, rather than raising
        # out of the middle of a wake-up hook.  ``zcompare/3`` itself, the
        # position a program actually writes, raises.
        if is_atom(order):
            order = spelling(order)
            # Order is ground — enforce the relation
            if order == '<':
                if is_var(x):
                    new_xd = domain_remove_above(xd, y_hi - 1)
                    if not new_xd:
                        return False
                    if not _narrow_if_changed(x, new_xd, trail, queue):
                        return False
                if is_var(y):
                    new_yd = domain_remove_below(yd, x_lo + 1)
                    if not new_yd:
                        return False
                    if not _narrow_if_changed(y, new_yd, trail, queue):
                        return False
                # Check feasibility
                xd2 = _expr_domain(deref(self.x), trail)
                yd2 = _expr_domain(deref(self.y), trail)
                return bool(xd2) and bool(yd2) and domain_min(xd2) < domain_max(yd2)
            elif order == '=':
                inter = domain_intersection(xd, yd)
                if not inter:
                    return False
                if is_var(x):
                    if not _narrow_if_changed(x, inter, trail, queue):
                        return False
                if is_var(y):
                    if not _narrow_if_changed(y, inter, trail, queue):
                        return False
                return True
            elif order == '>':
                if is_var(x):
                    new_xd = domain_remove_below(xd, y_lo + 1)
                    if not new_xd:
                        return False
                    if not _narrow_if_changed(x, new_xd, trail, queue):
                        return False
                if is_var(y):
                    new_yd = domain_remove_above(yd, x_hi - 1)
                    if not new_yd:
                        return False
                    if not _narrow_if_changed(y, new_yd, trail, queue):
                        return False
                xd2 = _expr_domain(deref(self.x), trail)
                yd2 = _expr_domain(deref(self.y), trail)
                return bool(xd2) and bool(yd2) and domain_max(xd2) > domain_min(yd2)
            else:
                return False  # invalid order atom
        elif is_var(order):
            # Aliased operands: X vs X is always equal (A06-F012b).
            if x is y:
                return unify(order, mint('='), trail)
            # Determine order from domains
            if x_hi < y_lo:
                return unify(order, mint('<'), trail)
            elif x_lo > y_hi:
                return unify(order, mint('>'), trail)
            elif x_lo == x_hi and y_lo == y_hi and x_lo == y_lo:
                return unify(order, mint('='), trail)
            # Otherwise undetermined — keep constraint
            return True
        else:
            return False


# ── Public API for global constraints ──────────────────────────────────────


def cumulative(tasks, limit, trail: Trail) -> bool:
    """Post cumulative constraint.

    *tasks* is a list of (start, duration, resource) tuples.
    *limit* is the resource capacity (int or Var).
    """
    if not tasks:
        return True  # trivially satisfied
    # Units: not routed (two dimensions, time and resource, need their own
    # rule) and durations/resources never get solver state, so the
    # reattachment net would not fire either — refuse loudly here instead.
    # Per task, so a malformed task still fails the unpack below as before.
    if _units_flag_active():
        from clausal.logic.units_clp import plain_fields_or_unsupported  # noqa: PLC0415
        tasks = [tuple(plain_fields_or_unsupported(list(task), "cumulative/2"))
                 for task in tasks]
        limit = plain_fields_or_unsupported([limit], "cumulative/2")[0]

    task_tuples = []
    for start, dur, res in tasks:
        s = deref(start)
        d = dur if isinstance(dur, int) else deref(dur)
        r = res if isinstance(res, int) else deref(res)
        if is_var(s):
            _ensure_fd(s, trail)
        task_tuples.append((s, d, r))

    constraint = CumulativeConstraint(tuple(task_tuples), limit)
    return _post_constraint(constraint, trail)


def global_cardinality(vars_list, pairs, trail: Trail) -> bool:
    """Post global_cardinality constraint.

    *vars_list* is a list of variables/integers.
    *pairs* is a list of (value, count) pairs.
    """
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        return False
    # Units: the vars and the pair KEYS share one dimension (a key is a
    # value the vars may take), so they are stripped together.
    keys = [val for val, _ in pairs]
    both = _units_strip_list(list(vars_list) + keys, "global_cardinality/2", trail)
    vars_list, keys = both[:len(vars_list)], both[len(vars_list):]
    counts = [cnt for _, cnt in pairs]
    if _units_flag_active():
        # Counts are cardinalities, not measurements: a dimensioned count is
        # refused, a dimensionless quantity becomes a plain int (the
        # constraint would otherwise skip a non-int count silently).
        from clausal.logic.units_clp import plain_fields_or_unsupported  # noqa: PLC0415
        counts = plain_fields_or_unsupported(counts, "global_cardinality/2")
    pairs = list(zip(keys, counts))

    vars_deref = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            _ensure_fd(v, trail)
        vars_deref.append(v)

    pairs_deref = []
    for val, cnt in pairs:
        cnt = deref(cnt)
        pairs_deref.append((val, cnt))

    constraint = GlobalCardinalityConstraint(tuple(vars_deref), tuple(pairs_deref))
    return _post_constraint(constraint, trail)


def chain(vars_list, relation, trail: Trail) -> bool:
    """Post chain constraint: consecutive pairs satisfy *relation*.

    *relation* is one of "lt", "gt", "le", "ge", "eq", "ne".
    Decomposes into pairwise constraints.
    """
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        return False
    if len(vars_list) <= 1:
        return True  # trivially satisfied
    _rel_to_fn = {
        "lt": fd_lt, "gt": fd_gt, "le": fd_le, "ge": fd_ge,
        "eq": fd_eq, "ne": fd_ne,
    }
    post_fn = _rel_to_fn.get(relation)
    if post_fn is None:
        return False
    # Units after the relation check, so a bad relation still wins. No
    # whole-units guard: chain decomposes into the comparators, which take
    # rationals and reals (X < 10.50(euro) works, so must chain).
    if _strip_list_for_solver is None:
        _ensure_units_imports()
    vars_list, _ = _strip_list_for_solver(vars_list, "chain/2", trail)

    for i in range(len(vars_list) - 1):
        a = deref(vars_list[i])
        b = deref(vars_list[i + 1])
        # No _ensure_fd here: each comparator picks its own solver, as it
        # does when called directly. Pre-posting an unbounded FD domain made
        # a rational neighbour overflow in the FD -> CLP(Q) promotion
        # (todo/done/chain-rational-operand-fd-promotion-overflow-2026-09-12.md).
        if not post_fn(a, b, trail):
            return False
    return True


def tuples_in(tuples_list, relation, trail: Trail) -> bool:
    """Post tuples_in constraint.

    *tuples_list* is a list of variable-tuples (each a list).
    *relation* is a list of allowed value-tuples (each a tuple).
    """
    if not relation:
        return False  # empty relation — no tuple can match

    if _units_flag_active():
        from clausal.logic.units_clp import plain_fields_or_unsupported  # noqa: PLC0415
        relation = [plain_fields_or_unsupported(list(r), "tuples_in/2") for r in relation]
    relation_tuple = tuple(tuple(r) for r in relation)

    for tup in tuples_list:
        tup = deref(tup)
        if isinstance(tup, list):
            # Not routed through the units side channel: a row is one var
            # per COLUMN and columns carry different dimensions, so the
            # shared-dimension list form does not fit. Dimensioned material
            # is refused up front (a ground Quantity position would
            # otherwise be SKIPPED by the constraint's int/var tests and the
            # column silently dropped); a united var also trips the
            # reattachment net. Dimensionless quantities are plain numbers.
            if _units_flag_active():
                from clausal.logic.units_clp import plain_fields_or_unsupported  # noqa: PLC0415
                tup = plain_fields_or_unsupported(list(tup), "tuples_in/2")
            vars_ = []
            for v in tup:
                v = deref(v)
                if is_var(v):
                    _ensure_fd(v, trail)
                vars_.append(v)
            constraint = TuplesInConstraint(tuple(vars_), relation_tuple)
            if not _post_constraint(constraint, trail):
                return False
        else:
            return False
    return True


# Wake-up attr key for the zcompare order variable.  The order var is bound
# to an ORDER ATOM (``<`` / ``=`` / ``>``), not an int, so the FD hook is the
# wrong vehicle; this lightweight key re-runs the pending
# ZcompareConstraint(s) when the order var is later ground (A06-F012a).
ZCMP_KEY = "zcompare_wakeup"


def _zcompare_hook(attr_value, bound_to, trail: Trail) -> bool:
    """Fire the pending zcompare constraints when the order var is bound.

    *attr_value* is the list of ZcompareConstraint objects waiting on this
    order var.  Hooks run after the binding is committed, so each
    constraint's propagate() sees the now-ground order ATOM.
    """
    bound_to = deref(bound_to)
    if is_var(bound_to):
        # Order unified with another var — carry the wake-up list across.
        existing = get_attr(bound_to, ZCMP_KEY)
        merged = attr_value if existing is None else existing + attr_value
        put_attr(bound_to, ZCMP_KEY, merged, trail)
        return True
    queue: deque = deque()
    for constraint in attr_value:
        if not constraint.propagate(trail, queue):
            return False
    return propagate(queue, trail)


register_attr_hook(ZCMP_KEY, _zcompare_hook)


def zcompare(order, x, y, trail: Trail) -> bool:
    """Post zcompare/3 constraint.

    *order* is the ORDER ATOM ``<``, ``=`` or ``>`` (spec §6.4) — read by
    spelling when it is ground, minted when this posts the answer.  A plain
    ``str`` is a STRING, not a name, and raises ``type_error(atom, …)``.
    """
    order = deref(order)
    x = deref(x)
    y = deref(y)
    # Read (and validate) the Order BEFORE anything else, including the
    # ground/ground fast path below.  Fix round 1: with the check further
    # down, ``zcompare("<", 1, 5)`` took the fast path and merely FAILED (the
    # string does not unify with the order atom) while ``zcompare("<", X, Y)``
    # raised — one refusal for the same mistake, decided by the operands.
    # It also means the refusal lands before ``_ensure_fd`` has touched the
    # trail.
    order_name = _op_spelling(order, "zcompare/3")
    # Units side channel after the Order check, so a bad Order still wins.
    stripped = _units_strip(x, y, "zcompare/3", trail)
    if stripped is not None:
        sx, sy = stripped
        if order_name is None and (is_var(sx) or is_var(sy)):
            # An unbound Order with a variable operand posts
            # ZcompareConstraint over integer domains (no comparator to
            # delegate to), so the operands must be whole units, as in every
            # other integer-domain builtin. A ground pair is decided below
            # whatever its magnitudes.
            sx, sy = _whole_units_only([x, y], [sx, sy], "zcompare/3")
        x, y = sx, sy

    # If both x and y are ground numbers, just determine the order directly.
    # The answer is unified against *order*, which is either an unbound Var
    # (it gets bound) or the atom the caller already wrote (it is checked).
    if (isinstance(x, (int, Fraction, float)) and isinstance(y, (int, Fraction, float))
            and not isinstance(x, bool) and not isinstance(y, bool)):
        if x < y:
            return unify(order, mint('<'), trail)
        elif x > y:
            return unify(order, mint('>'), trail)
        else:
            return unify(order, mint('='), trail)

    # If order is ground, use it to constrain x and y
    if order_name is not None:
        if order_name == '<':
            return fd_lt(x, y, trail, _units_done=stripped is not None)
        elif order_name == '>':
            return fd_gt(x, y, trail, _units_done=stripped is not None)
        elif order_name == '=':
            return fd_eq(x, y, trail, _units_done=stripped is not None)
        else:
            return False

    # General case: post constraint (order is a Var, x/y may be vars).
    # FD state goes on x/y HERE, not before the ground-Order delegation
    # above: the comparators choose their own solver, and a pre-posted
    # unbounded FD domain overflowed the FD -> CLP(Q) promotion for a
    # rational operand (same defect as chain/2).
    if is_var(x):
        _ensure_fd(x, trail)
    if is_var(y):
        _ensure_fd(y, trail)
    # Don't put FD on order — it will be bound to an order ATOM
    constraint = ZcompareConstraint(order, x, y)
    # Attach constraint only to FD vars (x and y), not order
    for v in constraint.vars:
        v = deref(v)
        if is_var(v) and v is not deref(order):
            _add_constraint(v, constraint, trail)
    # Attach an atom-binding wake-up to the order var so that binding it
    # AFTER posting re-fires the constraint and narrows x/y (A06-F012a).
    od = deref(order)
    if is_var(od):
        existing = get_attr(od, ZCMP_KEY)
        put_attr(od, ZCMP_KEY,
                 [constraint] if existing is None else existing + [constraint],
                 trail)
    queue: deque = deque()
    if not constraint.propagate(trail, queue):
        return False
    return propagate(queue, trail)


# ── C-accelerated propagation (with Python fallback) ─────────────────────────
# If the C extension is available, its versions silently replace the Python ones.

class _NoValue:
    """What the C ``!=`` propagator is handed for an expression with no value
    (see :func:`_no_value_in_propagation`): it differs from nothing and
    equals nothing, so the C both-ground arm's ``lv != rv`` is False and the
    constraint FAILS -- ruling Q14 (2026-09-28), with no C change."""
    __slots__ = ()

    def __eq__(self, other):
        return False

    def __ne__(self, other):
        return False

    __hash__ = object.__hash__


_NO_VALUE_FOR_C = _NoValue()


def _eval_ground_for_c(x):
    """``_eval_ground`` as the C propagator module sees it (it binds the
    module attribute ``_eval_ground`` once, at its import): an expression with
    no value is :data:`_NO_VALUE_FOR_C` instead of an error."""
    try:
        return _eval_ground(x)
    except _LogicException as exc:
        if _no_value_in_propagation(exc):
            return _NO_VALUE_FOR_C
        raise


_USE_C_PROPAGATE = False
_ensure_exc_imports()

#: The cells as a CLP post evaluates them: :data:`EVALUABLE` with ``/``
#: RATIONAL (ruling Q15, 2026-09-28; see ``_ensure_term_imports``).
from clausal.logic.exact_arith import exact_div as _exact_div_cell  # noqa: E402
_CLP_CELL_EVALUABLE = {**_EVALUABLE, ("/", 2): _exact_div_cell}
_eval_ground_py = _eval_ground
_eval_ground = _eval_ground_for_c        # what the C init binds (see above)
try:
    from clausal.logic._clpfd_propagate import (
        FDVar as _C_FDVar,
        EqConstraint as _C_EqConstraint,
        NeConstraint as _C_NeConstraint,
        LtConstraint as _C_LtConstraint,
        LeConstraint as _C_LeConstraint,
        AllDiffConstraint as _C_AllDiffConstraint,
        SumConstraint as _C_SumConstraint,
        ScalarProductConstraint as _C_ScalarProductConstraint,
        _ensure_fd as _c_ensure_fd,
        _narrow as _c_narrow,
        _narrow_if_changed as _c_narrow_if_changed,
        propagate as _c_propagate,
        _add_constraint as _c_add_constraint,
        _post_constraint as _c_post_constraint,
        fd_eq as _c_fd_eq,
        fd_ne as _c_fd_ne,
        fd_lt as _c_fd_lt,
        fd_le as _c_fd_le,
        _fd_hook as _c_fd_hook,
    )
    _USE_C_PROPAGATE = True
except ImportError:
    pass
finally:
    _eval_ground = _eval_ground_py

if _USE_C_PROPAGATE:
    FDVar = _C_FDVar
    EqConstraint = _C_EqConstraint
    NeConstraint = _C_NeConstraint
    LtConstraint = _C_LtConstraint
    LeConstraint = _C_LeConstraint
    AllDiffConstraint = _C_AllDiffConstraint
    SumConstraint = _C_SumConstraint
    ScalarProductConstraint = _C_ScalarProductConstraint
    _ensure_fd = _c_ensure_fd
    _narrow = _c_narrow
    _narrow_if_changed = _c_narrow_if_changed
    propagate = _c_propagate
    _add_constraint = _c_add_constraint
    _post_constraint = _c_post_constraint

    def fd_eq(l, r, trail, _c_impl=_c_fd_eq, *, _units_done=False):
        if type(l) is int and type(r) is int:
            return l == r          # same fast path as the Python twin, ahead of the side channel
        stripped = None if _units_done else _units_strip(l, r, "(==)/2", trail)
        if stripped is not None:
            l, r = stripped
        # the ground-number VALUE comparison, ahead of the C impl's mixed
        # rational/real refusal (see _ground_number_pair).  ``_resolve`` folds
        # a GROUND expression tree to its number first, as the Python twin
        # does: ``X / Y == 3.5`` arrives with the tree on the left, and
        # without the fold it went straight to the C impl and its refusal
        # (the harness lane's probe, 2026-09-17 -- the shape this fix
        # claimed to close, and had not).
        _dl, _dr = _resolve(deref(l)), _resolve(deref(r))
        if _ground_number_pair(_dl, _dr):
            return _dl == _dr
        # ruling R9 A1: go on with the resolved operands (a ground cell has
        # folded to its number) and any arithmetic cell left as its node,
        # exactly as the Python twin does
        l, r = _cells_as_nodes(_dl, _dr)
        # A12-F002: the C fd_eq does not type-check operands, so guard here
        # (cheap: only touches the two derefs) before delegating.
        _reject_nonnumeric_eq(l, r)
        # The C impl's ground fallback is Python equality, same as the Python
        # twin's — so the chars-model arm has to sit in front of it here too,
        # or `==` answers differently depending on which impl is loaded.
        # the ground fallback sees a bound variable inside a compound as
        # its value (see _walk_compound); the C impl compares raw objects
        l, r = _walk_compound(deref(l)), _walk_compound(deref(r))
        _eq = _text_list_eq(l, r)
        if _eq is not None:
            return _eq
        return _c_impl(l, r, trail)

    def fd_ne(l, r, trail, _c_impl=_c_fd_ne, *, _units_done=False):
        if type(l) is int and type(r) is int:
            return l != r          # same fast path as the Python twin, ahead of the side channel
        stripped = None if _units_done else _units_strip(l, r, "(!=)/2", trail)
        if stripped is not None:
            l, r = stripped
        # the ground-number VALUE comparison, ahead of the C impl's mixed
        # rational/real refusal (see _ground_number_pair).  ``_resolve`` folds
        # a GROUND expression tree to its number first, as the Python twin
        # does: ``X / Y == 3.5`` arrives with the tree on the left, and
        # without the fold it went straight to the C impl and its refusal
        # (the harness lane's probe, 2026-09-17 -- the shape this fix
        # claimed to close, and had not).
        _dl, _dr = _resolve(deref(l)), _resolve(deref(r))
        if _ground_number_pair(_dl, _dr):
            return _dl != _dr
        # ruling R9 A1: go on with the resolved operands (a ground cell has
        # folded to its number) and any arithmetic cell left as its node,
        # exactly as the Python twin does
        l, r = _cells_as_nodes(_dl, _dr)
        # Same broken-var guard as fd_eq above; the C impl posts unchecked.
        _reject_nonnumeric_eq(l, r, "(!=)/2")
        l, r = _walk_compound(deref(l)), _walk_compound(deref(r))
        _eq = _text_list_eq(l, r)
        if _eq is not None:
            return not _eq
        return _c_impl(l, r, trail)

    def fd_lt(l, r, trail, _c_impl=_c_fd_lt, *, _units_done=False):
        if type(l) is int and type(r) is int:
            return l < r          # same fast path as the Python twin, ahead of the side channel
        stripped = None if _units_done else _units_strip(l, r, "(<)/2", trail)
        if stripped is not None:
            l, r = stripped
        # the ground-number VALUE comparison, ahead of the C impl's mixed
        # rational/real refusal (see _ground_number_pair).  ``_resolve`` folds
        # a GROUND expression tree to its number first, as the Python twin
        # does: ``X / Y == 3.5`` arrives with the tree on the left, and
        # without the fold it went straight to the C impl and its refusal
        # (the harness lane's probe, 2026-09-17 -- the shape this fix
        # claimed to close, and had not).
        _dl, _dr = _resolve(deref(l)), _resolve(deref(r))
        if _ground_number_pair(_dl, _dr):
            return _dl < _dr
        # ruling R9 A1: go on with the resolved operands (a ground cell has
        # folded to its number) and any arithmetic cell left as its node,
        # exactly as the Python twin does
        l, r = _cells_as_nodes(_dl, _dr)
        # The C fd_lt does no clean type-checking: an incomparable ground
        # comparison escapes as a raw Python TypeError. Convert those to a
        # catchable type_error, while preserving the legitimate mixed
        # CLP(Q)/CLP(R) TypeError and any error involving an unbound operand.
        # A var vs a ground non-numeric would post a broken constraint, so
        # guard before delegating (like fd_eq above).
        _reject_nonnumeric_order(l, r, "(<)/2")
        try:
            return _c_impl(l, r, trail)
        except TypeError:
            dl, dr = deref(l), deref(r)
            if is_var(dl) or is_var(dr):
                raise
            if _any_rational(dl, dr) and _any_real(dl, dr):
                raise
            raise _incomparable_order_error(dr, "(<)/2")

    def fd_le(l, r, trail, _c_impl=_c_fd_le, *, _units_done=False):
        if type(l) is int and type(r) is int:
            return l <= r          # same fast path as the Python twin, ahead of the side channel
        stripped = None if _units_done else _units_strip(l, r, "(=<)/2", trail)
        if stripped is not None:
            l, r = stripped
        # the ground-number VALUE comparison, ahead of the C impl's mixed
        # rational/real refusal (see _ground_number_pair).  ``_resolve`` folds
        # a GROUND expression tree to its number first, as the Python twin
        # does: ``X / Y == 3.5`` arrives with the tree on the left, and
        # without the fold it went straight to the C impl and its refusal
        # (the harness lane's probe, 2026-09-17 -- the shape this fix
        # claimed to close, and had not).
        _dl, _dr = _resolve(deref(l)), _resolve(deref(r))
        if _ground_number_pair(_dl, _dr):
            return _dl <= _dr
        # ruling R9 A1: go on with the resolved operands (a ground cell has
        # folded to its number) and any arithmetic cell left as its node,
        # exactly as the Python twin does
        l, r = _cells_as_nodes(_dl, _dr)
        _reject_nonnumeric_order(l, r, "(=<)/2")
        try:
            return _c_impl(l, r, trail)
        except TypeError:
            dl, dr = deref(l), deref(r)
            if is_var(dl) or is_var(dr):
                raise
            if _any_rational(dl, dr) and _any_real(dl, dr):
                raise
            raise _incomparable_order_error(dr, "(=<)/2")

    # Re-register the C fd_hook
    register_attr_hook(FD_KEY, _c_fd_hook)


# ── Ruling Q14 (2026-09-28): no value means no solutions ─────────────────────
#
# ``X == 1 // 0`` -- Scryer's ``X #= 1 // 0`` -- FAILS: "(#=)/2 is a relation:
# failure means that there are no solutions for these arguments" (Markus
# Triska).  In EVERY goal order: the ground post fails here, and a divisor
# (or a '^' exponent) that reaches a no-value while propagating empties the
# domain (``_expr_domain``) or fails the ``!=`` arm (``_eval_propagating``,
# ``_eval_ground_for_c``).  Plain arithmetic -- is/2, the ISO comparisons,
# eval_/2 -- keeps raising evaluation_error(zero_divisor).

def _relation_fails_without_value(post):
    def wrapped(l, r, trail, *args, **kwargs):
        try:
            return post(l, r, trail, *args, **kwargs)
        except _LogicException as exc:
            if _no_value_in_propagation(exc):
                return False
            raise
    wrapped.__name__ = post.__name__
    wrapped.__doc__ = post.__doc__
    wrapped.__wrapped__ = post
    return wrapped


fd_eq = _relation_fails_without_value(fd_eq)
fd_ne = _relation_fails_without_value(fd_ne)
fd_lt = _relation_fails_without_value(fd_lt)
fd_le = _relation_fails_without_value(fd_le)
