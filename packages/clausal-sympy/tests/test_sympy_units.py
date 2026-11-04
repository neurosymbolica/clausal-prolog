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
    factor, diff, integrate, degree, free_vars, subs, sym_equal, sym_str,
    gcd, lcm, roots, latex,
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
        # 12345 millidegrees Celsius as a temperature DIFFERENCE: 12345(kelvin) / 1000
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
        # 3(kelvin) + 5(pascal) - 5(pascal): SymPy folds it to 3(kelvin) on construction.
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
        # x**2 + x - 1(metre): every root adds a number to a length.
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
        # Exact: the term 20/log(3) * 1 (kelvin), not a float.
        assert isinstance(mean, Mult) and mean.right == kelvin(1)
        assert _to_sympy(mean) == 20 * _sympy_units.unit_symbol("kelvin") / sp.log(3)

    def test_square_root_of_a_temperature(self):
        with refused_as_units_mismatch():
            _first_solution(simplify, ("sqrt", kelvin(4)), Var())

    def test_dimensioned_exponent(self):
        with refused_as_units_mismatch():
            _first_solution(simplify, Pow(left=2, right=kelvin(1)), Var())


def second(n):
    return units.second(n)


def answers(predicate, *args):
    return _collect_solutions(predicate, *args)


# ── Review findings (engine-lane, 942de925) ─────────────────────────────────


class TestDimensionSymbolsAreNotVariables:
    """Finding 1-2: a dimension symbol is a constant, never 'the variable'."""

    def test_sym_equal_refuses_different_dimensions(self):
        with refused_as_units_mismatch():
            answers(sym_equal, metre(2), kelvin(2))
        with refused_as_units_mismatch():
            answers(sym_equal, metre(3), second(3))

    def test_sym_equal_same_dimension(self):
        assert answers(sym_equal, metre(2), metre(2))
        assert not answers(sym_equal, metre(2), metre(3))

    def test_sym_equal_quantity_is_not_the_atom(self):
        assert not answers(sym_equal, kelvin(1), "kelvin")

    def test_sym_equal_renaming_leaves_dimensions_alone(self):
        # x * 1(metre) against y * z: two variables against one, never equal.
        assert not answers(sym_equal, Mult(left=Var(), right=metre(1)),
                           Mult(left=Var(), right=Var()))

    def test_symexpr_equality_leaves_dimensions_alone(self):
        metre_symbol = _sympy_units.unit_symbol("metre")
        kelvin_symbol = _sympy_units.unit_symbol("kelvin")
        assert not (SymExpr(2 * metre_symbol) == SymExpr(2 * kelvin_symbol))

    def test_diff_of_a_constant_quantity_has_no_variable(self):
        assert answers(diff, kelvin(3), Var()) == []

    def test_diff_with_one_variable(self):
        (answer,) = answers(diff, Mult(left=Var(), right=kelvin(3)), Var())
        assert answer[1] == kelvin(3)

    def test_integrate_of_a_constant_quantity_has_no_variable(self):
        assert answers(integrate, metre(5), Var()) == []

    def test_integrate_with_one_variable(self):
        x = Var()
        (answer,) = answers(integrate, Mult(left=x, right=metre(5)), x, Var())
        assert isinstance(answer[2], SymExpr)
        assert answer[2]._expr == sp.Rational(5, 2) * sp.Symbol("x") ** 2 \
            * _sympy_units.unit_symbol("metre")

    def test_degree(self):
        assert answers(degree, kelvin(3), Var()) == []
        term = Mult(left=Pow(left=Var(), right=2), right=kelvin(1))
        assert answers(degree, term, Var())[0][1] == 2

    def test_free_vars_lists_variables_only(self):
        assert answers(free_vars, Mult(left=Var(), right=kelvin(3)), Var())[0][1] == ["x"]
        assert answers(free_vars, kelvin(3), Var())[0][1] == []


