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
* any other real magnitude (``sqrt(2)``, ``20/log(3)``, a ``LambertW``
  root) is a float ``Quantity`` (operator ruling 2026-11-04; the switch
  EXACT_IRRATIONAL_RESULTS brings back the exact arithmetic term
  ``Magnitude * Quantity(1, dims)``);
* a zero keeps the dimension the operation implies: the input's for
  ``simplify``/``expand``/``factor`` (``3(kelvin) - 3(kelvin)`` is
  ``0(kelvin)``), the variable's (from the constraints above) for a root of
  ``solve``; a zero SymPy makes later (``subs``, ``limit``) does not;
* a complex, infinite or NaN value is refused with
  ``evaluation_error(undefined)``; ``solve``, ``solve_all`` and ``roots``
  of an equation holding a quantity return its REAL roots (``real_roots``),
  and SymPy giving up is ``system_error(no_symbolic_solution)``;
* functions are classified by name (``_function_dimension``): a quantity
  inside one the wrapper does not know is refused, never stripped.

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
from clausal.logic.exceptions import LogicException, evaluation_error, system_error
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
        # A known representative first: the sum's dimension is then known.
        representatives.sort(key=lambda d: bool(d.unknown))
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


# -- Functions ---------------------------------------------------------------
#
# Every function the wrapper can build is in exactly one class, by name (the
# Clausal functor, or the SymPy class name of what it becomes):
#
# * DIMENSION-PRESERVING: abs, max, min, hypot.  All arguments must share
#   one dimension, and the value has it.
# * SAME DIMENSION IN, DIMENSIONLESS OUT: atan2 (an angle from two lengths).
# * ANY DIMENSION IN, DIMENSIONLESS OUT: sign.
# * POWERS: sqrt (1/2), cbrt (1/3) and ``^`` (as ``**``).
# * Everything else NEEDS DIMENSIONLESS ARGUMENTS and gives a dimensionless
#   value: the wrapper's own functions (log, exp, sin, ..., floor, ceiling,
#   gamma, factorial), SymPy's other functions, and any name the wrapper
#   does not know (log10, log2, sinh, cosh, tanh, f, ...), which SymPy keeps
#   as an undefined function.  A quantity inside an unknown function is
#   therefore REFUSED with units_mismatch: its dimension cannot be judged,
#   and putting the magnitude back without its unit would be wrong.

_PRESERVING_NAMES = frozenset({"abs", "Abs", "max", "Max", "min", "Min", "hypot"})
_SAME_DIMENSION_TO_DIMENSIONLESS = frozenset({"atan2"})
_ANY_DIMENSION_TO_DIMENSIONLESS = frozenset({"sign"})
_POWER_NAMES = {"sqrt": _sp.Rational(1, 2), "cbrt": _sp.Rational(1, 3)}


def _function_dimension(name: str, args: list, analysis: "Analysis") -> Dimension | None:
    if name in _POWER_NAMES and len(args) == 1:
        return _power(args[0], dimensionless(), _POWER_NAMES[name], analysis)
    if name in _PRESERVING_NAMES:
        return analysis.sum(args)
    if name in _SAME_DIMENSION_TO_DIMENSIONLESS:
        analysis.sum(args)
        return dimensionless()
    if name in _ANY_DIMENSION_TO_DIMENSIONLESS:
        return dimensionless()
    for a in args:
        require_dimensionless(f"{name}/{len(args)}", a, analysis)
    return dimensionless()


def term_dimension(term: Any, analysis: Analysis, *,
                   symbol_for_var: Callable, to_sympy: Callable) -> Dimension | None:
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
            if t[0] == "^" and len(t) == 3:
                return _power(walk(t[1]), walk(t[2]), to_sympy(t[2]), analysis)
            return _function_dimension(t[0], [walk(a) for a in t[1:]], analysis)
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
    if isinstance(expr, (_sp.Mod, _sp.core.relational.Relational)):
        return analysis.sum([sympy_dimension(a, analysis) for a in expr.args])
    if isinstance(expr, (_sp.Function, _sp.Max, _sp.Min)):
        return _function_dimension(
            type(expr).__name__,
            [sympy_dimension(a, analysis) for a in expr.args], analysis)
    # Anything else (a Derivative, an Integral, ...): check what is inside,
    # claim nothing about the whole.
    for argument in expr.args:
        if isinstance(argument, _sp.Expr):
            sympy_dimension(argument, analysis)
    return None


