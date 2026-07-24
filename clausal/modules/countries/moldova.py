"""Moldova — leu, cupon."""
from clausal.modules.countries._currency import _make_currency

leu = _make_currency("leu", iso_code="MDL", scale=2, symbol="MDL", start="1993-11-29", end=None)
cupon = _make_currency("cupon", iso_code="MDC", scale=2, symbol="MDC", start="1992-06-01", end="1993-11-29", historical=True)