class TestZerosKeepTheirDimension:
    """Finding 3: dimensions are carried on the Clausal term, so a zero
    (written, or folded by SymPy) cannot hide a mismatch."""

    @pytest.mark.parametrize("term", [
        Add(left=kelvin(3), right=Sub(left=pascal(5), right=pascal(5))),
        Add(left=pascal(0), right=kelvin(3)),
        Add(left=kelvin(3), right=Mult(left=0, right=pascal(5))),
        Add(left=0, right=kelvin(3)),
    ], ids=["folded difference", "zero pascal", "zero times pascal", "plain zero"])
    def test_mismatch_through_a_zero(self, term):
        with refused_as_units_mismatch():
            answers(simplify, term, Var())

    def test_same_unknown_with_different_dimensions(self):
        x = Var()
        equation = Add(left=Mult(left=x, right=kelvin(1)), right=Mult(left=x, right=pascal(1)))
        with refused_as_units_mismatch():
            answers(solve, equation, x, Var())

    def test_zero_root_has_the_variable_dimension(self):
        x = Var()
        (answer,) = answers(solve, Sub(left=x, right=kelvin(0)), x, Var())
        assert answer[2] == kelvin(0) and isinstance(answer[2], Quantity)

    def test_difference_to_zero_keeps_its_dimension(self):
        (answer,) = answers(simplify, Sub(left=kelvin(3), right=kelvin(3)), Var())
        assert isinstance(answer[1], Quantity) and answer[1] == kelvin(0)

    def test_dimensionless_root(self):
        x = Var()
        equation = Sub(left=Mult(left=x, right=kelvin(2)), right=kelvin(6))
        assert answers(solve, equation, x, Var())[0][2] == 3


class TestComplexAndNonFinite:
    """Findings 4-5."""

    def test_no_real_root_is_an_empty_list(self):
        x = Var()
        equation = Add(left=Pow(left=x, right=2), right=metre(4) * metre(1))
        assert answers(solve, equation, x, Var()) == []
        assert answers(solve_all, equation, x, Var())[0][2] == []

    def test_plain_equations_keep_their_complex_roots(self):
        x = Var()
        out = answers(solve_all, Add(left=Pow(left=x, right=2), right=4), x, Var())
        assert len(out[0][2]) == 2

    def test_roots_of_a_dimensioned_equation(self):
        x = Var()
        equation = Sub(left=Pow(left=x, right=2), right=metre(4) * metre(1))
        found = sorted(answer[2][0] for answer in answers(roots, equation, x, Var()))
        assert found == [metre(-2), metre(2)]

    def test_square_root_of_a_negative_area(self):
        with pytest.raises(LogicException) as caught:
            answers(simplify, ("sqrt", metre(-4) * metre(1)), Var())
        assert caught.value.term[1][0] == "evaluation_error"

    @pytest.mark.parametrize("magnitude", [
        Decimal("Infinity"), Decimal("-Infinity"), Decimal("NaN"),
        float("inf"), float("nan"),
    ], ids=["decimal infinity", "decimal minus infinity", "decimal nan",
            "float infinity", "float nan"])
    def test_non_finite_magnitude(self, magnitude):
        with pytest.raises(LogicException) as caught:
            answers(simplify, Quantity(magnitude, units.metre), Var())
        assert caught.value.term[1][0] == "evaluation_error"


class TestExactForms:
    """Finding 6: an exact irrational result stays exact."""

    def test_irrational_root_is_an_exact_term(self):
        x = Var()
        equation = Sub(left=Pow(left=x, right=2), right=metre(2) * metre(1))
        roots_found = answers(solve_all, equation, x, Var())[0][2]
        assert all(isinstance(r, Mult) and r.right == metre(1) for r in roots_found)
        assert sorted(_to_sympy(r) for r in roots_found) == sorted(
            [-sp.sqrt(2) * _sympy_units.unit_symbol("metre"),
             sp.sqrt(2) * _sympy_units.unit_symbol("metre")], key=str)

    def test_squaring_the_exact_root_is_exact(self):
        (answer,) = answers(simplify, ("sqrt", metre(2) * metre(1)), Var())
        (square,) = answers(simplify, Mult(left=answer[1], right=answer[1]), Var())
        assert square[1] == metre(2) * metre(1)
        assert isinstance(square[1].value, int)


