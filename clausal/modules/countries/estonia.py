"""Estonia — kroon."""
from clausal.modules.countries._currency import _make_currency

kroon = _make_currency("kroon", iso_code="EEK", scale=2, symbol="EEK", start="1992-06-21", end="2010-12-31", historical=True)
