"""Georgia — lari, larit."""
from clausal.modules.countries._currency import _make_currency

lari = _make_currency("lari", iso_code="GEL", scale=2, symbol="GEL", start="1995-09-23", end=None)
larit = _make_currency("larit", iso_code="GEK", scale=2, symbol="GEK", start="1993-04-05", end="1995-09-25", historical=True)
