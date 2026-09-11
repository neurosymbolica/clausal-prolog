"""Switzerland — franc."""
from clausal.modules.countries._currency import _make_currency

chf = _make_currency("franc", iso_code="CHF", scale=2, symbol="CHF", start="1799-03-17", end=None)
