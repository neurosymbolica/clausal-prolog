"""Hong Kong Sar China — dollar."""
from clausal.modules.countries._currency import _make_currency

dollar = _make_currency("dollar", iso_code="HKD", scale=2, symbol="HK$", start="1895-02-02", end=None)
