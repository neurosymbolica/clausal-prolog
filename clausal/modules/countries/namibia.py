"""Namibia — dollar."""
from clausal.modules.countries._currency import _make_currency

nad = _make_currency("dollar", iso_code="NAD", scale=2, symbol="NAD", start="1993-01-01", end=None)
