"""Thailand — baht."""
from clausal.modules.countries._currency import _make_currency, _make_minor_unit

baht = _make_currency("baht", iso_code="THB", scale=2, symbol="THB", start="1928-04-15", end=None)
satang = _make_minor_unit(baht)
