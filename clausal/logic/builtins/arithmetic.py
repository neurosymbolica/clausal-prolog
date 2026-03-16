"""Arithmetic builtins: Between/3, Succ/2, Plus/3, Abs/2, Max/3, Min/3,
Sign/2, Gcd/3, DivMod/4."""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify

from clausal.logic.builtins._registry import _builtin


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
    """plus(X, Y, Z) — Z = X + Y; any two determine the third."""
    x_val = deref(x)
    y_val = deref(y)
    z_val = deref(z)
    x_known = not is_var(x_val)
    y_known = not is_var(y_val)
    z_known = not is_var(z_val)

    if x_known and y_known:
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
    """abs_(X, Y) — Y = abs(X)."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if not isinstance(x_val, (int, float)):
        return
    mark = trail.mark()
    if unify(y, abs(x_val), trail):
        yield None
    trail.undo(mark)


@_builtin("Max", 3)
def _max__3(x, y, z, trail, k):
    """max_(X, Y, Z) — Z = max(X, Y)."""
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    mark = trail.mark()
    if unify(z, max(x_val, y_val), trail):
        yield None
    trail.undo(mark)


@_builtin("Min", 3)
def _min__3(x, y, z, trail, k):
    """min_(X, Y, Z) — Z = min(X, Y)."""
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
    """Sign(X, S) — S is the sign of X: -1, 0, or 1."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if not isinstance(x_val, (int, float)):
        return
    sign_val = (x_val > 0) - (x_val < 0)
    mark = trail.mark()
    if unify(s, sign_val, trail):
        yield None
    trail.undo(mark)


@_builtin("Gcd", 3)
def _gcd__3(x, y, g, trail, k):
    """Gcd(X, Y, G) — G is the greatest common divisor of X and Y."""
    from math import gcd
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    if not isinstance(x_val, int) or not isinstance(y_val, int):
        return
    mark = trail.mark()
    if unify(g, gcd(x_val, y_val), trail):
        yield None
    trail.undo(mark)


@_builtin("DivMod", 4)
def _divmod__4(x, y, q, r, trail, k):
    """DivMod(X, Y, Q, R) — Q is X // Y and R is X mod Y."""
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    if not isinstance(x_val, int) or not isinstance(y_val, int):
        return
    if y_val == 0:
        return
    quotient, remainder = divmod(x_val, y_val)
    mark = trail.mark()
    if unify(q, quotient, trail):
        m2 = trail.mark()
        if unify(r, remainder, trail):
            yield None
        trail.undo(m2)
    trail.undo(mark)
