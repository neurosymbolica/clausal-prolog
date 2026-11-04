"""Clausal quantities inside the SymPy wrapper (``clausal.modules.py.sympy``).

A Clausal ``Quantity`` reaches SymPy as its EXACT magnitude (stored in SI base
units) times one positive SymPy symbol per base dimension::

    Quantity(Fraction(2469, 200), {'kelvin': 1})  ->  2469/200 * kelvin
    Quantity(Decimal('0.500'), {'kilogram': 1, 'second': -1})
                                                  ->  1/2 * kilogram / second

SymPy then simplifies and solves over those symbols like any others, so a
root inherits its dimension from the equation (``F*cp*dT - P`` solved for
``F`` is ``P/(cp*dT)``, in kilogram/second).  The dimension symbols are
constants, never variables: ``free_variables`` leaves them out, so ``diff``,
``integrate``, ``degree``, ``free_vars`` and the renaming in ``sym_equal``
never treat ``kelvin`` as "the variable".

There is no second unit system here.  The dimension symbols are named by the
atoms that key ``Quantity.dims``, and every dimension judgement is made by
Clausal's own ``Quantity`` arithmetic on unit-magnitude quantities: a sum is
checked by adding ``Quantity(1, dims)`` values, so a mismatch raises the
units system's own ``UnitsMismatch`` (which the engine reports as
``error(system_error(units_mismatch), _)``), and an exponent is checked by
``Quantity.__pow__``.  ``sympy.physics.units`` is not used.

Where the dimensions are judged
-------------------------------
* On the CLAUSAL term, before SymPy sees it (``check_terms``).  SymPy folds
  ``5(pascal) - 5(pascal)`` and ``0 * 5(pascal)`` to the number 0, which has no dimension,
  so a check on SymPy's expression could not refuse ``3(kelvin) + (5(pascal) - 5(pascal))``.
  The walk carries every subterm's dimension.  A plain number is
  dimensionless (as in the engine, where ``0 + 3(kelvin)`` is a mismatch).  A
  variable's dimension is unknown, written as a power of the variable; a
  sum whose terms share the same unknown part must agree on the known part
  (``X*1(kelvin) + X*1(pascal)`` is refused), and any other sum states a constraint on
  the variables (``X - 3(kelvin)`` says X is a temperature).
* On every RESULT (``result_to_clausal``), because solving can introduce a
  mismatch (a root of ``X**2 + X - 1(metre)`` adds a number to a length).

What comes back
---------------
A ground result is a Clausal quantity:

* an exact rational magnitude is a ``Quantity`` with an int or ``Fraction``
  magnitude; a float magnitude is a ``Quantity`` with a float;
* any other exact real magnitude (``sqrt(2)``, ``20/log(3)``) stays EXACT, as
  the Clausal arithmetic term ``Magnitude * Quantity(1, dims)``, e.g.
  ``2**(1/2) * 1 (metre)``.  Comparison evaluates it; ``V is R`` (the seam's
  ``eval_(R, V)``) gives the decimal ``Quantity`` when one is wanted, and a
  further sympy call reads it back exactly;
* a zero keeps the dimension the operation implies: the input's for
  ``simplify``/``expand``/``factor`` (``3(kelvin) - 3(kelvin)`` is ``0(kelvin)``), the
  variable's (from the constraints above) for a root of ``solve``;
* a complex, infinite or NaN magnitude is refused with
  ``evaluation_error(undefined)``; ``solve``, ``solve_all`` and ``roots``
  of an equation holding a quantity return the REAL roots only.

A result that still holds free variables stays symbolic (a ``SymExpr``)
with its dimension symbols, which print as ``(kelvin)`` so they cannot be
mistaken for the atom ``kelvin``.
"""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction
from typing import Any, Callable

from clausal.logic.cells import is_chars
from clausal.logic.exceptions import LogicException, evaluation_error
from clausal.logic.variables import is_var
from clausal.modules.py import _import_stdlib
from clausal.terms import (
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate,
    Quantity, UnitsMismatch, _dims_str,
)
from clausal.terms import plain_deref as deref

_sp = _import_stdlib("sympy")


class _UnitSymbol(_sp.Symbol):
    """The SymPy symbol for one base dimension, named by its Clausal atom.

    A subclass, so it never equals a plain ``Symbol`` of the same name (an
    atom ``kelvin`` written in a term stays an ordinary symbol).  Positive,
    so ``sqrt(kelvin**2)`` is ``kelvin`` and ``x**2 = 4(metre**2)`` has the two
    roots ``-2(metre)`` and ``2(metre)``.  Prints as ``(kelvin)``, the way a Clausal
    quantity prints its unit.
    """

    __slots__ = ()

    def _sympystr(self, printer) -> str:
        return f"({self.name})"

    def _latex(self, printer) -> str:
        return r"\mathrm{%s}" % self.name.replace("_", r"\_")


