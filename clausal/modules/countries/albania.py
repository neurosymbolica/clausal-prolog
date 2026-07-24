"""Albania — lek, lek_1946_1965."""
from clausal.modules.countries._currency import _make_currency

lek = _make_currency("lek", iso_code="ALL", scale=2, symbol="ALL", start="1965-08-16", end=None)
lek_1946_1965 = _make_currency("lek_1946_1965", iso_code="ALK", scale=2, symbol="ALK", start="1946-11-01", end="1965-08-16", historical=True)
