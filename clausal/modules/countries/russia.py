"""Russia — ruble, ruble_1991_1998."""
from clausal.modules.countries._currency import _make_currency

ruble = _make_currency("ruble", iso_code="RUB", scale=2, symbol="RUB", start="1999-01-01", end=None)
ruble_1991_1998 = _make_currency("ruble_1991_1998", iso_code="RUR", scale=2, symbol="RUR", start="1991-12-25", end="1998-12-31", historical=True)