def same_dimension(first: Dimension | None, second: Dimension | None) -> None:
    """Refuse two values of different dimensions where one is required
    (``gcd``, ``lcm``, ``sym_equal``)."""
    Analysis().sum([first, second])


# -- Magnitudes ---------------------------------------------------------------


def real_magnitude(expr: Any) -> Any:
    return expr.subs({u: 1 for u in expr.atoms(_UnitSymbol)})


def _unit_product(dims) -> Any:
    product = _sp.Integer(1)
    for atom, exponent in dims.items():
        product = product * unit_symbol(atom) ** exponent
    return product


# -- Real values -------------------------------------------------------------
#
# A quantity is real.  Where SymPy cannot say whether a magnitude is real
# (a cubic's three real roots written with complex radicals, a LambertW
# branch), it is evaluated to NUMERIC_DIGITS significant digits and kept iff
# its imaginary part is negligible RELATIVE to its size; the value is then
# the real part, a float.  "Negligible" is set by the input's precision:
# EXACT_TOLERANCE when every number in it is exact, FLOAT_TOLERANCE when a
# float is in it (a float carries ~16 digits, so SymPy's answer does too).

NUMERIC_DIGITS = 50
EXACT_TOLERANCE = _sp.Float("1e-25", NUMERIC_DIGITS)
FLOAT_TOLERANCE = _sp.Float("1e-12", NUMERIC_DIGITS)


def tolerance_for(*exprs: Any) -> Any:
    return FLOAT_TOLERANCE if any(e.has(_sp.Float) for e in exprs) else EXACT_TOLERANCE


def _negligible(small: Any, scale: Any, tolerance: Any) -> bool:
    """``|small| <= tolerance * |scale|`` (exactly zero when scale is 0)."""
    return abs(small) <= tolerance * abs(scale)


def real_value(magnitude: Any, tolerance: Any = None) -> Any:
    """*magnitude* (no dimension symbols, no variables) as a real SymPy
    number: itself when SymPy knows it is real, else its numeric real part
    when the imaginary part is negligible relative to the whole.  None when
    it is not real, or not finite."""
    if tolerance is None:
        tolerance = tolerance_for(magnitude)
    if magnitude is _sp.nan or magnitude.is_finite is False:
        return None
    real = magnitude.is_extended_real
    if real is False:
        return None
    if real is True and not magnitude.has(_sp.I):
        return magnitude
    if magnitude.has(_sp.core.function.AppliedUndef):
        return magnitude                   # f(3): nothing to evaluate
    numeric = _sp.N(magnitude, NUMERIC_DIGITS)
    if not numeric.is_number:
        return magnitude if real is True else None
    re_part, im_part = numeric.as_real_imag()
    if not (re_part.is_finite and im_part.is_finite):
        return None
    if not _negligible(im_part, _sp.sqrt(re_part ** 2 + im_part ** 2), tolerance):
        return None
    return _sp.Float(re_part, NUMERIC_DIGITS)


def _is_exact_real(magnitude: Any) -> bool:
    """A root SymPy gives exactly and knows is real: correct by
    construction, so it is not substituted back."""
    return (magnitude.is_extended_real is True and not magnitude.has(_sp.I)
            and not magnitude.has(_sp.Float)
            and not magnitude.has(_sp.core.function.AppliedUndef))


def _satisfies(equation_magnitude: Any, symbol: Any, numeric: Any, tolerance: Any) -> bool:
    """The equation's residual at *numeric* is negligible RELATIVE to the
    size of its own terms there: |sum t_i| <= tolerance * sum |t_i|.  So the
    test does not depend on the scale of the root or of the coefficients."""
    terms = _sp.Add.make_args(_sp.expand(equation_magnitude))
    values = [_sp.N(t.subs(symbol, numeric), NUMERIC_DIGITS) for t in terms]
    if not all(v.is_number for v in values):
        return False
    residual = sum(values)
    scale = sum(abs(v) for v in values)
    return _negligible(residual, scale, tolerance)


