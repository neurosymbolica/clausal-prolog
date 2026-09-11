"""Argentina — peso, austral, ley, peso_1881_1970, peso_1983_1985."""
from clausal.modules.countries._currency import _make_currency

ars = _make_currency("peso", iso_code="ARS", scale=2, symbol="ARS", start="1992-01-01", end=None)
austral = _make_currency("austral", iso_code="ARA", scale=2, symbol="ARA", start="1985-06-14", end="1992-01-01", historical=True)
ley = _make_currency("ley", iso_code="ARL", scale=2, symbol="ARL", start="1970-01-01", end="1983-06-01", historical=True)
peso_1881_1970 = _make_currency("peso_1881_1970", iso_code="ARM", scale=2, symbol="ARM", start="1881-11-05", end="1970-01-01", historical=True)
peso_1983_1985 = _make_currency("peso_1983_1985", iso_code="ARP", scale=2, symbol="ARP", start="1983-06-01", end="1985-06-14", historical=True)
