"""Slovenia — tolar."""
from clausal.modules.countries._currency import _make_currency

tolar = _make_currency("tolar", iso_code="SIT", scale=2, symbol="SIT", start="1992-10-07", end="2007-01-14", historical=True)