def no_symbolic_solution() -> LogicException:
    return LogicException(system_error("no_symbolic_solution"))


#: Newton steps at most, when polishing a numeric root (see ``_polish``).
POLISH_STEPS = 20


def _polish(equation_magnitude: Any, symbol: Any, value: Any) -> Any:
    """*value* refined by Newton's method at NUMERIC_DIGITS on the equation
    in SI magnitudes, stopping when a step no longer shrinks (or is zero),
    after at most POLISH_STEPS.  SymPy computes a float equation's roots in
    double precision, where a small root beside a large one (X**2 -
    3.0 X + 1e-6) has lost its digits to cancellation and would fail the
    residual test; polished, it passes, and is reported rounded to double."""
    derivative = _sp.diff(equation_magnitude, symbol)
    previous_step = None
    for _ in range(POLISH_STEPS):
        slope = _sp.N(derivative.subs(symbol, value), NUMERIC_DIGITS)
        height = _sp.N(equation_magnitude.subs(symbol, value), NUMERIC_DIGITS)
        if not (slope.is_number and height.is_number) or slope == 0 \
                or not slope.is_extended_real or not height.is_extended_real:
            break
        step = height / slope
        if previous_step is not None and abs(step) >= abs(previous_step):
            break
        value = _sp.Float(value - step, NUMERIC_DIGITS)
        if step == 0:
            break
        previous_step = step
    return value


def float_polynomial(equation: Any, symbol: Any) -> Any:
    """*equation* as a polynomial over QQ in *symbol* alone (SI magnitudes),
    when it is one and holds a float coefficient, else None.

    Each float is read as the rational its SHORTEST REPR denotes,
    ``Fraction(repr(f))``: 1.1 is 11/10, not the binary 2476979795053773 /
    2**51.  That is the number the user wrote, and it keeps a repeated root
    repeated ((X - 1.1)**2 rounded to binary has a complex pair instead).
    A float polynomial is solved through it, never by SymPy's solve.
    The text parsed is the float's own repr, produced here from a Python
    float, never text taken from a term, so this reopens no parsing path."""
    magnitude = real_magnitude(equation)
    if not magnitude.has(_sp.Float) or free_variables(magnitude) - {symbol}:
        return None
    rational = magnitude.replace(
        lambda e: isinstance(e, _sp.Float),
        lambda e: _sp.Rational(*_fraction_parts(Fraction(repr(float(e))))))
    try:
        polynomial = _sp.Poly(rational, symbol, domain=_sp.QQ)
    except (_sp.PolynomialError, _sp.polys.polyerrors.GeneratorsNeeded,
            _sp.polys.polyerrors.CoercionFailed):
        return None
    return polynomial if polynomial.degree() >= 1 else None


def _fraction_parts(value: Fraction) -> tuple:
    return value.numerator, value.denominator


def float_polynomial_real_roots(polynomial: Any, units: Any) -> list | None:
    """The real roots of a rationalised float polynomial, as ``(root,
    multiplicity)`` in increasing order, each a float times *units*.

    The polynomial is split EXACTLY into square-free factors (``sqf_list``,
    a gcd computation over QQ: fast), so a repeated root is one simple root
    of a factor raised to its multiplicity, and never splits into a complex
    pair.  Each factor's roots are then found at NUMERIC_DIGITS
    (``nroots``); a root of a square-free factor is simple, so it converges
    well, and it is real iff its imaginary part is negligible
    (EXACT_TOLERANCE) relative to its size.  (Exact real-root isolation,
    ``Poly.real_roots``, was the first choice but runs for minutes at
    degree 20.)  None when the numerics fail; the caller then falls back to
    ``numeric_polynomial_roots``."""
    found = []
    try:
        _, factors = polynomial.sqf_list()
        for factor, multiplicity in factors:
            if factor.degree() < 1:
                continue
            for root in factor.nroots(n=NUMERIC_DIGITS, maxsteps=500):
                re_part, im_part = _sp.re(root), _sp.im(root)
                if _negligible(im_part, abs(root), EXACT_TOLERANCE):
                    found.append((_sp.Float(re_part, NUMERIC_DIGITS), multiplicity))
    except Exception:                       # mpmath NoConvergence and kin
        return None
    found.sort(key=lambda pair: pair[0])
    return [(root * units, multiplicity) for root, multiplicity in found]


