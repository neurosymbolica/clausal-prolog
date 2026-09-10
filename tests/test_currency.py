import os
import tempfile
from decimal import Decimal

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.terms import UnitsMismatch


class TestCurrencyVocabulary:
    def test_euro_metadata(self):
        from clausal.modules.countries.european_union import euro
        assert euro.is_currency is True
        assert euro.iso_code == "EUR"
        assert euro.scale == 2
        assert euro.symbol == "€"

    def test_currency_is_self_keyed_base_dimension(self):
        from clausal.modules.countries.european_union import euro
        assert euro._dims == {euro: 1}

    def test_scale_variety(self):
        from clausal.modules.countries.japan import yen
        from clausal.modules.countries.bahrain import dinar
        assert yen.scale == 0
        assert dinar.scale == 3

    def test_all_starter_currencies_defined(self):
        from clausal.modules.countries.european_union import euro
        from clausal.modules.countries.united_states import dollar
        from clausal.modules.countries.united_kingdom import sterling
        from clausal.modules.countries.japan import yen
        from clausal.modules.countries.bahrain import dinar
        seen = {c.iso_code for c in (euro, dollar, sterling, yen, dinar)}
        assert seen == {"EUR", "USD", "GBP", "JPY", "BHD"}

    def test_distinct_currencies_are_distinct_dimensions(self):
        from clausal.modules.countries.european_union import euro
        from clausal.modules.countries.united_states import dollar
        assert euro is not dollar
        assert euro._dims != dollar._dims


class TestCurrencyDecimalConstruction:
    def _euro(self, v):
        from clausal.terms import Quantity
        from clausal.modules.countries.european_union import euro
        return Quantity(v, euro)

    def test_float_magnitude_becomes_decimal(self):
        q = self._euro(7.89)
        assert isinstance(q.value, Decimal)
        assert q.value == Decimal("7.89")

    def test_int_magnitude_becomes_decimal(self):
        from clausal.terms import Quantity
        from clausal.modules.countries.japan import yen
        q = Quantity(5, yen)
        assert isinstance(q.value, Decimal)
        assert q.value == Decimal("5")

    def test_same_currency_addition_is_exact(self):
        # The whole point: 0.1 + 0.2 == 0.3 exactly, not 0.30000000000000004.
        r = self._euro(0.1) + self._euro(0.2)
        assert r.value == Decimal("0.3")

    def test_cross_currency_addition_raises(self):
        from clausal.terms import Quantity, UnitsMismatch
        from clausal.modules.countries.united_states import dollar
        with pytest.raises(UnitsMismatch):
            _ = self._euro(1.00) + Quantity(1.00, dollar)

    def test_currency_plus_plain_number_raises(self):
        from clausal.terms import UnitsMismatch
        with pytest.raises(UnitsMismatch):
            _ = self._euro(1.00) + 5

    def test_scale_by_dimensionless_keeps_decimal_and_dims(self):
        r = self._euro(10.00) * 3
        assert isinstance(r.value, Decimal)
        assert r.value == Decimal("30.00")
        from clausal.modules.countries.european_union import euro
        assert r.dims == {euro: 1}

    def test_ratio_of_same_currency_is_dimensionless(self):
        r = self._euro(10.00) / self._euro(4.00)
        assert r.dims == {}
        assert r.value == Decimal("2.5")


def _load(name, src):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.clausal")
    with open(p, "w") as f:
        f.write(src)
    return _load_module(name, p).__dict__["$module"]


def _succeeds(mod, pred="test"):
    return any(True for _ in call(pred, module=mod))


class TestCurrencyClausalIntegration:
    def test_bare_imported_currency_literal_is_exact(self):
        # 0.1(euro) + 0.2(euro) == 0.3(euro): passes ONLY with exact Decimal math.
        mod = _load("cur_bare",
            "-import_from(european_union, [euro])\n"
            "test <- (eval_(0.1(euro), A), eval_(0.2(euro), B), "
            "eval_(A + B, C), eval_(0.3(euro), D), C == D)\n")
        assert _succeeds(mod)

    def test_module_qualified_currency_literal(self):
        # european_union.euro must parse in n(Unit) position (the _is_unit_expr fix).
        mod = _load("cur_qual",
            "-import_module(european_union)\n"
            "test <- (eval_(7.89(european_union.euro), A), "
            "eval_(1.23(european_union.euro), B), eval_(A + B, C), "
            "eval_(9.12(european_union.euro), D), C == D)\n")
        assert _succeeds(mod)

    def test_cross_currency_addition_fails_in_clausal(self):
        # euro + dollar must raise UnitsMismatch (dimension safety end-to-end).
        mod = _load("cur_mismatch",
            "-import_from(european_union, [euro])\n"
            "-import_from(united_states, [dollar])\n"
            "test <- (eval_(1.00(euro), A), eval_(1.00(dollar), B), eval_(A + B, C))\n")
        with pytest.raises(UnitsMismatch):
            list(call("test", module=mod))

    def test_has_units_with_qualified_currency(self):
        mod = _load("cur_has_units",
            "-import_from(py.units, [has_units])\n"
            "-import_from(european_union, [euro])\n"
            "-import_module(european_union)\n"
            "test <- (eval_(7.89(euro), A), has_units(A, european_union.euro))\n")
        assert _succeeds(mod)

    def test_bare_and_qualified_currency_are_same_object(self):
        mod = _load("cur_identity",
            "-import_from(european_union, [euro])\n"
            "-import_module(european_union)\n"
            "test <- (eval_(1.10(euro), A), eval_(2.20(european_union.euro), B), "
            "eval_(A + B, C), eval_(3.30(euro), D), C == D)\n")
        assert _succeeds(mod)
