"""Turkiye — lira, lira_1922_2005."""
from clausal.modules.countries._currency import _make_currency

lira = _make_currency("lira", iso_code="TRY", scale=2, symbol="TRY", start="2005-01-01", end=None)
lira_1922_2005 = _make_currency("lira_1922_2005", iso_code="TRL", scale=2, symbol="TRL", start="1922-11-01", end="2005-12-31", historical=True)