_UNIT_SYMBOLS: dict[str, _UnitSymbol] = {}


def unit_symbol(atom: str) -> _UnitSymbol:
    symbol = _UNIT_SYMBOLS.get(atom)
    if symbol is None:
        symbol = _UnitSymbol(atom, positive=True)
        _UNIT_SYMBOLS[atom] = symbol
    return symbol


def has_units(expr: Any) -> bool:
    return isinstance(expr, _sp.Basic) and bool(expr.atoms(_UnitSymbol))


def free_variables(expr: Any) -> set:
    """``expr.free_symbols`` without the dimension symbols: the variables."""
    return {s for s in expr.free_symbols if not isinstance(s, _UnitSymbol)}


def _undefined() -> LogicException:
    return LogicException(evaluation_error("undefined"))


# -- Into SymPy --------------------------------------------------------------


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
    """Magnitude times dimension symbols.  An infinite or NaN magnitude is
    refused: SymPy folds ``oo * metre`` to ``oo`` and the dimension is lost."""
    value = quantity.value
    if isinstance(value, Decimal) and not value.is_finite():
        raise _undefined()
    if isinstance(value, float) and not math.isfinite(value):
        raise _undefined()
    expr = exact_number_to_sympy(value)
    for atom, exponent in quantity.dims.items():
        expr = expr * unit_symbol(atom) ** exponent
    return expr


# -- Dimensions: a known part (a unit Quantity) times powers of unknowns ----


class Dimension:
    """``known * prod(variable ** exponent)``.  ``known`` is ``Quantity(1,
    dims)``; ``unknown`` maps a SymPy symbol (a variable) to its exponent.
    ``None`` in place of a Dimension means undetermined (an unknown function,
    a symbol named by an atom)."""

    __slots__ = ("known", "unknown")

    def __init__(self, known: Quantity, unknown: dict | None = None) -> None:
        self.known = known
        self.unknown = {s: e for s, e in (unknown or {}).items() if e != 0}

    @property
    def signature(self) -> frozenset:
        return frozenset(self.unknown.items())


def _unit(dims) -> Quantity:
    return Quantity(1, dict(dims))


def dimensionless() -> Dimension:
    return Dimension(_unit({}))


def _variable(symbol) -> Dimension:
    return Dimension(_unit({}), {symbol: 1})


def _product(a: Dimension | None, b: Dimension | None, sign: int = 1) -> Dimension | None:
    if a is None or b is None:
        return None
    known = a.known * b.known if sign > 0 else a.known / b.known
    if not isinstance(known, Quantity):     # units that cancel give a number
        known = _unit({})
    unknown = dict(a.unknown)
    for s, e in b.unknown.items():
        unknown[s] = unknown.get(s, 0) + sign * e
    return Dimension(_unit(known.dims), unknown)


def _power(base: Dimension | None, exponent_dimension: Dimension | None,
           exponent: Any, analysis: "Analysis") -> Dimension | None:
    require_dimensionless("**", exponent_dimension, analysis)
    if base is None:
        return None
    if not base.known.dims and not base.unknown:
        return base
    if exponent is not None and getattr(exponent, "is_Rational", False):
        ratio = Fraction(int(exponent.p), int(exponent.q))
        dims = {}
        for atom, e in base.known.dims.items():
            scaled = e * ratio
            if scaled.denominator != 1:
                # Quantity.__pow__ refuses a non-integer exponent with the
                # units system's own message; let it.
                base.known ** exponent
                raise UnitsMismatch(
                    f"Exponent must be an integer constant for dimensional "
                    f"quantities, got {exponent}")
            dims[atom] = int(scaled)
        unknown = {}
        for s, e in base.unknown.items():
            scaled = e * ratio
            if scaled.denominator != 1:
                return None
            unknown[s] = int(scaled)
        return Dimension(_unit(dims), unknown)
    # A symbolic or float exponent: only a dimensionless base allows it.
    if base.known.dims:
        base.known ** exponent          # raises UnitsMismatch
    return None


