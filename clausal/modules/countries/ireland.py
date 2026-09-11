"""Ireland — pound."""
from clausal.modules.countries._currency import _make_currency

iep = _make_currency("pound", iso_code="IEP", scale=2, symbol="IEP", start="1922-01-01", end="2002-02-09", historical=True)
