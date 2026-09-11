"""Australia — dollar."""
from clausal.modules.countries._currency import _make_currency, _make_minor_unit

dollar = _make_currency("dollar", iso_code="AUD", scale=2, symbol="A$", start="1966-02-14", end=None)
cent = _make_minor_unit(dollar)
