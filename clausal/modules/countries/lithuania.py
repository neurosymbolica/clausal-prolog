"""Lithuania — litas, talonas."""
from clausal.modules.countries._currency import _make_currency

litas = _make_currency("litas", iso_code="LTL", scale=2, symbol="LTL", start="1993-06-25", end="2014-12-31", historical=True)
talonas = _make_currency("talonas", iso_code="LTT", scale=2, symbol="LTT", start="1992-10-01", end="1993-06-25", historical=True)
