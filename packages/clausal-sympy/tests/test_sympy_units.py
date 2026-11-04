"""clausal-sympy over Clausal quantities: conversion, exactness, refusals.

The end-to-end cases (a heat-exchanger duty, solving for the flow, the log
mean temperature difference) are in fixtures/sympy_units.seam; these pin the
Python-side contract they rest on.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest
import sympy as sp

from contextlib import contextmanager

from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Var
from clausal.terms import Add, Sub, Mult, Div, Pow, Quantity, UnitsMismatch
from clausal.modules import units
from clausal.modules.py import _sympy_units
from clausal.modules.py.sympy import (
    _to_sympy, _from_sympy, SymExpr, simplify, solve, solve_all, expand,
)

from test_sympy_module import _first_solution, _collect_solutions


def kelvin(n):
    return units.kelvin(n)


def pascal(n):
    return units.pascal(n)


def metre(n):
    return units.metre(n)


# ── Conversion is exact ─────────────────────────────────────────────────────


class TestExactConversion:
    def test_millidegree_difference_stays_rational(self):
        # 12345 millidegrees C as a temperature DIFFERENCE: 12345 K / 1000
        difference = kelvin(12345) / 1000
        assert difference.value == Fraction(2469, 200)
        expression = _to_sympy(difference)
        magnitude = expression.subs(_sympy_units.unit_symbol("kelvin"), 1)
        assert magnitude == sp.Rational(2469, 200)
        assert not expression.atoms(sp.Float)

    def test_decimal_magnitude_is_rational_not_float(self):
        flow = Quantity(500, units.gram) / units.second(1)
        assert isinstance(flow.value, Decimal)
        expression = _to_sympy(flow)
        assert not expression.atoms(sp.Float)
        assert expression == sp.Rational(1, 2) * _sympy_units.unit_symbol(
            "kilogram") / _sympy_units.unit_symbol("second")

    def test_plain_decimal_and_fraction_are_rational(self):
        assert _to_sympy(Decimal("0.001")) == sp.Rational(1, 1000)
        assert _to_sympy(Fraction(1, 3)) == sp.Rational(1, 3)

    def test_float_magnitude_stays_float(self):
        expression = _to_sympy(kelvin(2.5))
        assert expression.atoms(sp.Float)

    def test_dimension_symbol_is_not_the_atom_symbol(self):
        # An atom kelvin written in a term is an ordinary symbol; it never
        # unifies with the dimension.
        assert _to_sympy("kelvin") != _sympy_units.unit_symbol("kelvin")

    def test_dimensionless_ratio_unit_is_a_plain_rational(self):
        assert _to_sympy(Quantity(5, units.percent)) == sp.Rational(1, 20)


# ── Results come back as quantities ─────────────────────────────────────────


class TestResults:
    def test_product_comes_back_as_a_quantity(self):
        flow = Quantity(500, units.gram) / units.second(1)
        specific_heat = units.joule(4186) / units.kilogram(1) / kelvin(1)
        difference = kelvin(12345) / 1000
        term = Mult(left=Mult(left=flow, right=specific_heat), right=difference)
        _, duty = _first_solution(simplify, term, Var())
        assert isinstance(duty, Quantity)
        assert duty == flow * specific_heat * difference
        assert duty.value == Fraction(5167617, 200)
        assert dict(duty.dims) == dict(units.watt(1).dims)

    def test_units_that_cancel_give_a_plain_number(self):
        _, ratio = _first_solution(simplify, Div(left=kelvin(30), right=kelvin(10)), Var())
        assert ratio == 3 and not isinstance(ratio, Quantity)

    def test_zero_quantity_adds_to_its_own_dimension(self):
        _, total = _first_solution(simplify, Add(left=kelvin(0), right=kelvin(3)), Var())
        assert total == kelvin(3)

    def test_square_root_of_an_area_is_a_length(self):
        area = metre(4) * metre(1)
        _, side = _first_solution(simplify, ("sqrt", area), Var())
        assert side == metre(2)

    def test_absolute_value_keeps_the_dimension(self):
        _, size = _first_solution(simplify, ("abs", kelvin(-3)), Var())
        assert size == kelvin(3)

    def test_solve_gives_a_root_with_a_dimension(self):
        flow = Var()
        specific_heat = units.joule(4186) / units.kilogram(1) / kelvin(1)
        difference = kelvin(12345) / 1000
        duty = units.watt(5000)
        equation = Sub(left=Mult(left=Mult(left=flow, right=specific_heat),
                                 right=difference), right=duty)
        (root,) = [s[2] for s in _collect_solutions(solve, equation, flow, Var())]
        assert isinstance(root, Quantity)
        assert root == duty / (specific_heat * difference)
        assert isinstance(root.value, Fraction)

    def test_solve_all_quadratic_in_a_length(self):
        x = Var()
        equation = Sub(left=Pow(left=x, right=2), right=metre(2) * metre(2))
        _, _, roots = _first_solution(solve_all, equation, x, Var())
        assert sorted(roots) == [metre(-2), metre(2)]

    def test_symbolic_result_keeps_dimension_symbols(self):
        _, result = _first_solution(simplify, Mult(left=Var(), right=kelvin(3)), Var())
        assert isinstance(result, SymExpr)
        assert _sympy_units.unit_symbol("kelvin") in result._expr.free_symbols

    def test_from_sympy_gives_quantities(self):
        k = _sympy_units.unit_symbol("kelvin")
        assert _from_sympy(sp.Rational(7, 2) * k) == Quantity(Fraction(7, 2), {"kelvin": 1})
        assert _from_sympy(k) == kelvin(1)


# ── Refusals: the units system's own error ──────────────────────────────────


@contextmanager
def refused_as_units_mismatch():
    """A predicate call raises error(system_error(units_mismatch), _), the
    term the engine makes of the units system's UnitsMismatch."""
    with pytest.raises(LogicException) as caught:
        yield
    term = caught.value.term
    assert term[0] == "error" and term[1][0] == "system_error"
    assert term[1][1] == "units_mismatch"


