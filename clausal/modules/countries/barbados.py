"""Barbados — dollar."""
from clausal.modules.countries._currency import _make_currency

dollar = _make_currency("dollar", iso_code="BBD", scale=2, symbol="BBD", start="1973-12-03", end=None)
