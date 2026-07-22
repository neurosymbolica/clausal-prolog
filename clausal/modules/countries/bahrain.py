"""Bahrain — dinar (a three-minor-unit currency)."""
from clausal.modules.countries._currency import _make_currency

dinar = _make_currency("dinar", iso_code="BHD", scale=3, symbol="BD")
