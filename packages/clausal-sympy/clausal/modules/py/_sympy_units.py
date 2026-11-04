"""Clausal quantities inside the SymPy wrapper (``clausal.modules.py.sympy``).

A Clausal ``Quantity`` reaches SymPy as its EXACT magnitude (stored in SI base
units) times one positive SymPy symbol per base dimension::

    Quantity(Fraction(2469, 200), {'kelvin': 1})  ->  2469/200 * kelvin
    Quantity(Decimal('0.500'), {'kilogram': 1, 'second': -1})
                                                  ->  1/2 * kilogram / second

SymPy then simplifies and solves over those symbols like any others, so a
root inherits its dimension from the equation (``F*cp*dT - P`` solved for
``F`` is ``P/(cp*dT)``, in kilogram/second).

There is no second unit system here.  The dimension symbols are named by the
atoms that key ``Quantity.dims``, and every dimension judgement is made by
Clausal's own ``Quantity`` arithmetic on unit-magnitude quantities: a sum is
checked by adding ``Quantity(1, dims)`` values, so a mismatch raises the
units system's own ``UnitsMismatch`` (which the engine reports as
``error(system_error(units_mismatch), _)``), and an exponent is checked by
``Quantity.__pow__``.  ``sympy.physics.units`` is not used.

Checks happen in two places:

* while a Clausal term is converted (``check_sum``, ``check_function_args``),
  because SymPy folds ``3*K + 5*Pa - 5*Pa`` to ``3*K`` on construction and a
  later check would never see the mismatch;
* when a result comes back (``result_to_clausal``), because solving can
  introduce one (a root of ``X**2 + X - 1 m`` adds a number to a length).

A ground result comes back as a ``Quantity``: an exact rational magnitude as
an int or ``Fraction``, a float one as a float, and any other real number
(``20/log(3)`` from a log mean temperature difference) as a float, as the
engine's own ``is`` would give for ``log``.  A result that still holds free
variables stays symbolic (a ``SymExpr``) with its dimension symbols, after
the same check.

Literal zero is the one dimension-blind value: SymPy turns ``0 * kelvin`` into
the number ``0``, so a zero is treated as having whatever dimension its sum
needs rather than refusing ``0 K + 3 K``.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any

from clausal.modules.py import _import_stdlib
from clausal.terms import Quantity, UnitsMismatch, _dims_str

_sp = _import_stdlib("sympy")


class _UnitSymbol(_sp.Symbol):
    """The SymPy symbol for one base dimension, named by its Clausal atom.

    A subclass, so it never equals a plain ``Symbol`` of the same name (an
    atom ``kelvin`` written in a term stays an ordinary symbol).  Positive,
    so ``sqrt(kelvin**2)`` is ``kelvin`` and ``x**2 = 4 m**2`` has the two
    roots ``-2 m`` and ``2 m``.
    """

    __slots__ = ()


_UNIT_SYMBOLS: dict[str, _UnitSymbol] = {}


def unit_symbol(atom: str) -> _UnitSymbol:
    symbol = _UNIT_SYMBOLS.get(atom)
    if symbol is None:
        symbol = _UnitSymbol(atom, positive=True)
        _UNIT_SYMBOLS[atom] = symbol
    return symbol


def exact_number_to_sympy(value: Any) -> Any:
    """An exact ``Decimal`` or ``Fraction`` as a SymPy ``Rational`` (a float
    or a non-finite ``Decimal`` as a SymPy ``Float``)."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            return _sp.Float(value)
        value = Fraction(value)
    if isinstance(value, Fraction):
        return _sp.Rational(value.numerator, value.denominator)
    if isinstance(value, bool):
        raise TypeError(f"not a quantity magnitude: {value!r}")
    if isinstance(value, int):
        return _sp.Integer(value)
    if isinstance(value, float):
        return _sp.Float(value)
    raise TypeError(f"not a quantity magnitude: {value!r}")


def quantity_to_sympy(quantity: Quantity) -> Any:
    expr = exact_number_to_sympy(quantity.value)
    for atom, exponent in quantity.dims.items():
        expr = expr * unit_symbol(atom) ** exponent
    return expr


def has_units(expr: Any) -> bool:
    return isinstance(expr, _sp.Basic) and bool(expr.atoms(_UnitSymbol))


# -- Dimension of a SymPy expression, judged by Quantity arithmetic ---------

_DIMENSIONLESS = None  # built lazily: Quantity() touches the units flag

#: Functions whose value has the dimension of their (single) argument, as
#: ``abs`` does for a Quantity.  Every other known function needs a
#: dimensionless argument.
_DIMENSION_PRESERVING = ("Abs",)


def _dimensionless() -> Quantity:
    global _DIMENSIONLESS
    if _DIMENSIONLESS is None:
        _DIMENSIONLESS = Quantity(1, {})
    return _DIMENSIONLESS


