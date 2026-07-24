"""Italy — lira."""
from clausal.modules.countries._currency import _make_currency

lira = _make_currency("lira", iso_code="ITL", scale=2, symbol="ITL", start="1862-08-24", end="2002-02-28", historical=True)
