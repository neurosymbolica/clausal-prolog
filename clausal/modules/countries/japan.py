"""Japan — yen."""
from clausal.modules.countries._currency import _make_currency

yen = _make_currency("yen", iso_code="JPY", scale=0, symbol="¥", start="1871-06-01", end=None)
