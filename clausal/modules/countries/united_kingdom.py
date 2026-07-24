"""United Kingdom — sterling."""
from clausal.modules.countries._currency import _make_currency

sterling = _make_currency("sterling", iso_code="GBP", scale=2, symbol="£", start="1694-07-27", end=None)
