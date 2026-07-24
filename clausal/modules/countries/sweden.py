"""Sweden — krona."""
from clausal.modules.countries._currency import _make_currency

krona = _make_currency("krona", iso_code="SEK", scale=2, symbol="SEK", start="1873-05-27", end=None)
