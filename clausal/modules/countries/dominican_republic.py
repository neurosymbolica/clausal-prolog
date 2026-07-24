"""Dominican Republic — peso."""
from clausal.modules.countries._currency import _make_currency

peso = _make_currency("peso", iso_code="DOP", scale=2, symbol="DOP", start="1947-10-01", end=None)
