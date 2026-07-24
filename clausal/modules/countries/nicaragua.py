"""Nicaragua — cordoba, cordoba_1988_1991."""
from clausal.modules.countries._currency import _make_currency

cordoba = _make_currency("cordoba", iso_code="NIO", scale=2, symbol="NIO", start="1991-04-30", end=None)
cordoba_1988_1991 = _make_currency("cordoba_1988_1991", iso_code="NIC", scale=2, symbol="NIC", start="1988-02-15", end="1991-04-30", historical=True)
