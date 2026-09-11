"""Australia — dollar."""
from clausal.modules.countries._currency import _make_currency, _make_minor_unit

aud = _make_currency("dollar", iso_code="AUD", scale=2, symbol="A$", start="1966-02-14", end=None)
aud_cent = _make_minor_unit(aud)
