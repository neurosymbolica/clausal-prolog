"""Madagascar — ariary, franc."""
from clausal.modules.countries._currency import _make_currency

ariary = _make_currency("ariary", iso_code="MGA", scale=2, symbol="MGA", start="1983-11-01", end=None)
franc = _make_currency("franc", iso_code="MGF", scale=2, symbol="MGF", start="1963-07-01", end="2004-12-31", historical=True)