class Analysis:
    """Constraints met while walking: ``prod(var ** e) == known``."""

    __slots__ = ("constraints",)

    def __init__(self) -> None:
        self.constraints: list[tuple[dict, Quantity]] = []

    def sum(self, dimensions: list) -> Dimension | None:
        determined = [d for d in dimensions if d is not None]
        if not determined:
            return None
        groups: dict[frozenset, Dimension] = {}
        for d in determined:
            first = groups.get(d.signature)
            if first is None:
                groups[d.signature] = d
            else:
                first.known + d.known      # Quantity's own check: UnitsMismatch
        representatives = list(groups.values())
        head = representatives[0]
        for other in representatives[1:]:
            # head.known * head.unknown == other.known * other.unknown
            unknown = dict(other.unknown)
            for s, e in head.unknown.items():
                unknown[s] = unknown.get(s, 0) - e
            ratio = head.known / other.known
            known = ratio if isinstance(ratio, Quantity) else _unit({})
            self.constraints.append(
                ({s: e for s, e in unknown.items() if e}, _unit(known.dims)))
        return head

    def dimension_of(self, symbol) -> Quantity | None:
        """The dimension the constraints give *symbol* (``Quantity(1,
        dims)``), or None if they say nothing about it alone."""
        found = None
        for unknown, known in self.constraints:
            if set(unknown) != {symbol}:
                continue
            n = unknown[symbol]
            dims = {}
            for atom, e in known.dims.items():
                if e % n:
                    raise UnitsMismatch(
                        f"no dimension of {symbol} satisfies {symbol}**{n} = "
                        f"{_dims_str(known.dims)}")
                dims[atom] = e // n
            candidate = _unit(dims)
            if found is None:
                found = candidate
            else:
                found + candidate          # two constraints disagree
        return found


def require_dimensionless(name: str, dimension: Dimension | None,
                          analysis: Analysis) -> None:
    if dimension is None:
        return
    if dimension.unknown:
        # prod(var ** e) * known == 1
        inverse = _unit({}) / dimension.known
        known = inverse if isinstance(inverse, Quantity) else _unit({})
        analysis.constraints.append((dict(dimension.unknown), _unit(known.dims)))
        return
    if dimension.known.dims:
        raise UnitsMismatch(
            f"{name} requires a dimensionless argument; got "
            f"{_dims_str(dimension.known.dims)}")


#: Clausal function names whose value has their argument's dimension.
_PRESERVING_NAMES = ("abs",)
#: The same, as SymPy class names.
_PRESERVING_CLASSES = ("Abs",)


def term_dimension(term: Any, analysis: Analysis, *,
                   symbol_for_var: Callable, to_sympy: Callable,
                   known_functions) -> Dimension | None:
    """The dimension of a CLAUSAL term, carried node by node (before SymPy
    can fold anything).  Raises ``UnitsMismatch``."""
    def walk(t):
        t = deref(t)
        if is_var(t):
            return _variable(symbol_for_var(t))
        if isinstance(t, Quantity):
            return Dimension(_unit(t.dims))
        if isinstance(t, (bool, int, float, Decimal, Fraction)):
            return dimensionless()
        if is_chars(t) or isinstance(t, str):
            return None
        if isinstance(t, (Add, Sub)):
            return analysis.sum([walk(t.left), walk(t.right)])
        if isinstance(t, Mod):
            return analysis.sum([walk(t.left), walk(t.right)])
        if isinstance(t, FloorDiv):
            analysis.sum([walk(t.left), walk(t.right)])
            return dimensionless()
        if isinstance(t, Mult):
            return _product(walk(t.left), walk(t.right))
        if isinstance(t, Div):
            return _product(walk(t.left), walk(t.right), -1)
        if isinstance(t, Negate):
            return walk(t.operand)
        if isinstance(t, Pow):
            base, exponent = walk(t.left), walk(t.right)
            return _power(base, exponent, to_sympy(t.right), analysis)
        if type(t) is tuple and len(t) >= 2 and type(t[0]) is str:
            name, args = t[0], [walk(a) for a in t[1:]]
            if name == "sqrt" and len(args) == 1:
                return _power(args[0], dimensionless(), _sp.Rational(1, 2), analysis)
            if name in _PRESERVING_NAMES and len(args) == 1:
                return args[0]
            if name in known_functions:
                for a in args:
                    require_dimensionless(name, a, analysis)
                return dimensionless()
            return None                    # an unknown function
        return sympy_dimension(to_sympy(t), analysis)
    return walk(term)