class TestOtherPredicates:
    """Finding 7, nits 8-10, and the rest of the surface."""

    def test_gcd_and_lcm_refuse_mixed_dimensions(self):
        for predicate in (gcd, lcm):
            with refused_as_units_mismatch():
                answers(predicate, metre(6), kelvin(4), Var())

    def test_gcd_same_dimension(self):
        assert answers(gcd, metre(6), metre(4), Var())[0][2] == metre(2)

    def test_subs_refuses_a_dimension_as_key(self):
        with pytest.raises(LogicException) as caught:
            answers(subs, kelvin(5), [(kelvin(1), 2)], Var())
        assert caught.value.term[1][0] == "type_error"

    def test_subs_value_checked(self):
        x = Var()
        with refused_as_units_mismatch():
            answers(subs, Add(left=x, right=kelvin(3)), [(x, pascal(5))], Var())
        x = Var()
        assert answers(subs, Add(left=x, right=kelvin(3)), [(x, kelvin(2))],
                       Var())[0][2] == kelvin(5)

    def test_dimension_symbols_print_unlike_atoms(self):
        text = answers(sym_str, Add(left="kelvin", right=kelvin(1)), Var())[0][1]
        assert "(kelvin)" in str(text) and "kelvin + " in str(text)
        assert "mathrm{kelvin}" in str(answers(latex, kelvin(3), Var())[0][1])

    def test_unknown_function_of_a_quantity_is_refused(self):
        # Its dimension cannot be judged; dropping the unit would be wrong.
        with refused_as_units_mismatch():
            answers(simplify, ("f", kelvin(3)), Var())

    def test_unknown_function_of_a_number_stays_symbolic(self):
        (answer,) = answers(simplify, Mult(left=("f", 3), right=kelvin(1)), Var())
        assert isinstance(answer[1], SymExpr)

    @pytest.mark.parametrize("function", ["ceiling", "cos", "tan"])
    def test_more_functions_need_a_dimensionless_argument(self, function):
        with refused_as_units_mismatch():
            answers(simplify, (function, kelvin(3)), Var())
        assert answers(simplify, (function, Div(left=kelvin(3), right=kelvin(1))), Var())

    def test_factor_keeps_the_dimension(self):
        (answer,) = answers(factor, Add(left=metre(6), right=metre(4)), Var())
        assert answer[1] == metre(10)


# ── Second review (7ec542f3) ────────────────────────────────────────────────


def no_symbolic_solution():
    return pytest.raises(LogicException, match="no_symbolic_solution")


class TestEveryFunctionIsClassified:
    """Blocker 1: a unit inside a function the wrapper does not know is
    refused, never stripped."""

    @pytest.mark.parametrize("function", [
        "log10", "log2", "sinh", "cosh", "tanh", "f", "gamma", "factorial",
        "exp", "atan"])
    def test_dimensioned_argument_is_refused(self, function):
        with refused_as_units_mismatch():
            answers(simplify, Add(left=(function, kelvin(100)), right=1), Var())

    @pytest.mark.parametrize("function", ["log10", "sinh", "f"])
    def test_dimensionless_argument_is_accepted(self, function):
        ratio = Div(left=kelvin(100), right=kelvin(1))
        assert answers(simplify, Add(left=(function, ratio), right=1), Var())

    def test_unknown_function_beside_its_own_argument(self):
        with refused_as_units_mismatch():
            answers(simplify, Add(left=("f", kelvin(3)), right=kelvin(3)), Var())
        with refused_as_units_mismatch():
            answers(simplify, ("sin", ("f", kelvin(3))), Var())

    @pytest.mark.parametrize("function", ["max", "min"])
    def test_max_and_min_keep_one_dimension(self, function):
        (answer,) = answers(simplify, Mult(left=(function, kelvin(3), kelvin(5)), right=2), Var())
        assert answer[1] == (kelvin(10) if function == "max" else kelvin(6))
        with refused_as_units_mismatch():
            answers(simplify, (function, kelvin(3), pascal(5)), Var())

    def test_cube_root_is_a_power(self):
        volume = metre(8) * metre(1) * metre(1)
        assert answers(simplify, ("cbrt", volume), Var())[0][1] == metre(2)
        with refused_as_units_mismatch():
            answers(simplify, ("cbrt", kelvin(8)), Var())


