"""Exact arithmetic over the engine's number kinds -- ONE spelling, shared by
the interpreted evaluator (``clpfd._eval_ground``) and the compiled tree
(``terms_to_ast.arith_to_ast_expr`` emits ``$add``/``$sub``/``$mul``/``$div``).
It also holds the ONE evaluable functor table (:data:`EVALUABLE`) that the
operator nodes and the plain arithmetic cells both evaluate through, and the
runtime evaluator (:func:`evaluate`, emitted as ``$eval``) for ``eval_/2``'s
operand and for a term operand of the bare ``//``, ``%``, ``**``, ``-``.

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

from decimal import Decimal, InvalidOperation
from fractions import Fraction
from types import MappingProxyType

__all__ = ["exact_add", "exact_sub", "exact_mul", "exact_div", "exact_neg",
           "python_floordiv", "python_mod", "python_pow", "iso_intdiv",
           "iso_div", "iso_mod", "iso_pow", "iso_intpow", "iso_abs", "iso_max",
           "iso_min", "decimal_parts",
           "EVALUABLE", "NODE_EVALUABLE",
           "evaluate", "evaluate_python_result"]


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
    """An operand that is not a plain number: EVALUATE it, or refuse it.

    Python's operators must never see a term here.  Found 2026-09-18:
    ``eval_(decimal(1001, 2) * 2, R)`` answered the tuple REPEATED (Python's
    ``tuple * int``) and an atom cell did the same; found 2026-09-27: a
    variable bound to ``+(1, 2)`` -- built by ``=..`` at runtime, or an
    operator node from ``Y is 1 + 2`` -- reached the compiled tree through
    ``$deref`` and raised a raw Python ``TypeError`` or passed through.  So
    every term operand goes to :func:`evaluate`, which knows the one
    evaluable table; a canonical exact-number cell is its number there too.
    A Python value that is not a term (a ``Quantity``, a ``date``) passes
    through to Python's own operators, as it always has.  *op* is unused
    and kept for the call sites' readability."""
    t = type(x)
    if t is int or t is float or t is Fraction or t is Decimal:
        return x
    return evaluate(x)


# ── The evaluable functor table (ruling R9, 2026-09-27) ─────────────────────
#
# ONE table, keyed ``(name, arity)``, for the plain arithmetic CELLS
# ``('+', 1, 2)`` -- a quoted ``'//'(A, B)`` in source, or a cell that
# ``=..``/``functor/3``/``copy_term`` build at runtime.  CLOSED and STATIC:
# there is no registration API (ISO and Scryer have none) -- the mapping is
# read-only.
#
# Operator rulings of 2026-09-28: a QUOTED or cell spelling follows Scryer
# Prolog, while a BARE operator in today's (Python-shaped, seam) source
# syntax keeps Python's meaning.  So the cells and the operator NODES no
# longer share every entry:
#
# * cells, Scryer: ``//`` truncates toward zero (``'//'(-7, 2)`` is -3),
#   ``div`` floors (-4), ``mod`` takes the sign of the divisor, all three on
#   INTEGERS only (``type_error(integer, X)`` otherwise); ``**`` is always a
#   float (``'**'(2, 3)`` is 8.0); ``^`` is the integer power (``'^'(2, 3)``
#   is 8, ``'^'(2, -1)`` is ``type_error(float, 2)``);
# * nodes, Python: ``FloorDiv`` (bare ``//``) is Python's floor division,
#   ``Mod`` (bare ``%``) Python's modulo, ``Pow`` (bare ``**``) Python's
#   power (``2 ** 3`` is the integer 8), ``Div`` (bare ``/``) Python's true
#   division (``7 / 2`` is 3.5, ``6 / 2`` is 3.0; ruling Q15).  They are
#   keyed under private ``$``-names (:data:`NODE_EVALUABLE`) that no cell
#   can spell;
# * the cell ``'/'`` is Scryer's division, always a float; ``rdiv`` is the
#   exact-rational spelling (an exact-number cell, not in this table);
# * ``+``, ``-``, ``*`` and unary ``-`` are shared: exact on both spellings.
#
# INSIDE A CLP POST (``==``, ``<``, ...) ``/`` keeps its RATIONAL meaning,
# :func:`exact_div` (``X == 7 / 2`` is 7 rdiv 2, like Scryer's
# ``{X = 7/2}``): ``clausal.logic.clpfd`` evaluates both ``Div`` and the
# ``'/'`` cell's node through it.
#
# A zero divisor raises ``evaluation_error(zero_divisor)`` naming the
# operator (ISO 9.1.7; Q4 of 2026-09-28) on every spelling -- a bare node
# too, where Python would raise a raw ``ZeroDivisionError``.


