"""Germany — mark."""
from clausal.modules.countries._currency import _make_currency

dem = _make_currency("mark", iso_code="DEM", scale=2, symbol="DEM", start="1948-06-20", end="2002-05-15", historical=True)
