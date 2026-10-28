"""Propagators for the non-linear CLP(Z) operators: ``*`` of two unknowns,
``//``, ``div``, ``mod``, ``rem``, ``^``, ``min`` and ``max``.

A comparison posted over one of these used to be a check over the
expression TREE (``EqConstraint``/``LeConstraint``), which narrows only a
side that is a bare variable: ``R*T #= 14, T = 7`` left R unbound, ``X #=
Y mod 3`` left X in inf..sup and ``5 #= 13 // Y`` never looked at Y.  clpz
lifts each such sub-expression into a fresh variable with a propagator of
its own (``ptimes``, ``ptzdiv``, ``pdiv``, ``pmod``, ``prem``, ``pexp``,
``pmax``, ``pmin``) and posts the comparison over it; the posts in
``clpfd.py`` now do the same (``_lift_cells``), and the propagators live
here.

Each propagator narrows in every direction (the result from the operands,
each operand from the result and the other operand), runs to its own
fixpoint, and -- while the operands' domains are finite and small
(``_ENUM_LIMIT`` pairs) -- enumerates the pairs, which makes it domain
consistent.  Their bounds rules are the ones clpz uses, or stronger; every
rule is sound for the integers (each says only what no solution violates).

A pair with no value (a zero divisor, ``2^(-1)``) has no solution: the
relation fails rather than raising (ruling Q14, 2026-09-28; Scryer's ``X #=
1 // 0`` fails), and a divisor's 0 is removed from its domain at once.
"""

from __future__ import annotations

import math
from collections import deque
from fractions import Fraction

from clausal.logic.variables import Trail, deref, is_var

INF = float("inf")
NINF = float("-inf")

#: Largest number of operand pairs a propagator enumerates.
_ENUM_LIMIT = 1024
#: Largest exponent a power's bounds are computed for (beyond it the
#: bound is taken as infinite rather than built as a huge integer).
_POW_EXP_LIMIT = 4096

_cf = None


def _clpfd():
    global _cf
    if _cf is None:
        from clausal.logic import clpfd  # noqa: PLC0415
        _cf = clpfd
    return _cf


def _rng(lo, hi):
    if lo != lo or hi != hi or lo > hi:
        return ()
    return ((lo, hi),)


def _inter(d1, d2):
    return _clpfd().domain_intersection(d1, d2)


def _union(*ds):
    return _clpfd()._domain_union([d for d in ds if d])


def _lo(d):
    return d[0][0]


def _hi(d):
    return d[-1][1]


def _finite(d):
    return d[0][0] != NINF and d[-1][1] != INF


def _single(d):
    if len(d) == 1 and d[0][0] == d[0][1]:
        return d[0][0]
    return None


def _contains(d, v):
    for lo, hi in d:
        if lo <= v <= hi:
            return True
        if v < lo:
            return False
    return False


def _remove(d, v):
    return _clpfd().domain_remove(d, v)


def _size(d):
    n = 0
    for lo, hi in d:
        if lo == NINF or hi == INF:
            return INF
        n += hi - lo + 1
    return n


def _values(d):
    for lo, hi in d:
        yield from range(lo, hi + 1)


def _pos(d):
    """The part of *d* above 0."""
    return _inter(d, ((1, INF),))


def _neg(d):
    """The part of *d* below 0."""
    return _inter(d, ((NINF, -1),))


def _mul(a, b):
    """``a * b`` over the extended integers, with 0 * inf = 0."""
    if a == 0 or b == 0:
        return 0
    return a * b


def _maxabs(d):
    return max(abs(_lo(d)), abs(_hi(d)))


def _ceil(x):
    if x == INF or x == NINF:
        return x
    if isinstance(x, Fraction):
        return math.ceil(x)
    return x


def _floor(x):
    if x == INF or x == NINF:
        return x
    if isinstance(x, Fraction):
        return math.floor(x)
    return x


def _q(a, b):
    """``a / b`` exactly over the extended integers (b != 0); None when
    both are infinite."""
    a_inf = a in (INF, NINF)
    b_inf = b in (INF, NINF)
    if a_inf and b_inf:
        return None
    if b_inf:
        return Fraction(0)
    if a_inf:
        return a if b > 0 else -a
    return Fraction(a, b)


