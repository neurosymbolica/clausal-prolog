"""France — franc."""
from clausal.modules.countries._currency import _make_currency

frf = _make_currency("franc", iso_code="FRF", scale=2, symbol="FRF", start="1959-01-01", end="2002-02-17", historical=True)