def _zero_divisor(op: str):
    from clausal.logic.exceptions import LogicException, evaluation_error  # noqa: PLC0415
    return LogicException(evaluation_error("zero_divisor", f"({op})/2"))


def _undefined(op: str):
    from clausal.logic.exceptions import LogicException, evaluation_error  # noqa: PLC0415
    return LogicException(evaluation_error("undefined", f"({op})/2"))


def _float_overflow(op: str):
    from clausal.logic.exceptions import LogicException, evaluation_error  # noqa: PLC0415
    return LogicException(evaluation_error("float_overflow", f"({op})/2"))


def _type_error(kind: str, culprit, op: str):
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    return LogicException(type_error(kind, culprit, f"({op})/2"))


# -- bare operator nodes: Python semantics -----------------------------------

def python_floordiv(l, r):
    """Bare ``//`` (the ``FloorDiv`` node): Python's floor division.  The
    operands are already values -- evaluated by :func:`evaluate`, or by the
    compiled tree's ``_native_operand``, which leaves a ``++`` escape's
    Python value to Python's own operator."""
    try:
        return l // r
    except ZeroDivisionError:
        raise _zero_divisor("//") from None
    except InvalidOperation:          # Decimal 0 // 0
        if not r:
            raise _zero_divisor("//") from None
        raise


def python_mod(l, r):
    """Bare ``%`` (the ``Mod`` node): Python's modulo (operands as above)."""
    try:
        return l % r
    except ZeroDivisionError:
        raise _zero_divisor("mod") from None
    except InvalidOperation:          # Decimal x % 0
        if not r:
            raise _zero_divisor("mod") from None
        raise


def python_pow(l, r):
    """Bare ``**`` (the ``Pow`` node): Python's power (``2 ** 3`` is 8,
    ``2 ** -1`` is 0.5); ``0 ** -1`` is a zero divisor, as in Python."""
    try:
        return l ** r
    except ZeroDivisionError:
        raise _zero_divisor("**") from None
    except OverflowError:
        raise _float_overflow("**") from None


def python_truediv(l, r):
    """Bare ``/`` (the ``Div`` node) in EVALUATION: Python's true division
    (ruling Q15, 2026-09-28).  ``7 / 2`` is 3.5 and ``6 / 2`` is 3.0 -- only
    int / int becomes a float; exact kinds stay exact where Python keeps
    them: a Fraction over an int or a Fraction is a Fraction, a Decimal over
    an int or a Decimal is Python's Decimal quotient (context precision).
    Where Python has no answer or would mix kinds the engine keeps its
    rules: a Fraction beside a Decimal divides exactly (a Fraction), a float
    beside a Fraction or a Decimal raises type_error(exact_number) (RULED
    2026-09-17 Q5).  A Python value (a Quantity) meets Python's own ``/``.
    Inside a CLP post ``/`` keeps its rational meaning (:func:`exact_div`)."""
    if type(l) is int and type(r) is int:
        if not r:
            raise _zero_divisor("/")
        try:
            return l / r
        except OverflowError:
            raise _float_overflow("/") from None
    l, r = _operand(l, "div"), _operand(r, "div")
    tl, tr = type(l), type(r)
    if tl is int and tr is int:
        return python_truediv(l, r)
    _check_float_beside_fraction(l, r, "div")
    if (tl is Decimal or tr is Decimal) and (tl is float or tr is float):
        raise _float_beside_decimal(l if tl is float else r, "div")
    if (tl is Decimal and tr is Fraction) or (tl is Fraction and tr is Decimal):
        return exact_div(l, r)
    try:
        return l / r
    except ZeroDivisionError:
        raise _zero_divisor("/") from None
    except InvalidOperation:          # Decimal 0 / 0
        if not r:
            raise _zero_divisor("/") from None
        raise
    except OverflowError:
        raise _float_overflow("/") from None


# -- cells: Scryer semantics -------------------------------------------------

