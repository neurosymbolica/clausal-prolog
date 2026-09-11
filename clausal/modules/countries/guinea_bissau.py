"""Guinea Bissau — escudo, peso."""
from clausal.modules.countries._currency import _make_currency

gwe = _make_currency("escudo", iso_code="GWE", scale=2, symbol="GWE", start="1914-01-01", end="1976-02-28", historical=True)
gwp = _make_currency("peso", iso_code="GWP", scale=2, symbol="GWP", start="1976-02-28", end="1997-03-31", historical=True)
