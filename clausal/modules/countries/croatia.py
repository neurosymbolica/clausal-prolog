"""Croatia — dinar, kuna."""
from clausal.modules.countries._currency import _make_currency

hrd = _make_currency("dinar", iso_code="HRD", scale=2, symbol="HRD", start="1991-12-23", end="1995-01-01", historical=True)
kuna = _make_currency("kuna", iso_code="HRK", scale=2, symbol="HRK", start="1994-05-30", end="2023-01-14", historical=True)
