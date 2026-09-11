"""Malta — lira, pound."""
from clausal.modules.countries._currency import _make_currency

mtl = _make_currency("lira", iso_code="MTL", scale=2, symbol="MTL", start="1968-06-07", end="2008-01-31", historical=True)
mtp = _make_currency("pound", iso_code="MTP", scale=2, symbol="MTP", start="1914-08-13", end="1968-06-07", historical=True)
