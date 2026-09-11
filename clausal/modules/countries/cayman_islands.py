"""Cayman Islands — dollar."""
from clausal.modules.countries._currency import _make_currency

kyd = _make_currency("dollar", iso_code="KYD", scale=2, symbol="KYD", start="1971-01-01", end=None)
