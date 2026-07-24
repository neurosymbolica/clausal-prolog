"""Nepal — rupee."""
from clausal.modules.countries._currency import _make_currency

rupee = _make_currency("rupee", iso_code="NPR", scale=2, symbol="NPR", start="1933-01-01", end=None)
