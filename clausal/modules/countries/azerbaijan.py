"""Azerbaijan — manat, manat_1993_2006."""
from clausal.modules.countries._currency import _make_currency

manat = _make_currency("manat", iso_code="AZN", scale=2, symbol="AZN", start="2006-01-01", end=None)
manat_1993_2006 = _make_currency("manat_1993_2006", iso_code="AZM", scale=2, symbol="AZM", start="1993-11-22", end="2006-12-31", historical=True)
