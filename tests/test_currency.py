from decimal import Decimal

import pytest


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
