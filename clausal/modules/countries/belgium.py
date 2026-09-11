"""Belgium — franc."""
from clausal.modules.countries._currency import _make_currency

bef = _make_currency("franc", iso_code="BEF", scale=2, symbol="BEF", start="1831-02-07", end="2002-02-28", historical=True)
