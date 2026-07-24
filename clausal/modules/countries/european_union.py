"""European Union — euro."""
from clausal.modules.countries._currency import _make_currency

euro = _make_currency("euro", iso_code="EUR", scale=2, symbol="€", start="1999-01-01", end=None)
