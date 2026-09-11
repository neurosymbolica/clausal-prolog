"""Mali — franc."""
from clausal.modules.countries._currency import _make_currency

mlf = _make_currency("franc", iso_code="MLF", scale=2, symbol="MLF", start="1962-07-02", end="1984-08-31", historical=True)
