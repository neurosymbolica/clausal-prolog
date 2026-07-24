"""Afghanistan — afghani, afghani_1927_2002."""
from clausal.modules.countries._currency import _make_currency

afghani = _make_currency("afghani", iso_code="AFN", scale=2, symbol="AFN", start="2002-10-07", end=None)
afghani_1927_2002 = _make_currency("afghani_1927_2002", iso_code="AFA", scale=2, symbol="AFA", start="1927-03-14", end="2002-12-31", historical=True)
