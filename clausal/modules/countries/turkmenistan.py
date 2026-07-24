"""Turkmenistan — manat, manat_1993_2009."""
from clausal.modules.countries._currency import _make_currency

manat = _make_currency("manat", iso_code="TMT", scale=2, symbol="TMT", start="2009-01-01", end=None)
manat_1993_2009 = _make_currency("manat_1993_2009", iso_code="TMM", scale=2, symbol="TMM", start="1993-11-01", end="2009-01-01", historical=True)
