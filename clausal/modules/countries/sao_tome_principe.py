"""Sao Tome Principe — dobra, dobra_1977_2017."""
from clausal.modules.countries._currency import _make_currency

dobra = _make_currency("dobra", iso_code="STN", scale=2, symbol="STN", start="2018-01-01", end=None)
dobra_1977_2017 = _make_currency("dobra_1977_2017", iso_code="STD", scale=2, symbol="STD", start="1977-09-08", end="2017-12-31", historical=True)
