"""Zambia — kwacha, kwacha_1968_2013."""
from clausal.modules.countries._currency import _make_currency

kwacha = _make_currency("kwacha", iso_code="ZMW", scale=2, symbol="ZMW", start="2013-01-01", end=None)
kwacha_1968_2013 = _make_currency("kwacha_1968_2013", iso_code="ZMK", scale=2, symbol="ZMK", start="1968-01-16", end="2013-01-01", historical=True)
