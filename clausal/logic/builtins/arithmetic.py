"""Arithmetic builtins: Between/3, Succ/2, Plus/3, Abs/2, Max/3, Min/3,
Sign/2, Gcd/3, DivMod/4, Lcm/3, ExpMod/4, Popcount/2, Msb/2, Lsb/2.

All predicates that accept numeric values also accept Quantity values
(numbers with physical dimensions).  Dimension mismatches raise
``UnitsMismatch`` — they are **not** silenced.
"""

from __future__ import annotations

from math import gcd as _gcd

from clausal.logic.variables import deref, is_var, unify
from clausal.terms import Quantity

from clausal.logic.builtins._registry import _builtin


# ── Quantity helpers ───────────────────────────────────────────────────────


def _is_numeric(val) -> bool:
    """True if val is int, float, or Quantity (but not bool)."""
    if isinstance(val, bool):
        return False
    return isinstance(val, (int, float, Quantity))


def _is_int_like(val) -> bool:
    """True if val is a plain int or a Quantity with integer value (not bool)."""
    if isinstance(val, bool):
        return False
    if isinstance(val, int):
        return True
    if isinstance(val, Quantity):
        return isinstance(val.value, int) and not isinstance(val.value, bool)
    return False


def _int_value(val):
    """Extract the integer value from int or Quantity."""
    if isinstance(val, Quantity):
        return val.value
    return val


def _require_same_dims(a, b):
    """Verify both operands have compatible dimensions.

    Returns (has_quantity, dims) where dims is the shared dimension dict
    or None if neither is Quantity.

    Raises UnitsMismatch if:
    - Both are Quantity with different dims.
    - One is Quantity with non-empty dims and the other is a plain number
      (mixing dimensioned and dimensionless is an error for Gcd/Lcm/DivMod).
    """
    from clausal.terms import UnitsMismatch

    a_q = isinstance(a, Quantity)
    b_q = isinstance(b, Quantity)
    if a_q and b_q:
        if a.dims != b.dims:
            a._require_same_dims(b, "operate on")
        return True, a.dims
    if a_q or b_q:
        q = a if a_q else b
        if q.dims:
            # Dimensioned Quantity mixed with plain number — error
            plain = b if a_q else a
            raise UnitsMismatch(
                f"Cannot operate on dimensioned quantity and plain value {plain!r}"
            )
        # Dimensionless Quantity + plain number — treat as plain
        return False, None
    return False, None


def _wrap_quantity(value, dims):
    """Wrap an integer value back into a Quantity with the given dims."""
    if dims is not None and dims:
        return Quantity(value, dict(dims))
    return value


# ── Predicates ─────────────────────────────────────────────────────────────


@_builtin("Between", 3)
def _between__3(low, high, x, trail, k):
    """between(Low, High, X) — X ranges over integers from Low to High inclusive."""
    low_val = deref(low)
    high_val = deref(high)
    if is_var(low_val) or is_var(high_val):
        return
    if not isinstance(low_val, int) or not isinstance(high_val, int):
        return
    x_val = deref(x)
    if not is_var(x_val):
        # Check mode
        if isinstance(x_val, int) and low_val <= x_val <= high_val:
            yield None
    else:
        # Generate mode
        for i in range(low_val, high_val + 1):
            mark = trail.mark()
            if unify(x, i, trail):
                yield None
            trail.undo(mark)


@_builtin("Succ", 2)
def _succ__2(x, y, trail, k):
    """succ(X, Y) — Y = X + 1 (both non-negative integers)."""
    x_val = deref(x)
    y_val = deref(y)
    if not is_var(x_val):
        if not isinstance(x_val, int) or isinstance(x_val, bool) or x_val < 0:
            return
        mark = trail.mark()
        if unify(y, x_val + 1, trail):
            yield None
        trail.undo(mark)
    elif not is_var(y_val):
        if not isinstance(y_val, int) or isinstance(y_val, bool) or y_val < 1:
            return
        mark = trail.mark()
        if unify(x, y_val - 1, trail):
            yield None
        trail.undo(mark)


@_builtin("Plus", 3)
def _plus__3(x, y, z, trail, k):
    """plus(X, Y, Z) — Z = X + Y; any two determine the third.

    Supports Quantity values — dimension mismatches raise UnitsMismatch.
    """
    x_val = deref(x)
    y_val = deref(y)
    z_val = deref(z)
    x_known = not is_var(x_val)
    y_known = not is_var(y_val)
    z_known = not is_var(z_val)

    if x_known and y_known:
        # Z = X + Y  (UnitsMismatch propagates naturally)
        mark = trail.mark()
        if unify(z, x_val + y_val, trail):
            yield None
        trail.undo(mark)
    elif x_known and z_known:
        mark = trail.mark()
        if unify(y, z_val - x_val, trail):
            yield None
        trail.undo(mark)
    elif y_known and z_known:
        mark = trail.mark()
        if unify(x, z_val - y_val, trail):
            yield None
        trail.undo(mark)


