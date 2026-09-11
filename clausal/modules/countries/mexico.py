"""Mexico — peso, silver_peso."""
from clausal.modules.countries._currency import _make_currency

mxn = _make_currency("peso", iso_code="MXN", scale=2, symbol="MX$", start="1993-01-01", end=None)
silver_peso = _make_currency("silver_peso", iso_code="MXP", scale=2, symbol="MXP", start="1822-01-01", end="1992-12-31", historical=True)
