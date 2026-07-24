"""Iceland — krona, krona_1918_1981."""
from clausal.modules.countries._currency import _make_currency

krona = _make_currency("krona", iso_code="ISK", scale=0, symbol="ISK", start="1981-01-01", end=None)
krona_1918_1981 = _make_currency("krona_1918_1981", iso_code="ISJ", scale=2, symbol="ISJ", start="1918-12-01", end="1981-01-01", historical=True)
