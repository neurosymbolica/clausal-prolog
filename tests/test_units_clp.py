"""Units side channel around CLP: dimension analysis, shadows, reattachment.

Spec: docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md
"""
from decimal import (Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN,
                     ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR)
from fractions import Fraction

import pytest

from clausal.logic.atoms import mint
from clausal.logic.exceptions import LogicException
from clausal.terms import Compound, Quantity
from clausal.modules.countries.european_union import euro
from clausal.modules.countries.japan import yen
from clausal.modules.countries.kuwait import kwd


def _assert_system_error(ei, code):
    term = ei.value.term
    assert isinstance(term, Compound) and term.functor == "error"
    inner = term.args[0]
    assert isinstance(inner, Compound) and inner.functor == "system_error"
    assert inner.args[0] == mint(code)


class TestSystemErrorHelper:
    def test_builds_iso_shape(self):
        from clausal.logic.exceptions import system_error
        term = system_error("units_mismatch", "(==)/2: metre vs second")
        assert term.functor == "error"
        assert term.args[0].functor == "system_error"
        assert term.args[0].args == (mint("units_mismatch"),)
        assert term.args[1] == "(==)/2: metre vs second"


_MODES = [ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN, ROUND_UP,
          ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR]


class TestExactNumberCurrency:
    def test_currency_quantity_keeps_fraction(self):
        q = Quantity(Fraction(1, 3), {euro: 1})
        assert type(q.value) is Fraction and q.value == Fraction(1, 3)

    def test_decimal_and_fraction_quantities_compare_equal(self):
        assert Quantity(Decimal("1500.00"), {euro: 1}) == Quantity(Fraction(1500), {euro: 1})
        assert hash(Quantity(Decimal("1500.00"), {euro: 1})) == hash(Quantity(Fraction(1500), {euro: 1}))

    def test_tagging_terminating_fraction_passes_precision_check(self):
        q = Quantity(Fraction(3, 2), euro)          # 1.50, within scale 2
        assert q.value == Fraction(3, 2)

    def test_tagging_non_terminating_fraction_fails_precision_check(self):
        from clausal.terms import CurrencyPrecisionError
        with pytest.raises(CurrencyPrecisionError):
            Quantity(Fraction(1, 3), euro)

    @pytest.mark.parametrize("mode", _MODES)
    @pytest.mark.parametrize("num", [-27, -25, -23, -5, -1, 0, 1, 5, 23, 25, 27, 125, 135])
    def test_fraction_rounding_agrees_with_decimal_rounding(self, mode, num):
        """Positive control: on terminating fractions the Fraction rounder and
        Decimal.quantize must give the same integer for every mode."""
        from clausal.terms import _round_fraction_to_int
        fr = Fraction(num, 10)                       # x.5 ties and non-ties, both signs
        expected = int(Decimal(num).scaleb(-1).quantize(Decimal(1), rounding=mode))
        assert _round_fraction_to_int(fr, mode) == expected

    def test_quantize_fraction_third_of_a_yen(self):
        from clausal.terms import _quantize_to_scale
        assert _quantize_to_scale(Fraction(1000, 3), 0, "half_even") == Decimal("333")
        assert _quantize_to_scale(Fraction(1, 3), 3, "half_even") == Decimal("0.333")

    def test_money_round_on_fraction_quantity(self):
        from clausal.logic.variables import Trail, Var, deref
        from clausal.modules.currency import _money_round_impl
        q = Quantity(Fraction(1000, 3), {yen: 1})
        out = Var()
        assert list(_money_round_impl(q, "half_even", out, Trail())) == [None]
        assert deref(out) == Quantity(Decimal("333"), {yen: 1})
