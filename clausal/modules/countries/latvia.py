"""Latvia — lats, ruble."""
from clausal.modules.countries._currency import _make_currency

lats = _make_currency("lats", iso_code="LVL", scale=2, symbol="LVL", start="1993-06-28", end="2013-12-31", historical=True)
ruble = _make_currency("ruble", iso_code="LVR", scale=2, symbol="LVR", start="1992-05-07", end="1993-10-17", historical=True)
