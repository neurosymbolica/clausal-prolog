"""Belarus — ruble, ruble_1994_2000, ruble_2000_2017."""
from clausal.modules.countries._currency import _make_currency

ruble = _make_currency("ruble", iso_code="BYN", scale=2, symbol="BYN", start="2016-07-01", end=None)
ruble_1994_2000 = _make_currency("ruble_1994_2000", iso_code="BYB", scale=2, symbol="BYB", start="1994-08-01", end="2000-12-31", historical=True)
ruble_2000_2017 = _make_currency("ruble_2000_2017", iso_code="BYR", scale=2, symbol="BYR", start="2000-01-01", end="2017-01-01", historical=True)
