"""United States — dollar."""
from clausal.modules.countries._currency import _make_currency

dollar = _make_currency("dollar", iso_code="USD", scale=2, symbol="$", start="1792-01-01", end=None)