def iso_rdiv(l, r):
    """``rdiv/2``: exact rational division, the exact spelling (ruling Q15,
    as Scryer): ``rdiv(7, 2)`` is 7 rdiv 2, ``rdiv(6, 2)`` is 3,
    ``rdiv(rdiv(1, 2), 2)`` is 1 rdiv 4; a float operand is taken at its
    exact value (Scryer: ``7 rdiv 2.0`` is 7 rdiv 2)."""
    (lv, lnum), (rv, rnum) = _real(l), _real(r)
    for v, num in ((lv, lnum), (rv, rnum)):
        if not num:
            raise _type_error("rational", v, "rdiv")
    try:
        lq, rq = Fraction(lv), Fraction(rv)
    except (ValueError, OverflowError):   # inf / nan
        raise _type_error("rational", lv if not isinstance(lv, (int, Fraction)) else rv, "rdiv") from None
    if not rq:
        raise _zero_divisor("rdiv")
    return lq / rq


def iso_truediv(l, r):
    """``'/'/2``: Scryer's division -- always a FLOAT (``'/'(7, 2)`` is 3.5,
    ``'/'(6, 2)`` is 3.0, ``'/'(7 rdiv 2, 2)`` is 1.75); ``rdiv`` is the
    exact-rational spelling.  A Python value (a Quantity) meets Python's
    ``/``."""
    (lv, lnum), (rv, rnum) = _real(l), _real(r)
    if not (lnum and rnum):
        return python_truediv(lv, rv)
    try:
        fl, fr = float(lv), float(rv)
    except OverflowError:
        raise _float_overflow("/") from None
    if not fr:
        raise _zero_divisor("/")
    try:
        return fl / fr
    except OverflowError:
        raise _float_overflow("/") from None


def _presented(x):
    """*x* as the binder would present it: an integral Fraction (a nested
    ``4 / 2`` is ``Fraction(2, 1)``; only the tree ROOT is presented) or a
    Decimal with no decimal places is its int (``present_number``)."""
    t = type(x)
    if t is Fraction or t is Decimal:
        from clausal.logic.variables import present_number  # noqa: PLC0415
        return present_number(x)
    return x


def _int_pair(l, r, op: str):
    """Both operands evaluated and INTEGERS (ISO 9.1.3), else type_error.
    An integral rational counts (``'//'(4 / 2, 1)`` is 2, as in Scryer)."""
    if type(l) is not int:
        l = _presented(evaluate(l))
        if type(l) is not int:
            raise _type_error("integer", l, op)
    if type(r) is not int:
        r = _presented(evaluate(r))
        if type(r) is not int:
            raise _type_error("integer", r, op)
    return l, r


def iso_intdiv(l, r):
    """``'//'/2``: integer division truncating toward zero (-7 // 2 is -3)."""
    l, r = _int_pair(l, r, "//")
    if not r:
        raise _zero_divisor("//")
    q = abs(l) // abs(r)
    return q if (l < 0) == (r < 0) else -q


def iso_div(l, r):
    """``div/2``: integer division rounding toward negative infinity."""
    l, r = _int_pair(l, r, "div")
    if not r:
        raise _zero_divisor("div")
    return l // r


def iso_mod(l, r):
    """``mod/2``: integer modulo, the sign of the divisor."""
    l, r = _int_pair(l, r, "mod")
    if not r:
        raise _zero_divisor("mod")
    return l % r


def _real(x):
    """``(value, is_number)``: *x* evaluated once; a Python value that is not
    a number (a Quantity) comes back with False, to meet Python's operator."""
    t = type(x)
    if t is int or t is float or t is Fraction or t is Decimal:
        return x, True
    x = evaluate(x)
    t = type(x)
    return x, (t is int or t is float or t is Fraction or t is Decimal)


def _float_pow(l, r, op: str):
    """``l ** r`` as floats, with Scryer's errors (ISO 9.3.1)."""
    try:
        fl, fr = float(l), float(r)
    except OverflowError:
        raise _float_overflow(op) from None
    if fl == 0.0 and fr < 0:
        raise _undefined(op)
    if fl < 0 and not fr.is_integer():
        raise _undefined(op)
    try:
        res = fl ** fr
    except OverflowError:
        raise _float_overflow(op) from None
    except ZeroDivisionError:
        raise _undefined(op) from None
    if res in (float("inf"), float("-inf")) and fl not in (float("inf"), float("-inf")):
        raise _float_overflow(op)
    return res


def iso_pow(l, r):
    """``'**'/2``: the power as a FLOAT (``'**'(2, 3)`` is 8.0), as Scryer.
    A Python value (a Quantity) keeps Python's own ``**``."""
    (lv, lnum), (rv, rnum) = _real(l), _real(r)
    if not (lnum and rnum):
        return python_pow(lv, rv)
    return _float_pow(lv, rv, "**")


