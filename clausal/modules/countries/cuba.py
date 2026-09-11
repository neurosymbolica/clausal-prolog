"""Cuba — peso, convertible_peso."""
from clausal.modules.countries._currency import _make_currency

cup = _make_currency("peso", iso_code="CUP", scale=2, symbol="CUP", start="1859-01-01", end=None)
convertible_peso = _make_currency("convertible_peso", iso_code="CUC", scale=2, symbol="CUC", start="1994-01-01", end="2021-01-01", historical=True)