class TestRealRoots:
    """Blocker 2: an equation holding a quantity has real roots only,
    numerically checked, sorted, each once; SymPy giving up is an error."""

    def test_three_real_roots_written_with_complex_radicals(self):
        x = Var()
        equation = Add(left=Sub(left=Pow(left=x, right=3),
                                right=Mult(left=Mult(left=3, right=x),
                                           right=metre(1) * metre(1))),
                       right=metre(1) * metre(1) * metre(1))
        found = answers(solve_all, equation, x, Var())[0][2]
        assert len(found) == 3
        assert all(isinstance(r, Quantity) and dict(r.dims) == {"metre": 1} for r in found)
        values = [r.value for r in found]
        assert values == sorted(values)
        for v in values:
            assert abs(v ** 3 - 3 * v + 1) < 1e-12
        solved = sorted(a[2].value for a in answers(solve, equation, x, Var()))
        assert solved == values
        rooted = [a[2] for a in answers(roots, equation, x, Var())]
        assert [r[0].value for r in rooted] == values and all(r[1] == 1 for r in rooted)

    def test_no_real_root_is_the_same_in_every_predicate(self):
        x = Var()
        equation = Add(left=Pow(left=x, right=2), right=metre(4) * metre(1))
        assert answers(solve, equation, x, Var()) == []
        assert answers(solve_all, equation, x, Var())[0][2] == []
        assert answers(roots, equation, x, Var()) == []

    def test_a_double_root_is_one_root_of_multiplicity_two(self):
        x = Var()
        equation = Pow(left=Sub(left=x, right=metre(3)), right=2)
        assert answers(solve_all, equation, x, Var())[0][2] == [metre(3)]
        assert [a[2] for a in answers(roots, equation, x, Var())] == [(metre(3), 2)]

    def test_sympy_giving_up_is_a_named_error(self):
        # x - cos(x / 1 kelvin) * 1 kelvin: no closed form.
        x = Var()
        equation = Sub(left=x, right=Mult(left=("cos", Div(left=x, right=kelvin(1))),
                                          right=kelvin(1)))
        with no_symbolic_solution():
            answers(solve, equation, x, Var())
        with no_symbolic_solution():
            answers(solve_all, equation, x, Var())

    def test_roots_that_finds_only_some_is_a_named_error(self):
        # x**5 - x - 1 (in metres): roots/1 finds none of the five.
        x = Var()
        equation = Sub(left=Sub(left=Pow(left=x, right=5),
                                right=Mult(left=x, right=Pow(left=metre(1), right=4))),
                       right=Pow(left=metre(1), right=5))
        with no_symbolic_solution():
            answers(roots, equation, x, Var())

    def test_plain_equations_are_unchanged(self):
        x = Var()
        assert len(answers(solve_all, Add(left=Pow(left=x, right=2), right=1), x, Var())[0][2]) == 2

    def test_exact_forms_are_engine_evaluable(self):
        from clausal.logic.exact_arith import evaluate
        (answer,) = answers(simplify, ("sqrt", metre(2) * metre(1)), Var())
        value = evaluate(answer[1])
        assert isinstance(value, Quantity) and abs(value.value - 2 ** 0.5) < 1e-15


class TestZeroDerivative:
    def test_zero_derivative_keeps_a_known_dimension(self):
        # X * 1 metre - X * 1 metre + 3 kelvin * 1 metre: X is a temperature,
        # and d/dX of the whole is 0 metre.
        x = Var()
        term = Add(left=Sub(left=Mult(left=x, right=metre(1)), right=Mult(left=x, right=metre(1))),
                   right=kelvin(3) * metre(1))
        (answer,) = answers(diff, term, x, Var())
        assert answer[2] == metre(0) and isinstance(answer[2], Quantity)

    def test_zero_derivative_of_an_unconstrained_variable_is_a_plain_zero(self):
        # Nothing says what X is, so 3 kelvin per X has no known dimension.
        x = Var()
        assert answers(diff, kelvin(3), x, Var())[0][2] == 0
