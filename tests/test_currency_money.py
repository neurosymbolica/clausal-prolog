from decimal import Decimal

import pytest

from clausal.terms import Quantity, CurrencyPrecisionError
from clausal.modules.countries.european_union import euro
from clausal.modules.countries.japan import yen
from clausal.modules.countries.bahrain import dinar


class TestConstructionPrecisionCheck:
    def test_over_precise_euro_raises(self):
        with pytest.raises(CurrencyPrecisionError):
            Quantity(7.891, euro)          # 3 dp for a 2-dp currency

    def test_exact_euro_ok(self):
        assert Quantity(7.89, euro).value == Decimal("7.89")

    def test_trailing_zero_ok(self):
        assert Quantity(Decimal("7.890"), euro).value == Decimal("7.890")  # == 7.89, allowed

    def test_drifted_float_expression_raises(self):
        with pytest.raises(CurrencyPrecisionError):
            Quantity(0.1 + 0.2, euro)      # 0.30000000000000004

    def test_zero_scale_currency_rejects_fraction(self):
        with pytest.raises(CurrencyPrecisionError):
            Quantity(7.5, yen)             # yen scale 0
        assert Quantity(7, yen).value == Decimal("7")

    def test_three_scale_currency_ok(self):
        assert Quantity(Decimal("1.234"), dinar).value == Decimal("1.234")

    def test_arithmetic_intermediate_is_exempt(self):
        # A computed currency result (dims passed as a dict) must NOT be checked.
        r = Quantity(Decimal("10.00"), euro) / 3      # 3.333...(euro), built via dict dims
        assert r.value != r.value.quantize(Decimal("0.01"))   # has sub-scale digits
        assert r.dims == {euro: 1}                              # and did not raise
