"""Step 6 of the rdiv/decimal design, under RULED Q6 = option C (2026-09-18):

* a float literal a user WROTE beside an exact number is read through its
  shortest repr AT DECLARATION / CONSTRUCTION -- ``-constant_number_units(r,
  5.25, percent)`` and ``2.5(centimetre)`` are exact, for every unit, not
  only currency;
* at RUN TIME a float beside a Decimal or a Fraction RAISES
  ``type_error(exact_number, Float)`` -- in the evaluator (both paths) and
  inside quantity arithmetic, whose shortest-repr bridge is gone;
* the units vocabulary's SI-fraction factors are exact Decimals, never float
  literals, so money times a length or a mass never meets a float.
"""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import Quantity
from clausal.testing import load_clausal_module
from tests._suffix import SEAM

_HEADER = """-double_quotes(chars)
-private([yes, no])
-import_from(py.units, [metre, centimetre, gram, kilogram, percent, strip_units])
-import_from(united_states, [usd])
-constant_number_units(rate, 5.25, percent)
-constant_number_units(width, 2.5, centimetre)
-constant_number_units(fee, "1.50", usd)
third(F) <- 'is'(F, rdiv(1, 3))   # rdiv: exact (Q15)
"""


def _module(tmp_path, body=""):
    path = tmp_path / f"step6{SEAM}"
    path.write_text(_HEADER + body)
    return load_clausal_module(path)


def _first(mod, name, *args):
    for _ in call(name, *args, module=mod):
        return [deref(a) for a in args]
    pytest.fail(f"{name} had no solution")


def _raises(mod, name, *args):
    with pytest.raises(LogicException) as ei:
        for _ in call(name, *args, module=mod):
            break
    return str(ei.value)


class TestDeclarationIsExact:
    def test_a_float_literal_constant_with_a_ratio_unit_is_exact(self, tmp_path):
        mod = _module(tmp_path, "p(V) <- strip_units(++rate, V)\n")
        (v,) = _first(mod, "p", Var())
        assert type(v) is Decimal and v == Decimal("0.0525"), v

    def test_a_float_literal_constant_with_an_si_fraction_unit_is_exact(self, tmp_path):
        """2.5 centimetre used to be the FLOAT 0.025 (the factor was 1e-2)."""
        mod = _module(tmp_path, "p(V) <- strip_units(++width, V)\n")
        (v,) = _first(mod, "p", Var())
        assert type(v) is Decimal and v == Decimal("0.025"), v

    def test_the_recorded_declaration_keeps_the_written_digits(self, tmp_path):
        mod = _module(tmp_path)
        number, _units = vars(mod)["$module"].constant_units["width"]
        assert type(number) is Decimal and str(number) == "2.5"

    def test_construction_from_a_float_literal_beside_an_exact_factor(self):
        from clausal.modules.py.units import centimetre, gram
        assert Quantity(2.5, centimetre).value == Decimal("0.025")
        assert type(Quantity(2.5, centimetre).value) is Decimal
        assert Quantity(200, gram).value == Decimal("0.2")

    def test_money_construction_unchanged(self, tmp_path):
        usd = _module(tmp_path).usd
        assert Quantity(19.99, usd).value == Decimal("19.99")


class TestRuntimeFloatBesideExactRaises:
    def test_money_times_a_float_in_a_body_raises(self, tmp_path):
        """The compiled path reaches Quantity arithmetic and gets Q5's
        refusal; the interpreted ``is/2`` refuses a QUANTITY leaf outright
        (``type_error(evaluable, ...)``, pre-existing: quantities are
        ``eval_``/``#=`` operands) -- loud either way."""
        mod = _module(tmp_path, "p(R) <- eval_(++fee * 1.2, R)\nq(R) <- 'is'(R, ++fee * 1.2)\n")
        assert "exact_number" in _raises(mod, "p", Var())
        assert "type_error" in _raises(mod, "q", Var())

    def test_a_fraction_beside_a_float_raises_on_both_paths(self, tmp_path):
        mod = _module(tmp_path, "p(R) <- (third(F), eval_(F * 0.5, R))\nq(R) <- (third(F), 'is'(R, F * 0.5))\n")
        assert "exact_number" in _raises(mod, "p", Var())
        assert "exact_number" in _raises(mod, "q", Var())

    @pytest.mark.parametrize("op", ["+", "-", "*", "/"])
    def test_quantity_arithmetic_has_no_runtime_bridge(self, op):
        q = Quantity(Decimal("1.50"), {})
        f = Quantity(Fraction(1, 3), {})
        with pytest.raises(LogicException):
            eval(f"q {op} 0.25")
        with pytest.raises(LogicException):
            eval(f"0.25 {op} q")
        with pytest.raises(LogicException):
            eval(f"f {op} 0.5")

    def test_an_int_beside_a_decimal_is_still_fine(self):
        assert (Quantity(Decimal("1.50"), {}) * 2).value == Decimal("3.00")

    def test_a_float_beside_a_float_is_untouched(self):
        assert (Quantity(1.5, {}) * 0.5).value == 0.75


class TestUnitFactorsAreExact:
    _CONVERTED = ["centimetre", "millimetre", "micrometre", "nanometre", "gram", "milligram",
                  "microgram", "millisecond", "microsecond", "nanosecond", "bar", "electronvolt"]

    def test_the_si_fraction_factors_are_no_longer_floats(self):
        """The 13 float-literal factors of 2026-09-18 (12 names; one docstring
        mention).  MEASURED physical constants (avogadro, boltzmann, ...) stay
        floats: they are not written decimals."""
        from clausal.modules.py import units
        still_float = [n for n in self._CONVERTED if type(getattr(units, n).value) is float]
        assert still_float == [], still_float

    @pytest.mark.parametrize("name, want", [
        ("centimetre", "0.01"), ("millimetre", "0.001"), ("micrometre", "0.000001"),
        ("gram", "0.001"),
    ])
    def test_si_fraction_factors(self, name, want):
        from clausal.modules.py import units
        v = getattr(units, name).value
        assert type(v) is Decimal and v == Decimal(want), (name, v)

    def test_money_per_mass_is_exact(self, tmp_path):
        mod = _module(tmp_path, "p(V) <- (eval_(++fee / (200 * gram), P), strip_units(P, V))\n")
        (v,) = _first(mod, "p", Var())
        assert v == Fraction(15, 2), v