def iso_intpow(l, r):
    """``^/2``: the integer power (``'^'(2, 3)`` is 8).

    Scryer's rules for an integer base and exponent: a negative exponent is
    ``type_error(float, Base)`` unless the base is 1 or -1, and
    ``evaluation_error(undefined)`` for base 0.  A float operand gives a
    float.  An exact rational or Decimal base with an integer exponent stays
    EXACT (a Fraction; Scryer answers a float -- arithmetic here is
    rational, RULED 2026-09-17): a Decimal base keeps its scale for a
    non-negative exponent (``'^'(1.5, 2)`` is 2.25) and becomes a Fraction
    for a negative one, which has no finite decimal in general."""
    (lv, lnum), (rv, rnum) = _real(l), _real(r)
    if not (lnum and rnum):
        return python_pow(lv, rv)
    # an integral rational is an integer here (``'^'(2, 4 / 2)`` is 8)
    lv, rv = _presented(lv), _presented(rv)
    if type(rv) is int:
        if type(lv) is int:
            if rv >= 0:
                return lv ** rv
            if lv == 1:
                return 1
            if lv == -1:
                return 1 if rv % 2 == 0 else -1
            if lv == 0:
                raise _undefined("^")
            raise _type_error("float", lv, "^")
        if type(lv) is Fraction or type(lv) is Decimal:
            if type(lv) is Decimal and not lv.is_finite():
                raise _not_finite(lv, "^")
            if lv == 0 and rv < 0:
                raise _undefined("^")
            if type(lv) is Decimal and rv >= 0:
                m, s = decimal_parts(lv)
                return _from_parts(m ** rv, s * rv)
            return Fraction(lv) ** rv
    return _float_pow(lv, rv, "^")


def iso_abs(x):
    """``abs/1`` (ISO 9.1.7): the absolute value, in the operand's own kind
    (Scryer: ``abs(-3)`` is 3, ``abs(-3.5)`` is 3.5, an exact rational stays
    exact).  A Python value (a Quantity) meets Python's own ``abs``."""
    if type(x) is int:
        return -x if x < 0 else x
    return abs(_operand(x, "abs"))


def _float_compare_pick(lv, rv, pick_max: bool):
    """Scryer's ``min``/``max`` once a float is involved: the operands are
    compared AS FLOATS; the winner comes back in its own kind, and a tie is
    the float of the second operand for ``max``, of the first for ``min``
    (``max(1, 1.0)`` and ``min(1, 1.0)`` are both 1.0)."""
    try:
        fl, fr = float(lv), float(rv)
    except OverflowError:
        raise _float_overflow("max" if pick_max else "min") from None
    if fl == fr:
        return fr if pick_max else fl
    if pick_max:
        return lv if fl > fr else rv
    return lv if fl < fr else rv


def iso_max(l, r):
    """``max/2`` (ISO Cor.2 9.3.9): the larger operand, in its own kind
    (Scryer: ``max(2, 5)`` is 5, ``max(1, 2.0)`` is 2.0); beside a float the
    comparison is Scryer's, see :func:`_float_compare_pick`."""
    (lv, lnum), (rv, rnum) = _real(l), _real(r)
    if not (lnum and rnum):
        return max(lv, rv)
    if type(lv) is float or type(rv) is float:
        return _float_compare_pick(lv, rv, True)
    return lv if lv > rv else rv


def iso_min(l, r):
    """``min/2`` (ISO Cor.2 9.3.10): the smaller operand, as :func:`iso_max`."""
    (lv, lnum), (rv, rnum) = _real(l), _real(r)
    if not (lnum and rnum):
        return min(lv, rv)
    if type(lv) is float or type(rv) is float:
        return _float_compare_pick(lv, rv, False)
    return lv if lv < rv else rv


def exact_neg(x):
    if type(x) is int:
        return -x
    return -_operand(x, "neg")


_NODE_KEYS: dict = {}
_KEY_NODES: dict = {}