def _dimension(expr: Any) -> Quantity | None:
    """``Quantity(1, dims)`` for *expr*'s dimension, or None when it is not
    determined (a free variable, an unknown function, a literal zero).
    Raises ``UnitsMismatch`` where the expression is inconsistent."""
    if isinstance(expr, _UnitSymbol):
        return Quantity(1, {expr.name: 1})
    if expr.is_Number:
        return None if expr.is_zero else _dimensionless()
    if expr.is_NumberSymbol or expr is _sp.S.ImaginaryUnit:
        return _dimensionless()
    if isinstance(expr, _sp.Symbol):
        return None
    if isinstance(expr, _sp.Add):
        return _sum_dimension([_dimension(a) for a in expr.args])
    if isinstance(expr, _sp.Mul):
        result = _dimensionless()
        undetermined = False
        for factor in expr.args:
            d = _dimension(factor)
            if d is None:
                undetermined = True
            elif not undetermined:
                result = result * d
        return None if undetermined else _unit(result)
    if isinstance(expr, _sp.Pow):
        base, exponent = expr.args
        _require_dimensionless("**", _dimension(exponent))
        d = _dimension(base)
        if d is None or not d.dims:
            return d
        # Quantity.__pow__ refuses a non-integer exponent (a square root of
        # a temperature) with the units system's own message; let it.
        return _unit(d ** (int(exponent) if exponent.is_Integer else exponent))
    if isinstance(expr, _sp.Function) and type(expr).__name__ in _DIMENSION_PRESERVING:
        return _dimension(expr.args[0])
    if isinstance(expr, (_sp.Mod, _sp.core.relational.Relational)):
        return _sum_dimension([_dimension(a) for a in expr.args])
    if isinstance(expr, _sp.Function) and _is_known_function(expr):
        for argument in expr.args:
            _require_dimensionless(type(expr).__name__, _dimension(argument))
        return _dimensionless()
    # Anything else (an undefined function, a Derivative, ...): check what
    # is inside, claim nothing about the whole.
    for argument in expr.args:
        if isinstance(argument, _sp.Basic):
            _dimension(argument)
    return None


def _is_known_function(expr: Any) -> bool:
    # An undefined function f(x) is an instance of AppliedUndef; a SymPy
    # library function (log, exp, sin, gamma, ...) is not.
    return not isinstance(expr, _sp.core.function.AppliedUndef)


def _unit(quantity: Quantity) -> Quantity:
    return Quantity(1, dict(quantity.dims))


def _sum_dimension(dimensions: list) -> Quantity | None:
    known = [d for d in dimensions if d is not None]
    if not known:
        return None
    total = known[0]
    for d in known[1:]:
        total = total + d          # Quantity's own check: UnitsMismatch
    return _unit(total)


def _require_dimensionless(name: str, dimension: Quantity | None) -> None:
    if dimension is not None and dimension.dims:
        raise UnitsMismatch(
            f"{name} requires a dimensionless argument; got "
            f"{_dims_str(dimension.dims)}")


# -- Hooks called from the wrapper -------------------------------------------


def check_sum(left: Any, right: Any) -> None:
    """Refuse ``left + right`` (or ``left - right``) across dimensions."""
    if has_units(left) or has_units(right):
        _sum_dimension([_dimension(left), _dimension(right)])


def check_function_args(name: str, args: list) -> None:
    """Refuse a dimensioned argument to a function that needs a number."""
    if not any(has_units(a) for a in args):
        return
    if name == "sqrt":
        # A power: sqrt(4 m**2) is 2 m; a fractional dimension left over is
        # refused when the result is checked.
        return
    if name == "abs":
        for a in args:
            _dimension(a)
        return
    for a in args:
        _require_dimensionless(name, _dimension(a))


def result_to_clausal(expr: Any, symbolic: Any) -> Any:
    """A SymPy result holding dimension symbols, back in Clausal terms.

    Checks the dimension first (``UnitsMismatch`` if inconsistent).  A ground
    result is a ``Quantity``; one with free variables is ``symbolic(expr)``.
    """
    dimension = _dimension(expr)
    if expr.free_symbols - expr.atoms(_UnitSymbol):
        return symbolic(expr)
    magnitude = expr.subs({u: 1 for u in expr.atoms(_UnitSymbol)})
    if dimension is None:
        # Only a literal zero gets here: no dimension to attach.
        if magnitude.is_zero:
            return 0
        raise TypeError(f"undetermined dimension for {expr}")
    return Quantity(_magnitude_to_python(magnitude), dict(dimension.dims))


def _magnitude_to_python(magnitude: Any) -> Any:
    if magnitude.is_Integer:
        return int(magnitude)
    if magnitude.is_Rational:
        return Fraction(int(magnitude.p), int(magnitude.q))
    if magnitude.is_Float:
        return float(magnitude)
    if magnitude.is_number and magnitude.is_extended_real:
        return float(magnitude.evalf(17))
    raise TypeError(f"not a real quantity magnitude: {magnitude}")


def unit_symbol_to_clausal(symbol: _UnitSymbol) -> Quantity:
    return Quantity(1, {symbol.name: 1})
