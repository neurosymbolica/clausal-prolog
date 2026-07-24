"""Denmark — krone."""
from clausal.modules.countries._currency import _make_currency

krone = _make_currency("krone", iso_code="DKK", scale=2, symbol="DKK", start="1873-05-27", end=None)