def node_keys() -> dict:
    """``{operator node class: table key}`` -- every node the evaluator
    knows.  A bare ``//``, ``%``, ``**`` has a private ``$``-key (Python
    semantics, :data:`NODE_EVALUABLE`); the ``Iso*`` node classes are what a
    Scryer CELL becomes when a CLP post rewrites it into a node.  Filled
    lazily: ``clausal.pythonic_ast`` imports back into the engine."""
    if not _NODE_KEYS:
        from clausal.pythonic_ast.nodes import (  # noqa: PLC0415
            Add, Div, FloorDiv, IsoDiv, IsoIntDiv, IsoIntPow, IsoMod, IsoPow,
            IsoRdiv, IsoTrueDiv,
            Mod, Mult, Negate, Pow, Sub)
        keys = {Add: ("+", 2), Sub: ("-", 2), Mult: ("*", 2),
                Div: ("$python_div", 2),
                Negate: ("-", 1),
                FloorDiv: ("$python_floordiv", 2), Mod: ("$python_mod", 2),
                Pow: ("$python_pow", 2),
                IsoTrueDiv: ("/", 2), IsoRdiv: ("rdiv", 2),
                IsoIntDiv: ("//", 2), IsoDiv: ("div", 2), IsoMod: ("mod", 2),
                IsoPow: ("**", 2), IsoIntPow: ("^", 2)}
        # the inverse first: _NODE_KEYS non-empty is the "filled" flag
        _KEY_NODES.update({k: c for c, k in keys.items()})
        _NODE_KEYS.update(keys)
    return _NODE_KEYS


def key_nodes() -> dict:
    """The inverse of :func:`node_keys`: ``{table key: node class}``."""
    if not _KEY_NODES:
        node_keys()
    return _KEY_NODES

_Node = None


def cell_key_args(x):
    """``((name, arity), args)`` for a compound CELL, else None.

    A cell is ``(name, *args)`` with a str name and at least one argument;
    ``('x',)`` is reserved and is not a compound here.  The key is returned
    whether or not it is in :data:`EVALUABLE` -- the caller decides."""
    if type(x) is tuple:
        if len(x) >= 2 and type(x[0]) is str:
            return (x[0], len(x) - 1), x[1:]
    return None


def node_key_args(x):
    """``(key, args)`` for an evaluable operator NODE, else None."""
    key = (_NODE_KEYS or node_keys()).get(type(x))
    if key is None:
        return None
    if key[1] == 1:
        return key, (x.operand,)
    return key, (x.left, x.right)


def _is_term(x) -> bool:
    """True for a value that is a TERM (and so must be evaluable to be used
    as a number): an atom, a cell (a declared term such as ``z(1)`` is one; so
    is a string, the ``('$chars', Text)`` carrier) or a pythonic-AST node.
    Every tuple counts, even one without a str head: a tuple is a term (a cell,
    or the ``('$chars', Text)`` string carrier), never a Python value here.
    Anything else is a Python value and keeps Python semantics -- including a
    LIST, deliberately: ``eval_`` has always concatenated and repeated Python
    lists (``eval_(L + [3], X)``), and an ISO-strict refusal of lists is a
    separate question from the cells ruling R9 settled."""
    if type(x) is str or type(x) is tuple:
        return True
    global _Node
    if _Node is None:
        from clausal.pythonic_ast.nodes import Node  # noqa: PLC0415
        _Node = Node
    return isinstance(x, _Node)


def not_evaluable(term, context: str = "eval_/2"):
    """``type_error(evaluable, Name/Arity)`` for *term* (ISO 13211-1 7.9.2).

    An operator node the table does not know (``5 & 3``, ``~5``, ``+3``) is
    named by its operator and operand count -- ``(&)/2`` -- rather than by
    its dataclass (``'BitAnd'/3``, which counts the position field): the
    culprit names what the user wrote."""
    from clausal.logic.builtins.iso_compare import _evaluable_culprit  # noqa: PLC0415
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    from clausal.pythonic_ast.nodes import BinOp, UnaryOp  # noqa: PLC0415
    op = getattr(type(term), "op", None)
    if type(op) is str and isinstance(term, (BinOp, UnaryOp)):
        culprit = ("/", op, 2 if isinstance(term, BinOp) else 1)
    else:
        culprit = _evaluable_culprit(term)
    return LogicException(type_error("evaluable", culprit, context))


_deref = _is_var = _exact_cell_number = None


def _bind_variables() -> None:
    """Bind the variable-layer helpers once (``clausal.logic.variables``
    imports this module's neighbours; binding at first use avoids the cycle
    without an import statement per evaluated operand)."""
    global _deref, _is_var, _exact_cell_number
    from clausal.logic.variables import deref, exact_cell_number, is_var  # noqa: PLC0415
    _deref, _is_var, _exact_cell_number = deref, is_var, exact_cell_number