class TestRefusals:
    def test_kelvin_plus_pascal(self):
        with refused_as_units_mismatch():
            _first_solution(simplify, Add(left=kelvin(10), right=pascal(5)), Var())

    def test_mismatch_that_sympy_would_fold_away(self):
        # 3 K + 5 Pa - 5 Pa: SymPy folds it to 3 K on construction.
        term = Sub(left=Add(left=kelvin(3), right=pascal(5)), right=pascal(5))
        with pytest.raises(UnitsMismatch):
            _to_sympy(term)

    def test_number_plus_quantity(self):
        with pytest.raises(UnitsMismatch):
            _to_sympy(Add(left=5, right=kelvin(3)))

    def test_mismatch_beside_the_unknown_in_solve(self):
        flow = Var()
        equation = Add(left=Sub(left=Mult(left=flow, right=kelvin(1)),
                                right=units.watt(5000)), right=pascal(3))
        with refused_as_units_mismatch():
            _collect_solutions(solve, equation, flow, Var())

    def test_root_that_mixes_dimensions_is_refused(self):
        # x**2 + x - 1 m: every root adds a number to a length.
        x = Var()
        equation = Sub(left=Add(left=Pow(left=x, right=2), right=x), right=metre(1))
        with refused_as_units_mismatch():
            _first_solution(solve_all, equation, x, Var())

    @pytest.mark.parametrize("function", ["log", "exp", "sin", "floor"])
    def test_function_of_a_dimensioned_quantity(self, function):
        with refused_as_units_mismatch():
            _first_solution(simplify, (function, kelvin(30)), Var())

    def test_log_of_a_dimensionless_ratio_is_accepted(self):
        hot, cold = kelvin(30), kelvin(10)
        term = Div(left=Sub(left=hot, right=cold),
                   right=("log", Div(left=hot, right=cold)))
        _, mean = _first_solution(simplify, term, Var())
        assert isinstance(mean, Quantity)
        assert dict(mean.dims) == {"kelvin": 1}
        assert mean.value == pytest.approx(20 / sp.log(3).evalf(), rel=1e-15)

    def test_square_root_of_a_temperature(self):
        with refused_as_units_mismatch():
            _first_solution(simplify, ("sqrt", kelvin(4)), Var())

    def test_dimensioned_exponent(self):
        with refused_as_units_mismatch():
            _first_solution(simplify, Pow(left=2, right=kelvin(1)), Var())
