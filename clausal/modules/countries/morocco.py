"""Morocco — dirham, franc."""
from clausal.modules.countries._currency import _make_currency

dirham = _make_currency("dirham", iso_code="MAD", scale=2, symbol="MAD", start="1959-10-17", end=None)
franc = _make_currency("franc", iso_code="MAF", scale=2, symbol="MAF", start="1881-01-01", end="1959-10-17", historical=True)