def evaluate_python_result(x, context: str = "eval_/2"):
    """:func:`evaluate` for the result of a QUALIFIED call (``os.getcwd()``,
    ``math.sqrt(X)``): a ``str`` there is Python's string, not an atom, and
    passes through as it always did; a term result (a qualified term
    constructor's cell) is evaluated or refused like any other term."""
    if type(x) is str:
        return x
    return evaluate(x, context)


def evaluate(x, context: str = "eval_/2"):
    """Evaluate the arithmetic TERM *x* to a number -- ``eval_/2``'s evaluator.

    * a number is itself (an integral result is presented as int by the
      caller's ``$present``);
    * an unbound variable raises ``instantiation_error`` (ISO 9.1.1);
    * an operator node or a cell whose ``name/arity`` is in
      :data:`EVALUABLE` applies that entry to its evaluated arguments; a
      canonical exact-number cell (``rdiv/2``, ``decimal/2``) is its number;
    * any other TERM -- an atom, a non-evaluable compound -- raises
      ``type_error(evaluable, Name/Arity)``, where it used to be handed back
      unevaluated (ruling R9 A2);
    * a Python value that is not a term (a ``Quantity``, a ``date``, a
      ``bool``, a list) passes through, to meet Python's operators as before.
    """
    if _deref is None:
        _bind_variables()
    x = _deref(x)
    t = type(x)
    if t is int or t is float or t is Fraction or t is Decimal:
        return x
    if _is_var(x):
        from clausal.logic.exceptions import LogicException, instantiation_error  # noqa: PLC0415
        raise LogicException(instantiation_error(context))
    ka = node_key_args(x)
    if ka is None:
        if t is tuple:
            num = _exact_cell_number(x)
            if num is not None:
                return num
        ka = cell_key_args(x)
        if ka is None:
            if _is_term(x):
                raise not_evaluable(x, context)
            return x
    key, args = ka
    fn = EVALUABLE.get(key) if t is tuple else NODE_EVALUABLE.get(key)
    if fn is None:
        raise not_evaluable(x, context)
    return fn(*[evaluate(a, context) for a in args])


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
    """True division: rational over exact operands.  A zero divisor raises
    ``evaluation_error(zero_divisor)`` (Q4, 2026-09-28)."""
    if type(l) is int and type(r) is int:
        if r:
            return Fraction(l, r)
        raise _zero_divisor("/")
    l, r = _operand(l, "div"), _operand(r, "div")
    if type(l) is int and type(r) is int:
        if r:
            return Fraction(l, r)
        raise _zero_divisor("/")
    try:
        return _exact_div_general(l, r)
    except ZeroDivisionError:
        raise _zero_divisor("/") from None


def _exact_div_general(l, r):
    _check_float_beside_fraction(l, r, "div")
    if type(l) is Decimal or type(r) is Decimal:
        if type(l) is float or type(r) is float:
            raise _float_beside_decimal(l if type(l) is float else r, "div")
        for x in (l, r):
            if type(x) is Decimal and not x.is_finite():
                return l / r            # Decimal's own non-finite semantics
        return Fraction(l) / Fraction(r)
    return l / r


#: The evaluable functor table for CELLS (see the block comment above
#: ``python_floordiv``); defined last because it names the exact operators.
EVALUABLE = MappingProxyType({
    ("+", 2): exact_add, ("-", 2): exact_sub, ("*", 2): exact_mul,
    ("/", 2): iso_truediv, ("-", 1): exact_neg,
    ("//", 2): iso_intdiv, ("div", 2): iso_div, ("mod", 2): iso_mod,
    ("**", 2): iso_pow, ("^", 2): iso_intpow, ("rdiv", 2): iso_rdiv,
    # ISO 9.1.7 abs/1; ISO Cor.2 9.3.9-10 max/2, min/2 (Scryer's kinds)
    ("abs", 1): iso_abs, ("max", 2): iso_max, ("min", 2): iso_min,
})

#: :data:`EVALUABLE` plus the bare operator nodes' private Python-semantics
#: entries -- what a NODE evaluates through.  A cell never looks here.
NODE_EVALUABLE = MappingProxyType({
    **EVALUABLE,
    ("$python_div", 2): python_truediv,
    ("$python_floordiv", 2): python_floordiv, ("$python_mod", 2): python_mod,
    ("$python_pow", 2): python_pow,
})
