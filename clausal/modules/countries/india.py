"""India — rupee."""
from clausal.modules.countries._currency import _make_currency

inr = _make_currency("rupee", iso_code="INR", scale=2, symbol="₹", start="1835-08-17", end=None)
