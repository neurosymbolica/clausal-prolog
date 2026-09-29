"""Arithmetic builtins: between/3, succ/2, plus/3, abs_/2, max_/3, min_/3,
sign/2, gcd/3, divmod_/4, lcm/3, exp_mod/4, popcount/2, msb/2, lsb/2.

All predicates that accept numeric values also accept Quantity values
(numbers with physical dimensions).  Dimension mismatches raise
``UnitsMismatch`` — they are **not** silenced.
"""

from __future__ import annotations

from math import gcd as _gcd

from clausal.logic.variables import deref, is_var, unify, present_number
from clausal.terms import Quantity

from clausal.logic.builtins._registry import _builtin
from clausal.logic.exceptions import ARITH_OPERATOR_TERMS


# ── between/3 bound evaluation ─────────────────────────────────────────────
#
# A bound written as an expression — ``between(0, LENGTH - 1, X)`` — reaches
# the builtin as an unevaluated operator term (call arguments are structural,
# eval_arith=False). It is not a Var and not an int, so it used to fall
# through the type guard and *silently fail*: findall collected [] as a
# well-formed wrong answer. Comparison operators evaluate their operands
# (ARITH_OPERATOR_TERMS is exactly "the nodes ``==`` evaluates"), so
# "arithmetic works in argument position" is the generalisation the
# surrounding surface teaches — between/3 now follows it.
# See todo/done/between3-does-not-evaluate-arithmetic-in-its-bounds.md.


def _arith_has_unbound_var(term) -> bool:
    """True when an arithmetic operator term still contains an unbound Var."""
    term = deref(term)
    if is_var(term):
        return True
    if isinstance(term, ARITH_OPERATOR_TERMS):
        if hasattr(term, "operand"):  # Negate (unary)
            return _arith_has_unbound_var(term.operand)
        return (_arith_has_unbound_var(term.left)
                or _arith_has_unbound_var(term.right))
    return False


def _eval_between_bound(term):
    """Evaluate an arithmetic operator term appearing as a between/3 bound.

    Reuses the runtime ground evaluator behind the ``==`` comparison surface
    (``clpfd._eval_ground`` — int/int division yields an exact rational,
    presented as int when integral; ``present_number`` below is a local
    belt-and-braces for that evaluator's invariant).

    Returns the evaluated int, or None when the expression's only obstacle
    is an unbound Var — the caller then keeps between/3's silent
    mode-failure, matching a plain unbound bound.  A bound that can NEVER
    evaluate to an integer raises ``type_error(integer, ...)`` — the silent
    [] was the bug (see the module todo reference above).  That includes an
    expression mixing an unbound Var with a non-numeric leaf
    (``N - "a"``): ``_eval_ground`` raises on the garbage leaf whichever
    side it sits on (roborev job 13 — verified order-independent), and the
    raise is right — no future binding of ``N`` makes the bound legal.

    Raise sites: a non-numeric LEAF raises inside ``_eval_ground`` (its
    clpz ``domain_error`` is re-raised here as ``type_error(integer, Leaf)``
    with the "clpfd expression" context); a zero divisor raises
    ``evaluation_error(zero_divisor)`` there too (Q4, 2026-09-28); the local
    raise below covers a non-integer (7/2, bool) and names "between/3".
    """
    from clausal.logic.clpfd import _eval_ground  # lazy: clpfd is heavy
    from clausal.logic.exceptions import LogicException, type_error

    try:
        val = _eval_ground(term)
    except LogicException as exc:
        # The CLP(FD) leaf error is Scryer's clpz ``domain_error(
        # clpz_expression, Leaf)`` (Q3, 2026-09-28); between/3 is not a clpz
        # post, and a bound that can never be an integer keeps its
        # ``type_error(integer, Leaf)``.
        from clausal.logic.builtins.iso_compare import _clpfd_leaf_culprit  # noqa: PLC0415
        leaf = _clpfd_leaf_culprit(exc)
        if leaf is None:
            raise
        raise LogicException(type_error("integer", leaf, "clpfd expression")) from None
    if val is None:
        if _arith_has_unbound_var(term):
            return None
        # Ground but unevaluable (a zero divisor and a non-numeric leaf
        # raise inside _eval_ground already): name the unevaluated bound
        # rather than vanish.
        raise LogicException(type_error("integer", term, "between/3"))
    val = present_number(val)  # an exact rational that IS an integer (6 / 2)
    if not isinstance(val, int) or isinstance(val, bool):
        raise LogicException(type_error("integer", val, "between/3"))
    return val


