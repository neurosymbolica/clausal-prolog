"""United Kingdom — sterling."""
from clausal.modules.countries._currency import _make_currency

sterling = _make_currency("sterling", iso_code="GBP", scale=2, symbol="£")
