"""Uruguay — peso, peso_1975_1993."""
from clausal.modules.countries._currency import _make_currency

peso = _make_currency("peso", iso_code="UYU", scale=2, symbol="UYU", start="1993-03-01", end=None)
peso_1975_1993 = _make_currency("peso_1975_1993", iso_code="UYP", scale=2, symbol="UYP", start="1975-07-01", end="1993-03-01", historical=True)
