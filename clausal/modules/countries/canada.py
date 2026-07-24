"""Canada — dollar."""
from clausal.modules.countries._currency import _make_currency

dollar = _make_currency("dollar", iso_code="CAD", scale=2, symbol="CA$", start="1858-01-01", end=None)
