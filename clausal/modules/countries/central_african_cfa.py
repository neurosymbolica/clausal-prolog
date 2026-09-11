"""Central African Cfa — franc."""
from clausal.modules.countries._currency import _make_currency

xaf = _make_currency("franc", iso_code="XAF", scale=0, symbol="FCFA", start="1973-04-01", end=None)
