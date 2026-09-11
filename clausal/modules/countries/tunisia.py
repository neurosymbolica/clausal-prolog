"""Tunisia — dinar."""
from clausal.modules.countries._currency import _make_currency

tnd = _make_currency("dinar", iso_code="TND", scale=3, symbol="TND", start="1958-11-01", end=None)
