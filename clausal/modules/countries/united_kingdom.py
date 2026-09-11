"""United Kingdom — sterling."""
from clausal.modules.countries._currency import _make_currency, _make_minor_unit

sterling = _make_currency("sterling", iso_code="GBP", scale=2, symbol="£", start="1694-07-27", end=None)
penny = _make_minor_unit(sterling)
