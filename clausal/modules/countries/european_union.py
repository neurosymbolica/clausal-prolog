"""European Union — euro."""
from clausal.modules.countries._currency import _make_currency, _make_minor_unit

euro = _make_currency("euro", iso_code="EUR", scale=2, symbol="€", start="1999-01-01", end=None)
cent = _make_minor_unit(euro)
