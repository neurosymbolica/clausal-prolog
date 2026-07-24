"""Romania — leu, leu_1952_2006."""
from clausal.modules.countries._currency import _make_currency

leu = _make_currency("leu", iso_code="RON", scale=2, symbol="RON", start="2005-07-01", end=None)
leu_1952_2006 = _make_currency("leu_1952_2006", iso_code="ROL", scale=2, symbol="ROL", start="1952-01-28", end="2006-12-31", historical=True)
