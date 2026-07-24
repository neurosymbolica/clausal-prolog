"""South Africa — rand."""
from clausal.modules.countries._currency import _make_currency

rand = _make_currency("rand", iso_code="ZAR", scale=2, symbol="ZAR", start="1961-02-14", end=None)
