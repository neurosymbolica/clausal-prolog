"""Poland — zloty, zloty_1950_1994."""
from clausal.modules.countries._currency import _make_currency

zloty = _make_currency("zloty", iso_code="PLN", scale=2, symbol="PLN", start="1995-01-01", end=None)
zloty_1950_1994 = _make_currency("zloty_1950_1994", iso_code="PLZ", scale=2, symbol="PLZ", start="1950-10-28", end="1994-12-31", historical=True)
