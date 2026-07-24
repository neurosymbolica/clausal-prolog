"""Cyprus — pound."""
from clausal.modules.countries._currency import _make_currency

pound = _make_currency("pound", iso_code="CYP", scale=2, symbol="CYP", start="1914-09-10", end="2008-01-31", historical=True)
