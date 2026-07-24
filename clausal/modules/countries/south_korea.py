"""South Korea — won, hwan, won_1945_1953."""
from clausal.modules.countries._currency import _make_currency

won = _make_currency("won", iso_code="KRW", scale=0, symbol="₩", start="1962-06-10", end=None)
hwan = _make_currency("hwan", iso_code="KRH", scale=2, symbol="KRH", start="1953-02-15", end="1962-06-10", historical=True)
won_1945_1953 = _make_currency("won_1945_1953", iso_code="KRO", scale=2, symbol="KRO", start="1945-08-15", end="1953-02-15", historical=True)
