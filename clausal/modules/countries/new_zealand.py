"""New Zealand — dollar."""
from clausal.modules.countries._currency import _make_currency

dollar = _make_currency("dollar", iso_code="NZD", scale=2, symbol="NZ$")
