"""Exact arithmetic over the engine's number kinds -- ONE spelling, shared by
the interpreted evaluator (``clpfd._eval_ground``) and the compiled tree
(``terms_to_ast.arith_to_ast_expr`` emits ``$add``/``$sub``/``$mul``/``$div``).

Design 2026-09-17 (``docs/superpowers/specs/2026-09-17-rdiv-decimal-arithmetic-design.md``,
step 2) and the rulings of the same day:

* numbers are Python number objects -- ``int``, ``float``, ``Fraction`` (exact
  rational), ``Decimal`` (exact rational with a SCALE) (Q1);
* ``+``, ``-``, ``*`` over Decimals are EXACT and keep scale (a sum carries the
  larger scale, a product the sum of scales).  Python's own Decimal operators
  round to the context precision (28 digits) SILENTLY -- so they are not used;
  the arithmetic is done on ``(mantissa, scale)`` integer pairs;
* ``/`` over an exact operand yields a ``Fraction``, never a Decimal:
  ``Decimal('1') / 3`` has no finite decimal expansion and Python's Decimal
  division would round it -- the standing ruling is that arithmetic IS
  RATIONAL.  ``int / int`` is exact too, on BOTH paths: before this the
  compiled tree divided runtime ints natively and produced a float where the
  interpreted evaluator produced ``Fraction(7, 2)`` (the parked
  "eval_ variable-operand float");
* a Decimal beside a Fraction goes exact-to-exact as a Fraction (scale
  dropped);
* a float beside a Decimal OR a Fraction RAISES ``type_error(exact_number,
  Float)`` (Q5: no implicit coercion, it risks loss of precision; the Fraction
  half landed with step 6, 2026-09-18).

Every helper fast-paths ``int op int`` with two pointer compares; the
compiled tree pays ~30 ns per operator for the call (measured), and exact
``int / int`` ~300 ns for the Fraction -- the price of the ruling, paid on
the compiled path exactly as the interpreted path has always paid it.
Integral results are presented as ``int`` at the tree ROOT by
``present_number`` (``$present``), not here.
"""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

__all__ = ["exact_add", "exact_sub", "exact_mul", "exact_div", "decimal_parts"]


def _float_beside_decimal(f, context: str):
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    return LogicException(type_error(
        "exact_number", f,
        f"{context}: a float beside a Decimal is refused (RULED 2026-09-17 Q5: "
        f"no implicit coercion, it risks loss of precision)"))


def _not_finite(d, context: str):
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    return LogicException(type_error("exact_number", d, f"{context}: not a finite decimal"))


def decimal_parts(d: Decimal) -> tuple[int, int]:
    """``(mantissa, scale)`` with ``d == mantissa * 10**-scale``, exact.
    ``scale`` may be negative for ``1E+5`` (mantissa 1, scale -5)."""
    sign, digits, exp = d.as_tuple()
    m = int("".join(map(str, digits))) if digits else 0
    return (-m if sign else m), -exp


def _from_parts(m: int, scale: int) -> Decimal:
    """The Decimal ``m * 10**-scale``, built from its digit tuple so no
    context rounding can touch it (``Decimal(int).scaleb`` rounds)."""
    return Decimal((1 if m < 0 else 0, tuple(int(c) for c in str(abs(m))), -scale))


def _dec_parts_of(x, context: str) -> "tuple[int, int] | None":
    """Parts of an int or a finite Decimal; None for any other kind."""
    if type(x) is Decimal:
        if not x.is_finite():
            return None
        return decimal_parts(x)
    if isinstance(x, int) and not isinstance(x, bool):
        return x, 0
    return None


def _check_float_beside_fraction(l, r, op: str):
    """Q5 extended to the Fraction (2026-09-18, step 6): a float beside a
    Fraction would silently produce a float -- a CLP(Q) result meeting a float
    threshold is the shape -- and is refused like a float beside a Decimal."""
    if type(l) is Fraction and type(r) is float:
        raise _float_beside_decimal(r, op)
    if type(r) is Fraction and type(l) is float:
        raise _float_beside_decimal(l, op)