def numeric_polynomial_roots(equation: Any, symbol: Any, units: Any) -> list | None:
    """All roots of *equation* as a polynomial in *symbol* alone,
    numerically (to NUMERIC_DIGITS), each times *units*, as ``(root, 1)``.
    None when it is not such a polynomial.  For when SymPy gives up on one
    (a quintic) by answering nothing or only some roots.  The numerics
    failing is ``system_error(no_symbolic_solution)``."""
    magnitude = real_magnitude(equation)
    if free_variables(magnitude) - {symbol}:
        return None
    try:
        polynomial = _sp.Poly(magnitude, symbol)
    except (_sp.PolynomialError, _sp.polys.polyerrors.GeneratorsNeeded):
        return None
    if polynomial.degree() < 1:
        return None
    try:
        found = polynomial.nroots(n=NUMERIC_DIGITS, maxsteps=200)
    except Exception as exc:                # mpmath.NoConvergence and kin
        raise no_symbolic_solution() from exc
    return [(r * units, 1) for r in found]


def real_roots(equation: Any, symbol: Any, roots: list, trusted: bool = False) -> list:
    """The REAL roots of an equation holding a quantity, in increasing
    order, each once, as ``(root, multiplicity)``: *roots* is a list of
    ``(root, multiplicity)`` from SymPy.

    * A root with another variable in it cannot be classified: it is kept as
      it is, after the ground ones (so "real only" applies to GROUND roots;
      ``X**2 + Y**2 * 1(metre**2)`` answers ``+-I*y*(metre)``).
    * A ground root SymPy gives exactly and knows is real is kept as it is.
    * Any other ground root is evaluated (``real_value``), polished by
      Newton's method at NUMERIC_DIGITS (``_polish``), and kept iff it is
      real and satisfies the equation when substituted back
      (``_satisfies``), both relative to the tolerance the input's
      precision sets (``tolerance_for``).  SymPy's candidates for a
      transcendental equation include spurious ones.
    * *trusted* roots (from ``float_polynomial_real_roots``: real and
      isolated exactly) are kept as they are, with no numeric check.
    * Two exact roots are one root iff they are equal; otherwise roots whose
      difference is negligible relative to their size are one root.  Either
      way their multiplicities are added.
    """
    tolerance = tolerance_for(equation)
    ground, symbolic = [], []
    equation_magnitude = real_magnitude(equation)
    checkable = not (free_variables(equation_magnitude) - {symbol})
    for root, multiplicity in roots:
        if free_variables(root):
            symbolic.append((root, multiplicity))
            continue
        dimension = sympy_dimension(root, Analysis())
        magnitude = real_magnitude(root)
        root_tolerance = max(tolerance, tolerance_for(magnitude))
        exact = trusted or _is_exact_real(magnitude)
        if exact:
            value = magnitude
        else:
            value = real_value(magnitude, root_tolerance)
            if value is None:
                continue
            if checkable:
                value = _polish(equation_magnitude, symbol, _sp.N(value, NUMERIC_DIGITS))
                if not _satisfies(equation_magnitude, symbol, value, root_tolerance):
                    continue
        units = _unit_product(dimension.known.dims) if dimension is not None else 1
        ground.append((_sp.N(value, NUMERIC_DIGITS), value, value * units,
                       multiplicity, root_tolerance, exact))
    ground.sort(key=lambda entry: entry[0])
    distinct: list[list] = []
    for numeric, value, root, multiplicity, root_tolerance, exact in ground:
        if distinct:
            previous_numeric, previous_value, _, _, previous_exact = distinct[-1]
            if exact and previous_exact:
                same = value == previous_value       # two exact roots: equal or not
            else:
                same = _negligible(numeric - previous_numeric,
                                   max(abs(numeric), abs(previous_numeric)), root_tolerance)
            if same:
                distinct[-1][3] += multiplicity
                continue
        distinct.append([numeric, value, root, multiplicity, exact])
    return [(entry[2], entry[3]) for entry in distinct] + symbolic


# -- Back to Clausal ---------------------------------------------------------

