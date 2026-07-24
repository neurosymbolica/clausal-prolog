"""Nigeria — naira."""
from clausal.modules.countries._currency import _make_currency

naira = _make_currency("naira", iso_code="NGN", scale=2, symbol="NGN", start="1973-01-01", end=None)