def sympy_dimension(expr: Any, analysis: Analysis) -> Dimension | None:
    """The dimension of a SymPy expression.  A SymPy zero is undetermined:
    it may be a folded ``5(pascal) - 5(pascal)``."""
    if isinstance(expr, _UnitSymbol):
        return Dimension(_unit({expr.name: 1}))
    if expr.is_Number:
        return None if (expr.is_zero or not expr.is_finite) else dimensionless()
    if expr.is_NumberSymbol or expr is _sp.S.ImaginaryUnit:
        return dimensionless()
    if isinstance(expr, _sp.Symbol):
        return _variable(expr)
    if isinstance(expr, _sp.Add):
        return analysis.sum([sympy_dimension(a, analysis) for a in expr.args])
    if isinstance(expr, _sp.Mul):
        result = dimensionless()
        for factor in expr.args:
            d = sympy_dimension(factor, analysis)
            result = _product(result, d) if result is not None else None
        return result
    if isinstance(expr, _sp.Pow):
        base, exponent = expr.args
        return _power(sympy_dimension(base, analysis),
                      sympy_dimension(exponent, analysis),
                      exponent if exponent.is_Number else None, analysis)
    if isinstance(expr, _sp.Function) and type(expr).__name__ in _PRESERVING_CLASSES:
        return sympy_dimension(expr.args[0], analysis)
    if isinstance(expr, (_sp.Mod, _sp.core.relational.Relational)):
        return analysis.sum([sympy_dimension(a, analysis) for a in expr.args])
    if isinstance(expr, _sp.Function) and not isinstance(
            expr, _sp.core.function.AppliedUndef):
        for argument in expr.args:
            require_dimensionless(type(expr).__name__,
                                  sympy_dimension(argument, analysis), analysis)
        return dimensionless()
    # Anything else (an undefined function, a Derivative, ...): check what
    # is inside, claim nothing about the whole.
    for argument in expr.args:
        if isinstance(argument, _sp.Expr):
            sympy_dimension(argument, analysis)
    return None


def same_dimension(first: Dimension | None, second: Dimension | None) -> None:
    """Refuse two values of different dimensions where one is required
    (``gcd``, ``lcm``, ``sym_equal``)."""
    Analysis().sum([first, second])


# -- Back to Clausal ---------------------------------------------------------


def real_magnitude(expr: Any) -> Any:
    return expr.subs({u: 1 for u in expr.atoms(_UnitSymbol)})


def is_possibly_real(root: Any) -> bool:
    """False only for a root SymPy knows is not real (``2*I*metre``)."""
    return real_magnitude(root).is_extended_real is not False


def result_to_clausal(expr: Any, symbolic: Callable, exact_term: Callable,
                      expected: Quantity | None = None) -> Any:
    """A SymPy result, back in Clausal terms, with its dimension checked.

    *expected* is the dimension the operation implies (``Quantity(1,
    dims)``), used for a zero and checked against a non-zero.  A ground
    result is a quantity (see the module docstring); one with free variables
    is ``symbolic(expr)``.  *exact_term* turns an exact SymPy number into a
    Clausal arithmetic term.
    """
    analysis = Analysis()
    dimension = sympy_dimension(expr, analysis)
    if free_variables(expr):
        return symbolic(expr)
    if dimension is None and not expr.is_zero:
        # An unknown function of a quantity, f(3(kelvin)): keep it symbolic.
        if expr.is_number is False or expr.atoms(_sp.core.function.AppliedUndef):
            return symbolic(expr)
    magnitude = real_magnitude(expr)
    if magnitude.is_finite is False or magnitude.is_extended_real is False \
            or magnitude is _sp.nan:
        raise _undefined()
    if dimension is not None:
        dims = dict(dimension.known.dims)
        if expected is not None:
            dimension.known + expected     # the operation's own dimension
    elif expected is not None:
        dims = dict(expected.dims)
    else:
        dims = {}
    if not dims:
        if magnitude.is_Integer:
            return int(magnitude)
        return symbolic(magnitude) if not magnitude.is_Float else float(magnitude)
    if magnitude.is_Integer:
        return Quantity(int(magnitude), dims)
    if magnitude.is_Rational:
        return Quantity(Fraction(int(magnitude.p), int(magnitude.q)), dims)
    if magnitude.is_Float:
        return Quantity(float(magnitude), dims)
    # Exact but not rational (sqrt(2), 20/log(3)): keep it exact.
    return Mult(left=exact_term(magnitude), right=Quantity(1, dims))


def unit_symbol_to_clausal(symbol: _UnitSymbol) -> Quantity:
    return Quantity(1, {symbol.name: 1})
