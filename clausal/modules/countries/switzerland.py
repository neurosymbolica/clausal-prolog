"""Switzerland — franc."""
from clausal.modules.countries._currency import _make_currency

franc = _make_currency("franc", iso_code="CHF", scale=2, symbol="CHF")
