"""Czechia — koruna."""
from clausal.modules.countries._currency import _make_currency

koruna = _make_currency("koruna", iso_code="CZK", scale=2, symbol="CZK", start="1993-01-01", end=None)