# ── Quantity helpers ───────────────────────────────────────────────────────


def _is_numeric(val) -> bool:
    """True if val is int, float, or Quantity (but not bool)."""
    if isinstance(val, bool):
        return False
    return isinstance(val, (int, float, Quantity))


def _all_known_numeric(*vals) -> bool:
    """A09-F011: True if every already-bound (non-Var) operand is numeric
    (int/float/Quantity, not bool). Var operands are allowed — the mode is not
    yet determined. Used to guard plus/max_/min_ at the dispatch boundary so a
    non-numeric operand fails cleanly instead of the C fast path concatenating
    strings or leaking a raw TypeError. bool is excluded (A09-F015/A01-D001)."""
    return all(is_var(v) or _is_numeric(v) for v in vals)


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
      (mixing dimensioned and dimensionless is an error for gcd/lcm/divmod_).
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


# ── C extension import ────────────────────────────────────────────────────

_USE_C_ARITH = False
try:
    from clausal.logic._arithmetic_core import (
        arith_between as _c_between,
        arith_succ as _c_succ,
        arith_plus as _c_plus,
        arith_abs as _c_abs,
        arith_max as _c_max,
        arith_min as _c_min,
        arith_sign as _c_sign,
        arith_gcd as _c_gcd,
        arith_divmod as _c_divmod,
        arith_lcm as _c_lcm,
        arith_exp_mod as _c_exp_mod,
        arith_popcount as _c_popcount,
        arith_msb as _c_msb,
        arith_lsb as _c_lsb,
    )
    _USE_C_ARITH = True
except ImportError:
    pass


# ── Python reference implementations ──────────────────────────────────────


def _between__3_py(low, high, x, trail, k):
    """between(Low, High, X) — X ranges over integers from Low to High inclusive."""
    low_val = deref(low)
    high_val = deref(high)
    if is_var(low_val) or is_var(high_val):
        return
    # A09-F015 / A01-D001(c): reject bool bounds — the C path already does, so
    # this removes the between(False, True, X) C-vs-Python divergence.
    if not isinstance(low_val, int) or isinstance(low_val, bool) or \
       not isinstance(high_val, int) or isinstance(high_val, bool):
        return
    x_val = deref(x)
    if not is_var(x_val):
        # Check mode
        if isinstance(x_val, int) and not isinstance(x_val, bool) \
                and low_val <= x_val <= high_val:
            yield None
    else:
        # Generate mode
        for i in range(low_val, high_val + 1):
            mark = trail.mark()
            if unify(x, i, trail):
                yield None
            trail.undo(mark)


def _succ__2_py(x, y, trail, k):
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


def _plus__3_py(x, y, z, trail, k):
    """plus(X, Y, Z) — Z = X + Y; any two determine the third.

    Supports Quantity values — dimension mismatches raise UnitsMismatch.
    """
    x_val = deref(x)
    y_val = deref(y)
    z_val = deref(z)
    x_known = not is_var(x_val)
    y_known = not is_var(y_val)
    z_known = not is_var(z_val)

    # plus/3 is a numeric relation: every KNOWN operand must be numeric — a
    # non-numeric operand (e.g. a string) must fail cleanly, not concatenate
    # (C fast path) or raise TypeError from the inverse subtraction
    # (A06-F015 / A09-F011; also enforced at the dispatch boundary).
    if not _all_known_numeric(x_val, y_val, z_val):
        return

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


