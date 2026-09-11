"""Mozambique — metical, escudo, metical_1980_2006."""
from clausal.modules.countries._currency import _make_currency

metical = _make_currency("metical", iso_code="MZN", scale=2, symbol="MZN", start="2006-07-01", end=None)
mze = _make_currency("escudo", iso_code="MZE", scale=2, symbol="MZE", start="1975-06-25", end="1980-06-16", historical=True)
metical_1980_2006 = _make_currency("metical_1980_2006", iso_code="MZM", scale=2, symbol="MZM", start="1980-06-16", end="2006-12-31", historical=True)
