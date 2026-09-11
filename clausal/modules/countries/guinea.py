"""Guinea — franc, syli."""
from clausal.modules.countries._currency import _make_currency

gnf = _make_currency("franc", iso_code="GNF", scale=0, symbol="GNF", start="1986-01-06", end=None)
syli = _make_currency("syli", iso_code="GNS", scale=2, symbol="GNS", start="1972-10-02", end="1986-01-06", historical=True)
