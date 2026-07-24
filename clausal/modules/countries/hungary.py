"""Hungary — forint."""
from clausal.modules.countries._currency import _make_currency

forint = _make_currency("forint", iso_code="HUF", scale=2, symbol="HUF", start="1946-07-23", end=None)
