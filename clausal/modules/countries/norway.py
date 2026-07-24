"""Norway — krone."""
from clausal.modules.countries._currency import _make_currency

krone = _make_currency("krone", iso_code="NOK", scale=2, symbol="NOK", start="1905-06-07", end=None)
