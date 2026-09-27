"""Exact arithmetic over the engine's number kinds -- ONE spelling, shared by
the interpreted evaluator (``clpfd._eval_ground``) and the compiled tree
(``terms_to_ast.arith_to_ast_expr`` emits ``$add``/``$sub``/``$mul``/``$div``
and, since ruling R9 of 2026-09-27, ``$floordiv``/``$mod``/``$pow``/``$neg``).
It also holds the ONE evaluable functor table (:data:`EVALUABLE`) that the
operator nodes and the plain arithmetic cells both evaluate through, and
``eval_/2``'s runtime evaluator (:func:`evaluate`).

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
from types import MappingProxyType

__all__ = ["exact_add", "exact_sub", "exact_mul", "exact_div", "exact_floordiv",
           "exact_mod", "exact_pow", "exact_neg", "decimal_parts", "EVALUABLE",
           "evaluate"]


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
# ONE table, keyed ``(name, arity)``, for every spelling of arithmetic: the
# operator nodes (``Add`` & co., mapped onto their key by ``node_keys``) and
# the plain cells ``('+', 1, 2)`` that ``=..``/``functor/3``/``copy_term``
# build at runtime.  CLOSED and STATIC: it holds exactly the evaluable
# functors the engine already evaluated through its nodes, under their ISO
# 13211-1 §9 names, and there is no registration API (ISO and Scryer have
# none) -- the mapping is read-only.
#
# The names are the ISO names of the NODE semantics, not the source spellings:
#
# * ``FloorDiv`` (source ``//``) FLOORS, which is ISO ``div/2`` (Cor.2), not
#   ISO ``(//)/2`` -- that one truncates in Scryer and SWI, and the ``.pl``
#   translator already routes it to ``prolog.TruncDiv``.  Aliasing ``//`` onto
#   the floored op would answer ``-7 // 2`` as -4 where Scryer says -3, so
#   ``//`` is left OUT and raises ``type_error(evaluable, (//)/2)``.
# * ``Mod`` (source ``%``) is floored, sign of the divisor: ISO ``mod/2``.
# * ``Pow`` (source ``**``) keeps the node's Python semantics (``2 ** 3`` is
#   the integer 8; Scryer answers 8.0) -- one semantics for both spellings.
#
# ``/`` is exact (a Fraction for int/int, RULED 2026-09-17), as on the nodes.

def exact_floordiv(l, r):
    if type(l) is int and type(r) is int:
        return l // r
    return _operand(l, "div") // _operand(r, "div")


def exact_mod(l, r):
    if type(l) is int and type(r) is int:
        return l % r
    return _operand(l, "mod") % _operand(r, "mod")


def exact_pow(l, r):
    if type(l) is int and type(r) is int:
        return l ** r
    return _operand(l, "pow") ** _operand(r, "pow")


def exact_neg(x):
    if type(x) is int:
        return -x
    return -_operand(x, "neg")


#: Keys whose second operand is a divisor.  The interpreted evaluator
#: (``clpfd._eval_ground``) answers "not yet evaluable" (None) for a zero
#: divisor, as its node arms always did; the compiled tree and ``evaluate``
#: let Python's ``ZeroDivisionError`` propagate, as ``eval_`` always did.
ZERO_DIVISOR_KEYS = frozenset({("/", 2), ("div", 2), ("mod", 2)})

_NODE_KEYS: dict = {}
_KEY_NODES: dict = {}


def node_keys() -> dict:
    """``{operator node class: table key}`` -- every node the evaluator knows.
    Filled lazily: ``clausal.pythonic_ast`` imports back into the engine."""
    if not _NODE_KEYS:
        from clausal.pythonic_ast.nodes import (  # noqa: PLC0415
            Add, Div, FloorDiv, Mod, Mult, Negate, Pow, Sub)
        _NODE_KEYS.update({
            Add: ("+", 2), Sub: ("-", 2), Mult: ("*", 2), Div: ("/", 2),
            FloorDiv: ("div", 2), Mod: ("mod", 2), Pow: ("**", 2),
            Negate: ("-", 1)})
        _KEY_NODES.update({k: c for c, k in _NODE_KEYS.items()})
    return _NODE_KEYS


def key_nodes() -> dict:
    """The inverse of :func:`node_keys`: ``{table key: node class}``."""
    if not _KEY_NODES:
        node_keys()
    return _KEY_NODES


_Compound = None
_Node = None


def cell_key_args(x):
    """``((name, arity), args)`` for a compound CELL or ``Compound``, else None.

    A cell is ``(name, *args)`` with a str name and at least one argument;
    ``('x',)`` is reserved and is not a compound here.  The key is returned
    whether or not it is in :data:`EVALUABLE` -- the caller decides."""
    global _Compound
    if type(x) is tuple:
        if len(x) >= 2 and type(x[0]) is str:
            return (x[0], len(x) - 1), x[1:]
        return None
    if _Compound is None:
        from clausal.terms import Compound  # noqa: PLC0415
        _Compound = Compound
    if isinstance(x, _Compound) and type(x.functor) is str and x.args:
        return (x.functor, len(x.args)), tuple(x.args)
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
    as a number): an atom, a cell, a ``Compound`` or a pythonic-AST node.
    Anything else is a Python value and keeps Python semantics -- including a
    LIST, deliberately: ``eval_`` has always concatenated and repeated Python
    lists (``eval_(L + [3], X)``), and an ISO-strict refusal of lists is a
    separate question from the cells ruling R9 settled."""
    if type(x) is str or type(x) is tuple:
        return True
    global _Compound, _Node
    if _Compound is None:
        from clausal.terms import Compound  # noqa: PLC0415
        _Compound = Compound
    if _Node is None:
        from clausal.pythonic_ast.nodes import Node  # noqa: PLC0415
        _Node = Node
    return isinstance(x, (_Compound, _Node))


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
        from clausal.terms import Compound  # noqa: PLC0415
        culprit = Compound("/", (op, 2 if isinstance(term, BinOp) else 1))
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
    fn = EVALUABLE.get(key)
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


#: The evaluable functor table (see the block comment above ``exact_floordiv``);
#: defined last because it names the four exact operators.
EVALUABLE = MappingProxyType({
    ("+", 2): exact_add, ("-", 2): exact_sub, ("*", 2): exact_mul,
    ("/", 2): exact_div, ("div", 2): exact_floordiv, ("mod", 2): exact_mod,
    ("**", 2): exact_pow, ("-", 1): exact_neg,
})