def _iroot_floor(n, k):
    """floor(n ** (1/k)) for n >= 0."""
    if n < 2:
        return n
    x = 1 << ((n.bit_length() + k - 1) // k)
    while True:
        y = ((k - 1) * x + n // x ** (k - 1)) // k
        if y >= x:
            break
        x = y
    while x ** k > n:
        x -= 1
    while (x + 1) ** k <= n:
        x += 1
    return x


def _iroot_ceil(n, k):
    """ceil(n ** (1/k)) for n >= 0."""
    r = _iroot_floor(n, k)
    return r if r ** k == n else r + 1


def _ilog_floor(n, b):
    """floor(log_b(n)) for n >= 1, b >= 2."""
    e, p = 0, b
    while p <= n:
        p *= b
        e += 1
    return e


def _base():
    return _clpfd().Constraint


class NonlinearConstraint:
    """Shared machinery: ``Z = A op B`` (``self.z``, ``self.a``,
    ``self.b``).  A subclass gives ``_value(a, b)`` (an int, or None when
    the pair has no value) and ``_bounds(zd, ad, bd)`` (narrowed domains,
    or None on a wipeout)."""

    def _doms(self, trail):
        ed = _clpfd()._expr_domain
        return (ed(deref(self.z), trail), ed(deref(self.a), trail),
                ed(deref(self.b), trail))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        cf = _clpfd()
        for _round in range(64):
            z, a, b = deref(self.z), deref(self.a), deref(self.b)
            zd, ad, bd = self._doms(trail)
            if not (zd and ad and bd):
                return False
            av, bv = _single(ad), _single(bd)
            if av is not None and bv is not None:
                v = self._value(av, bv)
                if v is None or not _contains(zd, v):
                    return False
                if is_var(z):
                    return cf._narrow_if_changed(z, ((v, v),), trail, queue)
                return True
            res = self._bounds(zd, ad, bd)
            if res is None:
                return False
            nz, na, nb = res
            if not (nz and na and nb):
                return False
            if a is b:
                na = nb = _inter(na, nb)
            res = self._enumerate(z, a, b, nz, na, nb)
            if res is None:
                return False
            nz, na, nb = res
            changed = False
            for v, old, new in ((z, zd, nz), (a, ad, na), (b, bd, nb)):
                v = deref(v)
                if new != old and is_var(v):
                    if not cf._narrow_if_changed(v, new, trail, queue):
                        return False
                    changed = True
            if not changed:
                return True
        return True

    def _enumerate(self, z, a, b, zd, ad, bd):
        """Domain consistency while the operands are small and finite."""
        if not (_finite(ad) and _finite(bd)):
            return zd, ad, bd
        same_ab = a is b
        n = _size(ad) if same_ab else _size(ad) * _size(bd)
        if n > _ENUM_LIMIT or not self._enumerable(ad, bd):
            return zd, ad, bd
        z_is_a = z is a and is_var(z)
        z_is_b = z is b and is_var(z)
        img, sa, sb = set(), set(), set()
        pairs = ((x, x) for x in _values(ad)) if same_ab else (
            (x, y) for x in _values(ad) for y in _values(bd))
        for x, y in pairs:
            v = self._value(x, y)
            if v is None or not _contains(zd, v):
                continue
            if (z_is_a and v != x) or (z_is_b and v != y):
                continue
            img.add(v)
            sa.add(x)
            sb.add(y)
        if not img:
            return None
        to_dom = _clpfd()._indices_to_domain
        return (_inter(zd, to_dom(sorted(img))), to_dom(sorted(sa)),
                to_dom(sorted(sb)))

    def _enumerable(self, ad, bd):
        return True


def _make(cls_name, value_fn, bounds_fn, enumerable=None):
    base = _base()

    def __init__(self, z, a, b):
        self.z = z
        self.a = a
        self.b = b
        vs = []
        for t in (z, a, b):
            t = deref(t)
            if is_var(t) and not any(t is u for u in vs):
                vs.append(t)
        base.__init__(self, tuple(vs))

    ns = {"__slots__": ("z", "a", "b"), "__init__": __init__,
          "_value": staticmethod(value_fn), "_bounds": staticmethod(bounds_fn),
          "propagate": NonlinearConstraint.propagate,
          "_doms": NonlinearConstraint._doms,
          "_enumerate": NonlinearConstraint._enumerate,
          "_enumerable": (staticmethod(enumerable) if enumerable
                          else NonlinearConstraint._enumerable)}
    return type(cls_name, (base,), ns)


# ── values ──────────────────────────────────────────────────────────────────

def _v_times(x, y):
    return x * y


def _v_tdiv(x, y):
    if y == 0:
        return None
    q = abs(x) // abs(y)
    return q if (x >= 0) == (y > 0) else -q


def _v_fdiv(x, y):
    return None if y == 0 else x // y


def _v_mod(x, y):
    return None if y == 0 else x % y


def _v_rem(x, y):
    if y == 0:
        return None
    return x - y * _v_tdiv(x, y)


def _v_pow(x, y):
    if y < 0:
        if x == 1:
            return 1
        if x == -1:
            return -1 if y % 2 else 1
        return None
    return x ** y


def _v_min(x, y):
    return min(x, y)


def _v_max(x, y):
    return max(x, y)


# ── bounds ──────────────────────────────────────────────────────────────────

def _times_hull(ad, bd):
    cs = [_mul(p, q) for p in (_lo(ad), _hi(ad)) for q in (_lo(bd), _hi(bd))]
    return _rng(min(cs), max(cs))


def _quot_hull(zd, bd):
    """Integer hull of the integers y with z = b*y for some z in zd, b in bd
    (bd one-signed).  When a corner is undefined (an infinite z over an
    infinite b) the signs still bound it: y has the sign of z/b, and
    |y| >= 1 once z excludes 0."""
    qs = []
    for zz in (_lo(zd), _hi(zd)):
        for bb in (_lo(bd), _hi(bd)):
            q = _q(zz, bb)
            if q is None:
                return _sign_quot(zd, bd)
            qs.append(q)
    return _rng(_ceil(min(qs)), _floor(max(qs)))


def _sign_quot(zd, bd):
    zl, zh = _lo(zd), _hi(zd)
    sb = 1 if _lo(bd) > 0 else -1
    if zl >= 0:
        sz = 1
    elif zh <= 0:
        sz = -1
    else:
        return ((NINF, INF),)
    nonzero = zl > 0 or zh < 0
    mag_lo = 1 if nonzero else 0
    maxz = max(abs(zl), abs(zh))
    minb = min(abs(_lo(bd)), abs(_hi(bd)))
    mag_hi = INF if maxz == INF else maxz // minb
    if sz * sb > 0:
        return _rng(mag_lo, mag_hi)
    return _rng(-mag_hi, -mag_lo)


def _factor(zd, other):
    """What a factor can be, given the product's domain and the other
    factor's."""
    ov = _single(other)
    if ov == 0:
        return ((NINF, INF),) if _contains(zd, 0) else ()
    if _contains(zd, 0) and _contains(other, 0):
        return ((NINF, INF),)
    parts = []
    for part in (_neg(other), _pos(other)):
        if part:
            parts.append(_quot_hull(zd, part))
    return _union(*parts)


def _b_times(zd, ad, bd, square=False):
    if square:
        lo, hi = _lo(ad), _hi(ad)
        if lo >= 0:
            img = _rng(_mul(lo, lo), _mul(hi, hi))
        elif hi <= 0:
            img = _rng(_mul(hi, hi), _mul(lo, lo))
        else:
            img = _rng(0, max(_mul(lo, lo), _mul(hi, hi)))
        zd = _inter(zd, img)
        if not zd:
            return None
        zhi, zlo = _hi(zd), _lo(zd)
        if zhi < 0:
            return None
        r = INF if zhi == INF else math.isqrt(zhi)
        s = 0 if zlo <= 0 else _iroot_ceil(zlo, 2)
        if s == 0:
            ad = _inter(ad, _rng(-r, r))
        else:
            ad = _inter(ad, _union(_rng(-r, -s), _rng(s, r)))
        return zd, ad, ad
    zd = _inter(zd, _times_hull(ad, bd))
    if not zd:
        return None
    for known, other, first in ((bd, ad, True), (ad, bd, False)):
        c = _single(known)
        if c is None or c == 0:
            continue
        # Z = c * F exactly: Z within c times F's intervals, F within Z's
        # intervals over c (clpz's domain_expand / domain_contract)
        zd = _inter(zd, _union(*(_rng(min(_mul(c, lo), _mul(c, hi)),
                                      max(_mul(c, lo), _mul(c, hi)))
                                 for lo, hi in other)))
        if not zd:
            return None
        pre = _union(*(_quot_hull(((lo, hi),), known) for lo, hi in zd))
        other = _inter(other, pre)
        if not other:
            return None
        if first:
            ad = other
        else:
            bd = other
    if not _contains(zd, 0):
        ad, bd = _remove(ad, 0), _remove(bd, 0)
        if not (ad and bd):
            return None
    ad = _inter(ad, _factor(zd, bd))
    if not ad:
        return None
    bd = _inter(bd, _factor(zd, ad))
    if not bd:
        return None
    return zd, ad, bd


def _b_times_plain(zd, ad, bd):
    return _b_times(zd, ad, bd)


def _qround(q, trunc):
    """Round an exact quotient (a Fraction, or an infinity) toward zero
    (``//``) or down (``div``)."""
    if q in (INF, NINF):
        return q
    if trunc:
        return math.trunc(q)
    return math.floor(q)


def _div_corner(a, b, trunc):
    """The rounded quotient at a corner, as a LIMIT when b is infinite."""
    if b in (INF, NINF):
        if a in (INF, NINF):
            return None
        s = (a > 0) - (a < 0)
        s *= 1 if b > 0 else -1
        return -1 if (s < 0 and not trunc) else 0
    q = _q(a, b)
    if q is None:
        return None
    return _qround(q, trunc)


def _div_image(ad, bpart, trunc):
    cs = []
    for x in (_lo(ad), _hi(ad)):
        for y in (_lo(bpart), _hi(bpart)):
            c = _div_corner(x, y, trunc)
            if c is None:
                return ((NINF, INF),)
            cs.append(c)
    # a in the interior of A matters only through monotonicity, but a
    # domain spanning 0 reaches 0 too
    if _lo(ad) <= 0 <= _hi(ad):
        cs.append(0)
    return _rng(min(cs), max(cs))


def _div_dividend(zlo, zhi, b, trunc):
    """The dividends a with ``a op b`` in [zlo, zhi], b > 0: (lo, hi)."""
    if trunc:
        lo = _mul(zlo, b) if zlo > 0 else _mul(zlo - 1, b) + 1
        hi = _mul(zhi + 1, b) - 1 if zhi >= 0 else _mul(zhi, b)
    else:
        lo = _mul(zlo, b)
        hi = _mul(zhi + 1, b) - 1
    return lo, hi


def _b_div(zd, ad, bd, trunc):
    bd = _remove(bd, 0)
    if not bd:
        return None
    # the quotient from the operands
    img = _union(*(_div_image(ad, part, trunc)
                   for part in (_neg(bd), _pos(bd)) if part))
    zd = _inter(zd, img)
    if not zd:
        return None
    zlo, zhi = _lo(zd), _hi(zd)
    # the dividend from the quotient and the divisor
    parts = []
    for part, sign in ((_pos(bd), 1), (_neg(bd), -1)):
        if not part:
            continue
        lows, highs = [], []
        for bb in (_lo(part), _hi(part)):
            m = abs(bb)
            if sign > 0:
                lo, hi = _div_dividend(zlo, zhi, m, trunc)
            else:
                # a op b == (-a) op |b| for b < 0, both roundings
                lo2, hi2 = _div_dividend(zlo, zhi, m, trunc)
                lo, hi = -hi2, -lo2
            lows.append(lo)
            highs.append(hi)
        parts.append(_rng(min(lows), max(highs)))
    ad = _inter(ad, _union(*parts))
    if not ad:
        return None
    bv = _single(bd)
    if bv is not None:
        # a known divisor: exact image and preimage, interval by interval
        zd = _inter(zd, _div_image_known(ad, bv, trunc))
        if not zd:
            return None
        ad = _inter(ad, _div_preimage(zd, bv, trunc))
        if not ad:
            return None
        return zd, ad, bd
    # the divisor from the dividend and the quotient
    bd = _divisor(zd, ad, bd, trunc)
    if not bd:
        return None
    return zd, ad, bd


def _divisor(zd, ad, bd, trunc):
    """The divisor from the dividend and the quotient: r = a/b lies in a
    real interval R given by Z and the rounding; |b| = |a|/|r| then bounds
    |b|, and R's sign fixes b's sign against a one-signed A."""
    zlo, zhi = _lo(zd), _hi(zd)
    # R = (L, U) with closedness flags
    if trunc:
        L, lc = (zlo, True) if zlo > 0 else (zlo - 1, False)
        U, uc = (zhi + 1, False) if zhi >= 0 else (zhi, True)
    else:
        L, lc, U, uc = zlo, True, zhi + 1, False
    if L >= 0:
        rmin, rmin_c, rmax, rmax_c, rel = L, lc, U, uc, 1
    elif U <= 0:
        rmin, rmin_c, rmax, rmax_c, rel = -U, uc, -L, lc, -1
    else:
        rmin, rmin_c, rel = 0, True, 0
        if -L > U:
            rmax, rmax_c = -L, lc
        elif U > -L:
            rmax, rmax_c = U, uc
        else:
            rmax, rmax_c = U, lc or uc
    alo, ahi = _lo(ad), _hi(ad)
    maxa = max(abs(alo), abs(ahi))
    mina = 0 if alo <= 0 <= ahi else min(abs(alo), abs(ahi))
    # |b| <= maxa / rmin  (strict when rmin's end is open)
    hi_b = INF
    if rmin > 0 and maxa != INF:
        q = Fraction(maxa) / Fraction(rmin)
        hi_b = math.floor(q) if rmin_c else math.ceil(q) - 1
    # |b| >= mina / rmax  (strict when rmax's end is open)
    lo_b = 1
    if rmax != INF and mina > 0:
        q = Fraction(mina) / Fraction(rmax)
        lo_b = max(1, math.ceil(q) if rmax_c else math.floor(q) + 1)
    if hi_b < lo_b:
        return ()
    mag = _union(_rng(-hi_b, -lo_b), _rng(lo_b, hi_b))
    bd = _inter(bd, mag)
    if not bd:
        return bd
    # signs: r > 0 means b has a's sign, r < 0 the opposite one
    if rel != 0 and (L > 0 or U < 0 or alo > 0 or ahi < 0):
        sa = 1 if alo > 0 else (-1 if ahi < 0 else 0)
        if sa:
            if sa * rel > 0:
                bd = _inter(bd, ((1, INF),))
            else:
                bd = _inter(bd, ((NINF, -1),))
    return bd


def _div_preimage(zd, b, trunc):
    """The dividends whose quotient by the known b != 0 is in zd (exact:
    the quotient is monotone in the dividend)."""
    m = abs(b)
    parts = []
    for zl, zh in zd:
        lo, hi = _div_dividend(zl, zh, m, trunc)
        if b < 0:
            lo, hi = -hi, -lo
        parts.append(_rng(lo, hi))
    return _union(*parts)


def _div_image_known(ad, b, trunc):
    """The quotients of A's values by the known b, interval by interval."""
    parts = []
    for lo, hi in ad:
        c1 = _div_corner(lo, b, trunc)
        c2 = _div_corner(hi, b, trunc)
        parts.append(_rng(min(c1, c2), max(c1, c2)))
    return _union(*parts)


def _b_tdiv(zd, ad, bd):
    return _b_div(zd, ad, bd, True)


def _b_fdiv(zd, ad, bd):
    return _b_div(zd, ad, bd, False)


def _congruent_bounds(ad, z, m, sign):
    """Narrow A to its least and greatest values congruent to z mod m
    (and of the given sign: 1 for a > 0, -1 for a < 0, 0 for any)."""
    if sign > 0:
        ad = _inter(ad, ((1, INF),))
    elif sign < 0:
        ad = _inter(ad, ((NINF, -1),))
    if not ad:
        return ad
    lo, hi = _lo(ad), _hi(ad)
    if lo != NINF:
        lo = lo + ((z - lo) % m)
    if hi != INF:
        hi = hi - ((hi - z) % m)
    return _inter(ad, _rng(lo, hi))


def _boundary_support(ad, b, zd, value, steps=64):
    """With the divisor known, drop A's least and greatest values while they
    have no value in Z (at most *steps* each way)."""
    for _ in range(steps):
        if not ad:
            return ad
        lo = _lo(ad)
        if lo == NINF:
            break
        v = value(lo, b)
        if v is not None and _contains(zd, v):
            break
        ad = _remove(ad, lo)
    for _ in range(steps):
        if not ad:
            return ad
        hi = _hi(ad)
        if hi == INF:
            break
        v = value(hi, b)
        if v is not None and _contains(zd, v):
            break
        ad = _remove(ad, hi)
    return ad


def _b_modrem(zd, ad, bd, is_rem):
    bd = _remove(bd, 0)
    if not bd:
        return None
    value = _v_rem if is_rem else _v_mod
    # the result from the operands
    if is_rem:
        m = max(abs(_lo(bd)), abs(_hi(bd)))
        zl = 0 if _lo(ad) >= 0 else max(_lo(ad), -(m - 1))
        zh = 0 if _hi(ad) <= 0 else min(_hi(ad), m - 1)
        zd = _inter(zd, _rng(zl, zh))
    else:
        parts = []
        if _pos(bd):
            parts.append(_rng(0, _hi(bd) - 1))
        if _neg(bd):
            parts.append(_rng(_lo(bd) + 1, 0))
        zd = _inter(zd, _union(*parts))
        if zd and _lo(ad) >= 0:
            zd = _inter(zd, ((NINF, _hi(ad)),))
        if zd and _hi(ad) <= 0:
            zd = _inter(zd, ((_lo(ad), INF),))
    if not zd:
        return None
    # identity: |b| beyond |a| leaves a unchanged
    if _finite(ad):
        mabs = _maxabs(ad)
        if is_rem:
            bp, bn = _pos(bd), _neg(bd)
            ident = ((not bp or _lo(bp) > mabs)
                     and (not bn or _hi(bn) < -mabs))
        else:
            ident = ((_lo(ad) >= 0 and _lo(bd) > _hi(ad))
                     or (_hi(ad) <= 0 and _hi(bd) < _lo(ad)))
        if ident:
            both = _inter(zd, ad)
            if not both:
                return None
            zd = ad = both
    # the divisor from the result
    zlo, zhi = _lo(zd), _hi(zd)
    if is_rem:
        if not _contains(zd, 0):
            mz = min(abs(v) for v in (zlo, zhi)) if (zlo > 0 or zhi < 0) else 1
            bd = _inter(bd, _union(_rng(NINF, -(mz + 1)), _rng(mz + 1, INF)))
    else:
        if zlo > 0:
            bd = _inter(bd, ((zlo + 1, INF),))
        elif zhi < 0:
            bd = _inter(bd, ((NINF, zhi - 1),))
    if not bd:
        return None
    # b divides a - z when z can never be a
    if _finite(ad) and _finite(zd) and not _inter(ad, zd):
        m = max(abs(_lo(ad) - zhi), abs(_hi(ad) - zlo))
        bd = _inter(bd, _rng(-m, m))
        if not bd:
            return None
    # the dividend from the result and a known divisor
    bv = _single(bd)
    if bv is not None:
        zv = _single(zd)
        if zv is not None:
            sign = ((zv > 0) - (zv < 0)) if is_rem else 0
            ad = _congruent_bounds(ad, zv, abs(bv), sign)
        elif is_rem:
            if zlo > 0:
                ad = _inter(ad, ((1, INF),))
            elif zhi < 0:
                ad = _inter(ad, ((NINF, -1),))
        if ad:
            ad = _boundary_support(ad, bv, zd, value)
        if not ad:
            return None
    return zd, ad, bd


def _b_mod(zd, ad, bd):
    return _b_modrem(zd, ad, bd, False)


def _b_rem(zd, ad, bd):
    return _b_modrem(zd, ad, bd, True)


def _ipow(base, e):
    """``base ** e`` over the extended integers, e >= 0 (an infinite e
    allowed); None when too large to build."""
    if e == 0:
        return 1
    if base in (0, 1):
        return base
    if base == -1:
        return None if e == INF else (1 if e % 2 == 0 else -1)
    if e == INF or base in (INF, NINF):
        if base in (INF, NINF):
            if e == INF:
                return INF if base > 0 else None
            return base if (base > 0 or e % 2) else INF
        return INF if base > 0 else None
    if e > _POW_EXP_LIMIT and abs(base) > 1:
        return None
    return base ** e


def _b_pow(zd, ad, bd):
    av = _single(ad)
    if av in (0, 1, -1):
        return _pow_small_base(zd, ad, bd, av)
    # a negative exponent has a value only for a base of 1 or -1
    if not (_contains(ad, 1) or _contains(ad, -1)):
        bd = _inter(bd, ((0, INF),))
        if not bd:
            return None
    nb = _inter(bd, ((0, INF),))
    if not nb:
        return zd, ad, bd       # only negative exponents: base is +-1
    blo, bhi = _lo(nb), _hi(nb)
    # the result from the operands (non-negative exponents)
    alo, ahi = _lo(ad), _hi(ad)
    bv = _single(nb)
    img = None
    if bv is not None and nb == bd:
        if bv == 0:
            img = ((1, 1),)
        elif bv % 2 == 0:
            mn = 0 if alo <= 0 <= ahi else min(abs(alo), abs(ahi))
            mx = max(abs(alo), abs(ahi))
            lo, hi = _ipow(mn, bv), _ipow(mx, bv)
            img = _rng(lo if lo is not None else 0, hi if hi is not None else INF)
        else:
            lo, hi = _ipow(alo, bv), _ipow(ahi, bv)
            img = _rng(lo if lo is not None else NINF, hi if hi is not None else INF)
    elif nb == bd:
        if alo >= 1:
            lo, hi = _ipow(alo, blo), _ipow(ahi, bhi)
            img = _rng(lo if lo is not None else 1, hi if hi is not None else INF)
        elif alo >= 0:
            hi = _ipow(ahi, bhi)
            img = _rng(0, max(1, hi) if hi is not None else INF)
        else:
            mx = max(abs(alo), abs(ahi))
            hi = _ipow(mx, bhi)
            if hi is not None and hi != INF:
                hi = max(1, hi)
                img = _rng(-hi, hi)
    if img is not None:
        zd = _inter(zd, img)
        if not zd:
            return None
    if nb == bd and blo >= 1:
        if not _contains(ad, 0):
            zd = _remove(zd, 0)
        if not _contains(zd, 0):
            ad = _remove(ad, 0)
        if not (zd and ad):
            return None
    zlo, zhi = _lo(zd), _hi(zd)
    # the base from the result and a known exponent
    if bv is not None and nb == bd and bv >= 1:
        if bv % 2 == 0:
            if zhi < 0:
                return None
            r = INF if zhi == INF else _iroot_floor(zhi, bv)
            s = 0 if zlo <= 0 else _iroot_ceil(zlo, bv)
            if s == 0:
                ad = _inter(ad, _rng(-r, r))
            else:
                ad = _inter(ad, _union(_rng(-r, -s), _rng(s, r)))
        else:
            def sroot_floor(n):
                if n in (INF, NINF):
                    return n
                return _iroot_floor(n, bv) if n >= 0 else -_iroot_ceil(-n, bv)

            def sroot_ceil(n):
                if n in (INF, NINF):
                    return n
                return _iroot_ceil(n, bv) if n >= 0 else -_iroot_floor(-n, bv)
            ad = _inter(ad, _rng(sroot_ceil(zlo), sroot_floor(zhi)))
        if not ad:
            return None
    # the exponent from the base and the result
    mina = min(abs(x) for x in (alo, ahi)) if (alo > 0 or ahi < 0) else 0
    if mina >= 2 and _finite(zd):
        mz = max(abs(zlo), abs(zhi))
        if mz < 1:
            return None
        top = _ilog_floor(mz, mina)
        bd = _inter(bd, ((NINF, top),))
        if not bd:
            return None
    return zd, ad, bd


def _pow_small_base(zd, ad, bd, a):
    """``Z = a ^ B`` for a known base 0, 1 or -1."""
    if a == 1:
        zd = _inter(zd, ((1, 1),))
        return (zd, ad, bd) if zd else None
    if a == 0:
        bd = _inter(bd, ((0, INF),))       # 0^(-n) has no value
        zd = _inter(zd, ((0, 1),))
        if not (bd and zd):
            return None
        if not _contains(zd, 1):
            bd = _inter(bd, ((1, INF),))
        if not _contains(zd, 0):
            bd = _inter(bd, ((0, 0),))
        if not _contains(bd, 0):
            zd = _inter(zd, ((0, 0),))
        if _lo(bd) > 0 or _hi(bd) < 0:
            zd = _inter(zd, ((0, 0),))
        if bd == ((0, 0),):
            zd = _inter(zd, ((1, 1),))
        return (zd, ad, bd) if (zd and bd) else None
    # a == -1: 1 for an even exponent, -1 for an odd one
    zd = _inter(zd, ((-1, -1), (1, 1)))
    if not zd:
        return None
    return zd, ad, bd


def _pow_enumerable(ad, bd):
    return _hi(bd) <= _POW_EXP_LIMIT or _maxabs(ad) <= 1


def _b_minmax(zd, ad, bd, is_max):
    if is_max:
        neg = _clpfd()._domain_negate
        r = _b_minmax(neg(zd), neg(ad), neg(bd), False)
        if r is None:
            return None
        return tuple(neg(d) for d in r)
    # Z = min(A, B)
    alo, ahi, blo, bhi = _lo(ad), _hi(ad), _lo(bd), _hi(bd)
    if ahi < blo:
        img = ad
    elif bhi < alo:
        img = bd
    else:
        img = _inter(_union(ad, bd), _rng(min(alo, blo), min(ahi, bhi)))
    zd = _inter(zd, img)
    if not zd:
        return None
    above = ((_lo(zd), INF),)
    ad, bd = _inter(ad, above), _inter(bd, above)
    if not (ad and bd):
        return None
    # Z is one of them: an operand that cannot be Z leaves Z to the other
    if not _inter(ad, zd):
        bd = _inter(bd, zd)
        zd = _inter(zd, bd)
    elif not _inter(bd, zd):
        ad = _inter(ad, zd)
        zd = _inter(zd, ad)
    if not (ad and bd and zd):
        return None
    return zd, ad, bd


def _b_min(zd, ad, bd):
    return _b_minmax(zd, ad, bd, False)


def _b_max(zd, ad, bd):
    return _b_minmax(zd, ad, bd, True)


_CLASSES: dict = {}


def constraint_class(kind):
    """The propagator class for *kind* (``times``, ``tdiv``, ``fdiv``,
    ``mod``, ``rem``, ``pow``, ``min``, ``max``)."""
    cls = _CLASSES.get(kind)
    if cls is None:
        table = {
            "times": ("TimesConstraint", _v_times, None),
            "tdiv": ("TruncDivConstraint", _v_tdiv, _b_tdiv),
            "fdiv": ("FloorDivConstraint", _v_fdiv, _b_fdiv),
            "mod": ("ModConstraint", _v_mod, _b_mod),
            "rem": ("RemConstraint", _v_rem, _b_rem),
            "pow": ("PowConstraint", _v_pow, _b_pow),
            "min": ("MinConstraint", _v_min, _b_min),
            "max": ("MaxConstraint", _v_max, _b_max),
        }
        name, vf, bf = table[kind]
        if kind == "times":
            cls = _make_times()
        else:
            cls = _make(name, vf, bf,
                        _pow_enumerable if kind == "pow" else None)
        _CLASSES[kind] = cls
    return cls


def _make_times():
    base = _base()

    class TimesConstraint(base):
        """``Z = X * Y`` (``X * X`` a square): bounds in every direction,
        0 excluded from both factors once the product excludes it, and
        domain consistency on small factors."""
        __slots__ = ("z", "x", "y", "a", "b")

        def __init__(self, z, x, y):
            self.z = z
            self.x = self.a = x
            self.y = self.b = y
            vs = []
            for t in (z, x, y):
                t = deref(t)
                if is_var(t) and not any(t is u for u in vs):
                    vs.append(t)
            base.__init__(self, tuple(vs))

        def _bounds(self, zd, ad, bd):
            a, b = deref(self.a), deref(self.b)
            return _b_times(zd, ad, bd, square=(a is b and is_var(a)))

        _value = staticmethod(_v_times)
        propagate = NonlinearConstraint.propagate
        _doms = NonlinearConstraint._doms
        _enumerate = NonlinearConstraint._enumerate
        _enumerable = NonlinearConstraint._enumerable

    return TimesConstraint
