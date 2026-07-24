"""Israel — shekel, pound, shekel_1980_1985."""
from clausal.modules.countries._currency import _make_currency

shekel = _make_currency("shekel", iso_code="ILS", scale=2, symbol="₪", start="1985-09-04", end=None)
pound = _make_currency("pound", iso_code="ILP", scale=2, symbol="ILP", start="1948-08-16", end="1980-02-22", historical=True)
shekel_1980_1985 = _make_currency("shekel_1980_1985", iso_code="ILR", scale=2, symbol="ILR", start="1980-02-22", end="1985-09-04", historical=True)
