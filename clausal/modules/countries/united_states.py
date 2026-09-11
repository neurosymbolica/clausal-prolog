"""United States — dollar."""
from clausal.modules.countries._currency import _make_currency, _make_minor_unit

usd = _make_currency("dollar", iso_code="USD", scale=2, symbol="$", start="1792-01-01", end=None)
usd_cent = _make_minor_unit(usd)
