"""Monaco — franc."""
from clausal.modules.countries._currency import _make_currency

mcf = _make_currency("franc", iso_code="MCF", scale=2, symbol="MCF", start="1960-01-01", end="2002-02-17", historical=True)