def _abs__2_py(x, y, trail, k):
    """abs_(X, Y) — Y = abs(X).  Supports Quantity (preserves dimensions)."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if not _is_numeric(x_val):
        return
    mark = trail.mark()
    if unify(y, abs(x_val), trail):
        yield None
    trail.undo(mark)


def _max__3_py(x, y, z, trail, k):
    """max_(X, Y, Z) — Z = max(X, Y).

    Supports Quantity — dimensions must agree (UnitsMismatch propagates).
    """
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    if not _all_known_numeric(x_val, y_val):  # A06-F015 / A09-F011
        return
    # max() uses __gt__ which Quantity implements (raises on dim mismatch)
    mark = trail.mark()
    if unify(z, max(x_val, y_val), trail):
        yield None
    trail.undo(mark)


def _min__3_py(x, y, z, trail, k):
    """min_(X, Y, Z) — Z = min(X, Y).

    Supports Quantity — dimensions must agree (UnitsMismatch propagates).
    """
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    if not _all_known_numeric(x_val, y_val):  # A06-F015 / A09-F011
        return
    mark = trail.mark()
    if unify(z, min(x_val, y_val), trail):
        yield None
    trail.undo(mark)


def _sign__2_py(x, s, trail, k):
    """sign(X, S) — S is the sign of X: -1, 0, or 1 (always dimensionless).

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


def _gcd__3_py(x, y, g, trail, k):
    """gcd(X, Y, G) — G is the greatest common divisor of X and Y.

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


def _divmod__4_py(x, y, q, r, trail, k):
    """divmod_(X, Y, Q, R) — Q is X // Y, R is X mod Y.

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


def _lcm__3_py(x, y, l, trail, k):
    """lcm(X, Y, L) — L is the least common multiple of X and Y.

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


def _expmod__4_py(base, exp, mod, result, trail, k):
    """exp_mod(Base, Exp, Mod, Result) — Result is Base^Exp mod Mod.

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


def _popcount__2_py(x, count, trail, k):
    """popcount(X, Count) — Count is the number of set bits in X.

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


def _msb__2_py(x, bit, trail, k):
    """msb(X, Bit) — Bit is the position of the most significant set bit (0-indexed).

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