@_builtin("Abs", 2)
def _abs__2(x, y, trail, k):
    """Abs(X, Y) — Y = abs(X).  Supports Quantity (preserves dimensions)."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if not _is_numeric(x_val):
        return
    mark = trail.mark()
    if unify(y, abs(x_val), trail):
        yield None
    trail.undo(mark)


@_builtin("Max", 3)
def _max__3(x, y, z, trail, k):
    """Max(X, Y, Z) — Z = max(X, Y).

    Supports Quantity — dimensions must agree (UnitsMismatch propagates).
    """
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    # max() uses __gt__ which Quantity implements (raises on dim mismatch)
    mark = trail.mark()
    if unify(z, max(x_val, y_val), trail):
        yield None
    trail.undo(mark)


@_builtin("Min", 3)
def _min__3(x, y, z, trail, k):
    """Min(X, Y, Z) — Z = min(X, Y).

    Supports Quantity — dimensions must agree (UnitsMismatch propagates).
    """
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    mark = trail.mark()
    if unify(z, min(x_val, y_val), trail):
        yield None
    trail.undo(mark)


@_builtin("Sign", 2)
def _sign__2(x, s, trail, k):
    """Sign(X, S) — S is the sign of X: -1, 0, or 1 (always dimensionless).

    Supports Quantity — extracts the numeric value, returns plain int.
    """
    x_val = deref(x)
    if is_var(x_val):
        return
    if not _is_numeric(x_val):
        return
    v = x_val.value if isinstance(x_val, Quantity) else x_val
    sign_val = (v > 0) - (v < 0)
    mark = trail.mark()
    if unify(s, sign_val, trail):
        yield None
    trail.undo(mark)


@_builtin("Gcd", 3)
def _gcd__3(x, y, g, trail, k):
    """Gcd(X, Y, G) — G is the greatest common divisor of X and Y.

    Supports Quantity — dimensions must agree; result has the same dimensions.
    """
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    if not _is_int_like(x_val) or not _is_int_like(y_val):
        return
    has_q, dims = _require_same_dims(x_val, y_val)
    result = _gcd(_int_value(x_val), _int_value(y_val))
    if has_q:
        result = _wrap_quantity(result, dims)
    mark = trail.mark()
    if unify(g, result, trail):
        yield None
    trail.undo(mark)


@_builtin("DivMod", 4)
def _divmod__4(x, y, q, r, trail, k):
    """DivMod(X, Y, Q, R) — Q is X // Y, R is X mod Y.

    Supports Quantity — dimensions must agree; Q is dimensionless, R keeps dimensions.
    """
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    if not _is_int_like(x_val) or not _is_int_like(y_val):
        return
    xv, yv = _int_value(x_val), _int_value(y_val)
    if yv == 0:
        return
    has_q, dims = _require_same_dims(x_val, y_val)
    quotient, remainder = divmod(xv, yv)
    # Quotient is always dimensionless; remainder keeps the dimensions
    if has_q:
        remainder = _wrap_quantity(remainder, dims)
    mark = trail.mark()
    if unify(q, quotient, trail):
        m2 = trail.mark()
        if unify(r, remainder, trail):
            yield None
        trail.undo(m2)
    trail.undo(mark)


@_builtin("Lcm", 3)
def _lcm__3(x, y, l, trail, k):
    """Lcm(X, Y, L) — L is the least common multiple of X and Y.

    Supports Quantity — dimensions must agree; result has the same dimensions.
    """
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    if not _is_int_like(x_val) or not _is_int_like(y_val):
        return
    has_q, dims = _require_same_dims(x_val, y_val)
    xv, yv = _int_value(x_val), _int_value(y_val)
    if xv == 0 or yv == 0:
        result = 0
    else:
        result = abs(xv * yv) // _gcd(xv, yv)
    if has_q:
        result = _wrap_quantity(result, dims)
    mark = trail.mark()
    if unify(l, result, trail):
        yield None
    trail.undo(mark)


@_builtin("ExpMod", 4)
def _expmod__4(base, exp, mod, result, trail, k):
    """ExpMod(Base, Exp, Mod, Result) — Result is Base^Exp mod Mod.

    Integer-only (no Quantity support — modular exponentiation has no
    meaningful dimensional interpretation).
    """
    base_val = deref(base)
    exp_val = deref(exp)
    mod_val = deref(mod)
    if is_var(base_val) or is_var(exp_val) or is_var(mod_val):
        return
    if not isinstance(base_val, int) or not isinstance(exp_val, int) or not isinstance(mod_val, int):
        return
    if mod_val == 0:
        return
    r = pow(base_val, exp_val, mod_val)
    mark = trail.mark()
    if unify(result, r, trail):
        yield None
    trail.undo(mark)


@_builtin("Popcount", 2)
def _popcount__2(x, count, trail, k):
    """Popcount(X, Count) — Count is the number of set bits in X.

    Integer-only (bitwise operation, no Quantity support).
    """
    x_val = deref(x)
    if is_var(x_val):
        return
    if not isinstance(x_val, int) or isinstance(x_val, bool) or x_val < 0:
        return
    result = bin(x_val).count('1')
    mark = trail.mark()
    if unify(count, result, trail):
        yield None
    trail.undo(mark)


@_builtin("Msb", 2)
def _msb__2(x, bit, trail, k):
    """Msb(X, Bit) — Bit is the position of the most significant set bit (0-indexed).

    Integer-only (bitwise operation, no Quantity support).
    """
    x_val = deref(x)
    if is_var(x_val):
        return
    if not isinstance(x_val, int) or isinstance(x_val, bool) or x_val <= 0:
        return
    result = x_val.bit_length() - 1
    mark = trail.mark()
    if unify(bit, result, trail):
        yield None
    trail.undo(mark)


@_builtin("Lsb", 2)
def _lsb__2(x, bit, trail, k):
    """Lsb(X, Bit) — Bit is the position of the least significant set bit (0-indexed).

    Integer-only (bitwise operation, no Quantity support).
    """
    x_val = deref(x)
    if is_var(x_val):
        return
    if not isinstance(x_val, int) or isinstance(x_val, bool) or x_val <= 0:
        return
    result = (x_val & -x_val).bit_length() - 1
    mark = trail.mark()
    if unify(bit, result, trail):
        yield None
    trail.undo(mark)
