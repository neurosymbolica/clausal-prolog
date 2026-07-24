"""Mauritania — ouguiya, ouguiya_1973_2018."""
from clausal.modules.countries._currency import _make_currency

ouguiya = _make_currency("ouguiya", iso_code="MRU", scale=2, symbol="MRU", start="2018-01-01", end=None)
ouguiya_1973_2018 = _make_currency("ouguiya_1973_2018", iso_code="MRO", scale=2, symbol="MRO", start="1973-06-29", end="2018-06-30", historical=True)
