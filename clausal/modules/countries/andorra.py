"""Andorra — peseta."""
from clausal.modules.countries._currency import _make_currency

adp = _make_currency("peseta", iso_code="ADP", scale=2, symbol="ADP", start="1936-01-01", end="2001-12-31", historical=True)
