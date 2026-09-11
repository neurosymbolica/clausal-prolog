"""Taiwan — dollar."""
from clausal.modules.countries._currency import _make_currency

twd = _make_currency("dollar", iso_code="TWD", scale=2, symbol="NT$", start="1949-06-15", end=None)