#: How a ground result whose magnitude is real but not rational (sqrt(2),
#: 20/log(3)) comes back.  False (the default, operator ruling 2026-11-04:
#: "ok floats for now and a todo for when we feel we haven't suffered
#: enough"): a float ``Quantity``, which compares, ``has_units/2`` and
#: ``strip_units/2`` like any other.  True: exact, as ``Magnitude *
#: Quantity(1, dims)`` (an arithmetic term the caller must evaluate before
#: comparing).  A RATIONAL magnitude is exact either way.  The one switch.
#: With True, the constants e and pi in such a term come back as the atoms
#: ``e`` and ``pi`` (which the engine evaluates), not as numbers.
EXACT_IRRATIONAL_RESULTS = False


#: SymPy functions whose Clausal spelling the engine's ``is`` evaluates
#: (checked against clausal.logic.exact_arith.evaluate).  An exact
#: magnitude using anything else (LambertW, gamma, ...) comes back as a
#: float: an exact term the engine cannot evaluate would be a trap.
_ENGINE_EVALUABLE_FUNCTIONS = frozenset({
    "sin", "cos", "tan", "asin", "acos", "atan", "exp", "log", "Abs",
    "ceiling", "floor"})


def _engine_evaluable(magnitude: Any) -> bool:
    if magnitude.has(_sp.I):
        return False
    for node in _sp.preorder_traversal(magnitude):
        if isinstance(node, _sp.Function) and \
                type(node).__name__ not in _ENGINE_EVALUABLE_FUNCTIONS:
            return False
        if node.is_NumberSymbol and node not in (_sp.pi, _sp.E):
            return False
    return True


def _irrational_result(magnitude: Any, dims: dict, exact_term: Callable) -> Any:
    if EXACT_IRRATIONAL_RESULTS and _engine_evaluable(magnitude):
        return Mult(left=exact_term(magnitude), right=Quantity(1, dims))
    return Quantity(float(_sp.N(magnitude, NUMERIC_DIGITS)), dims)


def _lattice(expr: Any) -> Any:
    """The wrapper's max/min (SymPy undefined functions) as SymPy's Max and
    Min, so a ground max(3 kelvin, 5 kelvin) is 5 kelvin."""
    lattice = {"max": _sp.Max, "min": _sp.Min}
    return expr.replace(
        lambda e: isinstance(e, _sp.core.function.AppliedUndef)
        and type(e).__name__ in lattice,
        lambda e: lattice[type(e).__name__](*e.args))


def result_to_clausal(expr: Any, symbolic: Callable, exact_term: Callable,
                      expected: Quantity | None = None) -> Any:
    """A SymPy result, back in Clausal terms, with its dimension checked.

    *expected* is the dimension the operation implies (``Quantity(1,
    dims)``), used for a zero and checked against a non-zero.  A ground
    result is a quantity (see the module docstring); one with free variables
    is ``symbolic(expr)``.  *exact_term* turns an exact SymPy number into a
    Clausal arithmetic term.  A magnitude that is not real and finite is
    ``evaluation_error(undefined)``.
    """
    analysis = Analysis()
    dimension = sympy_dimension(expr, analysis)
    if free_variables(expr):
        return symbolic(expr)
    expr = _lattice(expr)
    value = real_value(real_magnitude(expr), tolerance_for(expr))
    if value is None:
        raise _undefined()
    if value.has(_sp.core.function.AppliedUndef):
        return symbolic(expr)              # f(3) * 1 kelvin: stays symbolic
    if dimension is not None:
        dims = dict(dimension.known.dims)
        if expected is not None:
            dimension.known + expected     # the operation's own dimension
    elif expected is not None:
        dims = dict(expected.dims)
    else:
        dims = {}
    if not dims:
        if value.is_Integer:
            return int(value)
        return float(value) if value.is_Float else symbolic(value)
    if value.is_Integer:
        return Quantity(int(value), dims)
    if value.is_Rational:
        return Quantity(Fraction(int(value.p), int(value.q)), dims)
    if value.is_Float:
        return Quantity(float(value), dims)
    return _irrational_result(value, dims, exact_term)


def unit_symbol_to_clausal(symbol: _UnitSymbol) -> Quantity:
    return Quantity(1, {symbol.name: 1})
