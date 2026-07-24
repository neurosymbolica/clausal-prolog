"""Chile — peso, escudo."""
from clausal.modules.countries._currency import _make_currency

peso = _make_currency("peso", iso_code="CLP", scale=0, symbol="CLP", start="1975-09-29", end=None)
escudo = _make_currency("escudo", iso_code="CLE", scale=2, symbol="CLE", start="1960-01-01", end="1975-09-29", historical=True)