def _dec_binop(l, r, op: str):
    """``l op r`` with at least one Decimal operand.  Exact, scale-keeping
    for Decimal/int pairs; a Fraction pulls both sides to Fraction; a float
    raises (Q5)."""
    if type(l) is float or type(r) is float:
        raise _float_beside_decimal(l if type(l) is float else r, op)
    for x in (l, r):
        if type(x) is Decimal and not x.is_finite():
            # NaN / Infinity have no (mantissa, scale); Decimal's own
            # semantics apply (NaN propagates, Infinity absorbs) -- the
            # evaluator refuses them at the LEAF, quantity arithmetic keeps
            # them (tests/test_units_clp.py, round twenty).
            return {"add": l.__add__, "sub": l.__sub__, "mul": l.__mul__}[op](r) if type(l) is Decimal \
                else {"add": r.__radd__, "sub": r.__rsub__, "mul": r.__rmul__}[op](l)
    pl = _dec_parts_of(l, op)
    pr = _dec_parts_of(r, op)
    if pl is None or pr is None:
        # the non-Decimal side is a Fraction (or something arithmetic will
        # refuse on its own): exact-to-exact as a Fraction
        fl = Fraction(l) if type(l) is Decimal else l
        fr = Fraction(r) if type(r) is Decimal else r
        if op == "add":
            return fl + fr
        if op == "sub":
            return fl - fr
        return fl * fr
    (ml, sl), (mr, sr) = pl, pr
    if op == "mul":
        return _from_parts(ml * mr, sl + sr)
    s = max(sl, sr)
    ml *= 10 ** (s - sl)
    mr *= 10 ** (s - sr)
    return _from_parts(ml + mr if op == "add" else ml - mr, s)


def _operand(x, op: str):
    """A tuple operand is either a CANONICAL exact-number cell -- the
    transfer form of a Decimal or a Fraction, which a spelling written in
    source (``decimal(1001, 2)``, ``rdiv(1, 3)``) reaches the compiled tree
    as -- and evaluates as that number, or it is not a number at all and is
    refused LOUDLY.  Found 2026-09-18: ``eval_(decimal(1001, 2) * 2, R)``
    answered the tuple REPEATED, Python's ``tuple * int``, silently, while
    ``is/2`` converted the leaf; an atom cell ``('yes',) * 2`` did the same.
    Python's tuple operators must never see an operand here."""
    if type(x) is tuple:
        from clausal.logic.variables import exact_cell_number  # noqa: PLC0415
        num = exact_cell_number(x)
        if num is None:
            from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
            raise LogicException(type_error("evaluable", x, f"{op}: not a number"))
        return num
    return x


def exact_add(l, r):
    if type(l) is int and type(r) is int:
        return l + r
    l, r = _operand(l, "add"), _operand(r, "add")
    if type(l) is Decimal or type(r) is Decimal:
        return _dec_binop(l, r, "add")
    _check_float_beside_fraction(l, r, "add")
    return l + r


def exact_sub(l, r):
    if type(l) is int and type(r) is int:
        return l - r
    l, r = _operand(l, "sub"), _operand(r, "sub")
    if type(l) is Decimal or type(r) is Decimal:
        return _dec_binop(l, r, "sub")
    _check_float_beside_fraction(l, r, "sub")
    return l - r


def exact_mul(l, r):
    if type(l) is int and type(r) is int:
        return l * r
    l, r = _operand(l, "mul"), _operand(r, "mul")
    if type(l) is Decimal or type(r) is Decimal:
        return _dec_binop(l, r, "mul")
    _check_float_beside_fraction(l, r, "mul")
    return l * r


def exact_div(l, r):
    """True division: rational over exact operands.  ``ZeroDivisionError``
    propagates as it always has on the compiled path (the interpreted
    evaluator screens ``r == 0`` before calling)."""
    if type(l) is int and type(r) is int:
        return Fraction(l, r)
    l, r = _operand(l, "div"), _operand(r, "div")
    if type(l) is int and type(r) is int:
        return Fraction(l, r)
    _check_float_beside_fraction(l, r, "div")
    if type(l) is Decimal or type(r) is Decimal:
        if type(l) is float or type(r) is float:
            raise _float_beside_decimal(l if type(l) is float else r, "div")
        for x in (l, r):
            if type(x) is Decimal and not x.is_finite():
                return l / r            # Decimal's own non-finite semantics
        return Fraction(l) / Fraction(r)
    return l / r