def _lsb__2_py(x, bit, trail, k):
    """lsb(X, Bit) — Bit is the position of the least significant set bit (0-indexed).

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


# ── C-accelerated wrappers ────────────────────────────────────────────────
#
# Return protocol from C functions:
#   PyLong (mark)  → unify succeeded; yield then trail.undo(mark)
#   None           → no solution
#   False          → Quantity detected; fall back to Python
#   tuple          → between/3 generate mode: (lo, hi)

if _USE_C_ARITH:
    def _between__3_c(low, high, x, trail, k):
        ret = _c_between(low, high, x, trail)
        if ret is None:
            return
        if ret is False:
            yield from _between__3_py(low, high, x, trail, k)
            return
        if isinstance(ret, tuple):
            # Generate mode — C returned (lo, hi)
            lo, hi = ret
            for i in range(lo, hi + 1):
                mark = trail.mark()
                if unify(x, i, trail):
                    yield None
                trail.undo(mark)
            return
        if ret is True:
            # Check mode — x was already bound and in range, no trail to undo
            yield None
            return
        # Check mode with unification — ret is the mark
        yield None
        trail.undo(ret)

    def _succ__2_c(x, y, trail, k):
        ret = _c_succ(x, y, trail)
        if ret is None:
            return
        yield None
        trail.undo(ret)

    def _plus__3_c(x, y, z, trail, k):
        ret = _c_plus(x, y, z, trail)
        if ret is None:
            return
        if ret is False:
            yield from _plus__3_py(x, y, z, trail, k)
            return
        yield None
        trail.undo(ret)

    def _abs__2_c(x, y, trail, k):
        ret = _c_abs(x, y, trail)
        if ret is None:
            return
        if ret is False:
            yield from _abs__2_py(x, y, trail, k)
            return
        yield None
        trail.undo(ret)

    def _max__3_c(x, y, z, trail, k):
        ret = _c_max(x, y, z, trail)
        if ret is None:
            return
        if ret is False:
            yield from _max__3_py(x, y, z, trail, k)
            return
        yield None
        trail.undo(ret)

    def _min__3_c(x, y, z, trail, k):
        ret = _c_min(x, y, z, trail)
        if ret is None:
            return
        if ret is False:
            yield from _min__3_py(x, y, z, trail, k)
            return
        yield None
        trail.undo(ret)

    def _sign__2_c(x, s, trail, k):
        ret = _c_sign(x, s, trail)
        if ret is None:
            return
        if ret is False:
            yield from _sign__2_py(x, s, trail, k)
            return
        yield None
        trail.undo(ret)

    def _gcd__3_c(x, y, g, trail, k):
        ret = _c_gcd(x, y, g, trail)
        if ret is None:
            return
        if ret is False:
            yield from _gcd__3_py(x, y, g, trail, k)
            return
        yield None
        trail.undo(ret)

    def _divmod__4_c(x, y, q, r, trail, k):
        ret = _c_divmod(x, y, q, r, trail)
        if ret is None:
            return
        if ret is False:
            yield from _divmod__4_py(x, y, q, r, trail, k)
            return
        yield None
        trail.undo(ret)

    def _lcm__3_c(x, y, l, trail, k):
        ret = _c_lcm(x, y, l, trail)
        if ret is None:
            return
        if ret is False:
            yield from _lcm__3_py(x, y, l, trail, k)
            return
        yield None
        trail.undo(ret)

    def _expmod__4_c(base, exp, mod, result, trail, k):
        ret = _c_exp_mod(base, exp, mod, result, trail)
        if ret is None:
            return
        yield None
        trail.undo(ret)

    def _popcount__2_c(x, count, trail, k):
        ret = _c_popcount(x, count, trail)
        if ret is None:
            return
        yield None
        trail.undo(ret)

    def _msb__2_c(x, bit, trail, k):
        ret = _c_msb(x, bit, trail)
        if ret is None:
            return
        yield None
        trail.undo(ret)

    def _lsb__2_c(x, bit, trail, k):
        ret = _c_lsb(x, bit, trail)
        if ret is None:
            return
        yield None
        trail.undo(ret)


# ── Register builtins (C-accelerated if available, else Python) ───────────

_arith_cells_to_nodes = None


def _cell_bound_as_node(bound):
    """A between/3 bound written as an arithmetic CELL (``+(1, 2)``, built by
    ``=..`` at runtime) as its operator node, so it evaluates like the node
    (ruling R9 A1); it used to fail silently.  Anything else is unchanged."""
    global _arith_cells_to_nodes
    if type(bound) is not int:
        if _arith_cells_to_nodes is None:
            from clausal.logic.clpfd import _arith_cells_to_nodes as f  # lazy: clpfd is heavy
            _arith_cells_to_nodes = f
        node = _arith_cells_to_nodes(bound)
        if node is not None:
            return node
    return bound


def _between_bound_error(bound):
    """Raise between/3's ISO error for *bound*: an instantiation error when
    it is (or its expression holds) an unbound variable, else
    type_error(integer, Bound) -- for an expression, the term as written."""
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, instantiation_error, type_error)
    from clausal.logic.builtins._helpers import _is_ground  # noqa: PLC0415
    b = deref(bound)
    if is_var(b) or not _is_ground(b):
        raise LogicException(instantiation_error("between/3"))
    raise LogicException(type_error("integer", b, "between/3"))


@_builtin("between", 3)
def _between__3(low, high, x, trail, k):
    # Evaluate expression bounds here, at the dispatch boundary (the same
    # placement as plus/3's A09-F011 guard), so the C fast path and the
    # Python reference implementation see identical already-evaluated ints
    # in both enumeration and check mode.
    low_d = _cell_bound_as_node(deref(low))
    if isinstance(low_d, ARITH_OPERATOR_TERMS):
        low = _eval_between_bound(low_d)
        if low is None:
            _between_bound_error(low_d)
            return
    high_d = _cell_bound_as_node(deref(high))
    if isinstance(high_d, ARITH_OPERATOR_TERMS):
        high = _eval_between_bound(high_d)
        if high is None:
            _between_bound_error(high_d)
            return
    # Scryer's library(between) (must_be/can_be): an unbound bound is an
    # instantiation error, a non-integer bound -- or a bound X that is not an
    # integer -- a type_error(integer, _).  These used to FAIL silently
    # (``between(1, a, X)``, ``between(_, 3, X)``).  A bool is not an
    # integer (A09-F015).  Checked only here, off the answering path's
    # imports.
    for bound in (deref(low), deref(high)):
        if is_var(bound) or not isinstance(bound, int) or isinstance(bound, bool):
            _between_bound_error(bound)
    x_val = deref(x)
    if not is_var(x_val) and (not isinstance(x_val, int)
                              or isinstance(x_val, bool)):
        _between_bound_error(x_val)
    yield from (_between__3_c if _USE_C_ARITH else _between__3_py)(low, high, x, trail, k)

@_builtin("succ", 2)
def _succ__2(x, y, trail, k):
    yield from (_succ__2_c if _USE_C_ARITH else _succ__2_py)(x, y, trail, k)

@_builtin("plus", 3)
def _plus__3(x, y, z, trail, k):
    # A09-F011: guard here so the C fast path (which concatenates strings and
    # raises a raw TypeError on mixed operands) never runs on non-numerics.
    if not _all_known_numeric(deref(x), deref(y), deref(z)):
        return
    yield from (_plus__3_c if _USE_C_ARITH else _plus__3_py)(x, y, z, trail, k)

@_builtin("abs_", 2)
def _abs__2(x, y, trail, k):
    yield from (_abs__2_c if _USE_C_ARITH else _abs__2_py)(x, y, trail, k)

@_builtin("max_", 3)
def _max__3(x, y, z, trail, k):
    if not _all_known_numeric(deref(x), deref(y)):  # A09-F011 (see plus/3)
        return
    yield from (_max__3_c if _USE_C_ARITH else _max__3_py)(x, y, z, trail, k)

@_builtin("min_", 3)
def _min__3(x, y, z, trail, k):
    if not _all_known_numeric(deref(x), deref(y)):  # A09-F011 (see plus/3)
        return
    yield from (_min__3_c if _USE_C_ARITH else _min__3_py)(x, y, z, trail, k)

@_builtin("sign", 2)
def _sign__2(x, s, trail, k):
    yield from (_sign__2_c if _USE_C_ARITH else _sign__2_py)(x, s, trail, k)

@_builtin("gcd", 3)
def _gcd__3(x, y, g, trail, k):
    yield from (_gcd__3_c if _USE_C_ARITH else _gcd__3_py)(x, y, g, trail, k)

@_builtin("divmod_", 4)
def _divmod__4(x, y, q, r, trail, k):
    yield from (_divmod__4_c if _USE_C_ARITH else _divmod__4_py)(x, y, q, r, trail, k)

@_builtin("lcm", 3)
def _lcm__3(x, y, l, trail, k):
    yield from (_lcm__3_c if _USE_C_ARITH else _lcm__3_py)(x, y, l, trail, k)

@_builtin("exp_mod", 4)
def _expmod__4(base, exp, mod, result, trail, k):
    # A09-F012: pow(base, -1, mod) raises a raw ValueError when base has no
    # modular inverse (uncatchable by catch/3). Convert to a typed
    # evaluation_error(undefined) — this covers both the C and Python paths.
    try:
        yield from (_expmod__4_c if _USE_C_ARITH else _expmod__4_py)(base, exp, mod, result, trail, k)
    except ValueError:
        from clausal.logic.exceptions import LogicException, evaluation_error
        raise LogicException(evaluation_error("undefined", "exp_mod/4"))

@_builtin("popcount", 2)
def _popcount__2(x, count, trail, k):
    yield from (_popcount__2_c if _USE_C_ARITH else _popcount__2_py)(x, count, trail, k)

@_builtin("msb", 2)
def _msb__2(x, bit, trail, k):
    yield from (_msb__2_c if _USE_C_ARITH else _msb__2_py)(x, bit, trail, k)

@_builtin("lsb", 2)
def _lsb__2(x, bit, trail, k):
    yield from (_lsb__2_c if _USE_C_ARITH else _lsb__2_py)(x, bit, trail, k)
